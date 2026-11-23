"""F3 of the tester feedback of 2026-11-23 through the edit route: one commit, one Undo, codes that reach the client."""

from tests.projects.support import Editor, v2_app
from tests.templates.e04_fixtures import TASK, e04_workspace
from tests.templates.test_range_removal import blocks, edge, line, shown
from tests.templates.test_structural_preparation import intent


def request(editor, kind, identifier, **values):
    value = intent(editor.workspace(), kind, **values)
    value.client_mutation_id, value.capture.action_id = identifier, 'action-' + identifier
    return value.model_dump(mode='json', by_alias=True)


def test_a_range_is_one_commit_and_one_undo(tmp_path):
    workspace, sources = e04_workspace()
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        before = editor.workspace()
        first, second = line(before, TASK.rstrip('.')), line(before, TASK.rstrip('.'), 1)
        result = editor.edit(request(editor, 'remove_range', 'range-1', start=edge(first, 12), end=edge(second, 18)))
        assert result['revision'] > before.project_revision and not result['replayed']
        assert shown(next(block for block in blocks(editor.workspace()) if block.id == first.id)) == 'Implemented processing'
        assert result['history']['undo']['actionId'] == 'action-range-1'
        editor.step('undo', 'undo-1', expected='action-range-1')
        after = editor.workspace()
        assert [shown(block) for block in blocks(after) if isinstance(block.content, list)] == [
            shown(block) for block in blocks(before) if isinstance(block.content, list)]
        assert editor.history['undo'] is None or editor.history['undo']['actionId'] != 'action-range-1'


def test_a_refused_range_keeps_its_code_and_changes_nothing(tmp_path):
    workspace, sources = e04_workspace()
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        before = editor.workspace()
        employer, python = line(before, 'Example Labs'), line(before, 'Python')
        body = editor.edit(request(editor, 'remove_range', 'range-2', start=edge(employer, 3), end=edge(python, 2)), status=422)
        assert body['error']['code'] == 'TECHNOLOGY_IN_FACTS'
        assert editor.workspace().project_revision == before.project_revision
