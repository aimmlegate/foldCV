"""GET /v2/projects and the response cache: one unreadable project is an error entry, an unloaded session lists its
heading from the file, and responses are kept for the four latest projects only."""

import json

import pytest

from packages.resume_core.project_repository import ProjectRepository, blob_path
from packages.resume_core.templates import models
from resume_api.projects.service import ProjectService
from tests.projects.support import v2_app
from tests.projects.test_project_catalog import FIRST, OTHER, projects
from tests.templates.storage_fixtures import workspace as papers


def listed(client):
    reply = client.get('/v2/projects')
    assert reply.status_code == 200, reply.text[:300]
    return reply.json()


@pytest.mark.parametrize(('damage', 'code'), [('nested', 'PROJECT_LOAD_FAILED'), ('asset', 'PROJECT_UNSAFE_STORAGE')])
def test_one_unreadable_project_is_an_error_entry_and_the_others_keep_their_heading(tmp_path, monkeypatch, damage, code):
    with v2_app(tmp_path, projects()) as (_client, application):
        directory = application.state.projects.repository.open(FIRST).directory
    with v2_app(tmp_path) as (client, _application):
        other = client.get('/v2/projects/' + OTHER).json()
        if damage == 'nested':
            (directory / 'workspace.json').write_bytes(b'[' * 100000 + b']' * 100000)
        else:
            # An asset the process has not read yet, in a group-readable file the owned-file check refuses.
            asset = other['workspace']['project']['templatePackage']['assets'][0]['sha256']
            monkeypatch.delitem(models._ASSET_TEXTS, asset)
            blob_path(directory, 'template-assets', asset).chmod(0o644)
        value = listed(client)
        assert value['errors'] == [{'projectId': FIRST, 'errorCode': code}]
        entries = {entry['projectId']: entry for entry in value['entries']}
        assert set(entries) == {FIRST, OTHER} and entries[OTHER]['title'] == other['identity']['title']


@pytest.mark.parametrize(('damage', 'code'), [('marker', 'PROJECT_UNSAFE_STORAGE'), ('package', 'PROJECT_LOAD_FAILED'),
    ('assets', 'PROJECT_LOAD_FAILED'), ('history', 'PROJECT_LOAD_FAILED'), ('symlink', 'PROJECT_UNSAFE_STORAGE')])
def test_a_damaged_project_is_listed_as_unopenable_and_open_gives_the_same_code(tmp_path, damage, code):
    with v2_app(tmp_path, projects()) as (_client, application):
        directory = application.state.projects.repository.open(FIRST).directory
    target = directory / 'workspace.json'
    if damage == 'marker':
        (directory / '.project-identity.json').write_bytes(b'not json')
    elif damage == 'symlink':
        outside = tmp_path / 'outside.json'
        outside.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(outside)
    else:
        value = json.loads(target.read_bytes())
        if damage == 'history':
            value['project']['importHistory'] = 5
        else:
            value['project']['templatePackage'] = 'text' if damage == 'package' else {'assets': 5}
        target.write_text(json.dumps(value))
    with v2_app(tmp_path) as (client, _application):
        value = listed(client)
        assert value['errors'] == [{'projectId': FIRST, 'errorCode': code}]
        assert {entry['projectId'] for entry in value['entries']} == {FIRST, OTHER}
        opened = client.post('/v2/projects/' + FIRST + '/open', json={})
        assert opened.status_code == 503 and opened.json()['error']['code'] == code


def test_an_unloaded_session_lists_its_heading_from_the_file(tmp_path):
    with v2_app(tmp_path, projects()) as (client, application):
        service = application.state.projects
        heading = client.get('/v2/projects/' + FIRST).json()['identity']['title']
        session = service.repository.open(FIRST)
        # Eviction unloads the workspace and keeps the handle.
        workspace, session.workspace = session.workspace, None
        service.identities.clear()
        try:
            entries = {entry['projectId']: entry for entry in listed(client)['entries']}
        finally:
            session.workspace = workspace
        assert entries[FIRST]['title'] == heading


def test_responses_are_kept_for_the_four_latest_projects(tmp_path):
    workspace, _sources = papers()
    service = ProjectService(ProjectRepository(tmp_path / 'data'))
    for index in range(6):
        service.response('project-' + str(index), workspace)
    assert list(service.responses) == ['project-2', 'project-3', 'project-4', 'project-5']
    service.response('project-2', workspace)
    service.response('project-6', workspace)
    assert list(service.responses) == ['project-4', 'project-5', 'project-2', 'project-6']
