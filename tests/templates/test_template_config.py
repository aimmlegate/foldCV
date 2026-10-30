"""Settings template editor: read, check, save and reset the YAML of each template, and choose the default one."""

import ast
import base64
import json
from pathlib import Path
import shutil

import pytest
import yaml

from packages.resume_core.templates import focus
from packages.resume_core.templates.compiler import compile_bytes, compile_template
from packages.resume_core.templates.models import StoredTemplatePackage
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, TemplateStore
from resume_api.template_config import ID_CHANGED, REVISION_TAKEN, TemplateConfig
from resume_api.template_reasons import FALLBACK, FAMILIES, PREFIXES, REASONS, reason_text
from tests.templates.scripted_template_provider import ScriptedTemplateProvider
from tests.templates.test_template_import_app import app_client, upload
from tests.templates.test_template_store import GENERIC, SECOND, second_bundled

BUNDLED_TEXT = BUNDLED_TEMPLATE.read_text(encoding='utf-8')
BUNDLED_REVISION = compile_template(BUNDLED_TEMPLATE).revision


def revised(text, revision='9.0.1', name=None):
    text = text.replace(f'  revision: {BUNDLED_REVISION}\n', f'  revision: {revision}\n', 1)
    return text if name is None else text.replace('  name: Две колонки\n', f'  name: {name}\n', 1)


def test_an_empty_store_offers_the_bundled_yaml_unchanged(tmp_path):
    state = TemplateConfig(tmp_path).read(GENERIC)
    assert state['text'] == BUNDLED_TEXT and state['format'] == 'yaml'
    assert (state['bundled'], state['edited']) == (True, False) and state['package']['revision'] == BUNDLED_REVISION
    assert TemplateConfig(tmp_path).check(GENERIC, BUNDLED_TEXT)['valid'] is True


def test_a_changed_template_needs_a_new_revision_even_before_the_store_records_the_bundled_one(tmp_path):
    result = TemplateConfig(tmp_path).check(GENERIC, revised(BUNDLED_TEXT, BUNDLED_REVISION, 'Renamed'))
    assert result == {'schemaVersion': 1, 'valid': False, 'package': None,
        'error': {'path': '/template/revision', 'message': REVISION_TAKEN}}
    assert not (tmp_path / 'template-packages').exists()


def test_a_yaml_with_another_template_id_is_refused(tmp_path, monkeypatch):
    # Saving it would make it the current version of another template than the one being edited.
    second_bundled(tmp_path, monkeypatch)
    config = TemplateConfig(tmp_path / 'data')
    other = revised(BUNDLED_TEXT).replace(f'  id: {GENERIC}\n', f'  id: {SECOND}\n', 1)
    refused = {'path': '/template/id', 'message': ID_CHANGED.format(GENERIC)}
    assert config.check(GENERIC, other)['error'] == refused
    assert config.save(GENERIC, other)[1]['error'] == refused
    assert not (tmp_path / 'data').exists()


def test_save_is_the_current_version_of_its_template_and_reset_restores_the_bundled_one(tmp_path):
    config, edited = TemplateConfig(tmp_path), revised(BUNDLED_TEXT, name='Renamed')
    saved, refused = config.save(GENERIC, edited)
    assert refused is None and saved['text'] == edited and (saved['bundled'], saved['edited']) == (True, True)
    assert saved['package']['name'] == 'Renamed' and TemplateStore(tmp_path).active().revision == '9.0.1'
    # The same revision with other content is refused; the same content saves again without change.
    assert config.check(GENERIC, revised(BUNDLED_TEXT, name='Other'))['error']['path'] == '/template/revision'
    assert config.save(GENERIC, edited)[1] is None
    reset = config.reset(GENERIC)
    assert reset['edited'] is False and reset['text'] == BUNDLED_TEXT
    # 9.0.1 stays registered, so a different 9.0.1 is still refused after the reset.
    assert config.check(GENERIC, revised(BUNDLED_TEXT, name='Other'))['valid'] is False


@pytest.mark.parametrize(('text', 'path', 'fragment'), [
    ('schema_version: 3\ntemplate: [\n', '/', 'ошибка синтаксиса YAML'),
    (BUNDLED_TEXT.replace('  default_locale: ru\n', '  default_locale: ru\n  colour: red\n', 1), '/template/colour', 'лишнее поле'),
    (revised(BUNDLED_TEXT).replace('  name: Две колонки\n', '', 1), '/template/name', 'обязательное поле'),
    ('- just\n- a list\n', '/', 'набором полей'),
])
def test_invalid_text_reports_a_path_and_saves_nothing(tmp_path, text, path, fragment):
    config = TemplateConfig(tmp_path)
    result = config.check(GENERIC, text)
    assert result['valid'] is False and result['error']['path'] == path and fragment in result['error']['message']
    assert config.save(GENERIC, text) == (None, result)
    assert config.read(GENERIC)['edited'] is False


def _compiler_reasons():
    """Every reason the template code writes: (fixed text, whether a value follows it)."""
    for path in Path(compile_template.__code__.co_filename).parent.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            name = getattr(node.func, 'id', getattr(node.func, 'attr', '')) if isinstance(node, ast.Call) else ''
            if name in {'SchemaFailure', 'fail'} and len(node.args) >= 2:
                reason = node.args[1]
                if isinstance(reason, ast.Constant):
                    yield reason.value, False
                elif isinstance(reason, ast.BinOp):
                    while isinstance(reason, ast.BinOp):
                        reason = reason.left
                    yield reason.value, True


def test_every_compiler_reason_has_russian_text():
    missing = [text for text, dynamic in _compiler_reasons()
        if not (text in PREFIXES or text in FAMILIES if dynamic else text in REASONS)]
    assert not missing
    assert all(any('а' <= letter.lower() <= 'я' for letter in text)
        for text in [*REASONS.values(), *PREFIXES.values(), *FAMILIES.values()])


def test_a_reason_nobody_listed_stays_russian_and_no_class_name_reaches_the_editor():
    assert reason_text('unknown dependency') == 'неизвестная зависимость'
    assert reason_text('unknown reference: logo') == 'неизвестная ссылка: logo'
    assert reason_text('Input should be a valid string') == 'значение не подходит к этому полю'
    assert reason_text('something new') == reason_text('') == FALLBACK


def test_an_error_without_text_shows_no_class_name(tmp_path, monkeypatch):
    config = TemplateConfig(tmp_path)

    def broken(*_args, **_kwargs):
        raise ValueError()

    monkeypatch.setattr('resume_api.template_config.compile_bytes', broken)
    assert config.check(GENERIC, 'text')['error'] == {'path': '/', 'message': FALLBACK}


def test_assets_come_from_the_current_package_and_paths_stay_inside_the_template(tmp_path):
    folder = tmp_path / 'template'
    shutil.copytree(BUNDLED_TEMPLATE.parent, folder)
    (folder / 'assets/extra.png').write_bytes((folder / 'assets/foldcv.png').read_bytes())
    text = revised(BUNDLED_TEXT, '9.1.0').replace('\nassets:\n', '\nassets:\n  extra: assets/extra.png\n', 1)
    (folder / 'template.yaml').write_text(text, encoding='utf-8')
    TemplateStore(tmp_path / 'data').activate(compile_template(folder / 'template.yaml'))
    config = TemplateConfig(tmp_path / 'data')
    # extra.png exists only inside the saved package, not in the bundled folder.
    assert not (BUNDLED_TEMPLATE.parent / 'assets/extra.png').exists()
    assert config.check(GENERIC, revised(text, '9.1.0').replace('revision: 9.1.0', 'revision: 9.1.1'))['valid'] is True
    for path in ('assets/missing.png', '../../../requirements.txt'):
        result = config.check(GENERIC, text.replace('extra: assets/extra.png', f'extra: {path}').replace('revision: 9.1.0', 'revision: 9.1.2'))
        assert result['valid'] is False and result['error']['path'] == '/assets/' + path


@pytest.mark.asyncio
async def test_routes_save_one_template_for_projects_created_after_it(tmp_path):
    async with app_client(tmp_path, call_cap=4, provider=ScriptedTemplateProvider()) as (client, _app):
        listing = (await client.get('/v1/rich/template-config')).json()
        # The import fixture activated its own template, so that one is the default.
        default = listing['defaultId']
        state = (await client.get('/v1/rich/template-config/' + default)).json()
        before = (await upload(client)).json()['workspace']
        definition = json.loads(state['text'])
        definition['template']['revision'] = definition['template']['revision'] + '-edited'
        edited = json.dumps(definition, ensure_ascii=False)
        path = '/v1/rich/template-config/' + default
        assert (await client.post(path + '/check', json={'text': edited})).json()['valid'] is True
        broken = await client.put(path, json={'text': '{"template": 1}'})
        assert broken.status_code == 422 and broken.json()['valid'] is False
        saved = await client.put(path, json={'text': edited})
        assert saved.status_code == 200, saved.text
        status = (await client.get('/v1/rich/template-import')).json()
        assert status['defaultId'] == default
        [entry] = [value for value in status['templates'] if value['id'] == default]
        assert entry['revision'] == definition['template']['revision'] and entry['bundled'] is False
        after = (await upload(client)).json()['workspace']
        reread = (await client.post('/v2/projects/' + before['projectId'] + '/open', json={})).json()['response']['workspace']
        assert reread['preDraft']['templatePackage']['packageHash'] == state['package']['packageHash']
        assert after['preDraft']['templatePackage']['packageHash'] == entry['packageHash'] != state['package']['packageHash']
        too_long = await client.post(path + '/check', json={'text': 'x' * (1024 * 1024 + 1)})
        assert too_long.status_code == 413 and too_long.json()['error']['code'] == 'INPUT_TOO_LARGE'
        # Only a template the app ships can go back to its bundled file.
        refused = await client.post(path + '/reset', json={})
        assert refused.status_code == 404 and refused.json()['error']['code'] == 'TEMPLATE_NOT_FOUND'
        reset = await client.post('/v1/rich/template-config/' + GENERIC + '/reset', json={})
        assert reset.status_code == 200 and reset.json()['edited'] is False


@pytest.mark.asyncio
async def test_routes_save_and_reset_one_template_and_keep_the_default_until_it_is_chosen(tmp_path, monkeypatch):
    second_bundled(tmp_path, monkeypatch)
    async with app_client(tmp_path, call_cap=4, provider=ScriptedTemplateProvider()) as (client, _app):
        listing = (await client.get('/v1/rich/template-config')).json()
        default = listing['defaultId']
        assert [value['id'] for value in listing['templates']] == [GENERIC, SECOND, default]
        state = (await client.get('/v1/rich/template-config/' + SECOND)).json()
        edited = state['text'].replace(f'  revision: {BUNDLED_REVISION}\n', '  revision: 9.2.0\n', 1)
        saved = await client.put('/v1/rich/template-config/' + SECOND, json={'text': edited})
        assert saved.status_code == 200 and (saved.json()['edited'], saved.json()['package']['revision']) == (True, '9.2.0')
        listing = (await client.get('/v1/rich/template-config')).json()
        assert listing['defaultId'] == default
        assert [value['edited'] for value in listing['templates']] == [False, True, True]
        chosen = await client.put('/v1/rich/template-default', json={'templateId': SECOND})
        assert chosen.status_code == 200 and chosen.json()['defaultId'] == SECOND
        created = (await upload(client)).json()['workspace']['preDraft']['templatePackage']
        assert (created['id'], created['revision']) == (SECOND, '9.2.0')
        reset = await client.post('/v1/rich/template-config/' + SECOND + '/reset', json={})
        assert reset.json()['text'] == state['text'] and reset.json()['edited'] is False
        assert (await client.get('/v1/rich/template-import')).json()['defaultId'] == SECOND
        for method, path, body in [('GET', '/v1/rich/template-config/missing', None),
                ('POST', '/v1/rich/template-config/missing/check', {'text': edited}),
                ('PUT', '/v1/rich/template-config/missing', {'text': edited}),
                ('POST', '/v1/rich/template-config/missing/reset', {}),
                ('PUT', '/v1/rich/template-default', {'templateId': 'missing'})]:
            reply = await client.request(method, path, json=body)
            assert (reply.status_code, reply.json()['error']['code']) == (404, 'TEMPLATE_NOT_FOUND'), path
        assert (await client.get('/v1/rich/template-import')).json()['defaultId'] == SECOND


def edited(change, revision='9.0.2'):
    config = yaml.safe_load(BUNDLED_TEXT)
    config['template']['revision'] = revision
    change(config)
    return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)


def block(config, identifier):
    return next(value for value in config['blocks'] if value['id'] == identifier)


def operation(config, identifier):
    return next(value for value in config['operations'] if value['id'] == identifier)


def logo_as_catalog(config):
    config['style']['focus']['icon_catalog'] = config['style']['header']['logo']['asset']


def unknown_operation(config):
    config['operations'].append({'id': 'keep', 'kind': 'preserve_stated_text', 'parameters': {}, 'inputs': ['source:all']})


def skills_without_their_groups(config):
    operation(config, 'technical-skills')['inputs'] = ['projects']


def derived_from_another_operation(config):
    block(config, 'other_projects')['operation'] = 'source-periods'


def compact_on_another_field(config):
    config['content_definitions']['names'] = {'names': 'texts'}
    compact = block(config, 'other_projects')
    compact.update(schema='names', facts={'other_projects': ['names/*=items.*']})
    compact['view']['nodes'][0]['field'] = '/names'


def view_without_a_style(config):
    block(config, 'location')['view'] = {'title': {'ru': 'X'}, 'nodes': []}


def anyof_true(config):
    next(value for value in config['fact_types'] if value['id'] == 'identity')['fields']['name'] = {'anyOf': [True]}


@pytest.mark.parametrize(('change', 'path', 'fragment'), [
    (logo_as_catalog, '/style/focus/icon_catalog', 'unreadable'),
    (unknown_operation, '/operations/keep', 'registered'),
    (skills_without_their_groups, '/operations/technical-skills', 'inputs'),
    (derived_from_another_operation, '/blocks/other_projects/operation', 'partition_employment'),
    (compact_on_another_field, '/blocks/other_projects/view', '/items'),
    (view_without_a_style, '/blocks/location/view', 'fallback_style'),
    (anyof_true, '/name', 'anyOf'),
])
def test_check_reports_what_every_import_would_refuse_or_lose_with_its_location(tmp_path, change, path, fragment):
    config = TemplateConfig(tmp_path)
    result = config.check(GENERIC, edited(change))
    assert (result['valid'], result['error']['path']) == (False, path) and fragment in result['error']['message']
    assert config.save(GENERIC, edited(change))[1]['error'] == result['error']
    assert not (tmp_path / 'template-packages').exists()


def test_stored_packages_keep_opening_without_the_new_package_checks(tmp_path, monkeypatch):
    # Only compile_bytes refuses these; verification of a stored package never runs the checks.
    from packages.resume_core.templates import compiler
    from packages.resume_core.templates.store import verify_package
    monkeypatch.setattr(compiler, 'check_runs', lambda _definition: None)
    package = compile_bytes(edited(unknown_operation).encode(), BUNDLED_TEMPLATE.parent)
    monkeypatch.undo()
    assert verify_package(package) is package


def test_an_empty_asset_is_refused_at_compile(tmp_path):
    (tmp_path / 'empty.txt').write_bytes(b'')
    captured = {asset.path: base64.b64decode(asset.bytes_base64) for asset in compile_template(BUNDLED_TEMPLATE).assets}
    raw = edited(lambda config: config['assets'].update(nothing={'path': 'empty.txt'})).encode()
    with pytest.raises(SchemaFailure, match='/assets/empty.txt: asset is empty'):
        compile_bytes(raw, tmp_path, assets=captured)
    assert all(StoredTemplatePackage.model_validate(compile_template(BUNDLED_TEMPLATE)).assets)


def test_a_text_only_change_is_what_save_returns_and_reset_drops_it(tmp_path):
    config, commented = TemplateConfig(tmp_path), BUNDLED_TEXT + '\n# my note\n'
    saved, refused = config.save(GENERIC, commented)
    assert refused is None and saved['text'] == commented
    assert saved['package']['packageHash'] == compile_template(BUNDLED_TEMPLATE).package_hash
    # The text differs from the shipped one, so Reset stays offered.
    assert saved['edited'] is True and config.read(GENERIC) == saved
    assert next(item for item in config.catalog()['templates'] if item['id'] == GENERIC)['edited'] is True
    assert config.reset(GENERIC)['text'] == BUNDLED_TEXT
    assert config.read(GENERIC)['edited'] is False


def test_saving_the_same_package_again_keeps_the_latest_text_of_a_custom_version(tmp_path):
    config, first = TemplateConfig(tmp_path), revised(BUNDLED_TEXT)
    assert config.save(GENERIC, first)[0]['text'] == first
    assert config.save(GENERIC, first + '# second\n')[0]['text'] == first + '# second\n'
    # Text saved before this store kept one beside the package reads from the package itself.
    package, _bundled = config.store.versions(GENERIC)
    (config.store.root / package.package_hash / 'original.json').unlink()
    assert config.read(GENERIC)['text'] == first


@pytest.mark.asyncio
async def test_a_catalog_captured_unreadable_leaves_focus_rows_as_text(tmp_path, monkeypatch):
    from packages.resume_core.templates.presentation_plan import editor_plan
    from tests.templates.test_focus_icons import published
    _fixture, workspace, _originals = await published(tmp_path)
    def unreadable(_package):
        raise ValueError('focus icon catalog is unreadable')
    monkeypatch.setattr(focus, '_CATALOGS', {})
    monkeypatch.setattr(focus, 'icon_catalog', unreadable)
    plan = editor_plan(workspace.project)
    rows = [entry['focus'] for entry in plan['blocks'].values() if 'focus' in entry]
    assert rows and all(row['icon'] is None for row in rows) and 'icons' not in plan.get('focusPanel', {})
