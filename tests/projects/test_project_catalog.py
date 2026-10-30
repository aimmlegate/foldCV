"""The project catalog (project_catalog) through the v2 routes: listing order, recency, archive flags and deletion keep
project files as they are and never decode or follow what they should not."""

import json

import pytest

from packages.resume_core.project_repository import ProjectRepository
from packages.resume_core.project_store import ProjectStoreFailure
from tests.projects.support import Editor, source_blobs, v2_app
from tests.templates.storage_fixtures import workspace as papers

FIRST, OTHER = 'template-project', 'other-project'


def copy(identifier):
    first, sources = papers()
    data = first.model_dump(by_alias=True)
    data['projectId'] = data['project']['projectId'] = identifier
    return type(first).model_validate(data), sources


def projects():
    return [papers(), copy(OTHER)]


def entries(client):
    reply = client.get('/v2/projects')
    assert reply.status_code == 200, reply.text[:300]
    return {entry['projectId']: entry for entry in reply.json()['entries']}


def delete(client, project):
    reply = client.request('DELETE', '/v2/projects/' + project, json={'confirmed': True})
    assert reply.status_code == 200, reply.text[:300]
    return reply.json()


def test_only_an_explicit_open_updates_recency_and_the_archive_flag_survives_restart(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        assert client.post('/v2/projects/' + FIRST + '/open', json={}).status_code == 200
        initial = entries(client)[FIRST]['lastOpenedAt']
        assert initial is not None
        client.get('/v2/projects/' + FIRST)
        application.state.projects.repository.close(FIRST)
        assert entries(client)[FIRST]['lastOpenedAt'] == initial
        assert client.post('/v2/projects/' + OTHER + '/open', json={}).status_code == 200
        assert client.post('/v2/projects/' + FIRST + '/catalog/archive', json={}).status_code == 200
        path = application.state.projects.repository.open(FIRST).directory / 'workspace.json'
    before = path.read_bytes()
    with v2_app(tmp_path) as (client, _application):
        listed = entries(client)
        assert listed[FIRST]['archived'] and not listed[OTHER]['archived']
        assert client.post('/v2/projects/' + FIRST + '/catalog/restore', json={}).status_code == 200
        assert not entries(client)[FIRST]['archived'] and entries(client)[FIRST]['lastOpenedAt'] == initial
    assert path.read_bytes() == before


def test_the_listing_is_newest_added_first_whatever_was_opened_renamed_or_archived_since(tmp_path):
    def order(client):
        return [entry['projectId'] for entry in client.get('/v2/projects').json()['entries']]
    with v2_app(tmp_path, [*projects(), copy('third-project')]) as (client, application):
        assert order(client) == ['third-project', OTHER, FIRST]
        editor = Editor(client, FIRST)
        editor.call('post', '/rename', {'editorToken': editor.token, 'baseRevision': editor.revision, 'title': 'Renamed'})
        archived = client.post('/v2/projects/' + OTHER + '/catalog/archive', json={}).json()['entries']
        assert [entry['projectId'] for entry in archived] == ['third-project', OTHER, FIRST]
        assert order(client) == ['third-project', OTHER, FIRST]
        added, sources = copy('added-project')
        application.state.projects.repository.create(added, blobs=source_blobs(sources))
        assert order(client) == ['added-project', 'third-project', OTHER, FIRST]
    with v2_app(tmp_path) as (client, _application):
        assert order(client) == ['added-project', 'third-project', OTHER, FIRST]


@pytest.mark.parametrize('version', [5, 99, 'unreadable'])
def test_old_and_unreadable_projects_archive_and_delete_without_opening(tmp_path, version):
    with v2_app(tmp_path, projects()) as (client, application):
        target = application.state.projects.repository.open(FIRST).directory / 'workspace.json'
        application.state.projects.repository.close(FIRST)
    if version == 'unreadable':
        target.write_bytes(b'broken workspace')
    else:
        value = json.loads(target.read_bytes())
        value['schemaVersion'] = version
        target.write_text(json.dumps(value))
    before = target.read_bytes()
    with v2_app(tmp_path) as (client, _application):
        opened = client.post('/v2/projects/' + FIRST + '/open', json={})
        assert opened.status_code >= 400 and opened.json()['error']['code']
        listing = client.get('/v2/projects').json()
        assert [error['projectId'] for error in listing['errors']] == [FIRST]
        assert entries(client)[FIRST]['lastOpenedAt'] is None
        assert client.post('/v2/projects/' + FIRST + '/catalog/archive', json={}).status_code == 200
        assert entries(client)[FIRST]['archived'] and target.read_bytes() == before
        result = delete(client, FIRST)
        assert result['deleted'] and result['cleanupStatus'] == 'complete' and not target.exists()
        assert FIRST not in entries(client)
        assert client.get('/v2/projects/' + OTHER).json()['workspace']['projectId'] == OTHER


def test_cleanup_is_retryable_and_an_unrelated_file_never_becomes_a_delete_target(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        directory = application.state.projects.repository.open(FIRST).directory
        extra = directory / 'unknown-user-file.txt'
        extra.write_text('Keep until inspected')
        result = delete(client, FIRST)
        assert result['deleted'] and result['cleanupStatus'] == 'failed'
        assert extra.read_text() == 'Keep until inspected' and FIRST not in entries(client)
        # The project's own files go at once: only the unknown file and the marker that lets a retry finish stay.
        assert {path.name for path in directory.iterdir()} == {extra.name, '.project-identity.json'}
        assert client.post('/v2/projects/' + FIRST + '/open', json={}).json()['error']['code'] == 'PROJECT_DELETED'
        assert client.get('/v2/projects/' + OTHER).json()['workspace']['projectId'] == OTHER
        extra.unlink()
        assert delete(client, FIRST)['cleanupStatus'] == 'complete' and not directory.exists()


@pytest.mark.parametrize('status', ['pending', 'failed'])
def test_the_next_start_finishes_a_deletion_that_did_not_complete(tmp_path, status):
    with v2_app(tmp_path, projects()) as (client, application):
        repository = application.state.projects.repository
        directory = repository.open(FIRST).directory
        if status == 'pending':
            # The service stopped between the tombstone and the removal.
            repository.close(FIRST)
            repository.store.tombstone(FIRST)
            repository.sessions.pop(FIRST)
        else:
            extra = directory / 'unknown-user-file.txt'
            extra.write_text('Removed by the user later')
            assert delete(client, FIRST)['cleanupStatus'] == 'failed'
            extra.unlink()
    restarted = ProjectRepository(tmp_path / 'data')
    restarted.start()
    assert not directory.exists()
    entry = next(item for item in restarted.store.registry().entries if item.project_id == FIRST)
    assert entry.tombstoned and entry.cleanup_status == 'complete'


@pytest.mark.parametrize('damage', ['text', 'mode', 'folder'])
def test_a_damaged_catalog_costs_only_flags_and_a_working_page_keeps_its_token(tmp_path, damage):
    with v2_app(tmp_path, projects()) as (client, application):
        editor = Editor(client, FIRST)
        path = application.state.projects.repository.store.root / 'catalog.json'
        if damage == 'folder':
            path.unlink()
            path.mkdir()
        elif damage == 'mode':
            path.chmod(0o644)
        else:
            path.write_bytes(b'{broken')
        assert set(entries(client)) == {FIRST, OTHER}
        assert client.post('/v2/projects/' + OTHER + '/open', json={}).status_code == 200
        editor.call('post', '/rename', {'editorToken': editor.token, 'baseRevision': editor.revision, 'title': 'Kept'})
        assert Editor(client, FIRST).response['workspace']['title'] == 'Kept'


def test_a_catalog_write_failure_on_a_flag_is_a_public_code(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        path = application.state.projects.repository.store.root / 'catalog.json'
        path.mkdir()
        refused = client.post('/v2/projects/' + FIRST + '/catalog/archive', json={})
        assert refused.status_code == 503 and refused.json()['error']['code'] == 'PROJECT_SAVE_FAILED'


def test_a_damaged_registry_gives_open_the_code_the_listing_gives(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        repository = application.state.projects.repository
        repository.close(FIRST)
        repository.store.registry_path.write_bytes(b'{broken')
        for reply in (client.get('/v2/projects'), client.post('/v2/projects/' + FIRST + '/open', json={})):
            assert reply.status_code == 503 and reply.json()['error']['code'] == 'PROJECT_LOAD_FAILED'


def test_a_damaged_registry_does_not_stop_the_service_from_starting(tmp_path):
    with v2_app(tmp_path, projects()) as (_client, application):
        path = application.state.projects.repository.store.registry_path
    path.write_bytes(b'{broken')
    with v2_app(tmp_path) as (client, _application):
        assert client.get('/v2/projects').json()['error']['code'] == 'PROJECT_LOAD_FAILED'
    assert path.read_bytes() == b'{broken'


def test_catalog_flags_never_follow_a_project_symlink(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        service = application.state.projects
        outside = tmp_path / 'outside'
        outside.mkdir()
        sentinel = outside / 'keep.txt'
        sentinel.write_text('Keep')
        (service.repository.store.projects / 'linked').symlink_to(outside, target_is_directory=True)
        with pytest.raises(ProjectStoreFailure):
            service.catalog.update('linked', archived=True)
        assert client.post('/v2/projects/linked/catalog/archive', json={}).status_code >= 400
        assert sentinel.read_text() == 'Keep' and list(outside.iterdir()) == [sentinel]
        assert 'linked' not in service.catalog.entries()


def test_an_interrupted_directory_removal_is_retried_without_the_identity_marker(tmp_path, monkeypatch):
    with v2_app(tmp_path, projects()) as (client, application):
        repository = application.state.projects.repository
        directory = repository.open(FIRST).directory
        original, failed = type(directory).rmdir, []
        def interrupted(path):
            if path == directory and not failed:
                failed.append(path)
                raise OSError('interrupted removal')
            return original(path)
        monkeypatch.setattr(type(directory), 'rmdir', interrupted)
        assert delete(client, FIRST)['cleanupStatus'] == 'failed'
        assert directory.is_dir() and not (directory / '.project-identity.json').exists()
        assert repository.cleanup_deleted(FIRST).cleanup_status == 'complete' and not directory.exists()
        assert repository.cleanup_deleted(FIRST).cleanup_status == 'complete'
        assert client.get('/v2/projects/' + OTHER).json()['workspace']['projectId'] == OTHER


def test_delete_without_the_literal_confirmation_is_refused_and_removes_nothing(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        directory = application.state.projects.repository.open(FIRST).directory
        for body in ({}, {'confirmed': False}, {'confirmed': 'true'}):
            assert client.request('DELETE', '/v2/projects/' + FIRST, json=body).status_code == 422
        assert directory.is_dir() and FIRST in entries(client)
