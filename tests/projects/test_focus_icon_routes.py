"""Focus icon choice through the routes (D122): a pick is remembered, Undo and Redo move the memory with it, the
choices route lists the template's icons and serves their PNGs, and a row added later takes the remembered icon."""

import errno

import pytest

from tests.projects.support import Editor, v2_app
from tests.templates.test_focus_icon_choice import chosen, imported
from tests.templates.test_focus_panel import panel, technology


def command(editor, operation, record_id, identifier, values=None):
    return panel(editor.workspace(), operation, record_id, values=values, identifier=identifier).model_dump(
        mode='json', by_alias=True)


@pytest.mark.asyncio
async def test_a_pick_is_remembered_follows_undo_and_redo_and_an_added_row_takes_it(tmp_path):
    workspace, sources = await imported(tmp_path / 'import')
    with v2_app(tmp_path / 'app', [(workspace, sources)]) as (client, application):
        store = application.state.projects.icons
        editor = Editor(client, workspace.project_id)
        sql = technology(editor.workspace(), 'SQL')
        choices = editor.call('get', '/focus-icons')
        assert choices['rows'][sql.id]['remembered'] is None
        mysql = next(icon['sha256'] for icon in choices['icons'] if icon['id'] == 'mysql')
        served = client.get('/v1/rich/template-assets/' + mysql)
        assert served.status_code == 200 and served.content.startswith(b'\x89PNG')
        editor.edit(command(editor, 'set_focus_icon', sql.id, 'pick', {'icon': 'mysql'}))
        assert chosen(editor.workspace(), sql.id) == 'mysql' and store.load() == {'sql': 'mysql'}
        editor.step('undo', 'undo-pick')
        assert chosen(editor.workspace(), sql.id) is None and store.load() == {}
        editor.step('redo', 'redo-pick')
        assert store.load() == {'sql': 'mysql'}
        assert editor.call('get', '/focus-icons')['rows'][sql.id]['remembered'] == 'mysql'
        editor.edit(command(editor, 'remove_from_focus', sql.id, 'remove'))
        editor.edit(command(editor, 'add_to_focus', sql.id, 'add'))
        assert chosen(editor.workspace(), sql.id) == 'mysql'
        # An unknown icon keeps its refusal code for the panel; the memory stays.
        refused = editor.edit(command(editor, 'set_focus_icon', sql.id, 'bad', {'icon': 'keycloak'}), status=422)
        assert refused['error']['code'] == 'FOCUS_ICON_UNKNOWN' and store.load() == {'sql': 'mysql'}
        editor.edit(command(editor, 'set_focus_icon', sql.id, 'reset', {'icon': ''}))
        assert chosen(editor.workspace(), sql.id) is None and store.load() == {}


@pytest.mark.asyncio
async def test_a_failed_icon_memory_write_keeps_the_saved_pick(tmp_path, monkeypatch):
    workspace, sources = await imported(tmp_path / 'import')
    with v2_app(tmp_path / 'app', [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        sql = technology(editor.workspace(), 'SQL')
        def full(*_args, **_kwargs):
            raise OSError(errno.ENOSPC, 'no space')
        monkeypatch.setattr('packages.resume_core.focus_icons.atomic_write', full)
        editor.edit(command(editor, 'set_focus_icon', sql.id, 'pick', {'icon': 'mysql'}))
        assert chosen(editor.workspace(), sql.id) == 'mysql'
