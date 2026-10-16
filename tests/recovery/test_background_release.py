"""Final serial delivery, rollback and resource ownership through the real API."""

import asyncio
import hashlib
import json

import pytest

from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_retention import JobRetention
from packages.resume_core.background_store import BackgroundFailure, JobStore, TERMINAL_EXECUTION
from packages.resume_core.background_supervisor import COMPLETED_CONTROLS
from packages.resume_core.models.background import JobReplayRequestV1
from spikes.background.writer_bridge import Bridge
from tests.recovery.test_background_agent import hold_writer
from tests.recovery.test_background_exports import HeldRenderer
from tests.recovery.test_background_inverse import mutation, put
from tests.recovery.test_background_store import capture
from tests.recovery.test_background_supervisor import environment
from tests.support.background import save_input


async def submit(bridge, key, *, edits=True):
    service, project = bridge.service, bridge.project
    registry = service.project(project)
    workspace = service.projects.storage.read_committed(project)[0]
    request = dict(schemaVersion=1, lineage=registry.lineage, requestEpoch=registry.request_epoch,
        request=dict(clientRequestId=key, conversationId=bridge.conversation.id,
            message="Synthetic serial acceptance " + key, allowEdits=edits, allowWeb=False,
            scope={"kind": "resume"}, settingsRevision=2, projectRevision=workspace.project_revision,
            documentRevision=workspace.document_revision, factsRevision=workspace.project.facts.revision))
    response = await bridge.handle(dict(kind="http", path=f"/v1/rich/projects/{project}/jobs/agent", body=request))
    assert response["status"] == 202, response
    return service.store.read(project, response["value"]["id"])


async def opened(root):
    bridge = Bridge(root)
    bridge.send = lambda _value: None
    await bridge.start()
    return bridge


async def held(bridge, key="held"):
    reached = asyncio.Event()
    bridge.send = lambda value: reached.set() if value.get("token") == key else None
    await bridge.handle(dict(kind="hold", token=key, name="scripted_model_ready", family="job"))
    job = await submit(bridge, key)
    await asyncio.wait_for(reached.wait(), 10)
    return job


@pytest.mark.asyncio
async def test_busy_login_preserves_the_live_job_and_connection_without_probes(tmp_path):
    bridge = await opened(tmp_path)
    try:
        def forbidden_login(*_args):
            raise AssertionError("BUSY login must not invoke the connection adapter")
        bridge.adapter.login = forbidden_login
        job = await held(bridge)
        service = bridge.service
        before = service.store.read(bridge.project, job.id)
        inspections = bridge.adapter.inspections
        response = await bridge.client.post("/v1/host/login", json={})
        assert response.status_code == 429 and response.json()["error"]["code"] == "BUSY", response.text
        status = await bridge.client.post("/v1/host/status", json={})
        assert status.status_code == 200
        assert service.store.read(bridge.project, job.id) == before
        assert bridge.adapter.inspections == inspections and len(bridge.factory.calls) == 1
        await bridge.handle(dict(kind="release", token="held"))
        final = await bridge.wait_execution(bridge.project, job.id)
        assert final.execution == "completed" and final.receipt.durable
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_export_and_manual_save_progress_while_the_only_model_is_held(tmp_path):
    bridge = await opened(tmp_path)
    render_task = None
    renderer = HeldRenderer()
    try:
        service, project = bridge.service, bridge.project
        service.projects.renderer = renderer
        job = await held(bridge)
        proof = hold_writer(service, service.projects.storage.read_committed(project)[0])
        captured = service.projects.storage.read_committed(project)[0]
        render_task = asyncio.create_task(bridge.client.post(f"/v1/rich/projects/{project}/export", json={}))
        await asyncio.wait_for(renderer.entered.wait(), 10)
        command = mutation(captured, [put(captured, "quote", text="Manual input while model and render wait")], "held-export")
        saved = await asyncio.wait_for(asyncio.to_thread(save_input, service, command, proof), 10)
        assert saved.workspace.project_revision == captured.project_revision + 1
        assert service.admission.locked() and service.supervisor.active.run_id == job.id
        renderer.release.set()
        response = await asyncio.wait_for(render_task, 10)
        assert response.status_code == 200
        assert response.headers["x-foldcv-sha256"] == hashlib.sha256(response.content).hexdigest()
        assert json.loads(response.content)["document"] == captured.project.document.model_dump(mode="json", by_alias=True)
        assert not service.projects.tasks and not service.projects.files
        assert all(pin.kind != "export" for pin in service.store.load(project).asset_pins)
        assert service.store.read(project, job.id).execution == "running" and len(bridge.factory.calls) == 1
        await bridge.handle(dict(kind="release", token="held"))
        final = await bridge.wait_execution(project, job.id)
        assert final.execution == "completed" and final.publication == "waiting_for_sync"
        assert next(b for b in service.projects.storage.read_committed(project)[0].project.document.blocks()
            if b.id == "quote").content[0].text == "Manual input while model and render wait"
    finally:
        renderer.release.set()
        if render_task is not None:
            await asyncio.gather(render_task, return_exceptions=True)
        await bridge.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["success", "pending", "retention"], ids=["NB-R04:v01", "NB-R04:v02", "NB-R04:v05"])
async def test_repeated_results_retain_only_bounded_runtime_records_and_explicit_owners(tmp_path, mode):
    bridge = await opened(tmp_path)
    try:
        service, project = bridge.service, bridge.project
        if mode == "pending":
            hold_writer(service, service.projects.storage.read_committed(project)[0])
        for cycle in range(12):
            job = await submit(bridge, "cycle-" + str(cycle))
            final = await bridge.wait_execution(project, job.id)
            assert final.execution == "completed", final.error
            assert final.publication == ("waiting_for_sync" if mode == "pending" else "saved")
            stream = service.stream(project, job.id, JobReplayRequestV1(schemaVersion=1, after=0, generation=1))
            assert await anext(stream)
            await stream.aclose()
            service.supervisor.reap()
            state = service.store.load(project)
            assert len(state.proposals) == cycle + 1
            assert not service.supervisor.listeners and service.supervisor.active is None
            assert not service.admission.locked() and not service.admission.waiting and not service.admission.async_waiters
            assert len(service.supervisor.controls) <= COMPLETED_CONTROLS
            assert len(service.proposals[project].tasks) <= 1
            assert not service.publication_tasks and not service.projects.tasks and not service.projects.files
            assert all(control.task.done() and control.owned is None and control.permit is None
                for control in service.supervisor.controls.values())
            bridge.factory.verify()
            events = service.store.projects / project / "events" / (job.id + ".json")
            assert events.stat().st_size <= LIMITS.replay_bytes
        if mode == "retention":
            before = service.projects.storage.read_committed(project)[1]
            bridge.wall_offset += LIMITS.request_replay_seconds + 1
            after = JobRetention(service.store).sweep(project)
            assert not after.jobs and not after.requests and not after.proposals and not after.cleanup_refs
            assert not list((service.store.projects / project / "agent-artifacts").glob("*.json"))
            assert not list((service.store.projects / project / "events").glob("*.json"))
            assert service.projects.storage.read_committed(project)[1] == before
            with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
                service.store.submit(job.submission)
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_repeated_cleanup_failure_keeps_real_ownership_until_verified_death(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    try:
        for cycle in range(12):
            key = "failed-cleanup-" + str(cycle)
            factory.cleanup_errors.add(key)
            job, _ = await supervisor.submit(capture(state, key))
            actor = await factory.actor(job)
            await asyncio.wait_for(supervisor.controls[job.id].task, 10)
            control = supervisor.controls[job.id]
            assert supervisor.active is control and control.owned is actor
            assert supervisor.fenced == "CLEANUP_FAILED" and not actor.verified_dead()
            assert actor.child.command("probe") == {"type": "alive"}
            assert not store.read(state.project_id, job.id).attempts[-1].cleanup_verified
            actor.close_error = False
            await supervisor.verify_cleanup(job.id)
            supervisor.reap()
            assert supervisor.active is None and supervisor.fenced is None
            assert len(supervisor.controls) <= COMPLETED_CONTROLS
            assert store.read(state.project_id, job.id).attempts[-1].cleanup_verified
            assert all(item.verified_dead() for item in factory.actors.values())
    finally:
        for actor in factory.actors.values():
            actor.close_error = False
        if supervisor.active is not None:
            await supervisor.verify_cleanup(supervisor.active.run_id)
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_repeated_queue_saturation_and_cancellation_leak_no_admission_or_listeners(tmp_path):
    bridge = await opened(tmp_path)
    try:
        service, project = bridge.service, bridge.project
        for cycle in range(4):
            token = "held-" + str(cycle)
            first = await held(bridge, token)
            queued = [await submit(bridge, f"queued-{cycle}-{index}", edits=False)
                for index in range(LIMITS.pending_noninteractive_project)]
            before = len(bridge.factory.calls)
            with pytest.raises(AssertionError, match="JOB_QUEUE_FULL"):
                await submit(bridge, "overflow-" + str(cycle))
            for job in queued:
                result = await service.supervisor.cancel(project, job.id)
                assert result.execution == "cancelled" and result.publication == "none"
            await service.supervisor.cancel(project, first.id)
            await bridge.handle(dict(kind="release", token=token))
            await bridge.wait_execution(project, first.id)
            assert len(bridge.factory.calls) == before
            assert not service.admission.locked() and not service.admission.waiting and not service.supervisor.listeners
            assert all(job.execution in TERMINAL_EXECUTION for job in service.store.load(project).jobs)
            bridge.factory.verify()
    finally:
        await bridge.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["queued", "running", "proposal", "intent", "saved", "serial"],
    ids=[f"NB-X01:v{index:02d}" for index in range(1, 7)])
async def test_feature_retirement_and_flag_off_restart_keep_the_canonical_authority(tmp_path, phase):
    bridge = await opened(tmp_path)
    restarted = None
    try:
        service, project = bridge.service, bridge.project
        baseline = service.projects.storage.read_committed(project)[0]
        proof = hold_writer(service, baseline) if phase == "proposal" else None
        reached, stopped = asyncio.Event(), asyncio.Event()
        if phase == "queued":
            service.supervisor.dispatch_enabled = False
        elif phase == "running":
            await held(bridge)
        elif phase == "intent":
            bridge.send = lambda value: reached.set() if value.get("token") == "intent" else None
            await bridge.handle(dict(kind="hold", token="intent", name="before_workspace_replaced", family="writer", jobOnly=True))
        if phase == "serial":
            first = await held(bridge)
            second = await submit(bridge, "serial-second", edits=False)
            assert service.store.read(project, second.id).execution == "queued" and len(bridge.factory.calls) == 1
            await bridge.handle(dict(kind="release", token="held"))
            await bridge.wait_execution(project, first.id)
            await bridge.wait_execution(project, second.id)
            assert len(bridge.factory.calls) == 2
        elif phase != "running":
            job = await submit(bridge, "retire-" + phase)
            if phase == "intent":
                await asyncio.wait_for(reached.wait(), 10)
            elif phase != "queued":
                await bridge.wait_execution(project, job.id)
        if phase == "proposal":
            from packages.resume_core.models.background import WriterCheckpointV1
            document = baseline.project.document.model_copy(deep=True)
            next(block for block in document.blocks() if block.id == "quote").content[0].text = "Retained rollback draft"
            command = mutation(baseline, [put(baseline, "quote", text="Retained rollback draft")], "retained-draft")
            command.capture.session_id = proof.session_id
            service.writers.checkpoint(project, WriterCheckpointV1(schemaVersion=1, proof=proof, id="rollback-draft",
                sequence=1, actionCursor=1, baseRevision=baseline.project_revision,
                baseSha256=service.projects.storage.read_committed(project)[1], payload=dict(schemaVersion=1,
                    document=document.model_dump(by_alias=True), facts=baseline.project.facts.model_dump(by_alias=True),
                    touches=[dict(cursor=1, mutation=command.model_dump(by_alias=True))], outbox=[], assetPins=[])))
        original_shutdown = service.shutdown
        async def observe_shutdown():
            stopped.set()
            await original_shutdown()
        service.shutdown = observe_shutdown
        task = asyncio.create_task(service.disable())
        await asyncio.wait_for(stopped.wait(), 10)
        assert not service.accepting and not service.supervisor.dispatch_enabled
        # Reject before touching a possibly claimed project's locked state.
        from packages.resume_core.models.background import JobAgentRequestV1
        from spikes.background.fixtures import examples
        with pytest.raises(BackgroundFailure, match="JOB_DISABLED"):
            await service.submit(project, JobAgentRequestV1.model_validate(examples()["background_agent_request_v1"]))
        if phase == "intent":
            await bridge.handle(dict(kind="release", token="intent"))
        elif phase == "running":
            await bridge.handle(dict(kind="release", token="held"))
        await asyncio.wait_for(task, 10)
        state = service.store.load(project)
        assert service.enabled and service.projects.background_jobs is service
        assert all(job.execution in TERMINAL_EXECUTION for job in state.jobs)
        assert all(intent.phase in {"receipt_stored", "reconciled"} for intent in state.intents)
        assert service.supervisor.active is None and not service.admission.locked()
        assert not service.supervisor.listeners and not service.publication_tasks
        canonical = service.projects.storage.read_committed(project)[0]
        if phase == "proposal":
            assert state.proposals and state.proposals[0].authority == "active"
            assert state.jobs[0].publication == "waiting_for_sync" and canonical == baseline
            assert len(state.drafts) == 1
        elif phase in {"saved", "intent", "serial"}:
            assert state.jobs[0].receipt.durable and canonical.project_revision == baseline.project_revision + 1
        else:
            assert canonical == baseline
        saved_state = state.model_dump(mode="json", by_alias=True)
        await bridge.close()
        restarted = Bridge(tmp_path, background_enabled=False)
        restarted.send = lambda _value: None
        await restarted.start()
        recovered = restarted.service
        assert recovered.enabled and not recovered.accepting and not recovered.supervisor.dispatch_enabled
        assert not restarted.factory.calls and not recovered.supervisor.controls
        after = recovered.store.load(project)
        assert after.jobs == state.jobs and after.proposals == state.proposals and after.drafts == state.drafts
        assert recovered.projects.storage.read_committed(project)[0] == canonical
        assert after.model_dump(mode="json", by_alias=True)["intents"] == saved_state["intents"]
        denied = await restarted.client.post(f"/v1/rich/projects/{project}/generation", json={})
        assert denied.status_code == 409 and denied.json()["error"]["code"] == "JOB_SCOPE_INVALID"
        assert recovered.projects.background_jobs is recovered
        if proof is not None:
            assert JobStore(recovered.store.root).load(project).writer.status == "recovering"
    finally:
        if restarted is not None:
            await restarted.close()
        elif not bridge.client.is_closed:
            await bridge.close()
