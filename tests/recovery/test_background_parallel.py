"""Exercise real parallel scheduling with owned synthetic pipe children."""

import asyncio

import pytest

from packages.resume_core.rich_project_store import RichProjectStore
from tests.recovery.test_background_queue import captured
from tests.recovery.test_background_supervisor import environment


def other_project(root, store, state, identifier="parallel-other"):
    canonical = RichProjectStore(root)
    workspace = canonical.read_committed(state.project_id)[0].model_copy(deep=True)
    workspace.project_id = workspace.project.project_id = identifier
    canonical.save(workspace, {}, {})
    return store.open(workspace.project_id)


async def finish(supervisor, factory, clock):
    for actor in factory.actors.values():
        actor.result.set()
        actor.ready_permission.set()
        actor.cleanup_permission.set()
    await supervisor.shutdown()
    factory.verify()
    clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-Q05:v01", "NB-Q05:v02", "NB-Q05:v03", "NB-Q05:v05"])
async def test_parallel_positions_preserve_interactive_reserve_and_scoped_stop(tmp_path, variant):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    supervisor.parallel = True
    supervisor.pause("RATE_LIMITED")
    other = other_project(tmp_path, store, state)
    factory.hold_results.update({"A", "B", "rewrite", "waiting"})
    factory.hold_cleanup.add("A")
    try:
        first, _ = await supervisor.submit(captured(state, "A"))
        second_request = captured(state if variant == "NB-Q05:v03" else other, "B")
        if variant == "NB-Q05:v03":
            second_request.allow_edits = False
            second_request.tools = [name for name in second_request.tools if name not in {"prepare_edit_batch", "apply_edit_batch"}]
            second_request.guards.writes = []
        second, _ = await supervisor.submit(second_request)
        rewrite, _ = await supervisor.submit(captured(state, "rewrite", "rewrite"))
        waiting, _ = await supervisor.submit(captured(state, "waiting"))
        supervisor.resume(1)
        actors = [await factory.actor(job) for job in (first, second, rewrite)]
        await asyncio.wait_for(asyncio.gather(*(actor.started.wait() for actor in actors)), 10)
        assert len(supervisor.active_controls) == 3
        assert all(supervisor.owns(supervisor.controls[job.id]) for job in (first, second, rewrite))
        assert sum(c.job.submission.scheduling_class != "interactive" for c in supervisor.active_controls.values()) == 2
        assert store.read(waiting.submission.identity.project_id, waiting.id).execution == "queued"
        assert not store.read(waiting.submission.identity.project_id, waiting.id).attempts
        assert not supervisor.login_allowed()
        await supervisor.cancel(state.project_id, first.id)
        await asyncio.wait_for(actors[0].cleanup_started.wait(), 10)
        assert len(supervisor.active_controls) == 3
        assert supervisor.owns(supervisor.controls[first.id])
        assert not actors[1].closed.is_set() and not actors[2].closed.is_set()
        assert not supervisor.controls[second.id].cancel.is_set()
        actors[0].cleanup_permission.set()
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        replacement = await factory.actor(waiting)
        await asyncio.wait_for(replacement.started.wait(), 10)
        assert store.read(state.project_id, first.id).execution == "cancelled"
        assert len(supervisor.active_controls) == 3
        for job, actor in [(second, actors[1]), (rewrite, actors[2]), (waiting, replacement)]:
            actor.result.set()
            await asyncio.wait_for(supervisor.controls[job.id].task, 10)
            assert store.read(job.submission.identity.project_id, job.id).execution == "completed"
        assert not supervisor.active_controls and supervisor.active is None
        assert supervisor.login_allowed()
    finally:
        await finish(supervisor, factory, clock)


@pytest.mark.asyncio
async def test_shutdown_never_dispatches_the_pending_queue_after_a_position_closes(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    supervisor.parallel = True
    supervisor.pause("RATE_LIMITED")
    other = other_project(tmp_path, store, state)
    factory.hold_results.update({"A", "B"})
    factory.hold_cleanup.add("A")
    try:
        first, _ = await supervisor.submit(captured(state, "A"))
        second, _ = await supervisor.submit(captured(other, "B"))
        pending, _ = await supervisor.submit(captured(state, "pending"))
        supervisor.resume(1)
        actors = [await factory.actor(job) for job in (first, second)]
        await asyncio.wait_for(asyncio.gather(*(actor.started.wait() for actor in actors)), 10)
        closing = asyncio.create_task(supervisor.shutdown())
        await asyncio.wait_for(actors[0].cleanup_started.wait(), 10)
        assert supervisor.closed and len(factory.calls) == 2
        actors[0].cleanup_permission.set()
        await asyncio.wait_for(closing, 10)
        assert len(factory.calls) == 2
        untouched = store.read(state.project_id, pending.id)
        assert untouched.execution == "queued" and not untouched.attempts
        assert not supervisor.active_controls
    finally:
        await finish(supervisor, factory, clock)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_first", [False, True])
async def test_waiting_parallel_admission_is_cancellable_without_a_foreign_permit(tmp_path, cancel_first):
    from types import SimpleNamespace
    from resume_api.inference_admission import AdmissionCancelled, InferenceAdmission
    from resume_api.jobs.parallel import ParallelOwner
    admission = InferenceAdmission()
    assert admission.acquire(blocking=False)
    service = SimpleNamespace(admission=admission, supervisor=SimpleNamespace(active_controls={}))
    owner = ParallelOwner(service, None, native=False)
    entered = asyncio.Event()
    original = admission.reserve
    async def reserve(cancelled):
        entered.set()
        return await original(cancelled)
    admission.reserve = reserve
    first = SimpleNamespace(cancelled=asyncio.Event())
    second = SimpleNamespace(cancelled=asyncio.Event())
    tasks = [asyncio.create_task(owner.reserve(first))]
    await asyncio.wait_for(entered.wait(), 10)
    tasks.append(asyncio.create_task(owner.reserve(second)))
    if cancel_first:
        first.cancelled.set()
    else:
        second.cancelled.set()
    try:
        stopped = tasks[0 if cancel_first else 1]
        with pytest.raises(AdmissionCancelled):
            await asyncio.wait_for(stopped, 10)
        assert admission.locked() and owner.reservation is None
        first.cancelled.set()
        second.cancelled.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert not owner.permits and not owner.lock.locked()
        assert not admission.waiting and not admission.async_waiters
    finally:
        first.cancelled.set()
        second.cancelled.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        admission.release()
        await owner.idle()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["complete", "stop", "hung-tool", "output-limit", "old-parser", "old-tool", "owner-failure"])
async def test_one_job_service_runs_two_agents_and_rewrite_on_one_owned_server(tmp_path, monkeypatch, scenario):
    import json
    import httpx
    import threading
    from packages.resume_core.models.agent import AgentSettingsRequest
    from resume_api.agent.service import AgentConnection
    from resume_api.jobs.appserver import CapabilityClient, SharedAgentRuntime, SharedContentProvider
    from tests.recovery.generation_fixtures import CreationProvider
    from tests.recovery.test_background_agent import environment as job_environment
    from tests.recovery.test_background_appserver import shared_peer, complete_shared, shared_tool, emit_shared, tool_frame
    from tests.recovery.test_background_fixed_jobs import fixed_request, rewrite_command, settled
    driver = shared_peer(tmp_path / "transport")
    outputs = {}
    tool_entered, tool_released = asyncio.Event(), asyncio.Event()
    clients_closed = set()
    damaged = {}
    wire = []
    driver.wire_audit = wire.append
    scripted = CreationProvider()
    class Structured(SharedContentProvider):
        async def execute(self, request, cancel):
            outputs[self.job_id] = scripted.generate(request, None, threading.Event()).value.model_dump_json(by_alias=True)
            return await super().execute(request, cancel)
    class Client(CapabilityClient):
        async def call(self, name, arguments):
            if scenario == "hung-tool" and self.job == first.id:
                tool_entered.set()
                await tool_released.wait()
            return await super().call(name, arguments)
        async def close(self):
            clients_closed.add(self.job)
            if self.job == first.id:
                tool_released.set()
            await super().close()
    def client(value):
        session = service.supervisor.controls[value.job_id].owned.session
        assert value.token == session.token
        result = Client(value, transport=httpx.ASGITransport(app=session))
        result.job = value.job_id
        return result
    monkeypatch.setattr("resume_api.jobs.parallel.SharedAgentRuntime",
        lambda server, native: SharedAgentRuntime(server, native=native, client_factory=client))
    monkeypatch.setattr("resume_api.jobs.parallel.SharedContentProvider", Structured)
    service, factory, workspace, payload, connection, _old = await job_environment(tmp_path / "jobs",
        parallel=True, server_factory=lambda: driver)
    connection["value"] = AgentConnection(True, ("gpt-6-luna",), "account_1")
    service.settings.save(AgentSettingsRequest(expectedRevision=2, enabled=True,
        selectedAgentModel="gpt-6-luna"), connection["value"].models)
    payload.request.settings_revision = 3
    service.projects.provider_factory = lambda: (Structured(driver, native=False), "gpt-6-luna")
    ready = asyncio.Queue()
    async def observe(name, identifier):
        if name in {"scripted_model_ready", "scripted_fixed_model_ready"}:
            ready.put_nowait(identifier)
        if scenario == "owner-failure" and name == "slot_released" and identifier == second.id:
            from dataclasses import replace
            guard = driver.pipe.ownership
            original = guard.inspector.identity
            def changed(pid):
                result = original(pid)
                return replace(result, microseconds=result.microseconds + 1) if result is not None and pid == guard.process.pid else result
            damaged.update(guard=guard, original=original)
            guard.inspector.identity = changed
    service.supervisor.observer = observe
    service.supervisor.pause("RATE_LIMITED")
    ledger = __import__("pathlib").Path("docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json")
    before = ledger.read_bytes()
    try:
        first, _ = await service.submit(workspace.project_id, payload)
        check = payload.model_copy(deep=True)
        check.request.client_request_id = "parallel-check"
        check.request.allow_edits = False
        second, _ = await service.submit(workspace.project_id, check)
        reply, _ = await service.fixed.submit(workspace.project_id,
            fixed_request(service, workspace.project_id, "parallel-rewrite", rewrite_command(workspace)))
        service.supervisor.resume(1)
        observed = {await asyncio.wait_for(ready.get(), 10) for _ in range(3)}
        assert observed == {first.id, second.id, reply.job.id}
        assert len(driver.live) == len(service.parallel_owner.permits) == 3
        assert service.admission.locked() and not service.supervisor.login_allowed()
        assert len({live.slot.thread for live in driver.live.values()}) == 3
        assert len({live.server_pid for live in driver.live.values()}) == 1
        previous_slot = driver.live[first.id].slot
        if scenario == "hung-tool":
            emit_shared(driver, tool_frame(previous_slot, identifier=100, tool="get_resume_context",
                arguments={"query": {"kind": "document", "ids": ["narrative"]}}))
            await asyncio.wait_for(tool_entered.wait(), 10)
        for job in ((second,) if scenario == "hung-tool" else (first, second)):
            result = await shared_tool(driver, job.id, "get_resume_context",
                {"query": {"kind": "document", "ids": ["narrative"]}}, 100 if job is first else 200)
            assert "snapshot" in result
        if scenario in {"stop", "hung-tool"}:
            await service.supervisor.cancel(workspace.project_id, first.id)
        elif scenario == "output-limit":
            from packages.resume_core.agent_limits import ASSISTANT_TEXT_BYTES
            params = dict(threadId=previous_slot.thread, turnId=previous_slot.turn)
            item = dict(id="overflow_A", type="agentMessage", phase="final_answer", text="")
            emit_shared(driver, dict(method="item/started", params={**params, "item": item}),
                dict(method="item/agentMessage/delta", params={**params, "itemId": item["id"], "delta": "x" * (ASSISTANT_TEXT_BYTES + 1)}))
        else:
            complete_shared(driver, first.id, "Checked the private resume.")
        await asyncio.wait_for(service.supervisor.controls[first.id].task, 10)
        assert driver.pipe.process.poll() is None and not driver.fenced
        assert service.admission.locked() and len(service.parallel_owner.permits) == 2
        assert second.id in driver.live and reply.job.id in driver.live
        assert first.id in clients_closed and second.id not in clients_closed
        if scenario == "hung-tool":
            assert tool_released.is_set()
        if scenario in {"old-parser", "old-tool"}:
            if scenario == "old-parser":
                emit_shared(driver, dict(method="item/agentMessage/delta", params=dict(threadId=previous_slot.thread,
                    turnId=previous_slot.turn, itemId="old_A", delta="Foreign old answer")))
            else:
                emit_shared(driver, tool_frame(previous_slot, identifier=300, call="late_A", tool="get_resume_context",
                    arguments={"query": {"kind": "document", "ids": ["narrative"]}}))
            await driver.rpc("config/read", {"includeLayers": True})
            assert driver.live[second.id].slot.text == "" and len(driver.live[second.id].slot.calls) == 1
            if scenario == "old-tool":
                assert any(row["direction"] == "client" and row["frame"].get("id") == 300 for row in wire)
        outcome = service.store.read(workspace.project_id, first.id)
        assert outcome.execution == ("cancelled" if scenario in {"stop", "hung-tool"} else
            "failed" if scenario == "output-limit" else "completed")
        complete_shared(driver, reply.job.id, outputs[reply.job.id])
        done = await settled(service, workspace.project_id, reply.job.id, publication="saved")
        assert done.receipt.durable and scripted.calls
        complete_shared(driver, second.id, "Checked without editing.")
        await asyncio.wait_for(service.supervisor.controls[second.id].task, 10)
        if scenario == "owner-failure":
            from resume_api.lifecycle import SpikeError
            from spikes.background.appserver_protocol import TransportFailure
            with pytest.raises((SpikeError, TransportFailure)):
                await service.parallel_owner.idle()
            assert service.admission.blocked and service.admission.locked()
            assert service.supervisor.fenced == "CLEANUP_FAILED" and not service.supervisor.login_allowed()
            assert service.store.read(workspace.project_id, reply.job.id).receipt == done.receipt
            assert service.parallel_owner.reservation is not None and not service.parallel_owner.permits
            assert ledger.read_bytes() == before
            return
        await service.parallel_owner.idle()
        assert service.parallel_owner.server is None and service.parallel_owner.reservation is None
        assert not service.admission.locked() and service.supervisor.login_allowed()
        assert driver.closed and driver.pipe is None and driver.owner_context is None
        saved = service.projects.storage.read_committed(workspace.project_id)[0]
        assert "Clearer:" in next(b for b in saved.project.document.blocks() if b.id == "narrative").content[0].text
        assert ledger.read_bytes() == before
    finally:
        tool_released.set()
        if damaged:
            from contextlib import suppress
            from packages.resume_core.background_store import BackgroundFailure
            from resume_api.lifecycle import SpikeError
            from spikes.background.appserver_protocol import TransportFailure
            guard = damaged["guard"]
            guard.inspector.identity = damaged["original"]
            await asyncio.to_thread(guard.stop_verified_process)
            with suppress(SpikeError, TransportFailure, BackgroundFailure):
                await service.shutdown()
            with suppress(SpikeError, TransportFailure):
                await driver.close()
            service.content_pool.shutdown(wait=True, cancel_futures=True)
            assert guard.process.poll() is not None
        else:
            await service.shutdown()
            await driver.close()
        factory.verify()
        service.supervisor.clock.verify()
