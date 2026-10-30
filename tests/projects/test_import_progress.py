"""Import progress in the task detail: steps, model activity, the stall bounds, the chosen effort and imports of
several projects at once (feedback items 12, 20, 22 and 23)."""

import asyncio
from datetime import datetime, timedelta, timezone
import threading
from types import SimpleNamespace

import pytest

from packages.resume_core.reasoning import ModelReasoning
from resume_api.connection import Metadata, Quota
from resume_api.projects.import_progress import import_progress, quiet_limit
from tests.templates.scripted_template_provider import ScriptedTemplateProvider
from tests.templates.test_template_import_app import CatalogAdapter, app_client, operation_of, upload

T0 = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
POLICY = SimpleNamespace(processing_seconds=3600, cleanup_seconds=5, finalization_seconds=158)


def at(seconds):
    return (T0 + timedelta(seconds=seconds)).isoformat()


def operation(*attempts, results=(), state='processing'):
    tasks = [SimpleNamespace(id='task-' + name, block_id=name) for name in ('identity', 'projects', 'project-window')]
    return SimpleNamespace(state=state, capture=SimpleNamespace(policy=POLICY), tasks=tasks, attempts=list(attempts),
        receipts=[], task_inputs=[SimpleNamespace(task_id=task.id, captured_at=at(0)) for task in tasks[:2]],
        cleanup_records=[], authorizations=[], last_observed_at=None, finalization=None,
        task_results=[SimpleNamespace(task_id=value) for value in results])


def attempt(task, slot, dispatched, returned=None, outcome=None):
    return SimpleNamespace(task_id=task, slot=slot, reserved_at=at(dispatched), dispatched_at=at(dispatched),
        returned_at=None if returned is None else at(returned), outcome=outcome,
        state='dispatch_started' if returned is None else 'returned')


PACKAGE = SimpleNamespace(definition=SimpleNamespace(template=SimpleNamespace(default_locale='ru'),
    blocks=[SimpleNamespace(id='identity', view=SimpleNamespace(title={})),
        SimpleNamespace(id='projects', view=SimpleNamespace(title={'ru': 'ПРОЕКТЫ', 'en': 'PROJECTS'}))],
    operations=[SimpleNamespace(id='project-window', kind='partition_employment')]))


def progress(value, seconds, **times):
    return import_progress(value, PACKAGE, stage=times.pop('stage', 'processing'), now=T0 + timedelta(seconds=seconds),
        started_at=at(0), **times)


def test_quiet_bounds_cover_the_longest_call_and_the_captured_time_limits():
    # D114: a call has no limit of its own, so one may stay silent for the whole 3600 s import limit; cleanup 5 s and
    # 60 s grace follow.
    assert quiet_limit('processing', POLICY) == 3600 + 5 + 60
    assert quiet_limit('publication', POLICY) == 158 + 60
    # A whole import under its captured limits may run ahead of a queued one.
    assert quiet_limit('queued', POLICY) == 3600 + 5 + 158 + 60
    assert quiet_limit('starting', POLICY) == quiet_limit('processing', None) == 120


def test_steps_and_activity_come_from_the_operation_records():
    value = operation(attempt('task-identity', 'initial', 10, 30, 'completed'), attempt('task-identity', 'review', 31, 40, 'completed'),
        attempt('task-projects', 'initial', 41), results=['task-identity'])
    found = progress(value, 50, admitted_at=at(5))
    assert (found['phase'], found['done'], found['total'], found['current']) == ('processing', 1, 3, ['ПРОЕКТЫ'])
    assert [event['text'] for event in found['events']] == ['Извлекаем данные: «ПРОЕКТЫ»',
        'Ответ получен: «Шапка»', 'Проверяем результат: «Шапка»', 'Ответ получен: «Шапка»',
        'Извлекаем данные: «Шапка»']
    assert found['lastModelAt'] == found['lastEventAt'] == at(41)
    assert (found['quietSeconds'], found['stalled']) == (9.0, False)


def test_entry_steps_carry_the_entry_title_and_the_outline_calls_have_their_own_lines():
    # D117: a block extracted entry by entry adds steps while it runs; each shows the block and the entry.
    value = operation(attempt('task-projects', 'outline', 10, 20, 'completed'), attempt('task-outline-review', 'outline_review', 21),
        attempt('task-entry-2', 'initial', 22))
    value.tasks += [SimpleNamespace(id='task-outline-review', block_id='projects', entry=None),
        SimpleNamespace(id='task-entry-1', block_id='projects', entry=SimpleNamespace(title='Example Labs')),
        SimpleNamespace(id='task-entry-2', block_id='projects', entry=SimpleNamespace(title='Old Systems'))]
    value.task_inputs.append(SimpleNamespace(task_id='task-entry-1', captured_at=at(21)))
    found = progress(value, 30, admitted_at=at(5))
    assert (found['done'], found['total'], found['current']) == (0, 6, ['Шапка', 'ПРОЕКТЫ', 'ПРОЕКТЫ: Example Labs', 'ПРОЕКТЫ: Old Systems'])
    assert [event['text'] for event in found['events']][:3] == ['Извлекаем данные: «ПРОЕКТЫ: Old Systems»',
        'Проверяем разметку записей: «ПРОЕКТЫ»', 'Ответ получен: «ПРОЕКТЫ»']


def test_an_import_is_stalled_after_a_silence_longer_than_its_time_limit_or_past_its_whole_time_limit():
    # D114: a call has no limit of its own, so the silence bound is the import limit with cleanup and grace.
    value = operation(attempt('task-projects', 'initial', 100))
    assert progress(value, 100 + 3665, admitted_at=at(5))['stalled'] is False
    late = progress(value, 100 + 3666, admitted_at=at(5))
    assert (late['quietSeconds'], late['quietLimitSeconds'], late['stalled']) == (3666.0, 3665, True)
    # Events keep arriving, but the run is past processing, cleanup, publication and the grace.
    busy = operation(attempt('task-projects', 'initial', 3800))
    assert progress(busy, 3810, admitted_at=at(5))['stalled'] is False
    assert progress(busy, 3830, admitted_at=at(5))['stalled'] is True


def test_a_queued_import_is_quiet_from_the_last_queue_movement_and_ignores_old_records():
    value = operation(attempt('task-projects', 'initial', -86400, -86390, 'timed_out'))
    queued = progress(value, 3000, stage='queued', queued_at=at(0), queue_moved_at=at(2000))
    assert (queued['phase'], queued['quietSeconds'], queued['stalled']) == ('queued', 1000.0, False)
    assert progress(value, 2000 + 3824, stage='queued', queued_at=at(0), queue_moved_at=at(2000))['stalled'] is True


class GatedAdapter(CatalogAdapter):
    """The processing model offers three efforts with medium as the default."""

    def inspect(self, _files, _cancel, *, full=True):
        return Metadata('fixture', ('assistant-model', 'processing-model'), 'plus', Quota('available', 10),
            {name: ModelReasoning(supported=['low', 'medium', 'high'], default='medium') for name in ('assistant-model', 'processing-model')})


class GatedProvider(ScriptedTemplateProvider):
    """Holds every call until the test opens the gate, and records the effort each call ran with."""

    def __init__(self):
        super().__init__()
        self.entered, self.gate, self.efforts = threading.Event(), threading.Event(), []

    def generate(self, request, files, cancel):
        self.efforts.append(request.policy.reasoning_effort)
        self.entered.set()
        assert self.gate.wait(10)
        return super().generate(request, files, cancel)


async def until(condition):
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError('condition not reached')


async def start(client, project, request_id, **body):
    return await client.post('/v2/projects/' + project + '/import', json={'kind': 'start', 'clientRequestId': request_id,
        'allowTextRewrite': True, **body})


async def task_of(client, project, identifier):
    tasks = (await client.get('/v2/projects/' + project + '/tasks')).json()['tasks']
    return next(value for value in tasks if value['id'] == identifier)


@pytest.mark.asyncio
async def test_a_second_project_imports_beside_the_first_and_both_finish(tmp_path):
    provider = GatedProvider()
    async with app_client(tmp_path, call_cap=4, provider=provider, adapter=GatedAdapter()) as (client, app):
        first = (await upload(client)).json()['workspace']['projectId']
        second = (await upload(client, 'F02')).json()['workspace']['projectId']
        running = await start(client, first, 'import-a')
        assert running.status_code == 202 and running.json()['stage'] == 'processing'
        await until(provider.entered.is_set)
        held = (await task_of(client, first, running.json()['id']))['detail']['progress']
        assert (held['phase'], held['done'], held['total'], held['current']) == ('processing', 0, 1, ['PROJECTS'])
        assert held['events'][0]['text'] == 'Извлекаем данные: «PROJECTS»' and held['stalled'] is False
        assert held['lastModelAt'] is not None
        # D121: the second import does not queue behind the first; both model calls run at once.
        beside = await start(client, second, 'import-b')
        assert beside.status_code == 202 and beside.json()['stage'] == 'processing', beside.text
        await until(lambda: len(provider.efforts) == 2)
        assert (await task_of(client, second, beside.json()['id']))['detail']['progress']['phase'] == 'processing'
        # One import per project: a second start on the running project is refused.
        again = await start(client, first, 'import-a2')
        assert again.status_code == 409 and again.json()['error']['code'] == 'REQUEST_IN_PROGRESS'
        provider.gate.set()
        for project, reply in ((first, running), (second, beside)):
            runner = app.state.projects.imports.runners.get(reply.json()['id'])
            if runner is not None:
                await runner
            assert (await task_of(client, project, reply.json()['id']))['state'] == 'succeeded'
        assert len(provider.calls) == 4


@pytest.mark.asyncio
async def test_the_start_effort_reaches_the_capture_and_an_unoffered_one_refuses_the_start(tmp_path):
    provider = GatedProvider()
    provider.gate.set()
    async with app_client(tmp_path, call_cap=4, provider=provider, adapter=GatedAdapter()) as (client, app):
        intake = app.state.intake
        assert intake.model().effort == 'medium' and intake.model(effort='high').effort == 'high'
        project = (await upload(client)).json()['workspace']['projectId']
        refused = await start(client, project, 'import-x', effort='xhigh')
        assert refused.status_code == 202
        runner = app.state.projects.imports.runners.get(refused.json()['id'])
        if runner is not None:
            await runner
        failed = await task_of(client, project, refused.json()['id'])
        assert (failed['state'], failed['error']) == ('failed', 'IMPORT_EFFORT_UNSUPPORTED') and provider.calls == []
        assert (await start(client, project, 'import-y', effort='turbo')).status_code == 422
        chosen = await start(client, project, 'import-h', effort='high')
        runner = app.state.projects.imports.runners.get(chosen.json()['id'])
        if runner is not None:
            await runner
        assert (await task_of(client, project, chosen.json()['id']))['state'] == 'succeeded'
        capture = operation_of(app, project).capture
        # D116: the review runs at low, which this catalog offers; the proposal keeps the chosen high.
        assert capture.primary.effort == 'high' and capture.review.effort == 'low' and provider.efforts == ['high', 'low']
