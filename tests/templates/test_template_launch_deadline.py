"""Durable launch transitions cannot carry a stale inference deadline."""

import asyncio

import pytest

from packages.resume_core.template_import import CleanupProof, digest, spent_calls
from resume_api.importer.template_direct import TemplateDirect
from resume_api.inference_admission import InferenceAdmission
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for


def never_dispatched(attempt):
    return CleanupProof(attempt.id, digest(attempt.owner), digest({'unlaunched': attempt.id}),
        'controlled-never-dispatched', True)


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('phase', ['reserved', 'dispatch_started'])
@pytest.mark.parametrize('verified', [False, True])
async def test_elapsed_expiry_during_durable_launch_never_enters_transport(tmp_path, entry, phase, verified):
    fixture = RuntimeFixture(tmp_path)
    elapsed, observed = [0.0], []
    service = await service_for(fixture) if entry == 'queued' else None
    admission = service.admission if service else InferenceAdmission()
    pipeline = service.templates.pipeline if service else fixture.pipeline
    direct = TemplateDirect(pipeline, admission)
    pipeline.elapsed = lambda: elapsed[0]
    pipeline.persistence.elapsed = pipeline.elapsed
    # Launch steps save to the sidecar (S7e); both save paths are observed.
    def observing(original):
        def update(*args, **kwargs):
            workspace = original(*args, **kwargs)
            operation = (workspace.project or workspace.pre_draft).template_operations[0]
            if not observed and operation.attempts and operation.attempts[-1].state == phase:
                observed.append(phase)
                elapsed[0] = 301.0
            return workspace
        return update
    pipeline.update, pipeline.update_operation = observing(pipeline.update), observing(pipeline.update_operation)
    if verified:
        fixture.transport.reconcile = never_dispatched
    try:
        if service:
            if verified:
                await queued(service, fixture, fixture.command)
            else:
                job, _created = await service.templates.submit(fixture.project, fixture.command)
                async def stopped():
                    while True:
                        control = service.supervisor.controls.get(job.id)
                        if control is not None and control.task is not None and control.task.done():
                            return
                        await asyncio.sleep(0.02)
                await asyncio.wait_for(stopped(), 30)
        else:
            await direct.run(fixture.project, fixture.command)
        current = fixture.current()
        result = (current.project or current.pre_draft).template_operations[0]
        assert observed == [phase] and fixture.transport.calls == []
        assert result.inference_closed and len(result.attempts) == 1
        attempt = result.attempts[0]
        assert attempt.error_code == 'IMPORT_PROCESSING_EXHAUSTED' and attempt.raw_return is None
        if verified:
            assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
            assert attempt.state == 'released' and attempt.cleanup.state == 'verified'
            assert spent_calls(result) == 0 and not admission.locked()
        else:
            assert result.state == 'fenced' and current.project is None
            assert attempt.state == 'outcome_unknown' and attempt.cleanup.state == 'unknown'
            assert spent_calls(result) == 1 and admission.locked()
            fixture.transport.reconcile = never_dispatched
            recovered = await pipeline.recover(fixture.project, result.id)
            assert recovered.attempts[0].state == 'released' and spent_calls(recovered) == 0
            if service:
                await service.supervisor.verify_cleanup(job.id)
            else:
                direct.permits.pop(fixture.project)[0].release()
            assert not admission.locked()
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_transport_timeout_is_refreshed_after_durable_dispatch(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path)
    elapsed, timeouts = [0.0], []
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    pipeline.elapsed = lambda: elapsed[0]
    pipeline.persistence.elapsed = pipeline.elapsed
    original_generate = fixture.transport.generate
    # Launch steps save to the sidecar (S7e); both save paths are observed.
    def observing(original):
        def update(*args, **kwargs):
            workspace = original(*args, **kwargs)
            operation = (workspace.project or workspace.pre_draft).template_operations[0]
            if operation.attempts and operation.attempts[-1].state == 'dispatch_started':
                elapsed[0] = 299.0
            return workspace
        return update
    def generate(request, cancel):
        timeouts.append(request.policy.timeout_seconds)
        return original_generate(request, cancel)
    pipeline.update, pipeline.update_operation = observing(pipeline.update), observing(pipeline.update_operation)
    fixture.transport.generate = generate
    try:
        if service:
            await queued(service, fixture, fixture.command)
        else:
            await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        assert timeouts == [1.0, 1.0] and fixture.current().project is not None
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
