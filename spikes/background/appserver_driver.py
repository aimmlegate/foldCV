"""One owned server with independent, bounded, single-attempt job turns."""

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import inspect
import json
import math
import os

from packages.resume_core import agent_limits
from packages.resume_core.background_clock import Deadlines
from resume_api.agent.runtime import BASE_INSTRUCTIONS, provider_error
from resume_api.lifecycle import OperationFiles
from .appserver_offline import validate_config, structured_features
from .appserver_protocol import MultiplexProtocol, ProtocolLimits, TransportFailure, key
from .appserver_wire import OwnedRpcPipe


async def invoke(function, *args):
    result = function(*args)
    return await result if inspect.isawaitable(result) else result


def error_code(value):
    info = value.get("codexErrorInfo") if isinstance(value, dict) else None
    if info in ("usageLimitExceeded", "rateLimitExceeded"):
        return "RATE_LIMITED"
    if info == "unauthorized":
        return "AUTH_REQUIRED"
    return {"AGENT_QUOTA": "RATE_LIMITED", "AGENT_AUTH_REQUIRED": "AUTH_REQUIRED",
        "AGENT_MODEL_INCOMPATIBLE": "MODEL_DENIED"}.get(provider_error(value), "PROTOCOL")


@dataclass
class TurnInput:
    job: str
    model: str
    prompt: str
    developer: str
    cancelled: asyncio.Event
    tools: tuple[dict, ...] = ()
    call: object = None
    revoke: object = lambda: None
    close_tools: object = None
    before_turn: object = lambda: None
    started: object = lambda: None
    emit: object = lambda _kind, _value: None
    output_schema: dict | None = None
    text_limit: int = agent_limits.ASSISTANT_TEXT_BYTES
    allow_web: bool = False
    epoch: int = 1
    active_seconds: float = agent_limits.ACTIVE_SECONDS


@dataclass
class LiveTurn:
    value: TurnInput
    slot: object
    files: object
    context: object
    operation: object
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    calls: dict = field(default_factory=dict)
    items: dict = field(default_factory=dict)
    completed: set = field(default_factory=set)
    final_text: str | None = None
    usage: dict | None = None
    error: str | None = None
    native_started: bool = False
    began: float = 0
    started_at: float | None = None
    ended_at: float | None = None
    interrupt_at: float | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    server_pid: int | None = None
    generation: int = 0
    host_pids: tuple = ()


class SharedAppServer:
    def __init__(self, root, pipe_factory, *, owner, verify_host, clock=None,
                 limits=ProtocolLimits(), audit=lambda _value: None, wire_audit=lambda _value: None):
        self.root, self.pipe_factory = root, pipe_factory
        self.owner, self.verify_host, self.audit = owner, verify_host, audit
        self.wire_audit = wire_audit
        self.clock, self.limits = clock or Deadlines(), limits
        self.protocol = MultiplexProtocol(limits, clock=self.clock.now)
        self.pipe = self.pump = self.owner_context = None
        self.ownership = None
        self.pending, self.live = {}, {}
        self.request_jobs = {}
        self.lock, self.close_lock = asyncio.Lock(), asyncio.Lock()
        self.stopped = asyncio.Event()
        self.closed = self.fenced = False
        self.fence_code = None
        self.cleanup_failed = False
        self.generation = self.wire_bytes = 0
        self.models, self.host_pids, self.shutdowns = frozenset(), (), []

    @classmethod
    def native(cls, root, connection, **kwargs):
        from resume_api.agent.profile import AgentProfile
        from resume_api.agent.runtime import CodexAgentRuntime
        from resume_api.profile_ownership import shared_profile
        import threading
        import time
        profile = AgentProfile.from_connection(connection)
        cancel = threading.Event()
        @contextmanager
        def launch(operation):
            arguments = ("app-server", "--strict-config", "--listen", "stdio://",
                *profile.config(operation, allow_web=False))
            yield profile.launch(profile.executable, arguments, operation)
        return cls(root, lambda: OwnedRpcPipe(root, launch),
            owner=lambda: shared_profile(profile, cancel, deadline=time.monotonic() + 30, operations_root=root),
            verify_host=lambda pipe: asyncio.to_thread(CodexAgentRuntime.check_owned_host, pipe.files, require_host=False), **kwargs)

    async def until(self, awaitable, deadline):
        task, timer = asyncio.ensure_future(awaitable), asyncio.create_task(self.clock.wait(deadline))
        try:
            done, _ = await asyncio.wait((task, timer), return_when=asyncio.FIRST_COMPLETED)
            if timer in done and self.clock.now() >= deadline:
                raise TransportFailure("STARTUP_TIMEOUT")
            return await task
        finally:
            timer.cancel()
            if not task.done(): task.cancel()
            await asyncio.gather(task, timer, return_exceptions=True)

    async def prepare(self, planned=1):
        async with self.lock:
            if self.closed or self.fenced:
                raise TransportFailure("ACCOUNT_FENCED")
            if type(planned) is not int or not 1 <= planned <= self.limits.slots:
                raise TransportFailure("CAPACITY_FULL")
            if self.protocol.needs_rotation(planned):
                if self.live:
                    raise TransportFailure("SERVER_ROTATION_REQUIRED")
                await self.stop_generation()
            if self.pipe is not None:
                return
            if self.owner_context is None:
                context = self.owner()
                self.ownership = await asyncio.to_thread(context.__enter__)
                self.owner_context = context
            self.protocol = MultiplexProtocol(self.limits, clock=self.clock.now)
            self.stopped = asyncio.Event()
            self.generation += 1
            self.wire_bytes = 0
            self.host_pids = ()
            try:
                self.pipe = await self.pipe_factory().start()
                self.pump = asyncio.create_task(self.read())
                deadline = self.clock.now() + agent_limits.STARTUP_SECONDS
                await self.until(self.rpc("initialize", {"clientInfo": {"name": "foldcv", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True, "requestAttestation": False}}), deadline)
                self.send({"method": "initialized"})
                validate_config(await self.until(self.rpc("config/read", {"includeLayers": True}), deadline))
                metadata = await self.until(self.rpc("model/list", {"includeHidden": False, "limit": 100}), deadline)
                if metadata.get("nextCursor") is not None or not isinstance(metadata.get("data"), list):
                    raise TransportFailure("MODEL_DENIED")
                self.models = frozenset(item["model"] for item in metadata["data"]
                    if isinstance(item, dict) and key(item.get("model")) and "medium" in {
                        part.get("reasoningEffort") for part in item.get("supportedReasoningEfforts", [])})
            except BaseException:
                await self.fence("STARTUP_FAILED")
                raise

    async def rpc(self, method, params, *, job=None):
        if self.fenced:
            raise TransportFailure(self.fence_code or "ACCOUNT_FENCED")
        request = self.protocol.request(method, params, job=job)
        future = asyncio.get_running_loop().create_future()
        future.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
        self.pending[request["id"]] = future
        self.request_jobs[request["id"]] = job
        try:
            self.send(request)
            return await asyncio.shield(future)
        finally:
            if future.done():
                self.pending.pop(request["id"], None)
                self.request_jobs.pop(request["id"], None)

    def send(self, frame):
        self.wire_audit({"direction": "client", "generation": self.generation, "at": self.clock.now(), "frame": frame})
        self.pipe.send(frame)

    async def read(self):
        try:
            while True:
                raw = await self.pipe.receive()
                self.wire_bytes += len(raw)
                if self.wire_bytes > self.limits.wire_bytes_per_turn * self.limits.threads_per_server:
                    raise TransportFailure("SERVER_WIRE_LIMIT")
                frame = json.loads(raw)
                observed_at = self.clock.now()
                self.wire_audit({"direction": "server", "generation": self.generation, "at": observed_at, "frame": frame})
                actions = self.protocol.accept(raw)
                for action in actions:
                    try:
                        self.route(action, observed_at)
                    except Exception as error:
                        code = getattr(error, "code", "PROTOCOL")
                        live = self.live.get(action.job)
                        if live is None or code not in {"NORMALIZED_OUTPUT_LIMIT", "ITEM_LIMIT", "TEXT_LIMIT"}:
                            raise
                        live.error, live.slot.cancelling = code, True
                        live.value.revoke()
                        live.changed.set()
                if "method" not in frame:
                    future = self.pending.get(frame.get("id"))
                    if future is not None and not future.done():
                        if "error" in frame:
                            future.set_exception(TransportFailure(error_code(frame["error"])))
                        else:
                            future.set_result(frame["result"])
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            await self.fence(getattr(error, "code", "PROTOCOL"))

    def route(self, action, observed_at):
        if action.kind == "reply":
            self.send(action.value)
            return
        if action.kind == "account_event":
            if action.value["method"] == "account/updated" and action.value["params"].get("authMode") not in {None, "chatgpt"}:
                raise TransportFailure("AUTH_REQUIRED")
            return
        live = self.live.get(action.job)
        if live is None:
            return
        slot = live.slot
        if action.kind == "tool":
            call = action.value
            live.calls[call.call_id] = asyncio.create_task(self.tool(live, call))
        elif action.kind == "text":
            live.value.emit("message.delta", {"text": action.value})
        elif action.kind == "event":
            self.item(live, action.value)
        elif action.kind == "started":
            live.started_at = live.started_at if live.started_at is not None else observed_at
        elif action.kind == "terminal":
            live.ended_at = observed_at
            if slot.terminal == "failed":
                live.error = error_code(action.value.get("error"))
            if slot.terminal == "completed" and slot.active_deadline is not None and self.clock.now() >= slot.active_deadline:
                live.error = "DEADLINE"
        elif action.kind in {"limit", "deadline", "turn_error"}:
            live.error = error_code(action.value) if action.kind == "turn_error" else action.value
            slot.cancelling = True
            live.value.revoke()
        live.changed.set()

    def item(self, live, frame):
        params, method = frame["params"], frame["method"]
        if method == "thread/tokenUsage/updated":
            from packages.resume_core.models.agent import AgentUsage
            usage = params["tokenUsage"]["total"]
            live.usage = AgentUsage.model_validate({name: usage[name] for name in
                ("inputTokens", "cachedInputTokens", "outputTokens", "totalTokens")}).model_dump(by_alias=True)
            live.value.emit("usage.reported", live.usage)
            return
        if method not in {"item/started", "item/completed"}:
            return
        item = params.get("item", {})
        kind, identifier = item.get("type"), item.get("id")
        if not key(identifier) or kind not in {"userMessage", "agentMessage", "reasoning", "dynamicToolCall", "webSearch"}:
            raise TransportFailure("UNEXPECTED_TOOL_ACTIVITY")
        if kind == "dynamicToolCall" and (item.get("namespace") != live.slot.namespace or item.get("tool") not in live.slot.tools):
            raise TransportFailure("TOOL_CAPABILITY_DENIED")
        if kind == "webSearch" and not live.value.allow_web:
            raise TransportFailure("UNEXPECTED_TOOL_ACTIVITY")
        if method == "item/started":
            if identifier not in live.items and len(live.items) >= 128:
                raise TransportFailure("ITEM_LIMIT")
            if identifier in live.items and live.items[identifier] != kind:
                raise TransportFailure("IDENTITY_INVALID")
            live.items[identifier] = kind
        else:
            if live.items.get(identifier) != kind or identifier in live.completed:
                raise TransportFailure("IDENTITY_INVALID")
            live.completed.add(identifier)
            if kind == "agentMessage" and item.get("phase") != "commentary":
                text = item.get("text")
                if not isinstance(text, str) or len(text.encode()) > live.slot.text_limit:
                    raise TransportFailure("TEXT_LIMIT")
                live.final_text = text

    async def tool(self, live, call):
        try:
            live.value.emit("tool.started", {"callId": call.call_id, "name": call.tool, "error": None})
            if live.value.call is None or live.slot.cancelling:
                raise TransportFailure("TOOL_CAPABILITY_DENIED")
            content, success = await live.value.call(call.tool, call.arguments)
            reply = self.protocol.finish_tool(live.slot.job, live.slot.identity, call.call_id, content, success=success)
            if reply is not None and not self.fenced:
                self.send(reply)
            live.value.emit("tool.completed" if success else "tool.failed", {
                "callId": call.call_id, "name": call.tool, "error": None if success else {"code": "AGENT_TOOL_DENIED"}})
        except Exception as error:
            live.error = getattr(error, "code", "TOOL_FAILED")
            live.slot.cancelling = True
            live.value.revoke()
            if call.response is None:
                reply = self.protocol.reject_tool(live.slot.job, live.slot.identity, call.call_id)
                if reply is not None and not self.fenced:
                    self.send(reply)
        finally:
            live.changed.set()

    def validate_thread(self, live, result):
        if (result.get("model") != live.value.model or result.get("modelProvider") != "openai"
                or result.get("approvalPolicy") != "never" or result.get("approvalsReviewer") != "user"
                or result.get("sandbox", {}).get("type") != "readOnly" or result.get("instructionSources")
                or result.get("runtimeWorkspaceRoots") or result.get("reasoningEffort") != "medium"
                or result.get("cwd") != str(live.operation)
                or result.get("sandbox", {}).get("networkAccess") is not False
                or result.get("thread", {}).get("ephemeral") is not True
                or result.get("thread", {}).get("path") is not None):
            raise TransportFailure("ISOLATION_FAILED")

    async def run(self, value):
        if (not key(value.job) or value.model != "gpt-6-luna" or not isinstance(value.prompt, str)
                or len((BASE_INSTRUCTIONS + value.prompt + value.developer).encode()) > agent_limits.CONTEXT_BYTES
                or value.tools and (value.call is None or value.close_tools is None)
                or value.output_schema is not None and (value.tools or value.allow_web)
                or type(value.active_seconds) not in {int, float} or not math.isfinite(value.active_seconds)
                or not 0 < value.active_seconds <= agent_limits.ACTIVE_SECONDS):
            raise TransportFailure("INVALID_INPUT")
        await self.prepare()
        if value.model not in self.models:
            raise TransportFailure("MODEL_DENIED")
        names = [tool.get("name") for tool in value.tools]
        if len(names) != len(set(names)) or any(not key(name) for name in names):
            raise TransportFailure("INVALID_INPUT")
        namespace = "foldcv_" + hashlib.sha256(value.job.encode()).hexdigest()[:24]
        slot = self.protocol.register(value.job, namespace, names, epoch=value.epoch, text_limit=value.text_limit)
        slot.active_seconds = value.active_seconds
        files = OperationFiles(self.root)
        context = files.open()
        try:
            context.__enter__()
        except BaseException:
            slot.terminal = "failed"
            slot.tools_closed = slot.parser_closed = slot.operation_removed = True
            self.protocol.release(slot.job, slot.identity)
            raise
        live = LiveTurn(value, slot, files, context, files.path, began=self.clock.now())
        live.server_pid, live.generation = self.pipe.process.pid, self.generation
        self.live[value.job] = live
        try:
            tools = [{"type": "namespace", "name": namespace, "description": "This job's captured FoldCV tools",
                "tools": [{"type": "function", "name": tool["name"], "description": tool.get("description", ""),
                    "inputSchema": tool["inputSchema"]} for tool in value.tools]}] if value.tools else []
            config = {"web_search": "live" if value.allow_web else "disabled"}
            if value.output_schema is not None:
                config["features"] = structured_features()
            if self.ownership is not None:
                self.ownership.thread_pending()
            result = await self.until(self.rpc("thread/start", {"model": value.model, "cwd": str(files.path),
                "ephemeral": True, "allowProviderModelFallback": False, "approvalPolicy": "never",
                "approvalsReviewer": "user", "sandbox": "read-only", "baseInstructions": BASE_INSTRUCTIONS,
                "developerInstructions": value.developer, "environments": [], "runtimeWorkspaceRoots": [],
                "dynamicTools": tools, "config": config},
                job=value.job), slot.startup_deadline)
            self.validate_thread(live, result)
            current_hosts = tuple(await invoke(self.verify_host, self.pipe))
            self.host_pids = tuple(sorted(set(self.host_pids) | set(current_hosts)))
            live.host_pids = self.host_pids
            if self.ownership is not None:
                self.ownership.thread_ready(current_hosts)
            if self.clock.now() >= slot.startup_deadline:
                raise TransportFailure("STARTUP_TIMEOUT")
            if value.cancelled.is_set():
                raise TransportFailure("CANCELLED")
            await invoke(value.before_turn)
            if value.cancelled.is_set():
                raise TransportFailure("CANCELLED")
            params = {"threadId": slot.thread, "effort": "medium", "summary": "none",
                "input": [{"type": "text", "text": value.prompt}]}
            if value.output_schema is not None:
                params["outputSchema"] = value.output_schema
            live.native_started = True
            await self.until(self.rpc("turn/start", params, job=value.job), slot.startup_deadline)
            await invoke(value.started)
            await self.wait_terminal(live)
        except BaseException as error:
            live.error = getattr(error, "code", "PROTOCOL")
            if slot.start_request is None:
                slot.terminal = "failed"
                # A missing thread acknowledgment can still leave an unowned server context.
                if any(owner is slot for _, owner in self.protocol.pending.values()):
                    await self.fence(live.error)
            elif slot.terminal is None:
                await self.fence(live.error)
        finally:
            await self.finish(live)
        return {"state": "cancelled" if live.error == "CANCELLED" or slot.terminal == "interrupted" and not live.error else
                "failed" if live.error else slot.terminal,
            "error": live.error, "text": live.final_text, "usage": live.usage,
            "nativeStarted": live.native_started, "cleanupVerified": slot.released,
            "toolCalls": len(slot.calls), "witness": live.witness}

    async def wait_terminal(self, live):
        slot = live.slot
        while slot.terminal is None:
            live.changed.clear()
            self.protocol.expire()
            if slot.deadline_error is not None:
                live.error = slot.deadline_error
            if live.value.cancelled.is_set() or live.error is not None:
                slot.cancelling = True
                live.value.revoke()
                live.error = live.error or "CANCELLED"
                if slot.turn is not None and not slot.interrupt_requested:
                    live.interrupt_at = self.clock.now()
                    task = asyncio.create_task(self.rpc("turn/interrupt", {"threadId": slot.thread,
                        "turnId": slot.turn}, job=slot.job))
                    task.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
                if live.interrupt_at is not None and self.clock.now() >= live.interrupt_at + 0.5:
                    await self.fence("TURN_CLOSURE_UNVERIFIED")
                    break
            deadline = (live.interrupt_at + 0.5 if live.interrupt_at is not None else
                slot.active_deadline if slot.active_deadline is not None else slot.startup_deadline)
            tasks = [asyncio.create_task(live.changed.wait()), asyncio.create_task(self.clock.wait(deadline))]
            if not slot.cancelling:
                tasks.append(asyncio.create_task(live.value.cancelled.wait()))
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks: task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def finish(self, live):
        slot = live.slot
        cleanup = self.clock.now()
        try:
            live.value.revoke()
            async def close():
                if live.value.close_tools is not None:
                    if await invoke(live.value.close_tools) is not True:
                        raise TransportFailure("CLEANUP_FAILED")
                if live.calls:
                    await asyncio.gather(*live.calls.values())
                slot.tools_closed = True
                live.items.clear()
                live.completed.clear()
                slot.parser_closed = True
                await asyncio.to_thread(live.context.__exit__, None, None, None)
                slot.operation_removed = not live.operation.exists()
            await self.until(close(), cleanup + agent_limits.CLEANUP_SECONDS)
            if self.protocol.fenced and not self.protocol.server_dead:
                await self.until(self.stopped.wait(), cleanup + agent_limits.CLEANUP_SECONDS)
            self.protocol.release(slot.job, slot.identity)
            for identifier, job in tuple(self.request_jobs.items()):
                if job == slot.job:
                    future = self.pending.pop(identifier, None)
                    self.request_jobs.pop(identifier, None)
                    if future is not None and not future.done(): future.cancel()
        except BaseException:
            live.error = "CLEANUP_FAILED"
            self.cleanup_failed = True
            await self.fence("CLEANUP_FAILED")
        finally:
            live.witness = {"job": slot.job, "threadId": slot.thread, "turnId": slot.turn,
                "namespace": slot.namespace, "toolNames": sorted(slot.tools),
                "generation": live.generation, "serverPid": live.server_pid,
                "hostPids": list(live.host_pids), "nativeStarted": live.native_started,
                "toolsClosed": slot.tools_closed, "parserClosed": slot.parser_closed,
                "operation": str(live.operation), "operationRemoved": not live.operation.exists(),
                "turnResourcesClosed": slot.released, "sharedProcessDead": self.protocol.server_dead,
                "startedAt": live.started_at, "endedAt": live.ended_at, "cleanupSeconds": self.clock.now() - cleanup,
                "error": live.error, "textSha256": hashlib.sha256((live.final_text or "").encode()).hexdigest()}
            self.audit(live.witness)
            self.live.pop(slot.job, None)
            live.done.set()

    async def fence(self, code):
        self.fence_code = self.fence_code or code
        self.fenced = True
        self.protocol.server_failed()
        for live in self.live.values():
            live.error = live.error or code
            live.value.revoke()
            live.changed.set()
        for future in tuple(self.pending.values()):
            if not future.done(): future.set_exception(TransportFailure(code))
        await self.stop_generation()

    async def stop_generation(self):
        async with self.close_lock:
            pump = self.pump
            if pump is not None and pump is not asyncio.current_task():
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            if self.pipe is not None:
                try:
                    witness = await self.pipe.close()
                except BaseException:
                    self.cleanup_failed = True
                    raise
                from .appserver_offline import alive
                if any(alive(pid) for pid in self.host_pids):
                    self.cleanup_failed = True
                    raise TransportFailure("CLEANUP_FAILED")
                if self.ownership is not None:
                    self.ownership.generation_closed(self.host_pids)
                self.protocol.verified_server_dead()
                self.stopped.set()
                self.shutdowns.append({"generation": self.generation, **witness,
                    "hostPids": list(self.host_pids), "ownedHostPidsGone": True})
                self.pipe = self.pump = None

    async def close(self):
        self.closed = True
        lives = tuple(self.live.values())
        if self.live:
            await self.fence("SERVICE_SHUTDOWN")
        try:
            if lives:
                await self.until(asyncio.gather(*(live.done.wait() for live in lives)),
                    self.clock.now() + agent_limits.CLEANUP_SECONDS)
            await self.stop_generation()
            if self.cleanup_failed:
                raise TransportFailure("CLEANUP_FAILED")
        except BaseException as error:
            if self.owner_context is not None:
                context, self.owner_context = self.owner_context, None
                await asyncio.to_thread(context.__exit__, type(error), error, error.__traceback__)
            raise
        if self.owner_context is not None:
            context, self.owner_context = self.owner_context, None
            await asyncio.to_thread(context.__exit__, None, None, None)
