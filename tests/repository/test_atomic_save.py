"""A commit is durable before it is acknowledged; a crash at any point leaves the old or the new file (G1, G2)."""

import json
import logging
import os

import pytest

from packages.resume_core import project_journal, storage
from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, edit, history, repository, text_of


class Crash(BaseException):
    """The process dies here: nothing after this point runs."""


def stored(root):
    return json.loads((root / 'data/projects' / PROJECT / 'workspace.json').read_bytes())


def window(root):
    return [row['clientMutationId'] for row in stored(root)['mutationReplay']]


def test_crash_before_rename_keeps_the_old_file_and_a_retry_applies_once(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    before = (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes()
    original = os.replace
    def crash(source, target):
        if str(target).endswith('workspace.json'):
            raise Crash()
        return original(source, target)
    monkeypatch.setattr(storage.os, 'replace', crash)
    with pytest.raises(Crash):
        edit(repo, 'Lost', identifier='edit-1')
    monkeypatch.setattr(storage.os, 'replace', original)
    assert (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes() == before
    assert not [path for path in (tmp_path / 'data/projects' / PROJECT).iterdir() if path.name.startswith('.foldcv-write-')]
    reopened = ProjectRepository(tmp_path / 'data')
    assert reopened.read(PROJECT).project_revision == 1 and 'edit-1' not in window(tmp_path)
    outcome = edit(reopened, 'Lost', identifier='edit-1')
    assert outcome.revision == 2 and not outcome.replayed and window(tmp_path) == ['edit-1']


def test_crash_after_rename_before_the_journal_keeps_the_new_file_and_names_the_id(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    edit(repo, 'Kept', identifier='edit-1', action='typing')
    monkeypatch.setattr(project_journal.ProjectJournal, 'record_edit', lambda *_args, **_kwargs: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        edit(repo, 'Kept again', identifier='edit-2', action='other')
    monkeypatch.undo()
    reopened = ProjectRepository(tmp_path / 'data')
    assert text_of(reopened.read(PROJECT)) == 'Kept again' and window(tmp_path) == ['edit-1', 'edit-2']
    retried = edit(reopened, 'Kept again', identifier='edit-2', action='other', base=2)
    assert retried.replayed and retried.revision == 3
    # The journal lacks edit-2: undoing the older action would overwrite it, so the step is refused, not applied.
    from tests.repository.support import history
    with pytest.raises(RepositoryFailure) as refused:
        history(reopened, 'undo', identifier='undo-1')
    assert refused.value.code == 'HISTORY_STALE' and text_of(reopened.read(PROJECT)) == 'Kept again'
    assert reopened.open(PROJECT).journal.state() == {'undo': None, 'redo': None}


def test_crash_during_the_journal_append_truncates_the_torn_line(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    journal_path = tmp_path / 'data/projects' / PROJECT / 'history.jsonl'
    original = os.write
    def torn(descriptor, data):
        original(descriptor, data[:len(data) // 2])
        raise Crash()
    monkeypatch.setattr(project_journal.os, 'write', torn)
    with pytest.raises(Crash):
        edit(repo, 'Two', identifier='edit-2', action='two')
    monkeypatch.undo()
    assert not journal_path.read_bytes().endswith(b'\n')
    reopened = ProjectRepository(tmp_path / 'data')
    session = reopened.open(PROJECT)
    # The journal now ends at revision 2 and the file at 3: the history restarts instead of undoing around edit-2.
    assert journal_path.read_bytes().endswith(b'\n') and session.journal.state() == {'undo': None, 'redo': None}
    assert text_of(session.workspace) == 'Two' and window(tmp_path) == ['edit-1', 'edit-2']


def test_a_failed_journal_append_is_a_logged_gap_and_the_edit_stands(tmp_path, monkeypatch, caplog):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    def refused(*_args, **_kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(project_journal.os, 'write', refused)
    with caplog.at_level(logging.WARNING):
        outcome = edit(repo, 'Two', identifier='edit-2', action='two')
    assert outcome.revision == 3 and text_of(repo.read(PROJECT)) == 'Two'
    assert any('journal gap' in record.getMessage() for record in caplog.records)
    assert repo.open(PROJECT).journal.state() == {'undo': None, 'redo': None}


def test_an_edit_needs_at_most_three_fsyncs_and_no_registry_write(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    edit(repo, 'Warm', identifier='edit-1', action='one')
    registry = (tmp_path / 'data/registry.json').read_bytes()
    calls = []
    original = os.fsync
    monkeypatch.setattr(os, 'fsync', lambda descriptor: (calls.append(descriptor), original(descriptor))[1])
    edit(repo, 'Counted', identifier='edit-2', action='two')
    assert 1 <= len(calls) <= 3
    assert (tmp_path / 'data/registry.json').read_bytes() == registry


def test_a_lost_journal_line_restarts_the_history_instead_of_undoing_around_it(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    edit(repo, 'A', identifier='edit-1', action='a', index=0)
    monkeypatch.setattr(project_journal.ProjectJournal, 'record_edit', lambda *_args, **_kwargs: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        edit(repo, 'B', identifier='edit-2', action='b', index=1)
    monkeypatch.undo()
    reopened = ProjectRepository(tmp_path / 'data')
    assert reopened.open(PROJECT).journal.state() == {'undo': None, 'redo': None}
    with pytest.raises(RepositoryFailure) as refused:
        history(reopened, 'undo', identifier='undo-1')
    workspace = reopened.read(PROJECT)
    assert refused.value.code == 'HISTORY_STALE' and (text_of(workspace, 0), text_of(workspace, 1)) == ('A', 'B')


def test_a_lost_publication_barrier_does_not_bring_back_the_older_history(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    edit(repo, 'Before', identifier='edit-1', action='one', index=1)
    published = repo.read(PROJECT).model_copy(deep=True)
    published.project.document.regions[2].blocks[0].content[0].text = 'Published'
    monkeypatch.setattr(project_journal.ProjectJournal, 'barrier', lambda *_args, **_kwargs: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        repo.replace(PROJECT, base_revision=2, workspace=published, reason='publication')
    monkeypatch.undo()
    reopened = ProjectRepository(tmp_path / 'data')
    assert reopened.open(PROJECT).journal.state() == {'undo': None, 'redo': None}


def test_a_journal_gap_is_written_down_before_the_next_line(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    edit(repo, 'One', identifier='edit-1', action='one')
    original, failed = os.write, []
    def once(descriptor, data):
        if not failed:
            failed.append(data)
            raise OSError('disk full')
        return original(descriptor, data)
    monkeypatch.setattr(project_journal.os, 'write', once)
    edit(repo, 'Two', identifier='edit-2', action='two', index=1)
    edit(repo, 'Three', identifier='edit-3', action='three')
    monkeypatch.undo()
    reopened = ProjectRepository(tmp_path / 'data')
    assert [action.action_id for action in reopened.open(PROJECT).journal.undo] == ['three']


def test_a_decode_failure_commits_nothing_and_keeps_the_history(tmp_path, monkeypatch):
    from packages.resume_core import project_repository
    monkeypatch.setenv('FOLDCV_VERIFY', '1')
    repo = repository(tmp_path)
    original = text_of(repo.read(PROJECT))
    edit(repo, 'One', identifier='edit-1', action='one')
    raw = (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes()
    monkeypatch.setattr(project_repository, 'decode_project', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('bad')))
    with pytest.raises(RepositoryFailure) as refused:
        edit(repo, 'Two', identifier='edit-2', action='two', base=2)
    monkeypatch.undo()
    assert refused.value.code == 'PROJECT_SAVE_FAILED'
    assert (tmp_path / 'data/projects' / PROJECT / 'workspace.json').read_bytes() == raw
    history(repo, 'undo', identifier='undo-1', expected='one')
    assert text_of(repo.read(PROJECT)) == original


def test_a_failing_commit_hook_keeps_the_commit_and_its_undo_step(tmp_path):
    repo = repository(tmp_path)
    original = text_of(repo.read(PROJECT))
    def broken(_session):
        raise RuntimeError('hook failed')
    repo.committed_hooks.append(broken)
    outcome = edit(repo, 'Kept', identifier='edit-1', action='one')
    repo.committed_hooks.remove(broken)
    assert outcome.revision == 2 and repo.open(PROJECT).journal.state()['undo']['actionId'] == 'one'
    history(repo, 'undo', identifier='undo-1', expected='one')
    assert text_of(repo.read(PROJECT)) == original
