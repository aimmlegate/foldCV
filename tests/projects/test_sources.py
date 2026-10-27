"""Original bytes keep their hash, private-file checks and safe download name."""

from packages.resume_core.project_repository import blob_path
from tests.projects.support import v2_app
from tests.templates.storage_fixtures import workspace as papers


def test_original_hash_and_symlink_checks(tmp_path):
    workspace, sources = papers()
    project = workspace.project_id
    source = workspace.project.sources[0]
    with v2_app(tmp_path, [(workspace, sources)]) as (client, app):
        path = '/v2/projects/' + project + '/sources/' + source.id + '/original'
        response = client.get(path)
        assert response.status_code == 200 and response.content == sources[source.id]
        assert response.headers['x-foldcv-sha256'] == source.byte_sha256
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert client.get(path + '/download').headers['content-disposition'].startswith('attachment;')
        stored = blob_path(app.state.projects.repository.open(project).directory, 'sources', source.id)
        stored.write_bytes(b'corrupt')
        assert client.get(path).json()['error']['code'] == 'SOURCE_BYTES_MISMATCH'
        outside = tmp_path / 'outside.txt'
        outside.write_bytes(sources[source.id])
        stored.unlink()
        stored.symlink_to(outside)
        denied = client.get(path)
        assert denied.status_code == 503 and denied.json()['error']['code'] == 'PROJECT_UNSAFE_STORAGE'
