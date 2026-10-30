"""Run lifecycle hooks of the assistant service (assistant/runs): the model is captured at submit, and turning the
assistant off or deleting the project stops a running run."""

import asyncio
import threading
import time

from packages.resume_core.models.template_render import TemplateRendererIdentity
from packages.resume_core.reasoning import ModelReasoning
from resume_api.connection import Metadata, Quota
from tests.assistant.support import MODEL, PROJECT, MetadataAdapter, assistant_app, base, conversation, finish, start


def blocking(started, release, models):
    async def steps(_tools, value, cancel, _emit):
        models.append(value.model)
        started.set()
        while not release.is_set() and not cancel.is_set():
            await asyncio.sleep(0.01)
        return 'Ответ.'
    return steps


def wait(event):
    deadline = time.monotonic() + 5
    while not event.is_set():
        assert time.monotonic() < deadline, 'the run did not start'
        event.wait(0.01)


def settings(client, **values):
    current = client.get('/v1/settings/assistant').json()
    reply = client.put('/v1/settings/assistant', json={'expectedRevision': current['revision'], 'enabled': current['enabled'],
        'selectedAgentModel': current['selectedAgentModel'], **values})
    assert reply.status_code == 200, reply.text[:300]
    return reply.json()


def test_a_model_change_during_a_run_keeps_the_captured_model_and_reaches_only_the_next_run(tmp_path):
    started, release, models = threading.Event(), threading.Event(), []
    with assistant_app(tmp_path, blocking(started, release, models)) as (client, _application, _runtime):
        cid = conversation(client)
        run = start(client, cid)
        wait(started)
        settings(client, selectedAgentModel='processing-model')
        release.set()
        run, _events = finish(client, run)
        assert run['state'] == 'completed' and run['model'] == MODEL and models == [MODEL]
        started.clear()
        later, _events = finish(client, start(client, cid, request_id='request-2'))
        assert later['model'] == 'processing-model' and models == [MODEL, 'processing-model']


def test_turning_the_assistant_off_cancels_the_running_run(tmp_path):
    started, release, models = threading.Event(), threading.Event(), []
    with assistant_app(tmp_path, blocking(started, release, models)) as (client, _application, _runtime):
        run = start(client, conversation(client))
        wait(started)
        settings(client, enabled=False)
        run, _events = finish(client, run)
        assert run['state'] == 'cancelled' and not release.is_set()


def test_deleting_the_project_stops_its_run_and_the_ending_run_writes_no_assistant_files(tmp_path):
    started, release, models = threading.Event(), threading.Event(), []
    with assistant_app(tmp_path, blocking(started, release, models)) as (client, application, _runtime):
        run = start(client, conversation(client))
        wait(started)
        store = application.state.assistant.store
        # Taken before the delete: a run that ended drops its control.
        control = application.state.assistant.controls[run['id']]
        deleted = client.request('DELETE', '/v2/projects/' + PROJECT, json={'confirmed': True})
        assert deleted.status_code == 200, deleted.text[:300]
        deadline = time.monotonic() + 5
        while control.task is not None and not control.task.done():
            assert time.monotonic() < deadline, 'the run did not stop'
            time.sleep(0.01)
        assert control.cancel.is_set() and control.deleted
        assert client.get(base() + '/conversations').status_code == 404
        assert not store.directory(PROJECT).exists()


class ReasoningAdapter(MetadataAdapter):
    def inspect(self, _files, _cancel, *, full=True):
        reasoning = {MODEL: ModelReasoning(supported=['low', 'medium', 'high'], default='medium'),
                     'processing-model': ModelReasoning(supported=['medium'], default='medium')}
        return Metadata('fixture', (MODEL, 'processing-model'), 'plus', Quota('available', 10), reasoning)


def test_the_chosen_assistant_effort_reaches_the_run_and_null_runs_the_catalog_default(tmp_path):
    efforts = []

    async def steps(_tools, value, _cancel, _emit):
        efforts.append(value.reasoning_effort)
        return 'Ответ.'
    with assistant_app(tmp_path, steps, adapter=ReasoningAdapter()) as (client, _application, _runtime):
        cid = conversation(client)
        assert client.get('/v1/settings/assistant').json()['reasoningEffort'] is None
        finish(client, start(client, cid))
        assert settings(client, reasoningEffort='high')['reasoningEffort'] == 'high'
        finish(client, start(client, cid, request_id='request-2'))
        assert efforts == ['medium', 'high']
        current = client.get('/v1/settings/assistant').json()
        refused = client.put('/v1/settings/assistant', json={'expectedRevision': current['revision'], 'enabled': True,
            'selectedAgentModel': 'processing-model', 'reasoningEffort': 'high'})
        assert refused.status_code == 409 and refused.json()['error']['code'] == 'AGENT_MODEL_INCOMPATIBLE'
        assert client.get('/v1/settings/assistant').json() == current


def test_deleting_the_project_drops_its_export_links(tmp_path):
    links = []

    async def render(_request):
        return b'PK\x03\x04synthetic-assistant-export'

    async def steps(tools, _value, _cancel, _emit):
        links.append(await tools.call('export_document', {'format': 'docx'}))
        return 'Файл готов.'
    with assistant_app(tmp_path, steps) as (client, application, _runtime):
        exports = application.state.projects.exports
        exports._renderer = TemplateRendererIdentity(id='captured-docx', version='test', sha256='a' * 64)
        exports.render = render
        finish(client, start(client, conversation(client)))
        assert client.get(links[0]['url']).status_code == 200
        deleted = client.request('DELETE', '/v2/projects/' + PROJECT, json={'confirmed': True})
        assert deleted.status_code == 200, deleted.text[:300]
        assert client.get(links[0]['url']).status_code == 404 and not application.state.assistant.files
