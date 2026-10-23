"""Strict declared JSON uses compiler3 without reinterpreting retained packages."""

import base64
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_archive import export_rich_archive,open_rich_archive
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.templates.compiler import canonical,compile_bytes,compile_definition,compile_template
from packages.resume_core.templates.loading import load_declared_definition,load_definition
from packages.resume_core.templates.models import TemplatePackage
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import verify_package
from tests.templates.storage_fixtures import workspace
from tests.templates.test_compiler_versions import retained


HISTORICAL={1:'32144b10ad171e5f171bbc020185c46b82e4d682ed841df3e1b8267c0d286d08',
    2:'c9c359c894c49ec25247188fb1c411d6f5558dea8c7c1c41be7176edbe12df23'}


def compile_config(config,tmp_path,*,original_format='json'):
    source=retained()
    for asset in source.assets:
        path=tmp_path/asset.path;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(base64.b64decode(asset.bytes_base64))
    raw=json.dumps(config).encode() if original_format=='json' else yaml.safe_dump(config).encode()
    return compile_bytes(raw,tmp_path,original_format=original_format)


@pytest.mark.parametrize('version',[1,2])
def test_prechange_scientific_packages_keep_exact_bytes_and_legacy_meaning(version):
    path=Path(f'tests/fixtures/synthetic/templates/compiler-v{version}-scientific-package.json');raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==HISTORICAL[version]
    package=TemplatePackage.model_validate_json(raw)
    assert verify_package(package)==package and canonical(package)==raw
    assert package.definition.content_definitions['legacy-scientific']['const']=='1e3'
    original=base64.b64decode(package.original_base64)
    assert load_definition(original)['content_definitions']['legacy-scientific']['const']=='1e3'
    assert load_declared_definition(original,'json')['content_definitions']['legacy-scientific']['const']==1000.0
    assert compile_definition(package.definition,package.compiler_version)==(package.blocks,package.recipe,package.manifest)
    # Relabelling an old package never opts its retained meaning into the new loader.
    changed=package.model_copy(update={'compiler_version':'template-compiler-3'})
    with pytest.raises(SchemaFailure):verify_package(changed)


def test_compiler3_preserves_scientific_style_and_schema_numbers_in_declared_json(tmp_path):
    config=retained().definition.model_dump(mode='json',by_alias=True)
    config['style']['text']['body'].update(size=1e308,line_height=1e-308)
    config['content_definitions']['scientific']={'type':'number','const':1e100,'minimum':1e-100}
    captured=compile_config(config,tmp_path)
    assert captured.compiler_version=='template-compiler-3' and verify_package(captured)==captured
    assert captured.definition.style.text['body'].size==1e308
    assert captured.definition.style.text['body'].line_height==1e-308
    assert captured.definition.content_definitions['scientific']==config['content_definitions']['scientific']
    restored=TemplatePackage.model_validate_json(canonical(captured))
    assert canonical(verify_package(restored))==canonical(captured)


def test_supported_yaml_json_definitions_keep_the_same_compiler3_semantics(tmp_path):
    config=retained().definition.model_dump(mode='json',by_alias=True)
    config['style']['text']['body'].update(size=1e100,line_height=1e-100)
    config['content_definitions']['scientific']={'type':'number','const':1e100}
    first=compile_config(config,tmp_path)
    second=compile_config(config,tmp_path,original_format='yaml')
    assert first.compiler_version==second.compiler_version=='template-compiler-3'
    assert first.definition==second.definition and first.recipe==second.recipe and first.package_hash==second.package_hash
    assert first.original_hash!=second.original_hash


@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"outer":{"a":1,"a":2}}',b'{"a":NaN}',
    b'{"a":Infinity}',b'{"a":-Infinity}',b'{"a":1e309}',b'{"a":1e-999}',b'{"a":01}',
    b'{"a":1,}',b'a: 1',b'[]',b'{"a":"\\ud800"}',b'{"\\ud800":1}',b'{"a":1} trailing'])
def test_invalid_json_never_falls_back_or_coerces_out_of_range_numbers(raw):
    with pytest.raises(SchemaFailure):load_declared_definition(raw,'json')


def test_json_keeps_real_strings_and_negative_zero_without_yaml_scalar_inference():
    result=load_declared_definition(b'{"number":1e3,"text":"1e3","zero":-0.0,"tiny":5e-324}','json')
    assert result=={'number':1000.0,'text':'1e3','zero':-0.0,'tiny':5e-324}
    assert canonical(result).find(b'"zero":-0.0')>=0
    assert load_declared_definition(b'{"zero":0e-9999}','json')=={'zero':0.0}


@pytest.mark.parametrize('value', ['1.0e-999', '-1.0e-999', '1.0e+999'])
@pytest.mark.parametrize('format', ['yaml', 'json'])
def test_numeric_range_is_the_same_for_yaml_and_json(value, format):
    raw = ('minimum: ' + value if format == 'yaml' else '{"minimum":' + value + '}').encode()
    with pytest.raises(SchemaFailure):
        load_declared_definition(raw, format)


def test_yaml_keeps_representable_subnormals_and_real_zero():
    assert load_declared_definition(b'tiny: 5.0e-324\nzero: 0.0e-999\n', 'yaml') == {'tiny': 5e-324, 'zero': 0.0}


def test_json_retains_existing_byte_depth_and_node_limits(monkeypatch):
    monkeypatch.setattr('packages.resume_core.templates.loading.CONFIG_BYTES',10)
    with pytest.raises(SchemaFailure,match='byte limit'):load_declared_definition(b'{"long":"123456"}','json')
    monkeypatch.setattr('packages.resume_core.templates.loading.CONFIG_BYTES',1000)
    monkeypatch.setattr('packages.resume_core.templates.loading.CONFIG_DEPTH',2)
    with pytest.raises(SchemaFailure,match='nesting/node'):load_declared_definition(b'{"a":[[[1]]]}','json')
    monkeypatch.setattr('packages.resume_core.templates.loading.CONFIG_DEPTH',64)
    monkeypatch.setattr('packages.resume_core.templates.loading.CONFIG_NODES',3)
    with pytest.raises(SchemaFailure,match='nesting/node'):load_declared_definition(b'{"a":[1,2]}','json')


def test_file_extension_selects_declared_parser_and_json_does_not_fall_back(tmp_path):
    config=retained().definition.model_dump(mode='json',by_alias=True)
    compile_config(config,tmp_path)
    path=tmp_path/'template.json';path.write_text(yaml.safe_dump(config))
    with pytest.raises(SchemaFailure,match='invalid JSON'):compile_template(path)
    yaml_path=tmp_path/'template.yaml';yaml_path.write_bytes(path.read_bytes())
    assert compile_template(yaml_path).original_format=='yaml'


def predraft(captured):
    before,sources=workspace();data=before.model_dump(mode='json',by_alias=True)
    prior=data['project'];data['project']=None
    data['preDraft']={'selectedInput':'text','selectedSourceId':prior['sources'][0]['id'],
        'sources':prior['sources'],'facts':WorkingFactsV2(schemaVersion=2,revision=1,records=[],tombstones=[],
            extensions=[],observations=[],relations=[],manualScopes=[]).model_dump(by_alias=True),
        'operations':[],'warnings':[],'templatePackage':captured.model_dump(by_alias=True),'templateOperations':[]}
    return WorkspaceV7.model_validate(data),sources


@pytest.mark.parametrize('version',[1,2,3])
@pytest.mark.parametrize('stage',['predraft','authored'])
def test_archive_and_reopen_keep_exact_version_format_and_original_meaning(tmp_path,version,stage):
    if version<3:
        captured=TemplatePackage.model_validate_json(Path(f'tests/fixtures/synthetic/templates/compiler-v{version}-scientific-package.json').read_bytes())
    else:
        config=retained().definition.model_dump(mode='json',by_alias=True)
        config['content_definitions']['scientific']={'const':1e100}
        captured=compile_config(config,tmp_path)
    before,sources=predraft(captured);exact=canonical(captured)
    if stage=='authored':
        authored,_=workspace();data=authored.model_dump(mode='json',by_alias=True)
        data['project']['templatePackage']=captured.model_dump(by_alias=True)
        data['project']['facts']=before.pre_draft.facts.model_dump(by_alias=True)
        for region in data['project']['document']['regions']:region['blocks']=[]
        before=WorkspaceV7.model_validate(data)
    store=RichProjectStore(tmp_path/'first');store.save(before,{(before.project_id,key):value for key,value in sources.items()},{})
    loaded,failures,_=RichProjectStore(tmp_path/'first').load_all();assert not failures
    recovered=loaded[before.project_id][0];assert canonical((recovered.project or recovered.pre_draft).template_package)==exact
    moved,originals,artifacts,images=open_rich_archive(export_rich_archive(recovered,sources,{},{}),'new-owner')
    restored=(moved.project or moved.pre_draft).template_package
    assert canonical(restored)==exact and originals==sources and not artifacts and not images
    assert verify_package(restored)==captured
