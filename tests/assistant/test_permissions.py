"""Permissions: internet follows the run's flag; edits off still allows a draft; Apply needs the current editor."""

from packages.resume_core.models.agent import AgentWebSource
from tests.assistant.support import PROJECT, Editor, apply, assistant_app, base, conversation, finish, proposals, proposing, run_once, start

REPLACE = {'op': 'replace_text', 'blockId': 'block-paper-a', 'find': 'Shared', 'replace': 'Common'}


class Fetcher:
    def __init__(self):
        self.urls = []

    async def fetch(self, request, _cancel):
        self.urls.append(request.url)
        return AgentWebSource(id='source_page', runId='run_placeholder', requestedUrl=request.url, finalUrl=request.url,
            title='Вакансия', retrievedAt='2026-10-27T10:00:00+00:00', contentSha256='a' * 64, text='Python, Kafka',
            truncated=False, originalBytes=13)


def test_internet_off_refuses_public_pages_and_on_fetches_and_records_the_source(tmp_path):
    results = []

    async def steps(tools, _value, _cancel, _emit):
        results.append(await tools.call('read_public_page', {'url': 'https://example.test/job'}))
        return 'Готово.'
    with assistant_app(tmp_path, steps) as (client, application, runtime):
        fetcher = application.state.assistant._fetcher = Fetcher()
        cid = conversation(client)
        finish(client, start(client, cid, web=False))
        assert results[0] == {'error': {'code': 'AGENT_WEB_DISABLED'}} and fetcher.urls == []
        finish(client, start(client, cid, web=True, request_id='request-2'))
        assert results[1]['source']['id'] == 'source_page' and results[1]['excerpt'] == 'Python, Kafka'
        messages = client.get(base() + f'/conversations/{cid}/messages').json()
        assert [source['id'] for source in messages['sources']] == ['source_page']
        assert messages['messages'][-1]['sources'][0]['label'] == 'Вакансия'


def test_edits_off_still_allows_a_draft_that_applies_once_edits_are_on(tmp_path):
    with assistant_app(tmp_path) as (client, _application, runtime):
        run, _events = run_once(client, proposing(REPLACE), runtime, edits=False)
        assert run['state'] == 'completed' and run['allowEdits'] is False
        proposal = proposals(client)[0]
        editor = Editor(client, PROJECT)
        assert apply(client, editor, proposal['id'], edits=False, status=409)['error']['code'] == 'ASSISTANT_EDITS_OFF'
        assert apply(client, editor, proposal['id'])['proposal']['state'] == 'applied'


def test_apply_from_a_replaced_or_unknown_editor_is_refused(tmp_path):
    with assistant_app(tmp_path) as (client, _application, runtime):
        run_once(client, proposing(REPLACE), runtime)
        proposal = proposals(client)[0]
        old = Editor(client, PROJECT)
        Editor(client, PROJECT)
        assert apply(client, old, proposal['id'], status=409)['error']['code'] == 'EDITOR_REPLACED'
        old.token = 'editor_unknown'
        assert apply(client, old, proposal['id'], status=409)['error']['code'] == 'EDITOR_TOKEN_UNKNOWN'
        assert proposals(client)[0]['state'] == 'draft'
