"""Exact authored references and positive marks resolve without paragraph-style loss."""

from io import BytesIO
from decimal import localcontext
import math

from fontTools.ttLib import TTFont
import pytest
import yaml

from packages.resume_core.models.template_document import PresentedHyperlink,PresentedText,TemplateParagraphBlock
from packages.resume_core.rendering.captured_styles import CapturedStyleResolver
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.templates.materialize_nodes import reference
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.test_captured_assets import changed_asset,package
from tests.templates.test_captured_fonts import changed_font


@pytest.fixture(scope='module')
def captured():return package()


def paragraph(captured,token='body',text='Exact text'):
    ref=reference(captured,'identity',token,'style-fixture')
    return TemplateParagraphBlock(type='paragraph',id='styled-paragraph',revision=1,props={},
        content=[PresentedText(type='text',text=text,styles={},presentation=None)],children=[],
        provenance=[],presentation=ref)


def test_absent_inline_ref_inherits_block_overrides_but_explicit_same_token_does_not(captured):
    block=paragraph(captured);inline=block.content[0];resolver=CapturedStyleResolver(captured)
    explicit=block.presentation.model_copy(deep=True)
    block.presentation.overrides.font='black';block.presentation.overrides.size=24
    inherited=resolver.run(block,inline)
    assert inherited.selection.font.weight==900 and inherited.size==24
    inline.presentation=explicit
    own=resolver.run(block,inline)
    assert own.selection.font.weight==300 and own.size==10
    inline.presentation.overrides.size=14
    assert resolver.run(block,inline).size==14
    assert resolver.paragraph(block)[0]==pytest.approx(12.57*14/10)


def test_merged_distinct_inline_refs_keep_font_and_size_while_paragraph_alignment_stays_leading(captured):
    block=paragraph(captured,'body');resolver=CapturedStyleResolver(captured)
    other=reference(captured,'identity','name','other-item')
    other.overrides.alignment='right';other.overrides.size=26
    block.content.append(PresentedText(type='text',text='Different title',styles={},presentation=other))
    block.props.alignment='center';block.presentation.overrides.alignment='justify'
    first,second=[resolver.run(block,span) for span in block.content]
    assert (first.selection.font.weight,first.size)==(300,10)
    assert (second.selection.font.weight,second.size)==(900,26)
    height,alignment=resolver.paragraph(block)
    assert height==pytest.approx(22.6*26/18) and alignment=='justify'
    block.presentation.overrides.alignment=None
    assert resolver.paragraph(block)[1]=='center'


def test_positive_marks_follow_nullable_presentation_overrides(captured):
    block=paragraph(captured,'name');span=block.content[0];resolver=CapturedStyleResolver(captured)
    base=resolver.run(block,span);assert base.selection.font.weight==900 and not base.selection.italic
    block.presentation.overrides.bold=False;block.presentation.overrides.italic=False
    assert resolver.run(block,span).selection.font.weight==400
    span.styles.bold=True;span.styles.italic=True;span.styles.underline=True;span.styles.strike=True
    styled=resolver.run(block,span)
    assert styled.selection.font.weight==700 and styled.selection.italic
    assert styled.underline and styled.strike


def test_color_and_background_precedence_are_explicit_and_do_not_infer_tag_highlights(captured):
    block=paragraph(captured);span=block.content[0];resolver=CapturedStyleResolver(captured)
    assert resolver.run(block,span).color=='#000000' and resolver.run(block,span).background is None
    block.props.text_color='#112233';block.props.background_color='#334455'
    assert (resolver.run(block,span).color,resolver.run(block,span).background)==('#112233','#334455')
    block.presentation.overrides.color='#445566'
    assert resolver.run(block,span).color=='#445566'
    span.styles.text_color='#778899';span.styles.background_color='#99aabb'
    assert (resolver.run(block,span).color,resolver.run(block,span).background)==('#778899','#99aabb')
    span.styles.text_color='default';span.presentation=reference(captured,'identity','support','own')
    assert resolver.run(block,span).color=='#112233'


def test_empty_paragraph_uses_block_style_and_mixed_runs_take_largest_scaled_height(captured):
    block=paragraph(captured,text='');resolver=CapturedStyleResolver(captured)
    block.presentation.overrides.size=20
    assert resolver.paragraph(block)[0]==pytest.approx(25.14)
    block.content=[];assert resolver.paragraph(block)[0]==pytest.approx(25.14)
    small=reference(captured,'identity','body','small');small.overrides.size=8
    large=reference(captured,'identity','profession','large');large.overrides.size=32
    block.content=[PresentedText(type='text',text='small',styles={},presentation=small),
        PresentedText(type='text',text='large',styles={},presentation=large)]
    assert resolver.paragraph(block)[0]==pytest.approx(40.2)


def test_unemitted_paragraph_default_face_is_not_a_used_font_requirement(captured):
    changed=changed_asset(captured,captured.recipe.style.fonts['black'],content=b'unsupported unused font')
    block=paragraph(changed);span=block.content[0]
    span.presentation=block.presentation.model_copy(deep=True)
    block.presentation.overrides.font='black'
    resolver=CapturedStyleResolver(changed)
    assert resolver.paragraph(block)[0]==pytest.approx(12.57)
    block.content=[]
    with pytest.raises(RenderFailure,match='FONT_MISMATCH'):resolver.paragraph(block)


def test_unknown_font_reference_is_invalid_even_when_its_default_face_is_not_emitted(captured):
    block=paragraph(captured);span=block.content[0];span.presentation=block.presentation.model_copy(deep=True)
    block.presentation.overrides.font='unknown-font-token';resolver=CapturedStyleResolver(captured)
    with pytest.raises(RenderFailure,match='RICH_EXPORT_UNSUPPORTED'):resolver.run(block,span)
    with pytest.raises(RenderFailure,match='RICH_EXPORT_UNSUPPORTED'):resolver.paragraph(block)


def test_scaled_lineheight_does_not_overflow_a_representable_finite_result(captured):
    block=paragraph(captured);block.presentation.overrides.size=1e308
    block=TemplateParagraphBlock.model_validate(block.model_dump(by_alias=True))
    resolved=CapturedStyleResolver(captured).run(block,block.content[0])
    assert math.isfinite(resolved.line_height) and resolved.line_height==pytest.approx(1.257e308)


@pytest.mark.parametrize(('base_size','height','size'),[(1e-308,1e308,1e308),(1e308,5e-324,5e-324)])
def test_unrepresentable_scaled_lineheight_fails_explicitly(captured,base_size,height,size):
    config=captured.definition.model_dump(mode='json',by_alias=True)
    config['style']['text']['body'].update(size=base_size,line_height=height)
    changed=compile_bytes(yaml.safe_dump(config).encode(),BUNDLED_TEMPLATE.parent,original_format='yaml')
    block=paragraph(changed);block.presentation.overrides.size=size
    with pytest.raises(RenderFailure,match='RICH_EXPORT_UNSUPPORTED'):
        CapturedStyleResolver(changed).run(block,block.content[0])


def test_scaled_lineheight_is_independent_of_the_ambient_decimal_context(captured):
    block=paragraph(captured);block.presentation.overrides.size=20
    with localcontext() as context:
        context.prec=2
        resolved=CapturedStyleResolver(captured).run(block,block.content[0])
    assert resolved.line_height==pytest.approx(25.14)


@pytest.mark.parametrize('damage',['font','style','view','package','node','code','link'])
def test_unsupported_reference_or_inline_font_capability_fails_explicitly(captured,damage):
    block=paragraph(captured);span=block.content[0];resolver=CapturedStyleResolver(captured)
    if damage=='font':block.presentation.overrides.font='unknown-font'
    elif damage=='style':block.presentation.style_token='unknown-style'
    elif damage=='view':block.presentation.view_key='unknown-view'
    elif damage=='package':block.presentation.package_hash='f'*64
    elif damage=='node':block.presentation.node_index=9999
    elif damage=='code':span.styles.code=True
    else:
        # A link child is read with the link's presentation, which here names an unknown style.
        link=block.presentation.model_copy(update={'style_token':'unknown-style'})
        block.content=[PresentedHyperlink(type='link',href='https://example.invalid',content=[span],presentation=link)]
    with pytest.raises(RenderFailure):resolver.paragraph(block)


def test_actual_emitted_common_text_and_structural_controls_are_preserved(captured):
    text='Русский текст, Ελληνικά: 2020–2023 • mail@example.test\n\r\t'
    block=paragraph(captured,text=text);resolver=CapturedStyleResolver(captured)
    assert resolver.run(block,block.content[0]).selection.font.weight==300
    assert block.content[0].text==text


@pytest.mark.parametrize('text',['e\u0301','a\ufe0f','a\u200d','a\u202e','a\x00','a\ud800'])
def test_combining_variation_formatting_and_control_sequences_fail_without_rewriting(captured,text):
    block=paragraph(captured,text=text);resolver=CapturedStyleResolver(captured)
    with pytest.raises(RenderFailure,match='RICH_EXPORT_UNSUPPORTED'):resolver.run(block,block.content[0])
    assert block.content[0].text==text


def test_missing_or_zero_glyph_mapping_fails_even_when_package_and_font_hashes_are_valid(captured):
    def zero(font):
        for table in font['cmap'].tables:
            if table.isUnicode():table.cmap[ord('A')]='.notdef'
    changed=changed_font(captured,'light',zero)
    block=paragraph(changed,text='A');resolver=CapturedStyleResolver(changed)
    with pytest.raises(RenderFailure,match='FONT_UNAVAILABLE'):resolver.run(block,block.content[0])
    missing=paragraph(captured,text='Missing \U0010ffff')
    with pytest.raises(RenderFailure,match='FONT_UNAVAILABLE'):
        CapturedStyleResolver(captured).run(missing,missing.content[0])


def test_generated_text_must_be_checked_against_its_actual_selected_face(captured):
    block=paragraph(captured);resolver=CapturedStyleResolver(captured)
    selection=resolver.run(block,block.content[0]).selection
    resolver.validate_text(selection,'1. • — mail@example.com')
    with pytest.raises(RenderFailure,match='FONT_UNAVAILABLE'):resolver.validate_text(selection,'Missing \U0010ffff')
    with TTFont(BytesIO(selection.font.content)) as font:
        assert ord('•') in font.getBestCmap()


def test_resolver_owns_style_and_font_metadata_after_capture(captured):
    mutable=captured.model_copy(deep=True);block=paragraph(mutable);resolver=CapturedStyleResolver(mutable)
    mutable.recipe.style.text['body'].size=99;mutable.recipe.style.colors['ink']='#123456'
    resolved=resolver.run(block,block.content[0])
    assert resolved.size==10 and resolved.color=='#000000'


@pytest.mark.parametrize('text',['soft\u00adhyphen','zero\u200bwidth','\ufeffbom','\u00ad\u200b\ufeff'])
def test_invisible_characters_without_content_do_not_refuse_their_block(captured,text):
    block=paragraph(captured,text=text);resolver=CapturedStyleResolver(captured)
    assert resolver.run(block,block.content[0]).selection.font.weight==300
    assert resolver.paragraph(block)
    assert block.content[0].text==text
