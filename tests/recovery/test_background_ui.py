"""Global background summaries and actions use the real isolated HTTP boundary."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from packages.resume_core.models.background import JobIndexV1
from spikes.background.writer_bridge import Bridge
from spikes.background.fixed_fixtures import FixedProofProvider
from tests.recovery.test_background_agent import hold_writer
from tests.recovery.test_background_fixed_jobs import fixed_request, rewrite_command


@asynccontextmanager
async def opened(tmp_path):
    bridge = Bridge(tmp_path)
    bridge.send = lambda value: None
    await bridge.start()
    try:
        yield bridge
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_global_index_is_authenticated_disabled_and_read_only(tmp_path):
    async with opened(tmp_path) as bridge:
        client, service = bridge.client, bridge.service
        path = "/v1/background/jobs"
        service.project(bridge.project)
        before = bridge.stats(bridge.project)
        raw = {str(path): path.read_bytes() for path in service.store.root.rglob("*.json")}
        for _ in range(2):
            response = await client.get(path)
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert JobIndexV1.model_validate(response.json()).jobs == []
        after = bridge.stats(bridge.project)
        assert after["workspaceSha256"] == before["workspaceSha256"]
        assert after["syntheticStarts"] == 0 and after["fixedStarts"] == 0
        assert {str(path): path.read_bytes() for path in service.store.root.rglob("*.json")} == raw
        assert (await client.get(path, headers={"Origin": "http://127.0.0.1:1"})).status_code == 403
        cookies = dict(client.cookies)
        client.cookies.clear()
        assert (await client.get(path)).status_code == 401
        client.cookies.update(cookies)
        service.enabled = False
        denied = await client.get(path)
        assert denied.status_code == 409 and denied.json()["error"]["code"] == "JOB_DISABLED"


@pytest.mark.asyncio
async def test_global_exact_stop_leaves_another_project_job_to_save(tmp_path):
    async with opened(tmp_path) as bridge:
        other = await bridge.handle({"kind": "clone"})
        projects = (bridge.project, other["project"])
        for project in projects:
            await bridge.handle({"kind": "fixed_fixture", "project": project})
        reached = asyncio.Event()
        bridge.send = lambda value: reached.set() if value.get("event") == "hook" else None
        await bridge.handle({"kind": "hold", "name": "fixed_model_ready", "family": "job", "token": "two-projects"})
        jobs = []
        for index, project in enumerate(projects):
            workspace = bridge.service.projects.storage.read_committed(project)[0]
            request = fixed_request(bridge.service, project, "global-" + str(index), rewrite_command(workspace))
            response = await bridge.client.post(f"/v1/rich/projects/{project}/jobs/fixed", json=request.model_dump(mode="json", by_alias=True))
            assert response.status_code == 202, response.text
            jobs.append(response.json()["job"]["id"])
            if index == 0:
                await asyncio.wait_for(reached.wait(), 10)
        await asyncio.wait_for(reached.wait(), 10)
        response = await bridge.client.get("/v1/background/jobs")
        index = JobIndexV1.model_validate(response.json())
        assert {(row.project_id, row.job_id) for row in index.jobs} == set(zip(projects, jobs))
        assert all(not row.saved and row.project_title for row in index.jobs)
        assert "submission" not in response.text and "document" not in response.text and "credential" not in response.text
        stopped = await bridge.client.post(f"/v1/rich/projects/{projects[0]}/jobs/{jobs[0]}/cancel", json={})
        assert stopped.status_code == 200 and stopped.json()["execution"] in {"cancelling", "cancelled"}
        await bridge.handle({"kind": "release", "token": "two-projects"})
        for project, job in zip(projects, jobs):
            await bridge.handle({"kind": "wait_fixed", "project": project, "job": job})
        final = JobIndexV1.model_validate((await bridge.client.get("/v1/background/jobs")).json())
        first, second = (next(row for row in final.jobs if row.project_id == project) for project in projects)
        assert first.execution == "cancelled" and not first.saved
        assert second.execution == "completed" and second.saved
        saved = bridge.stats(projects[1])["workspaceSha256"]
        discarded = await bridge.client.post(f"/v1/rich/projects/{projects[1]}/jobs/{jobs[1]}/discard", json={})
        assert discarded.status_code == 200 and discarded.json()["publication"] == "saved"
        assert bridge.stats(projects[1])["workspaceSha256"] == saved
        assert bridge.stats(projects[0])["fixedStarts"] == 1


@pytest.mark.asyncio
async def test_discard_rejects_unresolved_commit_and_cross_project_job(tmp_path):
    async with opened(tmp_path) as bridge:
        await bridge.handle({"kind": "fixed_fixture"})
        service, project = bridge.service, bridge.project
        workspace = service.projects.storage.read_committed(project)[0]
        hold_writer(service, workspace)
        request = fixed_request(service, project, "unknown-discard", rewrite_command(workspace))
        reply, _created = await service.fixed.submit(project, request)
        await bridge.handle({"kind": "wait_fixed", "job": reply.job.id})
        assert service.store.read(project, reply.job.id).publication == "waiting_for_sync"
        before = bridge.stats(project)["workspaceSha256"]
        other = await bridge.handle({"kind": "clone"})
        missing = await bridge.client.post(f"/v1/rich/projects/{other['project']}/jobs/{reply.job.id}/discard", json={})
        assert missing.status_code == 404
        def uncertain(_state, row):
            row.publication, row.receipt = "outcome_unknown", None
        service.store.update(project, reply.job.id, uncertain)
        denied = await bridge.client.post(f"/v1/rich/projects/{project}/jobs/{reply.job.id}/discard", json={})
        assert denied.status_code == 409 and denied.json()["error"]["code"] == "OUTCOME_UNKNOWN"
        assert bridge.stats(project)["workspaceSha256"] == before


@pytest.mark.asyncio
async def test_reloaded_fixed_metadata_preserves_dependency_kinds_and_durability(tmp_path):
    async with opened(tmp_path) as bridge:
        service, project = bridge.service, bridge.project
        provider = FixedProofProvider()
        service.projects.provider_factory = lambda: (provider, "processing-model")
        request = fixed_request(service, project, "metadata-durability", {"kind": "completion", "request": {
            "capture": {"sessionId": "nb06-cache", "actionId": "nb06-cache:1", "actionToken": 0, "dependencies": []},
            "blockIds": ["narrative", "quote"], "movedIds": [], "removedFields": [], "removedRecordIds": [], "interpret": False}})
        reply, _created = await service.fixed.submit(project, request)
        await bridge.handle({"kind": "wait_fixed", "job": reply.job.id})
        committed = service.projects.storage.read_committed(project)[0]
        record = next(record for record in committed.sync_records if record.id == reply.sync_id)
        assert {stamp.kind for stamp in record.dependencies} >= {"block", "ownership"}
        for _ in range(3):
            response = service.projects.response(project)
            assert response.durability == "durable"
            assert response.workspace == committed
            cached = next(record for record in service.projects.workspaces[project].sync_records if record.id == reply.sync_id)
            assert len({id(stamp) for stamp in cached.dependencies}) == len(cached.dependencies)
            assert cached.dependencies == record.dependencies
        assert len(service.store.read(project, reply.job.id).attempts) == 1
        assert not bridge.factory.calls and not provider.calls
