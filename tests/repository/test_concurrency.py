"""One lock per project: writers serialize, background work never overwrites an edit (G4)."""

import threading

import pytest

from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, create_other, edit, repository, text_of, typing


def test_concurrent_writers_serialize_and_no_update_is_lost(tmp_path):
    repo = repository(tmp_path)
    errors, done = [], []
    def writer(index):
        for attempt in range(20):
            try:
                edit(repo, 'Writer %d' % index, identifier='edit-%d' % index, index=index % 2)
                done.append(index)
                return
            except RepositoryFailure as error:
                if error.code != 'REVISION_CONFLICT':
                    errors.append(error.code)
                    return
    threads = [threading.Thread(target=writer, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors and sorted(done) == list(range(6))
    current = repo.read(PROJECT)
    assert current.project_revision == 7 and len(current.mutation_replay) == 6


def test_a_replace_during_an_edit_conflicts_and_never_overwrites_it(tmp_path):
    repo = repository(tmp_path)
    computed = repo.read(PROJECT).model_copy(deep=True)
    computed.title = 'Export record from revision one'
    building, release = threading.Event(), threading.Event()
    def slow(workspace):
        building.set()
        release.wait(5)
        return typing('Manual edit', identifier='edit-1')(workspace)
    outcome = {}
    def run_edit():
        outcome['edit'] = repo.mutate(PROJECT, base_revision=1, client_mutation_id='edit-1', request_sha256='a' * 64,
            action_id='edit-1', kind='edit', build=slow)
    def run_replace():
        try:
            repo.replace(PROJECT, base_revision=1, workspace=computed)
        except RepositoryFailure as error:
            outcome['replace'] = error.code
    first = threading.Thread(target=run_edit)
    first.start()
    assert building.wait(5)
    second = threading.Thread(target=run_replace)
    second.start()
    release.set()
    first.join(5); second.join(5)
    assert outcome == {'edit': outcome['edit'], 'replace': 'REVISION_CONFLICT'}
    current = repo.read(PROJECT)
    assert text_of(current) == 'Manual edit' and current.title == 'Synthetic papers'


def test_eviction_keeps_the_revision_history_and_writes_the_registry(tmp_path):
    import hashlib
    from tests.templates.storage_fixtures import workspace as papers
    repo = repository(tmp_path)
    repo.open_limit = 1
    edit(repo, 'Before eviction', identifier='edit-1', action='one')
    other, sources = papers()
    data = other.model_dump(by_alias=True)
    data['projectId'] = data['project']['projectId'] = 'second-project'
    other = type(other).model_validate(data)
    repo.create(other, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
    assert [key for key, value in repo.sessions.items() if value.workspace is not None] == ['second-project']
    entry = next(value for value in repo.store.registry().entries if value.project_id == PROJECT)
    assert entry.updated_at != '2026-10-21T00:00:00Z'
    session = repo.open(PROJECT)
    assert session.revision == 2 and text_of(session.workspace) == 'Before eviction'
    assert session.journal.state()['undo']['actionId'] == 'one'


def test_edits_do_not_write_the_registry_but_close_does(tmp_path):
    repo = repository(tmp_path)
    registry = tmp_path / 'data/registry.json'
    raw = registry.read_bytes()
    edit(repo, 'One', identifier='edit-1')
    edit(repo, 'Two', identifier='edit-2')
    assert registry.read_bytes() == raw
    listed = next(entry for entry in repo.listing() if entry.project_id == PROJECT)
    assert listed.updated_at == repo.read(PROJECT).updated_at
    repo.close(PROJECT)
    assert registry.read_bytes() != raw
    assert ProjectRepository(tmp_path / 'data').read(PROJECT).project_revision == 3


def test_an_outside_write_is_adopted_instead_of_overwritten(tmp_path):
    from packages.resume_core.project_repository import rich_snapshot_bytes
    from packages.resume_core.storage import atomic_write
    repo = repository(tmp_path)
    edit(repo, 'Mine', identifier='edit-1', action='one')
    outside = repo.read(PROJECT).model_copy(deep=True)
    outside.title, outside.project_revision, outside.project.revision = 'Written elsewhere', 5, 5
    atomic_write(tmp_path / 'data/projects' / PROJECT / 'workspace.json', rich_snapshot_bytes(outside))
    with pytest.raises(RepositoryFailure) as refused:
        edit(repo, 'Late', identifier='edit-2', base=2)
    assert refused.value.code == 'REVISION_CONFLICT' and refused.value.details['revision'] == 5
    assert repo.read(PROJECT).title == 'Written elsewhere' and repo.open(PROJECT).journal.state()['undo'] is None


def test_a_new_editor_keeps_its_token_when_all_older_sessions_are_pinned(tmp_path):
    import hashlib
    from tests.templates.storage_fixtures import workspace as papers
    repo = repository(tmp_path)
    repo.open_limit = 1
    other, sources = papers()
    data = other.model_dump(by_alias=True)
    data['projectId'] = data['project']['projectId'] = 'new-project'
    other = type(other).model_validate(data)
    with repo.pinned(PROJECT):
        opened = repo.create(other, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
        token = opened.open_editor()
        current = repo.open('new-project')
        current.require_editor(token)
        assert current is opened
        repo.mutate('new-project', base_revision=1, client_mutation_id='new-edit', request_sha256='a' * 64,
            action_id='new-action', kind='edit', build=typing('Still open', identifier='new-edit'))
        assert text_of(repo.read('new-project')) == 'Still open'


def test_a_session_held_across_an_eviction_stays_the_project_session(tmp_path):
    repo = repository(tmp_path)
    repo.open_limit = 1
    held = repo.open(PROJECT)
    create_other(repo, 'second-project')
    assert held.workspace is None
    with held.lock:
        assert held.revision == 1
        edit(repo, 'Through the held session', identifier='edit-1')
        assert text_of(held.workspace) == 'Through the held session'
    assert repo.open(PROJECT) is held and repo.read(PROJECT).project_revision == 2
    with pytest.raises(RepositoryFailure) as refused:
        edit(repo, 'Same base again', identifier='edit-2', base=1)
    assert refused.value.code == 'REVISION_CONFLICT'


def test_an_eviction_keeps_the_editor_tokens_and_the_clipboard(tmp_path):
    repo = repository(tmp_path)
    repo.open_limit = 1
    session = repo.open(PROJECT)
    first = session.open_editor()
    current = session.open_editor()
    session.remember_capture('capture-1', 'copied')
    create_other(repo, 'second-project')
    reopened = repo.open(PROJECT)
    reopened.require_editor(current)
    with pytest.raises(RepositoryFailure) as replaced:
        reopened.require_editor(first)
    assert replaced.value.code == 'EDITOR_REPLACED' and reopened.clipboard['capture-1'] == 'copied'


def test_a_failed_registry_write_on_eviction_does_not_fail_another_open(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    repo.open_limit = 1
    edit(repo, 'Dirty title time', identifier='edit-1')
    def refused(_workspace):
        raise RepositoryFailure('PROJECT_SAVE_FAILED')
    monkeypatch.setattr(repo, '_write_registry_entry', refused)
    create_other(repo, 'second-project')
    evicted = repo.sessions[PROJECT]
    assert evicted.workspace is None and evicted.registry_dirty
    monkeypatch.undo()
    assert text_of(repo.read(PROJECT)) == 'Dirty title time'
    repo.close(PROJECT)
    assert not evicted.registry_dirty


def test_an_edit_racing_a_delete_is_refused_even_when_cleanup_fails(tmp_path, monkeypatch):
    from packages.resume_core import project_repository
    repo = repository(tmp_path)
    workspace_file = tmp_path / 'data/projects' / PROJECT / 'workspace.json'
    raw = workspace_file.read_bytes()
    outcome = {}
    def racing_edit():
        try:
            edit(repo, 'Zombie', identifier='zombie', base=1)
        except RepositoryFailure as error:
            outcome['code'] = error.code
    original = repo.store.tombstone
    def tombstone(project_id):
        # Before the fix the racing edit loaded a second session here and committed into the project being deleted.
        racer = threading.Thread(target=racing_edit)
        racer.start()
        racer.join(0.5)
        outcome['racer'] = racer
        return original(project_id)
    monkeypatch.setattr(repo.store, 'tombstone', tombstone)
    monkeypatch.setattr(project_repository, '_remove_project_files', lambda _directory: (_ for _ in ()).throw(OSError('busy')))
    entry = repo.delete(PROJECT)
    outcome['racer'].join(5)
    assert entry.cleanup_status == 'failed' and outcome.get('code') == 'PROJECT_DELETED'
    assert workspace_file.read_bytes() == raw and PROJECT not in repo.sessions


def test_cleanup_removes_temporary_files_left_in_blob_folders(tmp_path):
    repo = repository(tmp_path)
    directory = repo.open(PROJECT).directory
    leftover = directory / 'sources' / '.foldcv-write-interrupted'
    leftover.write_bytes(b'partial')
    leftover.chmod(0o600)
    entry = repo.delete(PROJECT)
    assert entry.cleanup_status == 'complete' and not directory.exists()
