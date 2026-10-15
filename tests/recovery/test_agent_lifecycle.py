"""Captured choices, owner leases and app lifecycle use only scripted runtime turns."""

import asyncio
from pathlib import Path
import sys
import threading

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.rules import RulesStore
from resume_api.agent.runtime import RuntimeResult, ScriptedAgentRuntime
from resume_api.agent.service import AgentConnection, AgentService
from resume_api.app import create_app
from resume_api.connection import Metadata, Quota
from resume_api.inference_admission import INFERENCE
from resume_api.gui_admission import QueuedProvider
from resume_api.rich_projects import RichProjectService
from tests.recovery.generation_fixtures import CreationProvider
from tests.support.agent import isolated_project, run_request


class ToolSession:
    prompt = "Synthetic Python evidence. Read the resume and check it."
    url = "http://127.0.0.1:12345/mcp"
    token = "synthetic_mcp_capability"
    names = ("get_resume_context", "check_resume")

    def __init__(self, on_close=lambda: None):
        self.closed = False
        self.on_close = on_close

    async def close(self):
        if not self.closed:
            self.on_close()
            self.closed = True


class Tools:
    names = ToolSession.names

    def __init__(self, on_close=lambda: None):
        self.sessions = []
        self.on_close = on_close

    async def open(self, control, run, journal):
        session = ToolSession(self.on_close)
        self.sessions.append(session)
        return session


def setup(tmp_path, script, *, clock=None, on_close=lambda: None):
    _, canonical, workspace, conversation = isolated_project(tmp_path / "FoldCV")
    projects = RichProjectService(tmp_path / "operations", RulesStore(canonical.root), lambda: None, storage=canonical)
    projects.ensure_loaded()
    connection = {"value": AgentConnection(True, ("assistant-model", "processing-model"), "account_1")}
    runtime = ScriptedAgentRuntime(script)
    options = {"lease_clock": clock} if clock is not None else {}
    service = AgentService(projects, runtime, lambda: connection["value"], tools=Tools(on_close), **options)
    projects.agent = service
    service.settings.save(AgentSettingsRequest(expectedRevision=1, enabled=True,
        selectedAgentModel="assistant-model"), connection["value"].models)
    lease = service.leases.open(workspace.project_id, "history_1")
    request = run_request(conversation.id, owner=lease.owner.model_dump(by_alias=True), settingsRevision=2)
    return service, runtime, projects, workspace, conversation, request, connection


@pytest.mark.asyncio
async def test_active_model_is_captured_while_both_preferences_change_and_retry_is_stable(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        await release.wait()
        return RuntimeResult(state="completed", text="Checked with " + value.model, native_started=True, tool_calls=1)
    service, runtime, projects, workspace, conversation, request, _ = setup(tmp_path, script)
    processing = PreferencesStore(projects.storage.root)
    processing.select_model("processing-model")
    run, created = service.submit(workspace.project_id, request)
    assert created and run.model == "assistant-model"
    control = service.start(workspace.project_id, run.id)
    await asyncio.wait_for(entered.wait(), 2)
    processing.select_model("assistant-model")
    service.settings.save(AgentSettingsRequest(expectedRevision=2, enabled=True,
        selectedAgentModel="processing-model"), ("assistant-model", "processing-model"))
    duplicate, created = service.submit(workspace.project_id, request)
    assert not created and duplicate.id == run.id and duplicate.model == "assistant-model"
    release.set()
    await asyncio.wait_for(control.task, 2)
    _, saved, journal = run_in(service.store.load(workspace.project_id), run.id)
    assert saved.state == "completed" and saved.model == "assistant-model"
    assert journal.events[-1].root.type == "run.state_changed" and journal.events[-1].root.payload.state == "completed"
    next_request = run_request(conversation.id, clientRequestId="send_2", owner=request.owner.model_dump(by_alias=True), settingsRevision=3)
    following, _ = service.submit(workspace.project_id, next_request)
    await asyncio.wait_for(service.start(workspace.project_id, following.id).task, 2)
    assert runtime.calls == ["assistant-model", "processing-model"]
    assert processing.load().selected_model == "assistant-model"
    assert service.settings.load().selected_agent_model == "processing-model"
    assert all(session.closed for session in service.tools.sessions)


@pytest.mark.asyncio
async def test_owner_cannot_transfer_active_run_and_expiry_revokes_before_cleanup(tmp_path):
    now = [0.0]
    entered = asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        while not cancel.is_set():
            await asyncio.sleep(0.01)
        return RuntimeResult(state="cancelled", error="AGENT_CANCELLED", native_started=True)
    service, _, _, workspace, _, request, _ = setup(tmp_path, script, clock=lambda: now[0])
    run, _ = service.submit(workspace.project_id, request)
    control = service.start(workspace.project_id, run.id)
    await asyncio.wait_for(entered.wait(), 2)
    for session in ("history_1", "another_tab"):
        with pytest.raises(AgentFailure, match="AGENT_OWNER_MISMATCH"):
            service.leases.open(workspace.project_id, session)
    now[0] = 16
    await asyncio.wait_for(control.task, 2)
    assert control.revoked.is_set() and control.result.error == "AGENT_LEASE_EXPIRED"
    saved = run_in(service.store.load(workspace.project_id), run.id)[1]
    assert saved.state == "interrupted"
    new = service.leases.open(workspace.project_id, "new_history")
    assert new.owner.epoch > request.owner.epoch
    with pytest.raises(AgentFailure, match="AGENT_OWNER_MISMATCH"):
        service.leases.renew(workspace.project_id, request.owner)


@pytest.mark.asyncio
async def test_native_permit_remains_owned_through_deterministic_tool_cleanup(tmp_path):
    order = []
    def closed():
        assert INFERENCE.locked()
        order.append("tool cleanup")
    async def script(value, cancel, emit):
        assert INFERENCE.locked()
        order.append("turn")
        return RuntimeResult(state="completed", text="Checked", native_started=True)
    service, _, _, workspace, _, request, _ = setup(tmp_path, script, on_close=closed)
    run, _ = service.submit(workspace.project_id, request)
    await asyncio.wait_for(service.start(workspace.project_id, run.id).task, 2)
    assert order == ["turn", "tool cleanup"] and not INFERENCE.locked()


@pytest.mark.asyncio
async def test_pending_manual_sync_does_not_block_deterministic_assistant_application(tmp_path):
    order = []
    entered, apply = asyncio.Event(), asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        await apply.wait()
        order.append("apply")
        return RuntimeResult(state="completed", text="Applied", native_started=True)
    service, _, _, workspace, _, request, _ = setup(tmp_path, script, on_close=lambda: order.append("tools closed"))
    run, _ = service.submit(workspace.project_id, request)
    control = service.start(workspace.project_id, run.id)
    await asyncio.wait_for(entered.wait(), 2)
    class ManualSync:
        def generate(self, *_args):
            order.append("manual sync")
            return "manual result"
    waiting = asyncio.create_task(asyncio.to_thread(QueuedProvider(ManualSync(), lambda: None).generate,
        None, None, threading.Event()))
    await asyncio.sleep(0.03)
    assert not waiting.done() and order == []
    apply.set()
    await asyncio.wait_for(control.task, 2)
    assert await asyncio.wait_for(waiting, 2) == "manual result"
    assert order == ["apply", "tools closed", "manual sync"]


@pytest.mark.parametrize("code", ["AGENT_AUTH_REQUIRED", "AGENT_QUOTA", "AGENT_MODEL_INCOMPATIBLE"])
@pytest.mark.asyncio
async def test_only_specific_model_failure_marks_the_captured_configuration_incompatible(tmp_path, code):
    async def script(value, cancel, emit):
        return RuntimeResult(state="failed", error=code, native_started=True)
    service, runtime, _, workspace, _, request, _ = setup(tmp_path, script)
    run, _ = service.submit(workspace.project_id, request)
    await asyncio.wait_for(service.start(workspace.project_id, run.id).task, 2)
    capability = next(model for model in service.capabilities(workspace.project_id).models if model.model == run.model)
    assert capability.state == ("incompatible" if code == "AGENT_MODEL_INCOMPATIBLE" else "unverified")
    alternative = service.capabilities(workspace.project_id, allow_edits=False, allow_web=False)
    assert next(model for model in alternative.models if model.model == run.model).state == "unverified"
    assert service.settings.load().selected_agent_model == run.model
    assert runtime.calls == [run.model]


@pytest.mark.asyncio
async def test_project_deletion_stops_runtime_and_late_events_cannot_recreate_sidecar(tmp_path):
    entered = asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        while not cancel.is_set():
            await asyncio.sleep(0.01)
        return RuntimeResult(state="cancelled", error="AGENT_CANCELLED", native_started=True)
    service, _, projects, workspace, _, request, _ = setup(tmp_path, script)
    run, _ = service.submit(workspace.project_id, request)
    control = service.start(workspace.project_id, run.id)
    await asyncio.wait_for(entered.wait(), 2)
    result = await projects.delete_project(workspace.project_id)
    assert result.status == "deleted" and control.revoked.is_set() and control.task.done()
    assert not (service.store.projects / workspace.project_id).exists()
    assert projects.storage.registry().entries[0].tombstoned
    with pytest.raises(AgentFailure, match="AGENT_PROJECT_DELETED"):
        service.leases.open(workspace.project_id, "late_tab")
    with pytest.raises(AgentFailure, match="AGENT_PROJECT_DELETED"):
        service.event(control, "edit.result", {"batchId": "late", "disposition": "saved", "error": None})
    assert not (service.store.projects / workspace.project_id).exists()


@pytest.mark.asyncio
async def test_connection_epoch_change_interrupts_without_relabelling_or_resuming(tmp_path):
    entered = asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        while not cancel.is_set():
            await asyncio.sleep(0.01)
        return RuntimeResult(state="cancelled", error="AGENT_CANCELLED", native_started=True)
    service, runtime, _, workspace, _, request, connection = setup(tmp_path, script)
    run, _ = service.submit(workspace.project_id, request)
    control = service.start(workspace.project_id, run.id)
    await asyncio.wait_for(entered.wait(), 2)
    connection["value"] = AgentConnection(False, (), "account_2", "AGENT_CONNECTION_UNAVAILABLE")
    await asyncio.wait_for(control.task, 2)
    assert control.result.error == "AGENT_CONNECTION_CHANGED"
    saved = run_in(service.store.load(workspace.project_id), run.id)[1]
    assert saved.state == "interrupted" and saved.model == "assistant-model" and saved.connection_epoch == "account_1"
    assert service.start(workspace.project_id, run.id) is control
    assert runtime.calls == ["assistant-model"]


class MetadataAdapter:
    def __init__(self):
        self.inspections = 0

    def inspect(self, _files, _cancel, *, full=True):
        self.inspections += 1
        return Metadata("fixture", ("assistant-model", "processing-model"), "plus", Quota("available", 10))


@pytest.mark.asyncio
async def test_settings_and_status_reuse_connection_without_processing_choice_or_active_probe(tmp_path):
    _, canonical, workspace, conversation = isolated_project(tmp_path / "FoldCV")
    entered, release = asyncio.Event(), asyncio.Event()
    async def script(value, cancel, emit):
        entered.set()
        while not release.is_set() and not cancel.is_set():
            await asyncio.sleep(0.01)
        return RuntimeResult(state="cancelled" if cancel.is_set() else "completed", text="Checked", native_started=True)
    adapter = MetadataAdapter()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("fixture")
    origin = "http://127.0.0.1:39272"
    app = create_app(origin=origin, secret="synthetic-agent-secret-0123456789", temp_root=tmp_path / "operations",
        dist=dist, connection_adapter=adapter, gui_provider=CreationProvider(), data_root=canonical.root,
        agent_runtime=ScriptedAgentRuntime(script), agent_tools=Tools())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin, headers={"Origin": origin}) as client:
        assert (await client.post("/v1/session/exchange", json={"secret": "synthetic-agent-secret-0123456789"})).status_code == 200
        assert (await client.post("/v1/host/status", json={})).json()["selectedModel"] is None
        service = app.app.state.agent
        service.settings.save(AgentSettingsRequest(expectedRevision=1, enabled=True,
            selectedAgentModel="assistant-model"), ("assistant-model", "processing-model"))
        assert service.capabilities(workspace.project_id).ready and adapter.inspections == 1
        epoch = service.connection().epoch
        lease = service.leases.open(workspace.project_id, "history_1")
        request = run_request(conversation.id, owner=lease.owner.model_dump(by_alias=True), settingsRevision=2)
        run, _ = service.submit(workspace.project_id, request)
        control = service.start(workspace.project_id, run.id)
        await asyncio.wait_for(entered.wait(), 2)
        assert (await client.get("/v1/settings/connection")).json()["metadataReady"]
        assert (await client.post("/v1/host/status", json={})).status_code == 200
        assert adapter.inspections == 1 and service.connection().epoch == epoch
        assert (await client.post("/v1/host/select", json={"model": "processing-model"})).status_code == 200
        assert service.connection().epoch == epoch and not control.cancel.is_set()
        assert service.settings.load().selected_agent_model == "assistant-model"
        assert (await client.post("/v1/host/detach", json={})).status_code == 200
        assert control.task.done() and control.result.error == "AGENT_CONNECTION_CHANGED"
        assert service.connection().epoch != epoch and not service.closed
        assert service.runtime.calls == ["assistant-model"]
