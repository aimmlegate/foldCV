"""Pinned protocol/lifecycle checks use a scripted executable, never native inference."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.agent_store import AgentFailure
from resume_api.agent.runtime import (CodexAgentRuntime, NativeSession, RuntimeInput, SERVER_REQUESTS,
    SessionFinished, frame)
from resume_api.cli.process_runner import ProcessRunner
from resume_api.inference_admission import AdmissionCancelled, InferenceAdmission
from tests.support.agent import fake_agent_cli


def input_value(**changes):
    return replace(RuntimeInput(model="gpt-6-luna", prompt="Read the synthetic Python evidence and check it.",
        url="http://127.0.0.1:12345/mcp", token="synthetic_mcp_capability", tools=("get_resume_context", "check_resume"),
        allow_web=False), **changes)


def config_result(value):
    return {"config": {"model_provider": "openai", "forced_login_method": "chatgpt", "project_doc_max_bytes": 0,
        "openai_base_url": None, "model_providers": {}, "model_instructions_file": None,
        "web_search": "live" if value.allow_web else "disabled", "history": {"persistence": "none"},
        "features": {**{key: False for key in ("shell_tool", "unified_exec", "multi_agent", "multi_agent_v2",
            "guardian_approval", "daemon_auto_start", "plugins", "hooks", "memories", "apps", "browser_use", "computer_use")},
            **{key: True for key in ("code_mode", "code_mode_host", "code_mode_prewarm", "skip_host_skill_discovery")}},
        "mcp_servers": {"foldcv": {"url": value.url, "bearer_token_env_var": "FOLDCV_AGENT_MCP_CAPABILITY",
            "required": True, "enabled": True, "enabled_tools": list(value.tools), "default_tools_approval_mode": "approve"}}},
        "layers": [{"name": {"type": "user"}, "config": {}}]}


def model_result(value):
    return {"data": [{"model": value.model, "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}], "nextCursor": None}


def thread_result(value):
    return {"thread": {"id": "thread_1"}, "model": value.model, "modelProvider": "openai",
        "approvalPolicy": "never", "approvalsReviewer": "user", "sandbox": {"type": "readOnly", "networkAccess": False},
        "instructionSources": [], "runtimeWorkspaceRoots": [], "reasoningEffort": "medium"}


def notification(method, **params):
    return {"method": method, "params": {"threadId": "thread_1", **params}}


def script(value, *, turn_events=None, interrupt=False):
    steps = [
        {"method": "initialize", "send": [{"id": "$id", "result": {"userAgent": "fixture"}}]},
        {"method": "initialized"}, {"method": "config/read"},
        {"method": "model/list", "send": [{"id": "$id", "result": model_result(value)},
            {"id": 1, "result": config_result(value)}]},
        {"method": "thread/start", "send": [{"id": "$id", "result": thread_result(value)}]},
        {"method": "mcpServerStatus/list", "send": [{"id": "$id", "result": {"data": [{
            "name": "foldcv", "runtimeStatus": "connected", "tools": {name: {} for name in value.tools}}], "nextCursor": None}}]},
        {"method": "turn/start", "send": [{"id": "$id", "result": {"turn": {"id": "turn_1", "status": "inProgress"}}},
            notification("turn/started", turn={"id": "turn_1", "status": "inProgress"}), *(turn_events or [])]},
    ]
    if interrupt:
        steps.append({"method": "turn/interrupt", "params": {"threadId": "thread_1", "turnId": "turn_1"},
            "send": [{"id": "$id", "result": {}}, notification("turn/completed", turn={"id": "turn_1", "status": "interrupted"})]})
    return steps


def complete_events():
    return [notification("item/started", item={"id": "reasoning_1", "type": "reasoning"}),
        notification("item/reasoning/textDelta", itemId="reasoning_1", delta="HIDDEN_CANARY"),
        notification("item/completed", item={"id": "reasoning_1", "type": "reasoning", "text": "HIDDEN_CANARY"}),
        notification("item/started", item={"id": "tool_1", "type": "mcpToolCall", "server": "foldcv", "tool": "get_resume_context"}),
        notification("item/completed", item={"id": "tool_1", "type": "mcpToolCall", "server": "foldcv", "tool": "get_resume_context", "status": "completed"}),
        notification("item/started", item={"id": "answer_1", "type": "agentMessage"}),
        notification("item/agentMessage/delta", itemId="answer_1", delta="Python evidence checked."),
        *[notification("thread/tokenUsage/updated", turnId="turn_1", tokenUsage={"total": {
            "inputTokens": count, "cachedInputTokens": 0, "outputTokens": 10, "totalTokens": count + 10}}) for count in (100, 120)],
        notification("item/completed", item={"id": "answer_1", "type": "agentMessage", "text": "Python evidence checked."}),
        notification("turn/completed", turn={"id": "turn_1", "status": "completed"}),
        notification("turn/completed", turn={"id": "turn_1", "status": "failed"}),
        notification("item/agentMessage/delta", itemId="answer_1", delta="LATE_CANARY")]


def runtime(tmp_path, value, steps, **options):
    executable = fake_agent_cli(tmp_path / "peer", steps, fragment_bytes=7)
    def runner(_files):
        return ProcessRunner(Path(sys.executable)), (str(executable), "app-server")
    return CodexAgentRuntime(SimpleNamespace(executable=executable), tmp_path / "operations",
        fixture_runner=runner, **options)


@pytest.mark.asyncio
async def test_scripted_native_driver_correlates_out_of_order_replies_and_replaces_usage(tmp_path):
    calls, events = [], []
    value = input_value(before_start=lambda: calls.append("start"))
    driver = runtime(tmp_path, value, script(value, turn_events=complete_events()))
    result = await driver.run(value, threading.Event(), lambda kind, payload: events.append((kind, payload)))
    assert result.state == "completed" and result.error is None
    assert result.text == "Python evidence checked." and result.usage.total_tokens == 130
    assert result.native_started and result.tool_calls == 1 and calls == ["start"]
    assert "HIDDEN_CANARY" not in json.dumps(events) and "LATE_CANARY" not in result.text
    assert not any((tmp_path / "operations").iterdir())
    assert result.timings["cleanup"] < 5


@pytest.mark.asyncio
async def test_active_stop_writes_interrupt_without_waiting_for_another_output_event(tmp_path):
    cancel, started, revoked = threading.Event(), threading.Event(), threading.Event()
    value = input_value(revoke=revoked.set)
    driver = runtime(tmp_path, value, script(value, interrupt=True))
    def emitted(kind, _payload):
        if kind == "run.state_changed":
            started.set()
    task = asyncio.create_task(driver.run(value, cancel, emitted))
    assert await asyncio.to_thread(started.wait, 2)
    cancel.set()
    result = await asyncio.wait_for(task, 3)
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
    result = await asyncio.wait_for(task, 2)
    admission.release()
    assert result.state == "cancelled" and not result.native_started and started == []
    assert not (tmp_path / "operations").exists()
    assert not (tmp_path / "peer/requests.jsonl").exists()


@pytest.mark.parametrize("method", sorted(SERVER_REQUESTS))
def test_all_native_server_requests_get_correlated_denial_and_bounded_failure(method):
    value = input_value()
    session = NativeSession(value, threading.Event(), lambda *_: None)
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
    value = input_value()
    startup = runtime(tmp_path / "startup", value, [{"method": "initialize"}], startup_seconds=0.1)
    result = await startup.run(value, threading.Event(), lambda *_: None)
    assert result.error == "AGENT_STARTUP_TIMEOUT" and not result.native_started
    active = runtime(tmp_path / "active", value, script(value), active_seconds=0.1)
    result = await active.run(value, threading.Event(), lambda *_: None)
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
    value = input_value()
    events = []
    steps = script(value, turn_events=[notification("turn/moderationMetadata", turnId="turn_1",
        metadata={"opaque": "MODERATION_CANARY"}), *complete_events()])
    result = await runtime(tmp_path, value, steps).run(value, threading.Event(), lambda *event: events.append(event))
    assert result.state == "completed" and result.error is None and result.native_started
    assert result.tool_calls == 1 and result.text == "Python evidence checked." and result.usage.total_tokens == 130
    assert "MODERATION_CANARY" not in json.dumps(events)
    assert not any((tmp_path / "operations").iterdir())
