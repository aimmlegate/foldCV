"""One undo stack over the authored document, facts, issues, coverage and sync rows (G3)."""

import json

import pytest

from packages.resume_core import project_journal
from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, edit, history, repository, text_of


# Counters outside the undoable keys (project, facts, document, regions) only move forward; the timestamp and replay
# window are per commit.
FORWARD = {'projectRevision', 'documentRevision', 'updatedAt', 'mutationReplay'}


def comparable(workspace):
    data = workspace.model_dump(mode='json', by_alias=True)
    for key in FORWARD:
        data.pop(key)
    data['project'].pop('revision')
    data['project']['facts'].pop('revision')
    data['project']['document'].pop('revision')
    for region in data['project']['document']['regions']:
        region.pop('revision')
    return data


def test_typing_coalesces_by_action_and_one_undo_returns_the_exact_earlier_values(tmp_path):
    repo = repository(tmp_path)
    original = repo.read(PROJECT)
    edit(repo, 'S', identifier='edit-1', action='typing')
    edit(repo, 'Sh', identifier='edit-2', action='typing')
    edit(repo, 'Shx', identifier='edit-3', action='typing')
    assert len(repo.open(PROJECT).journal.undo) == 1
    history(repo, 'undo', identifier='undo-1', expected='typing')
    assert comparable(repo.read(PROJECT)) == comparable(original)
    assert repo.read(PROJECT).project_revision == 5


def test_undo_then_redo_reproduce_the_bytes_except_forward_counters(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'Edited', identifier='edit-1', action='one', index=1)
    after = repo.read(PROJECT)
    history(repo, 'undo', identifier='undo-1')
    history(repo, 'redo', identifier='redo-1')
    assert comparable(repo.read(PROJECT)) == comparable(after)
    assert repo.open(PROJECT).journal.state() == {'undo': {'actionId': 'one', 'kind': 'edit'}, 'redo': None}


def test_a_new_edit_clears_redo_and_a_barrier_clears_both(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    edit(repo, 'Two', identifier='edit-2', action='two', index=1)
    history(repo, 'undo', identifier='undo-1')
    assert repo.open(PROJECT).journal.state()['redo']['actionId'] == 'two'
    edit(repo, 'Three', identifier='edit-3', action='three', index=1)
    assert repo.open(PROJECT).journal.state() == {'undo': {'actionId': 'three', 'kind': 'edit'}, 'redo': None}
    changed = repo.read(PROJECT).model_copy(deep=True)
    changed.project.document.regions[2].blocks[0].content[0].text = 'Imported'
    repo.replace(PROJECT, base_revision=changed.project_revision, workspace=changed, reason='import')
    assert repo.open(PROJECT).journal.state() == {'undo': None, 'redo': None}
    reopened = ProjectRepository(tmp_path / 'data')
    assert reopened.open(PROJECT).journal.state() == {'undo': None, 'redo': None}


def test_a_net_empty_action_leaves_no_undo_step(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'First', identifier='edit-1', action='first')
    edit(repo, 'Typed', identifier='edit-2', action='typing')
    edit(repo, 'First', identifier='edit-3', action='typing')
    assert [action.action_id for action in repo.open(PROJECT).journal.undo] == ['first']


def test_history_refuses_a_stale_expected_action_and_keeps_the_stack(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    with pytest.raises(RepositoryFailure) as refused:
        history(repo, 'undo', identifier='undo-1', expected='other')
    assert refused.value.code == 'HISTORY_STALE' and refused.value.details['history']['undo']['actionId'] == 'one'
    assert text_of(repo.read(PROJECT)) == 'One'


def test_bounds_drop_the_oldest_actions_and_load_compacts_a_long_file(tmp_path, monkeypatch):
    monkeypatch.setattr(project_journal, 'ACTIONS', 3)
    repo = repository(tmp_path)
    for index in range(8):
        edit(repo, 'Text %d' % index, identifier='edit-%d' % index, action='action-%d' % index)
    session = repo.open(PROJECT)
    assert [action.action_id for action in session.journal.undo] == ['action-5', 'action-6', 'action-7']
    path = session.directory / 'history.jsonl'
    assert len(path.read_bytes().splitlines()) == 8
    repo.close(PROJECT)
    lines = path.read_bytes().splitlines()
    assert [json.loads(line)['actionId'] for line in lines] == ['action-5', 'action-6', 'action-7']
    reopened = ProjectRepository(tmp_path / 'data')
    assert [action.action_id for action in reopened.open(PROJECT).journal.undo] == ['action-5', 'action-6', 'action-7']


def test_the_byte_bound_keeps_only_what_fits(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    edit(repo, 'x' * 400, identifier='edit-1', action='one')
    monkeypatch.setattr(project_journal, 'BYTES', 2 * repo.open(PROJECT).journal.undo[0].bytes + 10)
    edit(repo, 'y' * 400, identifier='edit-2', action='two', index=1)
    edit(repo, 'z' * 400, identifier='edit-3', action='three')
    assert [action.action_id for action in repo.open(PROJECT).journal.undo] == ['two', 'three']


def test_a_compacted_redo_list_survives_a_reopen(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    edit(repo, 'Two', identifier='edit-2', action='two', index=1)
    history(repo, 'undo', identifier='undo-1')
    history(repo, 'undo', identifier='undo-2')
    repo.close(PROJECT)
    reopened = ProjectRepository(tmp_path / 'data')
    assert [action.action_id for action in reopened.open(PROJECT).journal.redo] == ['two', 'one']
    history(reopened, 'redo', identifier='redo-1', expected='one')
    assert text_of(reopened.read(PROJECT)) == 'One'


def test_a_corrupt_tail_is_truncated_and_the_earlier_lines_load(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    path = repo.open(PROJECT).directory / 'history.jsonl'
    good = path.read_bytes()
    with path.open('ab') as stream:
        stream.write(b'{"kind": "edit", "broken"\n{"kind":"barrier"}\n')
    reopened = ProjectRepository(tmp_path / 'data')
    assert reopened.open(PROJECT).journal.state()['undo']['actionId'] == 'one'
    assert path.read_bytes() == good


def test_undo_restores_fact_order_issues_and_sync_rows_exactly(tmp_path):
    from tests.templates.golden.corpus import corpus as stored_corpus, loaded
    from packages.resume_core.project_journal import apply, changes, snapshot
    from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
    from packages.resume_core.template_preparation import prepare_edit
    from tests.templates.test_template_preparation import response
    corpus = stored_corpus()
    for name in ['delete_entity', 'resolve_template_sync', 'replace_text']:
        entry = next(value for value in corpus['entries'] if value['name'] == name)
        before, _sources = loaded(corpus['fixtures'][entry['fixture']])
        request = TemplateEditPreparationV1.model_validate(entry['preparation'])
        request.capture.session_id = 'session'
        after = prepare_edit(response(before), request).preview.workspace
        old, new = changes(snapshot(before), snapshot(after))
        assert comparable(apply(after, old)) == comparable(before), name
        assert comparable(apply(apply(after, old), new)) == comparable(after), name


def test_a_payload_that_no_longer_validates_is_stale_history(tmp_path, monkeypatch):
    from packages.resume_core import project_repository
    from packages.resume_core.models.template_workspace import WorkspaceV7
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    monkeypatch.setattr(project_repository, 'apply_payloads', lambda *_args: WorkspaceV7.model_validate({}))
    with pytest.raises(RepositoryFailure) as refused:
        history(repo, 'undo', identifier='undo-1')
    assert refused.value.code == 'HISTORY_STALE' and refused.value.details['history'] == {'undo': None, 'redo': None}
    assert text_of(repo.read(PROJECT)) == 'One'


def test_a_commit_without_undoable_changes_keeps_the_history_after_a_restart(tmp_path):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    titled = repo.read(PROJECT).model_copy(deep=True)
    titled.title = 'Renamed'
    repo.replace(PROJECT, base_revision=2, workspace=titled, reason='rename')
    # No close: the journal is read as a crash would leave it, and its last line still names revision 3.
    reopened = ProjectRepository(tmp_path / 'data')
    assert reopened.open(PROJECT).journal.state()['undo']['actionId'] == 'one'


def test_a_long_session_compacts_its_journal_without_a_close(tmp_path, monkeypatch):
    monkeypatch.setattr(project_journal, 'ACTIONS', 2)
    repo = repository(tmp_path)
    for index in range(12):
        edit(repo, 'Text %d' % index, identifier='edit-%d' % index, action='action-%d' % index)
    path = repo.open(PROJECT).directory / 'history.jsonl'
    assert len(path.read_bytes().splitlines()) <= 4 * 2
    reopened = ProjectRepository(tmp_path / 'data')
    assert [action.action_id for action in reopened.open(PROJECT).journal.undo] == ['action-10', 'action-11']
