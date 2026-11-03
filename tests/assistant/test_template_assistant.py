"""The template assistant (D136): its own scope without the repository, the draft tools, proposals, concurrency with
a resume run, and the run routes under /v2/templates/assistant."""

import asyncio
import hashlib
import json
import threading

from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from resume_api.assistant.skills import SKILLS, TEMPLATE_SKILLS, skill_catalog
from resume_api.assistant.template_tools import (ACTIVE_SECONDS, TEMPLATE_BASE_INSTRUCTIONS,
    TEMPLATE_DEVELOPER_INSTRUCTIONS, TEMPLATE_TOOL_NAMES)
from resume_api.assistant.tools import TOOL_NAMES
from tests.assistant.support import assistant_app, base, conversation, finish, start
from tests.assistant.template_support import (TBASE, template_conversation, template_finish, template_request,
    template_start, using)
from tests.assistant.test_runs_lifecycle import settings, wait

GENERIC = 'generic-two-column'
TEXT = BUNDLED_TEMPLATE.read_text(encoding='utf-8')
REVISION = next(line for line in TEXT.splitlines() if line.startswith('  revision: '))
NAME = '  name: Две колонки\n'


def test_the_template_scope_has_no_resume_tool_and_no_repository(tmp_path):
    seen = {}

    async def steps(tools, value, _cancel, _emit):
        seen[value.allow_web] = (value.tools, await tools.listed(), value.base_instructions, value.developer_instructions,
            value.active_seconds, value.prompt)
        return 'Готово.'
    with assistant_app(tmp_path) as (client, application, runtime):
        using(runtime, steps)
        service = application.state.template_assistant
        assert service.projects is None and service.store.root == tmp_path / 'data/assistant-templates'
        resume_only = set(TOOL_NAMES) - {'read_skill', 'read_public_page'}
        assert not resume_only & set(TEMPLATE_TOOL_NAMES)
        capabilities = client.get(TBASE + '/capabilities').json()
        assert capabilities['ready'] is True and capabilities['tools'] == list(TEMPLATE_TOOL_NAMES)
        assert client.get(base() + '/capabilities').json()['tools'] == list(TOOL_NAMES)
        cid = template_conversation(client)
        for web, request_id in ((False, 'off'), (True, 'on')):
            run = template_start(client, cid, TEXT, web=web, request_id=request_id)
            assert run['projectId'] == 'templates' and run['allowEdits'] is False and run['baseRevision'] == 1
            assert template_finish(client, run)[0]['state'] == 'completed'
        offered, listed, base_text, developer, active, prompt = seen[False]
        assert 'read_public_page' not in offered and sorted(offered) == listed
        assert set(offered) == set(TEMPLATE_TOOL_NAMES) - {'read_public_page'}
        assert set(seen[True][0]) == set(seen[True][1]) == set(TEMPLATE_TOOL_NAMES)
        assert (base_text, developer, active) == (TEMPLATE_BASE_INSTRUCTIONS, TEMPLATE_DEVELOPER_INSTRUCTIONS, ACTIVE_SECONDS)
        assert 'resume' not in json.loads(prompt.split('\n', 1)[1]) and TEXT not in prompt
        # Template conversations live in their own store; a project id path never reaches them.
        assert (tmp_path / 'data/assistant-templates/templates/conversations' / (cid + '.json')).exists()
        assert client.get(base('templates') + '/conversations').status_code == 404


def test_the_draft_is_edited_by_unique_matches_checked_and_proposed_once(tmp_path):
    results = {}

    async def steps(tools, _value, _cancel, _emit):
        first = await tools.call('read_draft', {'page': 0})
        pages = [first] + [await tools.call('read_draft', {'page': page}) for page in range(1, first['pages'])]
        results['draft'] = ''.join(page['text'] for page in pages)
        results['ambiguous'] = await tools.call('edit_draft', {'edits': [
            {'find': NAME, 'replace': '  name: Две колонки 2\n'}, {'find': '\n', 'replace': ' \n'}]})
        results['missing'] = await tools.call('edit_draft', {'edits': [{'find': 'no such text', 'replace': ''}]})
        results['unchanged'] = await tools.call('check_draft')
        results['broken'] = await tools.call('edit_draft', {'edits': [
            {'find': '  default_locale: ru\n', 'replace': '  default_locale: ru\n  colour: red\n'}]})
        results['refused'] = await tools.call('propose_draft', {'summary': 'Крупнее'})
        results['fixed'] = await tools.call('edit_draft', {'edits': [
            {'find': '  colour: red\n', 'replace': ''}, {'find': NAME, 'replace': '  name: Две колонки 2\n'},
            {'find': REVISION + '\n', 'replace': '  revision: 9.9.9\n'}]})
        results['proposed'] = await tools.call('propose_draft', {'summary': 'Имя изменено'})
        results['again'] = await tools.call('propose_draft', {'summary': 'Ещё раз'})
        results['too_many'] = await tools.call('edit_draft', {'edits': [{'find': 'a', 'replace': 'b'}] * 21})
        return 'Предложение готово.'
    with assistant_app(tmp_path) as (client, application, runtime):
        using(runtime, steps)
        cid = template_conversation(client)
        run, events = template_finish(client, template_start(client, cid, TEXT))
        assert run['state'] == 'completed'
        assert results['draft'] == TEXT
        assert results['ambiguous']['error']['code'] == 'AGENT_EDIT_INVALID'
        assert 'edit 1: find occurs' in results['ambiguous']['detail'][0] and 'No edit was applied' in results['ambiguous']['detail'][0]
        assert 'occurs 0 time(s)' in results['missing']['detail'][0]
        assert results['unchanged']['valid'] is True and results['unchanged']['template']['name'] == 'Две колонки'
        assert results['broken']['valid'] is False and results['broken']['error']['path'] == '/template/colour'
        assert results['refused']['error']['code'] == 'AGENT_EDIT_INVALID' and '/template/colour' in results['refused']['detail'][0]
        assert results['fixed']['valid'] is True and results['fixed']['template'] == {
            'id': GENERIC, 'revision': '9.9.9', 'name': 'Две колонки 2'}
        assert results['again']['error']['code'] == 'AGENT_EDIT_LIMIT'
        assert results['too_many']['error']['code'] == 'AGENT_EDIT_LIMIT'
        proposal_id = results['proposed']['proposalId']
        assert [event['payload'] for event in events if event['type'] == 'proposal.ready'] == [{'id': proposal_id}]
        listing = client.get(TBASE + '/proposals?conversationId=' + cid)
        assert listing.status_code == 200, listing.text[:300]
        [proposal] = listing.json()['items']
        assert set(proposal) == {'id', 'conversationId', 'runId', 'templateId', 'name', 'baseHash', 'text', 'summary', 'state'}
        assert (proposal['id'], proposal['runId'], proposal['templateId'], proposal['state']) == (
            proposal_id, run['id'], GENERIC, 'proposed')
        assert proposal['baseHash'] == hashlib.sha256(TEXT.encode()).hexdigest() and proposal['name'] is None
        assert proposal['text'] == TEXT.replace(NAME, '  name: Две колонки 2\n').replace(REVISION, '  revision: 9.9.9')
        assert client.get(TBASE + '/proposals/' + proposal_id).json() == proposal
        applied = client.post(TBASE + f'/proposals/{proposal_id}/state', json={'state': 'applied'})
        assert applied.status_code == 200 and applied.json()['state'] == 'applied'
        assert client.get(TBASE + '/proposals?conversationId=' + cid).json()['items'][0]['state'] == 'applied'
        assert client.post(TBASE + f'/proposals/{proposal_id}/state', json={'state': 'proposed'}).status_code == 422
        assert client.post(TBASE + '/proposals/proposal_missing/state', json={'state': 'discarded'}).status_code == 404
        # The draft went with the run; the proposal stays in its directory. The template store is untouched.
        directory = tmp_path / 'data/assistant-templates/templates/runs' / run['id']
        assert not (directory / 'draft.yaml').exists() and (directory / 'proposal.json').exists()
        assert not (tmp_path / 'data/template-packages').exists()
        assert client.get('/v1/rich/template-config/' + GENERIC).json()['edited'] is False


def test_a_new_template_draft_takes_its_name_and_reads_saved_templates_in_pages(tmp_path):
    results = {}

    async def steps(tools, _value, _cancel, _emit):
        results['list'] = await tools.call('list_templates')
        first = await tools.call('read_template', {'templateId': GENERIC, 'page': 0})
        results['pages'] = [first] + [await tools.call('read_template', {'templateId': GENERIC, 'page': page})
            for page in range(1, first['pages'])]
        results['unknown'] = await tools.call('read_template', {'templateId': 'missing'})
        results['beyond'] = await tools.call('read_draft', {'page': 99})
        results['sample'] = await tools.call('read_sample')
        results['skill'] = await tools.call('read_skill', {'name': 'import-resume'})
        results['web'] = await tools.call('read_public_page', {'url': 'https://example.com/'})
        await tools.call('edit_draft', {'edits': [{'find': NAME, 'replace': '  name: Новый\n'}]})
        results['proposed'] = await tools.call('propose_draft', {'summary': 'Новый шаблон'})
        return 'Готово.'
    with assistant_app(tmp_path) as (client, _application, runtime):
        using(runtime, steps)
        cid = template_conversation(client)
        run = template_start(client, cid, TEXT, template_id=None, assets_from=GENERIC)
        assert template_finish(client, run)[0]['state'] == 'completed'
        assert results['list']['defaultId'] == GENERIC and GENERIC in [item['id'] for item in results['list']['templates']]
        assert ''.join(page['text'] for page in results['pages']) == TEXT and len(results['pages']) >= 2
        assert all(len(json.dumps(page, ensure_ascii=False).encode()) <= 16 * 1024 for page in results['pages'])
        assert results['unknown']['error']['code'] == 'AGENT_NOT_FOUND'
        assert results['beyond']['error']['code'] == 'AGENT_SCOPE_INVALID'
        assert results['sample']['error']['code'] == 'AGENT_NOT_FOUND'
        # Resume skills and the page tool without internet are not tools of this run.
        assert 'sdkError' in results['skill'] and 'design-template' in results['skill']['sdkError']
        assert results['web']['error']['code'] == 'AGENT_ARGUMENT_INVALID'
        [proposal] = client.get(TBASE + '/proposals?conversationId=' + cid).json()['items']
        assert (proposal['templateId'], proposal['name']) == (None, 'Новый')


def test_a_run_request_is_checked_before_the_run_starts(tmp_path):
    with assistant_app(tmp_path) as (client, _application, runtime):
        using(runtime, lambda *_args: asyncio.sleep(0))
        cid = template_conversation(client)
        for changes, status in [({'textHash': '0' * 64}, 422), ({'allowEdits': True}, 422),
                ({'text': 'x' * (256 * 1024 + 1)}, 422), ({'selection': None}, 422)]:
            body = {**template_request(TEXT), **changes}
            if 'text' in changes:
                body['textHash'] = hashlib.sha256(changes['text'].encode()).hexdigest()
            assert client.post(TBASE + f'/conversations/{cid}/runs', json=body).status_code == status, changes
        assert template_start(client, cid, TEXT, sample_id='sample_gone', status=404)['error']['code'] == 'SAMPLE_NOT_FOUND'
        assert template_start(client, cid, TEXT, assets_from='missing', status=404)['error']['code'] == 'TEMPLATE_NOT_FOUND'
        assert template_start(client, cid, TEXT, template_id='missing', status=404)['error']['code'] == 'TEMPLATE_NOT_FOUND'
        messages = client.get(TBASE + f'/conversations/{cid}/messages').json()
        assert messages['runs'] == [] and messages['messages'] == []
        # The proposals list takes exactly one conversationId; any other query string stays refused.
        for query in ('', '?conversationId=' + cid + '&x=1', '?other=1', '?conversationId=a%20b'):
            assert client.get(TBASE + '/proposals' + query).status_code in {403, 422}, query
        assert client.get(base() + '/proposals?conversationId=' + cid).status_code == 403
        assert client.get(TBASE + '/proposals?conversationId=conversation_missing').status_code == 404


def test_a_resume_run_and_a_template_run_go_side_by_side(tmp_path):
    started, release = threading.Event(), threading.Event()

    async def steps(tools, value, cancel, _emit):
        if 'read_draft' in value.tools:
            started.set()
            while not release.is_set() and not cancel.is_set():
                await asyncio.sleep(0.01)
            await tools.call('check_draft')
        else:
            await tools.call('read_resume', {'page': 0})
        return 'Готово.'
    with assistant_app(tmp_path) as (client, application, runtime):
        using(runtime, steps)
        cid = template_conversation(client)
        template_run = template_start(client, cid, TEXT)
        wait(started)
        assert template_start(client, template_conversation(client), TEXT, request_id='second',
            status=409)['error']['code'] == 'ASSISTANT_RUN_ACTIVE'
        resume_run, _events = finish(client, start(client, conversation(client)))
        assert resume_run['state'] == 'completed'
        assert client.get(TBASE + f"/runs/{template_run['id']}/events/0").json()['run']['state'] == 'running'
        release.set()
        assert template_finish(client, template_run)[0]['state'] == 'completed'
        assert application.state.template_assistant.controls == {}


def test_turning_the_assistant_off_and_a_connection_stop_cancel_a_template_run(tmp_path):
    started, release = threading.Event(), threading.Event()

    async def steps(_tools, _value, cancel, _emit):
        started.set()
        while not release.is_set() and not cancel.is_set():
            await asyncio.sleep(0.01)
        return 'Ответ.'
    with assistant_app(tmp_path) as (client, application, runtime):
        using(runtime, steps)
        run = template_start(client, template_conversation(client), TEXT)
        wait(started)
        settings(client, enabled=False)
        assert template_finish(client, run)[0]['state'] == 'cancelled'
        settings(client, enabled=True)
        started.clear()
        run = template_start(client, template_conversation(client), TEXT, request_id='second')
        wait(started)
        application.state.template_assistant.stop_all()
        assert template_finish(client, run)[0]['state'] == 'cancelled'


def test_the_template_skill_is_registered_for_the_template_scope_only():
    [skill] = TEMPLATE_SKILLS
    assert (skill.id, skill.title) == ('design-template', 'Шаблон по образцу')
    assert {key: path.name for key, path in skill.resources.items()} == {
        'SKILL.md': 'design-template.md', 'references/template-authoring.md': 'template-authoring.md'}
    assert 'design-template' not in [item['id'] for item in skill_catalog()]
    assert [item['id'] for item in skill_catalog(TEMPLATE_SKILLS)] == ['design-template']
    assert not {value.id for value in SKILLS} & {value.id for value in TEMPLATE_SKILLS}
    assert '/design-template' in TEMPLATE_DEVELOPER_INSTRUCTIONS and '/import-resume' not in TEMPLATE_DEVELOPER_INSTRUCTIONS
    assert 'durable save' not in TEMPLATE_DEVELOPER_INSTRUCTIONS


def test_a_public_page_is_read_with_internet_and_cited_in_the_templates_conversation(tmp_path):
    from tests.assistant.test_permissions import Fetcher
    results = []

    async def steps(tools, _value, _cancel, _emit):
        results.append(await tools.call('read_public_page', {'url': 'https://example.test/style'}))
        return 'Готово.'
    with assistant_app(tmp_path) as (client, application, runtime):
        using(runtime, steps)
        fetcher = application.state.template_assistant._fetcher = Fetcher()
        cid = template_conversation(client)
        assert template_finish(client, template_start(client, cid, TEXT, web=True))[0]['state'] == 'completed'
        assert results[0]['source']['id'] == 'source_page' and fetcher.urls == ['https://example.test/style']
        messages = client.get(TBASE + f'/conversations/{cid}/messages').json()
        assert [source['id'] for source in messages['sources']] == ['source_page']
        assert messages['messages'][-1]['sources'][0]['label'] == 'Вакансия'
