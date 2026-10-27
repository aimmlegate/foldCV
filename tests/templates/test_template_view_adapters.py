"""Bound links and Focus entries materialize from admitted cells and export through the captured DOCX writer."""

import base64
import json
from types import SimpleNamespace

from lxml import etree
import pytest

from packages.resume_core.models.template_document import BoundLink, FieldOccurrence
from packages.resume_core.models.template_render import TemplateRenderRequestV1
from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.template_export import capture_export, snapshot_identity
from packages.resume_core.template_identity import capture_span
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.materialize_nodes import link_part, reference
from packages.resume_core.templates.presentation_plan import hyperlink_target
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.employment_fixtures import TEXT, employment_package, employment_source, object_schema
from tests.templates.test_captured_docx import NS, emitted, parts, recapture, xml
from tests.templates.template_runtime_fixtures import EmploymentFixture


FOCUS = [('Python', '10 months'), ('SQL', 'about 2.5 years'), ('UnknownTool', '7 weeks')]
URL = 'https://example.org/portfolio'


def view_package():
    config = employment_package().definition.model_dump(mode='json', by_alias=True)
    config['template'].update(id='synthetic-view-adapters', name='Links and Focus')
    config['fact_types'] += [
        {'id': 'portfolio', 'schema_version': '1', 'schema': object_schema({'name': TEXT, 'url': TEXT}),
            'builtin_kind': None, 'relations': []},
        {'id': 'focus', 'schema_version': '1', 'schema': object_schema({'technology': TEXT, 'experience': TEXT}),
            'builtin_kind': None, 'relations': []}]
    def block(identifier, semantic, fields, region, view):
        return {'id': identifier, 'mode': 'model', 'selectors': [{'kind': 'source', 'id': 'all'}],
            'content_schema': {'type': 'array', 'items': object_schema({field: TEXT for field in fields})},
            'bindings': [{'pointer': '/*/' + field, 'semantic_type': semantic, 'field': field, 'relation': None} for field in fields],
            'extract': [], 'rewrite': {'fields': [], 'instructions': []}, 'checks': [], 'depends_on': [], 'operation': None,
            'when': None, 'placement': {'region': region, 'order': 1}, 'view': view}
    config['blocks'] = [
        block('focus', 'focus', ['technology', 'experience'], 'sidebar', {'mode': 'items', 'heading': 'plain',
            'title': {'en': 'FOCUS'}, 'inset': 0, 'item_gap': 8, 'nodes': [{'type': 'focus_entry', 'name_field': '/technology',
                'experience_field': '/experience', 'style': 'emphasis', 'detail_style': 'body'}]}),
        block('portfolio', 'portfolio', ['name', 'url'], 'main', {'mode': 'items', 'heading': 'band',
            'title': {'en': 'PORTFOLIO'}, 'inset': 0, 'item_gap': 8,
            'nodes': [{'type': 'link', 'name_field': '/name', 'url_field': '/url', 'style': 'body'}]})]
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def scripted(src, focus, links):
    def span(text):
        unit = src.units[0]
        offset = unit.text.index(text)
        return capture_span(src, unit, offset, offset + len(text)).model_dump(by_alias=True)
    def items(semantic, rows):
        discoveries, fields = [], []
        for index, row in enumerate(rows):
            discoveries.append({'key': semantic + str(index), 'semanticType': semantic, 'pointer': '/' + str(index)})
            fields += [{'item': {'kind': 'discovery_key', 'key': semantic + str(index)}, 'fieldKey': key,
                'pointer': '/' + str(index) + '/' + key, 'evidence': [span(value)] if value else [], 'effectiveCellIds': []}
                for key, value in row.items()]
        return {'schemaVersion': 1, 'payload': rows, 'discoveries': discoveries, 'fields': fields,
            'lineage': [{'kind': 'add', 'parents': [], 'children': [value['key'] for value in discoveries]}] if rows else [],
            'relations': []}
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
                'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
        if value['declaration']['id'] == 'focus':
            return items('focus', [{'technology': name, 'experience': experience} for name, experience in focus])
        return items('portfolio', links)
    return script


async def published(tmp_path, *, focus=FOCUS, links=({'name': 'Portfolio', 'url': URL},)):
    src, raw = employment_source('F06')
    fixture = EmploymentFixture(tmp_path, captured=view_package(), src=src, original_bytes=raw,
        scripted=scripted(src, focus, list(links)), cap=8, fallback=False)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved'
    return fixture, fixture.current(), {src.id: raw}


def view_blocks(workspace, view):
    return [block for block in workspace.project.document.blocks() if block.presentation.view_key == view]


def text(block):
    return ''.join(child.text for part in block.content for child in (part.content if isinstance(part, BoundLink) else [part]))


def render(workspace, tmp_path, document=None):
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    if document is not None:
        request = recapture(request, document=document)
    out = tmp_path / ('render-' + str(len(list(tmp_path.glob('render-*')))))
    out.mkdir()
    return render_captured_docx(request, out)


def hyperlinks(content):
    tree, rels = xml(content), etree.fromstring(parts(content)['word/_rels/document.xml.rels'])
    targets = {child.get('Id'): (child.get('Target'), child.get('TargetMode')) for child in rels}
    return [(emitted(node), targets[node.get('{%s}id' % NS['r'])]) for node in tree.iter('{%s}hyperlink' % NS['w'])]


@pytest.mark.asyncio
@pytest.mark.parametrize(('row', 'shown', 'bound'), [
    ({'name': 'Portfolio', 'url': URL}, 'Portfolio', ('label', 'url')),
    ({'name': None, 'url': URL}, URL, ('url',)),
    ({'name': 'Portfolio', 'url': None}, 'Portfolio', ())])
async def test_link_cells_keep_label_and_url_identities_through_archive_and_docx(tmp_path, row, shown, bound):
    _fixture, workspace, originals = await published(tmp_path, links=(row,))
    [block] = [block for block in view_blocks(workspace, 'portfolio') if block.type == 'paragraph']
    assert text(block) == shown
    [part] = block.content
    records = {record.id: record for record in workspace.project.facts.extensions}
    if bound:
        assert isinstance(part, BoundLink) and part.href == URL
        assert tuple(role for role, value in [('label', part.label_binding), ('url', part.url_binding)] if value) == bound
        url_cell = next(cell for cell in records[part.url_binding.record_id].cells if cell.field_key == 'url')
        assert part.url_binding.cell_id == url_cell.id and url_cell.raw_input == URL
        # The shown occurrence is the label, or the URL itself for a URL-only record.
        child = part.content[0]
        assert isinstance(child, FieldOccurrence) and child.field_key == ('name' if row['name'] else 'url')
        assert child.occurrence_id == (part.label_binding or part.url_binding).occurrence_id
    else:
        assert isinstance(part, FieldOccurrence) and part.field_key == 'name'
    copied, *_ = open_archive_v7(write_zip(archive_payload_v7(workspace, originals, {})), 'link-transfer')
    assert copied.project.document == workspace.project.document and copied.project.facts == workspace.project.facts
    content = render(workspace, tmp_path)
    assert hyperlinks(content) == ([(shown, (URL, 'External'))] if bound else [])
    assert shown in emitted(xml(content))


@pytest.mark.asyncio
@pytest.mark.parametrize('href', ['', 'example.org/portfolio', 'javascript:alert(1)', 'https://exa mple.org'])
async def test_cleared_or_unsafe_url_exports_the_label_as_plain_text(tmp_path, href):
    _fixture, workspace, _originals = await published(tmp_path)
    document = workspace.project.document.model_copy(deep=True)
    link = next(part for block in document.blocks() for part in block.content if isinstance(part, BoundLink))
    link.href = href
    content = render(workspace, tmp_path, document)
    assert hyperlinks(content) == [] and 'Portfolio' in emitted(xml(content))
    assert link.url_binding is not None


def test_hyperlink_targets_follow_the_editor_link_rule():
    for value in ['https://example.org/a?b=1#c', 'http://example.org', 'HTTPS://Example.org', 'mailto:a@example.org']:
        assert hyperlink_target(value) == value
    for value in ['', 'example.org', 'https://', 'mailto:', 'ftp://example.org', 'https://a b', 'https://a\x00', 'javascript:x']:
        assert hyperlink_target(value) is None


def test_a_link_cell_inside_a_manual_scope_is_refused():
    cell = SimpleNamespace(id='cell', field_key='name', raw_input='Portfolio', manual_scope_id='scope')
    field = SimpleNamespace(record_id='record', item_handle='handle', cell=cell)
    ref = reference(view_package(), 'portfolio', 'body', 'instance', node_index=0)
    with pytest.raises(ValueError, match='manual edit scope'):
        link_part(ref, 'instance', [field], [], {}, set())


@pytest.mark.asyncio
async def test_focus_entries_keep_stated_durations_and_show_catalog_icons_only(tmp_path):
    _fixture, workspace, originals = await published(tmp_path)
    blocks = [block for block in view_blocks(workspace, 'focus') if block.type == 'paragraph']
    assert [text(block) for block in blocks] == [value for row in FOCUS for value in row]
    styles = [block.presentation.style_token for block in blocks]
    assert styles == ['emphasis', 'body'] * len(FOCUS)
    sections = [block for block in view_blocks(workspace, 'focus') if block.type == 'section']
    assert [len(section.children) for section in sections] == [2] * len(FOCUS)
    copied, *_ = open_archive_v7(write_zip(archive_payload_v7(workspace, originals, {})), 'focus-transfer')
    assert copied.project.document == workspace.project.document
    content = render(workspace, tmp_path)
    tree = xml(content)
    body = emitted(tree)
    positions = [body.index(value) for row in FOCUS for value in row]
    assert positions == sorted(positions) and all(body.count(value) == 1 for row in FOCUS for value in row)
    # Only Python has a catalog icon; SQL and the unknown tool stay text only.
    icons = tree.xpath('//w:body//wp:anchor', namespaces={**NS, 'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'})
    assert len(icons) == 1
    anchor = icons[0]
    position = {axis: anchor.find('{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}position' + axis)
        for axis in 'HV'}
    assert position['H'].get('relativeFrom') == 'column' and position['V'].get('relativeFrom') == 'paragraph'
    embedded = anchor.xpath('.//a:blip/@r:embed', namespaces={**NS, 'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'})
    rels = etree.fromstring(parts(content)['word/_rels/document.xml.rels'])
    target = next(child.get('Target') for child in rels if child.get('Id') == embedded[0])
    python = next(asset for asset in workspace.project.template_package.assets if asset.id == 'python')
    assert parts(content)['word/' + target] == base64.b64decode(python.bytes_base64)
    # Each entry stays on one page: its lines keep with the next; the last line does not.
    keep = {name: tree.xpath('string(//w:p[.//w:t[text()="%s"]]/w:pPr/w:keepNext/@w:val)' % name, namespaces=NS) for name in ['SQL', 'about 2.5 years']}
    assert keep['SQL'] in {'', '1', 'true', 'on'} and keep['about 2.5 years'] == '0'
    indents = {int(value) for value in tree.xpath('//w:p[.//w:t[text()="SQL" or text()="7 weeks"]]/w:pPr/w:ind/@w:left', namespaces=NS)}
    assert indents == {round(workspace.project.template_package.recipe.style.focus.text_x * 20)}


@pytest.mark.asyncio
async def test_a_missing_experience_leaves_the_name_line_only(tmp_path):
    _fixture, workspace, _originals = await published(tmp_path, focus=[('Python', None)])
    blocks = [block for block in view_blocks(workspace, 'focus') if block.type == 'paragraph']
    assert [text(block) for block in blocks] == ['Python']
    assert 'Python' in emitted(xml(render(workspace, tmp_path)))


@pytest.mark.asyncio
async def test_editor_plan_names_band_focus_icons_live_links_and_captured_faces(tmp_path):
    from packages.resume_core.template_api import TemplateProjectResponseV1
    from packages.resume_core.templates.presentation import project_presentation
    _fixture, workspace, _originals = await published(tmp_path)
    plan = project_presentation(workspace)['editor']
    blocks = {block.id: block for block in workspace.project.document.blocks()}
    assert [blocks[key].presentation.view_key for key, value in plan['blocks'].items() if value.get('band')] == ['portfolio']
    rows = [value['focus'] for value in plan['blocks'].values() if 'focus' in value]
    assert [[text(blocks[key]) for key in row['blocks']] for row in rows] == [list(row) for row in FOCUS]
    assert [row['icon'] for row in rows] == ['python', None, None] and plan['icons'] == ['python']
    [link] = [part for block in blocks.values() for part in block.content if isinstance(part, BoundLink)]
    assert [value['links'] for value in plan['blocks'].values() if 'links' in value] == [[link.label_binding.occurrence_id]]
    package = workspace.project.template_package
    faces = {asset.id for asset in package.assets if asset.role == 'font'}
    for key, style in plan['styles'].items():
        token = package.recipe.style.text[key]
        assert style['size'] == token.size and style['lineHeight'] == token.line_height
        assert style['faces']['regular'] == package.recipe.style.fonts[token.font] and set(style['faces'].values()) <= faces
    assert set(plan['fonts']) <= faces
    # The plan is part of the verified response: a changed decision is refused.
    from tests.templates.test_template_preparation import response
    value = response(workspace).model_dump(mode='json', by_alias=True)
    TemplateProjectResponseV1.model_validate(value)
    # A response stored before the plan existed stays valid; the editor then shows the plain document.
    older = {**value, 'presentation': {key: item for key, item in value['presentation'].items() if key != 'editor'}}
    assert TemplateProjectResponseV1.model_validate(older).presentation.editor is None
    first = next(iter(value['presentation']['editor']['blocks']))
    value['presentation']['editor']['blocks'][first]['band'] = True
    with pytest.raises(ValueError, match='presentation differs'):
        TemplateProjectResponseV1.model_validate(value)


@pytest.mark.asyncio
async def test_editor_plan_keeps_inline_styles_and_drops_links_that_export_as_text(tmp_path):
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from packages.resume_core.templates.presentation_plan import editor_plan
    _fixture, workspace, _originals = await published(tmp_path)
    value = workspace.model_copy(deep=True)
    link = next(part for block in value.project.document.blocks() for part in block.content if isinstance(part, BoundLink))
    link.href = 'example.org/portfolio'
    label = link.content[0]
    label.presentation = label.presentation.model_copy(update={'style_token': 'emphasis'})
    value = WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    plan = editor_plan(value.project)
    [entry] = [entry for entry in plan['blocks'].values() if 'inline' in entry]
    assert 'links' not in entry and entry['inline'] == {label.binding_id: 'emphasis'} and entry['style'] == 'body'


@pytest.mark.asyncio
async def test_editor_plan_records_literal_styles_in_utf16_units(tmp_path):
    # A literal has no binding id. An emoji outside the BMP is two UTF-16 units and one Python character.
    from packages.resume_core.models.template_document import PresentedText
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from packages.resume_core.templates.presentation_plan import editor_plan, literal_key, utf16_len
    _fixture, workspace, _originals = await published(tmp_path)
    value = workspace.model_copy(deep=True)
    block = next(block for block in value.project.document.blocks() if any(isinstance(part, BoundLink) for part in block.content))
    link = next(part for part in block.content if isinstance(part, BoundLink))
    emphasis = block.presentation.model_copy(update={'style_token': 'emphasis'})
    link.presentation = emphasis
    label = link.content[0]
    label.presentation = emphasis
    inherited = PresentedText(type='text', text='ид', styles={}, presentation=None)
    link.content = [label, inherited]
    prefix = PresentedText(type='text', text='A🙂', styles={}, presentation=emphasis)
    same = PresentedText(type='text', text='same', styles={}, presentation=block.presentation)
    empty = PresentedText(type='text', text='', styles={}, presentation=emphasis)
    plain = PresentedText(type='text', text='plain', styles={}, presentation=None)
    suffix = PresentedText(type='text', text='Z', styles={}, presentation=emphasis)
    block.content = [prefix, same, empty, plain, link, suffix]
    value = WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    plan = editor_plan(value.project)
    entry = plan['blocks'][block.id]
    assert utf16_len('A🙂') == 3 and len('A🙂') == 2
    prefix_end = utf16_len(prefix.text)
    cursor = prefix_end + utf16_len(same.text) + utf16_len(plain.text)
    label_end = cursor + utf16_len(label.text)
    inherited_end = label_end + utf16_len(inherited.text)
    suffix_end = inherited_end + utf16_len(suffix.text)
    assert entry['style'] == 'body'
    assert entry['inline'] == {
        literal_key(0, prefix_end): 'emphasis',
        label.binding_id: 'emphasis',
        literal_key(label_end, inherited_end): 'emphasis',
        literal_key(inherited_end, suffix_end): 'emphasis'}
    assert literal_key(cursor, label_end) not in entry['inline']
    assert literal_key(prefix_end, prefix_end + utf16_len(same.text)) not in entry['inline']
