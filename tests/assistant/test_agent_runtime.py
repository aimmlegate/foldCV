"""The pinned App Server driver against a scripted peer: protocol, limits, deadlines and cleanup; no native inference."""

import asyncio
import json
import threading

import pytest

from packages.resume_core.assistant_store import AgentFailure
from resume_api.agent.runtime import NativeSession, SERVER_REQUESTS, frame
from resume_api.inference_admission import AdmissionBlocked, AdmissionCancelled, InferenceAdmission
from tests.support.appserver import (JumpClock, complete_events, config_result, input_value, model_result, notification,
    runtime, script, thread_result)


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", ["medium", "high"])
async def test_scripted_native_driver_correlates_out_of_order_replies_and_replaces_usage(tmp_path, effort, monkeypatch):
    calls, events, requests = [], [], []
    original = NativeSession.request

    def observed(session, method, params):
        requests.append({"method": method, "params": params})
        return original(session, method, params)
    monkeypatch.setattr(NativeSession, "request", observed)
    value = input_value(before_start=lambda: calls.append("start"), reasoning_effort=effort)
    driver = runtime(tmp_path, value, script(value, turn_events=complete_events()))
    result = await driver.run(value, threading.Event(), lambda kind, payload: events.append((kind, payload)))
    assert result.state == "completed" and result.error is None
    assert result.text == "Python evidence checked." and result.usage.total_tokens == 130
    assert result.native_started and result.tool_calls == 1 and calls == ["start"]
    assert "HIDDEN_CANARY" not in json.dumps(events) and "LATE_CANARY" not in result.text
    assert not any((tmp_path / "operations").iterdir())
    assert result.timings["cleanup"] < 5
    assert next(r for r in requests if r["method"] == "thread/start")["params"]["config"]["model_reasoning_effort"] == effort
    assert next(r for r in requests if r["method"] == "turn/start")["params"]["effort"] == effort


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["unsupported", "downgraded"])
async def test_requested_effort_is_verified_before_start_without_fallback(tmp_path, mismatch):
    value = input_value(reasoning_effort="high")
    steps = script(value, turn_events=complete_events())
    if mismatch == "unsupported":
        steps[3]["send"][0]["result"] = model_result(input_value())
    else:
        steps[4]["send"][0]["result"] = thread_result(input_value())
    result = await runtime(tmp_path, value, steps).run(value, threading.Event(), lambda *_: None)
    assert result.error == ("AGENT_MODEL_INCOMPATIBLE" if mismatch == "unsupported" else "AGENT_RUNTIME_UNSUPPORTED")
    assert not result.native_started


@pytest.mark.asyncio
async def test_active_stop_writes_interrupt_without_waiting_for_another_output_event(tmp_path):
    cancel, started, revoked = threading.Event(), threading.Event(), threading.Event()
    value = input_value(revoke=revoked.set)
    driver = runtime(tmp_path, value, script(value, interrupt=True))

    def emitted(kind, _payload):
        if kind == "run.state_changed":
            started.set()
    task = asyncio.create_task(driver.run(value, cancel, emitted))
    assert await asyncio.to_thread(started.wait, 5)
    cancel.set()
    result = await asyncio.wait_for(task, 5)
    assert result.state == "cancelled" and result.error == "AGENT_CANCELLED" and revoked.is_set()
    requests = [json.loads(line)["method"] for line in (tmp_path / "peer/requests.jsonl").read_text().splitlines()]
    assert requests.count("turn/start") == requests.count("turn/interrupt") == 1
    assert not any((tmp_path / "operations").iterdir())


@pytest.mark.asyncio
async def test_queued_stop_spends_no_start_and_never_creates_an_operation(tmp_path):
    admission = InferenceAdmission()
    admission.acquire()
    started, cancel = [], threading.Event()
    value = input_value(before_start=lambda: started.append(True))
    driver = runtime(tmp_path, value, script(value), admission=admission)
    task = asyncio.create_task(driver.run(value, cancel, lambda *_: None))
    await asyncio.sleep(0.03)
    cancel.set()
    result = await asyncio.wait_for(task, 5)
    admission.release()
    assert result.state == "cancelled" and not result.native_started and started == []
    assert not (tmp_path / "operations").exists()
    assert not (tmp_path / "peer/requests.jsonl").exists()


@pytest.mark.parametrize("method", sorted(SERVER_REQUESTS))
def test_all_native_server_requests_get_correlated_denial_and_bounded_failure(method):
    session = NativeSession(input_value(), threading.Event(), lambda *_: None)
    response = session.accept(json.dumps({"id": "server_1", "method": method, "params": {"secret": "CANARY"}}).encode())
    assert json.loads(response) == {"id": "server_1", "error": {"code": -32601, "message": "Client requests are disabled"}}
    assert session.result.error == "AGENT_TOOL_DENIED" and session.abort_at is not None
    assert "CANARY" not in response.decode()


@pytest.mark.parametrize(("method", "code"), [("model/rerouted", "AGENT_MODEL_REROUTED"),
    ("thread/compacted", "AGENT_UNEXPECTED_COMPACTION"), ("hook/started", "AGENT_PROTOCOL"),
    ("future/write", "AGENT_PROTOCOL")])
def test_state_changing_notifications_fail_closed(method, code):
    with pytest.raises(AgentFailure, match=code):
        NativeSession(input_value(), threading.Event(), lambda *_: None).accept(frame(None, method, {}))


def captured_settings(value, cwd):
    return {"threadId": "thread_1", "threadSettings": {"model": value.model, "modelProvider": "openai",
        "cwd": str(cwd), "approvalPolicy": "never", "approvalsReviewer": "user", "effort": value.reasoning_effort,
        "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
        "collaborationMode": {"mode": "default", "settings": {"model": value.model,
            "reasoning_effort": value.reasoning_effort, "developer_instructions": None}}}}


def test_native_settings_echo_keeps_captured_permissions_and_emits_no_payload(tmp_path):
    value, events = input_value(), []
    session = NativeSession(value, threading.Event(), lambda *event: events.append(event))
    session.thread, session.operation = "thread_1", tmp_path
    assert session.accept(frame(None, "thread/settings/updated", captured_settings(value, tmp_path))) is None
    assert not events and session.result.error is None and session.turn is None


@pytest.mark.parametrize(("key", "changed", "code"), [
    ("model", "other-model", "AGENT_MODEL_REROUTED"),
    ("modelProvider", "foreign", "AGENT_RUNTIME_UNSUPPORTED"),
    ("approvalPolicy", "never-again", "AGENT_RUNTIME_UNSUPPORTED"),
    ("approvalsReviewer", "auto_review", "AGENT_RUNTIME_UNSUPPORTED"),
    ("cwd", "/different", "AGENT_RUNTIME_UNSUPPORTED"),
    ("effort", "high", "AGENT_RUNTIME_UNSUPPORTED"),
    ("sandboxPolicy", {"type": "readOnly", "networkAccess": True}, "AGENT_RUNTIME_UNSUPPORTED"),
    ("sandboxPolicy", {"type": "workspaceWrite"}, "AGENT_RUNTIME_UNSUPPORTED"),
    ("sandboxPolicy", None, "AGENT_RUNTIME_UNSUPPORTED"),
    ("collaborationMode", {"mode": "plan", "settings": {}}, "AGENT_RUNTIME_UNSUPPORTED"),
    ("collaborationMode", {"mode": "default", "settings": {"model": "different"}}, "AGENT_RUNTIME_UNSUPPORTED"),
])
def test_native_settings_echo_rejects_model_or_permission_changes(tmp_path, key, changed, code):
    value = input_value()
    session = NativeSession(value, threading.Event(), lambda *_: None)
    session.thread, session.operation = "thread_1", tmp_path
    params = captured_settings(value, tmp_path)
    params["threadSettings"][key] = changed
    with pytest.raises(AgentFailure, match=code):
        session.accept(frame(None, "thread/settings/updated", params))


def test_native_settings_echo_requires_the_bound_thread_and_settings(tmp_path):
    session = NativeSession(input_value(), threading.Event(), lambda *_: None)
    session.thread, session.operation = "thread_1", tmp_path
    for params in ({"threadId": "thread_1"}, {"threadId": "foreign", "threadSettings": {}},
            {"threadId": "thread_1", "threadSettings": []}):
        with pytest.raises(AgentFailure, match="AGENT_PROTOCOL"):
            session.accept(frame(None, "thread/settings/updated", params))


def test_a_tool_call_from_another_server_is_denied_before_it_can_execute():
    # Host resource discovery arrives as a tool call of the built-in "codex" server.
    session = NativeSession(input_value(), threading.Event(), lambda *_: None)
    with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
        session.item("item/started", {"id": "resource-discovery", "type": "mcpToolCall",
            "server": "codex", "tool": "list_mcp_resources"})
    assert session.result.tool_calls == 0 and session.items == {}


@pytest.mark.parametrize(("error", "code"), [({"code": "insufficient_quota"}, "AGENT_QUOTA"),
    ({"code": "unauthorized"}, "AGENT_AUTH_REQUIRED"), ({"code": "unsupported_model"}, "AGENT_MODEL_INCOMPATIBLE")])
@pytest.mark.asyncio
async def test_native_errors_are_typed_without_a_second_turn_or_raw_diagnostic(tmp_path, error, code):
    value = input_value()
    driver = runtime(tmp_path, value, [{"method": "initialize", "send": [{"id": "$id", "error": {**error, "message": "PRIVATE_CANARY"}}]}])
    result = await driver.run(value, threading.Event(), lambda *_: None)
    assert result.state == "failed" and result.error == code and not result.native_started
    assert result.text == "" and "PRIVATE_CANARY" not in repr(result)
    assert not any((tmp_path / "operations").iterdir())


@pytest.mark.asyncio
async def test_startup_and_active_deadlines_have_distinct_typed_outcomes(tmp_path):
    clock = JumpClock()
    value = input_value(elapsed_clock=clock, child_started=lambda: clock.jump(16))
    result = await runtime(tmp_path / "startup", value, [{"method": "initialize"}], startup_seconds=15).run(
        value, threading.Event(), lambda *_: None)
    assert result.error == "AGENT_STARTUP_TIMEOUT" and not result.native_started
    clock = JumpClock()
    value = input_value(elapsed_clock=clock)

    def emitted(kind, _payload):
        if kind == "run.state_changed":
            clock.jump(181)
    result = await runtime(tmp_path / "active", value, script(value), active_seconds=180).run(value, threading.Event(), emitted)
    assert result.error == "AGENT_DEADLINE" and result.native_started


def test_untrusted_configuration_and_web_off_fail_before_side_effects():
    value = input_value()
    session = NativeSession(value, threading.Event(), lambda *_: None)
    config = config_result(value)
    config["layers"][0]["config"] = {"mcp_servers": {"foreign": {}}}
    with pytest.raises(AgentFailure, match="AGENT_RUNTIME_UNSUPPORTED"):
        session.validate_config(config)
    with pytest.raises(AgentFailure, match="AGENT_WEB_DISABLED"):
        session.item("item/started", {"id": "web_1", "type": "webSearch"})


def test_shared_permit_cancels_a_waiter_without_releasing_its_current_owner():
    permit = InferenceAdmission()
    permit.acquire()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(AdmissionCancelled):
        with permit.hold(cancel):
            pytest.fail("cancelled waiter entered")
    assert permit.locked() and not permit.acquire(blocking=False)
    permit.release()
    assert permit.acquire(blocking=False)
    permit.release()


@pytest.mark.asyncio
async def test_scripted_native_turn_completes_after_pinned_moderation_metadata_without_exposing_it(tmp_path):
    value, events = input_value(), []
    steps = script(value, turn_events=[notification("turn/moderationMetadata", turnId="turn_1",
        metadata={"opaque": "MODERATION_CANARY"}), *complete_events()])
    result = await runtime(tmp_path, value, steps).run(value, threading.Event(), lambda *event: events.append(event))
    assert result.state == "completed" and result.error is None and result.native_started
    assert result.tool_calls == 1 and result.text == "Python evidence checked." and result.usage.total_tokens == 130
    assert "MODERATION_CANARY" not in json.dumps(events)
    assert not any((tmp_path / "operations").iterdir())


def widen_fragments(tmp_path):
    path = tmp_path / "peer/fixture.json"
    data = json.loads(path.read_text())
    data["fragmentBytes"] = 65536
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.asyncio
async def test_native_raw_frame_exact_limit_and_one_over_including_ignored_reasoning(tmp_path, extra):
    value = input_value()
    ignored = notification("item/reasoning/textDelta", itemId="reasoning_1", delta="")
    overhead = len(json.dumps(ignored, ensure_ascii=False).encode())
    ignored["params"]["delta"] = "r" * (2 * 1024 * 1024 - overhead + extra)
    driver = runtime(tmp_path, value, script(value, turn_events=[ignored, *complete_events()[:-2]]))
    widen_fragments(tmp_path)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    if extra:
        assert result.error == "AGENT_OUTPUT_LIMIT" and result.truncated
    else:
        assert result.state == "completed" and result.error is None
    assert "rrrrrrrrrrrr" not in result.text
    assert not any((tmp_path / "operations").iterdir())


def outgoing_bytes(steps):
    identifiers = {"initialize": 0, "model/list": 2, "thread/start": 3, "mcpServerStatus/list": 4, "turn/start": 5}
    total = 0
    for step in steps:
        for item in step.get("send", []):
            message = {**item}
            if message.get("id") == "$id":
                message["id"] = identifiers[step["method"]]
            total += len((json.dumps(message, ensure_ascii=False) + "\n").encode())
    return total


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.asyncio
async def test_native_stdout_aggregate_exact_limit_and_one_over_counts_ignored_events(tmp_path, extra):
    value = input_value()
    ignored = [notification("item/reasoning/textDelta", itemId="reasoning_1", delta="") for _ in range(5)]
    steps = script(value, turn_events=[*ignored, *complete_events()[:-2]])
    remaining = 8 * 1024 * 1024 - outgoing_bytes(steps) + extra
    for item in ignored:
        size = min(remaining, 2 * 1024 * 1024 - 1024)
        item["params"]["delta"] = "r" * size
        remaining -= size
    assert remaining == 0 and outgoing_bytes(steps) == 8 * 1024 * 1024 + extra
    driver = runtime(tmp_path, value, steps)
    widen_fragments(tmp_path)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    assert (result.error == "AGENT_OUTPUT_LIMIT") if extra else (result.state == "completed" and result.error is None)
    assert "rrrrrrrrrrrr" not in result.text


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.asyncio
async def test_native_stderr_has_an_independent_exact_limit_and_no_raw_diagnostic_leak(tmp_path, extra):
    value = input_value()
    steps = script(value, turn_events=complete_events()[:-2])
    steps[3]["stderr"] = "PRIVATE_CANARY".ljust(256 * 1024 + extra, "x")
    driver = runtime(tmp_path, value, steps)
    widen_fragments(tmp_path)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    assert (result.error == "AGENT_OUTPUT_LIMIT") if extra else (result.state == "completed" and result.error is None)
    assert "PRIVATE_CANARY" not in repr(result)


@pytest.mark.asyncio
async def test_cleanup_failure_blocks_the_permit_before_another_waiter_can_enter(tmp_path):
    permit = InferenceAdmission()
    value = input_value(close_tools=lambda _seconds: (_ for _ in ()).throw(OSError("PRIVATE_CANARY")))
    driver = runtime(tmp_path, value, script(value, turn_events=complete_events()[:-2]), admission=permit)
    result = await driver.run(value, threading.Event(), lambda *_: None)
    assert result.error == "AGENT_CLEANUP_FAILED" and permit.blocked
    assert not permit.acquire(blocking=False)
    with pytest.raises(AdmissionBlocked):
        with permit.hold(threading.Event()):
            pytest.fail("cleanup-blocked permit entered")
    assert "PRIVATE_CANARY" not in repr(result)
