"""F8 (D179): green marks only for text a model wrote and no person wrote since; red rows for what left the page. The
document is a lite import of an invented CV."""

import pytest

from packages.resume_core.fields import field_key
from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.repository.accept import accept
from packages.resume_core.repository.assistant_compiler import compile_ops
from packages.resume_core.repository.block_reword import UpdateFactOp
from packages.resume_core.repository.source_diff import additions, removals
from resume_api.projects.service import response_for_workspace
from tests.templates.test_block_reword import Rewording, card
from tests.templates.test_lite_import import Unwritten, lite_run

TASK = 'Перевела расчёты с Oracle на PostgreSQL'


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    return lite_run(tmp_path_factory.mktemp('accepted'), 'promotions', calls=Unwritten('promotions'))[0]


def summary_cell(workspace):
    record = next(value for value in workspace.project.facts.extensions if value.semantic_type == 'foldcv:summary')
    return record, record.cells[0]


def typed(workspace, record_id, field, value):
    """The workspace after the user's own text in a value, through the path an edit takes."""
    after, _created = compile_ops(workspace, [UpdateFactOp(op='update_fact', recordId=record_id, field=field, value=value)],
        action_id='typed-' + str(workspace.project_revision), occupied=set(), response_for=response_for_workspace)
    return after


def marked(workspace, cell):
    """The workspace with one cell marked as a model's Apply leaves it."""
    after = workspace.model_copy(deep=True)
    after.project.facts.model_written = {cell: 'reword-1'}
    return after


def test_g1_the_imports_own_text_keeps_its_green_words(imported):
    workspace = imported.current()
    _record, cell = summary_cell(workspace)
    assert cell.origin == 'model' and 'специализируюсь' in additions(workspace)[cell.id]


def test_g2_a_word_the_user_types_in_a_green_value_takes_every_green_mark_of_the_value(imported):
    workspace = imported.current()
    record, cell = summary_cell(workspace)
    after = typed(workspace, record.id, cell.field_key, cell.raw_input + ' Ещёслово')
    assert cell.id not in additions(after)


def test_g2_typing_in_a_builtin_value_a_model_wrote_takes_its_mark_too(imported):
    workspace = imported.current()
    _block, source = card(workspace, TASK)
    target = source.targets[1]
    cell = field_key(target.record_id, target.field)
    before = marked(typed(workspace, target.record_id, target.field, 'Перевод расчётов с Oracle на PostgreSQL'), cell)
    assert additions(before)[cell] == ['Перевод', 'расчётов']
    after = typed(before, target.record_id, target.field, 'Перевод расчётов с Oracle на PostgreSQL сам')
    assert cell not in after.project.facts.model_written and cell not in additions(after)


def test_g3_a_value_the_user_wrote_through_the_editor_is_not_marked(imported):
    workspace = imported.current()
    _block, source = card(workspace, TASK)
    target = source.targets[1]
    after = typed(workspace, target.record_id, target.field, 'Перевод расчётов с Oracle на PostgreSQL')
    assert field_key(target.record_id, target.field) not in additions(after)


def test_a_mark_goes_with_its_record_and_a_mark_of_no_cell_is_refused(imported):
    workspace = imported.current()
    data = workspace.project.facts.model_dump(mode='json', by_alias=True)
    with pytest.raises(ValueError, match='model written mark'):
        WorkingFactsV2.model_validate({**data, 'modelWritten': {'["fact","record-missing","value"]': 'reword-1'}})


def test_g5_the_lines_of_a_removed_card_are_red_as_removed(imported):
    workspace = imported.current()
    after = workspace.model_copy(deep=True)
    region = next(value for value in after.project.document.regions if any(block.presentation is not None
        and block.presentation.view_key == 'education' for block in value.blocks))
    region.blocks[:] = [block for block in region.blocks if not (block.type == 'section' and block.presentation is not None
        and block.presentation.view_key == 'education')]
    rows = [row for row in removals(after) if row not in removals(workspace)]
    assert rows and {row['reason'] for row in rows} == {'removed'}
    # No shown value rests on the card's line, so it is red whole, though the page shows two of its words elsewhere
    # (remark 2 after stop 4).
    from packages.resume_core.repository.source_diff import shown_fields
    from packages.resume_core.importing.lite.words import line_words, words
    shown = set().union(*(words(text) for _id, _key, text, _lines, _record in shown_fields(after)))
    assert [row['words'] for row in rows] == [None]
    assert line_words(rows[0]['text']) & shown, 'the case holds a word the page shows on another line'


def test_g5_a_removed_field_line_of_a_card_that_stays_gives_removed_word_rows(imported):
    workspace = imported.current()
    after = workspace.model_copy(deep=True)
    job = next(block for block in after.project.document.blocks() if block.type == 'section'
        and block.presentation is not None and block.presentation.view_key == 'projects')
    job.children[:] = [child for child in job.children if child.presentation.node_index != 4]
    rows = [row for row in removals(after) if row not in removals(workspace)]
    assert rows and all(row['reason'] == 'removed' and row['words'] for row in rows)


def test_g5_a_line_a_shown_value_rests_on_is_not_red_whole(imported):
    workspace = imported.current()
    assert not [row for row in removals(workspace) if row['reason'] == 'removed'], 'a new import has nothing off the page'


def test_g8_accept_of_a_word_mark_takes_the_values_green_and_its_check(imported):
    workspace = imported.current()
    _record, cell = summary_cell(workspace)
    after = accept(workspace, cell_id=cell.id, action_id='accept-1', client_mutation_id='accept-1')
    assert cell.id not in additions(after)
    kept = next(value for record in after.project.facts.extensions for value in record.cells if value.id == cell.id)
    assert (kept.origin, kept.user_corrected, kept.raw_input) == ('human', True, cell.raw_input)
    # A builtin value: the user's flag, which also ends «Проверьте значение».
    _block, source = card(workspace, TASK)
    target = source.targets[1]
    claim = field_key(target.record_id, target.field)
    written = marked(typed(workspace, target.record_id, target.field, 'Перевод расчётов с Oracle на PostgreSQL'), claim)
    taken = accept(written, cell_id=claim, action_id='accept-2', client_mutation_id='accept-2')
    assert claim not in taken.project.facts.model_written and claim not in additions(taken)
    assert accept(taken, cell_id=claim, action_id='accept-3', client_mutation_id='accept-3') is None, 'nothing is left to accept'


def test_g8_accept_of_a_block_mark_retires_its_notice_and_accepts_each_value_of_the_block(tmp_path):
    fixture, _operation = lite_run(tmp_path / 'import', 'promotions')
    workspace = fixture.current()
    issue = next(value for value in workspace.project.import_issues if value.code == 'IMPORT_TEXT_GENERATED' and value.state == 'active')
    from packages.resume_core.repository.accept import _block_cells
    from packages.resume_core.repository.assistant_compiler import find_block
    written = set().union(*(_block_cells(find_block(workspace, identifier)) for identifier in issue.block_ids))
    assert written & set(additions(workspace)), 'the written block has green words'
    after = accept(workspace, block_id=issue.block_ids[0], action_id='accept-1', client_mutation_id='accept-1')
    assert next(value for value in after.project.import_issues if value.id == issue.id).state == 'retired'
    assert not written & set(additions(after))


def test_g2a_g2b_and_g8_through_the_routes_with_one_undo(tmp_path):
    from tests.projects.support import Editor, v2_app
    fixture, _operation = lite_run(tmp_path / 'import', 'promotions', calls=Unwritten('promotions'))
    workspace = fixture.current()
    block_id, source = card(workspace, TASK)
    target = source.targets[1]
    cell = field_key(target.record_id, target.field)
    with v2_app(tmp_path / 'app', [(workspace, fixture.originals)], content_provider=Rewording()) as (client, _application):
        project = workspace.project_id
        editor = Editor(client, project)

        def apply(identifier, edited):
            shown = editor.call('post', '/reword/preview', {'editorToken': editor.token, 'requestId': 'reword-' + identifier,
                'blockId': block_id, 'instruction': 'Задачи — существительным'})
            value = shown['values'][1]['after'] + (' сам' if edited else '')
            return editor.adopt(editor.call('post', '/reword/apply', {'editorToken': editor.token, 'clientMutationId': identifier,
                'blockId': block_id, 'touched': shown['touched'],
                'changes': [{'recordId': target.record_id, 'field': target.field, 'value': value, 'edited': edited}]}))
        diff = lambda: client.get('/v2/projects/' + project + '/source-diff').json()
        apply('apply-edited', True)
        assert cell not in diff()['added'], 'G2a: a preview the user changed is the user\'s'
        editor.step('undo', 'undo-1')
        apply('apply-same', False)
        assert diff()['added'][cell] == ['Перевод', 'расчётов'], 'G2b: an unchanged preview stays the model\'s'
        editor.adopt(editor.call('post', '/accept', {'editorToken': editor.token, 'clientMutationId': 'accept-1', 'cellId': cell}))
        assert cell not in diff()['added']
        editor.step('undo', 'undo-2')
        assert diff()['added'][cell] == ['Перевод', 'расчётов'], 'one Undo brings the green back'
