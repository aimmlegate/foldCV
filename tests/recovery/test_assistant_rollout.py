"""Old captured jobs never become approval when the staged protocol changes."""

import asyncio

import pytest

from tests.recovery.test_background_agent import environment
from packages.resume_core.agent_store import digest
from packages.resume_core.background_store import BackgroundFailure
from tests.support.background_publication import PublicationFixture


@pytest.mark.asyncio
async def test_old_queued_configuration_is_rejected_before_owned_runtime_dispatch(tmp_path):
    jobs, factory, workspace, payload, _, agent = await environment(tmp_path)
    jobs.supervisor.dispatch_enabled = False
    try:
        job, _ = await jobs.submit(workspace.project_id, payload)
        assert jobs.preflight(job) is None
        agent.assistant_protocol_enabled = True
        assert jobs.preflight(job) == 'JOB_SCOPE_INVALID'
        jobs.supervisor.dispatch_enabled = True
        jobs.supervisor.changed.set()
        for _ in range(200):
            current = jobs.store.read(workspace.project_id, job.id)
            if current.execution == 'failed':
                break
            await asyncio.sleep(0.01)
        assert current.execution == 'failed' and current.error.code == 'JOB_SCOPE_INVALID'
        assert not current.attempts and not factory.calls
        assert not jobs.projects.read(workspace.project_id).mutation_replay
    finally:
        await jobs.shutdown()
        factory.verify(); jobs.supervisor.clock.verify()


@pytest.mark.parametrize('phase', ['ready', 'waiting_for_sync', 'needs_review'])
def test_old_pending_publication_and_reconnect_stay_unapproved_after_restart(tmp_path, phase):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _ = fixture.accepted()
    fixture.jobs.update(fixture.project, job.id, lambda _state, current: setattr(current, 'publication', phase))
    before = digest(fixture.current())
    restarted = fixture.fresh()
    restarted.coordinator.assistant_review_required = lambda: True
    restarted.coordinator.recover(fixture.project)
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        restarted.publish(job, proposal)
    # A writer reconnect is still not a UI acceptance.
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        restarted.publish(job, proposal)
    current = restarted.jobs.read(fixture.project, job.id)
    assert current.publication == phase and current.receipt is None
    assert digest(restarted.current()) == before and not restarted.current().mutation_replay


@pytest.mark.parametrize('phase', ['commit_claimed', 'workspace_durable'])
def test_already_claimed_old_job_reconciles_its_original_canonical_proof(tmp_path, phase):
    def interrupt(name, _project):
        if name == phase:
            raise OSError('Synthetic interruption after old authority won')
    fixture = PublicationFixture(tmp_path, observer=interrupt)
    job, proposal, _ = fixture.accepted()
    try:
        fixture.publish(job, proposal)
    except (OSError, BackgroundFailure):
        pass
    restarted = fixture.fresh()
    restarted.coordinator.assistant_review_required = lambda: True
    restarted.coordinator.recover(fixture.project)
    current = restarted.jobs.read(fixture.project, job.id)
    saved = phase == 'workspace_durable'
    assert current.publication == ('saved' if saved else 'save_failed')
    assert len(restarted.current().mutation_replay) == int(saved)
    if saved:
        assert restarted.publish(job, proposal).receipt == current.receipt


@pytest.mark.asyncio
async def test_unexpected_queued_runtime_failure_seals_the_useful_continued_draft(tmp_path):
    from tests.recovery.test_assistant_continuation import incomplete
    from packages.resume_core.agent_store import journal_request
    from packages.resume_core.models.background import JobAgentRequestV1
    from packages.resume_core.models.assistant_continuation import AssistantContinueJobV1
    from resume_api.agent.continuation import submit_job
    from resume_api.agent.runtime import ScriptedAgentRuntime
    from resume_api.jobs.service import JobService
    from resume_api.inference_admission import InferenceAdmission
    agent, _, projects, workspace, original, payload = await incomplete(tmp_path)
    async def fail(*_args):
        raise RuntimeError('Synthetic unexpected runtime failure')
    runtime = ScriptedAgentRuntime(fail)
    jobs = JobService(projects, runtime, agent.connection, enabled=True, admission=InferenceAdmission())
    before = projects.storage.read_committed(workspace.project_id)[1]
    try:
        await jobs.start()
        context = jobs.project(workspace.project_id)
        body = AssistantContinueJobV1(protocolVersion=1, proposal=payload.proposal,
            request=JobAgentRequestV1(schemaVersion=1, lineage=context.lineage, requestEpoch=context.request_epoch,
                request=journal_request(payload.request)))
        job, _ = await submit_job(agent, jobs, workspace.project_id, body)
        for _ in range(200):
            control = jobs.supervisor.controls.get(job.id)
            if control is not None and control.task.done():
                break
            await asyncio.sleep(0.01)
        assert control is not None and control.task.done()
        draft = agent.proposals.get(workspace.project_id, original.proposal.id, 2)
        assert draft.proposal.state == 'incomplete'
        assert draft.proposal.content_sha256 == original.proposal.content_sha256
        assert jobs.store.read(workspace.project_id, job.id).execution == 'failed'
        assert projects.storage.read_committed(workspace.project_id)[1] == before
        assert runtime.native is False and runtime.calls == ['assistant-model']
    finally:
        with pytest.raises(BackgroundFailure, match='CLEANUP_FAILED'):
            await jobs.shutdown()
        jobs.content_pool.shutdown(wait=True, cancel_futures=True)


@pytest.mark.asyncio
async def test_queued_continue_refuses_a_different_captured_account_before_dispatch(tmp_path):
    from tests.recovery.test_assistant_continuation import incomplete
    from packages.resume_core.agent_store import AgentFailure, journal_request
    from packages.resume_core.models.background import JobAgentRequestV1
    from packages.resume_core.models.assistant_continuation import AssistantContinueJobV1
    from resume_api.agent.continuation import submit_job
    from resume_api.agent.service import AgentConnection
    from resume_api.jobs.service import JobService
    from resume_api.inference_admission import InferenceAdmission
    agent, runtime, projects, workspace, original, payload = await incomplete(tmp_path)
    jobs = JobService(projects, runtime, lambda: AgentConnection(True, ('assistant-model',), 'different_account'),
        enabled=True, admission=InferenceAdmission())
    try:
        await jobs.start()
        context = jobs.project(workspace.project_id)
        body = AssistantContinueJobV1(protocolVersion=1, proposal=payload.proposal,
            request=JobAgentRequestV1(schemaVersion=1, lineage=context.lineage, requestEpoch=context.request_epoch,
                request=journal_request(payload.request)))
        with pytest.raises(AgentFailure, match='AGENT_CONNECTION_CHANGED'):
            await submit_job(agent, jobs, workspace.project_id, body)
        assert agent.proposals.list(workspace.project_id) == [original]
        assert all(job.execution == 'cancelled' and not job.attempts for job in jobs.store.load(workspace.project_id).jobs)
        assert not runtime.calls and not projects.read(workspace.project_id).mutation_replay
    finally:
        await jobs.shutdown()
