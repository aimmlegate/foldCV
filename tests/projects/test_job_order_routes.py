"""Job order through the routes (D182): a move and the sort are one history action each with Undo and Redo, and the date
check reads the project and writes nothing. Synthetic data only."""

import pytest

from packages.resume_core.editing.template_panel_jobs import job_lists
from tests.projects.support import Editor, v2_app
from tests.templates.generic_fixtures import generic_import
from tests.templates.test_panel_creation import request


def employers(editor):
    project = editor.workspace().project
    names = {record.id: record.employer.raw_text for record in project.facts.records if record.kind == 'employment'}
    return [names[block.props.record_id] for _parent, cards in job_lists(project) for block in cards]


def edit(editor, identifier, **options):
    return editor.edit(request(editor.workspace(), identifier=identifier, **options).model_dump(mode='json', by_alias=True))


def job(editor, name):
    return next(record.id for record in editor.workspace().project.facts.records if record.kind == 'employment'
        and record.employer.raw_text == name)


@pytest.mark.asyncio
async def test_a_move_and_the_sort_undo_and_redo_and_the_date_check_saves_nothing(tmp_path):
    _fixture, _result, workspace, sources = await generic_import(tmp_path / 'import', 'F10')
    with v2_app(tmp_path / 'app', [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        edit(editor, 'add-early', values={'employer': 'Early Corp', 'role': 'Dev', 'start': '2010', 'end': '2012'})
        assert employers(editor) == ['Example Labs', 'Early Corp']
        edit(editor, 'move-up', operation='move_job', kind='employment', record_id=job(editor, 'Early Corp'),
            values={'direction': 'up'})
        assert employers(editor) == ['Early Corp', 'Example Labs']
        assert editor.response['presentation']['editor']['sortJobs'] is True
        assert editor.history['undo']['actionId'] == 'move-up'
        editor.step('undo', 'undo-move')
        assert employers(editor) == ['Example Labs', 'Early Corp']
        editor.step('redo', 'redo-move')
        assert employers(editor) == ['Early Corp', 'Example Labs']
        edit(editor, 'sort', operation='sort_jobs', kind='employment')
        assert employers(editor) == ['Example Labs', 'Early Corp']
        assert 'sortJobs' not in editor.response['presentation']['editor']
        editor.step('undo', 'undo-sort')
        assert employers(editor) == ['Early Corp', 'Example Labs']
        editor.step('redo', 'redo-sort')
        assert employers(editor) == ['Example Labs', 'Early Corp']
        # The plan's row order follows the page after each step.
        order = editor.response['presentation']['editor']['jobOrder']
        assert order[:2] == [job(editor, 'Example Labs'), job(editor, 'Early Corp')]
        revision, history = editor.revision, editor.history
        early = editor.workspace().project.facts.records
        record = next(value for value in early if value.id == job(editor, 'Early Corp'))
        key = f'period:{record.periods[0].id}:'
        found = editor.call('post', '/date-check', {'recordId': record.id, 'values': {key + 'start': '2021', key + 'end': '2022'}})
        assert found == {'schemaVersion': 1, 'warnings': [
            {'kind': 'overlap', 'recordId': job(editor, 'Example Labs'), 'period': '03.2020 – 11.2023'}]}
        added = editor.call('post', '/date-check', {'recordId': None, 'values': {'start': '2012', 'end': '2011'}})
        assert added['warnings'][0] == {'kind': 'reversed'}
        refused = editor.refused('post', '/date-check', {'recordId': None, 'values': {'employer': 'x'}}, 422)
        assert refused['error']['code'] == 'DATE_CHECK_UNAVAILABLE'
        reopened = Editor(client, workspace.project_id)
        assert reopened.revision == revision and reopened.history == history
        assert employers(reopened) == ['Example Labs', 'Early Corp']
