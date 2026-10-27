"""POST /v2/projects/{id}/clipboard: a retried capture id returns the same metadata, a reused id or a stale snapshot is
refused, and a refused capture retains nothing."""

from tests.projects.support import Editor, v2_app
from tests.templates.golden.corpus import corpus, loaded


def fixture():
    data = corpus()
    entry = next(item for item in data['entries'] if item['name'] == 'paste_inline_same_project')
    return entry['clipboard'], loaded(data['fixtures'][entry['fixture']])


def request(editor, selection, identifier):
    return {'editorToken': editor.token, 'clientCaptureId': identifier, 'snapshot': editor.response['snapshot'],
        'selection': selection}


def test_a_retried_capture_returns_the_same_metadata_and_a_reused_id_is_refused(tmp_path):
    selection, (workspace, sources) = fixture()
    with v2_app(tmp_path, [(workspace, sources)]) as (client, application):
        editor = Editor(client, workspace.project_id)
        first = editor.call('post', '/clipboard', request(editor, selection, 'copy-1'))
        assert set(first) == {'schemaVersion', 'clipboardCaptureId', 'projectId', 'sourceSnapshot', 'selection'}
        assert editor.call('post', '/clipboard', request(editor, selection, 'copy-1')) == first
        other = {**selection, 'range': {**selection['range'], 'end': selection['range']['end'] - 1}}
        refused = editor.refused('post', '/clipboard', request(editor, other, 'copy-1'), 409)
        assert refused['error']['code'] == 'MUTATION_ID_REUSED'
        assert list(application.state.projects.repository.open(workspace.project_id).clipboard) == [first['clipboardCaptureId']]


def test_a_stale_snapshot_or_a_replaced_page_is_refused_without_a_capture(tmp_path):
    selection, (workspace, sources) = fixture()
    with v2_app(tmp_path, [(workspace, sources)]) as (client, application):
        editor = Editor(client, workspace.project_id)
        stale = request(editor, selection, 'stale-copy')
        stale['snapshot'] = {**stale['snapshot'], 'documentRevision': stale['snapshot']['documentRevision'] + 1}
        assert editor.refused('post', '/clipboard', stale, 409)['error']['code'] == 'DEPENDENCY_CHANGED'
        replaced = request(editor, selection, 'replaced-copy')
        Editor(client, workspace.project_id)
        assert editor.refused('post', '/clipboard', replaced, 409)['error']['code'] == 'EDITOR_REPLACED'
        assert not application.state.projects.repository.open(workspace.project_id).clipboard
