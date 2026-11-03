"""The template assistant in the test app: its routes, a request with the editor text, and its MCP tools in process."""

import hashlib
import json
import time

import httpx

from resume_api.agent.runtime import RuntimeResult
from tests.assistant.support import Tools

TBASE = '/v2/templates/assistant'


class TemplateTools(Tools):
    def session(self):
        return next(control.tools for control in self.application.state.template_assistant.controls.values()
            if control.tools is not None and control.tools.token == self.value.token)

    async def call(self, name, arguments=None):
        """The tool's JSON reply; an argument the SDK itself refuses comes back as {'sdkError': text}."""
        try:
            return await super().call(name, arguments)
        except json.JSONDecodeError as error:
            return {'sdkError': error.doc}

    async def listed(self):
        """The tool names the run's MCP listener offers."""
        session = self.session()
        headers = {'Authorization': 'Bearer ' + self.value.token, 'Accept': 'application/json, text/event-stream'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url='http://' + session.host,
                headers=headers, timeout=10) as client:
            await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'fixture', 'version': '1'}}})
            reply = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
        return sorted(tool['name'] for tool in reply.json()['result']['tools'])


def scripted(steps, runtime):
    """A script for both assistants: `steps(tools, value, cancel, emit)`; a template run gets template tools."""
    async def script(value, cancel, emit):
        kind = TemplateTools if 'read_draft' in value.tools else Tools
        text = await steps(kind(value, runtime.application), value, cancel, emit)
        return RuntimeResult(state='cancelled' if cancel.is_set() else 'completed', text=text or 'Готово.',
            native_started=True, tool_calls=1)
    return script


def using(runtime, steps):
    runtime.script = scripted(steps, runtime)


def template_conversation(client):
    reply = client.post(TBASE + '/conversations', json={})
    assert reply.status_code == 201, reply.text[:300]
    return reply.json()['id']


def template_request(text, message='Сделай имя крупнее', *, request_id='template-1', template_id='generic-two-column',
        assets_from='generic-two-column', sample_id=None, web=False, **changes):
    return {'clientRequestId': request_id, 'message': message, 'allowEdits': False, 'allowWeb': web,
        'templateId': template_id, 'assetsFrom': assets_from, 'text': text,
        'textHash': hashlib.sha256(text.encode()).hexdigest(), 'sampleId': sample_id, **changes}


def template_start(client, conversation_id, text, *, status=201, **options):
    reply = client.post(TBASE + f'/conversations/{conversation_id}/runs', json=template_request(text, **options))
    assert reply.status_code == status, reply.text[:400]
    return reply.json()


def template_finish(client, run, deadline=10.0):
    """Long-poll the template run until it ends; returns (run, events)."""
    events, after, ends = [], 0, time.monotonic() + deadline
    while time.monotonic() < ends:
        reply = client.get(TBASE + f"/runs/{run['id']}/events/{after}")
        assert reply.status_code == 200, reply.text[:300]
        body = reply.json()
        events += body['events']
        after = body['next']
        if body['run']['state'] in {'completed', 'failed', 'cancelled', 'interrupted'} and not body['events']:
            return body['run'], events
    raise AssertionError('run did not finish')


def upload_sample(client, data, name='sample.docx'):
    return client.post(TBASE + '/samples', files={'file': (name, data, 'application/octet-stream')})
