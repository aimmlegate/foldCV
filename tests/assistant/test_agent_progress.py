"""Public progress (agent_progress) is bounded, coalesced and separate from hidden reasoning, also through the runtime."""

import json
import threading

import pytest

from packages.resume_core.agent_progress import PublicProgress
from tests.support.appserver import complete_events, input_value, notification, runtime, script


def test_only_explicit_public_summary_fields_are_emitted_and_updates_are_coalesced():
    now, events = [0], []
    progress = PublicProgress(lambda: now[0])
    emit = lambda kind, payload: events.append((kind, payload))
    progress.accept("item/started", {"item": {"type": "reasoning", "id": "reasoning"}}, emit)
    progress.accept("item/reasoning/textDelta", {"itemId": "reasoning", "delta": "HIDDEN_CANARY"}, emit)
    progress.accept("item/reasoning/summaryTextDelta", {"itemId": "foreign", "summaryIndex": 0, "delta": "FOREIGN_CANARY"}, emit)
    for value in ["Reading", " source", " evidence"]:
        progress.accept("item/reasoning/summaryTextDelta", {"itemId": "reasoning", "summaryIndex": 0, "delta": value}, emit)
    assert len(events) == 1
    progress.accept("item/completed", {"item": {"type": "reasoning", "id": "reasoning", "text": "HIDDEN_CANARY",
        "content": ["HIDDEN_CANARY"], "summary": ["Reading source evidence"]}}, emit)
    assert [value[1]["text"] for value in events] == ["Reading", "Reading source evidence"]
    assert events[0][1]["itemId"] == events[1][1]["itemId"]
    assert "CANARY" not in json.dumps(events)


def test_public_summaries_have_per_item_and_per_run_bounds_without_failing_the_answer():
    events = []
    progress = PublicProgress()
    for index in range(40):
        item = {"type": "reasoning", "id": f"reasoning_{index}"}
        progress.accept("item/started", {"item": item}, lambda *_: None)
        progress.accept("item/completed", {"item": {**item, "summary": ["x" * 5000]}}, lambda kind, payload: events.append(payload))
    assert len(events) == 24
    assert all(len(event["text"]) == 1200 for event in events)


@pytest.mark.parametrize("payload", [None, [], {"item": []}, {"itemId": [], "summaryIndex": 0, "delta": "ignored"},
    {"itemId": {}, "summaryIndex": 0, "delta": "ignored"}, {"itemId": "reason", "summaryIndex": -1, "delta": "ignored"}])
def test_malformed_optional_progress_cannot_abort_the_answer(payload):
    progress, events = PublicProgress(), []
    progress.accept("item/reasoning/summaryTextDelta", payload, lambda *event: events.append(event))
    progress.accept("item/completed", payload, lambda *event: events.append(event))
    assert not events


@pytest.mark.asyncio
async def test_scripted_foreground_protocol_streams_summary_and_keeps_raw_reasoning_private(tmp_path, monkeypatch):
    from resume_api.agent.runtime import NativeSession
    requests, events = [], []
    original = NativeSession.request
    def observed(session, method, params):
        requests.append((method, params))
        return original(session, method, params)
    monkeypatch.setattr(NativeSession, "request", observed)
    value = input_value()
    summary = [notification("item/started", item={"type": "reasoning", "id": "summary_1"}),
        notification("item/reasoning/summaryTextDelta", itemId="summary_1", summaryIndex=0, delta="Checking stated facts."),
        notification("item/completed", item={"type": "reasoning", "id": "summary_1", "summary": ["Checking stated facts."], "text": "HIDDEN_CANARY"})]
    driver = runtime(tmp_path, value, script(value, turn_events=[*summary, *complete_events()]))
    result = await driver.run(value, threading.Event(), lambda kind, payload: events.append((kind, payload)))
    assert result.state == "completed" and result.text == "Python evidence checked."
    assert next(params for method, params in requests if method == "turn/start")["summary"] == "auto"
    assert any(kind == "activity.updated" and payload["text"] == "Checking stated facts." for kind, payload in events)
    assert "HIDDEN_CANARY" not in json.dumps(events)
