"""Current-agent review regressions for runtime cancellation and durable links."""

import asyncio
import json

import pytest

from packages.resume_core.background_proposals import JobProposals
from packages.resume_core.background_store import BackgroundFailure, JobStore
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.project_store import encoded
from packages.resume_core.storage import atomic_write
from tests.recovery.test_background_agent import environment as agent_environment
from tests.recovery.test_background_proposals import proposal
from tests.recovery.test_background_store import capture
from tests.recovery.test_background_supervisor import environment


@pytest.mark.asyncio
async def test_cancel_after_runtime_entry_before_turn_readiness_releases_the_real_permit(tmp_path):
    from resume_api.agent.runtime import ScriptedAgentRuntime
    from resume_api.jobs.runtime import JobRuntime
    service, factory, workspace, request, _connection, _old = await agent_environment(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    owned = []
    class BeforeTurn(ScriptedAgentRuntime):
        async def run(self, value, cancel, emit):
            entered.set()
            await release.wait()
            return await super().run(value, cancel, emit)
    def own(job, model):
        execution = JobRuntime(service, job, model)
        owned.append(execution)
        return execution
    service.runtime = BeforeTurn(None)
    service.supervisor.factory = own
    try:
        job, _ = await service.submit(workspace.project_id, request)
        await asyncio.wait_for(entered.wait(), 10)
        assert service.admission.locked() and not service.supervisor.controls[job.id].ready.is_set()
        await service.supervisor.cancel(workspace.project_id, job.id)
        release.set()
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        current = service.store.read(workspace.project_id, job.id)
        assert current.execution == "cancelled" and current.attempts[0].cleanup_verified, current
        assert service.supervisor.active is None and not service.admission.locked()
        assert owned[0].verified_dead() and not owned[0].session.active
    finally:
        release.set()
        try:
            await service.shutdown()
        except BackgroundFailure:
            assert all(execution.session.listener.fileno() == -1 and execution.session.task.done() for execution in owned)
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "foreign-job", "account", "execution-generation", "duplicate", "revoked"])
async def test_valid_json_with_broken_proposal_links_is_fenced_without_reset(tmp_path, fault):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    payload = b'{"syntheticImmutablePayload":"bound exact owner"}'
    proposals = JobProposals(supervisor, lambda _ref: payload)
    async def execute(control, _actor):
        await proposals.accept(control, proposal(control, payload))
        return ExecutionOutcome(finished_at=clock.now())
    factory.callbacks["bound-proposal"] = execute
    try:
        job, _ = await supervisor.submit(capture(state, "bound-proposal"))
        await factory.actor(job)
        await asyncio.wait_for(supervisor.controls[job.id].task, 10)
        await supervisor.shutdown(); await proposals.shutdown()
        path = store.projects / state.project_id / "state.json"
        value = json.loads(path.read_bytes())
        if fault == "missing":
            value["proposals"] = []
        elif fault == "foreign-job":
            value["proposals"][0]["jobId"] = "foreign-job"
        elif fault == "account":
            value["proposals"][0]["accountGeneration"] += 1
        elif fault == "execution-generation":
            value["proposals"][0]["executionGeneration"] += 1
        elif fault == "duplicate":
            value["proposals"].append(value["proposals"][0].copy())
        else:
            value["proposals"][0].update(authority="revoked", revocation="stop")
        raw = encoded(value)
        atomic_write(path, raw)
        fresh = JobStore(tmp_path)
        with pytest.raises(BackgroundFailure, match="JOB_STORE_CORRUPT"):
            fresh.load(state.project_id)
        assert path.read_bytes() == raw and fresh.fences[state.project_id] == "JOB_STORE_CORRUPT"
    finally:
        await supervisor.shutdown(); await proposals.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["RATE_LIMITED", "AUTH_REQUIRED"])
async def test_account_failure_observed_during_deadline_cleanup_still_pauses_dispatch(tmp_path, code):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    observed = asyncio.Event()
    async def execute(control, _actor):
        await control.cancelled.wait()
        observed.set()
        return ExecutionOutcome("failed", code, clock.now())
    factory.callbacks["deadline-and-account"] = execute
    try:
        first, _ = await supervisor.submit(capture(state, "deadline-and-account"))
        actor = await factory.actor(first)
        await asyncio.wait_for(actor.started.wait(), 10)
        second, _ = await supervisor.submit(capture(state, "still-queued"))
        clock.advance(180)
        await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        assert observed.is_set()
        assert store.read(state.project_id, first.id).error.code == "DEADLINE"
        assert supervisor.paused == store.dispatch_state().paused == code
        assert store.read(state.project_id, second.id).execution == "queued"
        assert factory.calls == [(first.id, "agent")]
    finally:
        await supervisor.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.asyncio
async def test_secondary_outcome_observation_cannot_interrupt_verified_cleanup(tmp_path):
    class SyntheticFatal(BaseException):
        pass
    store, state, clock, factory, supervisor = await environment(tmp_path)
    async def execute(_control, _actor):
        raise SyntheticFatal("synthetic nonstandard runtime exit")
    factory.callbacks["fatal-result"] = execute
    try:
        first, _ = await supervisor.submit(capture(state, "fatal-result"))
        actor = await factory.actor(first)
        with pytest.raises(SyntheticFatal):
            await asyncio.wait_for(supervisor.controls[first.id].task, 10)
        assert actor.verified_dead() and supervisor.active is None
        assert store.read(state.project_id, first.id).execution == "failed"
        assert store.read(state.project_id, first.id).attempts[0].cleanup_verified
    finally:
        await supervisor.shutdown()
        factory.verify(); clock.verify()
