"""F7 (D179): a job, education or language card off the page, or a field line of a card that stays, comes back from
Facts where the template puts it, once, with the facts' present values; one history action. The documents are lite
imports of invented CVs."""

import pytest

from packages.resume_core.editing.mutations import apply_rich_mutation
from packages.resume_core.editing.off_page import off_fields, off_page
from packages.resume_core.editing.template_panel_records import panel_plan
from packages.resume_core.editing.template_preparation import prepare_edit
from packages.resume_core.fields import inline_groups, occurrences, set_text
from packages.resume_core.models.assistant import DeleteBlocksOp
from packages.resume_core.models.rich_document import FactFieldSpan
from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.repository.assistant_compiler import compile_ops
from resume_api.projects.service import response_for_workspace
from tests.templates.test_focus_panel import undone
from tests.templates.test_lite_import import lite_run
from tests.templates.test_template_preparation import response


# By source, the import records (the fixtures share one project id): an edit's workspace is slim, as in memory (D104); the route reads them from history.
RECORDS = {}


def imported(tmp_path_factory, name):
    workspace = lite_run(tmp_path_factory.mktemp('restore-' + name), name)[0].current()
    RECORDS[workspace.project.sources[0].byte_sha256] = list(workspace.project.template_operations)
    return workspace


@pytest.fixture(scope='module')
def promotions(tmp_path_factory):
    return imported(tmp_path_factory, 'promotions')


@pytest.fixture(scope='module')
def junior(tmp_path_factory):
    return imported(tmp_path_factory, 'junior')


def cards(workspace, view):
    return [block for block in workspace.project.document.blocks() if block.type == 'section'
        and block.props.record_id is not None and block.presentation is not None and block.presentation.view_key == view]


def deleted(workspace, block_ids, name='delete'):
    """The workspace after the user deleted these blocks, as an edit deletes them."""
    after, _created = compile_ops(workspace, [DeleteBlocksOp(op='delete_blocks', blockIds=block_ids)], action_id=name,
        occupied=set(), response_for=response_for_workspace)
    return after


def without_card(workspace, view, index=0):
    card = cards(workspace, view)[index]
    return deleted(workspace, [child.id for child in card.children]), card.props.record_id


def restore(before, record_id, values=None, identifier="restore", operations=None):
    capture = {'sessionId': 'session', 'actionId': identifier, 'actionToken': 1, 'dependencies': []}
    request = TemplateEditPreparationV1(schemaVersion=1, clientMutationId=identifier, snapshot=response(before).snapshot,
        capture=capture, operations=[{'kind': 'builtin_panel', 'opId': 'panel', 'command': {'operation': 'restore',
            'recordId': record_id, 'recordKind': None, 'jobId': None, 'periodId': None, 'values': values or {},
            'factsRevision': before.project.facts.revision, 'documentRevision': before.document_revision, 'capture': capture}}])
    result = prepare_edit(response(before), request, operations=RECORDS[before.project.sources[0].byte_sha256] if operations is None else operations)
    assert result.mutation is not None
    return apply_rich_mutation(before, result.mutation)[0], result


def shown_records(workspace):
    return [span.record_id for block in workspace.project.document.blocks() for _key, content in inline_groups(block)
        for span in content if isinstance(span, FactFieldSpan)]


def test_a_new_import_offers_nothing_to_put_back(promotions, junior):
    for workspace in (promotions, junior):
        plan = panel_plan(workspace.project)
        assert 'offPage' not in plan and 'offPageFields' not in plan
        assert not off_page(workspace.project)


def test_a_removed_job_card_comes_back_once_in_its_place_with_its_bullets_and_one_undo(promotions):
    before = promotions
    order = [card.props.record_id for card in cards(before, 'projects')]
    removed, job = without_card(before, 'projects', 1)
    assert job not in [card.props.record_id for card in cards(removed, 'projects')]
    plan = panel_plan(removed.project)
    assert plan['offPage'] == [job]
    after, result = restore(removed, job)
    assert [card.props.record_id for card in cards(after, 'projects')] == order, 'the order of the import'
    # Each fact of the card is shown once, as the import showed it.
    assert sorted(shown_records(after)) == sorted(shown_records(before))
    assert {(group.record_id, group.key) for group in occurrences(after.project.document).values()} == \
        {(group.record_id, group.key) for group in occurrences(before.project.document).values()}
    assert 'offPage' not in panel_plan(after.project)
    undone(removed, after, result)


def test_a_card_is_not_placed_twice(promotions):
    removed, job = without_card(promotions, 'projects', 1)
    after, _result = restore(removed, job)
    with pytest.raises(ValueError):
        restore(after, job, identifier='again')


def test_a_card_whose_view_lost_every_card_comes_back_with_its_title(junior):
    before = junior
    card = cards(before, 'education')
    removed = deleted(before, [child.id for value in card for child in value.children])
    titles = [block for block in removed.project.document.blocks() if block.type == 'heading'
        and block.presentation is not None and block.presentation.view_key == 'education']
    after, _result = restore(removed, card[0].props.record_id)
    assert [value.props.record_id for value in cards(after, 'education')] == [card[0].props.record_id]
    shown_titles = [block for block in after.project.document.blocks() if block.type == 'heading'
        and block.presentation is not None and block.presentation.view_key == 'education']
    assert len(shown_titles) == 1, 'the title comes back, or stays, once' if titles else 'the title comes back'


def test_a_value_edited_in_facts_while_off_the_page_comes_back_edited(junior):
    removed, record_id = without_card(junior, 'languages')
    edited = removed.model_copy(deep=True)
    record = next(value for value in edited.project.facts.records if value.id == record_id)
    set_text(record, 'level', 'Synthetic level')
    edited.project.facts.revision += 1
    after, _result = restore(edited, record_id)
    texts = [span.text for block in after.project.document.blocks() for _key, content in inline_groups(block)
        for span in content if isinstance(span, FactFieldSpan) and span.record_id == record_id]
    assert 'Synthetic level' in texts


def test_the_dialog_of_a_removed_card_offers_its_fields(junior):
    removed, record_id = without_card(junior, 'education')
    assert record_id not in panel_plan(removed.project).get('unshownFields', {})


def test_a_removed_field_line_of_a_card_that_stays_comes_back_at_its_node(promotions):
    before = promotions
    card = cards(before, 'projects')[0]
    line = next(child for child in card.children if child.presentation.node_index == 4)
    removed = deleted(before, [line.id])
    job = card.props.record_id
    assert off_fields(removed.project)[job] == ['role']
    assert panel_plan(removed.project)['offPageFields'] == {job: ['role']}
    after, result = restore(removed, job, {'field': 'role'})
    assert (job, 'role') in {(group.record_id, group.key) for group in occurrences(after.project.document).values()}
    assert job not in off_fields(after.project)
    undone(removed, after, result)


def test_a_kind_with_no_control_is_refused(promotions):
    claim = next(record.id for record in promotions.project.facts.records if record.kind == 'claim')
    with pytest.raises(ValueError):
        restore(promotions, claim)
    job = cards(promotions, 'projects')[0].props.record_id
    with pytest.raises(ValueError):
        restore(promotions, job, {'field': 'employer'})


def test_the_route_builds_the_card_from_the_import_records_in_the_history_files(tmp_path):
    from tests.projects.support import Editor, v2_app
    fixture, _operation = lite_run(tmp_path / 'import', 'promotions')
    workspace = fixture.current()
    card = cards(workspace, 'projects')[1]
    with v2_app(tmp_path / 'app', [(workspace, fixture.originals)]) as (client, application):
        project = workspace.project_id
        assert not application.state.projects.repository.open(project).workspace.project.template_operations, 'memory is slim'
        editor = Editor(client, project)

        def preparation(identifier, operation):
            capture = {'sessionId': 'session', 'actionId': identifier, 'actionToken': 1, 'dependencies': []}
            return {'schemaVersion': 1, 'clientMutationId': identifier, 'snapshot': editor.response['snapshot'],
                'capture': capture, 'operations': [{**operation, 'opId': 'op'}]}
        editor.edit(preparation('remove', {'kind': 'remove_occurrences', 'blocks': [{'blockId': child.id,
            'beforeRevision': child.revision} for child in card.children]}))
        current = editor.workspace()
        assert editor.response['presentation']['editor']['offPage'] == [card.props.record_id]
        capture = {'sessionId': 'session', 'actionId': 'restore', 'actionToken': 1, 'dependencies': []}
        editor.edit({**preparation('restore', {'kind': 'builtin_panel', 'command': {'operation': 'restore',
            'recordId': card.props.record_id, 'recordKind': None, 'jobId': None, 'periodId': None, 'values': {},
            'factsRevision': current.project.facts.revision, 'documentRevision': current.document_revision, 'capture': capture}}),
            'capture': capture})
        assert card.props.record_id in [value.props.record_id for value in cards(editor.workspace(), 'projects')]
        assert 'offPage' not in editor.response['presentation']['editor']
        editor.step('undo', 'undo-restore')
        assert card.props.record_id not in [value.props.record_id for value in cards(editor.workspace(), 'projects')]
