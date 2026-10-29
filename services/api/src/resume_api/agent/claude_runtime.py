"""Claude assistant runtime (MP06a, plan section 8): one `claude -p` stream-json run per assistant run.

The same contract as `CodexAgentRuntime`: the inference permit and the profile lock, the FoldCV MCP tools only, the
same events and limits. The CLI reports its tool set and MCP status in `system/init`; until that matches, nothing
the run sends is trusted. Cancellation is SIGINT, which still ends the turn with a `result` (MP00 finding 15).
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import time

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_progress import PublicProgress
from packages.resume_core.assistant_store import AgentFailure
from packages.resume_core.models.agent import AgentUsage
from packages.resume_core.storage import StorageFailure
from resume_api.agent.host_profile import TOKEN_ENV
from resume_api.agent.runtime import BASE_INSTRUCTIONS, RuntimeResult, SessionFinished, terminal_cleanup
from resume_api.cli import qualification
from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.cli.profiles import claude as profile_rules
from resume_api.cli.profiles.claude import ClaudeProfileError
from resume_api.inference_admission import INFERENCE, AdmissionBlocked, AdmissionCancelled, AdmissionTimeout
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.profile_ownership import native_profile
from resume_api.providers.codex_cli import strict_json
from resume_api.providers.content import ContentFailure

SERVER = "foldcv"
PREFIX = "mcp__" + SERVER + "__"
# Notices without model output; `rate_limit_event` is its own type.
NOTICES = frozenset({"api_retry", "status", "thinking_tokens"})
REROUTED = frozenset({"model_fallback", "model_refusal_fallback", "model_consent_fallback"})
ERRORS = {"authentication_failed": "AGENT_AUTH_REQUIRED", "billing_error": "AGENT_QUOTA", "rate_limit": "AGENT_QUOTA",
          "model_not_found": "AGENT_MODEL_UNAVAILABLE"}
# The CLI exits by itself after its result; past this it is stopped like any other process.
EXIT_GRACE = 2.0
MAX_LINE = 2 * 1024 * 1024


def public_id(value: str) -> str:
    return "call_" + hashlib.sha256(value.encode()).hexdigest()[:24]


class MessagesStreamSession:
    """Strict reader of one assistant run's `stream-json` output, normalized to the FoldCV events (plan 8.3)."""

    def __init__(self, value, cancel, emit, *, startup, active, interrupt_grace, clock=time.monotonic):
        self.value, self.cancel, self.emit, self.clock = value, cancel, emit, clock
        self.startup, self.active, self.interrupt_grace = startup, active, interrupt_grace
        self.tools = frozenset(PREFIX + name for name in value.tools)
        self.started = clock()
        self.active_started = self.interrupt_at = self.done_at = self.cleanup_at = None
        self.done = False
        self.error: str | None = None
        self.calls: dict[str, str] = {}
        self.finished: set[str] = set()
        self.message = ""
        self.thoughts = 0
        self.progress = PublicProgress(clock)
        self.normalized = 0
        self.result = RuntimeResult()
        self.interrupt = lambda: None

    def publish(self, kind, payload):
        self.normalized += len(json.dumps({"type": kind, "payload": payload}, ensure_ascii=False).encode())
        if self.normalized > limits.RUN_BYTES - limits.TERMINAL_BYTES:
            raise AgentFailure("AGENT_OUTPUT_LIMIT")
        self.emit(kind, payload)

    def poll(self):
        now = self.clock()
        if self.done:
            if now - self.done_at >= EXIT_GRACE:
                raise SessionFinished()
            return None
        if self.active_started is None and now - self.started >= self.startup:
            raise AgentFailure("AGENT_STARTUP_TIMEOUT")
        if self.active_started is not None and now - self.active_started >= self.active:
            raise AgentFailure("AGENT_DEADLINE")
        if self.cancel.is_set():
            self.cleanup_at = self.cleanup_at or now
            self.value.revoke()
            if self.active_started is None:
                raise AgentFailure("AGENT_CANCELLED")
            if self.interrupt_at is None:
                self.interrupt_at = now
                self.interrupt()
            elif now - self.interrupt_at >= self.interrupt_grace:
                raise AgentFailure("AGENT_CANCELLED")
        return None

    def accept(self, raw):
        try:
            event = strict_json(raw, max_bytes=MAX_LINE)
        except ContentFailure:
            raise AgentFailure("AGENT_PROTOCOL") from None
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise AgentFailure("AGENT_PROTOCOL")
        if self.done:
            return None
        kind, subtype = event["type"], event.get("subtype")
        if kind == "system" and subtype == "init":
            return self.init(event)
        if self.active_started is None:
            raise AgentFailure("AGENT_PROTOCOL")
        # A nested agent's output carries its parent tool call; the run grants no agents.
        if event.get("parent_tool_use_id") is not None:
            raise AgentFailure("AGENT_TOOL_DENIED")
        if kind == "system":
            if subtype == "compact_boundary":
                raise AgentFailure("AGENT_UNEXPECTED_COMPACTION")
            if subtype == "permission_denied":
                raise AgentFailure("AGENT_TOOL_DENIED")
            if subtype in REROUTED:
                raise AgentFailure("AGENT_MODEL_REROUTED")
            if subtype not in NOTICES:
                raise AgentFailure("AGENT_PROTOCOL")
        elif kind == "stream_event":
            self.stream(event.get("event"))
        elif kind == "assistant":
            self.assistant(event)
        elif kind == "user":
            self.user(event)
        elif kind == "result":
            self.finish(event)
        elif kind != "rate_limit_event":
            raise AgentFailure("AGENT_PROTOCOL")
        return None

    def init(self, event):
        if self.active_started is not None:
            raise AgentFailure("AGENT_PROTOCOL")
        version = event.get("claude_code_version")
        try:
            if not isinstance(version, str) or profile_rules.COMPATIBILITY.status(
                    qualification.Version.parse(version)) in {"unsupported", "broken"}:
                raise AgentFailure("AGENT_RUNTIME_UNSUPPORTED")
            profile_rules.check_init(event, model=self.value.model, version=version, tools=tuple(sorted(self.tools)),
                                     mcp_servers=({"name": SERVER, "status": "connected"},))
        except (ClaudeProfileError, qualification.QualificationError):
            raise AgentFailure("AGENT_RUNTIME_UNSUPPORTED") from None
        if self.cancel.is_set():
            raise AgentFailure("AGENT_CANCELLED")
        self.value.before_start()
        self.active_started = self.clock()
        self.result.native_started = True
        return None

    def stream(self, event):
        if not isinstance(event, dict):
            raise AgentFailure("AGENT_PROTOCOL")
        if event.get("type") == "message_start":
            self.message = ""
        elif event.get("type") == "content_block_delta":
            delta = event.get("delta")
            if not isinstance(delta, dict):
                raise AgentFailure("AGENT_PROTOCOL")
            if delta.get("type") == "text_delta":
                text = delta.get("text")
                if not isinstance(text, str):
                    raise AgentFailure("AGENT_PROTOCOL")
                self.message += text
                self.limit_text(self.message)
                for start in range(0, len(text), 8000):
                    self.publish("message.delta", {"text": text[start:start + 8000]})

    def assistant(self, event):
        message = event.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            raise AgentFailure("AGENT_PROTOCOL")
        if isinstance(event.get("error"), str):
            self.error = event["error"]
        for block in message["content"]:
            kind = block.get("type") if isinstance(block, dict) else None
            if kind == "tool_use":
                identifier, name = block.get("id"), block.get("name")
                if not isinstance(identifier, str) or name not in self.tools:
                    raise AgentFailure("AGENT_TOOL_DENIED")
                if identifier in self.calls:
                    continue
                self.calls[identifier] = name
                self.result.tool_calls += 1
                if self.result.tool_calls > limits.TOOL_CALLS:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
                self.publish("tool.started", {"callId": public_id(identifier), "name": name[len(PREFIX):],
                                              "error": None})
            elif kind == "thinking":
                text = block.get("thinking")
                if isinstance(text, str) and text.strip():
                    # Claude returns summarized thinking; it goes through the same bounded public progress.
                    self.thoughts += 1
                    item = {"type": "reasoning", "id": f"thinking-{self.thoughts}"}
                    self.progress.accept("item/started", {"item": item}, self.publish)
                    self.progress.accept("item/completed", {"item": {**item, "summary": [text]}}, self.publish)
            elif kind == "text":
                if not isinstance(block.get("text"), str):
                    raise AgentFailure("AGENT_PROTOCOL")
                self.limit_text(block["text"])
            elif kind != "redacted_thinking":
                raise AgentFailure("AGENT_TOOL_DENIED")

    def user(self, event):
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            raise AgentFailure("AGENT_PROTOCOL")
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else None
            # SIGINT adds "[Request interrupted by user]" as a user turn.
            if kind == "text" and self.interrupt_at is not None:
                continue
            if kind != "tool_result" or block.get("tool_use_id") not in self.calls:
                raise AgentFailure("AGENT_TOOL_DENIED")
            identifier = block["tool_use_id"]
            if identifier in self.finished:
                continue
            self.finished.add(identifier)
            failed = block.get("is_error") is True
            self.publish("tool.failed" if failed else "tool.completed", {
                "callId": public_id(identifier), "name": self.calls[identifier][len(PREFIX):],
                "error": {"code": "AGENT_TOOL_DENIED"} if failed else None})

    def finish(self, event):
        self.usage(event.get("usage"))
        self.done, self.done_at = True, self.clock()
        self.cleanup_at = self.cleanup_at or self.done_at
        self.value.revoke()
        if event.get("permission_denials"):
            raise AgentFailure("AGENT_TOOL_DENIED")
        if self.interrupt_at is not None or self.cancel.is_set():
            self.result.state, self.result.error = "cancelled", "AGENT_CANCELLED"
            return
        if self.done_at - self.active_started >= self.active:
            raise AgentFailure("AGENT_DEADLINE")
        subtype, failed, text = event.get("subtype"), event.get("is_error"), event.get("result")
        if subtype == "error_max_turns":
            raise AgentFailure("AGENT_TOOL_LIMIT")
        if subtype != "success" or type(failed) is not bool:
            raise AgentFailure("AGENT_PROTOCOL")
        if failed:
            lowered = text.lower() if isinstance(text, str) else ""
            code = ERRORS.get(self.error or "", "AGENT_PROTOCOL")
            if self.error is None and "not logged in" in lowered:
                code = "AGENT_AUTH_REQUIRED"
            raise AgentFailure(code)
        if not isinstance(text, str):
            raise AgentFailure("AGENT_PROTOCOL")
        self.limit_text(text)
        self.result.text, self.result.state, self.result.error = text, "completed", None

    def usage(self, raw):
        if raw is None:
            return
        keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
        if not isinstance(raw, dict) or any(type(raw.get(key, 0)) is not int or raw.get(key, 0) < 0 for key in keys):
            raise AgentFailure("AGENT_PROTOCOL")
        cached = raw.get("cache_read_input_tokens", 0)
        inputs = raw.get("input_tokens", 0) + raw.get("cache_creation_input_tokens", 0) + cached
        output = raw.get("output_tokens", 0)
        self.result.usage = AgentUsage(inputTokens=inputs, cachedInputTokens=cached, outputTokens=output,
                                       totalTokens=inputs + output)
        self.publish("usage.reported", self.result.usage.model_dump(by_alias=True))

    def limit_text(self, text):
        raw = text.encode("utf-8")
        if len(raw) > limits.ASSISTANT_TEXT_BYTES or len(json.dumps(text, ensure_ascii=False).encode()) > limits.MESSAGE_BYTES - 4096:
            self.result.text = raw[:min(limits.ASSISTANT_TEXT_BYTES, 16 * 1024)].decode("utf-8", "ignore")
            self.result.truncated = True
            raise AgentFailure("AGENT_OUTPUT_LIMIT")


class ClaudeAgentRuntime:
    """`fixture_executable` runs a stand-in without the sandbox or the profile; `network` is the profile's mode
    ("loopback" for dispatch-free gates against the real CLI)."""

    def __init__(self, profile, temp_root: Path, *, fixture_executable: Path | None = None, admission=INFERENCE,
                 startup_seconds=limits.STARTUP_SECONDS, active_seconds=limits.ACTIVE_SECONDS, interrupt_grace=2.0,
                 network: bool | str = True, audit=None):
        self.profile = None if fixture_executable is not None else profile
        self.executable = fixture_executable if fixture_executable is not None else profile.executable
        self.temp_root, self.admission, self.network, self.audit = temp_root, admission, network, audit
        self.native = fixture_executable is None
        self.startup_seconds, self.active_seconds, self.interrupt_grace = startup_seconds, active_seconds, interrupt_grace

    async def run(self, value, cancel, emit):
        return await asyncio.to_thread(self.execute, value, cancel, emit)

    @contextmanager
    def owner(self, cancel, deadline):
        with native_profile(self.profile, cancel, deadline=deadline, operations_root=self.temp_root):
            try:
                yield
            finally:
                # Plan 8.4: sessions, caches and logs go after every assistant run.
                if self.profile is not None:
                    self.profile.wipe()

    def launch(self, token):
        def launch(executable, args, operation):
            if self.profile is None:
                environment = {"PATH": "/usr/bin:/bin", "TMPDIR": str(operation / "tmp")}
                command = (executable, args)
            else:
                launcher, arguments, environment = self.profile.launch(executable, args, operation,
                                                                       network=self.network)
                command = (launcher, arguments)
            environment.update({TOKEN_ENV: token, "MCP_TIMEOUT": "10000"})
            return (*command, environment)
        return launch

    def execute(self, value, cancel, emit):
        result = RuntimeResult()
        queued = value.queued_at if value.queued_at is not None else time.monotonic()
        elapsed = value.elapsed_clock
        began = elapsed()
        session, cleanup_started, operation_path, argv = None, None, None, ()
        active_seconds = self.active_seconds if value.active_seconds is None else value.active_seconds
        system = BASE_INSTRUCTIONS + "\n\n" + value.developer_instructions
        try:
            if len((value.prompt + system).encode()) > limits.CONTEXT_BYTES:
                raise AgentFailure("AGENT_CONTEXT_LIMIT")
            with self.admission.hold(cancel, deadline=queued + limits.ADMISSION_SECONDS), self.owner(
                    cancel, queued + limits.ADMISSION_SECONDS), terminal_cleanup(
                    value, self.admission, lambda: cleanup_started):
                result.timings["admission"] = time.monotonic() - queued
                session = MessagesStreamSession(value, cancel, emit, startup=self.startup_seconds,
                                                active=active_seconds, interrupt_grace=self.interrupt_grace,
                                                clock=elapsed)
                session.result.timings = result.timings
                result = session.result
                with OperationFiles(self.temp_root).open() as files:
                    operation_path = files.path
                    (files.path / "tmp").mkdir(mode=0o700, exist_ok=True)
                    config = files.path / "mcp.json"
                    descriptor = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                        # The token stays in the environment; the file names only the variable.
                        json.dump({"mcpServers": {SERVER: {"type": "http", "url": value.url, "timeout": 20000,
                            "headers": {"Authorization": "Bearer ${" + TOKEN_ENV + "}"}}}}, stream)
                    argv = profile_rules.agent_arguments(config, value.model, value.reasoning_effort,
                                                         tuple(sorted(session.tools)), system,
                                                         max_turns=limits.TOOL_CALLS + 2)
                    runner = ProcessRunner(self.executable, launch=self.launch(value.token), clock=elapsed)

                    def interrupt():
                        if files.process is not None and files.process.poll() is None:
                            os.killpg(files.process.pid, signal.SIGINT)
                    session.interrupt = interrupt

                    def before_cleanup():
                        nonlocal cleanup_started
                        if cleanup_started is None:
                            cleanup_started = session.cleanup_at or elapsed()
                        value.revoke()
                    try:
                        try:
                            runner.run(files, argv, data=value.prompt.encode(), cancel=threading.Event(),
                                       deadline=elapsed() + self.startup_seconds + active_seconds + EXIT_GRACE,
                                       on_line=session.accept, poll_input=session.poll, before_cleanup=before_cleanup,
                                       on_spawn=value.child_started, max_line=MAX_LINE, max_stdout=8 * 1024 * 1024,
                                       max_stderr=256 * 1024, max_output=8 * 1024 * 1024 + 256 * 1024)
                        except SessionFinished:
                            pass
                        except ProcessExit:
                            # A run that ends with an error result exits non-zero; the result decides.
                            if not session.done:
                                raise
                        if not session.done:
                            raise AgentFailure("AGENT_PROTOCOL")
                    finally:
                        before_cleanup()
                        files.stop_worker()
                result.timings["cleanup"] = elapsed() - cleanup_started
                if result.timings["cleanup"] > limits.CLEANUP_SECONDS:
                    raise AgentFailure("AGENT_CLEANUP_FAILED")
        except AdmissionCancelled:
            result.state, result.error = "cancelled", "AGENT_CANCELLED"
        except AdmissionTimeout:
            result.error = "AGENT_BUSY"
        except AdmissionBlocked:
            self.admission.block()
            result.state, result.error = "failed", "AGENT_CLEANUP_FAILED"
        except AgentFailure as error:
            result.state, result.error = ("cancelled" if error.code == "AGENT_CANCELLED" else "failed"), error.code
            result.truncated = result.truncated or error.code == "AGENT_OUTPUT_LIMIT"
        except (ClaudeProfileError, StorageFailure):
            result.state, result.error = "failed", "AGENT_RUNTIME_UNSUPPORTED"
        except (ProcessExit, SpikeError) as error:
            result.state = "failed"
            result.error = ("AGENT_CLEANUP_FAILED" if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}
                            else "AGENT_OUTPUT_LIMIT" if error.code in {"OUTPUT_TOO_LARGE", "INVALID_LIMIT"}
                            else "AGENT_DEADLINE" if error.code == "DEADLINE_EXCEEDED" else "AGENT_PROTOCOL")
        except (KeyError, TypeError, ValueError, AttributeError):
            result.state, result.error = "failed", "AGENT_PROTOCOL"
        except Exception:
            result.state, result.error = "failed", "AGENT_PROCESS_FAILED"
        finally:
            value.revoke()
            result.timings["total"] = elapsed() - began
            if cleanup_started is not None:
                result.timings["cleanup"] = elapsed() - cleanup_started
                if result.timings["cleanup"] > limits.CLEANUP_SECONDS:
                    result.state, result.error = "failed", "AGENT_CLEANUP_FAILED"
            if session is not None:
                result.timings["startup"] = (session.active_started or cleanup_started or elapsed()) - session.started
                if session.active_started is not None:
                    result.timings["active"] = (cleanup_started or elapsed()) - session.active_started
            result.cleanup_verified = result.error != "AGENT_CLEANUP_FAILED"
            if self.audit is not None:
                self.audit({"argv": list(argv), "operation": str(operation_path) if operation_path else None,
                            "operationRemoved": operation_path is None or not operation_path.exists(),
                            "normalizedBytes": session.normalized if session else 0, "state": result.state,
                            "error": result.error, "model": value.model, "reasoningEffort": value.reasoning_effort,
                            "nativeStarted": result.native_started, "toolCalls": result.tool_calls,
                            "usage": result.usage.model_dump(by_alias=True) if result.usage else None,
                            "timings": result.timings})
        return result
