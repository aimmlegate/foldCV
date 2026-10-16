"""Real agent reads/compiler/artifact adapters under the capacity-one Job owner."""

import asyncio
from datetime import datetime, timedelta
import hashlib
import json

import pytest

from packages.resume_core.agent_store import AgentFailure, digest, journal_request, run_in
from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.agent import AgentApplyRequest, AgentQuery, AgentSettingsRequest
from packages.resume_core.models.background import JobAgentRequestV1
from spikes.background.fixtures import TIME
from tests.recovery.test_agent_edits import command, replace
from tests.recovery.test_agent_lifecycle import setup
from tests.support.background import PipeExecutions


async def environment(root):
    from resume_api.jobs.service import JobService
    from resume_api.inference_admission import InferenceAdmission
    old, _, projects, workspace, conversation, request, connection = setup(root, None)
    clock = ControlledDeadlines()
    factory = PipeExecutions(root / "pipes", clock)
    service = JobService(projects, None, lambda: connection["value"], enabled=True,
        factory=factory, clock=clock, admission=InferenceAdmission())
    base = datetime.fromisoformat(TIME.replace("Z", "+00:00"))
    service.store.clock = service.artifacts.clock = lambda: (base + timedelta(seconds=clock.now())).isoformat()
    await service.start()
    state = service.project(workspace.project_id)
    payload = JobAgentRequestV1(schemaVersion=1, lineage=state.lineage, requestEpoch=state.request_epoch,
        request=journal_request(request))
    return service, factory, workspace, payload, connection, old


def hold_writer(service, workspace):
    from packages.resume_core.background_history import digest_bytes
    from packages.resume_core.models.background import WriterOpenV1, WriterProofV1
    current = service.projects.storage.read_committed(workspace.project_id)[0]
    view = service.writers.open(workspace.project_id, WriterOpenV1(schemaVersion=1, sessionId="held-editor",
        incarnation="held-connection", credential="synthetic_held_writer_credential_0123456789",
        canonicalRevision=current.project_revision, canonicalSha256=digest_bytes(current), actionCursor=0))
    return WriterProofV1(schemaVersion=1, lineage=view.writer.lineage, epoch=view.writer.epoch,
        sessionId=view.writer.session_id, incarnation=view.writer.incarnation,
        credential="synthetic_held_writer_credential_0123456789")


@pytest.mark.asyncio
async def test_server_capture_retry_and_legacy_view_have_one_job_authority(tmp_path):
    service, factory, workspace, payload, connection, old = await environment(tmp_path)
    factory.hold_results.add(payload.request.client_request_id)
    old_before = old.store.load(workspace.project_id)
    try:
        first, created = await service.submit(workspace.project_id, payload)
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        service.settings.save(AgentSettingsRequest(expectedRevision=2, enabled=True,
            selectedAgentModel="processing-model"), connection["value"].models)
        replay, created = await service.submit(workspace.project_id, payload)
        assert not created and replay.id == first.id
        assert replay.submission.models[0].model == "assistant-model"
        changed = payload.model_copy(deep=True)
        changed.request.message = "Another request with the same ID"
        with pytest.raises(BackgroundFailure, match="JOB_IDEMPOTENCY_CONFLICT"):
            await service.submit(workspace.project_id, changed)
        following = payload.model_copy(deep=True)
        following.request.client_request_id = "second-send"
        following.request.settings_revision = 3
        second, created = await service.submit(workspace.project_id, following)
        assert created and second.submission.models[0].model == "processing-model"
        view = service.artifacts.bound(workspace.project_id, first.id)
        assert view.legacy().run.state == "running"
        assert view.legacy().publication == "none"
        with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
            view.update(workspace.project_id, lambda state: setattr(run_in(state, first.id)[1], "state", "cancelled"))
        assert service.store.read(workspace.project_id, first.id).execution == "running"
        assert old.store.load(workspace.project_id) == old_before
        await service.supervisor.cancel(workspace.project_id, first.id)
        await asyncio.wait_for(service.supervisor.controls[first.id].task, 10)
        second_actor = await factory.actor(second)
        await asyncio.wait_for(second_actor.closed.wait(), 10)
        await asyncio.wait_for(service.supervisor.controls[second.id].task, 10)
        assert not service.admission.locked()
    finally:
        if "began" in locals():
            began.cancel()
            await asyncio.gather(began, return_exceptions=True)
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-J03:v{index:02d}" for index in range(1, 7)])
async def test_captured_models_rules_and_bound_capabilities_cannot_be_replaced(tmp_path, variant):
    service, factory, workspace, payload, connection, old = await environment(tmp_path)
    checked = []
    if variant == "NB-J03:v02":
        payload.request.allow_edits = False
    async def execute(control, _actor):
        import copy
        import httpx
        session = service.tools.session(control)
        try:
            if variant == "NB-J03:v01":
                service.settings.save(AgentSettingsRequest(expectedRevision=2, enabled=True,
                    selectedAgentModel="processing-model"), connection["value"].models)
                replay, created = await service.submit(workspace.project_id, payload)
                assert not created and replay.submission.models[0].model == "assistant-model"
            elif variant == "NB-J03:v02":
                assert "apply_edit_batch" not in control.job.submission.tools
                result = await session.call("apply_edit_batch", AgentApplyRequest(batchId="forged-batch"))
                assert result["error"]["code"] == "AGENT_TOOL_DENIED"
                assert "prepare_edit_batch" not in {tool.name for tool in await session.sdk.list_tools()}
            elif variant == "NB-J03:v03":
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host) as client:
                    denied = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "get_resume_context"}}, headers={"Authorization": "Bearer foreign-project-capability"})
                    assert denied.status_code == 403 and session.calls == 0
            elif variant == "NB-J03:v04":
                service.store.replace_account(2)
                with pytest.raises(AgentFailure, match="AGENT_CONNECTION_CHANGED"):
                    session.guard()
            elif variant == "NB-J03:v05":
                current, checksum = service.projects.storage.read_committed(workspace.project_id)
                current.rules_used = service.projects.rules.load()
                service.publisher.snapshot(workspace.project_id, checksum, current, "rules-update")
                with pytest.raises(AgentFailure, match="AGENT_STALE_READ"):
                    session.guard()
                assert service.artifacts.record(workspace.project_id, control.run_id)[1].rules_sha256 == digest(None)
            else:
                service.supervisor.controls[control.run_id] = copy.copy(control)
                with pytest.raises(AgentFailure, match="AGENT_CANCELLED"):
                    session.guard()
                service.supervisor.controls[control.run_id] = control
            checked.append(variant)
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        actor = await factory.actor(job)
        await asyncio.wait_for(actor.closed.wait(), 10)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        failure = service.supervisor.controls[job.id].run_task.exception()
        if failure is not None:
            raise failure
        assert checked == [variant]
        assert service.store.read(workspace.project_id, job.id).publication == ("cancelled" if variant == "NB-J03:v04" else "none")
        assert old.store.load(workspace.project_id).journals == []
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_waiter", [False, True], ids=["NB-Q10:v10", "cancel-shared-waiter"])
async def test_shared_admission_wait_consumes_no_startup_or_active_budget(tmp_path, cancel_waiter):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    admission = service.admission
    assert admission.acquire(blocking=False)
    reached = asyncio.Event()
    original = admission.reserve
    async def reserve(cancelled):
        reached.set()
        return await original(cancelled)
    admission.reserve = reserve
    factory.hold_results.add(payload.request.client_request_id)
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        await asyncio.wait_for(reached.wait(), 10)
        control = service.supervisor.controls[job.id]
        assert admission.locked() and not control.slot_granted
        assert service.store.read(workspace.project_id, job.id).attempts == []
        assert not service.supervisor.login_allowed()
        service.supervisor.clock.advance(31)
        if cancel_waiter:
            await service.supervisor.cancel(workspace.project_id, job.id)
            await asyncio.wait_for(control.task, 10)
            assert admission.locked() and admission.reservation is None and factory.calls == []
            admission.release()
        else:
            admission.release()
            actor = await factory.actor(job)
            await asyncio.wait_for(actor.started.wait(), 10)
            assert control.active_deadline == 211
            actor.result.set()
            await asyncio.wait_for(control.task, 10)
            assert service.store.read(workspace.project_id, job.id).execution == "completed"
            assert len(service.store.read(workspace.project_id, job.id).attempts) == 1
        assert not admission.locked() and not admission.waiting
    finally:
        if admission.locked() and admission.reservation is None:
            admission.release()
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_runtime_adapter_uses_v2_instructions_and_closes_tools_before_permit_release(tmp_path):
    service, factory, workspace, payload, _connection, _old = await environment(tmp_path)
    from resume_api.agent.runtime import RuntimeResult, ScriptedAgentRuntime
    from resume_api.jobs.runtime import JobRuntime
    from resume_api.jobs.tools import DEVELOPER_INSTRUCTIONS_V2
    checked = asyncio.Event()
    async def script(value, _cancel, _emit):
        assert value.developer_instructions == DEVELOPER_INSTRUCTIONS_V2
        assert service.admission.locked() and service.supervisor.active.ready.is_set()
        assert "apply_edit_batch" in value.tools and value.token
        checked.set()
        return RuntimeResult(state="completed", text="Проверка завершена.")
    service.runtime = ScriptedAgentRuntime(script)
    owned_executions = []
    def own(job, model):
        owned = JobRuntime(service, job, model)
        owned_executions.append(owned)
        return owned
    service.supervisor.factory = own
    dispatched = asyncio.Event()
    async def observe(name, _job):
        if name == "slot_granted":
            dispatched.set()
    service.supervisor.observer = observe
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        await asyncio.wait_for(dispatched.wait(), 10)
        control = service.supervisor.controls[job.id]
        began = asyncio.create_task(checked.wait())
        await asyncio.wait([began, control.task], return_when=asyncio.FIRST_COMPLETED, timeout=10)
        owned = owned_executions[0]
        if owned.driver.done() and owned.driver.exception() is not None:
            raise owned.driver.exception()
        assert checked.is_set(), service.store.read(workspace.project_id, job.id)
        await began
        await asyncio.wait_for(control.task, 10)
        assert owned.verified_dead() and not owned.session.active
        assert not service.admission.locked() and service.supervisor.active is None
        current = service.store.read(workspace.project_id, job.id)
        assert current.execution == "completed" and current.attempts[0].cleanup_verified
        assert not current.attempts[0].native_started
        artifact = service.artifacts.record(workspace.project_id, job.id)[1]
        assert artifact.reply.text == "Проверка завершена." and service.runtime.calls == ["assistant-model"]
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("review", [False, True], ids=["NB-J04:v01", "NB-J04:v02"])
async def test_actual_compiler_apply_v2_retains_single_payload_after_native_exit_and_restart(tmp_path, review):
    service, factory, workspace, payload, _connection, old = await environment(tmp_path)
    hold_writer(service, workspace)
    canonical_before = digest(service.projects.read(workspace.project_id))
    old_before = old.store.load(workspace.project_id)
    replies = []
    expected_canonical = [canonical_before]
    async def execute(control, _actor):
        session = service.tools.session(control)
        try:
            result = await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"]))
            from packages.resume_core.models.agent import AgentReadSnapshot
            snapshot = AgentReadSnapshot.model_validate(result["snapshot"])
            prepared = await session.call("prepare_edit_batch", command(replace(snapshot, "narrative", 0, 6, "Clear")))
            assert prepared["disposition"] == "prepared", prepared
            if review:
                from tests.recovery.test_background_inverse import mutation, put
                current = service.projects.storage.read_committed(workspace.project_id)[0]
                service.publisher.manual(workspace.project_id,
                    mutation(current, [put(current, "narrative", text="Concurrent user input")], "manual-before-apply"),
                    originals=service.projects.originals, artifacts=service.projects.artifacts, images=service.projects.images)
                expected_canonical[0] = digest(service.projects.read(workspace.project_id))
            applied = await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"]))
            assert applied["disposition"] == ("needs_review" if review else "waiting_for_sync"), applied
            assert applied["proposalStored"] and not applied["durable"]
            assert await session.call("apply_edit_batch", AgentApplyRequest(batchId=prepared["batchId"])) == applied
            replies.append(applied)
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        actor = await factory.actor(job)
        await asyncio.wait_for(actor.closed.wait(), 10)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        current = service.store.read(workspace.project_id, job.id)
        failure = service.supervisor.controls[job.id].run_task.exception()
        if failure is not None:
            raise failure
        assert current.execution == "completed" and current.publication == ("needs_review" if review else "waiting_for_sync"), current
        assert current.receipt is None and len(replies) == 1
        assert service.supervisor.active is None and not service.admission.locked()
        state = service.store.load(workspace.project_id)
        artifact = service.artifacts.record(workspace.project_id, job.id)[1]
        batch = artifact.batches[0].batch
        raw = service.artifacts.payload_for(workspace.project_id, state.proposals[0].payload)
        assert len(artifact.batches) == 1 and batch is not None
        assert hashlib.sha256(raw).hexdigest() == state.proposals[0].payload_sha256
        sidecars = [path for path in (service.store.projects / workspace.project_id).rglob("*.json")
            if "agent-artifacts" not in str(path)]
        assert all(b'"mutation"' not in path.read_bytes() for path in sidecars)
        assert digest(service.projects.read(workspace.project_id)) == expected_canonical[0]
        assert old.store.load(workspace.project_id) == old_before
        await service.shutdown()
        from packages.resume_core.background_store import JobStore
        recovered = JobStore(service.store.root)
        recovered.recover(workspace.project_id)
        restored = recovered.load(workspace.project_id)
        assert restored.proposals == state.proposals and restored.jobs[0].publication == current.publication
        assert restored.jobs[0].receipt is None and factory.calls == [(job.id, "agent")]
        stored = json.loads((service.store.projects / workspace.project_id / "agent-artifacts" / (artifact.id + ".json")).read_text())
        assert "execution" not in stored and "publication" not in stored
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()
