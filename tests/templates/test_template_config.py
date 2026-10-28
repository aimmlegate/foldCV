"""Settings template editor: read, check, save and reset the YAML that new imports use."""

import json
import shutil

import pytest

from packages.resume_core.templates.compiler import compile_template
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, TemplateStore
from resume_api.template_config import REVISION_TAKEN, TemplateConfig
from tests.templates.scripted_template_provider import ScriptedTemplateProvider
from tests.templates.test_template_import_app import app_client, upload

BUNDLED_TEXT = BUNDLED_TEMPLATE.read_text(encoding='utf-8')
BUNDLED_REVISION = compile_template(BUNDLED_TEMPLATE).revision


def revised(text, revision='9.0.1', name=None):
    text = text.replace(f'  revision: {BUNDLED_REVISION}\n', f'  revision: {revision}\n', 1)
    return text if name is None else text.replace('  name: Две колонки\n', f'  name: {name}\n', 1)


def test_an_empty_store_offers_the_bundled_yaml_unchanged(tmp_path):
    state = TemplateConfig(tmp_path).read()
    assert state['text'] == BUNDLED_TEXT and state['format'] == 'yaml' and state['bundled'] is True
    assert state['package']['revision'] == BUNDLED_REVISION
    assert TemplateConfig(tmp_path).check(BUNDLED_TEXT)['valid'] is True


def test_a_changed_template_needs_a_new_revision_even_before_the_store_records_the_bundled_one(tmp_path):
    result = TemplateConfig(tmp_path).check(revised(BUNDLED_TEXT, BUNDLED_REVISION, 'Renamed'))
    assert result == {'schemaVersion': 1, 'valid': False, 'package': None,
        'error': {'path': '/template/revision', 'message': REVISION_TAKEN}}
    assert not (tmp_path / 'template-packages').exists()


def test_save_activates_for_new_imports_and_reset_restores_the_bundled_package(tmp_path):
    config, edited = TemplateConfig(tmp_path), revised(BUNDLED_TEXT, name='Renamed')
    saved, refused = config.save(edited)
    assert refused is None and saved['text'] == edited and saved['bundled'] is False
    assert saved['package']['name'] == 'Renamed' and TemplateStore(tmp_path).active().revision == '9.0.1'
    # The same revision with other content is refused; the same content saves again without change.
    assert config.check(revised(BUNDLED_TEXT, name='Other'))['error']['path'] == '/template/revision'
    assert config.save(edited)[1] is None
    reset = config.reset()
    assert reset['bundled'] is True and reset['text'] == BUNDLED_TEXT
    # 9.0.1 stays registered, so a different 9.0.1 is still refused after the reset.
    assert config.check(revised(BUNDLED_TEXT, name='Other'))['valid'] is False


@pytest.mark.parametrize(('text', 'path', 'fragment'), [
    ('schema_version: 3\ntemplate: [\n', '/', 'invalid YAML'),
    (BUNDLED_TEXT.replace('  default_locale: ru\n', '  default_locale: ru\n  colour: red\n', 1), '/template/colour', 'Extra inputs'),
    (revised(BUNDLED_TEXT).replace('  name: Две колонки\n', '', 1), '/template/name', 'Field required'),
    ('- just\n- a list\n', '/', 'object'),
])
def test_invalid_text_reports_a_path_and_saves_nothing(tmp_path, text, path, fragment):
    config = TemplateConfig(tmp_path)
    result = config.check(text)
    assert result['valid'] is False and result['error']['path'] == path and fragment in result['error']['message']
    assert config.save(text) == (None, result)
    assert config.read()['bundled'] is True


def test_assets_come_from_the_active_package_and_paths_stay_inside_the_template(tmp_path):
    folder = tmp_path / 'template'
    shutil.copytree(BUNDLED_TEMPLATE.parent, folder)
    (folder / 'assets/extra.png').write_bytes((folder / 'assets/foldcv.png').read_bytes())
    text = revised(BUNDLED_TEXT, '9.1.0').replace('\nassets:\n', '\nassets:\n  extra: assets/extra.png\n', 1)
    (folder / 'template.yaml').write_text(text, encoding='utf-8')
    TemplateStore(tmp_path / 'data').activate(compile_template(folder / 'template.yaml'))
    config = TemplateConfig(tmp_path / 'data')
    # extra.png exists only inside the active package, not in the bundled folder.
    assert not (BUNDLED_TEMPLATE.parent / 'assets/extra.png').exists()
    assert config.check(revised(text, '9.1.0').replace('revision: 9.1.0', 'revision: 9.1.1'))['valid'] is True
    for path in ('assets/missing.png', '../../../requirements.txt'):
        result = config.check(text.replace('extra: assets/extra.png', f'extra: {path}').replace('revision: 9.1.0', 'revision: 9.1.2'))
        assert result['valid'] is False and result['error']['path'] == '/assets/' + path


@pytest.mark.asyncio
async def test_routes_activate_a_new_revision_only_for_projects_created_after_it(tmp_path):
    async with app_client(tmp_path, call_cap=4, provider=ScriptedTemplateProvider()) as (client, _app):
        state = (await client.get('/v1/rich/template-config')).json()
        before = (await upload(client)).json()['workspace']
        definition = json.loads(state['text'])
        definition['template']['revision'] = definition['template']['revision'] + '-edited'
        edited = json.dumps(definition, ensure_ascii=False)
        assert (await client.post('/v1/rich/template-config/check', json={'text': edited})).json()['valid'] is True
        broken = (await client.put('/v1/rich/template-config', json={'text': '{"template": 1}'}))
        assert broken.status_code == 422 and broken.json()['valid'] is False
        saved = await client.put('/v1/rich/template-config', json={'text': edited})
        assert saved.status_code == 200, saved.text
        status = (await client.get('/v1/rich/template-import')).json()
        assert status['package']['revision'] == definition['template']['revision']
        after = (await upload(client)).json()['workspace']
        reread = (await client.post('/v2/projects/' + before['projectId'] + '/open', json={})).json()['response']['workspace']
        assert reread['preDraft']['templatePackage']['packageHash'] == state['package']['packageHash']
        assert after['preDraft']['templatePackage']['packageHash'] == status['package']['packageHash'] != state['package']['packageHash']
        too_long = await client.post('/v1/rich/template-config/check', json={'text': 'x' * (1024 * 1024 + 1)})
        assert too_long.status_code == 413 and too_long.json()['error']['code'] == 'INPUT_TOO_LARGE'
        reset = await client.post('/v1/rich/template-config/reset', json={})
        assert reset.status_code == 200 and reset.json()['bundled'] is True
