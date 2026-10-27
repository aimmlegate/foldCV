"""The project catalog (project_catalog) through the v2 routes: recency, archive flags and deletion keep project files
as they are and never decode or follow what they should not."""

import json

import pytest

from packages.resume_core.project_store import ProjectStoreFailure
from tests.projects.support import v2_app
from tests.templates.storage_fixtures import workspace as papers

FIRST, OTHER = 'template-project', 'other-project'


def projects():
    first, sources = papers()
    data = first.model_dump(by_alias=True)
    data['projectId'] = data['project']['projectId'] = OTHER
    return [(first, sources), (type(first).model_validate(data), sources)]


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
        assert client.get('/v2/projects').json()['entries'][0]['projectId'] == OTHER
        assert client.post('/v2/projects/' + FIRST + '/catalog/archive', json={}).status_code == 200
        path = application.state.projects.repository.open(FIRST).directory / 'workspace.json'
    before = path.read_bytes()
    with v2_app(tmp_path) as (client, _application):
        listed = entries(client)
        assert listed[FIRST]['archived'] and not listed[OTHER]['archived']
        assert client.post('/v2/projects/' + FIRST + '/catalog/restore', json={}).status_code == 200
        assert not entries(client)[FIRST]['archived'] and entries(client)[FIRST]['lastOpenedAt'] == initial
    assert path.read_bytes() == before


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
        assert client.post('/v2/projects/' + FIRST + '/open', json={}).json()['error']['code'] == 'PROJECT_DELETED'
        assert client.get('/v2/projects/' + OTHER).json()['workspace']['projectId'] == OTHER
        extra.unlink()
        assert delete(client, FIRST)['cleanupStatus'] == 'complete' and not directory.exists()


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
