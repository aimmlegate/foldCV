"""GET /v2/projects/{id}/sources/{source}/original: exact bytes, media types, session boundaries and failure codes the
hash and symlink checks of test_sources.py do not reach."""

import pytest

from packages.resume_core.project_repository import blob_path
from tests.projects.support import ORIGIN, v2_app
from tests.templates.storage_fixtures import workspace as papers

PROJECT = 'template-project'


def named(name):
    workspace, sources = papers()
    workspace.project.sources[0].original_name = name
    return workspace, sources


def path(source='source-papers'):
    return '/v2/projects/' + PROJECT + '/sources/' + source + '/original'


@pytest.mark.parametrize(('name', 'mime'), [
    ('Original.PDF', 'application/pdf'),
    ('Original.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    ('Original.txt', 'text/plain'), ('Original.MD', 'text/markdown'), ('Original.markdown', 'text/markdown'),
    ('Original', 'application/octet-stream'),
])
def test_the_exact_original_keeps_its_media_type_and_survives_a_restart_without_a_project_change(tmp_path, name, mime):
    workspace, sources = named(name)
    with v2_app(tmp_path, [(workspace, sources)]):
        pass
    with v2_app(tmp_path) as (client, application):
        file = application.state.projects.repository.open(PROJECT).directory / 'workspace.json'
        before = file.read_bytes()
        response = client.get(path())
        assert response.status_code == 200 and response.content == sources['source-papers']
        assert response.headers['content-type'].split(';')[0] == mime
        assert response.headers['cache-control'] == 'no-store'
        assert file.read_bytes() == before


def test_unknown_missing_and_changed_originals_fail_without_extracted_text(tmp_path):
    workspace, sources = papers()
    with v2_app(tmp_path, [(workspace, sources)]) as (client, application):
        stored = blob_path(application.state.projects.repository.open(PROJECT).directory, 'sources', 'source-papers')
        unknown = client.get(path('unowned'))
        assert unknown.status_code == 404 and unknown.json()['error']['code'] == 'SOURCE_NOT_FOUND'
        stored.unlink()
        missing = client.get(path())
        assert missing.status_code == 404 and missing.json()['error']['code'] == 'SOURCE_BYTES_MISSING'
        assert workspace.project.sources[0].units[0].text.encode() not in missing.content


def test_the_route_needs_the_session_and_origin_names_the_download_safely_and_ends_with_the_project(tmp_path):
    with v2_app(tmp_path, [named('../Резюме\r\n.docx')]) as (client, _application):
        anonymous = client.__class__(client.app, base_url=ORIGIN)
        assert anonymous.get(path()).status_code == 401
        assert client.get(path(), headers={'Origin': 'https://foreign.example'}).status_code == 403
        download = client.get(path() + '/download')
        assert download.status_code == 200
        assert download.headers['content-disposition'] == "attachment; filename*=UTF-8''%D0%A0%D0%B5%D0%B7%D1%8E%D0%BC%D0%B5.docx"
        assert client.get(path()).headers['content-disposition'].startswith('inline;')
        assert client.request('DELETE', '/v2/projects/' + PROJECT, json={'confirmed': True}).status_code == 200
        gone = client.get(path())
        assert gone.status_code == 410 and gone.json()['error']['code'] == 'PROJECT_DELETED'
