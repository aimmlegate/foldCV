"""Captured employment uses the actual DOCX writer and exact authored snapshots."""

from io import BytesIO
from copy import deepcopy
import json
from zipfile import ZipFile

from docx.oxml.ns import qn
from lxml import etree
import pytest

from packages.resume_core.models.template_document import (PresentedText, ManualScopeSpan, TemplateParagraphBlock,
    TemplateNumberedBlock, PresentedHyperlink)
from packages.resume_core.models.template_render import TemplateRenderRequestV1, TemplateRenderAsset, presentation_value
from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
from packages.resume_core.rendering.captured_layout import half_points, native_units
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_export import capture_export, snapshot_identity
from packages.resume_core.templates.compiler import canonical, compile_bytes, sha256
from packages.resume_core.templates.materialize_nodes import reference
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.pipeline_fixtures import source_draft
from tests.templates.test_materialize import admitted

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


@pytest.fixture(scope='module')
def captured_request():
    operation, facts, package, src, _raw = admitted()
    workspace = assemble_template(source_draft(operation, facts, captured=package, src=src), operation)
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    return TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=package)


def recapture(request, *, document=None, package=None):
    document = document or request.document.model_copy(deep=True)
    package = package or request.package
    for block in document.blocks():
        block.presentation.package_hash = package.package_hash
        for part in block.content if isinstance(block.content, list) else []:
            if part.presentation is not None:
                part.presentation.package_hash = package.package_hash
    return TemplateRenderRequestV1(schemaVersion=1, renderInputVersion=1, document=document, facts=request.facts,
        documentHash=sha256(canonical(document)), factsHash=request.facts_hash,
        presentationHash=sha256(canonical(presentation_value(document, package))), package=package,
        packageHash=package.package_hash, renderer=renderer_identity(), assets=[TemplateRenderAsset(id=asset.id,
            path=asset.path, sha256=asset.sha256, size=asset.size) for asset in package.assets])


def configured(request, edit):
    value = request.package.definition.model_dump(mode='json', by_alias=True)
    edit(value)
    package = compile_bytes(json.dumps(value).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    return recapture(request, package=package)


def parts(content):
    with ZipFile(BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def xml(content, name='word/document.xml'):
    return etree.fromstring(parts(content)[name])


def emitted(node):
    return ''.join('\n' if child.tag == qn('w:br') else '\t' if child.tag == qn('w:tab') else child.text or ''
        for child in node.iter() if child.tag in {qn('w:t'), qn('w:br'), qn('w:tab')})


def test_actual_employment_preserves_text_order_geometry_and_captured_assets(captured_request, tmp_path):
    before = canonical(captured_request)
    content = render_captured_docx(captured_request, tmp_path)
    tree = xml(content)
    text = emitted(tree)
    authored = [''.join(part.text for part in block.content) for block in captured_request.document.blocks()
        if isinstance(block.content, list)]
    position = 0
    for value in authored:
        position = text.index(value, position) + len(value)
    assert 'Example Labs' in text and 'Implemented queue processing.' in text
    assert '800 ms to 500 ms' in text and '80%' not in text
    assert canonical(captured_request) == before
    assert tree.xpath('string(//w:pgSz/@w:w)', namespaces=NS) == '11920'
    assert tree.xpath('string(//w:pgMar/@w:top)', namespaces=NS) == '480'
    assert tree.xpath('//w:tblGrid/w:gridCol/@w:w', namespaces=NS) == ['2370', '105', '8895']
    assert not tree.xpath('//w:cantSplit', namespaces=NS)
    assert all(node.get(qn('w:w')) == '0' for node in tree.xpath('//w:tcMar/*', namespaces=NS))
    assert tree.xpath('//w:body/w:p/w:pPr/w:pBdr/w:bottom/@w:color', namespaces=NS) == ['888888']
    assert tree.xpath('//w:body/w:p/w:pPr/w:pBdr/w:bottom/@w:sz', namespaces=NS) == ['8']
    assert not xml(content, 'word/header1.xml').xpath('//w:pBdr', namespaces=NS)
    assert int(tree.xpath('string(//w:pgMar/@w:footer)', namespaces=NS)) > 0
    assert tree.xpath('//w:pPr/w:shd/@w:fill', namespaces=NS) == ['EFEFEF']
    assert tree.xpath('//w:pPr[w:shd]/w:ind/@w:left', namespaces=NS) == ['0']
    assert tree.xpath('//w:pPr[w:shd]/w:ind/@w:firstLine', namespaces=NS) == ['105']
    assert tree.xpath('//w:pPr[w:shd]/w:spacing/@w:line', namespaces=NS) == ['560']
    assert tree.xpath('//w:rPr/w:shd[@w:fill="EFEFEF"]', namespaces=NS)
    assert tree.xpath('//w:numPr', namespaces=NS)
    archive = parts(content)
    import base64
    assert archive['word/media/image1.png'] == base64.b64decode(next(asset.bytes_base64 for asset in captured_request.package.assets if asset.id == 'generic'))
    fonts = xml(content, 'word/fontTable.xml')
    for embed in fonts.xpath('//w:embedRegular|//w:embedBold|//w:embedItalic|//w:embedBoldItalic', namespaces=NS):
        import uuid
        key = uuid.UUID(embed.get(qn('w:fontKey')))
        rels = etree.fromstring(archive['word/_rels/fontTable.xml.rels'])
        target = next(child.get('Target') for child in rels if child.get('Id') == embed.get(qn('r:id')))
        raw = bytearray(archive['word/' + target])
        for index in range(32):
            raw[index] ^= key.bytes[::-1][index % 16]
        assert sha256(raw) in {asset.sha256 for asset in captured_request.package.assets if asset.role == 'font'}


def test_literal_field_manual_scope_marks_controls_are_exact_at_emission(captured_request, tmp_path):
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'paragraph' and block.content)
    value = 'Literal\r\nline\rlone\nnext\tend  '
    scope = ManualScopeSpan(type='manual_scope', text='Human scope', styles={'italic': True},
        scopeId='scope', occurrenceId='scope-copy', fragmentId='scope-fragment', presentation=None)
    block.content = [PresentedText(type='text', text=value, styles={'bold': True, 'underline': True,
        'strike': True, 'textColor': '#123456', 'backgroundColor': '#ABCDEF'}, presentation=None), scope]
    request = recapture(captured_request, document=document)
    content = render_captured_docx(request, tmp_path)
    tree = xml(content)
    paragraph = next(node for node in tree.iter(qn('w:p')) if 'Literal' in emitted(node))
    assert emitted(paragraph) == value.replace('\r\n', '\n').replace('\r', '\n') + 'Human scope'
    assert len(paragraph.xpath('.//w:br', namespaces=NS)) == 3
    assert len(paragraph.xpath('.//w:tab', namespaces=NS)) == 1
    assert paragraph.xpath('.//w:rPr/w:color/@w:val', namespaces=NS)[0] == '123456'
    assert paragraph.xpath('.//w:rPr/w:shd/@w:fill', namespaces=NS)[0] == 'ABCDEF'
    assert paragraph.xpath('.//w:rPr/w:u/@w:val', namespaces=NS)[0] == 'single'
    assert block.content[0].text == value


def test_changed_recipe_optional_logo_divider_footer_and_geometry(captured_request, tmp_path):
    def edit(config):
        config['style']['header'].update(logo=None, divider=None)
        config['style']['footer']['text'] = ''
        config['style']['page'].update(width=640, height=900, first_body_top=120, continuation_body_top=30, body_bottom=800)
        config['layout']['regions'][1].update(x=40, width=100)
        config['layout']['regions'][2].update(x=160, width=450)
    request = configured(captured_request, edit)
    content = render_captured_docx(request, tmp_path)
    tree = xml(content)
    assert tree.xpath('string(//w:pgSz/@w:w)', namespaces=NS) == '12800'
    assert tree.xpath('string(//w:pgMar/@w:top)', namespaces=NS) == '600'
    assert tree.xpath('//w:tblGrid/w:gridCol/@w:w', namespaces=NS) == ['2000', '400', '9000']
    assert not any(name.startswith('word/media/') for name in parts(content))
    assert not any(b'mail@example.com' in raw for name, raw in parts(content).items() if name.endswith('.xml'))


@pytest.mark.parametrize('damage', ['right_sidebar', 'negative_first_offset', 'collapsed_column', 'huge_page'])
def test_valid_but_unsupported_geometry_fails_explicitly(captured_request, tmp_path, damage):
    def edit(config):
        if damage == 'right_sidebar':
            config['layout']['regions'][1].update(x=500, width=90)
            config['layout']['regions'][2].update(x=20, width=450)
        elif damage == 'negative_first_offset':
            config['style']['page']['first_body_top'] = 10
        elif damage == 'collapsed_column':
            config['layout']['regions'][1]['width'] = 0.001
        else:
            config['style']['page']['height'] = 1e308
    request = configured(captured_request, edit)
    with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(request, tmp_path)


@pytest.mark.parametrize('size', [0.5, 10.25, 1639, 1e308, 1e-308])
def test_unsupported_native_font_sizes_fail_without_altering_authored_state(captured_request, tmp_path, size):
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'paragraph' and block.content)
    block.presentation.overrides.size = size
    for part in block.content:
        part.presentation = None
    request = recapture(captured_request, document=document)
    before = canonical(request)
    with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(request, tmp_path)
    assert canonical(request) == before


def test_native_units_use_stable_ties_and_reject_underflow_overflow():
    assert native_units(1.025) == 21
    assert half_points(1638.5) == 3277
    for value in [1e308, 0.001, float('inf')]:
        with pytest.raises(RenderFailure):
            native_units(value, positive=True)


def test_renderer_identity_and_snapshot_hashes_are_verified(captured_request, tmp_path):
    broken = captured_request.model_copy(deep=True)
    broken.renderer.sha256 = '0' * 64
    with pytest.raises(RenderFailure, match='RENDERER_MISMATCH'):
        render_captured_docx(broken, tmp_path)
    broken = captured_request.model_copy(deep=True)
    next(block for block in broken.document.blocks() if block.content).content[0].text = 'Changed after capture'
    with pytest.raises(ValueError, match='hash mismatch'):
        render_captured_docx(broken, tmp_path)


def test_converted_or_deleted_heading_is_not_recreated(captured_request, tmp_path):
    document = captured_request.document.model_copy(deep=True)
    main = document.regions[2]
    heading = next(block for block in main.blocks if block.type == 'heading')
    main.blocks.remove(heading)
    request = recapture(captured_request, document=document)
    content = render_captured_docx(request, tmp_path)
    assert 'PROJECTS' not in emitted(xml(content))
    assert not xml(content).xpath('//w:pPr/w:shd', namespaces=NS)


def header_request(request, name='Synthetic Name', profession='Backend Engineer'):
    def edit(config):
        block = deepcopy(config['blocks'][0])
        block['id'] = 'explicit-header'
        block['placement'] = {'region': 'header', 'order': 0}
        block['view'].update(heading='none', nodes=[
            {'type': 'text', 'field': '/company', 'style': 'name', 'header_slot': 'name'},
            {'type': 'text', 'field': '/role', 'style': 'profession', 'header_slot': 'profession'}])
        config['blocks'].append(block)
    request = configured(request, edit)
    document = request.document.model_copy(deep=True)
    for index, (text, token) in enumerate([(name, 'name'), (profession, 'profession')]):
        ref = reference(request.package, 'explicit-header', token, 'header-instance', node_index=index)
        document.regions[0].blocks.append(TemplateParagraphBlock(type='paragraph', id='header-' + token,
            revision=1, props={}, content=[PresentedText(type='text', text=text, styles={}, presentation=ref)],
            children=[], provenance=[], presentation=ref))
    return recapture(request, document=document)


def test_explicit_header_slots_copy_order_and_growth_move_body(captured_request, tmp_path):
    request = header_request(captured_request, name='Long Synthetic Candidate Name ' * 8)
    document = request.document.model_copy(deep=True)
    copy = document.regions[0].blocks[0].model_copy(deep=True)
    copy.id = 'copied-header-name'
    document.regions[0].blocks.append(copy)
    request = recapture(request, document=document)
    content = render_captured_docx(request, tmp_path)
    header = xml(content, 'word/header1.xml')
    actual = [emitted(node) for node in header.iter(qn('w:p')) if emitted(node)]
    assert actual == ['Long Synthetic Candidate Name ' * 8, 'Backend Engineer', 'Long Synthetic Candidate Name ' * 8]
    frames = header.xpath('//w:p[w:r/w:t]/w:pPr/w:framePr/@w:y', namespaces=NS)
    assert list(map(int, frames)) == sorted(map(int, frames))
    assert all(value == 'around' for value in header.xpath('//w:framePr/@w:wrap', namespaces=NS))
    assert not header[-1].xpath('w:pPr/w:framePr', namespaces=NS)
    body = xml(content)
    assert int(body.xpath('string(//w:body/w:p[1]/w:pPr/w:spacing/@w:line)', namespaces=NS)) > 1420


@pytest.mark.parametrize('damage', ['missing', 'mixed', 'unsupported'])
def test_actual_header_fails_explicitly_for_missing_mixed_or_unsupported_refs(captured_request, tmp_path, damage):
    request = header_request(captured_request)
    document = request.document.model_copy(deep=True)
    block = document.regions[0].blocks[0]
    if damage == 'missing':
        block.presentation = next(block for block in document.blocks() if block.type == 'paragraph' and
            block.presentation.view_key == 'employment-view').presentation.model_copy(deep=True)
        block.content[0].presentation = None
    elif damage == 'mixed':
        block.content.append(document.regions[0].blocks[1].content[0].model_copy(deep=True))
    else:
        block.content[0].styles.code = True
    request = recapture(request, document=document)
    with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(request, tmp_path)


def test_crlf_split_between_authored_runs_is_one_break(captured_request, tmp_path):
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'paragraph' and block.content)
    block.content = [PresentedText(type='text', text='First\r', styles={}, presentation=None),
        PresentedText(type='text', text='\nSecond', styles={'bold': True}, presentation=None)]
    content = render_captured_docx(recapture(captured_request, document=document), tmp_path)
    paragraph = next(node for node in xml(content).iter(qn('w:p')) if 'First' in emitted(node))
    assert emitted(paragraph) == 'First\nSecond'


def test_native_numbering_keeps_start_sequence_and_marker_style(captured_request, tmp_path):
    document = captured_request.document.model_copy(deep=True)
    source = next(block for block in document.blocks() if block.type == 'bullet_list')
    for index in range(2):
        data = source.model_dump(by_alias=True)
        data.update(type='numbered_list', id=f'numbered-{index}', props={'start': 7 if index == 0 else None},
            content=[{'type': 'text', 'text': f'Numbered item {index}', 'styles': {'bold': True}}])
        document.regions[2].blocks.append(TemplateNumberedBlock.model_validate(data))
    content = render_captured_docx(recapture(captured_request, document=document), tmp_path)
    tree = xml(content)
    paragraphs = [node for node in tree.iter(qn('w:p')) if emitted(node).startswith('Numbered item')]
    ids = [node.xpath('string(w:pPr/w:numPr/w:numId/@w:val)', namespaces=NS) for node in paragraphs]
    assert len(ids) == 2 and ids[0] == ids[1]
    numbering = xml(content, 'word/numbering.xml')
    number = numbering.xpath('w:num[@w:numId=$id]', namespaces=NS, id=ids[0])[0]
    abstract = numbering.xpath('w:abstractNum[@w:abstractNumId=$id]', namespaces=NS,
        id=number.xpath('string(w:abstractNumId/@w:val)', namespaces=NS))[0]
    assert abstract.xpath('string(.//w:start/@w:val)', namespaces=NS) == '7'
    assert abstract.xpath('string(.//w:rFonts/@w:ascii)', namespaces=NS) == 'Source Sans Pro Light'
    assert abstract.xpath('string(.//w:sz/@w:val)', namespaces=NS) == '28'
    assert abstract.xpath('string(.//w:b/@w:val)', namespaces=NS) == '0'


@pytest.mark.parametrize('href', ['https://example.invalid/a', 'example.invalid/a'])
def test_a_technical_link_exports_its_exact_target_only_when_it_is_a_web_address(captured_request, tmp_path, href):
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'paragraph' and block.content)
    block.content = [PresentedHyperlink(type='link', href=href,
        content=[PresentedText(type='text', text='Authored link', styles={})])]
    content = render_captured_docx(recapture(captured_request, document=document), tmp_path)
    links = xml(content).xpath('//w:hyperlink', namespaces=NS)
    rels = etree.fromstring(parts(content)['word/_rels/document.xml.rels'])
    assert [next(rel.get('Target') for rel in rels if rel.get('Id') == link.get(qn('r:id'))) for link in links] == (
        [href] if href.startswith('https://') else [])
    assert 'Authored link' in emitted(xml(content))


@pytest.mark.parametrize('damage', ['code', 'focus', 'missing_glyph', 'quote'])
def test_used_unsupported_capabilities_fail_without_rewriting(captured_request, tmp_path, damage):
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'paragraph' and block.content)
    if damage == 'code':
        block.content[0].styles.code = True
    elif damage == 'focus':
        next(block for block in document.blocks() if block.type == 'section').props.presentation = 'focus'
    elif damage == 'quote':
        from packages.resume_core.models.template_document import TemplateQuoteBlock
        region = document.regions[2]
        data = block.model_dump(by_alias=True)
        data['type'] = 'quote'
        replacement = TemplateQuoteBlock.model_validate(data)
        def replace_block(values):
            for index, value in enumerate(values):
                if value.id == block.id:
                    values[index] = replacement
                    return True
                if replace_block(value.children):
                    return True
        assert replace_block(region.blocks)
    else:
        block.content = [PresentedText(type='text', text='Missing \U0010ffff', styles={})]
    request = recapture(captured_request, document=document)
    before = canonical(request)
    with pytest.raises(RenderFailure, match='FONT_UNAVAILABLE' if damage == 'missing_glyph' else 'RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(request, tmp_path)
    assert canonical(request) == before


@pytest.mark.parametrize('text', ['Wrapped heading ' * 60, 'Two\nlines', 'Heading\twith tab'])
def test_wrapped_or_control_band_titles_remain_explicitly_unsupported(captured_request, tmp_path, text):
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'heading')
    block.content = [PresentedText(type='text', text=text, styles={})]
    with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(recapture(captured_request, document=document), tmp_path)


@pytest.mark.parametrize('part', ['body_line', 'band'])
def test_a_single_native_line_or_band_must_fit_the_continuation_body(captured_request, tmp_path, part):
    def edit(config):
        if part == 'body_line':
            config['style']['text']['body']['line_height'] = 900
        else:
            config['style']['section_band']['height'] = 900
    request = configured(captured_request, edit)
    before = canonical(request)
    with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(request, tmp_path)
    assert canonical(request) == before


def test_empty_spans_validate_metadata_without_selecting_unemitted_faces(captured_request, tmp_path):
    from tests.templates.test_captured_assets import changed_asset
    package = changed_asset(captured_request.package, captured_request.package.recipe.style.fonts['black'],
        content=b'unsupported unused captured font')
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'paragraph' and block.content)
    explicit = block.presentation.model_copy(deep=True)
    block.presentation.overrides.font = 'black'
    block.content = [PresentedText(type='text', text='Emitted body face', styles={}, presentation=explicit),
        PresentedText(type='text', text='', styles={}, presentation=None)]
    request = recapture(captured_request, document=document, package=package)
    assert 'Emitted body face' in emitted(xml(render_captured_docx(request, tmp_path)))


def test_empty_body_paragraph_still_requires_its_block_face(captured_request, tmp_path):
    from tests.templates.test_captured_assets import changed_asset
    package = changed_asset(captured_request.package, captured_request.package.recipe.style.fonts['black'],
        content=b'unsupported used paragraph font')
    document = captured_request.document.model_copy(deep=True)
    block = next(block for block in document.blocks() if block.type == 'paragraph' and block.content)
    block.presentation.overrides.font = 'black'
    block.content = []
    with pytest.raises(RenderFailure, match='FONT_MISMATCH'):
        render_captured_docx(recapture(captured_request, document=document, package=package), tmp_path)


@pytest.mark.parametrize('size', [30, 700])
def test_generated_marker_height_scales_and_participates_in_native_line_fit(captured_request, tmp_path, size):
    request = configured(captured_request, lambda config: config['style']['bullets'].update(marker_size=size))
    document = request.document.model_copy(deep=True)
    source = next(block for block in document.blocks() if block.type == 'bullet_list')
    data = source.model_dump(by_alias=True)
    data.update(type='numbered_list', id='marker-height', props={'start': 1},
        content=[{'type': 'text', 'text': 'Actual numbered marker', 'styles': {}}])
    document.regions[2].blocks = [TemplateNumberedBlock.model_validate(data)]
    request = recapture(request, document=document)
    if size == 700:
        with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
            render_captured_docx(request, tmp_path)
        return
    content = render_captured_docx(request, tmp_path)
    paragraph = next(node for node in xml(content).iter(qn('w:p')) if 'Actual numbered marker' in emitted(node))
    assert paragraph.xpath('string(w:pPr/w:spacing/@w:line)', namespaces=NS) == '754'
    numbering = xml(content, 'word/numbering.xml')
    assert numbering.xpath('//w:abstractNum[@w:abstractNumId="6000"]/w:lvl/w:rPr/w:sz/@w:val', namespaces=NS) == ['60']


def test_logo_containment_uses_actual_native_page_size(captured_request, tmp_path):
    def edit(config):
        config['style']['page']['width'] = 596.024
        config['style']['header']['logo'].update(x=0, top=0, width=596.024, height=400)
    with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(configured(captured_request, edit), tmp_path)


def test_region_roles_own_empty_header_requirements_with_opaque_ids(captured_request, tmp_path):
    from tests.templates.test_captured_assets import changed_asset
    package = changed_asset(captured_request.package, captured_request.package.recipe.style.fonts['black'],
        content=b'unsupported unused header font')
    document = captured_request.document.model_copy(deep=True)
    document.regions[0].id, document.regions[1].id, document.regions[2].id = 'custom-header', 'custom-sidebar', 'header'
    block = next(block for block in document.blocks() if block.type == 'paragraph').model_copy(deep=True)
    block.id, block.content, block.children = 'empty-header', [], []
    block.presentation.overrides.font = 'black'
    document.regions[0].blocks.append(block)
    request = recapture(captured_request, document=document, package=package)
    assert 'Example Labs' in emitted(xml(render_captured_docx(request, tmp_path)))


def test_body_id_cannot_bypass_role_based_native_line_fit(captured_request, tmp_path):
    request = configured(captured_request, lambda config: config['style']['text']['body'].update(line_height=900))
    document = request.document.model_copy(deep=True)
    document.regions[0].id, document.regions[2].id = 'custom-header', 'header'
    with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
        render_captured_docx(recapture(request, document=document), tmp_path)
