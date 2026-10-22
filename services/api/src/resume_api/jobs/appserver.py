"""Keep existing tool capabilities and fixed validators on one owned server."""

import asyncio
import json
import logging
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from packages.resume_core import agent_limits
from packages.resume_core.text_rewrite import PlainTextReply
from ..agent.runtime import RuntimeResult
from ..cli.experimental_profile import VERSION
from ..providers.codex_cli import Events, MAX_SCHEMA, strict_json
from ..providers.content import ContentFailure, ContentResult, ContentTransportReturn, ReportedUsage, outcome_state
from ..providers.structured_schema import StructuredSchema
from ..providers.dynamic_result import DynamicResultSpec
from spikes.background.appserver_driver import TurnInput, invoke
from spikes.background.appserver_protocol import TransportFailure


def agent_error(code):
    return {"RATE_LIMITED": "AGENT_QUOTA", "AUTH_REQUIRED": "AGENT_AUTH_REQUIRED",
        "MODEL_DENIED": "AGENT_MODEL_INCOMPATIBLE"}.get(code, "AGENT_" + code) if code else None


class CapabilityClient:
    def __init__(self, value, *, transport=None):
        parsed = urlsplit(value.url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None
                or parsed.path != "/mcp" or parsed.query or parsed.fragment or parsed.username is not None
                or parsed.password is not None or not isinstance(value.token, str) or not value.token):
            raise TransportFailure("INVALID_CAPABILITY")
        self.names = frozenset(value.tools)
        self.client = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=20, transport=transport,
            headers={"Authorization": "Bearer " + value.token, "Accept": "application/json, text/event-stream"})
        self.url, self.counter = value.url, 0

    async def rpc(self, method, params, *, max_bytes):
        self.counter += 1
        identifier = self.counter
        async with self.client.stream("POST", self.url, json={"jsonrpc": "2.0", "id": identifier,
                "method": method, "params": params}) as response:
            if response.status_code != 200:
                raise TransportFailure("TOOL_CAPABILITY_DENIED")
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > max_bytes:
                    raise TransportFailure("TOOL_LIMIT")
        frame = strict_json(bytes(raw), max_bytes=max_bytes)
        if (not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0" or frame.get("id") != identifier
                or "error" in frame or not isinstance(frame.get("result"), dict)):
            raise TransportFailure("PROTOCOL")
        return frame["result"]

    async def catalog(self):
        result = await self.rpc("tools/list", {}, max_bytes=256 * 1024)
        tools = result.get("tools")
        if (not isinstance(tools, list) or len(tools) != len(self.names)
                or {tool.get("name") for tool in tools} != self.names or result.get("nextCursor") is not None
                or any(not isinstance(tool.get("description"), str) or not isinstance(tool.get("inputSchema"), dict) for tool in tools)):
            raise TransportFailure("TOOL_CAPABILITY_DENIED")
        return tuple(tools)

    async def call(self, name, arguments):
        if name not in self.names or not isinstance(arguments, dict):
            raise TransportFailure("TOOL_CAPABILITY_DENIED")
        result = await self.rpc("tools/call", {"name": name, "arguments": arguments},
            max_bytes=agent_limits.TOOL_BYTES + 4096)
        content = result.get("content")
        if (not isinstance(content, list) or not content or len(content) > 16
                or any(part.get("type") != "text" or not isinstance(part.get("text"), str) for part in content)
                or type(result.get("isError", False)) is not bool):
            raise TransportFailure("PROTOCOL")
        return "\n".join(part["text"] for part in content), not result.get("isError", False)

    async def close(self):
        await self.client.aclose()


class SharedAgentRuntime:
    multiplexed = True

    def __init__(self, server, *, native=True, audit=lambda _value: None, client_factory=CapabilityClient):
        self.server, self.native, self.audit = server, native, audit
        self.client_factory = client_factory

    async def run(self, value, cancel, emit):
        result = RuntimeResult()
        client = None
        normalized = 0
        def publish(kind, payload):
            nonlocal normalized
            normalized += len(json.dumps({"type": kind, "payload": payload}, ensure_ascii=False).encode())
            if normalized > agent_limits.RUN_BYTES - agent_limits.TERMINAL_BYTES:
                raise TransportFailure("NORMALIZED_OUTPUT_LIMIT")
            if kind == "message.delta":
                for start in range(0, len(payload["text"]), 8000):
                    emit(kind, {"text": payload["text"][start:start + 8000]})
            else:
                emit(kind, payload)
        async def close():
            await client.close()
            return await invoke(value.close_tools, agent_limits.CLEANUP_SECONDS) is True
        try:
            if value.reasoning_effort != "medium":
                raise TransportFailure("MODEL_DENIED")
            if value.job_id is None or value.cancelled is None:
                raise TransportFailure("INVALID_INPUT")
            client = self.client_factory(value)
            tools = await client.catalog()
            response = await self.server.run(TurnInput(value.job_id, value.model, value.prompt,
                value.developer_instructions, value.cancelled, tools=tools, call=client.call,
                revoke=value.revoke, close_tools=close, before_turn=value.before_start,
                started=value.child_started, emit=publish, allow_web=value.allow_web,
                active_seconds=agent_limits.ACTIVE_SECONDS if value.active_seconds is None else value.active_seconds))
            result.state, result.text = response["state"], response["text"] or ""
            result.native_started = self.native and response["nativeStarted"]
            result.cleanup_verified, result.tool_calls = response["cleanupVerified"], response["toolCalls"]
            result.error = agent_error(response["error"])
            if result.state == "cancelled": result.error = result.error or "AGENT_CANCELLED"
            self.audit({**response["witness"], "state": response["state"], "nativeStarted": result.native_started,
                "error": response["error"] or ("CANCELLED" if response["state"] == "cancelled" else None),
                "cleanupVerified": result.cleanup_verified, "toolCalls": result.tool_calls,
                "normalizedBytes": normalized, "transport": "shared_appserver_v1"})
        except Exception as error:
            if not hasattr(error, "code"):
                logging.getLogger(__name__).exception("Shared runtime failed")
            code = getattr(error, "code", "PROTOCOL")
            result.state, result.error = "failed", agent_error(code)
            if client is not None:
                await client.close()
            value.revoke()
            result.cleanup_verified = (await invoke(value.close_tools, agent_limits.CLEANUP_SECONDS) is True
                and not self.server.cleanup_failed and value.job_id not in self.server.live)
        return result


class SharedContentProvider:
    multiplexed = True

    def __init__(self, server, *, native=True, audit=lambda _value: None):
        self.server, self.native, self.audit = server, native, audit
        self.loop = self.job_id = self.cancelled = None
        self.before_turn = lambda: None
        self.model_started = lambda: None
        self.sequence = 0
        self.cleanup_verified = True

    def generate(self, request, files, cancel):
        if self.loop is None or self.loop.is_closed() or self.job_id is None or self.cancelled is None:
            raise ContentFailure("BUSY")
        return asyncio.run_coroutine_threadsafe(self.execute(request, cancel), self.loop).result()

    def generate_owned(self, request, files, cancel, permit):
        with permit.hold(cancel):
            return self.generate(request, files, cancel)

    async def execute(self, request, cancel):
        policy, result_type = request.policy, request.result_type
        dynamic = isinstance(result_type, DynamicResultSpec)
        if policy.allow_repair or dynamic and request.transport is not None:
            raise ContentFailure("INVALID_INPUT")
        if not dynamic and (not isinstance(result_type, type) or not issubclass(result_type, BaseModel)
                or result_type.model_config.get("extra") != "forbid"):
            raise ContentFailure("INVALID_SCHEMA")
        plain = result_type is PlainTextReply
        began, attempts = self.server.clock.now(), 0
        reported, witness = ReportedUsage(), None
        effective_effort = policy.reasoning_effort
        raw_return, return_sent = None, False
        async def observed(outcome, code=None):
            nonlocal return_sent
            if request.on_return is not None and not return_sent:
                return_sent = True
                await asyncio.to_thread(request.on_return, ContentTransportReturn(raw_return, outcome, code,
                    attempts, reported, self.cleanup_verified, witness, effective_effort))
        def guard():
            if cancel.is_set(): raise ContentFailure("CANCELLED")
            if self.server.clock.now() >= began + policy.timeout_seconds:
                raise ContentFailure("DEADLINE")
        def failed(code):
            return ContentFailure(code,logical_attempts=attempts,usage=reported,
                cleanup_verified=self.cleanup_verified,dispatch_witness=witness,raw_return=raw_return)
        try:
            guard()
            if not plain and effective_effort is not None and effective_effort != "medium":
                raise ContentFailure("MODEL_DENIED")
            await self.server.prepare()
            metadata = self.server.reasoning.get(policy.model)
            if metadata is None: raise ContentFailure("MODEL_DENIED")
            if effective_effort is None:
                effective_effort = metadata.default
            if (effective_effort not in metadata.supported or not plain and effective_effort != "medium"):
                raise ContentFailure("MODEL_DENIED")
            if request.transport and hasattr(request.transport, "bind_guard"):
                request.transport.bind_guard(guard)
            text = request.transport.encode(request.text) if request.transport else request.text
            if not isinstance(text, str) or not text or len(text.encode()) > min(policy.max_input_bytes, policy.max_total_input_bytes):
                raise ContentFailure("INPUT_TOO_LARGE")
            result_schema = result_type.provider_schema if dynamic else result_type.model_json_schema()
            if request.transport is not None and hasattr(request.transport, "output_schema"):
                result_schema = request.transport.output_schema(result_schema)
            schema = StructuredSchema(result_schema)
            if len(json.dumps(schema.wire, ensure_ascii=False).encode()) > MAX_SCHEMA:
                raise ContentFailure("INVALID_SCHEMA")
            async def ready():
                nonlocal attempts
                guard()
                await invoke(self.before_turn)
                attempts = 1
            self.sequence += 1
            self.cleanup_verified = False
            turn_job = self.job_id if self.sequence == 1 else self.job_id + "_" + str(self.sequence)
            response = await self.server.run(TurnInput(turn_job, policy.model,
                text, "Return only the replacement text. Use no tools." if plain else
                    "Return only the captured structured result. Use no tools or invented facts.", self.cancelled,
                before_turn=ready, started=self.model_started, output_schema=None if plain else schema.wire,
                plain_text=plain, reasoning_effort=effective_effort,
                text_limit=policy.max_total_output_bytes, active_seconds=policy.timeout_seconds))
            # Preserve observed accounting before any content decoder can fail.
            witness = response["witness"]
            usage = response["usage"]
            reported = ReportedUsage(usage["inputTokens"], usage["cachedInputTokens"], usage["outputTokens"], True) if usage else ReportedUsage()
            self.cleanup_verified = response["cleanupVerified"] and not self.server.cleanup_failed
            raw_return = response["text"]
            if response["state"] != "completed" or response["error"] or not self.cleanup_verified:
                code = "CLEANUP_FAILED" if not self.cleanup_verified else response["error"] or ("CANCELLED" if response["state"] == "cancelled" else "CLI_FAILED")
                await observed(outcome_state(code), code)
                self.audit({**witness, "transport": "shared_appserver_v1", "structured": not plain,
                    "state": response["state"], "schemaValidated": False, "cleanupVerified": self.cleanup_verified})
                raise failed(code)
            await observed('completed')
            guard()
            events = Events(max_bytes=policy.max_total_output_bytes)
            events.complete, events.text = True, response["text"]
            value = events.result(result_type, schema, getattr(request.transport, "decode", None))
            if request.transport:
                value = result_type.model_validate(request.transport.restore(value), strict=True)
            guard()
            self.audit({**witness, "transport": "shared_appserver_v1", "structured": not plain,
                "nativeStarted": self.native and response["nativeStarted"], "state": response["state"],
                "schemaValidated": not plain, "textValidated": plain, "logicalAttempts": 1, "repairTurns": 0, "toolCalls": 0,
                "cleanupVerified": self.cleanup_verified})
            return ContentResult(value,reported,VERSION,policy.model,self.server.clock.now()-began,1,
                cleanup_verified=self.cleanup_verified,dispatch_witness=witness,reasoning_effort=effective_effort,
                raw_return=raw_return)
        except TransportFailure as error:
            self.cleanup_verified = not self.server.cleanup_failed and not any(
                key == self.job_id or key.startswith(self.job_id + "_") for key in self.server.live)
            await observed(outcome_state(error.code), error.code)
            raise failed(error.code) from None
        except ContentFailure as error:
            await observed(outcome_state(error.code), error.code)
            raise failed(error.code) from None
        except (ValidationError, ValueError, TypeError, UnicodeError):
            await observed('invalid_payload', 'INVALID_RESULT')
            raise failed("INVALID_RESULT") from None
        except OSError:
            await observed('transport_failure', 'TEMP_FAILED')
            raise failed("TEMP_FAILED") from None
        except Exception:
            # Interface failures must retain already observed charging evidence.
            await observed('transport_failure', 'CLI_FAILED')
            raise failed("CLI_FAILED") from None
