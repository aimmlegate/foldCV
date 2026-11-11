"""R3 and R4 of D158: a call the provider refused as rate-limited or overloaded is made once more after a pause and the
run halves its width; at most eight calls of a provider are in flight across imports; while an import runs, no call
qualifies the CLI again."""

import asyncio
from dataclasses import replace
import json
import threading
import time
from types import SimpleNamespace

import pytest

from packages.resume_core.importing.template_import import spent_calls
from resume_api.importer.template_pipeline import BACKOFF_SECONDS, AccountStop
from resume_api.importer.template_transport import JOB_PERMIT
from resume_api.inference_admission import CLAUDE_CALLS, INFERENCE, CallPlaces
from resume_api.lifecycle import OperationFiles
from resume_api.providers.claude.content import ClaudeCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure
from tests.providers.claude_relay import MODEL, RelayTransport, stand_in
from tests.templates.pipeline_fixtures import blocks_package, resume_command
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_import_usage import satisfied, stored
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_pipeline import satisfied_review
from tests.templates.test_template_retry import failing_first, failure, run


def paused(fixture, then=None):
    """The pauses the pipeline takes, recorded instead of waited; `then` runs in each."""
    seen = []

    async def pause(seconds, _cancel):
        seen.append(seconds)
        if then is not None:
            then()
    fixture.pipeline.pause = pause
    return seen


def operation_of(fixture):
    return fixture.current().pre_draft.template_operations[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('code,review', [('RATE_LIMITED', False), ('PROVIDER_OVERLOADED', False), ('RATE_LIMITED', True)])
async def test_a_call_the_provider_refused_is_made_once_more_after_a_pause_and_the_block_admitted(tmp_path, code,
                                                                                                review):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    fixture.transport.scripted = failing_first(fixture, code, review=review)
    pauses = paused(fixture)
    result = await run(fixture)
    assert result.state == 'published' and result.tasks[0].state == 'accepted' and not result.issues
    assert result.task_results[0].disposition == 'admitted'
    assert [attempt.slot for attempt in result.attempts] == (['initial', 'review', 'review'] if review
        else ['initial', 'initial', 'review'])
    first, again = result.attempts[1:] if review else result.attempts[:2]
    assert (first.error_code, first.outcome, first.proposal_record_id) == (code, 'transport_failure', None)
    # The same request in a new attempt of the slot, after one pause; it counts toward the call cap.
    assert again.input_hash == first.input_hash and again.owner != first.owner and again.outcome == 'completed'
    assert fixture.transport.prompts.count(fixture.transport.prompts[1 if review else 0]) == 2
    assert pauses == [BACKOFF_SECONDS] and spent_calls(result) == len(fixture.transport.calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['RATE_LIMITED', 'PROVIDER_OVERLOADED'])
async def test_when_the_second_call_is_refused_too_the_block_falls_back_as_before(tmp_path, code):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    fixture.transport.scripted = failing_first(fixture, code, times=2)
    pauses = paused(fixture)
    result = await run(fixture)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert [(attempt.slot, attempt.error_code) for attempt in result.attempts] == [('initial', code)] * 2
    assert pauses == [BACKOFF_SECONDS] and len(fixture.transport.calls) == spent_calls(result) == 2
    # The fallback of a single refused call before R3: its code in the diagnostics, the block's own notice.
    assert result.task_results[0].value['diagnostics'] == [code]
    assert fixture.text() == '' and result.issues[0].message.startswith('Блок не заполнен')


@pytest.mark.asyncio
@pytest.mark.parametrize('left,during', [(BACKOFF_SECONDS - 1, None), (BACKOFF_SECONDS + 5, 300.0)])
async def test_the_pause_and_the_one_more_call_stay_inside_the_import_time(tmp_path, left, during):
    # With less time left than the pause there is no pause; a pause the import's time runs out in ends without a call.
    fixture, elapsed = RuntimeFixture(tmp_path, fallback=False), [0.0]
    fixture.pipeline.elapsed = lambda: elapsed[0]

    def script(_request, _value):
        elapsed[0] = 300.0 - left
        failure('RATE_LIMITED')
    fixture.transport.scripted = script
    pauses = paused(fixture, then=None if during is None else lambda: elapsed.__setitem__(0, during))
    result = await run(fixture)
    assert pauses == ([] if during is None else [BACKOFF_SECONDS]) and len(fixture.transport.calls) == 1
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert result.task_results[0].value['diagnostics'] == ['RATE_LIMITED']


@pytest.mark.asyncio
async def test_a_cancel_ends_the_pause_and_makes_no_more_call(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    fixture.transport.scripted = failing_first(fixture, 'RATE_LIMITED')
    cancel, waited, real = threading.Event(), [], fixture.pipeline.pause

    async def pause(seconds, event):
        threading.Timer(0.2, cancel.set).start()
        started = time.monotonic()
        await real(seconds, event)
        waited.append((seconds, time.monotonic() - started))
    fixture.pipeline.pause = pause
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted, cancel_event=cancel)
    [(seconds, spent)] = waited
    assert seconds == BACKOFF_SECONDS and spent < 5
    assert len(fixture.transport.calls) == 1 and [attempt.error_code for attempt in result.attempts] == ['RATE_LIMITED']
    assert result.state != 'published'


@pytest.mark.asyncio
async def test_a_reply_that_names_the_usage_limit_still_stops_the_import(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    fixture.transport.scripted = failing_first(fixture, 'QUOTA_EXHAUSTED')
    pauses = paused(fixture)
    with pytest.raises(AccountStop, match='QUOTA_EXHAUSTED'):
        await run(fixture)
    operation = operation_of(fixture)
    assert pauses == [] and len(fixture.transport.calls) == 1
    assert operation.state != 'published' and [attempt.error_code for attempt in operation.attempts] == ['QUOTA_EXHAUSTED']


def scheduled(pipeline, names, width, *, slow=(), narrowing=None):
    """run_tasks over model tasks that only sleep; the task `narrowing` halves the run's width as a refused call does.
    Returns the run and, per task start, the tasks running then."""
    operation = SimpleNamespace(id='operation', tasks=[SimpleNamespace(id=name, dependencies=[], kind='extract')
        for name in names], capture=SimpleNamespace(policy=SimpleNamespace(concurrency=width)))
    starts, running = [], set()

    async def execute(project, _operation_id, identifier, _deadline, _cancel):
        running.add(identifier)
        starts.append((identifier, len(running)))
        if identifier == narrowing:
            pipeline.narrow(project, operation)
        try:
            await asyncio.sleep(0.1 if identifier in slow else 0.01)
        finally:
            running.discard(identifier)
    pipeline.execute_task = execute
    return pipeline.run_tasks('project', operation, None, threading.Event()), starts


@pytest.mark.asyncio
async def test_once_the_width_halves_new_model_tasks_start_below_half_and_the_next_run_has_it_whole(tmp_path):
    pipeline = RuntimeFixture(tmp_path).pipeline
    tasks, starts = scheduled(pipeline, 'abcdef', 4, slow={'b', 'c', 'd'}, narrowing='a')
    await tasks
    # a, b, c and d start together; once a halved the width, e and f wait until fewer than two run.
    assert [name for name, _count in starts] == list('abcdef') and dict(starts)['d'] == 4
    assert dict(starts)['e'] <= 2 and dict(starts)['f'] <= 2 and pipeline.widths == {}
    tasks, starts = scheduled(pipeline, 'ghij', 4, slow=set('ghij'))
    await tasks
    assert max(count for _name, count in starts) == 4


@pytest.mark.asyncio
async def test_a_refused_call_halves_the_runs_width_and_a_resumed_import_starts_at_its_captured_width(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False, concurrency=4)
    fixture.transport.scripted = failing_first(fixture, 'RATE_LIMITED')
    widths = []

    async def lost(_seconds, _cancel):
        widths.append(dict(fixture.pipeline.widths))
        raise RuntimeError('controlled loss during the pause')
    fixture.pipeline.pause = lost
    with pytest.raises(RuntimeError, match='controlled loss'):
        await run(fixture)
    previous = operation_of(fixture)
    key = (fixture.project, previous.id)
    # The run held the halved width, never the record.
    assert widths == [{key: 2}] and fixture.pipeline.widths == {} and previous.capture.policy.concurrency == 4
    assert [attempt.error_code for attempt in previous.attempts] == ['RATE_LIMITED']
    pipeline, seen = fixture.restart(), []

    def script(_request, value):
        seen.append(dict(pipeline.widths))
        return satisfied_review(value) if 'targets' in value else raw_proposal(fixture.source)
    fixture.transport.scripted = script
    pauses = paused(fixture)
    result = await pipeline.run(fixture.project, resume_command(previous), admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'accepted'
    assert pauses == [BACKOFF_SECONDS] and seen == [{key: 4}] * 2
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'initial', 'review']


def an_import(tmp_path, name, places, blocks):
    """An import at width 8 of `blocks` independent blocks that shares the call places `places`."""
    fixture = RuntimeFixture(tmp_path / name, captured=blocks_package(blocks), concurrency=8, cap=40, fallback=False)
    fixture.pipeline.places = places
    return fixture


@pytest.mark.asyncio
async def test_two_imports_at_width_eight_keep_eight_calls_in_flight_and_every_call_ends(tmp_path):
    places = CallPlaces({'controlled': CLAUDE_CALLS})
    fixtures = [an_import(tmp_path, name, places, 8) for name in ('first', 'second')]
    lock, state, flight = threading.Lock(), {'now': 0, 'peak': 0, 'started': 0}, []

    def counted(fixture):
        def script(_request, value):
            with lock:
                state['now'] += 1
                state['started'] += 1
                state['peak'] = max(state['peak'], state['now'])
                index = state['started']
            try:
                if index <= CLAUDE_CALLS:
                    # The first calls hold their places until the cap is full, and a while longer: every other task
                    # reaches it meanwhile.
                    end = time.monotonic() + 5
                    while state['now'] < CLAUDE_CALLS and time.monotonic() < end:
                        time.sleep(0.005)
                    time.sleep(0.5)
                time.sleep(0.05)
                if index == CLAUDE_CALLS:
                    # A call that waits for a place has no attempt in the records yet.
                    flight.append(sum(attempt.state in {'reserved', 'dispatch_started'} for other in fixtures
                        for attempt in operation_of(other).attempts))
                return satisfied_review(value) if 'targets' in value else raw_proposal(fixture.source)
            finally:
                with lock:
                    state['now'] -= 1
        return script
    for fixture in fixtures:
        fixture.transport.scripted = counted(fixture)
    results = await asyncio.gather(*(run(fixture) for fixture in fixtures))
    assert state['peak'] == CLAUDE_CALLS and len(flight) == 1 and flight[0] <= CLAUDE_CALLS
    for fixture, result in zip(fixtures, results):
        assert result.state == 'published' and [task.state for task in result.tasks] == ['accepted'] * 8
        assert spent_calls(result) == 16 and all(attempt.outcome == 'completed' for attempt in result.attempts)
    assert places.busy == {'controlled': 0} and not places.waiting['controlled']


@pytest.mark.asyncio
async def test_a_call_that_waits_for_a_place_until_the_import_time_ends_reserves_nothing(tmp_path):
    places = CallPlaces({'controlled': 1})
    fixture, elapsed = an_import(tmp_path, 'late', places, 1), [0.0]
    fixture.pipeline.elapsed, tasks = (lambda: elapsed[0]), fixture.pipeline.run_tasks

    async def late(*args, **options):
        # The import's time has 0.3 s left when its call waits for the one place.
        elapsed[0] = 300 - 0.3
        return await tasks(*args, **options)
    fixture.pipeline.run_tasks = late
    held = await places.take('controlled', threading.Event(), 5)
    try:
        result = await run(fixture)
    finally:
        held.release()
    assert result.attempts == [] and fixture.transport.calls == [] and result.inference_closed
    assert result.tasks[0].state == 'source_fallback'
    assert result.task_results[0].value['diagnostics'] == ['IMPORT_PROCESSING_EXHAUSTED']
    assert places.busy == {'controlled': 0} and not places.waiting['controlled']


@pytest.mark.asyncio
async def test_a_cancelled_import_stops_waiting_and_frees_its_places(tmp_path):
    places = CallPlaces({'controlled': CLAUDE_CALLS})
    holder = an_import(tmp_path, 'holder', places, 8)
    waiter, later = an_import(tmp_path, 'waiter', places, 2), an_import(tmp_path, 'later', places, 2)
    held = []

    def hanging(_request, cancel):
        # A CLI call stopped by its cancel: the process ends and the call comes back cancelled.
        held.append(1)
        cancel.wait(10)
        raise ContentFailure('CANCELLED', logical_attempts=1, cleanup_verified=True,
            dispatch_witness={'transport': 'controlled'})
    holder.transport.generate = hanging

    async def until(condition):
        for _ in range(1000):
            if condition():
                return
            await asyncio.sleep(0.01)
        raise AssertionError('condition not reached')
    first = asyncio.ensure_future(holder.pipeline.run(holder.project, holder.command, admitted=holder.admitted))
    await until(lambda: len(held) == CLAUDE_CALLS)
    stop = threading.Event()
    second = asyncio.ensure_future(waiter.pipeline.run(waiter.project, waiter.command, admitted=waiter.admitted,
        cancel_event=stop))
    await until(lambda: len(places.waiting['controlled']) == 2)
    # A cancel ends the wait: the waiting import recorded no attempt and none of its calls ran.
    stop.set()
    stopped_waiting = await asyncio.wait_for(second, 10)
    assert stopped_waiting.attempts == [] and waiter.transport.calls == []
    assert places.busy == {'controlled': CLAUDE_CALLS}
    third = asyncio.ensure_future(run(later))
    await until(lambda: len(places.waiting['controlled']) == 2)
    # The holder's cancel stops its calls; their places go to the import that waits.
    await holder.pipeline.cancel(holder.project, operation_of(holder).id)
    stopped, published = await asyncio.wait_for(asyncio.gather(first, third), 20)
    assert stopped.state == 'cancelled' and [attempt.outcome for attempt in stopped.attempts] == ['cancelled'] * 8
    assert published.state == 'published' and [task.state for task in published.tasks] == ['accepted'] * 2
    assert places.busy == {'controlled': 0} and not places.waiting['controlled']


@pytest.mark.asyncio
async def test_no_call_of_an_import_spends_time_qualifying_while_its_snapshot_stands(tmp_path):
    # R4, read from the import's usage file: the snapshot ended before the import, which keeps it valid; the next
    # qualification runs beside the calls. A qualification takes at least half a second here.
    directory, operations = tmp_path / 'claude stand-in', tmp_path / 'operations'
    cli = stand_in(directory)
    operations.mkdir(mode=0o700)
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    probes, probe = [], provider.probe

    def slow(files, cancel, *, deadline):
        probes.append(threading.current_thread().name)
        time.sleep(0.5)
        return probe(files, cancel, deadline=deadline)
    provider.probe = slow
    with OperationFiles(operations).open() as files:
        provider.preflight(files, threading.Event(), MODEL, deadline=provider.clock() + 30)
    cache = provider.preflight_cache
    cache.snapshot = replace(cache.snapshot, expires=cache.clock() - 1)
    fixture = RuntimeFixture(tmp_path / 'import', cap=8)
    fixture.transport = RelayTransport(provider, operations, satisfied(fixture), directory / 'answers')
    fixture.pipeline = fixture.fresh_pipeline()
    permit = await INFERENCE.reserve(asyncio.Event())
    token = JOB_PERMIT.set(permit)
    try:
        result = await run(fixture)
        cache.renewing.join(10)
    finally:
        JOB_PERMIT.reset(token)
        permit.release()
    assert result.state == 'published' and not result.issues
    _path, data = stored(fixture)
    assert len(data['attempts']) == 2 and all(row['phases']['preflight'] < 0.25 for row in data['attempts'])
    # The one qualification of the import ran on its own thread and replaced the snapshot.
    assert probes == ['MainThread', 'foldcv-preflight'] and cache.snapshot.expires > cache.clock() + 200
    generations = [json.loads(line) for line in (directory / 'audit.jsonl').read_text().splitlines()]
    assert sum(entry['args'] == ['auth', 'status', '--json'] for entry in generations) == 2
