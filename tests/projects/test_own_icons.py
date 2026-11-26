"""Own Focus icons (D187): the app's library (add, list, delete, a damaged library), a résumé's own copy that stays after
the library entry goes, Undo and Redo through the project history, and the icon in the DOCX. The icons are drawn here."""

import base64
import zipfile
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from packages.resume_core.repository.own_icons import OwnIconStore
from tests.projects.support import Editor, v2_app
from tests.templates.test_focus_icon_choice import chosen, imported
from tests.templates.test_focus_panel import panel, technology


def icon_png(color=(200, 60, 60, 255)):
    image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle([24, 24, 232, 232], radius=40, fill=color)
    raw = BytesIO()
    image.save(raw, format='PNG')
    return raw.getvalue()


def test_the_library_adds_lists_deletes_and_a_damaged_index_lists_nothing(tmp_path):
    store = OwnIconStore(tmp_path)
    first = store.add('Наш сервис', icon_png())
    second = store.add('Наш сервис', icon_png((60, 60, 200, 255)))
    assert first['id'] != second['id'] and [icon['name'] for icon in store.list()] == ['Наш сервис', 'Наш сервис']
    assert store.get(first['id']).name == 'Наш сервис'
    with pytest.raises(ValueError, match='IMAGE_SIZE'):
        store.add('Мелкая', icon_png()[:0] or _small())
    with pytest.raises(ValueError, match='ICON_NAME_INVALID'):
        store.add('   ', icon_png())
    assert store.delete(first['id']) and not store.delete(first['id']) and len(store.list()) == 1
    (tmp_path / 'own-icons' / 'index.json').write_text('{not json')
    assert store.list() == [] and store.get(second['id']) is None


def _small():
    raw = BytesIO()
    Image.new('RGBA', (64, 64), (0, 0, 0, 0)).save(raw, format='PNG')
    return raw.getvalue()


def command(editor, operation, record_id, identifier, values=None):
    return panel(editor.workspace(), operation, record_id, values=values, identifier=identifier).model_dump(mode='json', by_alias=True)


@pytest.mark.asyncio
async def test_a_resume_keeps_its_copy_of_an_own_icon_through_delete_history_and_export(tmp_path):
    workspace, sources = await imported(tmp_path / 'import')
    with v2_app(tmp_path / 'app', [(workspace, sources)]) as (client, application):
        editor = Editor(client, workspace.project_id)
        added = client.post('/v2/icons', json={'name': 'SQL своя', 'image': base64.b64encode(icon_png()).decode()})
        assert added.status_code == 201, added.text[:300]
        icon = added.json()['icon']
        choices = editor.call('get', '/focus-icons')
        assert [entry['id'] for entry in choices['own']] == [icon['id']]
        assert client.get('/v1/rich/template-assets/' + icon['sha256']).status_code == 200
        sql = technology(editor.workspace(), 'SQL')
        editor.edit(command(editor, 'set_focus_icon', sql.id, 'pick-own', {'icon': icon['id']}))
        assert chosen(editor.workspace(), sql.id) == icon['id']
        assert [value.id for value in editor.workspace().project.own_icons] == [icon['id']]
        # The library entry goes; the résumé still shows and exports its copy.
        assert client.delete('/v2/icons/' + icon['id']).status_code == 200
        assert client.get('/v2/icons').json()['icons'] == []
        plan = editor.call('post', '/open', {})['response']['presentation']['editor']
        editor = Editor(client, workspace.project_id)
        assert icon['id'] in plan.get('iconFiles', {}) or icon['id'] in plan.get('icons', [])
        reply = client.post('/v2/projects/' + workspace.project_id + '/export', json={'schemaVersion': 1,
            'snapshot': editor.response['snapshot'], 'editorToken': editor.token})
        assert reply.status_code == 200, reply.text[:300]
        media = [name for name in zipfile.ZipFile(BytesIO(reply.content)).namelist() if name.startswith('word/media/')]
        assert media
        editor = Editor(client, workspace.project_id)
        # Undo takes the choice and the copy back in one step; Redo puts both again.
        editor.step('undo', 'undo-own')
        assert chosen(editor.workspace(), sql.id) is None and editor.workspace().project.own_icons == []
        editor.step('redo', 'redo-own')
        assert chosen(editor.workspace(), sql.id) == icon['id'] and len(editor.workspace().project.own_icons) == 1
        # An own icon the library does not hold any more cannot be chosen anew.
        refused = editor.edit(command(editor, 'set_focus_icon', technology(editor.workspace(), 'Python').id, 'pick-gone',
            {'icon': 'own-' + '0' * 24}), status=422)
        assert refused['error']['code'] == 'FOCUS_ICON_UNKNOWN'
