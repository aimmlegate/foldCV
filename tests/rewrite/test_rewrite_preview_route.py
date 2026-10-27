"""POST /v2/projects/{id}/rewrite/preview: one generation over the exact selected text with the captured reasoning;
the preview never edits the project, a stale selection is refused before the model, and Apply is an ordinary edit."""

from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.templates.presentation import snapshot_identity
from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt
from resume_api.providers.content import ContentResult, ReportedUsage
from tests.projects.support import Editor, v2_app
from tests.projects.test_edit_routes import typing
from tests.templates.storage_fixtures import workspace as papers

PROJECT = 'template-project'


class Provider:
    """Answers with fixed text, or with the selected text itself when no reply is set."""

    def __init__(self, reply=None):
        self.requests, self.reply = [], reply

    def generate(self, request, _files, _cancel):
        self.requests.append(request)
        source = request.text.split('\n\nSelected text:\n', 1)[1]
        return ContentResult(PlainTextReply(text=self.reply or source), ReportedUsage(), 'fixture', request.policy.model, .01, 1)


def preview(editor, *, request_id='rewrite-1', block='block-paper-a', end=6, snapshot=None, status=200):
    workspace = editor.workspace()
    body = {'editorToken': editor.token, 'requestId': request_id,
        'snapshot': snapshot or snapshot_identity(workspace).model_dump(mode='json', by_alias=True),
        'range': {'blockId': block, 'beforeRevision': 1, 'cellId': None, 'field': 'content', 'start': 0, 'end': end},
        'instruction': 'Make clearer.'}
    if status != 200:
        return editor.refused('post', '/rewrite/preview', body, status)
    return editor.call('post', '/rewrite/preview', body)


def history_file(application):
    path = application.state.projects.repository.open(PROJECT).directory / 'history.jsonl'
    return path.read_bytes() if path.is_file() else None


def test_the_model_gets_only_the_selected_text_and_the_captured_reasoning_and_the_project_stays_unchanged(tmp_path):
    preferences = PreferencesStore(tmp_path / 'data')
    preferences.select_model('fixture')
    preferences.select_rewrite_reasoning('fixture', 'low')
    provider = Provider('Clear')
    with v2_app(tmp_path, [papers()], content_provider=provider) as (client, application):
        editor = Editor(client, PROJECT)
        before, journal = editor.workspace(), history_file(application)
        result = preview(editor)
        assert (result['source'], result['text'], result['requestId']) == ('Shared', 'Clear', 'rewrite-1')
        request, = provider.requests
        assert request.text == plain_prompt('Make clearer.', 'Shared') and request.result_type is PlainTextReply
        assert request.policy.reasoning_effort == 'low' and not request.policy.allow_repair
        assert application.state.projects.repository.read(PROJECT) == before
        assert history_file(application) == journal
        task, = [task for task in client.get('/v2/projects/' + PROJECT + '/tasks').json()['tasks'] if task['kind'] == 'rewrite']
        assert task['state'] == 'succeeded'


def test_an_unchanged_reply_is_a_preview_without_any_edit(tmp_path):
    with v2_app(tmp_path, [papers()], content_provider=Provider()) as (client, application):
        editor = Editor(client, PROJECT)
        before = editor.workspace()
        result = preview(editor, end=12)
        assert result['text'] == result['source'] == 'Shared title'
        assert application.state.projects.repository.read(PROJECT) == before


def test_a_stale_snapshot_or_a_missing_block_is_refused_before_the_model(tmp_path):
    provider = Provider('Clear')
    with v2_app(tmp_path, [papers()], content_provider=provider) as (client, _application):
        editor = Editor(client, PROJECT)
        stale = snapshot_identity(editor.workspace()).model_dump(mode='json', by_alias=True)
        editor.edit(typing(editor, 'Human', 'edit-1'))
        assert preview(editor, snapshot=stale, status=422)['error']['code'] == 'V7_INPUT_REJECTED'
        assert preview(editor, block='missing-block', status=422)['error']['code'] == 'V7_INPUT_REJECTED'
        assert provider.requests == []


def test_applying_a_corrected_preview_is_one_edit_of_the_selected_range(tmp_path):
    with v2_app(tmp_path, [papers()], content_provider=Provider('Clearer')) as (client, _application):
        editor = Editor(client, PROJECT)
        result = preview(editor)
        # The user corrects the preview text before Apply; Apply sends it as a normal range edit.
        applied = editor.edit(typing(editor, result['text'] + ' 🚀', 'apply-1'))
        assert applied['revision'] == 2 and applied['changedBlockIds'] == ['block-paper-a']
        content = applied['response']['workspace']['project']['document']['regions'][2]['blocks'][0]['content']
        assert ''.join(span['text'] for span in content) == 'Clearer 🚀 title'
        assert applied['history']['undo']['actionId'] == 'action-apply-1'
