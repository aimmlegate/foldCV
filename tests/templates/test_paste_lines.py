"""F3c and F3d of the tester feedback of 2026-11-23: pasted lines and Enter over a selection (`paste_lines`)."""

import pytest

from packages.resume_core.editing.template_preparation_chain import PASTE_LINES, pasted_lines, prepare_chained
from packages.resume_core.models.template_document import PresentedText
from tests.templates.e04_fixtures import TASK, e04_workspace
from tests.templates.test_range_removal import blocks, find, line, shown
from tests.templates.test_structural_preparation import intent
from tests.templates.test_template_preparation import response

TASK = TASK.rstrip('.')


def pasted(before, block, start, end, text, *, enter=False, target=None):
    destination = {'blockId': block.id, 'beforeRevision': block.revision, 'cellId': None, 'field': 'content',
        'start': start, 'end': end}
    if target is not None:
        destination['insertionTarget'] = target
    request = intent(before, 'paste_lines', destination=destination, text=text, styles={}, enter=enter)
    return prepare_chained(response(before), request, response_for=response).workspace


def siblings(workspace, identifier):
    parent = next(block for block in blocks(workspace) if any(child.id == identifier for child in block.children))
    return parent.children


def test_line_ends_and_blank_lines():
    assert pasted_lines('one') == ['one'] and pasted_lines(' ') == [' ']
    assert pasted_lines('a\r\nb\rc\nd\n') == ['a', 'b', 'c', 'd']
    assert pasted_lines('a\n   \n\nb') == ['a', 'b']


def test_three_lines_at_the_end_of_a_bullet_make_three_bullets_of_plain_text():
    before, _ = e04_workspace()
    bullet = line(before, TASK)
    after = pasted(before, bullet, len(TASK), len(TASK), 'one\ntwo\nthree', target={'kind': 'literal'})
    children = siblings(after, bullet.id)
    index = [child.id for child in children].index(bullet.id)
    made = children[index:index + 3]
    assert [shown(child) for child in made] == [TASK + 'one', 'two', 'three']
    assert {child.type for child in made} == {'bullet_list'}
    assert all(isinstance(span, PresentedText) for child in made[1:] for span in child.content)
    assert after.project.facts == before.project.facts


def test_lines_into_the_middle_of_a_line_keep_the_tail_after_the_last_line():
    before, _ = e04_workspace()
    tasks = line(before, 'Tasks:')
    after = pasted(before, tasks, 3, 3, 'A\nB\nC', target={'kind': 'literal'})
    children = siblings(after, tasks.id)
    index = [child.id for child in children].index(tasks.id)
    assert [shown(child) for child in children[index:index + 3]] == ['TasA', 'B', 'Cks:']


def test_enter_over_a_selection_deletes_it_and_splits():
    before, _ = e04_workspace()
    tasks = line(before, 'Tasks:')
    after = pasted(before, tasks, 1, 3, '', enter=True)
    children = siblings(after, tasks.id)
    index = [child.id for child in children].index(tasks.id)
    assert [shown(child) for child in children[index:index + 2]] == ['T', 'ks:']


def test_a_table_cell_takes_the_lines_as_one_line():
    from tests.templates.test_range_removal import tabled
    before = tabled()
    table = find(before, 'block-table')
    destination = {'blockId': table.id, 'beforeRevision': table.revision, 'cellId': 'cell', 'field': 'content',
        'start': 4, 'end': 4, 'insertionTarget': {'kind': 'literal'}}
    request = intent(before, 'paste_lines', destination=destination, text='one\ntwo', styles={}, enter=False)
    after = prepare_chained(response(before), request, response_for=response).workspace
    assert ''.join(span.text for span in find(after, table.id).content.rows[0].cells[0].content) == 'Cellone two text'


def test_more_than_the_limit_is_refused_with_its_code():
    before, _ = e04_workspace()
    tasks = line(before, 'Tasks:')
    with pytest.raises(ValueError, match='PASTE_TOO_LARGE'):
        pasted(before, tasks, 0, 0, '\n'.join(['x'] * (PASTE_LINES + 1)), target={'kind': 'literal'})
    with pytest.raises(ValueError, match='PASTE_TOO_LARGE'):
        pasted(before, tasks, 0, 0, 'x' * 64_001 + '\ny', target={'kind': 'literal'})


def test_a_technology_line_keeps_its_refusal():
    before, _ = e04_workspace()
    with pytest.raises(ValueError, match='TECHNOLOGY_IN_FACTS'):
        pasted(before, line(before, 'Python'), 6, 6, 'a\nb', target={'kind': 'literal'})


def test_lines_at_the_join_of_a_range():
    before, _ = e04_workspace()
    first, second = line(before, TASK), line(before, TASK, 1)
    request = intent(before, 'remove_range',
        start={'blockId': first.id, 'beforeRevision': first.revision, 'cellId': None, 'field': 'content', 'offset': 12},
        end={'blockId': second.id, 'beforeRevision': second.revision, 'cellId': None, 'field': 'content', 'offset': 18},
        join={'text': 'one\ntwo\nthree', 'styles': {}, 'enter': False})
    after = prepare_chained(response(before), request, response_for=response).workspace
    children = siblings(after, first.id)
    index = [child.id for child in children].index(first.id)
    assert [shown(child) for child in children[index:index + 3]] == ['Implemented one', 'two', 'threeprocessing']
