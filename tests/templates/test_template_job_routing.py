"""The existing queue selects template processing by protocol with no worker tools."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
import httpx
from fastapi import FastAPI

from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_limits import import_seconds
from packages.resume_core.background_supervisor import JobControl
from packages.resume_core.models.background import JobSubmissionV1, JobSnapshotV1
from packages.resume_core.template_import import processing_protocol, spent_calls
from tests.templates.template_runtime_fixtures import RuntimeFixture
from resume_api.inference_admission import InferenceAdmission
from resume_api.jobs.service import JobService


async def service_for(fixture):
    async def drain(**_kwargs):
        pass
    projects = SimpleNamespace(storage=fixture.canonical, temp_root=fixture.root / 'workers', provider_factory=lambda: None,
        agent_recovery_fences=set(), catalog_recovery_fences=set(), state_lock=threading.RLock(),
        drain_catalog_actions=drain, listing=lambda: {'entries': [{'projectId': fixture.project, 'title': 'Synthetic'}]})
    service = JobService(projects, None, lambda: SimpleNamespace(ready=False), enabled=True,
        admission=InferenceAdmission(), clock=ControlledDeadlines(),
        template_factory=lambda owner: fixture.fresh_pipeline(owner.publisher))
    service.store.clock = service.artifacts.clock = lambda: fixture.now
    await service.start()
    return service


@pytest.mark.asyncio
async def test_queued_cancellation_stays_cancelled_after_recovery(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture)
    service.supervisor.pause('AUTH_REQUIRED')
    try:
        job, _ = await service.templates.submit(fixture.project, fixture.command)
        cancelled = await service.templates.cancel(fixture.project, job.id)
        assert cancelled.execution == 'cancelled' and not cancelled.attempts
        await service.templates.recover()
        result = service.store.read(fixture.project, job.id)
        assert result.template_outcome.state == 'cancelled'
        assert result.publication == 'cancelled' and result.publication_error is None
    finally:
        await service.shutdown()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_queued_preprovider_refusal_releases_admission_and_survives_recovery(tmp_path):
    from resume_api.importer.template_transport import JOB_PERMIT, ProviderTemplateTransport
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture)
    admitted = []
    def disconnected():
        admitted.append((service.admission.locked(), JOB_PERMIT.get() is not None))
        return None
    service.templates.pipeline.transport = ProviderTemplateTransport(disconnected, tmp_path / 'transport')
    try:
        job, _ = await service.templates.submit(fixture.project, fixture.command)
        async def finish():
            while True:
                current = service.store.read(fixture.project, job.id)
                if current.template_outcome is not None:
                    return current
                await asyncio.sleep(0.02)
        current = await asyncio.wait_for(finish(), 60)
        assert current.publication == 'saved' and current.template_outcome.state == 'saved'
        operation = fixture.current().project.template_operations[0]
        assert admitted and all(held and owned for held, owned in admitted)
        assert operation.attempts and spent_calls(operation) == 0
        assert all(attempt.state == 'released' and attempt.cleanup.state == 'verified' for attempt in operation.attempts)
        assert fixture.transport.calls == [] and service.supervisor.fenced is None
        assert service.admission.acquire(blocking=False), 'the next operation can take the released slot'
        service.admission.release()
        await service.templates.recover()
        recovered = service.store.read(fixture.project, job.id)
        assert recovered.publication == 'saved' and recovered.template_outcome.state == 'saved'
    finally:
        await service.shutdown()
        service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_queue_and_direct_share_attempt_review_and_publication_owners(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture)
    claimed, finalizing = [], []
    original = fixture.transport.generate
    def generate(request, cancel):
        claimed.append(service.admission.locked())
        return original(request, cancel)
    fixture.transport.generate = generate
    def observe(name, project):
        if name != 'before_commit_claim':
            return
        intents = service.store.load(project).manual_intents
        if intents and intents[-1].template_finalization is not None:
            finalizing.append(service.admission.locked())
    service.publisher.observer = observe
    try:
        from resume_api.jobs.routes import mount_jobs
        app = FastAPI()
        mount_jobs(app, service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://foldcv.test') as client:
            response = await client.post('/v1/rich/projects/' + fixture.project + '/jobs/fixed',
                json=fixture.command.model_dump(mode='json', by_alias=True))
        assert response.status_code == 202
        job = JobSnapshotV1.model_validate(response.json())
        assert job.submission.protocol == 'template_import_v1' and job.submission.tools == []
        # The import time from Settings (D096), not the ordinary job deadline.
        assert JobControl(service.supervisor, job).active_seconds == import_seconds() == 3600
        async def finish():
            while True:
                current = service.store.read(fixture.project, job.id)
                if current.template_outcome is not None:
                    return current
                await asyncio.sleep(0.02)
        current = await asyncio.wait_for(finish(), 60)
        assert current.publication == 'saved' and current.receipt is None
        assert current.template_outcome.state == 'saved' and claimed == [True, True] and finalizing == [False]
        operation = fixture.current().project.template_operations[0]
        assert spent_calls(operation) == 2 and len(current.attempts) == 1
        assert service.fixed.generation(fixture.project).status == 'completed'
        assert service.index().jobs[0].saved
        repeated, created = await service.templates.submit(fixture.project, fixture.command)
        assert not created and repeated == current and len(fixture.transport.calls) == 2
    finally:
        await service.shutdown()
        service.supervisor.clock.verify()


def test_protocol_cannot_be_inferred_from_empty_tools_or_forge_legacy_input():
    base = {'schemaVersion': 1, 'identity': {'projectId': 'p', 'lineage': 'l', 'requestEpoch': 1, 'requestId': 'r'},
        'payloadSha256': '0' * 64, 'kind': 'processing', 'schedulingClass': 'background',
        'input': {'kind': 'processing', 'id': 'input', 'sha256': '0' * 64},
        'models': [{'stage': stage, 'model': 'controlled', 'configSha256': '0' * 64} for stage in ['assessment', 'extraction']],
        'accountGeneration': 1, 'tools': [], 'allowEdits': True, 'allowWeb': False, 'scope': {'kind': 'resume'},
        'guards': {'schemaVersion': 1, 'reads': [], 'writes': []}, 'submittedAt': '2026-10-21T00:00:00+00:00'}
    assert processing_protocol(JobSubmissionV1.model_validate(base)) == 'fixed_v1'
    with pytest.raises(ValueError):
        JobSubmissionV1.model_validate({**base, 'protocol': 'template_import_v1'})
    with pytest.raises(ValueError):
        JobSubmissionV1.model_validate({**base, 'input': {**base['input'], 'kind': 'template_import'}})
