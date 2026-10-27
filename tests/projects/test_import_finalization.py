"""Publication of an import rechecks the import authority after the last block (SR00 flag 2)."""

import pytest

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
