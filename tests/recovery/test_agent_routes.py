"""Assistant routes keep the browser boundary and never start hidden model work."""

from contextlib import asynccontextmanager
import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from packages.resume_core.agent_store import run_in
from packages.resume_core.models.agent import AgentPageRequest, AgentQuery
from packages.resume_core.models.agent import AgentMessage, AgentWebSource, AgentFinding, wire_bytes
from packages.resume_core import agent_limits as limits
from packages.resume_core.preferences import PreferencesStore
from resume_api.agent.edits import prepare
from resume_api.agent.runtime import ScriptedAgentRuntime, RuntimeResult
from resume_api.agent.tools import ToolSession
from resume_api.app import create_app
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_agent_lifecycle import MetadataAdapter, Tools
from tests.recovery.test_agent_tools import Fetcher
from tests.recovery.test_agent_edits import command, replace
from tests.recovery.test_agent_store import maximum_escaped, NOW
from tests.support.agent import isolated_project, run_request

ORIGIN = "http://127.0.0.1:39273"
SECRET = "synthetic-agent-route-secret-0123456789"


@asynccontextmanager
async def application(tmp_path, script):
    _, canonical, workspace, conversation = isolated_project(tmp_path / "FoldCV")
    dist = tmp_path / "dist"; dist.mkdir(); (dist / "index.html").write_text("fixture")
    runtime, adapter = ScriptedAgentRuntime(script), MetadataAdapter()
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
        connection_adapter=adapter, gui_provider=CreationProvider(), data_root=canonical.root,
        agent_runtime=runtime, agent_tools=Tools())
    async with app.app.router.lifespan_context(app.app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
            assert (await client.post("/v1/session/exchange", json={"secret": SECRET})).status_code == 200
            assert (await client.post("/v1/host/status", json={})).status_code == 200
            service = app.app.state.agent
            prefix = f"/v1/rich/projects/{workspace.project_id}/assistant"
            yield client, app, service, workspace, conversation, prefix, runtime, adapter


async def enabled(client):
    result = await client.put("/v1/settings/assistant", json={"expectedRevision": 1, "enabled": True, "selectedAgentModel": "assistant-model"})
    assert result.status_code == 200
    return result.json()


@pytest.mark.asyncio
async def test_settings_capabilities_and_public_reads_are_authenticated_inference_free_and_independent(tmp_path):
    async with application(tmp_path, None) as (client, app, service, workspace, conversation, prefix, runtime, adapter):
        assert (await client.get("/v1/settings/assistant")).json()["enabled"] is False
        assert not service.settings.path.exists()
        saved = await enabled(client)
        assert saved["revision"] == 2 and PreferencesStore(service.projects.storage.root).load().selected_model is None
        capabilities = (await client.get(prefix + "/capabilities")).json()
        assert capabilities["ready"] and all(model["state"] == "unverified" for model in capabilities["models"])
        off = (await client.get(prefix + "/capabilities", headers={"X-FoldCV-Agent-Web": "0", "X-FoldCV-Agent-Edits": "0"})).json()
        assert capabilities["configSha256"] != off["configSha256"]
        assert (await client.post(prefix + "/conversations/read", json={})).json()["items"][0]["id"] == conversation.id
        assert (await client.post(prefix + f"/conversations/{conversation.id}/read", json={})).json()["items"] == []
        assert not runtime.calls and adapter.inspections == 1
        assert (await client.put("/v1/settings/assistant", json={"expectedRevision": 1, "enabled": True, "selectedAgentModel": "processing-model"})).status_code == 409
        assert (await client.put("/v1/settings/assistant", content=b"{}", headers={"Content-Type": "text/plain"})).status_code == 415
        assert (await client.put("/v1/settings/assistant", content=b'{"enabled":true,"enabled":false}', headers={"Content-Type": "application/json"})).status_code == 422
        assert (await client.post(prefix + "/conversations", content=b"", headers={"Content-Type": "application/json"})).status_code == 422
        assert (await client.get(prefix + "/capabilities?token=forbidden")).status_code == 403
        assert (await client.get(prefix + "/capabilities", headers={"Origin": "https://foreign.example"})).status_code == 403
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as stranger:
            assert (await stranger.get(prefix + "/capabilities")).status_code == 401
        assert not runtime.calls


@pytest.mark.asyncio
async def test_unknown_commit_fence_rejects_all_later_edit_and_export_routes_but_keeps_reads(tmp_path):
    async with application(tmp_path, None) as (client, _, service, workspace, _, prefix, runtime, _):
        service.projects.agent_recovery_fences.add(workspace.project_id)
        for tail in ("rewrite", "completion", "panel/preview", "panel/sync", "save", "generation", "export", "archive", "mutations"):
            result = await client.post(f"/v1/rich/projects/{workspace.project_id}/{tail}", json={})
            assert result.status_code == 409 and result.json()["error"]["code"] == "AGENT_OUTCOME_UNKNOWN"
        assert (await client.get(f"/v1/rich/projects/{workspace.project_id}")).status_code == 200
        assert (await client.post(prefix + "/conversations/read", json={})).status_code == 200
        assert not runtime.calls


@pytest.mark.asyncio
async def test_route_send_retry_and_stream_reconnect_preserve_one_run_and_captured_model(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    async def script(value, cancel, emit):
        emit("message.delta", {"text": "Checked "}); entered.set()
        while not release.is_set() and not cancel.is_set(): await asyncio.sleep(0.01)
        return RuntimeResult(state="completed", text="Checked Python", tool_calls=1)
    async with application(tmp_path, script) as (client, _, service, workspace, conversation, prefix, runtime, _):
        await enabled(client)
        owner = (await client.post(prefix + "/lease/open", json={"sessionId": "history_1"})).json()["owner"]
        payload = run_request(conversation.id, owner=owner, settingsRevision=2).model_dump(mode="json", by_alias=True)
        run = (await client.post(prefix + f"/conversations/{conversation.id}/runs", json=payload)).json()
        await asyncio.wait_for(entered.wait(), 2)
        assert (await client.post(prefix + "/lease/open", json={"sessionId": "tab_2"})).status_code == 409
        assert (await client.put("/v1/settings/assistant", json={"expectedRevision": 2, "enabled": True, "selectedAgentModel": "processing-model"})).status_code == 200
        assert (await client.post("/v1/host/select", json={"model": "processing-model"})).status_code == 200
        repeated = await client.post(prefix + f"/conversations/{conversation.id}/runs", json=payload)
        assert repeated.status_code == 200 and repeated.json()["id"] == run["id"] and repeated.json()["model"] == "assistant-model"
        release.set(); await asyncio.wait_for(service.controls[run["id"]].task, 2)
        stream = await client.post(prefix + f"/runs/{run['id']}/events", json={"owner": owner, "afterSequence": 0})
        events = [json.loads(line) for line in stream.text.splitlines() if line]
        assert events[-1]["type"] == "run.state_changed" and events[-1]["payload"]["state"] == "completed"
        reconnect = await client.post(prefix + f"/runs/{run['id']}/events", json={"owner": owner, "afterSequence": events[0]["sequence"]})
        assert [json.loads(line)["sequence"] for line in reconnect.text.splitlines() if line] == [event["sequence"] for event in events[1:]]
        assert (await client.post(prefix + f"/runs/{run['id']}/events", json={"owner": owner, "afterSequence": 99999})).json()["error"]["code"] == "AGENT_RESYNC_REQUIRED"
        assert owner["token"] not in stream.text and runtime.calls == ["assistant-model"]
        page = (await client.post(prefix + f"/conversations/{conversation.id}/read", json={})).json()
        assert [message["role"] for message in page["items"]] == ["user", "assistant"]
        assert page["items"][-1]["text"] == "Checked Python"


@pytest.mark.asyncio
async def test_owner_close_and_disabling_cancel_without_resuming_and_foreign_ids_fail(tmp_path):
    entered = asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        while not cancel.is_set(): await asyncio.sleep(0.01)
        return RuntimeResult(state="cancelled", error="AGENT_CANCELLED")
    async with application(tmp_path, script) as (client, _, service, workspace, conversation, prefix, runtime, _):
        await enabled(client)
        owner = (await client.post(prefix + "/lease/open", json={"sessionId": "history_1"})).json()["owner"]
        payload = run_request(conversation.id, owner=owner, settingsRevision=2).model_dump(mode="json", by_alias=True)
        assert (await client.post(prefix + "/conversations/foreign/runs", json=payload)).status_code == 404
        assert (await client.post(prefix + "/runs/foreign/read", json={})).status_code == 404
        assert not runtime.calls
        run = (await client.post(prefix + f"/conversations/{conversation.id}/runs", json=payload)).json()
        await asyncio.wait_for(entered.wait(), 2)
        assert (await client.put("/v1/settings/assistant", json={"expectedRevision": 2, "enabled": False, "selectedAgentModel": "assistant-model"})).status_code == 200
        result = (await client.post(prefix + f"/runs/{run['id']}/read", json={})).json()
        assert result["run"]["state"] == "interrupted" and result["run"]["error"]["code"] == "AGENT_DISABLED"
        assert service.controls[run["id"]].task.done() and runtime.calls == ["assistant-model"]
        assert (await client.post(prefix + "/lease/close", json={"owner": owner})).status_code == 200


@pytest.mark.asyncio
async def test_prepared_save_uses_actual_owner_routes_and_returns_exact_saved_workspace(tmp_path):
    release, entered = asyncio.Event(), asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        while not release.is_set() and not cancel.is_set(): await asyncio.sleep(0.01)
        return RuntimeResult(state="completed", text="Saved", tool_calls=1)
    async with application(tmp_path, script) as (client, _, service, workspace, conversation, prefix, runtime, _):
        await enabled(client)
        owner = (await client.post(prefix + "/lease/open", json={"sessionId": "history_1"})).json()["owner"]
        payload = run_request(conversation.id, owner=owner, settingsRevision=2).model_dump(mode="json", by_alias=True)
        run = (await client.post(prefix + f"/conversations/{conversation.id}/runs", json=payload)).json()
        await asyncio.wait_for(entered.wait(), 2)
        control = service.controls[run["id"]]
        session = ToolSession(service, control, run_in(service.store.load(workspace.project_id), run["id"])[1], Fetcher())
        try:
            read = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
            result = prepare(session, command(replace(read.snapshot, "narrative", 0, 6, "Clear")))
            offer = asyncio.create_task(service.publication.offer(session, result.batch_id))
            await asyncio.sleep(0.02)
            path = prefix + f"/runs/{run['id']}/edits/{result.batch_id}"
            assert (await client.post(path + "/claim", json={"owner": {**owner, "token": "wrong_owner_capability_0123456789"}})).status_code == 409
            claim = (await client.post(path + "/claim", json={"owner": owner})).json()
            commit = await client.post(path + "/commit", json={"owner": owner, "ticket": claim["ticket"], "requestSha256": claim["batch"]["requestSha256"]})
            assert commit.status_code == 200 and commit.json()["receipt"]["durable"]
            receipt = commit.json()["receipt"]
            assert commit.json()["project"]["workspace"]["mutationReplay"][-1]["requestSha256"] == receipt["requestSha256"]
            assert (await client.post(path + "/result", json={"owner": owner, "receipt": receipt})).json() == receipt
            assert (await offer).durable
            release.set(); await asyncio.wait_for(control.task, 2)
            assert runtime.calls == ["assistant-model"]
            assert (await client.post(prefix + f"/runs/{run['id']}/read", json={})).json()["receipts"][0]["durable"]
        finally:
            release.set(); await session.close()


def test_latest_pages_keep_their_anchor_while_new_messages_arrive(tmp_path):
    store, _, workspace, conversation = isolated_project(tmp_path / "FoldCV")
    for index in range(3):
        request = run_request(conversation.id, clientRequestId="send_" + str(index))
        run, _ = store.submit(workspace.project_id, request, model="assistant-model", connection_epoch="account_1")
        store.finish(workspace.project_id, run.id, "completed", text="Reply " + str(index), native_completed=True)
    first = store.latest_messages_page(workspace.project_id, conversation.id, AgentPageRequest(limit=2))
    run, _ = store.submit(workspace.project_id, run_request(conversation.id, clientRequestId="later"), model="assistant-model", connection_epoch="account_1")
    store.finish(workspace.project_id, run.id, "completed", text="Later", native_completed=True)
    second = store.latest_messages_page(workspace.project_id, conversation.id, AgentPageRequest(limit=2, cursor=first.next_cursor))
    assert first.items[-1].text == "Reply 2" and second.items[-1].text == "Reply 1"
    assert not {message.id for message in first.items} & {message.id for message in second.items}


def test_conversation_pages_open_the_latest_and_keep_older_pages_stable_after_append(tmp_path):
    store, _, workspace, first = isolated_project(tmp_path / "FoldCV")
    second = store.create_conversation(workspace.project_id)
    latest = store.conversations_page(workspace.project_id, AgentPageRequest(limit=1))
    assert latest.items[0].id == second.id
    store.create_conversation(workspace.project_id)
    older = store.conversations_page(workspace.project_id, AgentPageRequest(limit=1, cursor=latest.next_cursor))
    assert older.items[0].id == first.id and older.next_cursor is None


@pytest.mark.asyncio
async def test_routes_page_maximum_escaped_records_without_inference_or_hidden_fetches(tmp_path):
    async with application(tmp_path, None) as (client, _, service, workspace, conversation, prefix, runtime, _):
        run, _ = service.store.submit(workspace.project_id, run_request(conversation.id), model="assistant-model", connection_epoch="account_1")
        service.store.clock = lambda: NOW
        text = maximum_escaped(AgentMessage, {"id": "m" * 32, "role": "assistant", "runId": run.id,
            "timestamp": NOW, "sources": [], "findings": [], "truncated": True, "error": None}, "text", limits.MESSAGE_BYTES).text
        source = maximum_escaped(AgentWebSource, {"id": "source_0", "runId": run.id,
            "requestedUrl": "https://example.invalid/vacancy", "finalUrl": "https://example.invalid/vacancy",
            "title": "Stored source", "retrievedAt": NOW, "contentSha256": "a" * 64,
            "truncated": True, "originalBytes": 100000}, "text", limits.SOURCE_BYTES)
        finding = maximum_escaped(AgentFinding, {"id": "finding_0", "runId": run.id,
            "severity": "warning", "anchors": [], "sourceIds": []}, "message", limits.FINDING_BYTES)
        def publish(state):
            conv, _, _ = run_in(state, run.id)
            conv.sources.extend(source.model_copy(update={"id": f"source_{i}"}) for i in range(4))
            conv.findings.append(finding)
        service.store.update(workspace.project_id, publish)
        service.store.finish(workspace.project_id, run.id, "completed", text=text, truncated=True, native_completed=True)
        path = prefix + f"/conversations/{conversation.id}"
        messages = await client.post(path + "/read", json={})
        assert messages.json()["items"][-1]["text"] == text and len(messages.content) <= limits.RESPONSE_BYTES
        first = await client.post(path + "/sources/read", json={})
        assert len(first.json()["sources"]) == 3 and len(first.content) <= limits.RESPONSE_BYTES
        second = await client.post(path + "/sources/read", json={"cursor": first.json()["nextCursor"]})
        assert len(second.json()["sources"]) == 1 and second.json()["nextCursor"] is None
        findings = await client.post(path + "/findings/read", json={})
        assert len(wire_bytes(AgentFinding.model_validate(findings.json()["findings"][0]))) == limits.FINDING_BYTES
        assert not runtime.calls
