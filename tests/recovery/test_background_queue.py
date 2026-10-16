"""Atomic pending reserves and real capacity-one ordering across projects/classes."""

import asyncio

import pytest

from packages.resume_core.background_store import BackgroundFailure, JobStore
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.background import JobSubmissionV1
from spikes.background.fixtures import TIME
from tests.recovery.test_background_store import capture
from tests.recovery.test_background_supervisor import environment
from tests.support.agent import isolated_project


def captured(state, key, kind="agent"):
    value = capture(state, key).model_dump(by_alias=True)
    if kind != "agent":
        stages = {"rewrite": ["rewrite"], "reconciliation": ["reconciliation"],
            "processing": ["assessment", "extraction"]}[kind]
        value.update(kind=kind, schedulingClass={"rewrite": "interactive", "processing": "background",
            "reconciliation": "reconciliation"}[kind], tools=[], allowWeb=False,
            input={"kind": "processing" if kind == "processing" else "rich_sync", "id": "synthetic-input", "sha256": "a" * 64},
            models=[{"stage": stage, "model": "synthetic-model", "configSha256": "a" * 64} for stage in stages])
    return JobSubmissionV1.model_validate(value)


def contexts(root, count):
    _, canonical, workspace, _ = isolated_project(root)
    store = JobStore(root, clock=lambda: TIME)
    result = []
    for index in range(count):
        clone = workspace.model_copy(deep=True)
        clone.project_id = clone.project.project_id = "queue-project-" + str(index)
        canonical.save(clone, {}, {})
        result.append(store.open(clone.project_id))
    return store, result


@pytest.mark.parametrize("variant", [f"NB-Q01:v{index:02d}" for index in range(1, 15)])
def test_pending_limits_preserve_interactive_places_and_exact_replay(tmp_path, variant):
    number = int(variant.rsplit("v", 1)[1])
    global_scope = number in {1, 2, 3, 7, 8, 9}
    store, states = contexts(tmp_path, 7 if global_scope else 1)
    if number <= 3:
        desired, maximum, kind, per_project = 18 + number, 20, "rewrite", 4
    elif number <= 6:
        desired, maximum, kind, per_project = number - 1, 4, "rewrite", 4
    elif number <= 9:
        desired, maximum, kind, per_project = number + 8, 16, "agent", 3
    elif number <= 12:
        desired, maximum, kind, per_project = number - 8, 3, "agent", 3
    else:
        desired, maximum, kind, per_project = 4, 4, "rewrite", 4
    before = min(desired - 1, maximum)
    jobs = []
    for index in range(before):
        state = states[index // per_project] if global_scope else states[0]
        jobs.append(store.submit(captured(state, "queued-" + str(index), kind))[0])
    target = states[before // per_project] if global_scope else states[0]
    attempt = captured(target, "last-place", kind)
    if desired > maximum:
        with pytest.raises(BackgroundFailure, match="JOB_QUEUE_FULL"):
            store.submit(attempt)
    else:
        final, created = store.submit(attempt)
        assert created and final.execution == "queued" and final.attempts == []
        jobs.append(final)
    assert sum(len(state.jobs) for state in store.snapshots().values()) == min(desired, maximum)
    if number == 13:
        replay, created = store.submit(attempt)
        assert replay == final and not created
        with pytest.raises(BackgroundFailure, match="JOB_QUEUE_FULL"):
            store.submit(captured(target, "overflow", kind))
    if number == 14:
        store.cancel(target.project_id, jobs[0].id)
        replacement, created = store.submit(captured(target, "replacement", kind))
        assert created and replacement.id not in {job.id for job in jobs}
    if kind == "agent" and desired >= maximum:
        rewrite, created = store.submit(captured(target, "reserved-rewrite", "rewrite"))
        assert created and rewrite.submission.scheduling_class == "interactive"
    assert all(job.attempts == [] for state in store.snapshots().values() for job in state.jobs)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-Q03:v01", "NB-Q03:v02", "NB-Q03:v03"])
async def test_fifo_round_robin_and_an_ineligible_head_use_the_real_dispatcher(tmp_path, variant):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    from packages.resume_core.rich_project_store import RichProjectStore
    canonical = RichProjectStore(tmp_path)
    workspace = canonical.load_all()[0][state.project_id][0]
    workspace.project_id = workspace.project.project_id = "other-project"
    canonical.save(workspace, {}, {})
    other = store.open(workspace.project_id)
    supervisor.pause("RATE_LIMITED")
    blocked = set()
    supervisor.eligible = lambda job: job.id not in blocked
    try:
        first, _ = await supervisor.submit(capture(state, "first"))
        second, _ = await supervisor.submit(capture(state, "second"))
        jobs = [first, second]
        if variant != "NB-Q03:v01":
            third, _ = await supervisor.submit(capture(other, "other-first"))
            fourth, _ = await supervisor.submit(capture(other, "other-second"))
            jobs.extend([third, fourth])
        if variant == "NB-Q03:v03":
            blocked.add(first.id)
        supervisor.resume(1)
        if variant == "NB-Q03:v03":
            for job in (third, fourth):
                actor = await factory.actor(job)
                await asyncio.wait_for(actor.closed.wait(), 10)
                await asyncio.wait_for(supervisor.controls[job.id].task, 10)
            assert [item[0] for item in factory.calls] == [third.id, fourth.id]
            assert store.read(state.project_id, second.id).execution == "queued"
            blocked.clear(); supervisor.changed.set()
        for job in jobs:
            actor = await factory.actor(job)
            await asyncio.wait_for(actor.closed.wait(), 10)
            await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        order = [item[0] for item in factory.calls]
        if variant == "NB-Q03:v01":
            assert order == [first.id, second.id]
        elif variant == "NB-Q03:v02":
            expected = [first.id, third.id, second.id, fourth.id] if state.project_id < other.project_id else [third.id, first.id, fourth.id, second.id]
            assert order == expected
        else:
            assert order == [third.id, fourth.id, first.id, second.id]
    finally:
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-Q03:v04", "NB-Q05:v04"])
async def test_capacity_one_serializes_all_kinds_and_both_processing_stages(tmp_path, variant):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    supervisor.pause("RATE_LIMITED")
    observed = []
    async def execute(control, actor):
        assert supervisor.active is control
        assert all(other is actor or other.verified_dead() for other in factory.actors.values())
        observed.append((control.job.id, actor.model.stage))
        return ExecutionOutcome(finished_at=clock.now())
    jobs = []
    try:
        for kind in ("agent", "processing", "rewrite", "reconciliation"):
            factory.callbacks[kind] = execute
            jobs.append((await supervisor.submit(captured(state, kind, kind)))[0])
        supervisor.resume(1)
        for job in jobs:
            await factory.actor(job)
            await asyncio.wait_for(supervisor.controls[job.id].task, 10)
            assert store.read(state.project_id, job.id).execution == "completed"
        assert len(observed) == 5 and observed == factory.calls
        processing = next(job for job in jobs if job.submission.kind == "processing")
        stages = [stage for identifier, stage in observed if identifier == processing.id]
        assert stages == ["assessment", "extraction"]
        assert len(store.read(state.project_id, processing.id).attempts) == 2
    finally:
        await supervisor.shutdown()
        factory.verify(); clock.verify()
