"""G02 for links, Focus entries and joins: edits keep field identity through Undo, transfer and DOCX."""

import json

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import BoundLink, FieldOccurrence, ManualScopeSpan
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical, compile_bytes
from packages.resume_core.templates.presentation_plan import editor_plan
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.employment_fixtures import employment_package, employment_source
from tests.templates.test_captured_docx import NS, emitted, xml
from tests.templates.test_template_employment import EmploymentFixture, scripted_employment
from tests.templates.test_template_preparation import command, proof, response
from tests.templates.test_template_view_adapters import URL, hyperlinks, published, render, text
from tests.templates.test_transactions import authorization


def request(workspace, operation, identifier):
    value = command(workspace).model_dump(by_alias=True)
    value['clientMutationId'] = value['capture']['actionId'] = identifier
    value['operations'] = [{'opId': 'op', **operation}]
    return TemplateEditPreparationV1.model_validate(value)


def edit(workspace, operation, identifier):
    prepared = prepare_edit(response(workspace), request(workspace, operation, identifier), proof())
    after = apply_rich_mutation(workspace, prepared.mutation)[0]
    assert canonical(after) == canonical(prepared.preview.workspace)
    return after


def undo(before, after, action):
    inverse = inverse_template_mutation(before, after, origin_action_id=action, mutation_id='undo-' + action,
        session_id='session', action_token=2)
    return apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))[0]


def transferred(workspace, originals):
    copied, *_ = open_rich_archive(export_rich_archive(workspace, originals, {}, {}), 'g02-transfer')
    assert copied.project.document == workspace.project.document and copied.project.facts == workspace.project.facts
    return copied


def find(workspace, wording, kind='paragraph'):
    return next(block for block in workspace.project.document.blocks() if block.type == kind and text(block) == wording)


def links(workspace):
    return [part for block in workspace.project.document.blocks() for part in block.content if isinstance(part, BoundLink)]


def text_range(block, start, end):
    return {'blockId': block.id, 'beforeRevision': block.revision, 'cellId': None, 'field': 'content', 'start': start, 'end': end}


@pytest.mark.asyncio
async def test_a_bound_link_keeps_label_and_url_identities_through_split_merge_copy_move_delete_and_undo(tmp_path):
    _fixture, workspace, originals = await published(tmp_path)
    [original] = links(workspace)
    block = find(workspace, 'Portfolio')
    # A split inside the label leaves two halves of one label occurrence, each linked to the same URL cell.
    split = edit(workspace, {'kind': 'split_block', 'blockId': block.id, 'beforeRevision': block.revision, 'offset': 4}, 'split')
    halves = [find(split, 'Port'), find(split, 'folio')]
    assert all((part.label_binding, part.url_binding, part.href) == (original.label_binding, original.url_binding, URL)
        for half in halves for part in half.content)
    assert hyperlinks(render(transferred(split, originals), tmp_path)) == [('Port', (URL, 'External')), ('folio', (URL, 'External'))]
    merged = edit(split, {'kind': 'merge_blocks', 'leadingId': halves[0].id, 'leadingRevision': halves[0].revision,
        'trailingId': halves[1].id, 'trailingRevision': halves[1].revision}, 'merge')
    assert text(find(merged, 'Portfolio')) == 'Portfolio'
    assert all((part.label_binding, part.url_binding) == (original.label_binding, original.url_binding) for part in links(merged))
    # A complete copy shows the same two cells under new occurrence roots; a partial copy is plain linked text.
    section = next(value for value in workspace.project.document.blocks() if value.type == 'section' and block in value.children)
    copied = edit(workspace, {'kind': 'copy_blocks', 'sources': [{'blockId': block.id, 'beforeRevision': block.revision}],
        'placement': {'parentId': section.id, 'afterId': block.id}}, 'copy')
    [_, copy] = links(copied)
    assert (copy.label_binding.cell_id, copy.url_binding.cell_id) == (original.label_binding.cell_id, original.url_binding.cell_id)
    assert copy.label_binding.occurrence_id != original.label_binding.occurrence_id
    assert copy.url_binding.occurrence_id != original.url_binding.occurrence_id
    assert copied.project.facts == workspace.project.facts
    fragment = edit(workspace, {'kind': 'copy_fragment', 'source': text_range(block, 0, 4),
        'placement': {'parentId': section.id, 'afterId': block.id}}, 'fragment')
    part = next(value for value in fragment.project.document.blocks() if value.id not in {item.id for item in workspace.project.document.blocks()})
    assert [(span.type, span.href) for span in part.content] == [('link', URL)] and len(links(fragment)) == 1
    assert hyperlinks(render(fragment, tmp_path)) == [('Portfolio', (URL, 'External')), ('Port', (URL, 'External'))]
    # Move into the sidebar, then delete: the facts stay, and Undo restores the exact block.
    sidebar = next(region for region in workspace.project.document.regions if region.role == 'sidebar')
    moved = edit(workspace, {'kind': 'move_block', 'blockId': section.id, 'beforeRevision': section.revision,
        'placement': {'parentId': sidebar.id, 'afterId': sidebar.blocks[-1].id}}, 'move')
    assert [value.id for value in next(region for region in moved.project.document.regions if region.role == 'sidebar').blocks][-1] == section.id
    assert links(moved) == links(workspace)
    removed = edit(workspace, {'kind': 'remove_occurrences', 'blocks': [{'blockId': block.id, 'beforeRevision': block.revision}]}, 'remove')
    assert not links(removed) and removed.project.facts == workspace.project.facts
    restored = undo(workspace, removed, 'remove')
    assert find(restored, 'Portfolio').content == block.content


@pytest.mark.asyncio
async def test_focus_durations_order_names_and_merges_stay_exact_through_undo_transfer_and_docx(tmp_path):
    _fixture, workspace, originals = await published(tmp_path)
    months = find(workspace, '10 months')
    typed = edit(workspace, {'kind': 'replace_text', 'range': text_range(months, 0, 2), 'text': '11', 'styles': {}}, 'duration')
    experience = next(cell for record in typed.project.facts.extensions for cell in record.cells if cell.raw_input == '11 months')
    assert (experience.state, experience.origin) == ('human_raw', 'human')
    # Manual order: the SQL entry moves above Python; nothing reorders it by years.
    sections = [block for block in typed.project.document.blocks() if block.type == 'section' and block.presentation.view_key == 'focus']
    sql = next(block for block in sections if text(block.children[0]) == 'SQL')
    heading = next(block for block in typed.project.document.blocks() if block.type == 'heading' and text(block) == 'FOCUS')
    region = next(region for region in typed.project.document.regions if heading in region.blocks)
    ordered = edit(typed, {'kind': 'move_block', 'blockId': sql.id, 'beforeRevision': sql.revision,
        'placement': {'parentId': region.id, 'afterId': heading.id}}, 'order')
    name = find(ordered, 'UnknownTool')
    renamed = edit(ordered, {'kind': 'replace_text', 'range': text_range(name, 0, len('UnknownTool')), 'text': 'Docker', 'styles': {}}, 'rename')
    python, detail = find(renamed, 'Python'), find(renamed, '11 months')
    merged = edit(renamed, {'kind': 'merge_blocks', 'leadingId': python.id, 'leadingRevision': python.revision,
        'trailingId': detail.id, 'trailingRevision': detail.revision}, 'merge')
    joined = find(merged, 'Python11 months')
    # Each field keeps its own style after the merge; icons follow the current names.
    styles = {}
    for part in joined.content:
        styles.setdefault((part.field_key, part.presentation.style_token), []).append(part.text)
    assert {key[1]: ''.join(value) for key, value in styles.items()} == {'emphasis': 'Python', 'body': '11 months'}
    plan = editor_plan(merged.project)
    assert [(text(block.children[0]), plan['blocks'][block.id]['focus']['icon']) for block in merged.project.document.blocks()
        if block.id in plan['blocks'] and 'focus' in plan['blocks'][block.id]] == [('SQL', None), ('Python11 months', 'python'), ('Docker', 'docker')]
    assert plan['blocks'][joined.id]['inline'] == {part.binding_id: 'body' for part in joined.content[1:]}
    copy = transferred(merged, originals)
    body = emitted(xml(content := render(copy, tmp_path)))
    order = ['SQL', 'about 2.5 years', 'Python', '11 months', 'Docker', '7 weeks']
    assert [body.index(value) for value in order] == sorted(body.index(value) for value in order)
    assert '10 months' not in body and len(xml(content).xpath('//w:body//wp:anchor', namespaces={**NS,
        'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'})) == 2
    unmerged = undo(renamed, merged, 'merge')
    assert [text(find(unmerged, value)) for value in ['Python', '11 months']] == ['Python', '11 months']


def join_package():
    config = employment_package().definition.model_dump(mode='json', by_alias=True)
    config['template'].update(id='synthetic-joins', name='Joined fields')
    nodes = config['blocks'][0]['view']['nodes']
    nodes[0] = {'type': 'join_fields', 'fields': ['/company', '/role'], 'separator': ' — ', 'style': 'project'}
    nodes[2] = {'type': 'join_items', 'field': '/technologies', 'item_field': '/display', 'separator': ', ', 'style': 'support'}
    del nodes[4]
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


@pytest.mark.asyncio
async def test_e08_joined_fields_edit_one_field_or_keep_a_cross_boundary_replacement_exact(tmp_path):
    src, raw = employment_source('F01')
    fixture = EmploymentFixture(tmp_path, captured=join_package(), src=src, original_bytes=raw,
        scripted=scripted_employment(src), cap=4, fallback=False)
    assert (await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)).publication.state == 'saved'
    workspace, originals = fixture.current(), {src.id: raw}
    block = find(workspace, 'Example Labs — backend engineer')
    assert [part.type for part in block.content] == ['fact_field', 'text', 'fact_field']
    job = next(record for record in workspace.project.facts.records if record.kind == 'employment')
    role = edit(workspace, {'kind': 'replace_text', 'range': text_range(block, 15, 31), 'text': 'Engineer', 'styles': {}}, 'role')
    changed = next(record for record in role.project.facts.records if record.id == job.id)
    assert (changed.employer, changed.role.raw_text) == (job.employer, 'Engineer')
    across = edit(workspace, {'kind': 'replace_text', 'range': text_range(block, 8, 22), 'text': 'Works — Staff', 'styles': {}}, 'across')
    shown = find(across, 'Example Works — Staff engineer')
    assert [type(part) for part in shown.content] == [FieldOccurrence, ManualScopeSpan, FieldOccurrence]
    pending = next(record for record in across.project.facts.records if record.id == job.id)
    # No assignment is invented: both touched cells wait on one exact human scope.
    assert {(field.status, field.raw_text, field.pending_raw_text) for field in (pending.employer, pending.role)} == {
        ('pending', '', 'Works — Staff')}
    assert [scope.raw_input for scope in across.project.facts.manual_scopes] == ['Works — Staff']
    assert 'Example Works — Staff engineer' in emitted(xml(render(transferred(across, originals), tmp_path)))
    restored = undo(workspace, across, 'across')
    assert text(find(restored, 'Example Labs — backend engineer')) == 'Example Labs — backend engineer'
    assert next(record for record in restored.project.facts.records if record.id == job.id).employer.raw_text == 'Example Labs'
    # A joined item list edits one item's cell.
    technologies = find(workspace, 'Python')
    item = edit(workspace, {'kind': 'replace_text', 'range': text_range(technologies, 0, 6), 'text': 'Python 3', 'styles': {}}, 'item')
    technology = next(record for record in item.project.facts.records if record.kind == 'technology')
    assert technology.display.raw_text == 'Python 3' and text(find(item, 'Python 3')) == 'Python 3'


@pytest.mark.asyncio
async def test_e10_yaml_styles_survive_new_block_ids_and_manual_marks_override_them(tmp_path):
    _fixture, workspace, originals = await published(tmp_path)
    python, sql = find(workspace, 'Python'), find(workspace, 'SQL')
    split = edit(workspace, {'kind': 'split_block', 'blockId': python.id, 'beforeRevision': python.revision, 'offset': 3}, 'split')
    second = find(split, 'hon')
    section = next(block for block in split.project.document.blocks() if block.type == 'section' and sql in block.children)
    copied = edit(split, {'kind': 'copy_blocks', 'sources': [{'blockId': sql.id, 'beforeRevision': sql.revision}],
        'placement': {'parentId': section.id, 'afterId': sql.id}}, 'copy')
    copy = next(block for block in copied.project.document.blocks() if text(block) == 'SQL' and block.id != sql.id)
    detail = find(copied, 'about 2.5 years')
    marked = edit(copied, {'kind': 'set_marks', 'range': text_range(detail, 0, 5), 'styles': {'bold': True}}, 'marks')
    # New block IDs keep the YAML style reference of the view node they came from.
    plan = editor_plan(marked.project)
    for block in [second, copy]:
        assert block.id not in {value.id for value in workspace.project.document.blocks()}
        assert block.presentation.style_token == 'emphasis' and plan['blocks'][block.id]['style'] == 'emphasis'
    assert plan['styles']['body']['faces']['bold'] == 'SourceSansPro-Bold'
    tree = xml(render(transferred(marked, originals), tmp_path))
    def runs(wording):
        return [(run.xpath('string(.//w:rFonts/@w:ascii)', namespaces=NS), run.xpath('string(.//w:b/@w:val)', namespaces=NS),
            run.xpath('string(.//w:sz/@w:val)', namespaces=NS)) for paragraph in tree.iter('{%s}p' % NS['w'])
            if emitted(paragraph) == wording for run in paragraph.iter('{%s}r' % NS['w'])]
    # The bold mark selects the captured bold face over the light body style; the rest keeps the YAML style.
    assert runs('about 2.5 years') == [('Source Sans Pro', '1', '20'), ('Source Sans Pro Light', '0', '20')]
    assert runs('hon') == runs('Pyt') == [('Source Sans Pro Semibold', '0', '20')]
