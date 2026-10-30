"""Captured compiler1 bytes remain exact while new item capabilities are explicit."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from packages.resume_core.templates.compiler import canonical, compile_bytes, compile_definition_v1
from packages.resume_core.templates.models import TemplatePackage
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import verify_package


FIXTURE = Path('tests/fixtures/synthetic/templates/compiler-v1-package.json')


def retained():
    return TemplatePackage.model_validate_json(FIXTURE.read_bytes())


def compile_config(config, tmp_path):
    (tmp_path / 'fixture.font').write_bytes(b'synthetic compiler compatibility asset; not a render font')
    return compile_bytes(json.dumps(config).encode(), tmp_path, original_format='json')


def nested_config():
    config = retained().definition.model_dump(mode='json', by_alias=True)
    config['template']['revision'] = '2'
    scalar = {'type': ['string', 'null']}
    config['fact_types'] = [
        {'id': 'employment', 'schema_version': '1', 'schema': {'type': 'object', 'additionalProperties': False,
            'required': ['company'], 'properties': {'company': scalar}}, 'builtin_kind': 'employment',
            'relations': [], 'builtin_fields': {'company': {'field': 'employer', 'period': None}}},
        {'id': 'extras', 'schema_version': '1', 'schema': {'type': 'object', 'additionalProperties': False,
            'required': ['scope'], 'properties': {'scope': scalar}}, 'builtin_kind': None,
            'relations': [{'kind': 'extension_of', 'target_types': ['employment']}]},
    ]
    block = config['blocks'][0]
    block['content_schema'] = {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'required': ['company', 'details', 'tasks'], 'properties': {'company': scalar,
            'details': {'type': 'object', 'additionalProperties': False, 'required': ['scope'], 'properties': {'scope': scalar}},
            'tasks': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                'required': ['value'], 'properties': {'value': scalar}}}}}}
    block['bindings'] = [
        {'pointer': '/*/company', 'semantic_type': 'employment', 'field': 'company', 'relation': None, 'item_pointer': '/*'},
        {'pointer': '/*/details/scope', 'semantic_type': 'extras', 'field': 'scope',
            'relation': {'kind': 'extension_of', 'subject_pointer': '/*'}, 'item_pointer': '/*/details'},
    ]
    block['view']['nodes'] = [{'type': 'text', 'style': 'body', 'field': '/company'},
        {'type': 'bullets', 'style': 'body', 'field': '/tasks', 'item_field': '/value'}]
    return config


def test_captured_compiler1_definition_recipe_manifest_and_bytes_are_exact():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'fbaf25820c53b361d9e8f210c4c73acdee28443436917ff9837c246bc4e29a25'
    package = retained()
    assert canonical(package) == raw and verify_package(package) == package
    blocks, recipe, manifest = compile_definition_v1(package.definition)
    assert (blocks, recipe, manifest) == (package.blocks, package.recipe, package.manifest)


def test_new_capabilities_compile_as_two_and_old_compiler_cannot_claim_them(tmp_path):
    package = compile_config(nested_config(), tmp_path)
    assert package.compiler_version == 'template-compiler-3'
    assert package.recipe.capabilities[-3:] == ['object_items', 'builtin_mapping', 'explicit_item_roots']
    assert verify_package(package) == package
    with pytest.raises(SchemaFailure, match='captured compiler version'):
        compile_definition_v1(package.definition)
    old = package.model_copy(update={'compiler_version': 'template-compiler-1'})
    with pytest.raises(SchemaFailure):
        verify_package(old)
    assert verify_package(retained()) == retained()


def test_explicit_fallback_style_is_validated_and_declared_without_changing_legacy_bytes(tmp_path):
    config = retained().definition.model_dump(mode='json', by_alias=True)
    config['template']['revision'] = 'fallback-style'
    config['blocks'][0]['view']['fallback_style'] = 'body'
    package = compile_config(config, tmp_path)
    assert package.compiler_version == 'template-compiler-3'
    assert package.recipe.capabilities[-1] == 'fallback_style'
    assert verify_package(package) == package
    with pytest.raises(SchemaFailure, match='captured compiler version'):
        compile_definition_v1(package.definition)
    config['blocks'][0]['view']['fallback_style'] = 'missing-style'
    with pytest.raises(SchemaFailure, match='unknown reference'):
        compile_config(config, tmp_path)
    assert canonical(retained()) == FIXTURE.read_bytes()


@pytest.mark.parametrize('failure', ['outside_root', 'scalar_root', 'wildcard_root', 'object_item', 'wrong_type', 'unknown_builtin',
    'period_slot', 'duplicate_destination'])
def test_invalid_new_mappings_fail_before_activation(tmp_path, failure):
    config = deepcopy(nested_config())
    bindings = config['blocks'][0]['bindings']
    mapped = config['fact_types'][0]
    if failure == 'outside_root':
        bindings[1]['item_pointer'] = '/*/tasks/*'
    elif failure == 'scalar_root':
        bindings[0]['item_pointer'] = '/*/company'
    elif failure == 'wildcard_root':
        bindings[1]['item_pointer'] = '/0/details'
    elif failure == 'object_item':
        config['blocks'][0]['view']['nodes'][1]['item_field'] = ''
    elif failure == 'wrong_type':
        mapped['builtin_fields']['company']['field'] = 'present'
        mapped['builtin_fields']['company']['period'] = 'job-period'
    elif failure == 'unknown_builtin':
        mapped['builtin_fields']['company']['field'] = 'arbitrary-python-field'
    elif failure == 'period_slot':
        mapped['builtin_fields']['company']['period'] = 'not-a-period-field'
    else:
        mapped['schema']['required'].append('alias')
        mapped['schema']['properties']['alias'] = {'type': ['string', 'null']}
        mapped['builtin_fields']['alias'] = {'field': 'employer', 'period': None}
    with pytest.raises((SchemaFailure, ValueError)):
        compile_config(config, tmp_path)
