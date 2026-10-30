"""POST /v2/projects/{id}/rewrite/preview: one generation over the exact selected text with the captured reasoning;
the preview never edits the project, a stale selection is refused before the model, and Apply is an ordinary edit."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import threading

import pytest

from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.reasoning import ModelReasoning
from tests.settings.test_rewrite_reasoning import Adapter
from packages.resume_core.templates.presentation import snapshot_identity
from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt
from resume_api.app import ProviderSlot
from resume_api.cli.profiles.claude import ClaudeCliProfile
from resume_api.connection import Metadata, Quota
from resume_api.providers.content import ContentResult, ReportedUsage
from resume_api.template_rewrite import EARLY_CANCELS_KEPT, TemplateRewrite
from tests.projects.support import Editor, v2_app
from tests.service.app_fixtures import HealthyConnection, add_project, make_app, open_project, signed_in
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


def test_a_rewrite_runs_on_the_chosen_rewrite_model_at_a_level_that_model_reports(tmp_path):
    provider = Provider('Clear')
    with v2_app(tmp_path, [papers()], content_provider=provider, connection_adapter=Adapter()) as (client, _application):
        client.post('/v1/host/status', json={})
        client.post('/v1/host/select', json={'model': 'model-a'})
        assert client.put('/v1/settings/rewrite-reasoning', json={'model': 'model-a', 'effort': 'low'}).status_code == 200
        editor = Editor(client, PROJECT)
        preview(editor, request_id='rewrite-a')
        # A processing model changed elsewhere keeps the saved level; this model lacks it and runs at its default.
        client.post('/v1/host/select', json={'model': 'model-b'})
        preview(editor, request_id='rewrite-b')
        client.post('/v1/host/select', json={'model': 'model-a'})
        assert client.put('/v1/settings/rewrite-model', json={'model': 'model-b'}).status_code == 200
        assert client.put('/v1/settings/rewrite-reasoning', json={'model': 'model-b', 'effort': 'high'}).status_code == 200
        preview(editor, request_id='rewrite-c')
    assert [(request.policy.model, request.policy.reasoning_effort) for request in provider.requests] == [
        ('model-a', 'low'), ('model-b', None), ('model-b', 'high')]


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


def test_a_rewrite_finishes_while_an_import_holds_its_inference_permit(tmp_path):
    from resume_api.inference_admission import INFERENCE
    provider = Provider('Clear')
    with v2_app(tmp_path, [papers()], content_provider=provider) as (client, _application):
        editor = Editor(client, PROJECT)
        # D121: a running import on either provider no longer queues the rewrite.
        assert INFERENCE.acquire(blocking=False)
        try:
            assert preview(editor)['text'] == 'Clear'
        finally:
            INFERENCE.release()


def test_a_cancel_sent_before_the_preview_registers_stops_it_before_the_model(tmp_path):
    provider = Provider('Clear')
    with v2_app(tmp_path, [papers()], content_provider=provider) as (client, _application):
        editor = Editor(client, PROJECT)
        assert editor.call('post', '/rewrite/cancel', {'editorToken': editor.token, 'requestId': 'rewrite-1'}) == {'cancelled': True}
        assert preview(editor, status=409)['error']['code'] == 'CANCELLED'
        assert provider.requests == []
        task, = [task for task in client.get('/v2/projects/' + PROJECT + '/tasks').json()['tasks'] if task['kind'] == 'rewrite']
        assert (task['state'], task['error']) == ('cancelled', 'CANCELLED')
        # The cancel named one request; the next one runs.
        assert preview(editor, request_id='rewrite-2')['text'] == 'Clear'


def test_early_cancels_are_bounded():
    rewrite = TemplateRewrite(lambda: None, preferences=None, temp_root=None, worker_slot=None, cleanup_error=None)
    for number in range(EARLY_CANCELS_KEPT + 5):
        assert rewrite.cancel('project', str(number))
    assert len(rewrite.early) == EARLY_CANCELS_KEPT and ('project', '0') not in rewrite.early


class Queued(Provider):
    """Reports the task stage it sees while waiting for its permit and after admission."""

    def __init__(self, stage):
        super().__init__('Clear')
        self.stage, self.stages = stage, []

    def generate_queued(self, request, files, cancel, admitted):
        self.stages.append(self.stage())
        admitted()
        self.stages.append(self.stage())
        return self.generate(request, files, cancel)


def test_the_task_stage_is_queued_until_the_provider_admits_the_call(tmp_path):
    stage = {}
    provider = Queued(lambda: stage['read']())
    with v2_app(tmp_path, [papers()], content_provider=provider) as (client, application):
        stage['read'] = lambda: application.state.projects.tasks.list(PROJECT)[-1]['stage']
        assert preview(Editor(client, PROJECT))['text'] == 'Clear'
    assert provider.stages == ['queued', 'generating']


@pytest.mark.asyncio
async def test_a_cancelled_handler_stops_its_model_call_and_worker(tmp_path):
    entered, finished, seen = threading.Event(), threading.Event(), {}

    class Held:
        def generate(self, request, files, cancel):
            seen['process'] = files.spawn(Path(sys.executable), ('-c', 'import signal; signal.pause()'), capture=False)
            entered.set()
            seen['cancelled'] = cancel.wait(5)
            finished.set()
            return ContentResult(PlainTextReply(text='Clear'), ReportedUsage(), 'fixture', request.policy.model, .01, 1)

    @asynccontextmanager
    async def slot(_cancel):
        yield

    rewrite = TemplateRewrite(lambda: (Held(), 'fixture'), preferences=None, temp_root=tmp_path, worker_slot=slot,
        cleanup_error=lambda _error: None)
    handler = asyncio.create_task(rewrite.text('project', 'rewrite-1', 'Make clearer.', 'Shared'))
    await asyncio.to_thread(entered.wait, 5)
    handler.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handler
    assert seen['process'].poll() is not None, 'the worker process stops with the handler'
    await asyncio.to_thread(finished.wait, 6)
    assert seen['cancelled'] is True
    assert rewrite.cancels == {} and rewrite.tasks == {} and rewrite.files == {}


class QuotaAdapter:
    executable = None

    def __init__(self, quota):
        self.quota = quota

    def inspect(self, _files, _cancel, *, full=True):
        return Metadata('2.1.320 (Claude Code)', ('claude-sonnet-5-5',), 'max', Quota(self.quota),
            {'claude-sonnet-5-5': ModelReasoning(default='high', supported=['low', 'high'])}, 'graceful')


class ClaudeProvider(Provider):
    template_adapter = 'claude_cli'

    def invalidate_preflight(self):
        pass


@pytest.mark.asyncio
async def test_a_rewrite_on_an_exhausted_plan_names_the_plan(tmp_path):
    executable = tmp_path / 'cli'
    executable.write_text('#!' + sys.executable + '\n')
    executable.chmod(0o700)
    slot = ProviderSlot(QuotaAdapter('exhausted'), ClaudeProvider('Clear'), ClaudeCliProfile(tmp_path / 'claude profile', executable))
    app = make_app(tmp_path, connection_adapter=HealthyConnection(), provider_slots={'claude_cli': slot})
    add_project(app)
    async with signed_in(app) as client:
        await client.post('/v1/host/enable', json={'provider': 'claude_cli', 'enabled': True})
        assert (await client.post('/v1/host/status', json={'provider': 'claude_cli'})).json()['state'] == 'quota_exhausted'
        await client.post('/v1/host/select', json={'provider': 'claude_cli', 'model': 'claude-sonnet-5-5'})
        token, snapshot = await open_project(client)
        reply = await client.post(f'/v2/projects/{PROJECT}/rewrite/preview', json={'editorToken': token, 'requestId': 'rewrite-1',
            'snapshot': snapshot, 'instruction': 'Make clearer.',
            'range': {'blockId': 'block-paper-a', 'beforeRevision': 1, 'cellId': None, 'field': 'content', 'start': 0, 'end': 6}})
    assert (reply.status_code, reply.json()['error']['code']) == (409, 'QUOTA_EXHAUSTED')
