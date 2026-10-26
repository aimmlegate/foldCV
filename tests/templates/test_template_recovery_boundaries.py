"""Startup proof controls reservation release and exact captured-operation resume."""

import asyncio

import pytest

from packages.resume_core.template_import import (CleanupProof, admit_operation, capture_task_input, digest,
    dispatch_attempt, reserve_attempt, spent_calls)
from tests.templates.pipeline_fixtures import owner, resume_command
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for
from tests.templates.test_semantic_admission import raw_proposal


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('dispatched', [False, True])
async def test_restart_proves_owner_before_releasing_or_retaining_spending(tmp_path, entry, dispatched):
    fixture = RuntimeFixture(tmp_path)
    operation = await fixture.pipeline.start(fixture.project, fixture.command)
    def interrupted(value, data, _workspace):
        value = admit_operation(value, fixture.now)
        task = value.tasks[0]
        captured, handles = fixture.pipeline.task_input(value, task, data)
        value = capture_task_input(value, task.id, captured, handles, fixture.now)
        request = {**captured, 'slot': 'initial', 'feedback': [], 'capturedHandles': [], 'capturedRelations': []}
        value, attempt = reserve_attempt(value, task.id, 'initial', digest(request), value.capture.primary,
            owner(999), fixture.now, request_value=request)
        return dispatch_attempt(value, attempt, fixture.now) if dispatched else value
    await asyncio.to_thread(fixture.pipeline.update, fixture.project, operation.id, interrupted)
    previous = fixture.current().pre_draft.template_operations[0]
    fixture.transport.reconcile = lambda attempt: CleanupProof(attempt.id, digest(attempt.owner), digest('owned-terminal-proof'),
        'controlled-owned-reservation-proof', not dispatched)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.fresh_pipeline()
    command = resume_command(previous)
    try:
        if service:
            await queued(service, fixture, command)
            result = fixture.current().project.template_operations[0]
        else:
            result = await pipeline.run(fixture.project, command, admitted=fixture.admitted)
        assert result.state == 'published' and result.capture == previous.capture and result.expires_at == previous.expires_at
        assert result.attempts[0].owner == previous.attempts[0].owner
        if dispatched:
            assert result.attempts[0].state == 'outcome_unknown' and spent_calls(result) == 1
            assert not fixture.transport.calls and result.tasks[0].state == 'source_fallback'
        else:
            assert result.attempts[0].state == 'released' and spent_calls(result) == 2
            assert len(fixture.transport.calls) == 2
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_spent_primary_and_uncertain_fallback_resume_without_any_resend(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path)
    rejected = []
    def script(_request, value):
        if 'targets' in value:
            rejected.extend(allocation['cellIds']['journal'] for allocation in value['handleMap'] if allocation['key'] == 'b')
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if target['targetId'] in rejected else 'satisfied',
                'reason': 'Journal is unsupported' if target['targetId'] in rejected else '',
                'actionable': target['targetId'] in rejected, 'evidence': []} for target in value['targets']]}
        if value['slot'] == 'primary_repair':
            return '{invalid primary repair'
        if value['slot'] == 'fallback_repair':
            raise SystemExit('controlled loss after fallback dispatch')
        result = raw_proposal(fixture.source)
        result['payload'][1]['journal'] = 'Invented journal'
        return result
    fixture.transport.scripted = script
    with pytest.raises(SystemExit):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    previous = fixture.current().pre_draft.template_operations[0]
    assert spent_calls(previous) == len(fixture.transport.calls) == 4
    assert previous.attempts[-1].slot == 'fallback_repair' and previous.attempts[-1].state == 'dispatch_started'
    fixture.transport.reconcile = lambda attempt: CleanupProof(attempt.id, digest(attempt.owner), digest('fallback-terminal'),
        'controlled-owned-fallback-terminal')
    fixture.transport.scripted = lambda *_args: pytest.fail('resume cannot repeat a consumed slot')
    service = await service_for(fixture) if entry == 'queued' else None
    try:
        if service:
            await queued(service, fixture, resume_command(previous))
            result = fixture.current().project.template_operations[0]
        else:
            result = await fixture.fresh_pipeline().run(fixture.project, resume_command(previous), admitted=fixture.admitted)
        assert result.state == 'published' and result.tasks[0].state == 'accepted'
        assert result.task_results[0].disposition == 'source_fallback'
        assert result.capture == previous.capture and result.expires_at == previous.expires_at
        assert result.allocations == previous.allocations and result.id == previous.id
        assert result.attempts[-1].state == 'outcome_unknown' and spent_calls(result) == 4
        assert len(fixture.transport.calls) == 4
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
