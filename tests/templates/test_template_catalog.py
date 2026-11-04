"""Template catalog: copies under new ids, unsaved new texts, and deletion that leaves projects their captured copy."""

import json

import pytest
import yaml

from packages.resume_core.templates.compiler import compile_template
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, TemplateRefused, TemplateStore, UnknownTemplate
from resume_api.template_config import (NO_HEADER, REVISION_TAKEN, TemplateConfig, new_id, next_revision, slug,
    stated_name, with_header)
from tests.templates.scripted_template_provider import ScriptedTemplateProvider
from tests.templates.test_template_import_app import app_client, upload
from tests.templates.test_template_store import GENERIC

BUNDLED_TEXT = BUNDLED_TEMPLATE.read_text(encoding='utf-8')


@pytest.mark.parametrize(('name', 'expected'), [('Мой', 'moy'), ('Две колонки 2026', 'dve-kolonki-2026'),
    ('Щука и Ёж!', 'shchuka-i-ezh'), ('  --My CV--  ', 'my-cv'), ('Объём', 'obem'), ('日本', ''), ('', '')])
def test_a_name_becomes_an_ascii_slug(name, expected):
    assert slug(name) == expected


def test_a_taken_id_gets_the_next_suffix_and_a_name_without_letters_a_number():
    assert new_id('Мой', {GENERIC}) == 'custom-moy'
    assert new_id('Мой', {'custom-moy', 'custom-moy-2'}) == 'custom-moy-3'
    assert new_id('!!!', set()) == 'custom-1' and new_id('日本', {'custom-1', 'custom-2'}) == 'custom-3'
    assert len(new_id('я' * 300, set())) <= 7 + 60


def test_the_header_lines_change_and_comments_and_the_short_form_stay():
    text = with_header(BUNDLED_TEXT, id='custom-moy', name='Мой', revision='1.0.0')
    head = text.splitlines()[:7]
    assert head == ['# yaml-language-server: $schema=../../contracts/template-source.schema.json', 'schema_version: 4',
        'template:', '  id: custom-moy', '  revision: 1.0.0', '  name: "Мой"', '  default_locale: ru']
    assert text.splitlines()[7:] == BUNDLED_TEXT.splitlines()[7:]
    # A key the mapping lacks is added at its indentation; nested keys named id are left alone.
    assert with_header('template:\n    id: a\n    extra:\n      name: inner\n', id='b', name='N', revision='1.0.0') == (
        'template:\n    revision: 1.0.0\n    name: "N"\n    id: b\n    extra:\n      name: inner\n')
    # Only the given lines change.
    raised = with_header(BUNDLED_TEXT, revision='9.9.9').splitlines()
    assert raised[4] == '  revision: 9.9.9' and raised[:4] + raised[5:] == BUNDLED_TEXT.splitlines()[:4] + BUNDLED_TEXT.splitlines()[5:]


def test_the_header_values_change_in_any_scalar_form_and_a_text_without_a_header_is_told_apart():
    # A folded or quoted value, a trailing comment and an empty value: the value changes, the rest of the line stays.
    folded = 'template:\n  id: generic  # keep\n  name: >-\n    Мой\n    шаблон\n  revision: "1.0.0"\n  default_locale: ru\n'
    assert with_header(folded, name='Мой шаблон', revision='1.0.1') == (
        'template:\n  id: generic  # keep\n  name: "Мой шаблон"\n  revision: 1.0.1\n  default_locale: ru\n')
    assert with_header('template:\n  id:\n  name: ""\n', id='x', name='Y') == 'template:\n  id: x\n  name: "Y"\n'
    # Flow and JSON headers are headers too; inside braces every value is quoted, so JSON stays JSON.
    assert with_header('template: {id: a, name: "N"}\nx: 1\n', id='b', revision='1.0.0') == (
        'template: {"revision": "1.0.0", id: "b", name: "N"}\nx: 1\n')
    headed = with_header('{"template": {"id": "a"}, "x": 1}', id='b', name='N', revision='1.0.0')
    assert json.loads(headed) == {'template': {'revision': '1.0.0', 'name': 'N', 'id': 'b'}, 'x': 1}
    # Windows line endings, a comment above the first key, a line separator inside a value and a duplicate key.
    assert with_header('template:\r\n  id: a\r\n', revision='2.0.0') == 'template:\r\n  revision: 2.0.0\r\n  id: a\r\n'
    assert with_header('template:\n  # header\n  id: a\n', revision='1.0.0') == 'template:\n  # header\n  revision: 1.0.0\n  id: a\n'
    assert with_header('template:\n  id: a\n  name: "N\u2028M"\n  revision: 1\n', revision='1.0.0') == (
        'template:\n  id: a\n  name: "N\u2028M"\n  revision: 1.0.0\n')
    assert with_header('template:\n  name: N\n  name: M\n', name='Z') == 'template:\n  name: "Z"\n  name: M\n'
    # No template mapping: None. Unreadable YAML comes back as it is, so the compiler names the real error.
    assert with_header('template:\n', revision='1.0.0') is None and with_header('- a list\n', revision='1.0.0') is None
    assert with_header('template: [\n', revision='1.0.0') == 'template: [\n'
    # The stated name is read as the compiler reads the text: aliases and duplicate keys do not load.
    assert stated_name('template:\n  name: " N "\n') == 'N' and stated_name('template:\n  name: ""\n') is None
    assert stated_name('template:\n  name: &a N\n  other: *a\n') is None and stated_name('template:\n  name: N\n  name: M\n') is None


@pytest.mark.parametrize(('revisions', 'expected'), [({'1.0.0'}, '1.0.1'), ({'1.0.0', '1.0.1', '0.9.9'}, '1.0.2'),
    ({'2.10.0', '2.9.7'}, '2.10.1'), ({'draft', '1.4.0'}, '1.4.1'), ({'draft'}, '1.0.0'), (set(), '1.0.0')])
def test_the_next_revision_is_the_patch_after_the_highest_numbered_one(revisions, expected):
    assert next_revision(revisions) == expected


def test_a_taken_revision_is_refused_with_the_next_free_one_and_saved_under_it(tmp_path):
    config = TemplateConfig(tmp_path)
    copied = config.copy(GENERIC, 'Мой')[0]['text']
    larger = copied.replace('      size: 18\n', '      size: 20\n', 1)
    assert larger != copied
    assert config.save('custom-moy', larger) == (None, {'schemaVersion': 1, 'valid': False, 'package': None,
        'error': {'path': '/template/revision', 'message': REVISION_TAKEN, 'nextRevision': '1.0.1'}})
    state, refused = config.save('custom-moy', larger, '1.0.1')
    assert refused is None and state['package']['revision'] == '1.0.1'
    assert state['text'] == larger.replace('  revision: 1.0.0\n', '  revision: 1.0.1\n', 1)
    # A text still naming the first revision is offered the patch after the highest one ever saved.
    largest = larger.replace('      size: 20\n', '      size: 22\n', 1)
    assert config.save('custom-moy', largest)[1]['error']['nextRevision'] == '1.0.2'
    # A shipped template edited under its own revision gets the patch after the shipped one; Check names it too.
    shipped = yaml.safe_load(BUNDLED_TEXT)['template']['revision']
    edited = BUNDLED_TEXT.replace('      size: 18\n', '      size: 20\n', 1)
    assert config.check(GENERIC, edited)['error']['nextRevision'] == next_revision({shipped})
    assert config.save('custom-moy', 'template: []\n', '1.0.3')[1]['error'] == {'path': '/template', 'message': NO_HEADER}
    # A JSON header takes the revision too; the compiler then names what the text lacks.
    assert config.save('custom-moy', json.dumps({'template': {'id': 'custom-moy'}}), '1.0.3')[1]['error']['path'] == '/schema_version'


def test_a_copy_is_a_new_id_at_the_first_revision_with_the_source_assets(tmp_path):
    config = TemplateConfig(tmp_path)
    state, refused = config.copy(GENERIC, 'Мой')
    assert refused is None
    assert state['package']['id'] == 'custom-moy' and state['package']['revision'] == '1.0.0'
    assert state['package']['name'] == 'Мой' and (state['bundled'], state['edited']) == (False, True)
    assert yaml.safe_load(state['text'])['template']['id'] == 'custom-moy' and state['text'].startswith('# yaml-language')
    copied, source = config.store.current('custom-moy'), compile_template(BUNDLED_TEMPLATE)
    assert {a.path: a.sha256 for a in copied.assets} == {a.path: a.sha256 for a in source.assets}
    listing = config.catalog()
    assert [item['id'] for item in listing['templates']][-1] == 'custom-moy' and listing['defaultId'] == GENERIC
    assert config.copy(GENERIC, 'Мой')[0]['package']['id'] == 'custom-moy-2'
    # The copy of a copy reads its text and assets from the copy.
    assert config.copy('custom-moy', 'Мой')[0]['package']['id'] == 'custom-moy-3'


def test_delete_refuses_shipped_and_default_ids_and_never_gives_a_deleted_id_again(tmp_path):
    config = TemplateConfig(tmp_path)
    config.copy(GENERIC, 'Мой')
    package = config.store.current('custom-moy')
    with pytest.raises(TemplateRefused) as bundled:
        config.delete(GENERIC)
    assert bundled.value.code == 'TEMPLATE_BUNDLED'
    config.set_default('custom-moy')
    with pytest.raises(TemplateRefused) as default:
        config.delete('custom-moy')
    assert default.value.code == 'TEMPLATE_DEFAULT'
    config.set_default(GENERIC)
    listing = config.delete('custom-moy')
    assert listing['schemaVersion'] == 1 and 'custom-moy' not in [item['id'] for item in listing['templates']]
    with pytest.raises(UnknownTemplate):
        config.delete('custom-moy')
    with pytest.raises(UnknownTemplate):
        config.read('custom-moy')
    # Identities and the package stay; the deleted id is still taken.
    assert (config.store.root / package.package_hash / 'package.json').exists()
    assert 'custom-moy' in config.store.taken_ids()
    assert config.copy(GENERIC, 'Мой')[0]['package']['id'] == 'custom-moy-2'


def test_an_unsaved_text_gets_an_id_from_its_name_and_the_assets_of_its_source(tmp_path):
    config = TemplateConfig(tmp_path)
    draft = BUNDLED_TEXT.replace('  name: Две колонки\n', '  name: Новый\n', 1)
    state, refused = config.create(draft, GENERIC)
    assert refused is None and state['package']['id'] == 'custom-novyy' and state['package']['revision'] == '1.0.0'
    assert config.create(draft, None)[0]['package']['id'] == 'custom-novyy-2'
    broken, error = config.create(draft.replace('  default_locale: ru\n', '  default_locale: ru\n  colour: red\n', 1), None)
    assert broken is None and error['valid'] is False and error['error']['path'] == '/template/colour'
    assert config.create('- a list\n', None)[1]['valid'] is False
    assert config.create(json.dumps({'template': {'name': 'J'}}), None)[1]['error']['path'] == '/schema_version'
    with pytest.raises(UnknownTemplate):
        config.create(draft, 'missing')


def test_a_new_id_is_chosen_and_recorded_under_one_store_lock(tmp_path):
    config = TemplateConfig(tmp_path)
    seen = []

    def build(taken):
        seen.append(set(taken))
        return None
    # The builder sees the taken ids under the lock; refusing stores nothing.
    assert config.store.create(build) is None and seen == [{GENERIC, 'generic-one-column'}]
    assert [item['id'] for item in config.catalog()['templates']] == [GENERIC, 'generic-one-column']
    # A package under an id of the taken set is a programming error the store refuses.
    with pytest.raises(SchemaFailure):
        config.store.create(lambda _taken: compile_template(BUNDLED_TEMPLATE))
    state, refused = config.copy(GENERIC, 'Мой')
    assert refused is None and state['package']['id'] == 'custom-moy' and 'custom-moy' in config.store.taken_ids()


@pytest.mark.asyncio
async def test_routes_copy_and_delete_and_a_project_keeps_its_deleted_template(tmp_path):
    async with app_client(tmp_path, call_cap=4, provider=ScriptedTemplateProvider()) as (client, app):
        default = (await client.get('/v1/rich/template-config')).json()['defaultId']
        created = await client.post('/v1/rich/template-config', json={'copyOf': GENERIC, 'name': 'Мой'})
        assert created.status_code == 201, created.text
        assert created.json()['package']['id'] == 'custom-moy' and created.json()['bundled'] is False
        assert 'custom-moy' in [item['id'] for item in (await client.get('/v1/rich/template-import')).json()['templates']]
        project = (await upload(client, template_id='custom-moy')).json()['workspace']
        assert project['preDraft']['templatePackage']['id'] == 'custom-moy'
        for body, status, code in [({'copyOf': 'missing', 'name': 'X'}, 404, 'TEMPLATE_NOT_FOUND'),
                ({'text': BUNDLED_TEXT, 'assetsFrom': 'missing'}, 404, 'TEMPLATE_NOT_FOUND'),
                ({'copyOf': GENERIC}, 422, None), ({'copyOf': GENERIC, 'name': 'X', 'text': ''}, 422, None)]:
            reply = await client.post('/v1/rich/template-config', json=body)
            assert reply.status_code == status, body
            assert code is None or reply.json()['error']['code'] == code
        twice = await client.post('/v1/rich/template-config', headers={'Content-Type': 'application/json'},
            content='{"copyOf":"a","copyOf":"b","name":"X"}')
        assert twice.status_code == 422 and twice.json()['error']['code'] == 'INVALID_REQUEST'
        broken = await client.post('/v1/rich/template-config', json={'text': 'template: [\n', 'assetsFrom': None})
        assert broken.status_code == 422 and broken.json()['valid'] is False and broken.json()['error']['message']
        saved = await client.post('/v1/rich/template-config', json={'text': BUNDLED_TEXT, 'assetsFrom': GENERIC})
        assert saved.status_code == 201 and saved.json()['package']['id'] == 'custom-dve-kolonki'
        for template_id, status, code in [(GENERIC, 409, 'TEMPLATE_BUNDLED'), (default, 409, 'TEMPLATE_DEFAULT'),
                ('missing', 404, 'TEMPLATE_NOT_FOUND')]:
            reply = await client.delete('/v1/rich/template-config/' + template_id)
            assert (reply.status_code, reply.json()['error']['code']) == (status, code), template_id
        deleted = await client.delete('/v1/rich/template-config/custom-moy')
        assert deleted.status_code == 200 and deleted.json()['defaultId'] == default
        assert 'custom-moy' not in [item['id'] for item in deleted.json()['templates']]
        assert (await upload(client, template_id='custom-moy')).status_code == 404
        reopened = await client.post('/v2/projects/' + project['projectId'] + '/open', json={})
        assert reopened.status_code == 200
        captured = reopened.json()['response']['workspace']['preDraft']['templatePackage']
        assert (captured['id'], captured['packageHash']) == ('custom-moy', project['preDraft']['templatePackage']['packageHash'])
        again = await client.post('/v1/rich/template-config', json={'copyOf': GENERIC, 'name': 'Мой'})
        assert again.json()['package']['id'] == 'custom-moy-2'
        # Save under the free revision the refusal offered; an empty revision is no request.
        larger = again.json()['text'].replace('      size: 18\n', '      size: 20\n', 1)
        refused = await client.put('/v1/rich/template-config/custom-moy-2', json={'text': larger})
        assert refused.status_code == 422 and refused.json()['error']['nextRevision'] == '1.0.1'
        assert (await client.put('/v1/rich/template-config/custom-moy-2', json={'text': larger, 'revision': ''})).status_code == 422
        raised = await client.put('/v1/rich/template-config/custom-moy-2', json={'text': larger, 'revision': '1.0.1'})
        assert raised.status_code == 200 and raised.json()['package']['revision'] == '1.0.1'
        store = TemplateStore(app.state.projects.repository.root)
        registry = json.loads((store.root / 'identities.json').read_text())
        assert json.dumps(['custom-moy', '1.0.0'], separators=(',', ':')) in registry
