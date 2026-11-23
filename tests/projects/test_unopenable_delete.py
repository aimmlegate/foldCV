"""F9 of the tester feedback of 2026-11-23: each résumé entry that the app cannot open can still be deleted in the app;
only a symbolic link and a foreign identity marker stay refused."""

import json
import shutil

import pytest

from packages.resume_core.repository.project_repository import ProjectRepository
from packages.resume_core.repository.project_store import ProjectStore
from tests.projects.support import v2_app
from tests.projects.test_project_catalog import FIRST, OTHER, entries, projects


def broken(tmp_path, damage):
    """A store with two projects; the first one damaged as `damage` says. Returns the first one's folder."""
    with v2_app(tmp_path, projects()) as (client, application):
        repository = application.state.projects.repository
        directory = repository.open(FIRST).directory
        assert client.post('/v2/projects/' + FIRST + '/catalog/archive', json={}).status_code == 200
        repository.close(FIRST)
    if damage == 'folder':
        shutil.rmtree(directory)
    elif damage == 'project':
        (directory / 'workspace.json').write_bytes(b'broken workspace')
    elif damage == 'version':
        value = json.loads((directory / 'workspace.json').read_bytes())
        value['schemaVersion'] = 99
        (directory / 'workspace.json').write_text(json.dumps(value))
    elif damage == 'marker':
        (directory / '.project-identity.json').unlink()
    elif damage == 'empty':
        shutil.rmtree(directory)
        directory.mkdir(mode=0o700)
    return directory


@pytest.mark.parametrize('damage', ['folder', 'project', 'version', 'marker', 'empty'])
def test_an_entry_that_cannot_be_opened_is_deleted_through_the_route_and_stays_gone(tmp_path, damage):
    directory = broken(tmp_path, damage)
    with v2_app(tmp_path) as (client, application):
        assert client.post('/v2/projects/' + FIRST + '/open', json={}).status_code >= 400
        reply = client.request('DELETE', '/v2/projects/' + FIRST, json={'confirmed': True})
        assert reply.status_code == 200, reply.text[:300]
        assert reply.json()['deleted'] and reply.json()['cleanupStatus'] == 'complete'
        assert FIRST not in entries(client) and OTHER in entries(client)
        # The catalog flags of the entry go with it.
        assert FIRST not in application.state.projects.catalog.entries()
    assert not directory.exists()
    with v2_app(tmp_path) as (client, _application):
        assert FIRST not in entries(client)


def test_an_entry_with_no_folder_is_deleted_by_the_store_and_the_repository(tmp_path):
    directory = broken(tmp_path, 'folder')
    store = ProjectStore(tmp_path / 'data')
    entry = store.tombstone(FIRST)
    assert entry.tombstoned and store.cleanup_deleted(FIRST).cleanup_status == 'complete'
    directory = broken(tmp_path / 'second', 'folder')
    repository = ProjectRepository(tmp_path / 'second' / 'data')
    repository.start()
    assert repository.delete(FIRST).cleanup_status == 'complete'
    assert FIRST not in {item.project_id for item in repository.listing()}
    assert not directory.exists()


def test_a_symbolic_link_and_a_foreign_marker_are_still_refused(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        repository = application.state.projects.repository
        directory = repository.open(FIRST).directory
        other = repository.open(OTHER).directory
        repository.close(FIRST); repository.close(OTHER)
    # A foreign marker: the folder names another project.
    (directory / '.project-identity.json').write_text(json.dumps({'version': 1, 'projectId': 'someone-else'}))
    # A link: the project's name points to a folder outside the store.
    outside = tmp_path / 'outside'
    shutil.move(str(other), str(outside))
    other.symlink_to(outside, target_is_directory=True)
    kept = sorted(path.name for path in outside.iterdir())
    with v2_app(tmp_path) as (client, _application):
        for project in (FIRST, OTHER):
            reply = client.request('DELETE', '/v2/projects/' + project, json={'confirmed': True})
            assert reply.status_code >= 400 and reply.json()['error']['code'] == 'PROJECT_DELETE_FAILED', reply.text[:200]
        assert {FIRST, OTHER} <= set(entries(client))
    assert directory.is_dir() and sorted(path.name for path in outside.iterdir()) == kept and other.is_symlink()


def test_a_second_delete_answers_as_a_deleted_project_does(tmp_path):
    broken(tmp_path, 'folder')
    with v2_app(tmp_path) as (client, _application):
        first = client.request('DELETE', '/v2/projects/' + FIRST, json={'confirmed': True})
        again = client.request('DELETE', '/v2/projects/' + FIRST, json={'confirmed': True})
        normal = client.request('DELETE', '/v2/projects/' + OTHER, json={'confirmed': True})
        normal_again = client.request('DELETE', '/v2/projects/' + OTHER, json={'confirmed': True})
    assert first.status_code == normal.status_code == 200
    assert (again.status_code, again.json()) == (normal_again.status_code, {**normal_again.json(), **(
        {'projectId': FIRST} if 'projectId' in normal_again.json() else {})})
