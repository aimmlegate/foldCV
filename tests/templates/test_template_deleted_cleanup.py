"""Deletion retains owned cleanup across loss of the original runtime."""

import asyncio

import pytest

from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.template_import import CleanupProof, TemplateImportFailure, digest
from resume_api.importer.template_direct import TemplateDirect
from resume_api.inference_admission import InferenceAdmission
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_job_routing import service_for


def prove(attempt):
    return CleanupProof(attempt.id, digest(attempt.owner), digest('deleted-owned-terminal'), 'controlled-owned-terminal')


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_deleted_return_releases_only_after_durable_owner_proof(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path)
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    jobs = pipeline.publisher.jobs
    admission = service.admission if service else InferenceAdmission()
    def deleted(_request, _value):
        fixture.canonical.tombstone(fixture.project)
        jobs.mark_deleted(fixture.project)
        return raw_proposal(fixture.source)
    fixture.transport.scripted = deleted
    fixture.transport.reconcile = prove
    try:
        if service:
            job, _created = await service.templates.submit(fixture.project, fixture.command)
            async def stopped():
                while job.id not in service.supervisor.controls:
                    await asyncio.sleep(0.01)
                await service.supervisor.controls[job.id].task
            await asyncio.wait_for(stopped(), 30)
            await service.stop_project(fixture.project)
        else:
            direct = TemplateDirect(pipeline, admission)
            with pytest.raises(ProjectStoreFailure, match='PROJECT_DELETED'):
                await direct.run(fixture.project, fixture.command)
        assert not admission.locked() and len(fixture.transport.calls) == 1
        with jobs.guard(fixture.project, deleted=True) as directory:
            state = jobs._read(fixture.project, directory)
            proof = state.template_authorizations[-1].deleted_cleanup
            assert len(proof.owners) == len(proof.records) == 1
            assert proof.records[0].owner_hash == digest(next(iter(proof.owners.values())))
            assert all(attempt.cleanup_verified for value in state.jobs for attempt in value.attempts)
        # After proof persistence, neither a prior control nor the canonical file is needed.
        assert fixture.canonical.cleanup_deleted(fixture.project).cleanup_status == 'complete'
        restarted = fixture.fresh_pipeline(pipeline.publisher)
        fixture.transport.reconcile = lambda _attempt: pytest.fail('persisted proof must replay')
        assert restarted.cleanup_deleted(fixture.project)
        with pytest.raises(ProjectStoreFailure, match='PROJECT_DELETED'):
            restarted.read(fixture.project)
        jobs.cleanup_deleted(fixture.project)
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_restart_unknown_deleted_owner_blocks_physical_cleanup(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.fail_at = 'dispatch'
    with pytest.raises(SystemExit):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    fixture.canonical.tombstone(fixture.project)
    fixture.jobs.mark_deleted(fixture.project)
    restarted = fixture.fresh_pipeline()
    assert not restarted.cleanup_deleted(fixture.project)
    with fixture.jobs.guard(fixture.project, deleted=True) as directory:
        partial = fixture.jobs._read(fixture.project, directory).template_authorizations[-1].deleted_cleanup
        assert not partial.complete and len(partial.owners) == 1 and not partial.records
    with pytest.raises(ProjectStoreFailure, match='PROJECT_DELETE_FAILED'):
        fixture.canonical.cleanup_deleted(fixture.project)
    # A mismatched incarnation is not evidence for the retained launch owner.
    fixture.transport.reconcile = lambda attempt: CleanupProof(attempt.id, digest('other-owner'), digest('proof'), 'pid-reused')
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_PROOF_INVALID'):
        restarted.cleanup_deleted(fixture.project)
    fixture.transport.reconcile = prove
    assert restarted.cleanup_deleted(fixture.project)
    assert fixture.canonical.cleanup_deleted(fixture.project).cleanup_status == 'complete'


@pytest.mark.asyncio
async def test_direct_deleted_cleanup_retry_retains_then_releases_its_exact_permit(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    admission = InferenceAdmission()
    direct = TemplateDirect(fixture.pipeline, admission)
    def deleted(_request, _value):
        fixture.canonical.tombstone(fixture.project)
        fixture.jobs.mark_deleted(fixture.project)
        return raw_proposal(fixture.source)
    fixture.transport.scripted = deleted
    with pytest.raises(ProjectStoreFailure, match='PROJECT_DELETED'):
        await direct.run(fixture.project, fixture.command)
    assert admission.locked() and not await direct.cleanup_deleted(fixture.project)
    fixture.transport.reconcile = prove
    assert await direct.cleanup_deleted(fixture.project)
    assert not admission.locked() and not direct.permits
    assert len(fixture.transport.calls) == 1
