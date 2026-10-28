"""Short template form (schema_version 4): each shorthand expands to the canonical definition it stands for."""

import base64
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from packages.resume_core.templates.compiler import canonical, compile_bytes, compile_template
from packages.resume_core.templates.loading import load_declared_definition, load_definition
from packages.resume_core.templates.models import TemplateDefinition
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.shorthand import STANDARD_SUPPORT, expand
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, TemplateStore
from resume_api.template_config import TemplateConfig
from tools.shorten_template import shorten

ROOT = Path(__file__).resolve().parents[2]
PUBLICATIONS = ROOT / 'tests/fixtures/synthetic/templates/publications/template.yaml'
DEFINITIONS = {'text': {'type': ['string', 'null'], 'minLength': 1}, 'date': {'type': ['object', 'null']},
    'period': {'type': 'object'}, 'terms': {'type': 'object'}}


def short(**sections):
    return {'schema_version': 4, 'content_definitions': DEFINITIONS, **sections}


def block(**fields):
    return expand(short(blocks=[{'id': 'jobs', 'region': 'main', 'order': 1, 'view': {'nodes': []}, **fields}]))['blocks'][0]


def full(path):
    return TemplateDefinition.model_validate(load_definition(path.read_bytes())).model_dump(mode='json', by_alias=True)


def test_the_bundled_short_template_is_the_same_package_as_its_full_form():
    package = compile_template(BUNDLED_TEMPLATE)
    assert yaml.safe_load(BUNDLED_TEMPLATE.read_text(encoding='utf-8'))['schema_version'] == 4
    written_out = compile_bytes(json.dumps(full(BUNDLED_TEMPLATE)).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    assert written_out.package_hash == package.package_hash and written_out.config_hash == package.config_hash
    assert len(BUNDLED_TEMPLATE.read_text(encoding='utf-8').splitlines()) < 1100


@pytest.mark.parametrize('path', [BUNDLED_TEMPLATE, PUBLICATIONS], ids=['generic', 'publications'])
def test_shortening_any_template_expands_back_to_the_same_definition(path):
    document = full(path)
    shortened = shorten(document)
    assert shortened['schema_version'] == 4
    text = yaml.safe_dump(shortened, allow_unicode=True, sort_keys=False).encode()
    assert canonical(TemplateDefinition.model_validate(load_definition(text))) == canonical(document)


def test_field_types_expand_to_json_schema():
    schema = block(schema=[{'name': 'string', 'start': 'date', 'tags': ['text'], 'ongoing?': 'boolean',
        'place?': {'city': 'text'}, 'lines': {'list': 'string', 'maxItems': 3},
        'raw': {'type': 'string', 'pattern': 'x'}}])['content_schema']
    assert schema['type'] == 'array'
    item = schema['items']
    assert item['additionalProperties'] is False and item['required'] == ['name', 'start', 'tags', 'ongoing', 'place',
        'lines', 'raw']
    assert item['properties'] == {'name': {'type': 'string', 'minLength': 1}, 'start': {'$ref': '#/$defs/date'},
        'tags': {'type': 'array', 'items': {'$ref': '#/$defs/text'}}, 'ongoing': {'type': ['boolean', 'null']},
        'place': {'type': ['object', 'null'], 'additionalProperties': False, 'required': ['city'],
            'properties': {'city': {'$ref': '#/$defs/text'}}},
        'lines': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string', 'minLength': 1}},
        'raw': {'type': 'string', 'pattern': 'x'}}


def test_block_defaults_fill_the_canonical_keys():
    value = block(schema={'text': 'text'}, when='role-branch = technical')
    assert value['mode'] == 'model' and value['selectors'] == [{'kind': 'source', 'id': 'all'}]
    assert value['depends_on'] == [] and value['operation'] is None and value['extract'] == []
    assert value['rewrite'] == {'fields': [], 'instructions': []} and value['placement'] == {'region': 'main', 'order': 1}
    assert value['when'] == {'operation': 'role-branch', 'equals': 'technical'}
    assert value['view'] == {'mode': 'object', 'heading': 'plain', 'title': {}, 'inset': 0, 'item_gap': 0, 'nodes': []}
    assert block(schema=[{'name': 'text'}], view={'nodes': [], 'heading': 'band'})['view']['mode'] == 'items'


def test_standard_checks_are_added_with_review_lines_and_extra_kinds():
    checks = block(schema={'text': 'text'}, review=['Fail a sentence.'], checks={'attribution': 'Keep attribution.'})['checks']
    assert checks == [
        {'id': 'jobs-evidence', 'kind': 'evidence_identity', 'version': 1, 'parameters': {'fields': [], 'instructions': []}},
        {'id': 'jobs-support', 'kind': 'semantic_support', 'version': 1,
            'parameters': {'fields': [], 'instructions': ['Fail a sentence.', STANDARD_SUPPORT]}},
        {'id': 'jobs-attribution', 'kind': 'attribution', 'version': 1,
            'parameters': {'fields': [], 'instructions': ['Keep attribution.']}}]
    # A list is the full canonical list, kept as written.
    assert block(schema={'text': 'text'}, checks=[])['checks'] == []


def test_without_facts_the_item_fields_record_the_block_type():
    assert block(schema=[{'name': 'text', 'url': 'text'}])['bindings'] == [
        {'pointer': '/*/name', 'semantic_type': 'foldcv:jobs', 'field': 'name', 'relation': None},
        {'pointer': '/*/url', 'semantic_type': 'foldcv:jobs', 'field': 'url', 'relation': None}]


def test_linked_facts_get_item_pointers_and_renamed_fields():
    bindings = block(schema=[{'company': 'text', 'period': 'period', 'tags': [{'display': 'string'}]}],
        facts={'jobs': ['company', 'period/ongoing=present'], 'job_tag (owned_by)': ['tags/*/display']})['bindings']
    assert bindings == [
        {'pointer': '/*/company', 'semantic_type': 'foldcv:jobs', 'field': 'company', 'relation': None, 'item_pointer': '/*'},
        {'pointer': '/*/period/ongoing', 'semantic_type': 'foldcv:jobs', 'field': 'present', 'relation': None,
            'item_pointer': '/*'},
        {'pointer': '/*/tags/*/display', 'semantic_type': 'foldcv:job_tag', 'field': 'display',
            'relation': {'kind': 'owned_by', 'subject_pointer': '/*'}, 'item_pointer': '/*/tags/*'}]


def test_fact_types_operations_and_assets_expand():
    value = expand(short(
        fact_types=[{'id': 'role', 'fields': {'scope': 'text', 'start': 'date'}, 'builtin': 'employment',
            'relations': ['extension_of jobs'], 'builtin_fields': {'scope': 'role', 'start': 'start @job-period'}}],
        operations=[{'id': 'window', 'kind': 'partition_employment', 'inputs': ['jobs', 'source:all'], 'parameters': {}}],
        assets={'regular': 'assets/Regular.ttf', 'aliases': 'assets/aliases.json',
            'logo': {'path': 'assets/logo.png', 'role': 'logo'}}))
    fact = value['fact_types'][0]
    assert fact['id'] == 'foldcv:role' and fact['schema_version'] == '1' and fact['builtin_kind'] == 'employment'
    assert fact['relations'] == [{'kind': 'extension_of', 'target_types': ['foldcv:jobs']}]
    assert fact['builtin_fields'] == {'scope': {'field': 'role', 'period': None}, 'start': {'field': 'start', 'period': 'job-period'}}
    assert value['operations'][0]['version'] == 1 and value['operations'][0]['depends_on'] == []
    assert value['operations'][0]['inputs'] == [{'kind': 'block', 'id': 'jobs'}, {'kind': 'source', 'id': 'all'}]
    assert value['assets'] == [
        {'id': 'regular', 'path': 'assets/Regular.ttf', 'role': 'font', 'mime_type': 'font/ttf', 'embedding': 'allowed'},
        {'id': 'aliases', 'path': 'assets/aliases.json', 'role': 'catalog', 'mime_type': 'application/json',
            'embedding': 'not_applicable'},
        {'id': 'logo', 'path': 'assets/logo.png', 'role': 'logo', 'mime_type': 'image/png', 'embedding': 'not_applicable'}]
    assert value['schema_version'] == 3


@pytest.mark.parametrize(('sections', 'path', 'reason'), [
    ({'blocks': [{'id': 'a', 'region': 'main', 'order': 1, 'view': {'nodes': []}, 'schema': {'x': 'txt'}}]},
        '/blocks/0/schema/x', 'unknown field type: txt'),
    ({'blocks': [{'id': 'a', 'region': 'main', 'order': 1, 'view': {'nodes': []}, 'schema': {'x': 'text'}, 'extact': []}]},
        '/blocks/0', 'unknown block keys: extact'),
    ({'blocks': [{'id': 'a', 'region': 'main', 'order': 1, 'view': {'nodes': []}, 'schema': {'x?': 'text'}}]},
        '/blocks/0/schema/x', 'a named type decides null itself; drop the "?"'),
    ({'blocks': [{'id': 'a', 'region': 'main', 'order': 1, 'view': {'nodes': []}, 'schema': {'x': {'y': 'text'}},
        'facts': {'part (extension_of)': ['x/y']}}]}, '/blocks/0/facts', 'a linked part needs a block of items'),
    ({'blocks': [{'id': 'a', 'region': 'main', 'order': 1, 'view': {'nodes': []}, 'schema': {'items': ['text']},
        'facts': {'a': ['items/*']}}]}, '/blocks/0/facts/a', 'name the fact field of items/* with =field'),
    ({'blocks': [{'id': 'a', 'order': 1, 'view': {'nodes': []}, 'schema': {'x': 'text'}}]}, '/blocks/0', 'missing region'),
    ({'fact_types': [{'id': 'a', 'fields': {'x': 'nope'}}]}, '/fact_types/0/fields/x', 'unknown field type: nope'),
    ({'assets': {'font': 'assets/font.woff'}}, '/assets/font', 'write role, mime_type and embedding for this file type'),
    ({'blocks': 5}, '/blocks', 'expected a list'),
])
def test_mistakes_name_the_short_path(sections, path, reason):
    with pytest.raises(SchemaFailure) as error:
        expand(short(**sections))
    assert (error.value.path, error.value.reason) == (path, reason)


def test_a_json_template_may_use_the_short_form_too():
    raw = json.dumps(yaml.safe_load(BUNDLED_TEMPLATE.read_text(encoding='utf-8'))).encode()
    assert canonical(TemplateDefinition.model_validate(load_declared_definition(raw, 'json'))) == canonical(full(BUNDLED_TEMPLATE))


def test_the_editor_schema_accepts_both_forms():
    schema = json.loads((ROOT / 'contracts/template-source.schema.json').read_text(encoding='utf-8'))
    validator = jsonschema.Draft202012Validator(schema)
    assert not list(validator.iter_errors(yaml.safe_load(BUNDLED_TEMPLATE.read_text(encoding='utf-8'))))
    assert not list(validator.iter_errors(full(BUNDLED_TEMPLATE)))
    typo = yaml.safe_load(BUNDLED_TEMPLATE.read_text(encoding='utf-8'))
    typo['blocks'][0]['extact'] = []
    assert list(validator.iter_errors(typo))


def test_settings_show_the_bundled_text_for_a_package_captured_from_the_old_long_form(tmp_path):
    document = full(BUNDLED_TEMPLATE)
    old = compile_bytes(yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode(), BUNDLED_TEMPLATE.parent)
    assert old.package_hash == compile_template(BUNDLED_TEMPLATE).package_hash
    TemplateStore(tmp_path / 'template-packages').activate(old)
    state = TemplateConfig(tmp_path / 'template-packages').read(old.id)
    assert base64.b64decode(old.original_base64).decode() != BUNDLED_TEMPLATE.read_text(encoding='utf-8')
    assert state['text'] == BUNDLED_TEMPLATE.read_text(encoding='utf-8') and state['edited'] is False
