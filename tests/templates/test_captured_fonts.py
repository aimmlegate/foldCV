"""Authored marks resolve exact captured faces without synthetic or host fonts."""

import base64
from io import BytesIO
import json

from fontTools.ttLib import TTFont,newTable
import pytest

from packages.resume_core.rendering.captured_assets import load_captured_assets
from packages.resume_core.rendering.captured_fonts import CapturedFontResolver,FontRequest
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.templates.compiler import canonical,compile_bytes,sha256
from packages.resume_core.templates.loading import load_definition
from packages.resume_core.templates.models import TemplatePackage
from packages.resume_core.templates.store import BUNDLED_TEMPLATE,TemplateStore
from tests.templates.test_captured_assets import changed_asset,package


@pytest.fixture(scope='module')
def captured():return package()


def changed_font(captured,token,mutate):
    identifier=captured.recipe.style.fonts[token]
    asset=next(value for value in captured.assets if value.id==identifier);output=BytesIO()
    with TTFont(BytesIO(base64.b64decode(asset.bytes_base64))) as font:
        mutate(font);font.save(output)
    return changed_asset(captured,identifier,content=output.getvalue())


@pytest.mark.parametrize(('token','weight','italic'),[
    ('light',300,False),('regular',400,False),('semibold',600,False),('bold',700,False),('black',900,False),
    ('light_italic',300,True),('italic',400,True),('semibold_italic',600,True),
    ('bold_italic',700,True),('black_italic',900,True),
])
def test_default_false_marks_preserve_exact_base_asset(captured,token,weight,italic):
    selected=CapturedFontResolver(captured).select(FontRequest(token,mark_bold=False,mark_italic=False))
    asset=next(value for value in captured.assets if value.id==captured.recipe.style.fonts[token])
    assert selected.font.asset_id==asset.id and selected.font.sha256==asset.sha256
    assert selected.font.content==base64.b64decode(asset.bytes_base64)
    assert (selected.weight,selected.italic)==(weight,italic)


@pytest.mark.parametrize(('font_request','expected'),[
    (FontRequest('light',mark_italic=True),'light_italic'),
    (FontRequest('semibold',mark_italic=True),'semibold_italic'),
    (FontRequest('black',mark_italic=True),'black_italic'),
    (FontRequest('black',mark_bold=True),'black'),
    (FontRequest('light',mark_bold=True,mark_italic=True),'bold_italic'),
    (FontRequest('black_italic',bold=False),'italic'),
    (FontRequest('black_italic',italic=False),'black'),
    (FontRequest('black_italic',bold=False,italic=False),'regular'),
    (FontRequest('black',bold=False,italic=False,mark_bold=True,mark_italic=True),'bold_italic'),
    (FontRequest('semibold_italic',italic=False,mark_italic=True),'semibold_italic'),
])
def test_nullable_overrides_then_positive_inline_marks_select_exact_face(captured,font_request,expected):
    selected=CapturedFontResolver(captured).select(font_request)
    assert selected.font.asset_id==captured.recipe.style.fonts[expected]
    assert selected.font.typographic_family=='Source Sans Pro'


def test_mixed_release_versions_are_explicit_metadata_evidence_only(captured):
    resolver=CapturedFontResolver(captured)
    roman=resolver.select(FontRequest('light')).font
    italic=resolver.select(FontRequest('light',mark_italic=True)).font
    with TTFont(BytesIO(roman.content)) as font:assert font['name'].getDebugName(5).startswith('Version 2.045;')
    with TTFont(BytesIO(italic.content)) as font:assert font['name'].getDebugName(5).startswith('Version 1.095;')
    assert roman.family==italic.family=='Source Sans Pro Light'
    assert roman.typographic_family==italic.typographic_family=='Source Sans Pro'
    assert roman.weight==italic.weight==300 and not roman.italic and italic.italic


def test_new_italic_assets_have_exact_upstream_hashes_and_embedding_rights(captured):
    root=BUNDLED_TEMPLATE.parent/'assets';provenance=json.loads((root/'source-sans-provenance.json').read_text())
    assert provenance['commit']=='ce77773581f4d454f0fa985c073bb25c721bfcf5'
    assert sha256((root/provenance['license']['path']).read_bytes())==provenance['license']['sha256']
    assert 'SIL OPEN FONT LICENSE Version 1.1' in (root/provenance['license']['path']).read_text()
    license=next(asset for asset in captured.assets if asset.id=='source-sans-license')
    assert base64.b64decode(license.bytes_base64)==(root/provenance['license']['path']).read_bytes()
    retained=next(asset for asset in captured.assets if asset.id=='source-sans-provenance')
    assert json.loads(base64.b64decode(retained.bytes_base64))==provenance
    assert len(provenance['files'])==5
    for name,source in provenance['files'].items():
        asset=next(value for value in captured.assets if value.path=='assets/'+name)
        assert (asset.sha256,asset.size)==(source['sha256'],source['size'])
        font=load_captured_assets(captured,[next(token for token,value in captured.recipe.style.fonts.items()
            if value==asset.id)]).fonts
        assert next(iter(font.values())).embedding_rights==0


@pytest.mark.parametrize('damage',['conflict','blank','unsupported_encoding','weight_zero','weight_high','variable'])
def test_invalid_typographic_family_weight_and_variable_font_reject(captured,damage):
    def mutate(font):
        if damage=='conflict':
            font['name'].setName('Conflicting family',16,3,10,0x0409)
        elif damage=='blank':font['name'].setName('',16,3,1,0x0409)
        elif damage=='unsupported_encoding':
            font['name'].names=[record for record in font['name'].names if record.nameID!=16]
            font['name'].setName('Unsupported family',16,2,0,1)
        elif damage.startswith('weight'):font['OS/2'].usWeightClass=0 if damage=='weight_zero' else 1001
        else:
            variable=newTable('fvar');variable.axes=[];variable.instances=[];font['fvar']=variable
    changed=changed_font(captured,'light',mutate)
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):
        CapturedFontResolver(changed).select(FontRequest('light'))


def test_family_falls_back_to_legacy_name_only_when_id16_is_absent(captured):
    regular=CapturedFontResolver(captured).select(FontRequest('regular')).font
    assert regular.typographic_family==regular.family=='Source Sans Pro'
    def remove(font):font['name'].names=[record for record in font['name'].names if record.nameID!=16]
    light=CapturedFontResolver(changed_font(captured,'light',remove)).select(FontRequest('light')).font
    assert light.typographic_family==light.family=='Source Sans Pro Light'


def test_identical_aliases_deduplicate_but_unchanged_base_keeps_its_own_asset_id(captured):
    source=next(asset for asset in captured.assets if asset.id==captured.recipe.style.fonts['bold_italic'])
    aliased=changed_asset(captured,captured.recipe.style.fonts['black_italic'],content=base64.b64decode(source.bytes_base64))
    resolver=CapturedFontResolver(aliased)
    selected=resolver.select(FontRequest('light',mark_bold=True,mark_italic=True))
    assert selected.font.sha256==source.sha256
    base=resolver.select(FontRequest('black_italic'))
    assert base.font.asset_id==captured.recipe.style.fonts['black_italic']
    assert base.font.sha256==selected.font.sha256


def test_different_byte_matching_faces_are_ambiguous_but_do_not_replace_unchanged_base(captured):
    source=next(asset for asset in captured.assets if asset.id==captured.recipe.style.fonts['bold_italic'])
    aliased=changed_asset(captured,captured.recipe.style.fonts['black_italic'],content=base64.b64decode(source.bytes_base64))
    changed=changed_font(aliased,'black_italic',lambda font:setattr(font['OS/2'],'fsType',0x0100))
    resolver=CapturedFontResolver(changed)
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):
        resolver.select(FontRequest('light',mark_bold=True,mark_italic=True))
    assert resolver.select(FontRequest('bold_italic')).font.asset_id==source.id
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):resolver.select(FontRequest('black_italic'))


def test_invalid_unused_font_does_not_block_a_valid_requested_face(captured):
    changed=changed_asset(captured,captured.recipe.style.fonts['black_italic'],content=b'unused unsupported face')
    resolver=CapturedFontResolver(changed)
    assert resolver.select(FontRequest('regular',mark_italic=True)).font.asset_id==captured.recipe.style.fonts['italic']
    with pytest.raises(RenderFailure,match='FONT_UNAVAILABLE'):
        resolver.select(FontRequest('black',mark_italic=True))


def test_resolver_owns_its_captured_bytes_and_rejects_unknown_tokens(captured):
    mutable=captured.model_copy(deep=True);resolver=CapturedFontResolver(mutable)
    identifier=mutable.recipe.style.fonts['regular'];asset=next(value for value in mutable.assets if value.id==identifier)
    original=asset.sha256;asset.bytes_base64=base64.b64encode(b'changed after capture').decode()
    mutable.recipe.style.fonts['regular']='missing'
    assert resolver.select(FontRequest('regular')).font.sha256==original
    with pytest.raises(RenderFailure,match='FONT_UNAVAILABLE'):resolver.select(FontRequest('unknown'))


def test_retained_package_stays_exact_and_missing_face_rejects_after_new_template_activates(captured,tmp_path):
    config=load_definition(BUNDLED_TEMPLATE.read_bytes())
    config['template']['revision']='pre-italic-fixture'
    removed={value for token,value in config['style']['fonts'].items() if 'italic' in token}
    config['style']['fonts']={token:value for token,value in config['style']['fonts'].items() if value not in removed}
    config['assets']=[asset for asset in config['assets'] if asset['id'] not in removed]
    old=compile_bytes(json.dumps(config).encode(),BUNDLED_TEMPLATE.parent,original_format='json')
    before=canonical(old);store=TemplateStore(tmp_path);store.activate(old);store.activate(captured)
    retained=TemplatePackage.model_validate_json((store.root/old.package_hash/'package.json').read_bytes())
    assert canonical(retained)==before and canonical(old)==before
    resolver=CapturedFontResolver(old)
    assert resolver.select(FontRequest('light')).font.asset_id==old.recipe.style.fonts['light']
    with pytest.raises(RenderFailure,match='FONT_UNAVAILABLE'):resolver.select(FontRequest('light',mark_italic=True))
