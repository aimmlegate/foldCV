"""Publication of an import rechecks the import authority after the last block (SR00 flag 2)."""

import pytest

from packages.resume_core.project_repository import RepositoryFailure
from tests.templates.template_runtime_fixtures import RuntimeFixture, import_task


@pytest.mark.asyncio
async def test_an_authority_lost_after_the_last_block_fails_the_task_and_publishes_nothing(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    run_tasks = fixture.pipeline.run_tasks
    async def then_revoked(*args, **kwargs):
        await run_tasks(*args, **kwargs)
        fixture.external_authority = False
    fixture.pipeline.run_tasks = then_revoked
    status = await import_task(fixture)
    assert (status['state'], status['error']) == ('failed', 'IMPORT_CAPTURE_STALE')
    current = fixture.current()
    assert current.project is None and len(fixture.transport.calls) == 2
    operation = current.pre_draft.template_operations[0]
    assert operation.finalization is None and operation.publication.state != 'saved'
    # The block results stay; a resume with the authority back publishes them without a model call.
    fixture.pipeline.run_tasks, fixture.external_authority = run_tasks, True
    resumed = await import_task(fixture, kind='resume', operation_id=operation.id)
    assert resumed['state'] == 'succeeded' and len(fixture.transport.calls) == 2
    assert fixture.current().project.template_operations[0].state == 'published'


@pytest.mark.asyncio
async def test_a_failed_publication_commit_is_published_by_a_later_resume(tmp_path):
    # The saved finalization named the first authorization, so every resume failed with DEPENDENCY_CHANGED and no new
    # import could start beside the finalizing one.
    fixture = RuntimeFixture(tmp_path)
    replace = fixture.repository.replace
    def failing(project_id, **options):
        if options['reason'] == 'publication':
            raise RepositoryFailure('PROJECT_SAVE_FAILED')
        return replace(project_id, **options)
    fixture.repository.replace = failing
    status = await import_task(fixture)
    assert (status['state'], status['error']) == ('failed', 'PROJECT_SAVE_FAILED')
    operation = fixture.current().pre_draft.template_operations[0]
    assert operation.state == 'finalizing' and operation.finalization is not None
    del fixture.repository.replace
    resumed = await import_task(fixture, kind='resume', operation_id=operation.id)
    assert (resumed['state'], resumed['error']) == ('succeeded', None)
    published = fixture.current().project.template_operations[0]
    assert published.state == 'published' and len(fixture.transport.calls) == 2
    # The resume renewed the saved candidate for its own authorization; what it publishes is unchanged.
    assert published.finalization_history == [operation.finalization]
    assert published.finalization.candidate_hash == operation.finalization.candidate_hash
    assert published.finalization.authorization_id == published.authorizations[-1].id != operation.finalization.authorization_id


@pytest.mark.asyncio
async def test_a_resume_publishes_the_current_content_when_it_changed_after_the_failed_publication(tmp_path):
    # A commit between the attempts can change what is assembled (assembly reads the formatting date), so the renewed
    # candidate has another content hash; before, every resume failed with DEPENDENCY_CHANGED and the finalizing
    # import blocked new imports for good.
    fixture = RuntimeFixture(tmp_path)
    replace = fixture.repository.replace
    def failing(project_id, **options):
        if options['reason'] == 'publication':
            raise RepositoryFailure('PROJECT_SAVE_FAILED')
        return replace(project_id, **options)
    fixture.repository.replace = failing
    status = await import_task(fixture)
    assert (status['state'], status['error']) == ('failed', 'PROJECT_SAVE_FAILED')
    del fixture.repository.replace
    assemble = fixture.pipeline.assemble
    def changed(before, operation):
        authored = assemble(before, operation)
        span = next(span for block in authored.project.document.blocks() for span in block.content if span.text)
        span.text += ' (updated)'
        return authored
    fixture.pipeline.assemble = changed
    operation = fixture.current().pre_draft.template_operations[0]
    resumed = await import_task(fixture, kind='resume', operation_id=operation.id)
    assert (resumed['state'], resumed['error']) == ('succeeded', None)
    current = fixture.current()
    published = current.project.template_operations[0]
    assert published.state == 'published' and published.finalization_history == [operation.finalization]
    assert published.finalization.candidate_hash != operation.finalization.candidate_hash
    assert any(span.text.endswith(' (updated)') for block in current.project.document.blocks() for span in block.content)
