"""F3a of the tester feedback of 2026-11-23: one user action removes a range over text containers (`remove_range`)."""

import pytest

from packages.resume_core.editing.mutations import apply_rich_mutation, inline_text
from packages.resume_core.editing.template_inverse import inverse_template_mutation, semantic
from packages.resume_core.editing.template_preparation_chain import prepare_chained
from packages.resume_core.models.template_document import FieldOccurrence, TemplateTableBlock
from packages.resume_core.models.template_workspace import WorkspaceV7
from tests.templates.e04_fixtures import TASK, e04_workspace
from tests.templates.test_structural_preparation import intent
from tests.templates.test_template_preparation import response
from tests.templates.test_transactions import authorization

TASK = TASK.rstrip('.')


def blocks(workspace):
    return workspace.project.document.blocks()


def line(workspace, text, index=0):
    return [block for block in blocks(workspace) if isinstance(block.content, list)
        and ''.join(getattr(span, 'text', '') for span in block.content) == text][index]


def find(workspace, identifier):
    return next((block for block in blocks(workspace) if block.id == identifier), None)


def shown(block):
    return ''.join(inline_text(span) for span in block.content)


def edge(block, offset):
    return {'blockId': block.id, 'beforeRevision': block.revision, 'cellId': None, 'field': 'content', 'offset': offset}


def ranged(before, first, start, last, end, join=None):
    values = {'start': edge(first, start), 'end': edge(last, end)}
    if join is not None:
        values['join'] = {'styles': {}, 'enter': False, **join}
    request = intent(before, 'remove_range', **values)
    result = prepare_chained(response(before), request, response_for=response)
    assert result.workspace is not None
    return result.workspace


def refused(before, first, start, last, end, match, join=None):
    values = {'start': edge(first, start), 'end': edge(last, end)}
    if join is not None:
        values['join'] = {'styles': {}, 'enter': False, **join}
    with pytest.raises(ValueError, match=match):
        prepare_chained(response(before), intent(before, 'remove_range', **values), response_for=response)


def records(workspace):
    return {record.id: record for record in workspace.project.facts.records}


def test_cut_to_cut_in_sibling_bullets_merges_them_and_keeps_both_cells():
    before, _ = e04_workspace()
    first, second = line(before, TASK), line(before, TASK, 1)
    after = ranged(before, first, 12, second, 18)
    merged = find(after, first.id)
    assert shown(merged) == 'Implemented processing' and find(after, second.id) is None
    assert [span.cell_id for span in merged.content] == [first.content[0].cell_id, second.content[0].cell_id]
    values = records(after)
    assert values[first.content[0].record_id].value.value == 'Implemented'
    assert values[second.content[0].record_id].value.value == 'processing'


def test_whole_first_to_cut_last():
    before, _ = e04_workspace()
    first, second = line(before, TASK), line(before, TASK, 1)
    after = ranged(before, first, 0, second, 18)
    assert find(after, first.id) is None and shown(find(after, second.id)) == 'processing'


def test_cut_first_to_whole_last():
    before, _ = e04_workspace()
    first, second = line(before, TASK), line(before, TASK, 1)
    after = ranged(before, first, 12, second, len(TASK))
    assert shown(find(after, first.id)) == 'Implemented ' and find(after, second.id) is None


def test_heading_to_the_end_of_its_section_removes_both_and_the_next_section_stays():
    before, _ = e04_workspace()
    heading = line(before, 'PROJECTS')
    section, other = [block for block in blocks(before) if block.type == 'section']
    last = section.children[-1]
    after = ranged(before, heading, 0, last, len(shown(last)))
    assert find(after, heading.id) is None and find(after, section.id) is None
    assert find(after, other.id) is not None and after.project.facts == before.project.facts


def test_a_line_of_card_a_to_a_line_of_card_b_does_not_merge_and_keeps_owners():
    before, _ = e04_workspace()
    role, employer = line(before, 'Role: Backend Engineer'), line(before, 'Second Works')
    section, other = [block for block in blocks(before) if block.type == 'section']
    after = ranged(before, role, 6, employer, 2)
    assert shown(find(after, role.id)) == 'Role: ' and shown(find(after, employer.id)) == 'cond Works'
    assert [child.id for child in find(after, section.id).children][-1] == role.id
    assert [child.id for child in find(after, other.id).children][0] == employer.id
    assert find(after, section.id).props == section.props and find(after, other.id).props == other.props
    # The role was cut whole and keeps its fact; the employer lost a part, so its fact changed.
    assert records(after)[role.content[1].record_id] == records(before)[role.content[1].record_id]
    assert records(after)[employer.content[0].record_id].employer.value == 'cond Works'


def test_a_wholly_covered_technology_line_goes_and_its_fact_stays():
    before, _ = e04_workspace()
    employer, role = line(before, 'Example Labs'), line(before, 'Role: Backend Engineer')
    python, dates = line(before, 'Python'), line(before, '03.2020–11.2023')
    after = ranged(before, employer, 5, role, 4)
    assert shown(find(after, employer.id)) == 'Examp: Backend Engineer'
    assert find(after, dates.id) is None and find(after, python.id) is None and find(after, role.id) is None
    technology = python.content[0].record_id
    assert records(after)[technology] == records(before)[technology]


def test_an_edge_that_cuts_a_technology_line_is_refused_from_each_side():
    before, _ = e04_workspace()
    employer, python, role = line(before, 'Example Labs'), line(before, 'Python'), line(before, 'Role: Backend Engineer')
    refused(before, employer, 3, python, 2, 'TECHNOLOGY_IN_FACTS')
    refused(before, python, 2, role, 4, 'TECHNOLOGY_IN_FACTS')


def test_an_edge_at_the_start_of_a_technology_line_keeps_it_with_no_merge():
    before, _ = e04_workspace()
    employer, python, dates = line(before, 'Example Labs'), line(before, 'Python'), line(before, '03.2020–11.2023')
    after = ranged(before, employer, 5, python, 0)
    assert shown(find(after, employer.id)) == 'Examp' and find(after, dates.id) is None
    assert find(after, python.id) == python or shown(find(after, python.id)) == 'Python'
    # Text typed over a range may not go into a technology line.
    refused(before, python, 6, role := line(before, 'Role: Backend Engineer'), 4, 'TECHNOLOGY_IN_FACTS', {'text': 'x'})
    assert role


def tabled():
    before, _ = e04_workspace()
    tasks = line(before, 'Tasks:')
    section = next(block for block in blocks(before) if tasks in block.children)
    table = TemplateTableBlock(type='table', id='block-table', revision=1, props={}, children=[], provenance=[],
        presentation=tasks.presentation, content={'rows': [{'id': 'row', 'cells': [{'id': 'cell', 'revision': 1,
            'content': [{'type': 'text', 'text': 'Cell text', 'styles': {}}]}, {'id': 'cell-2', 'revision': 1,
            'content': [{'type': 'text', 'text': 'Other cell', 'styles': {}}]}]}], 'columnWidths': [None, None], 'headerRows': 0,
            'headerCols': 0})
    section.children.insert(section.children.index(tasks) + 1, table)
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True))


def cell_edge(table, cell, offset):
    return {**edge(table, offset), 'cellId': cell}


def cells(workspace):
    return [''.join(span.text for span in cell.content) for row in find(workspace, 'block-table').content.rows for cell in row.cells]


def table_range(before, start, end, join=None):
    values = {'start': start, 'end': end, **({'join': {'styles': {}, 'enter': False, **join}} if join else {})}
    return prepare_chained(response(before), intent(before, 'remove_range', **values), response_for=response).workspace


def test_f3e_an_edge_in_a_cell_empties_the_covered_cell_text_and_keeps_the_table():
    before = tabled()
    table, tasks, bullet = find(before, 'block-table'), line(before, 'Tasks:'), line(before, TASK)
    into = table_range(before, edge(tasks, 2), cell_edge(table, 'cell-2', 3))
    assert shown(find(into, tasks.id)) == 'Ta' and cells(into) == ['', 'er cell']
    out = table_range(before, cell_edge(table, 'cell', 4), edge(bullet, 12))
    assert cells(out) == ['Cell', ''] and shown(find(out, bullet.id)) == 'queue processing'
    inside = table_range(before, cell_edge(table, 'cell', 2), cell_edge(table, 'cell-2', 2), {'text': 'X\nY',
        'insertionTarget': {'kind': 'literal'}})
    assert cells(inside) == ['CeX Y', 'her cell'] and find(inside, 'block-table') is not None


def test_a_table_between_the_edges_goes_as_a_block():
    before = tabled()
    tasks, bullet = line(before, 'Tasks:'), line(before, TASK)
    after = ranged(before, tasks, 2, bullet, 12)
    assert find(after, 'block-table') is None and shown(find(after, tasks.id)) == 'Taqueue processing'


def test_edges_in_two_regions():
    before, _ = e04_workspace()
    region = before.project.document.regions[1]
    tail = before.project.document.regions[2].blocks.pop()
    region.blocks.append(tail)
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    second = line(before, 'Second Works')
    tail = line(before, '2024–present')
    # Region 1 comes before region 2, so the edges run from the moved line to "Second Works".
    after = ranged(before, tail, 4, second, 6)
    assert shown(find(after, tail.id)) == '2024' and shown(find(after, second.id)) == ' Works'
    assert find(after, line(before, 'PROJECTS').id) is None


def test_text_at_the_join_replaces_the_cut_part_of_the_first_block():
    before, _ = e04_workspace()
    employer, role = line(before, 'Second Works'), line(before, 'Role: engineer')
    after = ranged(before, employer, 2, role, 4, {'text': 'new words'})
    assert shown(find(after, employer.id)) == 'Senew words: engineer' and find(after, role.id) is None
    assert records(after)[employer.content[0].record_id].employer.value == 'Senew words'
    # At the end of the first text the join needs the insertion target that the client takes from the editor.
    first, second = line(before, TASK), line(before, TASK, 1)
    after = ranged(before, first, len(TASK), second, 18, {'text': '!', 'insertionTarget': {'kind': 'literal'}})
    assert shown(find(after, first.id)) == TASK + '!processing'


def test_a_line_with_a_bound_link():
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    first, second = before.project.document.regions[2].blocks[:2]
    # The link of the first line is covered whole, so it goes with its text; both facts keep their values.
    after = ranged(before, first, 0, second, 2)
    assert find(after, first.id) is None and after.project.facts.extensions[0] == before.project.facts.extensions[0]
    kept = ranged(before, first, 7, second, 2)
    assert shown(find(kept, first.id)).startswith('Shared ')


@pytest.mark.parametrize('error', ['order', 'missing', 'revision', 'offset', 'same'])
def test_invalid_edges_are_refused(error):
    before, _ = e04_workspace()
    first, second = line(before, TASK), line(before, TASK, 1)
    start, end = edge(first, 2), edge(second, 2)
    if error == 'order':
        start, end = end, start
    elif error == 'missing':
        end['blockId'] = 'missing'
    elif error == 'revision':
        end['beforeRevision'] += 1
    elif error == 'offset':
        end['offset'] = 99
    if error == 'same':
        with pytest.raises(ValueError):
            intent(before, 'remove_range', start=start, end={**start, 'offset': 4})
        return
    with pytest.raises(ValueError):
        prepare_chained(response(before), intent(before, 'remove_range', start=start, end=end), response_for=response)


def test_all_of_the_document_leaves_one_empty_block():
    before, _ = e04_workspace()
    heading, tail = line(before, 'PROJECTS'), line(before, '2024–present')
    after = ranged(before, heading, 0, tail, len('2024–present'))
    assert [(block.id, block.content) for block in blocks(after)] == [(heading.id, [])]
    assert after.project.facts == before.project.facts


def test_facts_anchors_and_the_inverse_restore_all_ids():
    before, _ = e04_workspace()
    employer, role = line(before, 'Example Labs'), line(before, 'Role: Backend Engineer')
    after = ranged(before, employer, 5, role, 4)
    assert len(after.project.import_coverage) == len(before.project.import_coverage)
    assert all(set(value.block_ids) <= {block.id for block in blocks(after)} for value in after.project.import_coverage)
    inverse = inverse_template_mutation(before, after, origin_action_id='action', mutation_id='undo-range',
        session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(after, inverse, history_authorization=authorization(after, inverse))
    assert semantic(restored.project.document) == semantic(before.project.document)
    assert semantic(restored.project.facts) == semantic(before.project.facts)


def test_every_step_shares_the_request_action():
    before, _ = e04_workspace()
    first, second = line(before, TASK), line(before, TASK, 1)
    request = intent(before, 'remove_range', start=edge(first, 12), end=edge(second, 18))
    result = prepare_chained(response(before), request, response_for=response)
    assert result.created_ids and all(key.startswith('structure:') for key in result.created_ids)
    again = prepare_chained(response(before), request, response_for=response)
    assert again.workspace == result.workspace, 'the same request makes the same ids'
    assert not any(isinstance(span, FieldOccurrence) and not span.text for block in blocks(result.workspace)
        if isinstance(block.content, list) for span in block.content)


@pytest.mark.slow
def test_a_range_over_the_whole_generic_f10_document_fits_one_action(tmp_path):
    import asyncio
    import time
    from tests.templates.generic_fixtures import generic_import
    _fixture, result, before, _originals = asyncio.run(generic_import(tmp_path, 'F10'))
    assert result.state == 'published'
    texts = [block for block in blocks(before) if block.type in {'paragraph', 'heading', 'bullet_list', 'numbered_list'}
        and isinstance(block.content, list)]
    first, last = texts[0], texts[-1]
    started = time.monotonic()
    after = ranged(before, first, 0, last, len(shown(last)))
    print(f'whole generic-f10 range: {len(blocks(before))} blocks, {time.monotonic() - started:.2f} s')
    kept = [block for block in blocks(after) if isinstance(block.content, list) and block.type != 'section']
    assert [block.id for block in kept] == [first.id] and kept[0].content == []
    assert after.project.facts.records == before.project.facts.records


def test_an_edge_that_cuts_a_url_only_link_in_part_is_refused_with_its_own_code():
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    first, second = before.project.document.regions[2].blocks[:2]
    link = first.content[0]
    link.label_binding = None
    span = link.content[0]
    span.field_key, span.cell_id = 'url', 'a-url'
    span.occurrence_id = span.binding_root_id = 'url-occurrence'
    span.text = link.href
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    first = before.project.document.regions[2].blocks[0]
    refused(before, first, 3, second, 2, 'RANGE_LINK_EDGE')
