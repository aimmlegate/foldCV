"""Image bytes by hash, a journal reference that survives a delete, and orphan sweep (plan SR04)."""

import hashlib
import io

from PIL import Image

from tests.projects.support import Editor, v2_app
from tests.projects.test_edit_routes import typing
from tests.templates.storage_fixtures import workspace as papers


PROJECT = 'template-project'


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (1, 1), color).save(buffer, format='PNG')
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return data, digest, 'images/' + digest + '.png'


def test_a_referenced_image_survives_undo_and_orphans_are_swept(tmp_path):
    data, digest, path = png('red')
    orphan, _orphan_digest, orphan_path = png('blue')
    with v2_app(tmp_path, [papers()]) as (client, application):
        repository = application.state.projects.repository
        editor = Editor(client, PROJECT)
        editor.edit(typing(editor, path, 'image-text', end=6))
        directory = repository.open(PROJECT).directory
        (directory / 'images').mkdir(mode=0o700)
        (directory / path).write_bytes(data)
        (directory / orphan_path).write_bytes(orphan)
        (directory / path).chmod(0o600)
        (directory / orphan_path).chmod(0o600)
        reply = client.get('/v2/projects/' + PROJECT + '/images/' + digest)
        assert reply.status_code == 200 and reply.content == data
        assert repository.sweep_assets(PROJECT) == [orphan_path.rsplit('/', 1)[-1]]
        assert (directory / path).is_file() and not (directory / orphan_path).is_file()
        editor.edit(typing(editor, 'Paper', 'image-clear', end=len(path)))
        assert repository.sweep_assets(PROJECT) == []
        assert (directory / path).is_file()
        editor.step('undo', 'undo-image', expected='action-image-clear')
        assert path in editor.response['workspace']['project']['document']['regions'][2]['blocks'][0]['content'][0]['text']
        missing = client.get('/v2/projects/' + PROJECT + '/images/' + 'b' * 64)
        assert missing.status_code == 404 and missing.json()['error']['code'] == 'IMAGE_NOT_FOUND'
