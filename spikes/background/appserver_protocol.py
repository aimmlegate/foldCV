"""Bounded per-turn routing; shared-process ownership stays with the service."""

from collections import deque
from dataclasses import dataclass, field
import hashlib
import json

from packages.resume_core import agent_limits


class TransportFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProtocolLimits:
    version: int = 1
    slots: int = 3
    client_requests: int = 14
    tools_per_turn: int = agent_limits.TOOL_CALLS
    tool_bytes: int = agent_limits.TOOL_TOTAL_BYTES
    tool_argument_bytes: int = agent_limits.TOOL_TOTAL_BYTES
    text_bytes: int = agent_limits.ASSISTANT_TEXT_BYTES
    frame_bytes: int = 2 * 1024 * 1024
    wire_bytes_per_turn: int = 8 * 1024 * 1024
    early_frames: int = 24
    early_bytes: int = agent_limits.TOOL_TOTAL_BYTES
    terminal_routes: int = 8
    threads_per_server: int = 8


@dataclass
class ToolCall:
    identifier: str | int
    call_id: str
    fingerprint: str
    arguments: object
    tool: str
    response: dict | None = None


@dataclass
class Turn:
    job: str
    namespace: str
    tools: frozenset[str]
    epoch: int
    text_limit: int
    identity: object = field(default_factory=object)
    thread: str | None = None
    thread_requested: bool = False
    turn: str | None = None
    start_request: int | None = None
    acknowledged: bool = False
    cancelling: bool = False
    interrupt_requested: bool = False
    terminal: str | None = None
    text: str = ""
    wire_bytes: int = 0
    tool_bytes: int = 0
    argument_bytes: int = 0
    early_bytes: int = 0
    early: list[dict] = field(default_factory=list)
    calls: dict[str, ToolCall] = field(default_factory=dict)
    request_calls: dict[str | int, str] = field(default_factory=dict)
    tools_closed: bool = False
    parser_closed: bool = False
    operation_removed: bool = False
    released: bool = False
    startup_deadline: float | None = None
    active_deadline: float | None = None
    deadline_error: str | None = None
    active_seconds: float = agent_limits.ACTIVE_SECONDS


@dataclass(frozen=True)
class Routed:
    kind: str
    job: str | None = None
    value: object = None


def key(value):
    return isinstance(value, str) and 0 < len(value) <= 256


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate frame key")
        result[name] = value
    return result


class MultiplexProtocol:
    def __init__(self, limits=ProtocolLimits(), *, clock=None):
        self.limits = limits
        self.clock = clock
        self.slots, self.threads, self.pending = {}, {}, {}
        self.tool_requests = {}
        self.counter = 0
        self.closed = deque(maxlen=limits.terminal_routes)
        self.fenced = False
        self.server_dead = False
        self.thread_starts = 0

    def register(self, job, namespace, tools, *, epoch=1, text_limit=None):
        if self.fenced:
            raise TransportFailure("ACCOUNT_FENCED")
        if (not key(job) or not key(namespace) or not isinstance(tools, (list, tuple, set, frozenset))
                or type(epoch) is not int or epoch < 1
                or not all(key(tool) for tool in tools) or job in self.slots
                or any(slot.namespace == namespace for slot in self.slots.values())):
            raise TransportFailure("IDENTITY_INVALID")
        if len(self.slots) >= self.limits.slots:
            raise TransportFailure("CAPACITY_FULL")
        reservations = sum(not slot.thread_requested for slot in self.slots.values())
        if self.thread_starts + reservations >= self.limits.threads_per_server:
            raise TransportFailure("SERVER_ROTATION_REQUIRED")
        selected = self.limits.text_bytes if text_limit is None else text_limit
        if type(selected) is not int or not 0 < selected <= self.limits.wire_bytes_per_turn:
            raise TransportFailure("LIMIT_INVALID")
        slot = Turn(job, namespace, frozenset(tools), epoch, selected)
        if self.clock is not None:
            slot.startup_deadline = self.clock() + agent_limits.STARTUP_SECONDS
        self.slots[job] = slot
        return slot

    def request(self, method, params, *, job=None):
        if self.fenced or len(self.pending) >= self.limits.client_requests:
            raise TransportFailure("ACCOUNT_FENCED" if self.fenced else "REQUEST_LIMIT")
        if method not in {"initialize", "config/read", "model/list", "thread/start", "turn/start", "turn/interrupt"}:
            raise TransportFailure("METHOD_DENIED")
        slot = self.slots.get(job) if job is not None else None
        if method in {"initialize", "config/read", "model/list"}:
            if slot is not None or job is not None:
                raise TransportFailure("IDENTITY_INVALID")
        elif slot is None or slot.terminal is not None:
            raise TransportFailure("IDENTITY_INVALID")
        elif method == "thread/start":
            if slot.thread is not None or any(owner is slot for _, owner in self.pending.values()):
                raise TransportFailure("DUPLICATE_START")
            if self.thread_starts >= self.limits.threads_per_server:
                raise TransportFailure("SERVER_ROTATION_REQUIRED")
            self.thread_starts += 1
            slot.thread_requested = True
        elif method == "turn/start":
            if slot.thread is None or slot.start_request is not None or slot.turn is not None:
                raise TransportFailure("DUPLICATE_START")
            if params.get("threadId") != slot.thread:
                raise TransportFailure("IDENTITY_INVALID")
        elif method == "turn/interrupt":
            if (slot.thread is None or slot.turn is None or slot.interrupt_requested
                    or params != {"threadId": slot.thread, "turnId": slot.turn}):
                raise TransportFailure("IDENTITY_INVALID")
            slot.cancelling = True
            slot.interrupt_requested = True
        self.counter += 1
        self.pending[self.counter] = (method, slot)
        if method == "turn/start":
            slot.start_request = self.counter
        return {"id": self.counter, "method": method, "params": params}

    def accept(self, raw):
        if self.server_dead:
            raise TransportFailure("SERVER_CLOSED")
        if not isinstance(raw, bytes) or not raw or len(raw) > self.limits.frame_bytes:
            raise TransportFailure("FRAME_LIMIT")
        try:
            frame = json.loads(raw, object_pairs_hook=unique_object,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, UnicodeError, RecursionError) as error:
            raise TransportFailure("PROTOCOL") from error
        if not isinstance(frame, dict) or frame.keys() - {"id", "method", "params", "result", "error", "jsonrpc", "emittedAtMs"}:
            raise TransportFailure("PROTOCOL")
        if "emittedAtMs" in frame and ("method" not in frame or "id" in frame
                or type(frame["emittedAtMs"]) is not int or not 0 <= frame["emittedAtMs"] < 2**63):
            raise TransportFailure("PROTOCOL")
        if frame.get("jsonrpc", "2.0") != "2.0":
            raise TransportFailure("PROTOCOL")
        if "method" not in frame:
            return self.response(frame)
        method, params = frame["method"], frame.get("params", {})
        if not key(method) or not isinstance(params, dict) or "result" in frame or "error" in frame:
            raise TransportFailure("PROTOCOL")
        if "id" in frame:
            identifier = frame["id"]
            if not (key(identifier) or type(identifier) is int and identifier >= 0):
                raise TransportFailure("PROTOCOL")
            if method != "item/tool/call":
                return [Routed("reply", value=self.denied(identifier))]
        elif method in {"account/updated", "account/rateLimits/updated"}:
            return [Routed("account_event", value=frame)]
        elif method in {"warning", "configWarning", "deprecationNotice", "mcpServer/startupStatus/updated"}:
            return [Routed("metadata")]
        elif method == "remoteControl/status/changed":
            if params.get("status") != "disabled":
                raise TransportFailure("ISOLATION_FAILED")
            return [Routed("metadata")]
        elif method == "thread/started":
            # This notification never grants a route before the matching RPC response.
            return [Routed("metadata")]
        slot = self.threads.get(params.get("threadId"))
        if slot is None or slot.released or slot.terminal is not None:
            return [Routed("reply", value=self.denied(frame["id"]))] if "id" in frame else [Routed("stale")]
        if method == "thread/status/changed":
            return [Routed("metadata", slot.job)]
        slot.wire_bytes += len(raw)
        if slot.wire_bytes > self.limits.wire_bytes_per_turn:
            return [Routed("limit", slot.job, "WIRE_LIMIT")]
        if method == "turn/started":
            turn = self.turn_id(params)
            if slot.start_request is None or not key(turn) or slot.turn not in {None, turn}:
                raise TransportFailure("IDENTITY_INVALID")
            slot.turn = turn
            self.started(slot)
            return [Routed("started", slot.job, turn)]
        turn = params.get("turnId") if method != "turn/completed" else self.turn_id(params)
        if not key(turn) or turn != slot.turn:
            return [Routed("reply", value=self.denied(frame["id"]))] if "id" in frame else [Routed("stale", slot.job)]
        if not slot.acknowledged:
            slot.early_bytes += len(raw)
            if len(slot.early) >= self.limits.early_frames or slot.early_bytes > self.limits.early_bytes:
                raise TransportFailure("EARLY_FRAME_LIMIT")
            slot.early.append(frame)
            return []
        return self.scoped(slot, frame)

    def response(self, frame):
        identifier = frame.get("id")
        if type(identifier) is not int or identifier < 1 or ("result" in frame) == ("error" in frame):
            raise TransportFailure("PROTOCOL")
        request = self.pending.pop(identifier, None)
        if request is None:
            if identifier <= self.counter:
                return [Routed("stale")]
            raise TransportFailure("UNSOLICITED_RESPONSE")
        method, slot = request
        if "error" in frame:
            return [Routed("request_failed", slot.job if slot else None, frame["error"])]
        result = frame["result"]
        if not isinstance(result, dict):
            raise TransportFailure("PROTOCOL")
        if slot is None:
            return [Routed("response", value=result)]
        if method == "thread/start":
            thread_object = result.get("thread")
            if not isinstance(thread_object, dict):
                raise TransportFailure("PROTOCOL")
            thread = thread_object.get("id")
            if not key(thread) or thread in self.threads or thread in self.closed:
                raise TransportFailure("IDENTITY_INVALID")
            slot.thread = thread
            self.threads[thread] = slot
        elif method == "turn/start":
            turn = self.turn_id(result)
            if not key(turn) or slot.turn not in {None, turn}:
                raise TransportFailure("IDENTITY_INVALID")
            slot.turn, slot.acknowledged = turn, True
            self.started(slot)
            early, slot.early = slot.early, []
            slot.early_bytes = 0
            actions = [Routed("response", slot.job, result)]
            for frame in early:
                actions.extend(self.scoped(slot, frame))
            return actions
        # An interrupt reply is only an acknowledgment; terminal cleanup is still required.
        return [Routed("response", slot.job, result)]

    def scoped(self, slot, frame):
        method, params = frame["method"], frame["params"]
        if slot.terminal is not None:
            return [Routed("reply", value=self.denied(frame["id"]))] if "id" in frame else [Routed("stale", slot.job)]
        if method == "item/tool/call":
            identifier, call_id = frame["id"], params.get("callId")
            if (slot.cancelling or params.get("namespace") != slot.namespace or params.get("tool") not in slot.tools
                    or not key(call_id) or "arguments" not in params):
                return [Routed("reply", value=self.denied(identifier))]
            fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            previous = slot.calls.get(call_id)
            if previous is not None:
                if previous.fingerprint != fingerprint or previous.identifier != identifier:
                    return [Routed("reply", value=self.denied(identifier))]
                return [Routed("reply", slot.job, previous.response)] if previous.response is not None else []
            if identifier in slot.request_calls or len(slot.calls) >= self.limits.tools_per_turn:
                return [Routed("reply", value=self.denied(identifier))]
            if identifier in self.tool_requests:
                raise TransportFailure("IDENTITY_INVALID")
            argument_bytes = len(json.dumps(params["arguments"], ensure_ascii=False, separators=(",", ":")).encode())
            if argument_bytes > agent_limits.TOOL_BYTES or slot.argument_bytes + argument_bytes > self.limits.tool_argument_bytes:
                return [Routed("reply", value=self.denied(identifier)), Routed("limit", slot.job, "TOOL_ARGUMENT_LIMIT")]
            slot.argument_bytes += argument_bytes
            call = ToolCall(identifier, call_id, fingerprint, params["arguments"], params["tool"])
            slot.calls[call_id], slot.request_calls[identifier] = call, call_id
            self.tool_requests[identifier] = slot
            return [Routed("tool", slot.job, call)]
        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            if not isinstance(delta, str):
                raise TransportFailure("PROTOCOL")
            if len((slot.text + delta).encode()) > slot.text_limit:
                return [Routed("limit", slot.job, "TEXT_LIMIT")]
            slot.text += delta
            return [Routed("text", slot.job, delta)]
        if method == "turn/completed":
            status = params["turn"].get("status")
            if status not in {"completed", "failed", "interrupted"}:
                raise TransportFailure("PROTOCOL")
            slot.terminal = status
            return [Routed("terminal", slot.job, params["turn"])]
        if method == "turn/moderationMetadata":
            if "metadata" not in params:
                raise TransportFailure("PROTOCOL")
            return [Routed("metadata", slot.job)]
        if method == "error":
            if params.get("willRetry") is True:
                raise TransportFailure("HIDDEN_RETRY_DENIED")
            return [Routed("turn_error", slot.job, params.get("error"))]
        if method in {"model/rerouted", "thread/compacted"}:
            return [Routed("limit", slot.job, "MODEL_REROUTED" if method == "model/rerouted" else "UNEXPECTED_COMPACTION")]
        if method in {"item/started", "item/completed", "thread/tokenUsage/updated", "item/reasoning/summaryPartAdded",
                "item/reasoning/summaryTextDelta", "item/reasoning/textDelta", "item/mcpToolCall/progress"}:
            return [Routed("event", slot.job, frame)]
        raise TransportFailure("METHOD_DENIED")

    @staticmethod
    def turn_id(value):
        turn = value.get("turn")
        if not isinstance(turn, dict):
            raise TransportFailure("PROTOCOL")
        return turn.get("id")

    @staticmethod
    def denied(identifier):
        return {"id": identifier, "error": {"code": -32600, "message": "Tool capability denied"}}

    def finish_tool(self, job, identity, call_id, content, *, success):
        slot = self.slots.get(job)
        if slot is None or slot.identity is not identity or slot.released:
            return None
        call = slot.calls.get(call_id)
        if call is None or call.response is not None:
            return None
        if not isinstance(content, str) or type(success) is not bool:
            raise TransportFailure("PROTOCOL")
        size = len(content.encode())
        if size > agent_limits.TOOL_BYTES or slot.tool_bytes + size > self.limits.tool_bytes:
            raise TransportFailure("TOOL_LIMIT")
        slot.tool_bytes += size
        call.response = {"id": call.identifier, "result": {"contentItems": [{"type": "inputText", "text": content}], "success": success}}
        return None if slot.terminal is not None else call.response

    def reject_tool(self, job, identity, call_id):
        slot = self.slots.get(job)
        if slot is None or slot.identity is not identity or slot.released:
            return None
        call = slot.calls.get(call_id)
        if call is None or call.response is not None:
            return None
        call.response = self.denied(call.identifier)
        return None if slot.terminal is not None else call.response

    def release(self, job, identity):
        slot = self.slots.get(job)
        if (slot is None or slot.identity is not identity or slot.terminal is None
                or not slot.tools_closed or not slot.parser_closed or not slot.operation_removed
                or any(call.response is None for call in slot.calls.values())
                or self.fenced and not self.server_dead):
            raise TransportFailure("CLEANUP_UNVERIFIED")
        slot.released = True
        self.closed.append(slot.thread)
        self.threads.pop(slot.thread, None)
        self.tool_requests = {identifier: owner for identifier, owner in self.tool_requests.items() if owner is not slot}
        self.slots.pop(job)
        self.pending = {identifier: request for identifier, request in self.pending.items() if request[1] is not slot}
        return Routed("released", job, {"turnResourcesClosed": True, "sharedProcessDead": self.server_dead})

    def server_failed(self):
        self.fenced = True
        for slot in self.slots.values():
            slot.terminal, slot.cancelling = "failed", True
        return [Routed("server_failed", slot.job) for slot in self.slots.values()]

    def verified_server_dead(self):
        self.server_dead = True

    def started(self, slot):
        if slot.active_deadline is None and self.clock is not None:
            slot.active_deadline = self.clock() + slot.active_seconds

    def expire(self):
        if self.clock is None:
            raise TransportFailure("CLOCK_REQUIRED")
        now, events = self.clock(), []
        for slot in self.slots.values():
            deadline = slot.active_deadline if slot.active_deadline is not None else slot.startup_deadline
            if slot.terminal is None and slot.deadline_error is None and deadline is not None and now >= deadline:
                slot.deadline_error = "DEADLINE" if slot.active_deadline is not None else "STARTUP_TIMEOUT"
                slot.cancelling = True
                events.append(Routed("deadline", slot.job, slot.deadline_error))
        return events

    def needs_rotation(self, planned=1):
        reservations = sum(not slot.thread_requested for slot in self.slots.values())
        return self.thread_starts + reservations + planned > self.limits.threads_per_server
