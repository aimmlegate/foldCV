"""Authenticated writer routes use canonical authority without model admission."""

import httpx
import pytest

from packages.resume_core.models.rich_workspace import WorkspaceV6
from tests.recovery.test_agent_lifecycle import MetadataAdapter, Tools
from tests.recovery.test_background_inverse import mutation, put
from tests.support.agent import isolated_project


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True], ids=["disabled", "opt-in"])
async def test_writer_api_saves_only_through_the_current_connection_and_exact_watermark(tmp_path, enabled):
    from resume_api.app import create_app
    from resume_api.agent.runtime import ScriptedAgentRuntime
    _old, canonical, workspace, _conversation = isolated_project(tmp_path / "FoldCV")
    dist = tmp_path / "dist"; dist.mkdir(); (dist / "index.html").write_text("synthetic")
    adapter = MetadataAdapter()
    origin, secret = "http://127.0.0.1:39273", "synthetic-writer-service-secret-0123456789"
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist,
        data_root=canonical.root, connection_adapter=adapter, agent_runtime=ScriptedAgentRuntime(None),
        agent_tools=Tools(), background_enabled=enabled)
    prefix = "/v1/rich/projects/" + workspace.project_id
    async with app.app.router.lifespan_context(app.app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin,
                headers={"Origin": origin}) as client:
            assert (await client.get(prefix + "/writer")).status_code == 401
            assert (await client.post("/v1/session/exchange", json={"secret": secret})).status_code == 200
            bootstrap = await client.get(prefix + "/writer")
            if not enabled:
                assert bootstrap.json()["error"]["code"] == "JOB_DISABLED"
                assert not app.app.state.jobs.store.background.exists()
                return
            assert bootstrap.status_code == 200, bootstrap.text
            initial = bootstrap.json()
            opened = await client.post(prefix + "/writer/open", json={"schemaVersion": 1, "sessionId": "editor-session",
                "incarnation": "first-connection", "credential": "synthetic_writer_credential_0123456789",
                "canonicalRevision": initial["response"]["workspace"]["projectRevision"],
                "canonicalSha256": initial["workspaceSha256"], "actionCursor": 0})
            assert opened.status_code == 200, opened.text
            view = opened.json(); writer = view["writer"]
            proof = {"schemaVersion": 1, "lineage": writer["lineage"], "epoch": writer["epoch"],
                "sessionId": writer["sessionId"], "incarnation": writer["incarnation"],
                "credential": "synthetic_writer_credential_0123456789"}
            before = WorkspaceV6.model_validate(view["response"]["workspace"])
            command = mutation(before, [put(before, "narrative", text="Writer route input")], "writer-route")
            command.capture.session_id = proof["sessionId"]
            raw = command.model_dump(mode="json", by_alias=True)
            legacy = await client.post(prefix + "/mutations", json=raw)
            assert legacy.status_code == 409 and legacy.json()["error"]["code"] == "WRITER_UNKNOWN"
            assert canonical.read_committed(workspace.project_id)[0] == before
            payload = {"schemaVersion": 1, "proof": proof, "canonicalRevision": before.project_revision,
                "canonicalSha256": view["workspaceSha256"], "actionCursor": 1,
                "touches": [{"cursor": 1, "mutation": raw}], "mutation": raw}
            saved = await client.post(prefix + "/writer/save", json=payload)
            assert saved.status_code == 200, saved.text
            current = saved.json()
            assert current["canonicalReady"] and current["response"]["durability"] == "durable"
            assert current["writer"]["acknowledgedCursor"] == 1
            assert current["writer"]["acknowledgedSha256"] == current["workspaceSha256"]
            assert current["response"]["workspace"]["projectRevision"] == before.project_revision + 1
            replay = await client.post(prefix + "/writer/save", json=payload)
            assert replay.status_code == 200 and replay.json()["replayed"]
            stale = {**payload, "proof": {**proof, "incarnation": "wrong-connection"}, "mutation": {**raw, "clientMutationId": "new-command"}}
            rejected = await client.post(prefix + "/writer/save", json=stale)
            assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "WRITER_UNKNOWN"
            detached = await client.post(prefix + "/writer/detach", json={"schemaVersion": 1, "proof": proof,
                "canonicalRevision": current["response"]["workspace"]["projectRevision"],
                "canonicalSha256": current["workspaceSha256"], "actionCursor": 1, "touches": []})
            assert detached.status_code == 200 and detached.json()["writer"]["status"] == "clean_detached"
            assert not app.app.state.jobs.supervisor.controls and adapter.inspections == 0
