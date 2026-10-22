"""Both entry paths share cancellation winners and inference-free finalization resume."""

import asyncio
import threading

import pytest

from packages.resume_core.template_import import spent_calls
from tests.templates.pipeline_fixtures import resume_command
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_job_routing import service_for


async def queued(service, fixture, command):
    job, _created = await service.templates.submit(fixture.project, command)
    async def finish():
        while True:
            current = service.store.read(fixture.project, job.id)
            if current.template_outcome is not None:
                return current
            await asyncio.sleep(0.02)
    return await asyncio.wait_for(finish(), 60)


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_cancel_before_claim_needs_fresh_resume_without_new_model_calls(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    publisher = pipeline.publisher
    cancelled = []
    def cancel(name, project):
        if name == 'before_commit_claim':
            intents = publisher.jobs.load(project).manual_intents
            if intents and intents[-1].template_finalization is not None:
                cancelled.append(publisher.cancel_template(project, intents[-1].template_finalization.operation_id))
    publisher.observer = cancel
    try:
        if service:
            job = await queued(service, fixture, fixture.command)
            assert job.template_outcome.state == 'cancelled'
        else:
            result = await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
            assert result.publication.state == 'cancelled'
        current = fixture.current()
        assert current.project is None and cancelled == [True]
        operation = current.pre_draft.template_operations[0]
        assert operation.state == 'cancelled' and operation.finalization is not None
        calls, expires, finalization = len(fixture.transport.calls), operation.expires_at, operation.finalization
        publisher.observer = lambda *_args: None
        fixture.now = '2026-10-21T00:06:00+00:00'
        command = resume_command(operation)
        if service:
            result = await queued(service, fixture, command)
            assert result.template_outcome.state == 'saved'
        else:
            result = await pipeline.run(fixture.project, command, admitted=fixture.admitted)
            assert result.publication.state == 'saved'
        saved = fixture.current().project.template_operations[0]
        assert len(fixture.transport.calls) == calls == spent_calls(saved) == 2
        assert saved.expires_at == expires and saved.capture == operation.capture
        assert saved.finalization_history == [finalization] and saved.finalization.id != finalization.id
        assert saved.finalization.candidate_hash == finalization.candidate_hash
        assert len([intent for intent in publisher.jobs.load(fixture.project).manual_intents
            if intent.template_finalization is not None]) == 2
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('phase', ['commit_claimed', 'workspace_replaced'])
async def test_cancellation_after_claim_reports_actual_saved_result(tmp_path, entry, phase):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    publisher, results, threads, claimed = pipeline.publisher, [], [], []
    def after_claim(name, project):
        if name == 'before_commit_claim':
            intents = publisher.jobs.load(project).manual_intents
            claimed[:] = [intents[-1].template_finalization] if intents and intents[-1].template_finalization is not None else []
        if name != phase:
            return
        # The callback holds the guard; a separate caller must observe the claimed winner.
        if not claimed:
            return
        operation_id = claimed[0].operation_id
        thread = threading.Thread(target=lambda: results.append(publisher.cancel_template(project, operation_id)))
        threads.append(thread)
        thread.start()
    publisher.observer = after_claim
    try:
        if service:
            result = await queued(service, fixture, fixture.command)
            assert result.template_outcome.state == 'saved'
        else:
            result = await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
            assert result.publication.state == 'saved'
        for thread in threads:
            await asyncio.to_thread(thread.join, 5)
            assert not thread.is_alive()
        assert results == [False] and fixture.current().project is not None
        assert len(fixture.transport.calls) == 2
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('denial', ['authority', 'expiry'])
async def test_finalization_rechecks_authority_and_its_independent_expiry(tmp_path, entry, denial):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    reached = []
    def deny(name, project):
        if name == 'before_commit_claim':
            intents = pipeline.publisher.jobs.load(project).manual_intents
            if intents and intents[-1].template_finalization is not None:
                reached.append(denial)
                if denial == 'authority':
                    fixture.external_authority = False
                else:
                    fixture.now = '2026-10-21T00:00:31+00:00'
    pipeline.publisher.observer = deny
    try:
        if service:
            result = await queued(service, fixture, fixture.command)
            outcome = result.template_outcome
        else:
            result = await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
            outcome = result.publication
        assert outcome.state == 'failed_before_replacement' and reached == [denial]
        assert fixture.current().project is None and len(fixture.transport.calls) == 2
        assert outcome.error_code == ('DEPENDENCY_CHANGED' if denial == 'authority' else 'REQUEST_EXPIRED')
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
