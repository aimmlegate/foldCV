"""The service starts on a store that still holds files of the deleted generations, serves its V7 projects and leaves
those files as they were."""

import json
import os

import pytest

from tests.projects.support import v2_app
from tests.projects.test_project_catalog import FIRST, OTHER, projects
from tests.templates.storage_fixtures import workspace


def leftovers(data):
    v6 = {'schemaVersion': 6, 'projectId': 'project-v6', 'projectRevision': 3, 'documentRevision': 2, 'title': 'Old',
        'project': None, 'preDraft': None, 'syncRecords': [], 'mutationReplay': [], 'warnings': []}
    return {
        # The job store of the background stack.
        data / 'background/projects/project-old/state.json': b'{"schemaVersion":1,"jobs":[],"intents":[]}',
        data / 'background/dispatch.json': b'{"schemaVersion":1,"accountGeneration":4}',
        # The V6 assistant store and its catalog actions.
        data / 'assistant/projects/project-old/state.json': b'{"schemaVersion":1,"conversations":[]}',
        data / 'assistant/proposals/proposal-old.json': b'{"schemaVersion":1}',
        data / 'migrated-d104/project-old/state.json': b'{}',
        # A V6 workspace kept outside the projects tree.
        data / 'old-projects/project-v6/workspace.json': json.dumps(v6).encode(),
    }


def snapshot(data):
    return {path.relative_to(data): path.read_bytes() for path in sorted(data.rglob('*')) if path.is_file()
        and path.parts[len(data.parts)] in {'background', 'assistant', 'migrated-d104', 'old-projects'}}


def test_startup_serves_v7_projects_and_leaves_old_job_agent_and_v6_files_untouched(tmp_path):
    data = tmp_path / 'data'
    files = leftovers(data)
    for path, raw in files.items():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(raw)
    before = snapshot(data)
    project, sources = workspace()
    with v2_app(tmp_path, [(project, sources)]) as (client, _app):
        listing = client.get('/v2/projects')
        assert listing.status_code == 200
        body = listing.json()
        assert [entry['projectId'] for entry in body['entries']] == [project.project_id] and body['errors'] == []
        opened = client.post('/v2/projects/' + project.project_id + '/open', json={})
        assert opened.status_code == 200
    assert snapshot(data) == before


def damaged(target, how):
    if how == 'mode':
        target.chmod(0o644)
    elif how == 'hard_link':
        os.link(target, target.parent.parent / 'second-name')
    elif how == 'above_old_ceiling':
        # Allowed by a raised Settings size, above the 64 MiB default of owned_file.
        target.write_bytes(b'{' + b' ' * (65 * 1024 * 1024) + b'}')
    else:
        target.write_text(json.dumps({'schemaVersion': 7, 'project': {'templatePackage': how}}))


@pytest.mark.parametrize(('how', 'code'), [('mode', 'PROJECT_UNSAFE_STORAGE'), ('hard_link', 'PROJECT_UNSAFE_STORAGE'),
    ('above_old_ceiling', 'PROJECT_LOAD_FAILED'), ('text', 'PROJECT_LOAD_FAILED'), ({'assets': 5}, 'PROJECT_LOAD_FAILED')],
    ids=['mode', 'hard_link', 'above_old_ceiling', 'package_text', 'assets_number'])
def test_one_damaged_project_file_does_not_stop_the_service_from_starting(tmp_path, how, code):
    with v2_app(tmp_path, projects()) as (_client, application):
        target = application.state.projects.repository.open(FIRST).directory / 'workspace.json'
    damaged(target, how)
    with v2_app(tmp_path) as (client, _application):
        listing = client.get('/v2/projects').json()
        assert listing['errors'] == [{'projectId': FIRST, 'errorCode': code}]
        assert client.get('/v2/projects/' + OTHER).status_code == 200
