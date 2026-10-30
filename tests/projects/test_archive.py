"""A .foldcv export imports to the same project, and the undo journal stays out of the file (plan SR04); the zip is
built after the project lock is released."""

import hashlib
import io
import json
import threading
import zipfile

from PIL import Image
import pytest

from packages.resume_core.archive_zip import ArchiveFailure
from packages.resume_core.models.rich_workspace import LocalImageAsset
from packages.resume_core.template_archive import _verify_image
from tests.projects.support import Editor, v2_app
from tests.templates.storage_fixtures import workspace as papers


PROJECT = 'template-project'
VOLATILE = {'projectId', 'projectRevision', 'documentRevision', 'revision', 'createdAt', 'updatedAt', 'mutationReplay'}


def core(workspace):
    def strip(value):
        if isinstance(value, dict):
            return {key: strip(child) for key, child in value.items() if key not in VOLATILE}
        if isinstance(value, list):
            return [strip(child) for child in value]
        return value
    return strip(workspace)


def test_export_then_import_matches_and_omits_the_journal(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        editor = Editor(client, PROJECT)
        directory = application.state.projects.repository.open(PROJECT).directory
        (directory / 'history.jsonl').write_bytes(b'{"kind":"edit"}\n')
        body = {'editorToken': editor.token, 'projectRevision': editor.revision,
            'documentRevision': editor.response['workspace']['documentRevision']}
        downloaded = client.post('/v2/projects/' + PROJECT + '/archive', json=body)
        assert downloaded.status_code == 200, downloaded.text[:400]
        assert downloaded.headers['content-type'].startswith('application/vnd.foldcv.project+zip')
        names = zipfile.ZipFile(io.BytesIO(downloaded.content)).namelist()
        assert 'history.jsonl' not in names and not any(name.endswith('history.jsonl') for name in names)
        opened = client.post('/v2/projects/archive', files={'file': ('project.foldcv', downloaded.content, 'application/zip')})
        assert opened.status_code == 201, opened.text[:400]
        imported = opened.json()['workspace']
        assert imported['projectId'] != PROJECT
        original = editor.response['workspace']
        assert core(original) == core(imported)
        source = original['project']['sources'][0]['id']
        original_bytes = client.get('/v2/projects/' + PROJECT + '/sources/' + source + '/original')
        imported_bytes = client.get('/v2/projects/' + imported['projectId'] + '/sources/' + source + '/original')
        assert original_bytes.status_code == 200 and original_bytes.content == imported_bytes.content
        assert not (application.state.projects.repository.open(imported['projectId']).directory / 'history.jsonl').exists()
        assert core(Editor(client, imported['projectId']).response['workspace']) == core(original)


def test_the_zip_is_built_after_the_project_lock_is_released(tmp_path, monkeypatch):
    from resume_api.projects import archive
    with v2_app(tmp_path, [papers()]) as (client, application):
        editor = Editor(client, PROJECT)
        session = application.state.projects.repository.open(PROJECT)
        build, free = archive.write_zip, []

        def probed(payload):
            def probe():
                with session.lock:
                    pass
            prober = threading.Thread(target=probe, daemon=True)
            prober.start()
            prober.join(2)
            free.append(not prober.is_alive())
            return build(payload)

        monkeypatch.setattr(archive, 'write_zip', probed)
        body = {'editorToken': editor.token, 'projectRevision': editor.revision,
            'documentRevision': editor.response['workspace']['documentRevision']}
        downloaded = client.post('/v2/projects/' + PROJECT + '/archive', json=body)
        assert downloaded.status_code == 200, downloaded.text[:400]
        assert free == [True] and 'manifest.json' in zipfile.ZipFile(io.BytesIO(downloaded.content)).namelist()


def test_a_png_with_a_bad_chunk_checksum_is_an_archive_image_mismatch():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buffer, format='PNG')
    raw = bytearray(buffer.getvalue())
    raw[raw.index(b'IDAT') + 5] ^= 0xFF
    broken = bytes(raw)
    digest = hashlib.sha256(broken).hexdigest()
    asset = LocalImageAsset(id='asset-1', sha256=digest, path='images/' + digest + '.png', mimeType='image/png',
        size=len(broken), width=4, height=4)
    with pytest.raises(ArchiveFailure) as refused:
        _verify_image(asset, broken)
    assert refused.value.code == 'ARCHIVE_IMAGE_MISMATCH'


def test_a_lost_history_file_gives_the_archive_its_own_code(tmp_path):
    with v2_app(tmp_path, [papers()]) as (client, application):
        repository = application.state.projects.repository
        target = repository.open(PROJECT).directory / 'workspace.json'
        value = json.loads(target.read_bytes())
        value['project']['importHistory'] = [{'operationId': 'operation-1', 'sha256': 'a' * 64}]
        target.write_text(json.dumps(value))
        target.chmod(0o600)
        editor = Editor(client, PROJECT)
        reply = client.post('/v2/projects/' + PROJECT + '/archive', json={'editorToken': editor.token,
            'projectRevision': editor.revision, 'documentRevision': editor.response['workspace']['documentRevision']})
        assert reply.status_code == 404 and reply.json()['error']['code'] == 'PROJECT_HISTORY_MISSING'
