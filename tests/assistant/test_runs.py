"""Runs: ordered events, Stop, one run per project, the last messages in the next prompt, restart outcomes."""

import asyncio
import threading
import time

from tests.assistant.support import (PROJECT, Editor, assistant_app, base, conversation, finish, manual_edit, proposals,
    start, using)
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
    read = threading.Event()

    async def steps(_tools, _value, cancel, emit):
        emit('activity.updated', {'itemId': 'step_1', 'kind': 'summary', 'text': 'Читаю резюме'})
        emit('message.delta', {'text': 'Отв'})
        emit('message.delta', {'text': 'ет.'})
        # Deltas live only in the memory of a running run, so it ends after the test has read them.
        while not read.is_set() and not cancel.is_set():
            await asyncio.sleep(0.01)
        return 'Ответ.'
    with assistant_app(tmp_path, steps) as (client, _app, _runtime):
        cid = conversation(client)
        run = start(client, cid)
        events, after, deadline = [], 0, time.monotonic() + 5
        while len(events) < 4:
            assert time.monotonic() < deadline
            body = client.get(base() + f"/runs/{run['id']}/events/{after}").json()
            events, after = events + body['events'], body['next']
        read.set()
        run, rest = finish(client, run, after=after)
        events += rest
        assert run['state'] == 'completed' and run['finishedAt'] is not None
        assert [event['sequence'] for event in events] == list(range(1, len(events) + 1))
        assert [event['type'] for event in events] == ['run.state_changed', 'activity.updated', 'message.delta',
            'message.delta', 'run.state_changed']
        assert events[0]['payload']['state'] == 'running' and events[-1]['payload']['state'] == 'completed'
        messages = client.get(base() + f'/conversations/{cid}/messages').json()['messages']
        assert [(item['role'], item['text']) for item in messages] == [('user', 'Проверь резюме'), ('assistant', 'Ответ.')]
        # The ended run is read from its event file, which keeps everything but the deltas.
        later = client.get(base() + f"/runs/{run['id']}/events/{events[0]['sequence']}").json()
        assert [event['sequence'] for event in later['events']] == [2, 5]


def test_the_model_list_names_the_provider_of_each_model(tmp_path):
    with assistant_app(tmp_path) as (client, _application, _runtime):
        models = client.get(base() + '/capabilities').json()['models']
        assert models and {item['provider'] for item in models} == {'Codex'}


def test_a_blank_message_is_refused_as_invalid_input(tmp_path):
    with assistant_app(tmp_path) as (client, _app, _runtime):
        cid = conversation(client)
        assert start(client, cid, ' \n\t\x1c ', status=422)['error']['code'] == 'INVALID_REQUEST'
        stored = client.get(base() + f'/conversations/{cid}/messages').json()
        assert stored['messages'] == [] and stored['runs'] == []


def test_a_finished_run_leaves_no_control_and_is_read_from_its_files(tmp_path):
    async def steps(_tools, _value, _cancel, emit):
        emit('message.delta', {'text': 'Ответ.'})
        return 'Ответ.'
    with assistant_app(tmp_path, steps) as (client, application, _runtime):
        cid = conversation(client)
        run, events = finish(client, start(client, cid))
        assert application.state.assistant.controls == {}
        again = client.get(base() + f"/runs/{run['id']}/events/0").json()
        assert again['run']['state'] == 'completed' and [event['sequence'] for event in again['events']] == [
            event['sequence'] for event in events if event['type'] != 'message.delta']
        assert client.get(base() + f'/conversations/{cid}/messages').json()['runs'][-1]['state'] == 'completed'


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


def test_a_run_and_its_proposals_never_open_the_project_on_the_event_loop(tmp_path, monkeypatch):
    # A project load or a held project lock (an Apply, an import commit) would stall every request.
    on_loop = []

    async def steps(tools, _value, _cancel, _emit):
        await tools.call('propose_changes', {'request': {'summary': 'Правка', 'ops': [
            {'op': 'replace_text', 'blockId': 'block-paper-b', 'find': 'Shared', 'replace': 'Common'}]}})
        await tools.call('propose_changes', {'request': {'summary': 'Отмена', 'ops': [
            {'op': 'history', 'direction': 'undo'}]}})
        return 'Готово.'
    with assistant_app(tmp_path, steps) as (client, application, _runtime):
        manual_edit(Editor(client, PROJECT))
        cid = conversation(client)
        repository = application.state.projects.repository
        real = repository.open

        def open_(project_id):
            try:
                asyncio.get_running_loop()
                on_loop.append(project_id)
            except RuntimeError:
                pass
            return real(project_id)
        monkeypatch.setattr(repository, 'open', open_)
        run, _events = finish(client, start(client, cid))
        assert run['state'] == 'completed' and [item['kind'] for item in proposals(client)] == ['edit', 'history']
    assert on_loop == []


def test_a_run_writes_its_files_off_the_event_loop_in_event_order(tmp_path, monkeypatch):
    # Event lines, the run state and the answer were written on the event loop and stalled every request meanwhile.
    on_loop = []

    async def steps(tools, _value, _cancel, _emit):
        await tools.call('propose_changes', {'request': {'summary': 'Правка', 'ops': [
            {'op': 'replace_text', 'blockId': 'block-paper-b', 'find': 'Shared', 'replace': 'Common'}]}})
        return 'Готово.'
    with assistant_app(tmp_path, steps) as (client, application, _runtime):
        manual_edit(Editor(client, PROJECT))
        cid = conversation(client)
        store = application.state.assistant.store
        for name in ('append_event', 'update_conversation', 'save_proposal'):
            def watched(*args, _real=getattr(store, name), _name=name, **kwargs):
                try:
                    asyncio.get_running_loop()
                    on_loop.append(_name)
                except RuntimeError:
                    pass
                return _real(*args, **kwargs)
            monkeypatch.setattr(store, name, watched)
        run, _events = finish(client, start(client, cid))
        assert run['state'] == 'completed' and [item['kind'] for item in proposals(client)] == ['edit']
        stored = [event.root.sequence for event in store.events(PROJECT, run['id'])]
        assert stored and stored == sorted(stored) and stored[-1] == max(stored)
    assert on_loop == []
