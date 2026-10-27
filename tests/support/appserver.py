"""Scripted app-server steps and a runtime that drives the scripted peer; no native inference."""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

from resume_api.agent.runtime import CodexAgentRuntime, RuntimeInput
from resume_api.cli.process_runner import ProcessRunner

PEER = Path(__file__).resolve().parent / "appserver_peer.py"


def fake_agent_cli(root, steps, *, fragment_bytes=None):
    root.mkdir(parents=True)
    executable = root / "peer.py"
    shutil.copyfile(PEER, executable)
    config = {"agent": steps}
    if fragment_bytes is not None:
        config["fragmentBytes"] = fragment_bytes
    (root / "fixture.json").write_text(json.dumps(config))
    return executable


class JumpClock:
    """Monotonic time plus an offset the test moves forward instead of waiting."""

    def __init__(self):
        self.offset = 0.0

    def __call__(self):
        return time.monotonic() + self.offset

    def jump(self, seconds):
        self.offset += seconds


def input_value(**changes):
    return replace(RuntimeInput(model="gpt-6-luna", prompt="Read the synthetic Python evidence and check it.",
        url="http://127.0.0.1:12345/mcp", token="synthetic_mcp_capability", tools=("read_resume", "check_resume"),
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
    return {"data": [{"model": value.model, "supportedReasoningEfforts": [{"reasoningEffort": value.reasoning_effort}]}],
        "nextCursor": None}


def thread_result(value):
    return {"thread": {"id": "thread_1"}, "model": value.model, "modelProvider": "openai",
        "approvalPolicy": "never", "approvalsReviewer": "user", "sandbox": {"type": "readOnly", "networkAccess": False},
        "instructionSources": [], "runtimeWorkspaceRoots": [], "reasoningEffort": value.reasoning_effort}


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
        notification("item/started", item={"id": "tool_1", "type": "mcpToolCall", "server": "foldcv", "tool": "read_resume"}),
        notification("item/completed", item={"id": "tool_1", "type": "mcpToolCall", "server": "foldcv", "tool": "read_resume",
            "status": "completed"}),
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
    return CodexAgentRuntime(SimpleNamespace(executable=executable), tmp_path / "operations", fixture_runner=runner, **options)
