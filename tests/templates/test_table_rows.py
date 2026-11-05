"""Key-value table rows (D143): a node or a whole view opens a row with a label from the template; rows materialize as
sections, the plan labels them and the DOCX writes one table per run of rows."""

import json

import pytest

from packages.resume_core.models.template_document import TemplateSectionBlock
from packages.resume_core.models.template_render import TemplateRenderRequestV1
from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
from packages.resume_core.importing.template_assembly import assemble_template
from packages.resume_core.responses.template_export import capture_export, snapshot_identity
from packages.resume_core.editing.template_panel_creation import _rowed
from packages.resume_core.editing.template_panel_lines import line_container, row_start
from packages.resume_core.editing.template_preparation_panel import restore_view
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.materialize_nodes import reference
from packages.resume_core.templates.presentation import project_presentation
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.employment_fixtures import employment_package, employment_proposal, employment_source
from tests.templates.pipeline_fixtures import source_draft
from tests.templates.test_builtin_admission import accept, proposed_from
from tests.templates.test_captured_docx import NS, emitted, xml

CARDS = {'label_width': 110, 'label_style': 'emphasis', 'label_background': 'band', 'border_width': 0.75,
    'border_color': 'band', 'padding_x': 4, 'padding_y': 3}
LABELS = {1: 'Period', 2: 'Technologies', 3: 'Description', 4: 'Role', 5: 'Tasks', 6: 'Results'}


def config():
    return employment_package().definition.model_dump(mode='json', by_alias=True)


def compile_config(value):
    return compile_bytes(json.dumps(value).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def node_rows():
    """The employment view with a row per node after the company line, in a bordered card with grey labels."""
    value = config()
    value['style']['tables'] = {'cards': dict(CARDS)}
    value['style']['text']['project']['alignment'] = 'center'
    view = value['blocks'][0]['view']
    view['table'] = 'cards'
    for index, node in enumerate(view['nodes']):
        if index in LABELS:
            node['row'] = {'en': LABELS[index]}
    return value


def block_row():
    """The whole employment view as one row under its heading, ending with its item gap."""
    value = config()
    value['style']['tables'] = {'box': {'label_width': 0, 'label_style': 'body', 'background': 'band', 'border_width': 0,
        'padding_x': 6, 'padding_y': 4}}
    view = value['blocks'][0]['view']
    view.update(table='box', row={}, heading='plain', heading_style='project', item_gap=9)
    return value


def materialized(package):
    src, _raw = employment_source('F01')
    operation, facts, proposed, _package, _src = proposed_from(package, src, employment_proposal(src), allow_text_rewrite=True)
    operation, facts = accept(operation, facts, proposed, package, src, [])
    return assemble_template(source_draft(operation, facts, captured=package, src=src), operation)


def outline(blocks):
    return [(block.type, getattr(block.props, 'presentation', None), block.presentation.node_index, outline(block.children))
        for block in blocks]


def rendered(workspace, tmp_path):
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    out = tmp_path / ('render-' + str(len(list(tmp_path.glob('render-*')))))
    out.mkdir()
    return xml(render_captured_docx(request, out))


class Allocator:
    def __init__(self):
        self.count = 0

    def allocate(self, kind, parts):
        self.count += 1
        return f'{kind}-{self.count}'


@pytest.mark.parametrize('damage', ['no_table', 'unknown_table', 'header', 'both', 'border_color', 'label_style',
    'heading_style', 'focus_row'])
def test_rows_need_a_declared_table_style_and_valid_references(damage):
    value = node_rows()
    view = value['blocks'][0]['view']
    if damage == 'no_table':
        del view['table']
    elif damage == 'unknown_table':
        view['table'] = 'missing'
    elif damage == 'header':
        value['blocks'][0]['placement']['region'] = 'header'
    elif damage == 'both':
        view['row'] = {'en': 'Jobs'}
    elif damage == 'border_color':
        del value['style']['tables']['cards']['border_color']
    elif damage == 'label_style':
        value['style']['tables']['cards']['label_style'] = 'missing'
    elif damage == 'heading_style':
        view['heading_style'] = 'missing'
    else:
        view['nodes'].append({'type': 'focus_entry', 'name_field': '/company', 'experience_field': '/role', 'style': 'body',
            'row': {'en': 'Focus'}})
    with pytest.raises((SchemaFailure, ValueError)):
        compile_config(value)
    # The capabilities name what a renderer must know; a template without rows declares none of it.
    package = compile_config(node_rows())
    assert {'tables', 'style_alignment'} <= set(package.recipe.capabilities)
    assert not {'tables', 'style_alignment', 'node_styles', 'heading_styles'} & set(compile_config(config()).recipe.capabilities)


def test_node_rows_materialize_as_row_sections_and_a_row_without_content_is_left_out():
    workspace = materialized(compile_config(node_rows()))
    [section] = [block for block in workspace.project.document.regions[2].blocks if block.type == 'section']
    shape = outline(section.children)
    # The company line stays above the table; the description row shows nothing in F01, so it is not there.
    assert shape[0] == ('paragraph', None, 0, [])
    rows = [(presentation, index, [child[0] for child in children]) for kind, presentation, index, children in shape[1:]]
    assert [row[:2] for row in rows] == [('row', 1), ('row', 2), ('row', 4), ('row', 5), ('row', 6)]
    assert rows[3][2] == ['paragraph', 'bullet_list'] and all(isinstance(child, TemplateSectionBlock)
        and child.props.record_id is None for child in section.children[1:])
    plan = project_presentation(workspace)['editor']
    entries = [plan['blocks'][child.id] for child in section.children[1:]]
    assert [entry['row'] for entry in entries] == [
        {'table': 'cards', 'label': 'Period', 'first': True, 'last': False},
        {'table': 'cards', 'label': 'Technologies', 'first': False, 'last': False},
        {'table': 'cards', 'label': 'Role', 'first': False, 'last': False},
        {'table': 'cards', 'label': 'Tasks', 'first': False, 'last': False},
        {'table': 'cards', 'label': 'Results', 'first': False, 'last': True}]
    # A row's style is its label's, so the editor draws the label in it; the company line is centered by its style.
    assert {plan['styles'][entry['style']]['faces']['regular'] for entry in entries} == {'SourceSansPro-Bold'}
    assert plan['styles'][plan['blocks'][section.children[0].id]['style']]['alignment'] == 'center'


def test_the_docx_writes_the_rows_as_one_bordered_table_with_grey_labels_and_cell_margins(tmp_path):
    workspace = materialized(compile_config(node_rows()))
    tree = rendered(workspace, tmp_path)
    tables = tree.xpath('//w:tbl', namespaces=NS)
    # The layout table of the two columns, then the card inside the main column.
    assert len(tables) == 2
    card = tables[1]
    assert card.xpath('w:tblGrid/w:gridCol/@w:w', namespaces=NS)[0] == '2200'
    assert card.xpath('w:tblPr/w:tblBorders/w:insideH/@w:sz', namespaces=NS) == ['6']
    assert card.xpath('w:tblPr/w:tblBorders/w:top/@w:color', namespaces=NS) == ['EFEFEF']
    assert card.xpath('w:tblPr/w:tblCellMar/w:left/@w:w', namespaces=NS) == ['80']
    rows = card.xpath('w:tr', namespaces=NS)
    assert [emitted(row.xpath('w:tc', namespaces=NS)[0]) for row in rows] == ['Period', 'Technologies', 'Role', 'Tasks', 'Results']
    assert all(row.xpath('w:tc[1]/w:tcPr/w:shd/@w:fill', namespaces=NS) == ['EFEFEF'] for row in rows)
    assert emitted(rows[3].xpath('w:tc', namespaces=NS)[1]).startswith('Tasks:')
    assert rows[3].xpath('w:tc[2]//w:numPr', namespaces=NS)
    # Every cell ends with a paragraph, and the company line is centered.
    assert all(cell[-1].tag.endswith('}p') for row in rows for cell in row.xpath('w:tc', namespaces=NS))
    company = next(paragraph for paragraph in tree.xpath('//w:p', namespaces=NS) if emitted(paragraph) == 'Example Labs')
    assert company.xpath('w:pPr/w:jc/@w:val', namespaces=NS) == ['center']


def test_a_whole_block_row_wraps_its_entries_under_the_heading_and_ends_with_its_gap(tmp_path):
    workspace = materialized(compile_config(block_row()))
    main = workspace.project.document.regions[2].blocks
    assert [(block.type, getattr(block.props, 'presentation', None)) for block in main] == [('heading', None), ('section', 'row')]
    assert main[1].presentation.node_index is None and [child.type for child in main[1].children] == ['section']
    plan = project_presentation(workspace)['editor']
    assert plan['blocks'][main[1].id]['row'] == {'table': 'box', 'label': '', 'first': True, 'last': True, 'gap': 9}
    # The heading takes the view's own style, not the band's.
    assert main[0].presentation.style_token == 'project'
    tree = rendered(workspace, tmp_path)
    box = tree.xpath('//w:tbl', namespaces=NS)[1]
    assert len(box.xpath('w:tblGrid/w:gridCol', namespaces=NS)) == 1 and box.xpath('w:tblPr/w:tblBorders/w:top/@w:val', namespaces=NS) == ['nil']
    assert box.xpath('w:tr/w:tc/w:tcPr/w:shd/@w:fill', namespaces=NS) == ['EFEFEF']
    # No spacer inside the cell for the entry; one after the table for the view's gap, before the next content.
    cell = box.xpath('w:tr/w:tc', namespaces=NS)[0]
    assert not [paragraph for paragraph in cell.xpath('w:p', namespaces=NS) if paragraph.xpath('w:pPr/w:spacing/@w:line', namespaces=NS) == ['180']]
    following = box.getnext()
    assert following.tag.endswith('}p') and following.xpath('w:pPr/w:spacing/@w:line', namespaces=NS) == ['180']


def test_panel_lines_find_their_row_and_bring_a_removed_row_back_in_order():
    package = compile_config(node_rows())
    workspace = materialized(package)
    view = package.definition.blocks[0]
    assert [row_start(view, index) for index in range(7)] == [None, 1, 2, 3, 4, 5, 6]
    [section] = [block for block in workspace.project.document.regions[2].blocks if block.type == 'section']
    allocator = Allocator()
    period = line_container(package, section, 1, allocator)
    assert period is section.children[1] and period.presentation.node_index == 1 and allocator.count == 0
    # A line of the description node has no row yet: it gets one after the period row, before the technologies.
    description = line_container(package, section, 3, allocator)
    assert description.props.presentation == 'row' and description.presentation.node_index == 3
    assert [child.presentation.node_index for child in section.children] == [0, 1, 2, 3, 4, 5, 6]
    assert line_container(package, section, 0, allocator) is section
    # New entry lines of the panel go into rows the same way.
    lines = [section.children[0].model_copy(update={'id': f'line-{index}',
        'presentation': reference(package, view.id, 'body', 'instance', node_index=index)}) for index in (0, 1, 5, 5)]
    grouped = _rowed(package, view, lines, 'instance', allocator, ['record'])
    assert [(block.type, getattr(block.props, 'presentation', None), block.presentation.node_index) for block in grouped] == [
        ('paragraph', None, 0), ('section', 'row', 1), ('section', 'row', 5)]
    assert [child.id for child in grouped[2].children] == ['line-5', 'line-5']


def test_a_restored_whole_block_row_comes_back_inside_its_row():
    package = compile_config(block_row())
    workspace = materialized(package)
    document = workspace.project.document.model_copy(deep=True)
    view = package.definition.blocks[0]
    entry = document.regions[2].blocks[1].children[0]
    document.regions[2].blocks = []
    assert restore_view(document, package, view, [entry], Allocator(), 'employment')
    assert [(block.type, getattr(block.props, 'presentation', None)) for block in document.regions[2].blocks] == [('heading', None), ('section', 'row')]
    assert document.regions[2].blocks[1].children == [entry]
