"""S7e: processing steps are saved to one sidecar; the project is saved whole at start, admission and publication."""

import json

import pytest

from packages.resume_core.project_repository import RepositoryFailure
from packages.resume_core.template_import import spent_calls
from tests.templates.template_runtime_fixtures import RuntimeFixture


def counted(fixture):
    """Count whole-project commits through the repository."""
    saves = []
    original = fixture.repository.replace
    def replace(*args, **kwargs):
        saves.append(kwargs.get('reason'))
        return original(*args, **kwargs)
    fixture.repository.replace = replace
    return saves


@pytest.mark.asyncio
async def test_an_import_saves_the_project_at_start_admission_and_publication_and_leaves_no_sidecar(tmp_path):
    # P15: task input, reservation, dispatch, return, parse, review, admission of facts and finish go to the
    # sidecar; the publication saves fold it in.
    fixture = RuntimeFixture(tmp_path)
    saves = counted(fixture)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and len(fixture.transport.calls) == spent_calls(result) == 2
    # Start, admission, finalization, publication and its record: 5 saves, where the same import saved 16 times
    # before (two time observations, two reservations, two dispatches, two returns, a task input, parse, accept
    # and finish).
    assert saves == ['import', 'import', 'import', 'publication', 'import'], saves
    assert not fixture.sidecar.path(fixture.project, result.id).exists()
    assert fixture.saved() == fixture.current()


@pytest.mark.asyncio
async def test_a_sidecar_on_the_current_revision_is_overlaid_and_a_folded_one_is_ignored(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    operation = await fixture.pipeline.start(fixture.project, fixture.command)
    saved = fixture.saved()
    changed = operation.model_copy(update={'last_observed_at': fixture.now})
    fixture.sidecar.write(fixture.project, saved.project_revision, changed, saved.pre_draft.facts)
    assert fixture.current().pre_draft.template_operations[0] == changed
    # One revision on, a sidecar whose attempts the project holds at least as far is already folded.
    fixture.sidecar.write(fixture.project, saved.project_revision - 1, changed, saved.pre_draft.facts)
    assert fixture.current().pre_draft.template_operations[0] == saved.pre_draft.template_operations[0]


@pytest.mark.asyncio
async def test_a_save_that_lost_sidecar_steps_or_a_damaged_sidecar_fences_the_reader(tmp_path):
    # P17: an older sidecar holding an attempt the project lacks means a save dropped import steps.
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.fail_at = 'dispatch'
    with pytest.raises(SystemExit):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    path = fixture.sidecar.path(fixture.project, fixture.current().pre_draft.template_operations[0].id)
    stored = json.loads(path.read_bytes())
    assert stored['operation']['attempts'][0]['state'] == 'dispatch_started'
    stored['projectRevision'] -= 1
    path.write_text(json.dumps(stored))
    with pytest.raises(RepositoryFailure, match='OUTCOME_UNKNOWN'):
        fixture.pipeline.read(fixture.project)
    path.write_text('{"schemaVersion": 1, "projectRevision": 1}')
    with pytest.raises(RepositoryFailure, match='JOB_STORE_CORRUPT'):
        fixture.pipeline.read(fixture.project)


@pytest.mark.asyncio
async def test_a_crash_between_sidecar_steps_recovers_from_them_without_a_resend(tmp_path):
    # P16: the dispatch exists only in the sidecar; a fresh pipeline sees it and never sends the request again.
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.fail_at = 'dispatch'
    with pytest.raises(SystemExit):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert spent_calls(fixture.saved().pre_draft.template_operations[0]) == 0
    operation = fixture.current().pre_draft.template_operations[0]
    assert spent_calls(operation) == 1 and operation.attempts[0].state == 'dispatch_started'
    recovered = await fixture.restart().recover(fixture.project, operation.id)
    assert recovered.state == 'fenced' and len(fixture.transport.calls) == 1
    assert spent_calls(fixture.saved().pre_draft.template_operations[0]) == 1
