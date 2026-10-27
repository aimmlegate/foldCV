"""POST /v2/projects/{id}/history: one stack for paste and panel edits, a stale expected action, and replace barriers."""

from tests.projects.support import Editor, v2_app
from tests.templates.golden.corpus import corpus, loaded, with_capture

CORPUS = corpus()


def entry(name):
    value = next(item for item in CORPUS['entries'] if item['name'] == name)
    return value, loaded(CORPUS['fixtures'][value['fixture']])


def text(response, index=0):
    return ''.join(span.get('text', '') for span in response['workspace']['project']['document']['regions'][2]['blocks'][index]['content'])


def test_undo_after_a_paste_and_a_text_edit_walks_one_stack(tmp_path):
    paste, (workspace, sources) = entry('paste_inline_same_project')
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        original = text(editor.response)
        capture = editor.capture(paste['clipboard'], 'copy-1')
        pasted = editor.edit(with_capture(paste['preparation'], capture['clipboardCaptureId']))
        after_paste = text(pasted['response'])
        typed = editor.workspace()
        from tests.templates.test_template_preparation import command
        value = command(typed, start=0, end=3, text='Typed')
        value.client_mutation_id, value.capture.action_id = 'typed-1', 'typing'
        editor.edit(value.model_dump(mode='json', by_alias=True))
        assert editor.history['undo']['actionId'] == 'typing'
        editor.step('undo', 'undo-1', expected='typing')
        assert text(editor.response) == after_paste and editor.history['undo']['actionId'] == paste['preparation']['capture']['actionId']
        editor.step('undo', 'undo-2', expected=paste['preparation']['capture']['actionId'])
        assert text(editor.response) == original and editor.history['undo'] is None
        assert editor.history['redo']['actionId'] == paste['preparation']['capture']['actionId']


def test_undo_of_a_panel_edit_restores_the_fact_and_its_display(tmp_path):
    panel, (workspace, sources) = entry('builtin_panel')
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        before = editor.response['workspace']['project']['facts']['records']
        edited = editor.edit(panel['preparation'])
        assert edited['response']['workspace']['project']['facts']['records'] != before
        editor.step('undo', 'undo-panel', expected=panel['preparation']['capture']['actionId'])
        restored = editor.response['workspace']['project']['facts']['records']
        strip = lambda records: [{key: value for key, value in record.items() if key != 'revision'} for record in records]
        assert strip(restored) == strip(before)


def test_a_stale_expected_action_is_refused_with_the_current_history(tmp_path):
    paste, (workspace, sources) = entry('paste_inline_literal')
    with v2_app(tmp_path, [(workspace, sources)]) as (client, _application):
        editor = Editor(client, workspace.project_id)
        editor.edit(paste['preparation'])
        body = editor.step('undo', 'undo-1', expected='not-the-top', status=409)
        assert body['error']['code'] == 'HISTORY_STALE'
        assert body['history']['undo']['actionId'] == paste['preparation']['capture']['actionId']


def test_a_replace_that_changes_undoable_keys_clears_history_and_one_that_does_not_keeps_it(tmp_path):
    paste, (workspace, sources) = entry('paste_inline_literal')
    with v2_app(tmp_path, [(workspace, sources)]) as (client, application):
        editor = Editor(client, workspace.project_id)
        editor.edit(paste['preparation'])
        repository = application.state.projects.repository
        renamed = editor.call('post', '/rename', {'editorToken': editor.token, 'baseRevision': editor.revision, 'title': 'Renamed'})
        assert renamed['workspace']['title'] == 'Renamed'
        editor.response = renamed
        reopened = editor.call('get', '')
        assert reopened['workspace']['title'] == 'Renamed'
        assert repository.open(workspace.project_id).journal.state()['undo'] is not None
        changed = repository.read(workspace.project_id).model_copy(deep=True)
        changed.project.document.regions[2].blocks[1].content[0].text = 'Published by an import'
        repository.replace(workspace.project_id, base_revision=changed.project_revision, workspace=changed, reason='import')
        assert repository.open(workspace.project_id).journal.state() == {'undo': None, 'redo': None}
        assert Editor(client, workspace.project_id).history == {'undo': None, 'redo': None}
