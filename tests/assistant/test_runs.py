"""Runs: ordered events, Stop, one run per project, the last messages in the next prompt, restart outcomes."""

import asyncio
import threading
import time

from tests.assistant.support import (assistant_app, base, conversation, finish, start, using)
from tests.projects.support import v2_app


def blocking(started, release):
    """Steps that wait for the test (or a cancel) before they answer; time comes from the events, not sleeps."""
    async def steps(_tools, _value, cancel, emit):
        emit('activity.updated', {'itemId': 'step_1', 'kind': 'summary', 'text': 'Читаю резюме'})
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


def test_events_arrive_in_order_and_the_answer_is_kept(tmp_path):
    async def steps(_tools, _value, _cancel, emit):
        emit('activity.updated', {'itemId': 'step_1', 'kind': 'summary', 'text': 'Читаю резюме'})
        emit('message.delta', {'text': 'Отв'})
        emit('message.delta', {'text': 'ет.'})
        return 'Ответ.'
    with assistant_app(tmp_path, steps) as (client, _app, _runtime):
        cid = conversation(client)
        run, events = finish(client, start(client, cid))
        assert run['state'] == 'completed' and run['finishedAt'] is not None
        assert [event['sequence'] for event in events] == list(range(1, len(events) + 1))
        assert [event['type'] for event in events] == ['run.state_changed', 'activity.updated', 'message.delta',
            'message.delta', 'run.state_changed']
        assert events[0]['payload']['state'] == 'running' and events[-1]['payload']['state'] == 'completed'
        messages = client.get(base() + f'/conversations/{cid}/messages').json()['messages']
        assert [(item['role'], item['text']) for item in messages] == [('user', 'Проверь резюме'), ('assistant', 'Ответ.')]
        later = client.get(base() + f"/runs/{run['id']}/events/{events[2]['sequence']}").json()
        assert [event['sequence'] for event in later['events']] == [4, 5]


def test_stop_cancels_the_run_and_records_the_cancelled_answer(tmp_path):
    started, release = threading.Event(), threading.Event()
    with assistant_app(tmp_path, blocking(started, release)) as (client, _app, _runtime):
        cid = conversation(client)
        run = start(client, cid)
        wait(started)
        assert client.post(base() + f"/runs/{run['id']}/cancel", json={}).json()['state'] == 'cancelling'
        run, _events = finish(client, run)
        assert run['state'] == 'cancelled' and run['error']['code'] == 'AGENT_CANCELLED'
        answer = client.get(base() + f'/conversations/{cid}/messages').json()['messages'][-1]
        assert answer['role'] == 'assistant' and answer['error']['code'] == 'AGENT_CANCELLED'


def test_one_run_per_project_and_a_retried_submit_returns_the_same_run(tmp_path):
    started, release = threading.Event(), threading.Event()
    with assistant_app(tmp_path, blocking(started, release)) as (client, _app, _runtime):
        first, second = conversation(client), conversation(client)
        run = start(client, first)
        wait(started)
        assert start(client, first)['id'] == run['id']
        refused = start(client, second, request_id='request-2', status=409)
        assert refused['error']['code'] == 'ASSISTANT_RUN_ACTIVE'
        release.set()
        assert finish(client, run)[0]['state'] == 'completed'
        assert start(client, second, request_id='request-2')['state'] == 'queued'


def test_the_next_run_gets_the_last_messages_of_the_conversation(tmp_path):
    prompts = []

    async def steps(_tools, value, _cancel, _emit):
        prompts.append(value.prompt)
        return 'Первый ответ.' if len(prompts) == 1 else 'Второй ответ.'
    with assistant_app(tmp_path, steps) as (client, _app, runtime):
        cid = conversation(client)
        finish(client, start(client, cid, 'Сократи текст'))
        using(runtime, steps)
        finish(client, start(client, cid, 'Ещё короче', request_id='request-2'))
        assert 'Сократи текст' in prompts[1] and 'Первый ответ.' in prompts[1] and 'Ещё короче' in prompts[1]
        assert 'Первый ответ.' not in prompts[0]


def test_a_run_left_running_by_an_earlier_process_reads_as_interrupted(tmp_path):
    started, release = threading.Event(), threading.Event()
    with assistant_app(tmp_path, blocking(started, release)) as (client, application, _runtime):
        cid = conversation(client)
        run = start(client, cid)
        wait(started)
        # The process ends without finishing the run: its control and task are gone, the stored state stays running.
        service = application.state.assistant
        control = service.controls.pop(run['id'])
        release.set()
        deadline = time.monotonic() + 5
        while not control.task.done():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        stored = service.store.conversation('template-project', cid)
        stored.runs[-1] = stored.runs[-1].model_copy(update={'state': 'running', 'finished_at': None})
        service.store._write(service.store.directory('template-project', 'conversations', cid + '.json'), stored)
    with v2_app(tmp_path) as (client, _app):
        runs = client.get(base() + f'/conversations/{cid}/messages').json()['runs']
        assert runs[-1]['state'] == 'interrupted' and runs[-1]['error']['code'] == 'AGENT_INTERRUPTED'
