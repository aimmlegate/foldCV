"""Public progress is bounded, replayable and separate from hidden reasoning."""

import asyncio
import json
import threading

import pytest

from packages.resume_core.agent_progress import PublicProgress
from packages.resume_core.models.background import JobSnapshotV1
from tests.recovery.test_agent_runtime import input_value, script, runtime, notification, complete_events


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


def test_shared_appserver_uses_the_same_public_summary_boundary():
    from types import SimpleNamespace
    from spikes.background.appserver_driver import SharedAppServer
    events = []
    live = SimpleNamespace(progress=PublicProgress(), value=SimpleNamespace(emit=lambda kind, payload: events.append((kind, payload))),
        items={}, completed=set())
    server = SharedAppServer.__new__(SharedAppServer)
    for method, params in [("item/started", {"item": {"type": "reasoning", "id": "reason"}}),
            ("item/reasoning/textDelta", {"itemId": "reason", "delta": "HIDDEN_CANARY"}),
            ("item/reasoning/summaryTextDelta", {"itemId": "reason", "summaryIndex": 0, "delta": "Checking source evidence."}),
            ("item/completed", {"item": {"type": "reasoning", "id": "reason", "content": ["HIDDEN_CANARY"], "summary": ["Checking source evidence."]}})]:
        server.item(live, {"method": method, "params": params})
    assert len(events) == 1 and events[0][0] == "activity.updated"
    assert "HIDDEN_CANARY" not in json.dumps(events)


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


@pytest.mark.asyncio
async def test_background_progress_updates_the_live_job_and_survives_reload(tmp_path):
    from tests.recovery.test_background_agent import environment
    from resume_api.agent.runtime import RuntimeResult, ScriptedAgentRuntime
    from resume_api.jobs.runtime import JobRuntime
    service, _factory, workspace, payload, *_ = await environment(tmp_path)
    ready, finish = asyncio.Event(), asyncio.Event()
    async def scripted(_value, _cancel, emit):
        emit("tool.started", {"callId": "read", "name": "get_original_source", "error": None})
        emit("activity.updated", {"itemId": "summary", "kind": "summary", "text": "Сверяю исходник с фактами."})
        ready.set()
        await finish.wait()
        emit("tool.completed", {"callId": "read", "name": "get_original_source", "error": None})
        return RuntimeResult(state="completed", text="Проверка завершена.")
    service.runtime = ScriptedAgentRuntime(scripted)
    service.supervisor.factory = lambda job, model: JobRuntime(service, job, model)
    dispatched = asyncio.Event()
    async def observe(name, _job):
        if name == "slot_granted":
            dispatched.set()
    service.supervisor.observer = observe
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        await asyncio.wait_for(dispatched.wait(), 10)
        control = service.supervisor.controls[job.id]
        waiter = asyncio.create_task(ready.wait())
        await asyncio.wait([waiter, control.task], return_when=asyncio.FIRST_COMPLETED, timeout=10)
        assert ready.is_set(), control.task.exception() if control.task.done() else "Script did not start"
        current = service.store.read(workspace.project_id, job.id)
        assert current.event_cursor > job.event_cursor
        assert [event.root.type for event in current.activity] == ["tool.started", "activity.updated"]
        assert JobSnapshotV1.model_validate_json(current.model_dump_json(by_alias=True)).activity == current.activity
        finish.set(); await asyncio.wait_for(control.task, 10)
        saved = service.store.read(workspace.project_id, job.id)
        assert saved.execution == "completed" and saved.activity[-1].root.type == "tool.completed"
        assert service.runtime.calls == ["assistant-model"]
        assert not saved.attempts[0].native_started
        changed = saved.model_dump(by_alias=True)
        changed["activity"][0]["runId"] = "foreign"
        with pytest.raises(ValueError, match="public progress"):
            JobSnapshotV1.model_validate(changed)
    finally:
        finish.set(); await service.shutdown()
