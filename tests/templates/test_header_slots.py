"""Explicit header slots do not alter captured packages that omit them."""

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from packages.resume_core.templates.compiler import canonical,compile_definition,compile_definition_v1,compile_template
from packages.resume_core.templates.models import TemplatePackage
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE,verify_package
from tests.templates.test_compiler_versions import compile_config,retained


OLD_TWO=Path('tests/fixtures/synthetic/templates/compiler-v2-package.json')


def header_config():
    config=retained().definition.model_dump(mode='json',by_alias=True)
    block=config['blocks'][0];block['placement']['region']='header'
    block['view']['nodes'][0]['header_slot']='name'
    return config


def test_captured_compiler_one_and_two_without_slots_keep_exact_bytes_and_derivation():
    assert hashlib.sha256(OLD_TWO.read_bytes()).hexdigest()=='2c17ba2032055b1c85b42925cdeb2114fd9ea04b271aa18cf9419b55caf756ec'
    for package in [retained(),TemplatePackage.model_validate_json(OLD_TWO.read_bytes())]:
        raw=canonical(package)
        assert b'header_slot' not in raw and verify_package(package)==package
        blocks,recipe,manifest=compile_definition(package.definition,package.compiler_version)
        assert (blocks,recipe,manifest)==(package.blocks,package.recipe,package.manifest)
        assert canonical(TemplatePackage.model_validate_json(raw))==raw
    assert canonical(TemplatePackage.model_validate_json(OLD_TWO.read_bytes()))==OLD_TWO.read_bytes()


@pytest.mark.parametrize('kind',['text','join_fields'])
def test_explicit_header_slot_requires_modern_compiler_and_survives_package_verification(tmp_path,kind):
    config=header_config();node=config['blocks'][0]['view']['nodes'][0]
    if kind=='join_fields':node.update(type='join_fields',field=None,fields=['/title','/journal'],separator=' / ')
    package=compile_config(config,tmp_path)
    assert package.compiler_version=='template-compiler-3' and package.recipe.capabilities[-1]=='header_slots'
    assert package.recipe.views[config['blocks'][0]['id']].nodes[0].header_slot=='name'
    assert verify_package(package)==package
    with pytest.raises(SchemaFailure,match='captured compiler version'):compile_definition_v1(package.definition)


@pytest.mark.parametrize('damage',['body','duplicate_node','duplicate_block','unsupported_node'])
def test_invalid_slot_placement_or_duplicate_declaration_rejects_before_activation(tmp_path,damage):
    config=header_config();block=config['blocks'][0]
    if damage=='body':block['placement']['region']='main'
    elif damage=='duplicate_node':block['view']['nodes'].append(deepcopy(block['view']['nodes'][0]))
    elif damage=='duplicate_block':
        duplicate=deepcopy(block);duplicate['id']='other-header';duplicate['placement']['order']+=1
        config['blocks'].append(duplicate)
    else:
        block['view']['nodes'][0].update(type='period',field='/title')
    with pytest.raises((SchemaFailure,ValueError)):compile_config(config,tmp_path)


def test_new_generic_capture_has_explicit_name_and_profession_slots_only():
    package=compile_template(BUNDLED_TEMPLATE);view=package.recipe.views['identity']
    assert [(node.field,node.header_slot) for node in view.nodes]==[('/name','name'),('/profession','profession')]
    assert [node.header_slot for key,view in package.recipe.views.items() if key!='identity'
        for node in view.nodes if node.header_slot is not None]==[]
    assert verify_package(package)==package
