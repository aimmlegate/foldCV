"""A restarted import continues the saved operation and publishes through the same repository."""

import pytest

from packages.resume_core.project_repository import ProjectRepository
from packages.resume_core.template_import import admit_operation
from packages.resume_core.templates.operations import derive_task
from resume_api.projects.fold import register_import_fold, sidecar_store
from resume_api.projects.pipeline import RepositoryPipeline
from tests.projects.support import source_blobs
from tests.templates.employment_fixtures import employment_package, employment_source
from tests.templates.pipeline_fixtures import resume_command
from tests.templates.test_template_employment import EmploymentFixture, scripted_employment


def coordinator(fixture, repository):
    return RepositoryPipeline(None, fixture.transport, repository=repository, originals=fixture.originals,
        authority=fixture.pipeline.authority, assemble=fixture.assemble, derive=derive_task, wall=lambda: fixture.now)


@pytest.mark.asyncio
async def test_resume_executes_the_unfinished_tasks_from_the_sidecar(tmp_path, caplog):
    source, raw = employment_source('F01')
    fixture = EmploymentFixture(tmp_path / 'fixture', captured=employment_package(), src=source, original_bytes=raw,
        scripted=scripted_employment(source), cap=4, fallback=False)
    repository = ProjectRepository(tmp_path / 'repository')
    repository.start()
    register_import_fold(repository)
    repository.create(fixture.before, blobs=source_blobs({source.id: raw}))
    pipeline = coordinator(fixture, repository)
    operation = await pipeline.start(fixture.project, fixture.command)
    pipeline.update_operation(fixture.project, operation.id,
        lambda value, _data, _workspace: admit_operation(value, fixture.now))
    directory = repository.open(fixture.project).directory
    assert sidecar_store(directory).read(fixture.project, operation.id) is not None
    repository.close(fixture.project)

    restarted = ProjectRepository(tmp_path / 'repository')
    restarted.start()
    register_import_fold(restarted)
    recovered = coordinator(fixture, restarted)
    result = await recovered.run(fixture.project, resume_command(operation), admitted=fixture.admitted)
    assert result.state == 'published' and result.publication.state == 'saved'
    saved = recovered.read(fixture.project)
    assert saved.project is not None and saved.pre_draft is None
    assert any(record.kind == 'employment' for record in saved.project.facts.records)
    assert len(fixture.transport.calls) > 0
    assert sidecar_store(directory).read(fixture.project, operation.id) is None
    assert 'journal gap' not in caplog.text


@pytest.mark.asyncio
async def test_resume_after_publication_keeps_later_manual_text(tmp_path, monkeypatch):
    from packages.resume_core.models.template_document import PresentedText
    source, raw = employment_source('F01')
    fixture = EmploymentFixture(tmp_path / 'fixture', captured=employment_package(), src=source, original_bytes=raw,
        scripted=scripted_employment(source), cap=4, fallback=False)
    repository = ProjectRepository(tmp_path / 'repository')
    repository.start()
    register_import_fold(repository)
    repository.create(fixture.before, blobs=source_blobs({source.id: raw}))
    pipeline = coordinator(fixture, repository)
    original = pipeline.record_publication
    def crash(*_args):
        raise RuntimeError('crash after publication')
    monkeypatch.setattr(pipeline, 'record_publication', crash)
    with pytest.raises(RuntimeError, match='crash after publication'):
        await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    committed = repository.read(fixture.project)
    assert committed.project is not None

    def manual(workspace):
        updated = workspace.model_copy(deep=True)
        block = next(block for block in updated.project.document.blocks() if block.type == 'paragraph' and block.content)
        block.content.append(PresentedText(type='text', text=' Human text', styles={}))
        block.revision += 1
        return updated

    repository.mutate(fixture.project, base_revision=committed.project_revision, client_mutation_id='human-edit',
        request_sha256='a' * 64, action_id='human-edit', kind='edit', build=manual)
    before = repository.read(fixture.project).project.document.model_dump(mode='json', by_alias=True)
    monkeypatch.setattr(pipeline, 'record_publication', original)
    repository.close(fixture.project)
    restarted = ProjectRepository(tmp_path / 'repository')
    restarted.start()
    register_import_fold(restarted)
    recovered = coordinator(fixture, restarted)
    saved = recovered.read(fixture.project)
    operation = saved.project.template_operations[0]
    result = await recovered.run(fixture.project, resume_command(operation), admitted=fixture.admitted)
    assert result.publication.state == 'saved'
    assert recovered.read(fixture.project).project.document.model_dump(mode='json', by_alias=True) == before
    assert restarted.open(fixture.project).journal.state()['undo']['actionId'] == 'human-edit'


@pytest.mark.asyncio
async def test_a_revision_change_during_assembly_refuses_publication(tmp_path):
    from packages.resume_core.project_repository import RepositoryFailure
    source, raw = employment_source('F01')
    fixture = EmploymentFixture(tmp_path / 'fixture', captured=employment_package(), src=source, original_bytes=raw,
        scripted=scripted_employment(source), cap=4, fallback=False)
    repository = ProjectRepository(tmp_path / 'repository')
    repository.start()
    register_import_fold(repository)
    repository.create(fixture.before, blobs=source_blobs({source.id: raw}))
    pipeline = coordinator(fixture, repository)
    assemble = pipeline.assemble

    def concurrent_write(workspace, operation):
        authored = assemble(workspace, operation)
        updated = workspace.model_copy(deep=True)
        updated.formatting_as_of.day = 20
        repository.replace(fixture.project, base_revision=workspace.project_revision, workspace=updated,
            reason='formatting-date')
        return authored

    pipeline.assemble = concurrent_write
    with pytest.raises(RepositoryFailure) as refused:
        await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert refused.value.code == 'REVISION_CONFLICT'
    saved = repository.read(fixture.project)
    assert saved.project is None and saved.formatting_as_of.day == 20
