"""Configuration behavior uses independent geometry and rejection expectations."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from packages.resume_core.templates.compiler import compile_bytes, compile_template
from packages.resume_core.templates.loading import CONFIG_DEPTH, load_definition
from packages.resume_core.templates.projection import SchemaFailure, validate_payload
from packages.resume_core.templates.store import BUNDLED_TEMPLATE, BUNDLED_TEMPLATES, TemplateStore, verify_package


@pytest.fixture
def config():
    return load_definition(BUNDLED_TEMPLATE.read_bytes())


def compile_config(config):
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format="json")


def test_equivalent_yaml_json_keeps_originals_and_compiled_assets(config):
    yaml_package = compile_template(BUNDLED_TEMPLATE)
    json_package = compile_config(config)
    assert yaml_package.package_hash == json_package.package_hash
    assert yaml_package.original_hash != json_package.original_hash
    assert yaml_package.original_format == "yaml"
    assert json_package.original_format == "json"
    assert len(yaml_package.blocks) == 17
    assert yaml_package.recipe.style.text["name"].size == 18
    assert yaml_package.recipe.style.text["body"].size == 10
    assert yaml_package.recipe.layout.regions[1].width == 118.5
    assert yaml_package.recipe.style.footer.text == "mail@example.com"
    assert {asset.role for asset in yaml_package.assets} == {"font", "logo", "catalog"}
    assert verify_package(yaml_package) == yaml_package


def test_nested_dialect_is_rejected_and_payload_resolution_never_fetches(config, monkeypatch):
    import urllib.request
    attempted = []
    def forbidden(*args, **kwargs):
        attempted.append(args)
        raise AssertionError('network retrieval')
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    hidden = {'$schema': 'http://json-schema.org/draft-07/schema#',
        'dependencies': {'name': {'$ref': 'https://example.invalid/forbidden-schema'}}}
    config['blocks'][0]['content_schema']['allOf'] = [hidden]
    with pytest.raises(SchemaFailure, match='dialect'):
        compile_config(config)
    with pytest.raises(SchemaFailure, match='offline'):
        validate_payload({'allOf': [hidden]}, {'name': 'Synthetic'})
    assert attempted == []


def test_nested_definition_dependencies_survive_compilation_and_activation(config, tmp_path):
    config['content_definitions']['outer'] = {'type': 'string', '$defs': {
        'inner': {'$ref': '#/$defs/leaf'}, 'sibling': {'$ref': '#/$defs/other'}}}
    config['content_definitions']['leaf'] = {'type': 'string'}
    config['content_definitions']['other'] = {'type': 'integer'}
    schema = config['blocks'][0]['content_schema']
    schema['properties']['extra'] = {'$ref': '#/$defs/outer/$defs/inner'}
    schema['required'].append('extra')
    package = compile_config(config)
    TemplateStore(tmp_path).activate(package)
    validate_payload(package.blocks[0].full_schema, {'name': 'Synthetic', 'profession': None, 'role_family': {'family': None},
        'extra': 'Retained'})
    assert {'leaf', 'other', 'outer'} <= package.blocks[0].full_schema['$defs'].keys()


@pytest.mark.parametrize("raw", [b'a: 1\na: 2', b'1: value', b'x: .nan', b'x: .inf', b'x: 2026-10-21',
    b'x: !!set {a: null}', b'x: yes', b'x: 0xFF', b'x: &x [*x]', b'x: !unknown value', b'[]', b''])
def test_non_json_yaml_rejected_with_location(raw):
    with pytest.raises(SchemaFailure, match=': '): load_definition(raw)


def test_excessive_nesting_has_a_technical_error():
    with pytest.raises(SchemaFailure, match='nesting'):
        load_definition(('x: ' + '[' * (CONFIG_DEPTH + 1) + '0' + ']' * (CONFIG_DEPTH + 1)).encode())


@pytest.mark.parametrize("mutate,reason", [
    (lambda c:c.update(unknown_setting=True), 'Extra inputs'),
    (lambda c:c['blocks'].append(deepcopy(c['blocks'][0])), 'duplicate identity'),
    (lambda c:c['blocks'][0]['view']['nodes'][0].update(field='/missing'), 'unknown field'),
    (lambda c:c['blocks'][0]['view']['nodes'][0].update(style='absent'), 'unknown reference'),
    (lambda c:c['style']['header']['logo'].update(asset='absent'), 'unknown reference'),
    (lambda c:c['blocks'][0].update(depends_on=['absent']), 'unknown dependency'),
    (lambda c:c['blocks'][0].update(depends_on=['identity']), 'dependency cycle'),
    (lambda c:c['blocks'][0]['view']['nodes'][0].update(type='html'), 'Input should be'),
    (lambda c:c['blocks'][9]['view']['nodes'][3].update(field='/technologies'), 'incompatible view field type'),
    (lambda c:c['content_definitions'].update(unused_bad={'$ref':'https://example.invalid/schema'}), 'only local'),
    (lambda c:c['blocks'][0]['placement'].update(region='floating'), 'Input should be'),
    (lambda c:c['blocks'][1]['placement'].update(region='header',order=10), 'ambiguous active'),
    (lambda c:c['blocks'][0]['checks'][0].update(kind='arbitrary_code'), 'Input should be'),
    (lambda c:c['blocks'][0]['selectors'][0].update(id='unknown_source'), 'unknown reference'),
    (lambda c:c['blocks'][0]['bindings'][0].update(semantic_type='unknown_type'), 'unknown reference'),
    (lambda c:c['content_definitions']['text'].update({'$ref':'https://example.invalid/schema'}), 'only local'),
    (lambda c:c['content_definitions']['text'].update({'$ref':'#/$defs/text'}), 'recursive'),
])
def test_invalid_candidate_references_shapes_and_cycles(config, mutate, reason):
    mutate(config)
    with pytest.raises(SchemaFailure, match=reason): compile_config(config)


@pytest.mark.parametrize("mutate,path", [
    (lambda c:next(b for b in c['blocks'] if b['id']=='education')['placement'].update(region='sidebar'), '/blocks/education/placement'),
    (lambda c:c['layout'].update(reading_order=['header','sidebar','main']), '/layout'),
    (lambda c:c['layout']['regions'].reverse(), '/layout'),
    (lambda c:c['layout'].update(regions=c['layout']['regions'][1:], reading_order=['main']), '/layout'),
])
def test_a_one_column_layout_has_no_sidebar_and_refuses_a_block_placed_there(mutate, path):
    config = load_definition(BUNDLED_TEMPLATES['generic-one-column'].read_bytes())
    assert [region.id for region in compile_config(deepcopy(config)).recipe.layout.regions] == ['header', 'main']
    mutate(config)
    with pytest.raises(SchemaFailure) as error: compile_config(config)
    assert error.value.path == path


def test_provider_envelope_uses_only_reachable_definitions_and_keeps_server_constraints(config):
    config['content_definitions']['unused_incompatible'] = {'type':'string','not':{'const':'bad'}}
    package = compile_config(config)
    block = next(b for b in package.blocks if b.id == 'projects')
    assert block.provider_schema['type'] == 'object'
    assert block.provider_schema['required'] == ['payload']
    assert set(block.provider_schema['$defs']) == {'date','period','text'}
    assert 'unused_incompatible' not in block.full_schema['$defs']
    assert any(p.endswith('/if') for p in block.server_only)
    date = block.full_schema['$defs']['date']
    assert date['then'] == {'properties':{'year':{'type':'integer'}}}
    with pytest.raises(SchemaFailure):
        validate_payload({'$ref':'#/$defs/date','$defs':block.full_schema['$defs']}, {'raw':'May','year':None,'month':5})


def test_empty_optional_blocks_need_no_generic_operation(config):
    config['operations'] = []
    for block in config['blocks']:
        block['selectors'] = [{'kind':'source','id':'all'}]
        block['depends_on'] = []; block['operation'] = None; block['when'] = None
    config['blocks'] = config['blocks'][:1]
    config['blocks'][0]['content_schema'] = {'type':'object','additionalProperties':False,
        'required':['name','profession'],'properties':{'name':{'type':['string','null']},'profession':{'type':['string','null']}}}
    config['blocks'][0]['bindings'] = [value for value in config['blocks'][0]['bindings'] if value['pointer'] in {'/name','/profession'}]
    package = compile_config(config)
    validate_payload(package.blocks[0].full_schema, {'name':None,'profession':None})
    assert package.definition.operations == []


def test_activation_is_atomic_and_revision_collision_preserves_active_package(config,tmp_path):
    store = TemplateStore(tmp_path)
    original = compile_config(config); store.activate(original)
    before = (store.root/'active.json').read_bytes()
    config['style']['text']['body']['size'] = 11
    changed = compile_config(config)
    with pytest.raises(SchemaFailure,match='already identifies'): store.activate(changed)
    assert (store.root/'active.json').read_bytes() == before
    assert store.active().package_hash == original.package_hash
    config['template']['revision'] += '-next'; newer=compile_config(config); store.activate(newer)
    assert store.active().package_hash == newer.package_hash
    assert original.recipe.style.text['body'].size == 10
    assert (store.root/original.package_hash/'package.json').is_file()


def test_changed_asset_changes_package_and_old_capture_stays_exact(config,tmp_path):
    asset_root=tmp_path/'assets'; asset_root.mkdir()
    for a in config['assets']:
        blob=(BUNDLED_TEMPLATE.parent/a['path']).read_bytes()
        (tmp_path/a['path']).write_bytes(blob)
    original=compile_bytes(json.dumps(config).encode(),tmp_path)
    font=tmp_path/config['assets'][0]['path']; font.write_bytes(font.read_bytes()+b'changed')
    changed=compile_bytes(json.dumps(config).encode(),tmp_path)
    assert changed.config_hash == original.config_hash
    assert changed.package_hash != original.package_hash
    assert verify_package(original) == original


@pytest.mark.parametrize('path',['../outside.ttf','/tmp/outside.ttf','assets/../../outside.ttf','assets\\outside.ttf'])
def test_asset_escape_rejected(config,path):
    config['assets'][0]['path']=path
    with pytest.raises(SchemaFailure,match='package root'): compile_config(config)


def test_symlink_asset_is_rejected(config,tmp_path):
    (tmp_path/'assets').mkdir()
    for asset in config['assets']:
        (tmp_path/asset['path']).symlink_to(BUNDLED_TEMPLATE.parent/asset['path'])
    with pytest.raises(SchemaFailure,match='symlink'): compile_bytes(json.dumps(config).encode(),tmp_path)


def test_bundled_default_does_not_write_a_store(tmp_path):
    absent=tmp_path/'not-created'
    package=TemplateStore(absent).active()
    assert package.id == 'generic-two-column'
    assert not absent.exists()


def test_cli_validate_never_activates_and_activate_requires_explicit_root(tmp_path):
    command=[sys.executable,'tools/templates.py']
    completed=subprocess.run([*command,'validate',str(BUNDLED_TEMPLATE)],capture_output=True,text=True)
    assert completed.returncode == 0
    assert list(tmp_path.iterdir()) == []
    rejected=subprocess.run([*command,'activate',str(BUNDLED_TEMPLATE)],capture_output=True,text=True)
    assert rejected.returncode != 0 and '--store-root' in rejected.stderr
    activated=subprocess.run([*command,'activate',str(BUNDLED_TEMPLATE),'--store-root',str(tmp_path)],capture_output=True,text=True)
    assert activated.returncode == 0
    assert TemplateStore(tmp_path).active().id == 'generic-two-column'
    invalid=tmp_path/'invalid.yaml'; invalid.write_text('schema_version: 3\nschema_version: 4\n')
    before=(tmp_path/'template-packages/active.json').read_bytes()
    failed=subprocess.run([*command,'activate',str(invalid),'--store-root',str(tmp_path)],capture_output=True,text=True)
    assert failed.returncode == 1 and 'duplicate key' in failed.stderr
    assert (tmp_path/'template-packages/active.json').read_bytes() == before


def test_corrupt_package_and_unsupported_recipe_fail_explicitly():
    package=compile_template(BUNDLED_TEMPLATE)
    corrupt=package.model_copy(deep=True); corrupt.assets[0].bytes_base64='AA=='
    with pytest.raises(SchemaFailure,match='asset bytes'): verify_package(corrupt)
    unsupported=package.model_copy(deep=True); unsupported.compiler_version='future'
    with pytest.raises(SchemaFailure,match='unsupported'): verify_package(unsupported)


def test_failed_active_pointer_write_keeps_previous_capture(config,tmp_path,monkeypatch):
    from packages.resume_core.templates import store as module
    store=TemplateStore(tmp_path); first=compile_config(config); store.activate(first)
    before=(store.root/'active.json').read_bytes()
    config['template']['revision']='2'; second=compile_config(config)
    original=module.atomic_write
    def fail(path,blob):
        if path.name == 'active.json': raise OSError('synthetic write failure')
        return original(path,blob)
    monkeypatch.setattr(module,'atomic_write',fail)
    with pytest.raises(OSError,match='synthetic'): store.activate(second)
    assert (store.root/'active.json').read_bytes() == before
    assert store.active().package_hash == first.package_hash


def test_store_parent_symlink_is_rejected(tmp_path):
    from packages.resume_core.storage import StorageFailure
    real=tmp_path/'real'; TemplateStore(real).activate(compile_template(BUNDLED_TEMPLATE))
    linked=tmp_path/'link'; linked.symlink_to(real,target_is_directory=True)
    with pytest.raises(StorageFailure): TemplateStore(linked).active()


def test_schema_field_names_do_not_get_interpreted_as_schema_keywords(config):
    config['content_definitions']['keyword_fields']={'type':'object','additionalProperties':False,
        'required':['format','$ref'],'properties':{'format':{'type':'string'},'$ref':{'type':'string'}}}
    compile_config(config)


@pytest.mark.parametrize('reference',[{'operation':'focus'}, {'when':{'operation':'focus','equals':'impossible'}},
    {'when':{'operation':'role-branch','equals':'impossible'}}])
def test_operation_references_and_conditions_use_declared_outputs(config,reference):
    # The summary block feeds no operation, so a condition on it cannot form a dependency cycle.
    next(block for block in config['blocks'] if block['id']=='summary').update(reference)
    with pytest.raises(SchemaFailure,match='unknown reference|condition output'): compile_config(config)


def test_binding_payload_and_semantic_cell_shapes_are_compatible(config):
    location=next(value for value in config['fact_types'] if value['id']=='foldcv:location')
    location['schema']['properties']['city']={'type':'integer'}
    with pytest.raises(SchemaFailure,match='incompatible semantic binding type'): compile_config(config)


def test_rehashed_package_cannot_replace_derived_server_schema_or_projection():
    from packages.resume_core.templates.compiler import canonical,sha256
    from packages.resume_core.templates.store import package_identity
    package=compile_template(BUNDLED_TEMPLATE)
    package.blocks[0].full_schema={'type':'integer'}
    package.package_hash=sha256(canonical(package_identity(package)))
    with pytest.raises(SchemaFailure,match='derivation'): verify_package(package)


def test_nested_resource_id_cannot_change_local_ref_resolution(config):
    config['blocks'][0]['content_schema']['properties']['name']['$id']='https://example.invalid/nested.json'
    with pytest.raises(SchemaFailure,match='resource IDs'): compile_config(config)
