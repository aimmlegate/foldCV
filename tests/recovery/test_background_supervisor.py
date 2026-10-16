"""The capacity-one supervisor owns real pipe processes through verified cleanup."""

import asyncio
from datetime import datetime, timedelta

import pytest

from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_store import JobStore
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import JobSupervisor
from spikes.background.fixtures import TIME
from tests.recovery.test_background_store import capture
from tests.support.agent import isolated_project
from tests.support.background import PipeExecutions


async def environment(root, *, observer=None):
    _, _, workspace, _ = isolated_project(root)
    clock = ControlledDeadlines()
    base = datetime.fromisoformat(TIME.replace("Z", "+00:00"))
    store = JobStore(root, clock=lambda: (base + timedelta(seconds=clock.now())).isoformat())
    state = store.open(workspace.project_id)
    factory = PipeExecutions(root / "pipes", clock)
    supervisor = JobSupervisor(store, factory, clock=clock, **({"observer": observer} if observer else {}))
    await supervisor.start()
    return store, state, clock, factory, supervisor


@pytest.mark.asyncio
async def test_native_slot_is_held_until_owned_cleanup_and_the_next_job_then_runs(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_results.add("first")
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        second, _ = await supervisor.submit(capture(state, "second"))
        assert store.read(state.project_id, second.id).execution == "queued"
        assert factory.calls == [(first.id, "agent")]
        actor.result.set()
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        second_actor = await factory.actor(second)
        await asyncio.wait_for(second_actor.closed.wait(), 10)
        await asyncio.wait_for(supervisor.controls[second.id].task, 10)
        assert [store.read(state.project_id, job.id).execution for job in (first, second)] == ["completed", "completed"]
        assert supervisor.active is None
    finally:
        for actor in factory.actors.values():
            actor.result.set(); actor.ready_permission.set(); actor.cleanup_permission.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,offset", [(phase, offset) for phase in ("startup", "active") for offset in (-0.001, 0, 0.001)],
    ids=[f"NB-Q10:v{index:02d}" for index in range(1, 7)])
async def test_attempt_deadlines_use_elapsed_time_at_the_exact_boundary(tmp_path, phase, offset):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_results.add("deadline")
    if phase == "startup":
        factory.hold_startup.add("deadline")
    try:
        job, _ = await supervisor.submit(capture(state, "deadline"))
        actor = await factory.actor(job)
        await asyncio.wait_for((actor.child_ready if phase == "startup" else actor.started).wait(), 10)
        clock.advance((15 if phase == "startup" else 180) + offset)
        if offset < 0:
            actor.ready_permission.set()
            actor.result.set()
        control = supervisor.controls[job.id]
        await asyncio.wait_for(control.task, 10)
        result = store.read(state.project_id, job.id)
        assert result.execution == ("completed" if offset < 0 else "failed")
        assert (result.error.code if result.error else None) == (None if offset < 0 else "STARTUP_TIMEOUT" if phase == "startup" else "DEADLINE")
    finally:
        for actor in factory.actors.values():
            actor.ready_permission.set(); actor.result.set(); actor.cleanup_permission.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_cancellation_after_slot_grant_prevents_the_owned_child_start(tmp_path):
    reached, release = asyncio.Event(), asyncio.Event()
    async def observer(name, _job):
        if name == "slot_granted":
            reached.set()
            await release.wait()
    store, state, clock, factory, supervisor = await environment(tmp_path, observer=observer)
    try:
        job, _ = await supervisor.submit(capture(state))
        await asyncio.wait_for(reached.wait(), 10)
        await supervisor.cancel(state.project_id, job.id)
        release.set()
        await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        assert factory.calls == []
        assert store.read(state.project_id, job.id).execution == "cancelled"
    finally:
        release.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_unverified_cleanup_keeps_the_slot_and_blocks_the_next_job(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_cleanup.add("first")
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.cleanup_started.wait(), 10)
        second, _ = await supervisor.submit(capture(state, "second"))
        assert supervisor.active is supervisor.controls[first.id]
        assert actor.child.command("probe") == {"type": "alive"}
        clock.advance(5)
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        assert supervisor.fenced == "CLEANUP_FAILED" and supervisor.active is not None
        assert store.read(state.project_id, second.id).execution == "queued"
        assert factory.calls == [(first.id, "agent")]
        actor.cleanup_permission.set()
        await asyncio.wait_for(actor.closed.wait(), 10)
        await supervisor.verify_cleanup(first.id)
        next_actor = await factory.actor(second)
        await asyncio.wait_for(next_actor.closed.wait(), 10)
        await asyncio.wait_for(supervisor.controls[second.id].task, 10)
        assert store.read(state.project_id, second.id).execution == "completed"
    finally:
        for actor in factory.actors.values():
            actor.ready_permission.set(); actor.result.set(); actor.cleanup_permission.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["RATE_LIMITED", "AUTH_REQUIRED", "MODEL_DENIED"])
async def test_typed_runtime_failure_pauses_only_when_account_dispatch_requires_it(tmp_path, code):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.errors["first"] = code
    factory.hold_results.add("first")
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        assert not supervisor.login_allowed()
        second, _ = await supervisor.submit(capture(state, "second"))
        actor.result.set()
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        assert store.read(state.project_id, first.id).error.code == code
        if code in {"RATE_LIMITED", "AUTH_REQUIRED"}:
            assert supervisor.paused == store.dispatch_state().paused == code
            assert store.read(state.project_id, second.id).execution == "queued"
            assert factory.calls == [(first.id, "agent")]
            await supervisor.cancel(state.project_id, second.id)
            assert store.read(state.project_id, second.id).execution == "cancelled"
        else:
            second_actor = await factory.actor(second)
            await asyncio.wait_for(second_actor.closed.wait(), 10)
            await asyncio.wait_for(supervisor.controls[second.id].task, 10)
            assert store.read(state.project_id, second.id).execution == "completed"
            assert supervisor.paused is None
    finally:
        for actor in factory.actors.values():
            actor.ready_permission.set(); actor.result.set(); actor.cleanup_permission.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_confirmed_account_change_revokes_old_jobs_before_new_dispatch(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_results.add("first")
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        second, _ = await supervisor.submit(capture(state, "second"))
        supervisor.confirmed_account_change(2)
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        assert store.read(state.project_id, first.id).error.code == "ACCOUNT_CHANGED"
        assert store.read(state.project_id, second.id).execution == "cancelled"
        assert factory.calls == [(first.id, "agent")]
        current = store.load(state.project_id)
        assert current.account_generation == 2
        with pytest.raises(BackgroundFailure, match="ACCOUNT_CHANGED"):
            store.submit(capture(state, "stale-account"))
        supervisor.resume(2)
        third, _ = await supervisor.submit(capture(current, "new-account"))
        new_actor = await factory.actor(third)
        await asyncio.wait_for(new_actor.closed.wait(), 10)
        await asyncio.wait_for(supervisor.controls[third.id].task, 10)
        assert store.read(state.project_id, third.id).execution == "completed"
    finally:
        for actor in factory.actors.values():
            actor.ready_permission.set(); actor.result.set(); actor.cleanup_permission.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("hook", ["queue_eligible", "slot_granted", "before_spawn", "child_started",
    "cleanup_started", "children_verified_dead", "slot_released"])
async def test_dispatch_faults_reach_the_boundary_without_releasing_live_ownership(tmp_path, hook):
    reached = []
    async def observe(name, job):
        if name == hook:
            reached.append(job)
            raise RuntimeError("synthetic dispatch boundary failure")
    store, state, clock, factory, supervisor = await environment(tmp_path, observer=observe)
    try:
        job, _ = await supervisor.submit(capture(state))
        # slot_released is the final drive boundary; its own signal has no polling.
        finished = asyncio.Event()
        original = supervisor.observer
        async def final_observer(name, identity):
            try:
                await original(name, identity)
            finally:
                if name == "slot_released" or name == hook:
                    finished.set()
        supervisor.observer = final_observer
        await asyncio.wait_for(finished.wait(), 10)
        await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        assert reached == [job.id]
        assert supervisor.active is None
        assert all(actor.verified_dead() for actor in factory.actors.values())
        if hook in {"queue_eligible", "slot_granted", "before_spawn"}:
            assert factory.calls == []
        if hook == "slot_released":
            assert supervisor.fenced == "CLEANUP_FAILED"
    finally:
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_queued_cancel_does_not_start_a_process_or_cancel_its_neighbour(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_results.add("first")
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        second, _ = await supervisor.submit(capture(state, "second"))
        await supervisor.cancel(state.project_id, second.id)
        assert actor.child.command("probe") == {"type": "alive"}
        assert store.read(state.project_id, second.id).execution == "cancelled"
        actor.result.set()
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        assert factory.calls == [(first.id, "agent")]
    finally:
        for actor in factory.actors.values():
            actor.result.set(); actor.ready_permission.set(); actor.cleanup_permission.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-Q02:v03", "NB-Q02:v04", "NB-Q02:v05"])
async def test_stop_after_child_start_or_during_cleanup_keeps_the_owned_slot(tmp_path, variant):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_results.add("first")
    factory.hold_cleanup.add("first")
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        second, _ = await supervisor.submit(capture(state, "second"))
        if variant == "NB-Q02:v04":
            actor.result.set()
            await asyncio.wait_for(actor.cleanup_started.wait(), 10)
        await supervisor.cancel(state.project_id, first.id)
        if variant == "NB-Q02:v05":
            await supervisor.cancel(state.project_id, first.id)
        await asyncio.wait_for(actor.cleanup_started.wait(), 10)
        assert supervisor.active is supervisor.controls[first.id]
        assert store.read(state.project_id, second.id).execution == "queued"
        assert actor.child.command("probe") == {"type": "alive"}
        actor.cleanup_permission.set()
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        neighbour = await factory.actor(second)
        await asyncio.wait_for(neighbour.closed.wait(), 10)
        await asyncio.wait_for(supervisor.controls[second.id].task, 10)
        assert factory.calls == [(first.id, "agent"), (second.id, "agent")]
        assert store.read(state.project_id, first.id).execution == "cancelled"
        assert store.read(state.project_id, second.id).execution == "completed"
    finally:
        for actor in factory.actors.values():
            actor.cleanup_permission.set(); actor.result.set()
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-Q10:v11", "NB-Q10:v12"])
async def test_sleep_and_wall_clock_rollback_cannot_extend_the_active_deadline(tmp_path, variant):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_results.add("first")
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        if variant == "NB-Q10:v12":
            store.clock = lambda: "2026-10-01T00:00:00Z"
        clock.advance(3600 if variant == "NB-Q10:v11" else 180)
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        current = store.read(state.project_id, first.id)
        assert current.error.code == "DEADLINE" and current.execution == "failed"
        assert len(current.attempts) == 1 and current.attempts[0].cleanup_verified
        assert supervisor.active is None
    finally:
        await supervisor.shutdown()
        factory.verify(); clock.verify()
