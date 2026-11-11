"""R3 of D158: at most eight Claude calls in flight in the service, shared by imports and rewrite previews; the
assistant takes no place and Codex has no cap."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from packages.resume_core.editing.text_rewrite import PlainTextReply
from resume_api.inference_admission import CALLS, CLAUDE_CALLS, AdmissionCancelled, CallPlaces
from resume_api.lifecycle import OperationFiles
from resume_api.providers.admitted import QueuedProvider
from resume_api.providers.claude import profile as claude_profile
from resume_api.providers.claude.content import ClaudeCliProvider, FixtureTransport
from tests.assistant.test_claude_runtime import run as assistant_run
from tests.providers.test_claude_cli import fake, request  # noqa: F401 (pytest fixture)


def test_claude_calls_are_capped_at_eight_by_the_providers_adapter_name_and_codex_is_not():
    assert CALLS.caps == {claude_profile.KIND: CLAUDE_CALLS} and CLAUDE_CALLS == 8
    assert getattr(ClaudeCliProvider, 'template_adapter') == claude_profile.KIND


@pytest.mark.asyncio
async def test_a_provider_without_a_cap_gives_a_place_at_once():
    places, cancel = CallPlaces({'capped': 1}), threading.Event()
    with places.hold('capped', cancel):
        place = await places.take('codex_cli', cancel, 0)
        with places.hold('codex_cli', cancel):
            place.release()
    assert places.busy == {'capped': 0}


@pytest.mark.asyncio
async def test_waiting_calls_take_free_places_in_the_order_they_came():
    places, cancel, order = CallPlaces({'claude_cli': 2}), threading.Event(), []
    held = [await places.take('claude_cli', cancel, 5) for _ in range(2)]

    async def call(name):
        place = await places.take('claude_cli', cancel, 5)
        order.append(name)
        return place
    waiting = [asyncio.ensure_future(call(name)) for name in 'abc']
    await asyncio.sleep(0.05)
    assert order == [] and len(places.waiting['claude_cli']) == 3
    held[0].release()
    held[0].release()  # a place goes back once
    first = await asyncio.wait_for(waiting[0], 2)
    await asyncio.sleep(0.05)
    assert order == ['a'] and places.busy == {'claude_cli': 2}
    for place in (held[1], first):
        place.release()
    for place in await asyncio.wait_for(asyncio.gather(*waiting[1:]), 2):
        place.release()
    assert order == ['a', 'b', 'c'] and places.busy == {'claude_cli': 0} and not places.waiting['claude_cli']


@pytest.mark.asyncio
async def test_a_wait_ends_with_its_time_or_its_cancel_and_takes_nothing():
    places, cancel = CallPlaces({'claude_cli': 1}), threading.Event()
    held = await places.take('claude_cli', cancel, 5)
    started = time.monotonic()
    assert await places.take('claude_cli', cancel, 0.2) is None and 0.15 < time.monotonic() - started < 2
    threading.Timer(0.1, cancel.set).start()
    assert await places.take('claude_cli', cancel, 30) is None
    with pytest.raises(AdmissionCancelled):
        with places.hold('claude_cli', cancel):
            pytest.fail('a cancelled wait runs no call')
    held.release()
    assert places.busy == {'claude_cli': 0} and not places.waiting['claude_cli']


@pytest.mark.asyncio
async def test_a_followed_place_goes_back_when_its_thread_ends_or_never_runs():
    places, cancel = CallPlaces({'claude_cli': 2}), threading.Event()
    pool, gate = ThreadPoolExecutor(max_workers=1), threading.Event()
    try:
        running, queued = [await places.take('claude_cli', cancel, 5) for _ in range(2)]
        busy = pool.submit(gate.wait, 5)
        running.follow(busy)
        later = pool.submit(pytest.fail, 'a cancelled call never runs')
        queued.follow(later)
        assert later.cancel() and places.busy == {'claude_cli': 1}
        gate.set()
        busy.result(5)
        assert places.busy == {'claude_cli': 0}
    finally:
        gate.set()
        pool.shutdown()


def test_a_rewrite_preview_waits_for_a_place_among_the_claude_calls(fake):
    cli, root, _directory, configure, audit = fake
    configure("valid", text="Synthetic rewrite")
    provider, cancel = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli)), threading.Event()
    holds = [CALLS.hold(claude_profile.KIND, cancel) for _ in range(CLAUDE_CALLS)]
    for hold in holds:
        hold.__enter__()
    admitted, result = threading.Event(), []

    def preview():
        with OperationFiles(root).open() as files:
            result.append(QueuedProvider(provider, admitted.set).generate(request(result=PlainTextReply, repair=False),
                files, cancel))
    thread = threading.Thread(target=preview)
    try:
        thread.start()
        thread.join(0.5)
        # The preview stays queued and starts no CLI while eight Claude calls are in flight.
        assert thread.is_alive() and not admitted.is_set() and len(CALLS.waiting[claude_profile.KIND]) == 1
        assert not any(entry["generation"] for entry in audit())
        holds.pop().__exit__(None, None, None)
        thread.join(10)
        assert result[0].value.text == "Synthetic rewrite" and admitted.is_set()
        assert CALLS.busy[claude_profile.KIND] == CLAUDE_CALLS - 1
    finally:
        for hold in holds:
            hold.__exit__(None, None, None)
    assert CALLS.busy[claude_profile.KIND] == 0


def test_a_cancelled_preview_stops_waiting_for_a_place(fake):
    cli, root, _directory, _configure, audit = fake
    provider, cancel = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli)), threading.Event()
    holds = [CALLS.hold(claude_profile.KIND, threading.Event()) for _ in range(CLAUDE_CALLS)]
    for hold in holds:
        hold.__enter__()
    try:
        threading.Timer(0.2, cancel.set).start()
        with OperationFiles(root).open() as files, pytest.raises(AdmissionCancelled):
            QueuedProvider(provider, lambda: pytest.fail('a cancelled preview is never admitted')).generate(
                request(result=PlainTextReply, repair=False), files, cancel)
        assert not any(entry["generation"] for entry in audit()) and not CALLS.waiting[claude_profile.KIND]
    finally:
        for hold in holds:
            hold.__exit__(None, None, None)


@pytest.mark.asyncio
async def test_the_assistant_runs_while_eight_claude_calls_are_in_flight(tmp_path):
    cancel = threading.Event()
    holds = [CALLS.hold(claude_profile.KIND, cancel) for _ in range(CLAUDE_CALLS)]
    for hold in holds:
        hold.__enter__()
    try:
        result, *_rest = await asyncio.wait_for(assistant_run(tmp_path, "complete"), 30)
        assert result.state == "completed" and CALLS.busy[claude_profile.KIND] == CLAUDE_CALLS
    finally:
        for hold in holds:
            hold.__exit__(None, None, None)
