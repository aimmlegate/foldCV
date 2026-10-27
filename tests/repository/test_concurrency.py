"""One lock per project: writers serialize, background work never overwrites an edit (G4)."""

import threading

import pytest

from packages.resume_core.project_repository import ProjectRepository, RepositoryFailure
from tests.repository.support import PROJECT, edit, repository, text_of, typing


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
    assert list(repo.sessions) == ['second-project']
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
