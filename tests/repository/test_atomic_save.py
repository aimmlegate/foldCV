"""A commit is durable before it is acknowledged; a crash at any point leaves the old or the new file (G1, G2)."""

import json
import logging
import os

import pytest

from packages.resume_core import project_journal, storage
from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, edit, repository, text_of


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
    assert journal_path.read_bytes().endswith(b'\n') and session.journal.state()['undo']['actionId'] == 'one'
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
