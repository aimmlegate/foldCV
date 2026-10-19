"""Disabling the assistant revokes every agent owner without stopping fixed jobs."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.agent import AgentQuery, AgentSettingsRequest
from tests.recovery.test_background_agent import environment
from tests.recovery.test_background_store import capture
from resume_api.agent.routes import mount_agent


@pytest.mark.asyncio
async def test_settings_disable_cancels_running_and_queued_agents_and_keeps_fixed_work(tmp_path):
    jobs, factory, workspace, payload, connection, foreground = await environment(tmp_path)
    project = workspace.project_id
    factory.hold_results.add(payload.request.client_request_id)
    try:
        running, _ = await jobs.submit(project, payload)
        actor = await factory.actor(running)
        await asyncio.wait_for(actor.started.wait(), 10)
        queued_payload = payload.model_copy(deep=True)
        queued_payload.request.client_request_id = "queued-agent"
        queued, _ = await jobs.submit(project, queued_payload)
        jobs.supervisor.dispatch_enabled = False
        fixed, _ = jobs.store.submit(capture(jobs.store.load(project), "fixed-rewrite", kind="rewrite",
            schedulingClass="interactive", tools=[], input={"kind": "rich_sync", "id": "fixed-input", "sha256": "a" * 64},
            models=[{"stage": "rewrite", "model": "assistant-model", "configSha256": "a" * 64}]))
        before_fixed = jobs.store.read(project, fixed.id)
        app = FastAPI()
        mount_agent(app, foreground)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = await client.put("/v1/settings/assistant", json={"expectedRevision": 2, "enabled": False,
                "selectedAgentModel": "assistant-model"})
            assert result.status_code == 200, result.text
            assert result.json()["enabled"] is False
        assert jobs.store.read(project, running.id).execution == "cancelled"
        assert jobs.store.read(project, queued.id).execution == "cancelled"
        assert jobs.store.read(project, fixed.id) == before_fixed
        assert len(factory.calls) == 1 and not jobs.admission.locked()
        assert jobs.preflight(queued) == "JOB_DISABLED"
        session = jobs.tools.session(jobs.supervisor.controls[running.id])
        try:
            assert (await session.call("get_resume_context", AgentQuery(kind="context")))["error"]["code"] == "AGENT_DISABLED"
        finally:
            await session.close()
        with pytest.raises(BackgroundFailure, match="JOB_DISABLED"):
            jobs.publication.publish(project, queued.id, "a" * 64)
        jobs.settings.save(AgentSettingsRequest(expectedRevision=3, enabled=True,
            selectedAgentModel="assistant-model"), connection["value"].models)
        assert jobs.store.read(project, running.id).execution == "cancelled"
        assert jobs.store.read(project, queued.id).execution == "cancelled"
        assert factory.calls == [(running.id, "agent")]
    finally:
        await jobs.shutdown()
        factory.verify(); jobs.supervisor.clock.verify()
