"""Opt-in Job endpoints reuse the real local boundary and retain work on disconnect."""

import asyncio

import httpx
import pytest

from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.agent_store import journal_request
from packages.resume_core.models.background import JobReplayRequestV1
from tests.recovery.test_agent_lifecycle import MetadataAdapter, Tools
from tests.support.agent import isolated_project, run_request
from tests.support.background import PipeExecutions


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True], ids=["disabled", "opt-in"])
async def test_job_routes_capture_on_the_server_and_disconnect_keeps_the_execution(tmp_path, enabled):
    from resume_api.app import create_app
    from resume_api.agent.runtime import ScriptedAgentRuntime
    _, canonical, workspace, conversation = isolated_project(tmp_path / "FoldCV")
    clock = ControlledDeadlines()
    factory = PipeExecutions(tmp_path / "pipes", clock)
    factory.hold_results.add("send_1")
    adapter = MetadataAdapter()
    dist = tmp_path / "dist"
    dist.mkdir(); (dist / "index.html").write_text("synthetic")
    origin, secret = "http://127.0.0.1:39272", "synthetic-background-secret-0123456789"
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist,
        data_root=canonical.root, connection_adapter=adapter, agent_runtime=ScriptedAgentRuntime(None),
        agent_tools=Tools(), background_enabled=enabled, background_factory=factory)
    jobs = app.app.state.jobs
    jobs.supervisor.clock = clock
    prefix = "/v1/rich/projects/" + workspace.project_id + "/jobs"
    try:
        async with app.app.router.lifespan_context(app.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin,
                    headers={"Origin": origin}) as client:
                assert (await client.get(prefix)).status_code == 401
                assert (await client.post("/v1/session/exchange", json={"secret": secret})).status_code == 200
                if not enabled:
                    assert (await client.get(prefix)).json()["error"]["code"] == "JOB_DISABLED"
                    assert not jobs.store.background.exists() and not factory.calls
                    return
                assert (await client.post("/v1/host/status", json={})).status_code == 200
                assert adapter.inspections == 1
                jobs.settings.save(AgentSettingsRequest(expectedRevision=1, enabled=True,
                    selectedAgentModel="assistant-model"), ("assistant-model", "processing-model"))
                context = (await client.get(prefix)).json()
                request = journal_request(run_request(conversation.id, settingsRevision=2))
                payload = {"schemaVersion": 1, "lineage": context["lineage"], "requestEpoch": context["requestEpoch"],
                    "request": request.model_dump(mode="json", by_alias=True)}
                forged = {**payload, "models": [{"model": "forged"}], "schedulingClass": "interactive"}
                assert (await client.post(prefix + "/agent", json=forged)).status_code == 422
                assert not factory.calls
                submitted = await client.post(prefix + "/agent", json=payload)
                assert submitted.status_code == 202, submitted.text
                identifier = submitted.json()["id"]
                job = jobs.store.read(workspace.project_id, identifier)
                actor = await factory.actor(job)
                await asyncio.wait_for(actor.started.wait(), 10)
                replay = await client.post(prefix + "/agent", json=payload)
                assert replay.status_code == 200 and replay.json()["id"] == identifier
                stream = jobs.stream(workspace.project_id, identifier,
                    JobReplayRequestV1(schemaVersion=1, generation=1, after=0))
                assert b'"jobId"' in await anext(stream)
                await stream.aclose()
                assert not jobs.supervisor.listeners
                assert actor.child.command("probe") == {"type": "alive"}
                read = await client.post(prefix + "/" + identifier + "/read", json={})
                assert read.json()["execution"] == "running"
                legacy = await client.post(prefix + "/" + identifier + "/legacy-v2", json={})
                assert legacy.json()["schemaVersion"] == 2 and legacy.json()["run"]["state"] == "running"
                await client.post(prefix + "/" + identifier + "/cancel", json={})
                await asyncio.wait_for(jobs.supervisor.controls[identifier].task, 10)
                assert not jobs.admission.locked()
                result = await client.post(prefix + "/" + identifier + "/replay",
                    json={"schemaVersion": 1, "generation": 1, "after": 0})
                assert result.json()["events"][-1]["snapshot"]["execution"] == "cancelled"
                assert adapter.inspections == 1 and factory.calls == [(identifier, "agent")]
    finally:
        await jobs.shutdown()
        factory.verify(); clock.verify()
