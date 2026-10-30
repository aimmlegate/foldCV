"""A Focus row's icon chosen from the template's icons (D122): the editor and the DOCX show it, Undo takes it back, and
rows added later, from the facts panel or by an import, take the icon remembered for their name."""

import errno
import hashlib
import json
import os

from pydantic import ValidationError
import pytest

from packages.resume_core import focus_icons
from packages.resume_core.focus_icons import FocusIconStore
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.storage import StorageFailure
from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_panel_focus import icon_changes, icon_choices
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.focus import catalog_for, remembered_catalog, remembered_icon
from packages.resume_core.templates.presentation_plan import editor_plan
from tests.templates.employment_fixtures import employment_source
from tests.templates.template_runtime_fixtures import EmploymentFixture
from tests.templates.test_captured_docx import parts
from tests.templates.test_focus_panel import FOCUS, applied, panel, technology, technology_package, undone
from tests.templates.test_template_preparation import response
from tests.templates.test_template_view_adapters import render, scripted


async def imported(tmp_path, remembered=None):
    """The synthetic Focus import (Python, SQL, UnknownTool); its document is assembled with `remembered` icons."""
    class Remembering(EmploymentFixture):
        def assemble(self, before, operation):
            return assemble_template(before, operation, remembered=remembered)
    src, raw = employment_source('F06')
    fixture = Remembering(tmp_path, captured=technology_package(), src=src, original_bytes=raw,
        scripted=scripted(src, FOCUS, [{'name': 'Portfolio', 'url': 'https://example.org'}]), cap=8, fallback=False)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved'
    return fixture.current(), {src.id: raw}


def icons(workspace):
    return [entry['focus']['icon'] for entry in editor_plan(workspace.project)['blocks'].values() if entry.get('focus')]


def chosen(workspace, record_id):
    return next(block for block in workspace.project.document.blocks()
        if block.type == 'section' and block.props.record_id == record_id).props.icon


@pytest.mark.asyncio
async def test_a_chosen_icon_shows_in_the_editor_and_the_docx_and_undo_takes_it_back(tmp_path):
    before, _sources = await imported(tmp_path)
    automatic = icons(before)
    assert automatic[0] == 'python' and automatic[1].startswith('initial-')
    sql = technology(before, 'SQL')
    after, result = applied(before, panel(before, 'set_focus_icon', sql.id, values={'icon': 'mysql'}))
    assert icons(after) == [automatic[0], 'mysql', automatic[2]]
    png = catalog_for(after.project.template_package).files['mysql'].sha256
    assert editor_plan(after.project)['iconFiles']['mysql'] == png
    media = {hashlib.sha256(data).hexdigest() for name, data in parts(render(after, tmp_path)).items()
        if name.startswith('word/media/')}
    assert png in media
    restored = undone(before, after, result)
    assert icons(restored) == automatic and chosen(restored, sql.id) is None


@pytest.mark.asyncio
async def test_a_reset_returns_to_the_templates_choice_and_wrong_choices_are_refused(tmp_path):
    before, _sources = await imported(tmp_path)
    python = technology(before, 'Python')
    picked, _ = applied(before, panel(before, 'set_focus_icon', python.id, values={'icon': 'django'}))
    assert icons(picked)[0] == 'django'
    reset, _ = applied(picked, panel(picked, 'set_focus_icon', python.id, values={'icon': ''}, identifier='reset'))
    assert icons(reset)[0] == 'python' and chosen(reset, python.id) is None
    # The same choice again changes nothing.
    assert prepare_edit(response(reset), panel(reset, 'set_focus_icon', python.id, values={'icon': ''},
        identifier='same')).mutation is None
    with pytest.raises(ValueError, match='FOCUS_ICON_UNKNOWN'):
        prepare_edit(response(before), panel(before, 'set_focus_icon', python.id, values={'icon': 'keycloak'},
            identifier='unknown'))
    removed, _ = applied(before, panel(before, 'remove_from_focus', python.id, identifier='remove'))
    with pytest.raises(ValueError, match='FOCUS_SCOPE_INVALID'):
        prepare_edit(response(removed), panel(removed, 'set_focus_icon', python.id, values={'icon': 'django'},
            identifier='gone'))
    # The command names the icon and nothing else.
    for values in ({}, {'icon': 'django', 'experience': '3'}, {'icon': 'x' * 129}):
        with pytest.raises(ValidationError):
            panel(before, 'set_focus_icon', python.id, values=values, identifier='shape')


@pytest.mark.asyncio
async def test_a_chosen_icon_stays_through_a_years_edit_a_move_and_an_undone_removal(tmp_path):
    before, _sources = await imported(tmp_path)
    sql, python = technology(before, 'SQL'), technology(before, 'Python')
    picked, _ = applied(before, panel(before, 'set_focus_icon', sql.id, values={'icon': 'mysql'}))
    years, _ = applied(picked, panel(picked, 'edit', sql.id, values={'experience': '3'}, identifier='years'))
    moved, _ = applied(years, panel(years, 'move_focus', sql.id, before_id=python.id, identifier='move'))
    assert icons(moved)[0] == 'mysql'
    removed, result = applied(moved, panel(moved, 'remove_from_focus', sql.id, identifier='remove'))
    assert 'mysql' not in icons(removed)
    assert icons(undone(moved, removed, result))[0] == 'mysql'


@pytest.mark.asyncio
async def test_an_added_row_takes_the_icon_remembered_for_its_name(tmp_path):
    before, _sources = await imported(tmp_path)
    sql = technology(before, 'SQL')
    removed, _ = applied(before, panel(before, 'remove_from_focus', sql.id))
    request = panel(removed, 'add_to_focus', sql.id, identifier='add')
    def added(remembered):
        result = prepare_edit(response(removed), request, remembered=remembered)
        return chosen(apply_rich_mutation(removed, result.mutation)[0], sql.id)
    assert added(remembered_catalog({'sql': 'mysql'})) == 'mysql'
    # Nothing remembered, or an icon this template does not have: the template chooses.
    assert added(None) is None and added(remembered_catalog({'sql': 'keycloak'})) is None


def test_remembered_names_match_versions_and_catalog_technologies_and_the_latest_choice_wins():
    catalog = catalog_for(technology_package())
    remembered = remembered_catalog({'python': 'django', 'postgres': 'mysql', 'postgresql': 'sqlite'})
    assert remembered_icon(catalog, remembered, 'Python 3.12') == 'django'
    assert remembered_icon(catalog, remembered, 'PostgreSQL 15') == 'sqlite'
    # A misspelling the technology catalog knows resolves to PostgreSQL, whose latest choice wins.
    assert remembered_icon(catalog, remembered, 'Postges') == 'sqlite'
    assert remembered_icon(catalog, remembered, 'Go') is None and remembered_icon(catalog, None, 'Python') is None


@pytest.mark.asyncio
async def test_an_import_gives_its_rows_the_remembered_icons_its_template_has(tmp_path):
    workspace, _sources = await imported(tmp_path, remembered_catalog({'unknowntool': 'docker', 'sql': 'keycloak'}))
    automatic = icons(workspace)
    assert automatic[0] == 'python' and automatic[1].startswith('initial-') and automatic[2] == 'docker'
    assert chosen(workspace, technology(workspace, 'UnknownTool').id) == 'docker'
    assert chosen(workspace, technology(workspace, 'SQL').id) is None


@pytest.mark.asyncio
async def test_icon_changes_follow_a_pick_its_undo_and_a_reset_but_not_added_rows(tmp_path):
    before, _sources = await imported(tmp_path)
    sql = technology(before, 'SQL')
    picked, result = applied(before, panel(before, 'set_focus_icon', sql.id, values={'icon': 'mysql'}))
    assert icon_changes(before.project, picked.project) == [('SQL', 'mysql')]
    assert icon_changes(picked.project, undone(before, picked, result).project) == [('SQL', None)]
    removed, _ = applied(picked, panel(picked, 'remove_from_focus', sql.id, identifier='remove'))
    again = apply_rich_mutation(removed, prepare_edit(response(removed), panel(removed, 'add_to_focus', sql.id,
        identifier='add'), remembered=remembered_catalog({'sql': 'mysql'})).mutation)[0]
    assert icon_changes(picked.project, removed.project) == [] and icon_changes(removed.project, again.project) == []


@pytest.mark.asyncio
async def test_choices_list_every_icon_with_its_names_and_each_rows_own_and_remembered_icon(tmp_path):
    before, _sources = await imported(tmp_path)
    python, sql, tool = (technology(before, name) for name in ('Python', 'SQL', 'UnknownTool'))
    value, assets = icon_choices(before.project, remembered_catalog({'unknowntool': 'docker'}))
    assert len(value['icons']) == 657 and value['icons'][0]['id'] == 'aarch64'
    assert next(icon for icon in value['icons'] if icon['id'] == 'mssql')['names'] == ['microsoft sql server', 'msql', 'mssql']
    rows = value['rows']
    assert rows[python.id] == {'automatic': {'id': 'python', 'sha256': value['icons'][[icon['id'] for icon in
        value['icons']].index('python')]['sha256']}, 'remembered': None}
    assert rows[sql.id]['automatic']['id'].startswith('initial-') and rows[tool.id]['remembered'] == 'docker'
    assert {asset.sha256 for asset in assets} == {icon['sha256'] for icon in value['icons']} | {
        row['automatic']['sha256'] for row in rows.values()}


def test_the_store_keeps_the_latest_choice_last_and_forgets_a_reset(tmp_path):
    store = FocusIconStore(tmp_path)
    assert store.load() == {}
    store.update([('MS  SQL', 'mssql'), ('Go', 'golang')])
    store.update([('ms sql', 'azuresqldatabase')])
    assert list(store.load().items()) == [('go', 'golang'), ('ms sql', 'azuresqldatabase')]
    assert os.stat(store.path).st_mode & 0o777 == 0o600
    store.update([('GO', None), ('', 'go'), ('Rust', '../rust')])
    assert store.load() == {'ms sql': 'azuresqldatabase'}


def test_an_unreadable_store_remembers_nothing_and_the_next_choice_replaces_it(tmp_path):
    store = FocusIconStore(tmp_path)
    store.path.write_text('{"schemaVersion": 1, "names": {"go": "golang"')
    os.chmod(store.path, 0o600)
    assert store.load() == {}
    store.update([('Go', 'golang')])
    assert store.load() == {'go': 'golang'}
    # A file of another owner's permissions is not read either; entries that are not valid are left out.
    store.path.write_text(json.dumps({'schemaVersion': 1, 'names': {'go': 'golang', 'Rust': 'rust', 'c': '../x'}}))
    os.chmod(store.path, 0o644)
    assert store.load() == {}
    os.chmod(store.path, 0o600)
    assert store.load() == {'go': 'golang'}


def test_the_store_keeps_the_newest_choices_within_its_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(focus_icons, 'MAX_NAMES', 3)
    store = FocusIconStore(tmp_path / 'count')
    store.update([(name, 'golang') for name in ('a', 'b', 'c', 'd', 'e')])
    assert list(store.load()) == ['c', 'd', 'e']
    # The file stays readable: past its byte limit the oldest choices go too.
    monkeypatch.setattr(focus_icons, 'MAX_BYTES', len(store.path.read_bytes()) - 1)
    small = FocusIconStore(tmp_path / 'bytes')
    small.update([('f', 'golang'), ('g', 'golang'), ('h', 'golang')])
    assert list(small.load()) == ['g', 'h']


def test_a_reset_forgets_every_remembered_name_its_row_would_match(tmp_path):
    store = FocusIconStore(tmp_path)
    store.update([('Python 3.12', 'rust'), ('K8s', 'docker'), ('Go', 'mysql')])
    store.update([('Python', None), ('Kubernetes', None)])
    assert store.load() == {'go': 'mysql'}
    store.update([('Python', 'rust')])
    store.update([('Python 3.12', None)])
    assert store.load() == {'go': 'mysql'}


def test_a_deeply_nested_store_reads_as_empty(tmp_path):
    (tmp_path / 'focus-icons.json').write_bytes(b'[' * 200000)
    assert FocusIconStore(tmp_path).load() == {}


def test_a_failing_disk_never_escapes_the_store_as_a_plain_os_error(tmp_path, monkeypatch):
    def full(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, 'no space')
    store = FocusIconStore(tmp_path)
    monkeypatch.setattr(focus_icons, 'atomic_write', full)
    with pytest.raises(StorageFailure):
        store.update([('Python', 'rust')])
    monkeypatch.setattr(focus_icons, 'locked_root', full)
    assert store.load() == {}
