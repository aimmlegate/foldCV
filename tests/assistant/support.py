"""An app with the assistant enabled, a scripted runtime that calls the real MCP tools, and small route helpers."""

from contextlib import contextmanager
import json
import time

import httpx

from resume_api.agent.runtime import RuntimeResult, ScriptedAgentRuntime
from resume_api.connection import Metadata, Quota
from tests.projects.support import Editor, v2_app
from tests.templates.storage_fixtures import workspace as papers

PROJECT = 'template-project'
MODEL = 'assistant-model'


class MetadataAdapter:
    def inspect(self, _files, _cancel, *, full=True):
        return Metadata('fixture', (MODEL, 'processing-model'), 'plus', Quota('available', 10))


class Tools:
    """The run's MCP tools called in process (tests open no sockets), as the app-server would call them."""

    def __init__(self, value, application):
        self.value, self.application, self.sequence = value, application, 0

    def session(self):
        return next(control.tools for control in self.application.state.assistant.controls.values()
            if control.tools is not None and control.tools.token == self.value.token)

    async def call(self, name, arguments=None):
        self.sequence += 1
        session = self.session()
        headers = {'Authorization': 'Bearer ' + self.value.token, 'Accept': 'application/json, text/event-stream'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url='http://' + session.host,
                headers=headers, timeout=10) as client:
            if self.sequence == 1:
                await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'fixture', 'version': '1'}}})
            reply = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': self.sequence, 'method': 'tools/call',
                'params': {'name': name, 'arguments': arguments or {}}})
        assert reply.status_code == 200 and reply.content, (reply.status_code, reply.text[:300])
        result = reply.json()['result']
        return json.loads(result['content'][0]['text']) if result.get('content') else {}


def scripted(steps, runtime):
    """A runtime script: `steps(tools, value, cancel, emit)` returns the final text."""
    async def script(value, cancel, emit):
        text = await steps(Tools(value, runtime.application), value, cancel, emit)
        return RuntimeResult(state='cancelled' if cancel.is_set() else 'completed', text=text or 'Готово.',
            native_started=True, tool_calls=1)
    return script


@contextmanager
def assistant_app(tmp_path, steps=None, projects=None, *, enabled=True):
    runtime = ScriptedAgentRuntime(None)
    if steps:
        runtime.script = scripted(steps, runtime)
    with v2_app(tmp_path, projects if projects is not None else [papers()], connection_adapter=MetadataAdapter(),
            agent_runtime=runtime) as (client, application):
        application.state.assistant.wait_seconds = 1.0
        runtime.application = application
        assert client.post('/v1/host/status', json={}).status_code == 200
        if enabled:
            reply = client.put('/v1/settings/assistant', json={'expectedRevision': 1, 'enabled': True, 'selectedAgentModel': MODEL})
            assert reply.status_code == 200, reply.text[:300]
        yield client, application, runtime


def base(project=PROJECT):
    return '/v2/projects/' + project + '/assistant'


def conversation(client, project=PROJECT):
    reply = client.post(base(project) + '/conversations', json={})
    assert reply.status_code == 201, reply.text[:300]
    return reply.json()['id']


def start(client, conversation_id, message='Проверь резюме', *, edits=True, web=False, request_id='request-1', project=PROJECT,
        status=201):
    reply = client.post(base(project) + f'/conversations/{conversation_id}/runs', json={'clientRequestId': request_id,
        'message': message, 'allowEdits': edits, 'allowWeb': web})
    assert reply.status_code == status, reply.text[:400]
    return reply.json()


def finish(client, run, project=PROJECT, deadline=10.0, after=0):
    """Long-poll the run's events after `after` until it ends; returns (run, events)."""
    events, ends = [], time.monotonic() + deadline
    while time.monotonic() < ends:
        reply = client.get(base(project) + f"/runs/{run['id']}/events/{after}")
        assert reply.status_code == 200, reply.text[:300]
        body = reply.json()
        events += body['events']
        after = body['next']
        if body['run']['state'] in {'completed', 'failed', 'cancelled', 'interrupted'} and not body['events']:
            return body['run'], events
    raise AssertionError('run did not finish')


def proposals(client, project=PROJECT):
    reply = client.get(base(project) + '/proposals')
    assert reply.status_code == 200, reply.text[:300]
    return reply.json()['items']


def apply(client, editor, proposal_id, *, edits=True, mutation='apply-1', status=200, project=PROJECT):
    reply = client.post(base(project) + f'/proposals/{proposal_id}/apply', json={'editorToken': editor.token,
        'clientMutationId': mutation, 'allowEdits': edits})
    assert reply.status_code == status, reply.text[:400]
    body = reply.json()
    if status == 200 and body.get('edit'):
        editor.adopt(body['edit'])
    return body


__all__ = ['Editor', 'PROJECT', 'assistant_app', 'base', 'conversation', 'start', 'finish', 'proposals', 'apply', 'papers']


def using(runtime, steps):
    """The next runs use `steps`; the runtime stays the one the app holds."""
    runtime.script = scripted(steps, runtime)


def manual_edit(editor, *, index=0, text='Human', start=0, end=6, mutation='manual-1'):
    """A typing edit of one main-region block, as the editor page sends it."""
    block = editor.workspace().project.document.regions[2].blocks[index]
    return editor.edit({'schemaVersion': 1, 'clientMutationId': mutation, 'snapshot': editor.response['snapshot'],
        'capture': {'sessionId': 'session', 'actionId': mutation, 'actionToken': 1, 'dependencies': []},
        'operations': [{'kind': 'replace_text', 'opId': 'text', 'range': {'blockId': block.id, 'beforeRevision': block.revision,
            'cellId': None, 'field': 'content', 'start': start, 'end': end}, 'text': text, 'styles': {}}]})


def proposing(*ops, summary='Правка'):
    """Steps that read the resume once and store one proposal with `ops`."""
    async def steps(tools, _value, _cancel, _emit):
        await tools.call('read_resume', {'page': 0})
        result = await tools.call('propose_changes', {'request': {'summary': summary, 'ops': list(ops)}})
        assert 'proposalId' in result, result
        return 'Предложение готово.'
    return steps


def run_once(client, steps, runtime, *, edits=True, web=False, message='Проверь резюме', request_id='request-1'):
    using(runtime, steps)
    run, events = finish(client, start(client, conversation(client), message, edits=edits, web=web, request_id=request_id))
    return run, events
