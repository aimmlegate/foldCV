"""Captured renderer assets validate exact bytes and editable font permissions."""

import base64
from copy import deepcopy
from io import BytesIO

from fontTools.ttLib import TTFont
from PIL import Image
import pytest

from packages.resume_core.rendering.captured_assets import font_name,load_captured_assets
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.templates.compiler import canonical,compile_template,sha256
from packages.resume_core.templates.store import BUNDLED_TEMPLATE,package_identity,verify_package


def package():return compile_template(BUNDLED_TEMPLATE)


def changed_asset(before,identifier,*,content=None,mime=None,embedding=None):
    result=before.model_copy(deep=True)
    asset=next(value for value in result.assets if value.id==identifier)
    declaration=next(value for value in result.definition.assets if value.id==identifier)
    if content is not None:
        asset.bytes_base64=base64.b64encode(content).decode();asset.sha256=sha256(content);asset.size=len(content)
    if mime is not None:asset.mime_type=declaration.mime_type=mime
    if embedding is not None:declaration.embedding=embedding
    original=canonical(result.definition)
    result.original_format='json';result.original_base64=base64.b64encode(original).decode()
    result.original_hash=sha256(original);result.config_hash=sha256(original)
    result.package_hash=sha256(canonical(package_identity(result)))
    assert verify_package(result)==result
    return result


def test_actual_captured_fonts_and_logo_decode_and_materialize_exact_bytes(tmp_path,monkeypatch):
    captured=package();logo_id=captured.recipe.style.header.logo.asset
    def forbidden(*_args,**_kwargs):pytest.fail('captured assets must not use reference/template filesystem assets')
    monkeypatch.setattr('packages.resume_core.rendering.template.require_template',forbidden)
    monkeypatch.setattr('packages.resume_core.rendering.rich_template.require_rich_template',forbidden)
    loaded=load_captured_assets(captured,list(captured.recipe.style.fonts),logo_id)
    assert set(loaded.fonts)==set(captured.recipe.style.fonts)
    assert all(font.family and font.units_per_em>=16 for font in loaded.fonts.values())
    assert loaded.fonts['regular'].family==loaded.fonts['bold'].family
    assert not loaded.fonts['regular'].bold and loaded.fonts['bold'].bold
    assert loaded.fonts['regular'].full_name!=loaded.fonts['bold'].full_name
    assert loaded.logo.width>0 and loaded.logo.height>0
    paths=loaded.materialize(tmp_path)
    for font in loaded.fonts.values():
        assert paths[font.asset_id].read_bytes()==font.content
        assert paths[font.asset_id].resolve().is_relative_to(tmp_path.resolve())
    assert paths[logo_id].read_bytes()==loaded.logo.content
    assert len(list((tmp_path/'captured-assets').iterdir()))==len(set(paths.values()))
    with pytest.raises(RenderFailure,match='ASSET_UNAVAILABLE'):loaded.materialize(tmp_path)


@pytest.mark.parametrize('rights',[0,0x0008,0x0100,0x0108])
def test_full_font_embedding_honors_editable_or_installable_rights_and_no_subsetting(rights):
    captured=package();token=next(iter(captured.recipe.style.fonts));identifier=captured.recipe.style.fonts[token]
    asset=next(value for value in captured.assets if value.id==identifier)
    output=BytesIO()
    with TTFont(BytesIO(base64.b64decode(asset.bytes_base64))) as font:
        font['OS/2'].fsType=rights;font.save(output)
    changed=changed_asset(captured,identifier,content=output.getvalue())
    assert load_captured_assets(changed,[token]).fonts[token].embedding_rights==rights


@pytest.mark.parametrize('rights',[0x0002,0x0004,0x0200,0x000A,0x000C,0x4000])
def test_restricted_preview_bitmap_ambiguous_or_unknown_embedding_permissions_reject(rights):
    captured=package();token=next(iter(captured.recipe.style.fonts));identifier=captured.recipe.style.fonts[token]
    asset=next(value for value in captured.assets if value.id==identifier);output=BytesIO()
    with TTFont(BytesIO(base64.b64decode(asset.bytes_base64))) as font:
        font['OS/2'].fsType=rights;font.save(output)
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):
        load_captured_assets(changed_asset(captured,identifier,content=output.getvalue()),[token])


@pytest.mark.parametrize('damage',['mime','embedding','broken','opentype','missing'])
def test_selected_font_format_and_declaration_guards_are_explicit(damage):
    captured=package();token=next(iter(captured.recipe.style.fonts));identifier=captured.recipe.style.fonts[token]
    if damage=='mime':captured=changed_asset(captured,identifier,mime='application/octet-stream')
    elif damage=='embedding':captured=changed_asset(captured,identifier,embedding='not_applicable')
    elif damage=='broken':captured=changed_asset(captured,identifier,content=b'\x00\x01\x00\x00broken sfnt')
    elif damage=='opentype':captured=changed_asset(captured,identifier,content=b'OTTOunsupported CFF')
    else:token='missing-font-token'
    with pytest.raises(RenderFailure):load_captured_assets(captured,[token])


@pytest.mark.parametrize('damage',['mime','not_png','truncated','missing'])
def test_selected_logo_requires_exact_png_bytes(damage):
    captured=package();identifier=captured.recipe.style.header.logo.asset
    if damage=='mime':captured=changed_asset(captured,identifier,mime='image/jpeg')
    elif damage=='not_png':
        output=BytesIO();Image.new('RGB',(2,2)).save(output,format='JPEG')
        captured=changed_asset(captured,identifier,content=output.getvalue())
    elif damage=='truncated':captured=changed_asset(captured,identifier,content=b'\x89PNG\r\n\x1a\ntruncated')
    else:identifier='missing-logo'
    with pytest.raises(RenderFailure):load_captured_assets(captured,[],identifier)


def test_unused_font_format_is_not_a_used_rendering_requirement():
    captured=package();tokens=list(captured.recipe.style.fonts);unused=captured.recipe.style.fonts[tokens[-1]]
    changed=changed_asset(captured,unused,content=b'unsupported unused font bytes')
    loaded=load_captured_assets(changed,[tokens[0]])
    assert set(loaded.fonts)=={tokens[0]} and loaded.logo is None


def test_distinct_captured_fonts_cannot_share_an_ambiguous_word_face_name():
    captured=package();tokens=list(captured.recipe.style.fonts);first,last=tokens[0],tokens[-1]
    original=next(asset for asset in captured.assets if asset.id==captured.recipe.style.fonts[first])
    output=BytesIO()
    with TTFont(BytesIO(base64.b64decode(original.bytes_base64))) as font:
        font['OS/2'].fsType=0x0100;font.save(output)
    changed=changed_asset(captured,captured.recipe.style.fonts[last],content=output.getvalue())
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):load_captured_assets(changed,[first,last])
    identical=changed_asset(captured,captured.recipe.style.fonts[last],content=base64.b64decode(original.bytes_base64))
    loaded=load_captured_assets(identical,[first,last])
    assert loaded.fonts[first].family==loaded.fonts[last].family and loaded.fonts[first].sha256==loaded.fonts[last].sha256


def test_font_name_selection_is_order_independent_and_rejects_conflicting_preferred_records():
    captured=package();asset=captured.assets[0]
    asset=next(value for value in captured.assets if value.role=='font')
    with TTFont(BytesIO(base64.b64decode(asset.bytes_base64))) as font:
        table=font['name'];original=font_name(table,1);table.names.reverse()
        assert font_name(table,1)==original
        preferred=next(record for record in table.names if record.nameID==1 and record.platformID==3 and record.langID==0x0409)
        conflict=deepcopy(preferred);conflict.string='Conflicting face'.encode(conflict.getEncoding())
        table.names.append(conflict)
        with pytest.raises(ValueError,match='conflict'):font_name(table,1)


def test_font_conflicting_style_flags_reject_even_when_the_package_hashes_are_valid():
    captured=package();identifier=captured.recipe.style.fonts['regular']
    asset=next(value for value in captured.assets if value.id==identifier);output=BytesIO()
    with TTFont(BytesIO(base64.b64decode(asset.bytes_base64))) as font:
        font['OS/2'].fsSelection|=0x20;font['head'].macStyle&=~1;font.save(output)
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):
        load_captured_assets(changed_asset(captured,identifier,content=output.getvalue()),['regular'])


@pytest.mark.parametrize(('table','attribute','value'),[
    ('head','magicNumber',0),('head','tableVersion',2.0),('head','glyphDataFormat',1),
    ('hhea','tableVersion',0),('hhea','metricDataFormat',1),
    ('hhea','reserved0',1),('hhea','reserved1',1),('hhea','reserved2',1),('hhea','reserved3',1),
    ('maxp','tableVersion',0x00005000),('maxp','maxZones',3),
])
def test_rehashed_fonts_with_unsupported_required_headers_reject(table,attribute,value):
    captured=package();identifier=captured.recipe.style.fonts['regular']
    asset=next(value for value in captured.assets if value.id==identifier);output=BytesIO()
    with TTFont(BytesIO(base64.b64decode(asset.bytes_base64))) as font:
        setattr(font[table],attribute,value);font.save(output)
    changed=changed_asset(captured,identifier,content=output.getvalue())
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):load_captured_assets(changed,['regular'])


def test_materialization_rejects_symlinked_worker_or_asset_directory(tmp_path):
    captured=package();loaded=load_captured_assets(captured,[next(iter(captured.recipe.style.fonts))])
    target=tmp_path/'outside';target.mkdir();worker=tmp_path/'worker';worker.symlink_to(target,target_is_directory=True)
    with pytest.raises(RenderFailure,match='ASSET_UNAVAILABLE'):loaded.materialize(worker)
    assert not list(target.iterdir())
    normal=tmp_path/'normal';normal.mkdir();(normal/'captured-assets').symlink_to(target,target_is_directory=True)
    with pytest.raises(RenderFailure,match='ASSET_UNAVAILABLE'):loaded.materialize(normal)
    assert not list(target.iterdir())


def test_captured_envelope_hash_damage_fails_before_font_decoding():
    captured=package();captured.assets[0].bytes_base64=base64.b64encode(b'tampered').decode()
    with pytest.raises(ValueError):load_captured_assets(captured,[])
