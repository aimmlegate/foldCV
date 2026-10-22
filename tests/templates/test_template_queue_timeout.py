"""A stalled canonical writer cannot block the queue event loop after timeout."""

import asyncio
import threading

import pytest

from packages.resume_core.background_store import BackgroundFailure
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_job_routing import service_for


@pytest.mark.asyncio
@pytest.mark.parametrize('phase,saved', [('before_commit_claim', False), ('commit_claimed', True)])
async def test_queue_timeout_fences_then_reconciles_without_blocking_event_loop(tmp_path, phase, saved):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture)
    persistence = service.templates.pipeline.persistence
    reached, release, finalizing = threading.Event(), threading.Event(), []
    def pause(name, project):
        if name == 'before_commit_claim':
            intents = service.store.load(project).manual_intents
            finalizing[:] = [True] if intents and intents[-1].template_finalization is not None else []
        if finalizing and name == phase:
            reached.set()
            assert release.wait(10)
    service.publisher.observer = pause
    async def expire_at_stall(tasks, *, timeout):
        waited = 0
        while waited < timeout:
            done, waiting = await asyncio.wait(tasks, timeout=0.01)
            if done or reached.is_set():
                return done, waiting
            waited += 0.01
        return set(), tasks
    persistence.wait = expire_at_stall
    try:
        job, _created = await service.templates.submit(fixture.project, fixture.command)
        async def pending():
            while fixture.project not in service.templates.pending_jobs:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(pending(), 30)
        assert reached.is_set() and service.supervisor.fenced == 'OUTCOME_UNKNOWN'
        assert not service.admission.locked() and len(fixture.transport.calls) == 2
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            service.project(fixture.project)
        with pytest.raises(BackgroundFailure, match='OUTCOME_UNKNOWN'):
            service.index()
        assert service.fixed.generation(fixture.project).error_code == 'OUTCOME_UNKNOWN'
        await asyncio.wait_for(asyncio.sleep(0.01), 1)
    finally:
        release.set()
        await asyncio.gather(*tuple(service.templates.reconciliations.values()), return_exceptions=True)
        await service.shutdown()
        service.supervisor.clock.verify()
    current = service.store.read(fixture.project, job.id)
    assert current.template_outcome.state == ('saved' if saved else 'failed_before_replacement')
    assert bool(fixture.current().project) == saved
    assert not persistence.pending and not service.templates.pending_jobs and service.supervisor.fenced is None
