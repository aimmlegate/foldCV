"""Durable pending authority survives the owned native stand-in's cleanup."""

import asyncio
import hashlib

import pytest

from packages.resume_core.background_proposals import JobProposals
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.background import ProposalBindingV1
from packages.resume_core import background_proposals as persistence
from spikes.background.fixtures import examples
from tests.recovery.test_background_store import capture
from tests.recovery.test_background_supervisor import environment


def proposal(control, payload):
    value = examples()["background_proposal_v1"]
    value.update(id="proposal_" + control.job.id, jobId=control.job.id, projectId=control.job.submission.identity.project_id,
        lineage=control.job.submission.identity.lineage, accountGeneration=control.job.submission.account_generation,
        executionGeneration=control.job.execution_generation, turnId=control.job.id,
        payloadSha256=hashlib.sha256(payload).hexdigest(), payloadBytes=len(payload),
        scope=control.job.submission.scope.model_dump(by_alias=True), executionDeadline=control.job.attempts[-1].active_deadline)
    value["payload"]["runId"] = control.job.id
    return ProposalBindingV1.model_validate(value)


@pytest.mark.asyncio
async def test_durable_acceptance_can_finish_binding_after_deadline_and_native_cleanup(tmp_path):
    reached, release = asyncio.Event(), asyncio.Event()
    async def observe(name, _job):
        if name == "payload_stored":
            reached.set()
            await release.wait()
    store, state, clock, factory, supervisor = await environment(tmp_path, observer=observe)
    payload = b'{"syntheticImmutablePayload":"accepted before expiry"}'
    proposals = JobProposals(supervisor, lambda _reference: payload)
    async def execute(control, _actor):
        await proposals.accept(control, proposal(control, payload))
        return ExecutionOutcome(finished_at=clock.now())
    factory.callbacks["deferred-binding"] = execute
    try:
        job, _ = await supervisor.submit(capture(state, "deferred-binding"))
        await asyncio.wait_for(reached.wait(), 10)
        clock.advance(180)
        control = supervisor.controls[job.id]
        await asyncio.wait_for(control.task, 10)
        assert supervisor.active is None and control.revoked
        assert store.read(state.project_id, job.id).execution == "failed"
        release.set()
        result = await asyncio.wait_for(proposals.tasks[job.id][1], 10)
        assert result.disposition == "waiting_for_sync" and not result.durable
        saved = store.load(state.project_id)
        assert saved.proposals[0].authority == "active"
        assert saved.jobs[0].publication == "waiting_for_sync"
    finally:
        release.set()
        await supervisor.shutdown(); await proposals.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_late_new_proposal_is_rejected_before_loading_any_payload(tmp_path):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    factory.hold_results.add("late-proposal")
    payload = b'{"syntheticImmutablePayload":"too late"}'
    loaded = []
    def load(reference):
        loaded.append(reference)
        return payload
    proposals = JobProposals(supervisor, load)
    try:
        job, _ = await supervisor.submit(capture(state, "late-proposal"))
        actor = await factory.actor(job)
        await asyncio.wait_for(actor.started.wait(), 10)
        control = supervisor.controls[job.id]
        clock.advance(180)
        with pytest.raises(BackgroundFailure, match="DEADLINE"):
            await proposals.accept(control, proposal(control, payload))
        await asyncio.wait_for(control.task, 10)
        assert loaded == [] and store.load(state.project_id).proposals == []
    finally:
        await supervisor.shutdown(); await proposals.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_stop_between_payload_and_binding_revokes_the_backend_request(tmp_path):
    reached, release = asyncio.Event(), asyncio.Event()
    async def observe(name, _job):
        if name == "payload_stored":
            reached.set()
            await release.wait()
    store, state, clock, factory, supervisor = await environment(tmp_path, observer=observe)
    payload = b'{"syntheticImmutablePayload":"explicit stop"}'
    proposals = JobProposals(supervisor, lambda _reference: payload)
    async def execute(control, _actor):
        await proposals.accept(control, proposal(control, payload))
        return ExecutionOutcome(finished_at=clock.now())
    factory.callbacks["stop-binding"] = execute
    try:
        job, _ = await supervisor.submit(capture(state, "stop-binding"))
        await asyncio.wait_for(reached.wait(), 10)
        await supervisor.cancel(state.project_id, job.id)
        await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        release.set()
        with pytest.raises(BackgroundFailure, match="CANCELLED"):
            await asyncio.wait_for(proposals.tasks[job.id][1], 10)
        assert store.read(state.project_id, job.id).publication == "cancelled"
        assert store.load(state.project_id).proposals == []
    finally:
        release.set()
        await supervisor.shutdown(); await proposals.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-0.001, 0, 0.001], ids=["NB-Q10:v07", "NB-Q10:v08", "NB-Q10:v09"])
async def test_payload_fsync_must_be_observed_before_the_acceptance_deadline(tmp_path, monkeypatch, offset):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    payload = b'{"syntheticImmutablePayload":"durability precedes authority"}'
    proposals = JobProposals(supervisor, lambda _reference: payload)
    observed, outcomes = [], []
    original = persistence.atomic_write
    def slow_save(path, raw):
        original(path, raw)
        observed.append(str(path))
        clock.advance(180 + offset)
    monkeypatch.setattr(persistence, "atomic_write", slow_save)
    async def execute(control, _actor):
        try:
            outcomes.append(await proposals.accept(control, proposal(control, payload)))
        except BackgroundFailure as error:
            outcomes.append(error.code)
        return ExecutionOutcome(finished_at=clock.now())
    factory.callbacks["deadline-acceptance"] = execute
    try:
        job, _ = await supervisor.submit(capture(state, "deadline-acceptance"))
        await factory.actor(job)
        await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        assert len(observed) == 1
        current = store.load(state.project_id)
        if offset < 0:
            assert outcomes[0].proposal_stored and not outcomes[0].durable
            assert len(current.proposals) == 1 and current.jobs[0].publication == "waiting_for_sync"
        else:
            assert outcomes == ["DEADLINE"]
            assert current.proposals == [] and current.jobs[0].proposal_id is None
        assert len(list((store.projects / state.project_id / "proposal-intents").glob("*.json"))) == 1
        assert supervisor.active is None
    finally:
        await supervisor.shutdown(); await proposals.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_fault_after_proposal_durability_keeps_pending_authority_and_releases_native(tmp_path):
    observed = []
    async def observe(name, job):
        if name == "proposal_durable":
            observed.append(job)
            raise OSError("synthetic lost deferred reply")
    store, state, clock, factory, supervisor = await environment(tmp_path, observer=observe)
    payload = b'{"syntheticImmutablePayload":"durable binding before lost reply"}'
    proposals = JobProposals(supervisor, lambda _reference: payload)
    async def execute(control, _actor):
        await proposals.accept(control, proposal(control, payload))
        return ExecutionOutcome(finished_at=clock.now())
    factory.callbacks["fault-proposal"] = execute
    try:
        job, _ = await supervisor.submit(capture(state, "fault-proposal"))
        await factory.actor(job)
        await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        assert observed == [job.id]
        current = store.load(state.project_id)
        assert current.jobs[0].publication == "waiting_for_sync"
        assert current.proposals[0].authority == "active" and supervisor.active is None
        fresh = type(store)(tmp_path, clock=store.clock)
        fresh.recover(state.project_id)
        assert fresh.load(state.project_id).proposals == current.proposals
        assert factory.calls == [(job.id, "agent")]
    finally:
        await supervisor.shutdown(); await proposals.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("review", [False, True], ids=["pending", "review"])
async def test_pending_payload_binding_keeps_backend_authority_after_runtime_exit(tmp_path, review):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    payload = b'{"syntheticImmutablePayload":"one copy in the artifact owner"}'
    proposals = JobProposals(supervisor, lambda _reference: payload)
    results = []

    async def execute(control, actor):
        value = proposal(control, payload)
        result = await proposals.accept(control, value, needs_review=review)
        assert not result.durable and result.proposal_stored
        assert await proposals.accept(control, value, needs_review=review) == result
        forged = value.model_copy(update={"id": "another-proposal"})
        with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
            await proposals.accept(control, forged)
        results.append(result)
        return ExecutionOutcome(finished_at=clock.now())

    factory.callbacks["pending-result"] = execute
    try:
        job, _ = await supervisor.submit(capture(state, "pending-result"))
        actor = await factory.actor(job)
        await asyncio.wait_for(actor.closed.wait(), 10)
        await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        assert results[0].disposition == ("needs_review" if review else "waiting_for_sync")
        current = store.load(state.project_id)
        assert current.jobs[0].execution == "completed"
        assert current.jobs[0].publication == results[0].disposition
        assert current.proposals[0].authority == "active"
        assert current.proposals[0].payload_sha256 == hashlib.sha256(payload).hexdigest()
        assert supervisor.controls[job.id].revoked
        assert supervisor.active is None
        with pytest.raises(BackgroundFailure, match="CANCELLED"):
            await proposals.accept(supervisor.controls[job.id], proposal(supervisor.controls[job.id], payload))
    finally:
        await supervisor.shutdown()
        await proposals.shutdown()
        factory.verify(); clock.verify()
