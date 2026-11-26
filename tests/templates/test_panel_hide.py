"""«Скрыть» in Facts (D185): a job's card or a whole block off the page into the hidden store and back with the same
blocks and ids. Synthetic data only (the F10 fixture and the invented lite CV)."""

import asyncio

import pytest

from packages.resume_core.editing.mutations import apply_rich_mutation
from packages.resume_core.editing.template_inverse import inverse_template_mutation, semantic
from packages.resume_core.editing.template_panel_jobs import job_warnings
from packages.resume_core.editing.template_panel_records import panel_plan
from packages.resume_core.editing.template_preparation import prepare_edit
from packages.resume_core.hashing import canonical
from packages.resume_core.models.template_document import PresentedText, TemplateParagraphBlock
from packages.resume_core.repository.archive_zip import write_zip
from packages.resume_core.repository.template_archive import archive_payload_v7, open_archive_v7
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.generic_fixtures import generic_import
from tests.templates.test_panel_creation import request
from tests.templates.test_panel_preparation import prepared, restore
from tests.templates.test_template_preparation import response
from tests.templates.test_transactions import authorization

TYPED = 'Свой текст пользователя, не факт'


@pytest.fixture(scope='module')
def imported(tmp_path_factory):
    _fixture, _result, workspace, sources = asyncio.run(generic_import(tmp_path_factory.mktemp('hide'), 'F10'))
    return workspace, sources


def with_typed_line(workspace):
    """The summary block with one more line the user typed, in bold: text that is no fact value."""
    value = workspace.model_copy(deep=True)
    section = next(block for block in value.project.document.blocks()
                   if block.type == 'section' and block.presentation.view_key == 'summary')
    ref = section.children[0].presentation
    section.children.append(TemplateParagraphBlock(type='paragraph', id='typed-line', revision=1, props={}, children=[],
        provenance=[], presentation=ref, content=[PresentedText(type='text', text=TYPED, styles={'bold': True},
                                                                presentation=ref)]))
    return type(value).model_validate(value.model_dump(by_alias=True))


def job(workspace, eye='shown'):
    return next(identifier for identifier, value in panel_plan(workspace.project)['jobs'].items() if value.get('eye') == eye)


def blocks(workspace):
    return {row['id']: row for row in panel_plan(workspace.project)['hideBlocks']}


def hide(before, identifier, *, view=None, operation='hide', operations=None):
    value = request(before, operation=operation, kind='employment' if view is None else None,
                    record_id=None if view else identifier, values={'view': view} if view else None, identifier=identifier[:40] + operation)
    if operations is None:
        return prepared(before, value)
    # A Show of a card or block deleted on the page builds it from the import's records, as the route loads them.
    result = prepare_edit(response(before), value, operations=operations)
    assert apply_rich_mutation(before, result.mutation)[0] == result.preview.workspace
    return result


def deleted_on_page(workspace, gone):
    """The workspace with the top blocks `gone` picks deleted on the page, as a delete there leaves it: no anchor names
    them."""
    value = workspace.model_copy(deep=True)
    removed = set()
    for region in value.project.document.regions:
        for block in region.blocks:
            if gone(block):
                stack = [block]
                while stack:
                    item = stack.pop()
                    removed.add(item.id)
                    stack.extend(item.children)
        region.blocks = [block for block in region.blocks if not gone(block)]
    for item in [*value.project.import_coverage, *value.project.import_issues]:
        item.block_ids = [identifier for identifier in item.block_ids if identifier not in removed]
    return type(value).model_validate(value.model_dump(by_alias=True))


def page_text(workspace):
    return ' '.join(getattr(span, 'text', '') for block in workspace.project.document.blocks()
                    for span in getattr(block, 'content', []) if not isinstance(block.content, dict))


def test_the_plan_lists_each_block_once_with_its_place_and_no_eye_for_the_header(imported):
    workspace, _sources = imported
    rows = panel_plan(workspace.project)['hideBlocks']
    assert len({row['id'] for row in rows}) == len(rows)
    places = {row['id']: (row['place'], row.get('kind')) for row in rows}
    assert places['view:projects'] == ('group', 'employment') and places['view:education'] == ('group', 'education')
    assert places['view:languages'] == ('group', 'language') and places['view:focus'] == ('focus', None)
    assert {key for key, (place, _kind) in places.items() if place == 'technology'} == {
        'view:programming', 'view:data_and_tools', 'view:infrastructure'}
    assert {key for key, (place, _kind) in places.items() if place == 'other'} == {
        'view:courses', 'view:location', 'view:opensource', 'view:summary', 'view:other_projects'}
    assert 'view:identity' not in places
    assert next(row for row in rows if row['id'] == 'view:summary')['name'] == 'О СЕБЕ'
    assert not any(row['hidden'] for row in rows)
    # The detailed job has an eye; the compact list's job has none (no card of its own).
    eyes = [value.get('eye') for value in panel_plan(workspace.project)['jobs'].values()]
    assert sorted(eyes, key=str) == sorted(['shown', None], key=str)


def test_a_job_hides_and_shows_with_the_same_card_and_ids_and_one_undo_each(imported):
    workspace, _sources = imported
    identifier = job(workspace)
    hidden = hide(workspace, identifier)
    after = hidden.preview.workspace
    assert {step.kind for step in hidden.mutation.steps} >= {'put_hidden_blocks', 'remove_block'}
    assert not any(step.kind == 'set_issue_state' for step in hidden.mutation.steps)
    assert panel_plan(after.project)['jobs'][identifier]['eye'] == 'hidden'
    assert 'Queue Platform' not in page_text(after) and len(after.project.hidden_blocks) == 1
    assert restore(workspace, hidden).project.hidden_blocks == []
    shown = hide(after, identifier, operation='show')
    back = shown.preview.workspace
    assert semantic(back.project.document) == semantic(workspace.project.document)
    assert [block.id for block in back.project.document.blocks()] == [block.id for block in workspace.project.document.blocks()]
    assert back.project.import_issues == workspace.project.import_issues and back.project.hidden_blocks == []
    assert [value.block_ids for value in back.project.import_coverage] == [value.block_ids for value in workspace.project.import_coverage]
    undone = restore(after, shown)
    assert undone.project.hidden_blocks == after.project.hidden_blocks
    redo = inverse_template_mutation(back, undone, origin_action_id=shown.mutation.action_id, mutation_id='redo-show',
                                     session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(undone, redo, history_authorization=authorization(undone, redo))
    assert semantic(replayed.project.document) == semantic(workspace.project.document)


@pytest.mark.parametrize('view', ['education', 'summary', 'programming'])
def test_a_block_with_or_without_fact_rows_hides_whole_and_comes_back_the_same(imported, view):
    workspace, _sources = imported
    hidden = hide(workspace, 'v-' + view, view=view).preview.workspace
    assert blocks(hidden)['view:' + view]['hidden'] is True
    assert not any(block.presentation is not None and block.presentation.view_key == view for block in hidden.project.document.blocks())
    back = hide(hidden, 'v-' + view, view=view, operation='show').preview.workspace
    assert semantic(back.project.document) == semantic(workspace.project.document)
    assert blocks(back)['view:' + view]['hidden'] is False


def test_typed_text_and_its_formatting_come_back_and_a_fact_edited_meanwhile_takes_its_new_value(imported):
    workspace = with_typed_line(imported[0])
    hidden = hide(workspace, 'typed', view='summary').preview.workspace
    assert TYPED not in page_text(hidden)
    # An edit of another fact between Hide and Show; then the summary's own fact changes in the store.
    education = next(record for record in hidden.project.facts.records if record.kind == 'education')
    edited = prepared(hidden, request(hidden, operation='edit', kind=None, record_id=education.id,
                                      values={'institution': 'Other Institute'}, identifier='edit-between')).preview.workspace
    back = hide(edited, 'typed', view='summary', operation='show').preview.workspace
    line = next(block for block in back.project.document.blocks() if block.id == 'typed-line')
    assert line.content[0].text == TYPED and line.content[0].styles.bold
    assert 'Other Institute' in page_text(back)
    assert semantic(next(block for block in back.project.document.blocks() if block.type == 'section'
                         and block.presentation.view_key == 'summary')) == semantic(next(
        block for block in workspace.project.document.blocks() if block.type == 'section' and block.presentation.view_key == 'summary'))


def test_a_hidden_block_survives_save_reopen_and_a_portable_transfer(tmp_path, imported):
    workspace, sources = imported
    workspace = with_typed_line(workspace)
    editor = TemplateEditor(tmp_path, workspace, sources)
    value = request(workspace, operation='hide', kind=None, values={'view': 'summary'}, identifier='hide-saved')
    value.operations[0].command.capture = value.capture.model_copy(deep=True)
    editor.edit(value)
    reopened = editor.reopen()
    assert len(reopened.project.hidden_blocks) == 1 and blocks(reopened)['view:summary']['hidden']
    transferred, _retained, _, _ = open_archive_v7(write_zip(archive_payload_v7(reopened, sources, {})), 'hide-transfer')
    assert transferred.project.hidden_blocks == reopened.project.hidden_blocks
    back = hide(transferred, 'after-transfer', view='summary', operation='show').preview.workspace
    assert TYPED in page_text(back)
    assert semantic(back.project.document) == semantic(workspace.project.document)


def test_a_job_hidden_before_its_block_stays_hidden_when_the_block_comes_back(imported):
    workspace, _sources = imported
    identifier = job(workspace)
    first = hide(workspace, identifier).preview.workspace
    both = hide(first, 'projects', view='projects').preview.workspace
    assert panel_plan(both.project)['jobs'][identifier]['eye'] == 'hidden'
    shown = hide(both, 'projects', view='projects', operation='show').preview.workspace
    assert 'Queue Platform' not in page_text(shown) and panel_plan(shown.project)['jobs'][identifier]['eye'] == 'hidden'
    back = hide(shown, identifier, operation='show').preview.workspace
    assert semantic(back.project.document) == semantic(workspace.project.document)


def test_a_job_inside_a_hidden_block_is_locked_and_its_show_is_refused(imported):
    workspace, _sources = imported
    identifier = job(workspace)
    hidden = hide(workspace, 'projects', view='projects').preview.workspace
    assert panel_plan(hidden.project)['jobs'][identifier]['eye'] == 'locked'
    # A record a hidden block holds offers no «Вернуть на страницу» of its own.
    assert identifier not in panel_plan(hidden.project).get('offPage', [])
    with pytest.raises(ValueError, match='PANEL_ACTION_UNSUPPORTED'):
        prepare_edit(response(hidden), request(hidden, operation='show', kind='employment', record_id=identifier))


def test_a_card_deleted_on_the_page_shows_as_hidden_and_its_show_builds_it_again(imported):
    workspace, _sources = imported
    identifier = job(workspace)
    deleted = deleted_on_page(workspace, lambda block: getattr(block.props, 'record_id', None) == identifier)
    assert panel_plan(deleted.project)['jobs'][identifier]['eye'] == 'hidden' and not deleted.project.hidden_blocks
    records = workspace.project.template_operations
    back = hide(deleted, identifier, operation='show', operations=records).preview.workspace
    assert 'Queue Platform' in page_text(back)
    # A whole block deleted on the page is hidden too, and Show builds it again.
    gone = deleted_on_page(workspace, lambda block: block.presentation is not None and block.presentation.view_key == 'languages')
    assert blocks(gone)['view:languages']['hidden'] is True
    rebuilt = hide(gone, 'languages', view='languages', operation='show', operations=records).preview.workspace
    assert 'ЯЗЫКИ' in page_text(rebuilt) and 'English' in page_text(rebuilt)


def test_the_docx_has_no_text_of_a_hidden_job_or_block(imported, tmp_path):
    from packages.resume_core.models.template_render import TemplateRenderRequestV1, snapshot_identity
    from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
    from packages.resume_core.responses.template_export import capture_export
    from tests.templates.test_captured_docx import emitted, xml
    workspace, _sources = imported
    hidden = hide(workspace, job(workspace)).preview.workspace
    hidden = hide(hidden, 'summary', view='summary').preview.workspace
    _attempt, capture = capture_export(hidden, snapshot_identity(hidden), renderer_identity())
    value = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=hidden.project.template_package)
    text = emitted(xml(render_captured_docx(value, tmp_path)))
    assert 'Example Institute' in text and 'Queue Platform' not in text and 'Reduced median latency' not in text
    assert 'О СЕБЕ' not in text and 'reliable queue systems' not in text


def test_a_hidden_job_gets_and_gives_no_overlap_warning(imported):
    workspace, _sources = imported
    added = prepared(workspace, request(workspace, values={'employer': 'Parallel', 'role': 'Dev', 'start': '2021',
                                                           'end': '2022'}, identifier='add-parallel')).preview.workspace
    warnings, _order, _unsorted = job_warnings(added.project)
    labs = job(workspace)
    parallel = next(record.id for record in added.project.facts.records if record.kind == 'employment'
                    and record.employer.raw_text == 'Parallel')
    assert warnings[labs]['overlaps'] == [parallel]
    hidden = hide(added, labs).preview.workspace
    warnings, _order, _unsorted = job_warnings(hidden.project)
    assert 'overlaps' not in warnings[labs] and 'overlaps' not in warnings[parallel] and 'move' not in warnings[labs]


def test_removing_a_hidden_job_takes_its_kept_card_and_undo_brings_both_back(imported):
    workspace, _sources = imported
    identifier = job(workspace)
    hidden = hide(workspace, identifier).preview.workspace
    removed = prepared(hidden, request(hidden, operation='remove', kind=None, record_id=identifier, identifier='remove-hidden'))
    assert removed.preview.workspace.project.hidden_blocks == []
    assert restore(hidden, removed).project.hidden_blocks == hidden.project.hidden_blocks


@pytest.mark.parametrize('operation, record, values', [('hide', True, {'view': 'summary'}), ('show', False, {}),
                                                     ('hide', False, {'view': 'summary', 'other': 'x'})])
def test_a_hide_names_one_job_or_one_block(imported, operation, record, values):
    workspace, _sources = imported
    with pytest.raises(ValueError, match='PANEL_ACTION_UNSUPPORTED'):
        request(workspace, operation=operation, kind=None, record_id=job(workspace) if record else None, values=values)


@pytest.mark.parametrize('case', ['hidden-twice', 'shown-not-hidden', 'header', 'unknown', 'not-a-job'])
def test_a_hide_or_show_the_plan_does_not_offer_is_refused_and_changes_nothing(imported, case):
    workspace, _sources = imported
    before = hide(workspace, 'summary', view='summary').preview.workspace if case == 'hidden-twice' else workspace
    view = {'hidden-twice': 'summary', 'shown-not-hidden': 'summary', 'header': 'identity', 'unknown': 'nothing'}.get(case)
    operation = 'show' if case == 'shown-not-hidden' else 'hide'
    record = next(record.id for record in before.project.facts.records if record.kind == 'education') if case == 'not-a-job' else None
    value = request(before, operation=operation, kind=None, record_id=record, values={'view': view} if view else None)
    raw = canonical(before)
    with pytest.raises(ValueError, match='PANEL_ACTION_UNSUPPORTED'):
        prepare_edit(response(before), value)
    assert canonical(before) == raw


def test_a_resume_with_no_other_blocks_lists_none():
    from tests.templates.test_panel_creation import empty_configure
    empty = empty_configure(lambda _config: None)
    assert 'hideBlocks' not in panel_plan(empty.project)


def test_a_written_summary_keeps_its_model_mark_after_hide_and_show(tmp_path):
    from tests.templates.test_lite_import import lite_run
    fixture, _operation = lite_run(tmp_path, 'promotions')
    workspace = fixture.current()
    notices = [issue for issue in workspace.project.import_issues if issue.code == 'IMPORT_TEXT_GENERATED']
    assert notices and all(issue.block_ids for issue in notices)
    hidden = hide(workspace, 'summary', view='summary').preview.workspace
    back = hide(hidden, 'summary', view='summary', operation='show').preview.workspace
    assert [issue.block_ids for issue in back.project.import_issues] == [issue.block_ids for issue in workspace.project.import_issues]
    assert back.project.facts.model_written == workspace.project.facts.model_written
    assert semantic(back.project.document) == semantic(workspace.project.document)


def test_the_original_marks_the_lines_of_a_hidden_job_and_block_red_until_show(tmp_path):
    from packages.resume_core.repository.source_diff import removals
    from tests.templates.test_lite_import import lite_run
    fixture, _operation = lite_run(tmp_path, 'promotions')
    workspace = fixture.current()
    base = removals(workspace)
    hidden = hide(workspace, job(workspace)).preview.workspace
    hidden = hide(hidden, 'education', view='education').preview.workspace
    red = [row['text'] for row in removals(hidden) if row not in base]
    assert 'Провела переход группы на трёхнедельные релизы' in red
    assert any(text.startswith('Томский институт радиоэлектроники') for text in red)
    back = hide(hidden, 'education', view='education', operation='show').preview.workspace
    back = hide(back, job(workspace), operation='show').preview.workspace
    assert removals(back) == base


def test_undo_and_redo_of_hide_and_show_go_through_the_project_history(tmp_path, imported):
    """The app's Undo reads the project journal: the hidden store is one of its keys, so Undo of Hide puts the blocks back
    and empties the store in one step, and Redo hides them again."""
    workspace, sources = imported
    editor = TemplateEditor(tmp_path, workspace, sources)
    value = request(workspace, operation='hide', kind=None, values={'view': 'summary'}, identifier='hide-history')
    value.operations[0].command.capture = value.capture.model_copy(deep=True)
    editor.edit(value)
    assert len(editor.current().project.hidden_blocks) == 1
    undone = editor.undo('undo-hide', expected='hide-history').response.workspace
    assert undone.project.hidden_blocks == [] and semantic(undone.project.document) == semantic(workspace.project.document)
    redone = editor.redo('redo-hide', expected='hide-history').response.workspace
    assert len(redone.project.hidden_blocks) == 1 and blocks(redone)['view:summary']['hidden']
    shown = request(redone, operation='show', kind=None, values={'view': 'summary'}, identifier='show-history')
    shown.operations[0].command.capture = shown.capture.model_copy(deep=True)
    editor.edit(shown)
    back = editor.undo('undo-show', expected='show-history').response.workspace
    assert len(back.project.hidden_blocks) == 1 and blocks(back)['view:summary']['hidden']
