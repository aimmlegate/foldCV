"""E07: the fallback model preference is captured with each import, used for at most one repair and never replaced."""

import asyncio
import json

import pytest

from resume_api.providers.content import ContentFailure, ReportedUsage

from packages.resume_core.preferences import PreferencesFailure, PreferencesStore
from tests.templates.scripted_template_provider import ScriptedTemplateProvider, scripted_template_answer, scripted_template_result
from tests.templates.test_template_import_app import app_client, upload


class ModelRecorder(ScriptedTemplateProvider):
    """Answers as the scripted provider and records the model of every call; refuse(value) may replace an answer."""

    def __init__(self, refuse=None, during=None):
        super().__init__()
        self.models, self.refuse, self.during = [], refuse, during

    def generate(self, request, _files, _cancel):
        self.models.append(request.policy.model)
        if self.during is not None:
            self.during(len(self.models))
        def answer(value):
            refused = self.refuse(value, request.policy.model) if self.refuse else None
            return refused if refused is not None else scripted_template_answer(value)
        try:
            return scripted_template_result(self, request, answer)
        except ValueError:
            # As the CLI provider does: a reply its schema refuses comes back with its raw text.
            value = request.request_value
            raise ContentFailure('INVALID_RESULT', logical_attempts=1, usage=ReportedUsage(10, 0, 4, True),
                cleanup_verified=True, dispatch_witness={'transport': 'scripted'},
                raw_return=json.dumps({'payload': answer(value)})) from None


async def run_import(client, project, request_id):
    started = await client.post(f'/v1/rich/projects/{project}/template-import',
        json={'clientRequestId': request_id, 'allowTextRewrite': True})
    assert started.status_code == 202, started.text
    job = started.json()
    async def finished():
        while True:
            current = (await client.post(f'/v1/rich/projects/{project}/jobs/{job["id"]}/read', json={})).json()
            if current.get('templateOutcome') is not None:
                return current
            await asyncio.sleep(0.05)
    return job, await asyncio.wait_for(finished(), 60)


def test_the_fallback_preference_saves_clears_and_keeps_other_choices(tmp_path):
    store = PreferencesStore(tmp_path / 'store')
    store.select_import_model('model-a')
    assert store.load().selected_fallback_model is None
    store.select_fallback_model('model-b')
    saved = PreferencesStore(store.root).load()
    assert (saved.selected_import_model, saved.selected_fallback_model) == ('model-a', 'model-b')
    store.select_fallback_model(None)
    assert PreferencesStore(store.root).load().selected_fallback_model is None
    with pytest.raises(PreferencesFailure, match='MODEL_DENIED'):
        store.select_fallback_model('invalid/model')


@pytest.mark.asyncio
async def test_an_import_captures_the_fallback_and_settings_changes_reach_only_later_imports(tmp_path):
    # Null disables fallback; the fallback never replaces the primary, and editing models stay as they are.
    provider = ModelRecorder()
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, service, _jobs):
        path = '/v1/settings/fallback-model'
        assert (await client.put(path, json={'model': 'unlisted'})).status_code == 409
        saved = await client.put(path, json={'model': 'assistant-model'})
        assert saved.status_code == 200, saved.text
        assert saved.json()['selectedFallbackModel'] == 'assistant-model'
        assert saved.json()['selectedModel'] == 'processing-model' and saved.json().get('selectedImportModel') is None
        project = (await upload(client)).json()['workspace']['projectId']
        job, done = await run_import(client, project, 'first')
        capture = job['submission']['templateCommand']['capture']
        assert capture['primary']['model'] == 'processing-model' and capture['fallback']['model'] == 'assistant-model'
        assert done['templateOutcome']['state'] == 'saved' and set(provider.models) == {'processing-model'}
        assert (await client.put(path, json={'model': None})).status_code == 200
        second = (await upload(client)).json()['workspace']['projectId']
        job, _done = await run_import(client, second, 'second')
        assert job['submission']['templateCommand']['capture']['fallback'] is None
        # A fallback equal to the import model adds nothing.
        assert (await client.put(path, json={'model': 'assistant-model'})).status_code == 200
        assert (await client.put('/v1/settings/import-model', json={'model': 'assistant-model'})).status_code == 200
        third = (await upload(client)).json()['workspace']['projectId']
        job, _done = await run_import(client, third, 'third')
        capture = job['submission']['templateCommand']['capture']
        assert capture['primary']['model'] == 'assistant-model' and capture['fallback'] is None
        assert (await client.get('/v1/settings/connection')).json()['selectedModel'] == 'processing-model'


@pytest.mark.asyncio
async def test_a_running_import_keeps_its_captured_models_when_settings_change(tmp_path):
    # The import model changes in Settings after the first call; the import still runs and publishes on its own.
    def during(count):
        if count == 1:
            PreferencesStore(tmp_path / 'data').select_import_model('processing-model')
    provider = ModelRecorder(during=during)
    async with app_client(tmp_path, call_cap=4, provider=provider) as (client, _service, _jobs):
        assert (await client.put('/v1/settings/import-model', json={'model': 'assistant-model'})).status_code == 200
        project = (await upload(client)).json()['workspace']['projectId']
        _job, done = await run_import(client, project, 'running')
        assert done['templateOutcome']['state'] == 'saved', done
        assert provider.models == ['assistant-model', 'assistant-model']
        assert (await client.get('/v1/settings/preferences')).json()['selectedImportModel'] == 'processing-model'


@pytest.mark.asyncio
@pytest.mark.parametrize('available', [True, False])
async def test_the_fallback_model_makes_the_last_repair_and_is_never_replaced_when_unavailable(tmp_path, available):
    # The selected model's first reply and repair are refused; the captured fallback makes one more repair, reviewed by
    # the model that wrote it, as every review is. When it
    # left the catalog, the attempt is refused before any process and the block keeps its source wording.
    def refuse(value, model):
        if 'targets' in value or model == 'assistant-model':
            return None
        return {'unexpected': True}
    provider = ModelRecorder(refuse=refuse)
    async with app_client(tmp_path, call_cap=8, provider=provider) as (client, service, jobs):
        assert (await client.put('/v1/settings/fallback-model', json={'model': 'assistant-model'})).status_code == 200
        if not available:
            # The fallback leaves the catalog after the import captured it.
            from resume_api.gui_projects import ProjectFailure
            transport = jobs.templates.pipeline.transport
            offered = transport.model_provider
            def leaving(model):
                if model == 'assistant-model':
                    raise ProjectFailure('MODEL_DENIED', 409)
                return offered(model)
            transport.model_provider = leaving
        project = (await upload(client)).json()['workspace']['projectId']
        _job, done = await run_import(client, project, 'fallback')
        assert done['templateOutcome']['state'] == 'saved', done
        operation = service.storage.load_history(service.read(project)).project.template_operations[0]
        slots = [(attempt.slot, attempt.model.model) for attempt in operation.attempts]
        if available:
            assert slots == [('initial', 'processing-model'), ('primary_repair', 'processing-model'),
                ('fallback_repair', 'assistant-model'), ('replacement_review', 'assistant-model')]
            assert operation.tasks[0].state == 'accepted'
        else:
            assert provider.models == ['processing-model', 'processing-model']
            assert slots[-1] == ('fallback_repair', 'assistant-model') and operation.attempts[-1].error_code == 'MODEL_DENIED'
            assert operation.tasks[0].state == 'source_fallback'
