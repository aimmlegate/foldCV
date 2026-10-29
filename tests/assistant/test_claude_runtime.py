"""MP06a gates A1 to A10 for the Claude assistant runtime against the stream-json stand-in and a real FoldCV MCP
listener; no native inference."""

import asyncio
import json
from pathlib import Path
import sys
import threading

import pytest

from packages.resume_core import agent_limits as limits
from resume_api.agent.claude_runtime import ClaudeAgentRuntime
from resume_api.agent.mcp import PrivateMcp
from resume_api.agent.runtime import RuntimeInput
from resume_api.inference_admission import InferenceAdmission

STAND_IN = Path(__file__).resolve().parent / "fake_claude_agent.py"
TOOLS = ("read_resume", "check_resume")


class Dispatcher:
    def __init__(self):
        self.calls = 0

    def preflight(self, _params):
        return None

    def revoke(self):
        pass

    async def close(self):
        pass


class Listener(PrivateMcp):
    def __init__(self):
        self.dispatcher_state = Dispatcher()
        super().__init__(self.dispatcher_state)

        @self.sdk.tool()
        async def read_resume() -> str:
            """Read the resume."""
            self.dispatcher_state.calls += 1
            return "Synthetic resume"

        @self.sdk.tool()
        async def check_resume() -> str:
            """Check the resume."""
            return "ok"


def stand_in(root: Path, case: str) -> Path:
    directory = root / "stand-in"
    directory.mkdir()
    cli = directory / "claude"
    cli.write_text("#!" + sys.executable + "\n" + STAND_IN.read_text().split("\n", 1)[1])
    cli.chmod(0o700)
    (directory / "fixture.json").write_text(json.dumps({"case": case}))
    return cli


async def run(tmp_path, case, *, cancel=None, prompt="Проверь резюме.", grace=2.0, **options):
    cli = stand_in(tmp_path, case)
    operations = tmp_path / "operations"
    operations.mkdir(mode=0o700, exist_ok=True)
    listener = Listener()
    await listener.start()
    events, audit = [], []
    listener.issued = listener.token
    # As `ToolSession.revoke`: the listener refuses every later request.
    value = RuntimeInput(model="claude-sonnet-5-5", prompt=prompt, url=listener.url, token=listener.token, tools=TOOLS,
                         allow_web=False, reasoning_effort="high", revoke=lambda: setattr(listener, "active", False),
                         **options)
    runtime = ClaudeAgentRuntime(None, operations, fixture_executable=cli, admission=InferenceAdmission(),
                                 interrupt_grace=grace, audit=audit.append)
    try:
        result = await runtime.run(value, cancel or threading.Event(), lambda kind, payload: events.append((kind, payload)))
    finally:
        await listener.close()
    calls = [json.loads(line) for line in (cli.parent / "audit.jsonl").read_text().splitlines()]
    return result, events, calls, listener, audit[0], cli.parent


@pytest.mark.asyncio
async def test_a_run_reads_through_foldcv_tools_and_reports_text_usage_and_public_ids(tmp_path):
    result, events, calls, listener, audit, _directory = await run(tmp_path, "complete")
    assert result.state == "completed" and result.error is None and result.cleanup_verified
    assert result.text == "Готово: резюме прочитано." and result.native_started and result.tool_calls == 1
    assert listener.dispatcher_state.calls == 1
    kinds = [kind for kind, _payload in events]
    assert kinds.count("message.delta") == 2 and "activity.updated" in kinds
    started = next(payload for kind, payload in events if kind == "tool.started")
    completed = next(payload for kind, payload in events if kind == "tool.completed")
    assert started["name"] == completed["name"] == "read_resume" and started["callId"] == completed["callId"]
    assert started["callId"].startswith("call_") and "toolu_1" not in json.dumps(events)
    # A9: input counts the cache writes and reads; the total adds the output.
    assert result.usage.model_dump(by_alias=True) == {"inputTokens": 150, "cachedInputTokens": 30, "outputTokens": 40,
                                                      "totalTokens": 190}
    assert audit["operationRemoved"] and not any((tmp_path / "operations").iterdir())


@pytest.mark.asyncio
async def test_the_arguments_bind_only_the_foldcv_tools_and_keep_the_token_out_of_argv_and_files(tmp_path):
    result, _events, calls, listener, _audit, directory = await run(tmp_path, "complete")
    args = calls[0]["args"]
    # A10: the section 5 profile flags hold for the assistant arguments.
    for flag in ("--restricted", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
                 "--include-partial-messages"):
        assert flag in args
    assert args[args.index("--tools") + 1] == "" and args[args.index("--permission-mode") + 1] == "dontAsk"
    assert args[args.index("--allowedTools") + 1] == "mcp__foldcv__check_resume,mcp__foldcv__read_resume"
    assert args[args.index("--max-turns") + 1] == str(limits.TOOL_CALLS + 2)
    assert args[args.index("--effort") + 1] == "high" and json.loads(args[args.index("--settings") + 1])["disableAllHooks"]
    assert "--dangerously-skip-permissions" not in args and "--bare" not in args
    # A4: the bearer token reaches the CLI only through its environment.
    assert "FOLDCV_AGENT_MCP_CAPABILITY" in calls[0]["environment"] and listener.issued not in json.dumps(calls)
    for path in [*directory.rglob("*"), *(tmp_path / "operations").rglob("*")]:
        assert path.is_dir() or listener.issued not in path.read_text()
    assert (directory / "prompt.txt").read_text() == "Проверь резюме."
    assert result.state == "completed"


@pytest.mark.asyncio
async def test_the_mcp_config_names_the_variable_not_the_token(tmp_path, monkeypatch):
    seen = {}
    original = ClaudeAgentRuntime.launch

    def capture(self, token):
        inner = original(self, token)

        def launch(executable, args, operation):
            seen["config"] = (operation / "mcp.json").read_text()
            seen["mode"] = (operation / "mcp.json").stat().st_mode & 0o777
            seen["token"] = token
            return inner(executable, args, operation)
        return launch
    monkeypatch.setattr(ClaudeAgentRuntime, "launch", capture)
    result, *_rest = await run(tmp_path, "complete")
    assert result.state == "completed" and seen["mode"] == 0o600
    assert seen["token"] not in seen["config"] and "${FOLDCV_AGENT_MCP_CAPABILITY}" in seen["config"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "code"), [
    ("init_extra", "AGENT_RUNTIME_UNSUPPORTED"), ("wrong_token", "AGENT_RUNTIME_UNSUPPORTED"),
    ("builtin", "AGENT_TOOL_DENIED"), ("subagent", "AGENT_TOOL_DENIED"), ("denied", "AGENT_TOOL_DENIED"),
    ("permission", "AGENT_TOOL_DENIED"), ("compact", "AGENT_UNEXPECTED_COMPACTION"),
    ("fallback", "AGENT_MODEL_REROUTED"), ("unknown", "AGENT_PROTOCOL"), ("auth", "AGENT_AUTH_REQUIRED"),
    ("quota", "AGENT_QUOTA"), ("max_turns", "AGENT_TOOL_LIMIT"), ("big", "AGENT_OUTPUT_LIMIT"),
])
async def test_failures_are_typed_and_cleaned_up(tmp_path, case, code):
    result, _events, _calls, listener, audit, _directory = await run(tmp_path, case)
    assert (result.state, result.error) == ("failed", code) and result.cleanup_verified
    assert audit["operationRemoved"]
    # A1 and A2: an unbound tool set never starts the run; a built-in tool attempt has no side effect.
    if case in {"init_extra", "wrong_token"}:
        assert not result.native_started
    if case == "builtin":
        assert listener.dispatcher_state.calls == 0
    if case == "big":
        assert result.truncated and len(result.text.encode()) <= 16 * 1024


@pytest.mark.asyncio
async def test_a_run_that_renews_the_sign_in_runs_once_more_with_the_same_tools(tmp_path):
    started = []
    result, events, calls, listener, audit, _directory = await run(tmp_path, "renewal",
                                                                  before_start=lambda: started.append(1))
    assert result.state == "completed" and result.tool_calls == 1 and listener.dispatcher_state.calls == 1
    assert len(calls) == 2 and calls[0]["args"] == calls[1]["args"] and started == [1]
    # The renewal run publishes nothing: no usage, no text.
    assert [kind for kind, _payload in events].count("usage.reported") == 1 and audit["operationRemoved"]


@pytest.mark.asyncio
async def test_a_sign_in_that_stays_refused_fails_after_the_second_run(tmp_path):
    result, _events, calls, *_rest = await run(tmp_path, "auth")
    assert (result.state, result.error) == ("failed", "AGENT_AUTH_REQUIRED") and len(calls) == 2


@pytest.mark.asyncio
async def test_missing_usage_stays_unknown(tmp_path):
    result, events, *_rest = await run(tmp_path, "no_usage")
    assert result.state == "completed" and result.usage is None
    assert not any(kind == "usage.reported" for kind, _payload in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["hang", "stubborn"])
async def test_cancellation_interrupts_and_cleans_up_within_the_grace_period(tmp_path, case):
    cancel = threading.Event()

    async def stop():
        ready = tmp_path / "stand-in" / "ready"
        while not ready.exists():
            await asyncio.sleep(0.02)
        cancel.set()
    stopper = asyncio.create_task(stop())
    result, _events, _calls, _listener, audit, _directory = await run(tmp_path, case, cancel=cancel, grace=0.5)
    await stopper
    assert (result.state, result.error) == ("cancelled", "AGENT_CANCELLED") and result.cleanup_verified
    assert audit["operationRemoved"] and result.timings["cleanup"] < limits.CLEANUP_SECONDS


@pytest.mark.asyncio
async def test_an_oversized_context_starts_no_process(tmp_path):
    cli = stand_in(tmp_path, "complete")
    value = RuntimeInput(model="claude-sonnet-5-5", prompt="x" * limits.CONTEXT_BYTES, url="http://127.0.0.1:1/mcp",
                         token="t", tools=TOOLS, allow_web=False)
    runtime = ClaudeAgentRuntime(None, tmp_path, fixture_executable=cli, admission=InferenceAdmission())
    result = await runtime.run(value, threading.Event(), lambda *_: None)
    assert (result.state, result.error) == ("failed", "AGENT_CONTEXT_LIMIT")
    assert not (cli.parent / "audit.jsonl").exists()
