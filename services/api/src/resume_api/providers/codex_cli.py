"""Versioned Codex CLI adapter. Real generation remains closed by D004."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import math
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Callable
from contextlib import contextmanager

from pydantic import BaseModel, ValidationError

from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.cli.experimental_profile import ExperimentalCliProfile, ExperimentalProfileError
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.inference_admission import INFERENCE, AdmissionTimeout, AdmissionBlocked
from resume_api.profile_ownership import native_profile
from resume_api.rewrite_timing import add_phase, measure
from packages.resume_core.text_rewrite import PlainTextReply
from packages.resume_core.reasoning import ModelReasoning, model_reasoning
from packages.resume_core.storage import StorageFailure
from resume_api.providers.content import (ContentFailure, ContentInput, ContentResult, ContentTransportReturn, outcome_state,
                                          ReportedUsage, ResultT)
from resume_api.providers.structured_schema import StructuredSchema
from resume_api.providers.dynamic_result import DynamicResultSpec
from resume_api.providers.preflight import PreflightCache, preflight_key
from resume_api.cli.profile import (FIXTURE_VERSION, GAPS, REQUIRED_FLAGS, check_features, exec_arguments, overrides,
                                     qualify)
from resume_api.cli.qualification import QualificationError, missing_flags


MODEL = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")
MAX_SCHEMA = 65_536
MAX_RESULT = 65_536
MAX_DEPTH = 32
REPAIR_FEEDBACK = "The completed response was invalid JSON or did not match the schema. Return only a valid JSON object matching the schema."
_GENERATION_LOCK = INFERENCE


def strict_json(raw: bytes | str, *, max_bytes: int = MAX_RESULT) -> object:
    try:
        if isinstance(raw, bytes):
            if len(raw) > max_bytes:
                raise ValueError()
            text = raw.decode("utf-8", "strict")
        else:
            text = raw
            if len(text.encode("utf-8", "strict")) > max_bytes:
                raise ValueError()

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            value: dict[str, object] = {}
            for key, item in items:
                if key in value:
                    raise ValueError()
                value[key] = item
            return value

        def number(value: str) -> float:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError()
            return parsed

        value = json.loads(text, object_pairs_hook=pairs, parse_float=number,
                           parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))

        def inspect(item: object, depth: int) -> None:
            if depth > MAX_DEPTH:
                raise ValueError()
            if isinstance(item, str):
                item.encode("utf-8", "strict")
            elif isinstance(item, list):
                for part in item:
                    inspect(part, depth + 1)
            elif isinstance(item, dict):
                for key, part in item.items():
                    inspect(key, depth + 1)
                    inspect(part, depth + 1)

        inspect(value, 0)
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ContentFailure("INVALID_RESULT") from None


def _usage(raw: object) -> ReportedUsage:
    if raw is None:
        return ReportedUsage()
    if not isinstance(raw, dict):
        raise ContentFailure("INVALID_RESULT")
    keys = ("input_tokens", "cached_input_tokens", "output_tokens")
    if any(type(raw.get(key)) is not int or raw[key] < 0 for key in keys):
        raise ContentFailure("INVALID_RESULT")
    return ReportedUsage(raw["input_tokens"], raw["cached_input_tokens"], raw["output_tokens"], True)


def _combine(usages: list[ReportedUsage]) -> ReportedUsage:
    def total(name: str) -> int | None:
        values = [getattr(usage, name) for usage in usages]
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    return ReportedUsage(total("input_tokens"), total("cached_input_tokens"),
                         total("output_tokens"), bool(usages) and all(u.complete for u in usages))


class InvalidFinal(ContentFailure):
    def __init__(self):
        super().__init__("INVALID_RESULT")


class Events:
    def __init__(self, *, max_bytes: int = MAX_RESULT):
        self.max_bytes = max_bytes
        self.thread = False
        self.turn = False
        self.complete = False
        self.text: str | None = None
        self.message_ids: set[str] = set()
        self.usage = ReportedUsage()

    def accept(self, raw: bytes) -> None:
        event = strict_json(raw, max_bytes=self.max_bytes)
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or self.complete:
            raise ContentFailure("INVALID_RESULT")
        kind = event["type"]
        if kind == "thread.started" and not self.thread and not self.turn:
            self.thread = True
        elif kind == "turn.started" and self.thread and not self.turn:
            self.turn = True
        elif kind == "item.completed" and self.thread and isinstance(event.get("item"), dict) and event["item"].get("type") == "error":
            # Exec emits nonfatal warnings as error items, including before the turn.
            if not isinstance(event["item"].get("message"), str):
                raise ContentFailure("INVALID_RESULT")
        elif kind in {"item.started", "item.updated", "item.completed"} and self.turn:
            item = event.get("item")
            if not isinstance(item, dict):
                raise ContentFailure("INVALID_RESULT")
            if item.get("type") not in {"reasoning", "agent_message"}:
                raise ContentFailure("UNEXPECTED_TOOL_ACTIVITY")
            if kind == "item.completed" and item["type"] == "agent_message":
                message_id = item.get("id")
                if not isinstance(message_id, str) or not message_id or message_id in self.message_ids or not isinstance(item.get("text"), str):
                    raise ContentFailure("INVALID_RESULT")
                self.message_ids.add(message_id)
                # The last completed assistant message is the structured final response.
                self.text = item["text"]
        elif kind == "turn.completed" and self.turn and self.text is not None:
            self.usage = _usage(event.get("usage"))
            self.complete = True
        elif kind in {"error", "turn.failed"}:
            detail = event.get("error")
            if not isinstance(detail, dict) and isinstance(event.get("message"), str):
                try:
                    envelope = strict_json(event["message"])
                    detail = envelope.get("error") if isinstance(envelope, dict) else None
                except ContentFailure:
                    detail = None
            code = detail.get("code") if isinstance(detail, dict) else None
            mapped = {"rate_limit_exceeded": "RATE_LIMITED", "authentication_error": "AUTH_REQUIRED",
                      "model_not_supported": "MODEL_DENIED", "invalid_json_schema": "INVALID_SCHEMA"}
            if isinstance(code, str) and code in mapped:
                raise ContentFailure(mapped[code])
            # An exhausted plan comes as plain text with no code ("You've hit your usage limit ..."), D104.
            text = detail.get("message") if isinstance(detail, dict) else event.get("message")
            raise ContentFailure("QUOTA_EXHAUSTED" if isinstance(text, str) and "usage limit" in text.lower() else "CLI_FAILED")
        else:
            raise ContentFailure("INVALID_RESULT")

    def result(self, model: type[ResultT], schema: StructuredSchema,
               decoder: Callable[[object], ResultT] | None = None) -> ResultT:
        if not self.complete or self.text is None:
            raise ContentFailure("INCOMPLETE_STREAM")
        try:
            if model is PlainTextReply:
                if len(self.text.encode()) > self.max_bytes:
                    raise InvalidFinal()
                return PlainTextReply(text=self.text)
            value = strict_json(self.text, max_bytes=self.max_bytes)
            if not isinstance(value, dict):
                raise InvalidFinal()
            if isinstance(model, DynamicResultSpec):
                return model.decode_value(value)
            restored = schema.restore(value, model)
            return model.model_validate(decoder(restored) if decoder else restored, strict=True)
        except (ContentFailure, ValidationError, ValueError):
            raise InvalidFinal() from None


@dataclass(frozen=True)
class Probe:
    version: str
    auth_mode: str
    generation_ready: bool
    gaps: tuple[str, ...]
    reasoning: dict[str, ModelReasoning] = field(default_factory=dict)


@dataclass(frozen=True)
class FixtureTransport:
    """Explicit test-only pairing of a fake executable and fixture version."""
    executable: Path


class CodexCliProvider:
    def __init__(self, executable: Path | None = None, *,
                 fixture_transport: FixtureTransport | None = None,
                 experimental_profile: ExperimentalCliProfile | None = None,
                 clock: Callable[[], float] = time.monotonic):
        resolved = executable or shutil.which("codex")
        if resolved is None:
            raise ContentFailure("CLI_MISSING")
        self.executable = Path(resolved).absolute()
        self.fixture_transport = fixture_transport
        self.experimental_profile = experimental_profile
        self.clock = clock
        self.preflight_cache = PreflightCache[Probe](clock)
        self.model_started = None
        self.process = ProcessRunner(self.executable, clock=clock,
                                     launch=experimental_profile.launch if experimental_profile else None,
                                     workdir=getattr(experimental_profile, "workdir", None))

    def invalidate_preflight(self):
        self.preflight_cache.invalidate()

    def preflight(self, files, cancel, model, *, deadline, effort=None):
        self.process._check(deadline, cancel)
        key = preflight_key(self.executable, self.experimental_profile, self.fixture_transport)
        epoch, cached = self.preflight_cache.read(key, model)
        if cached is not None:
            self.check_effort(cached, model, effort)
            return cached
        probe = self.probe(files, cancel, deadline=deadline)
        if not probe.generation_ready:
            raise ContentFailure("CLI_PROFILE_UNSAFE")
        metadata = {}
        models = self.list_models(files, cancel, deadline=deadline, reasoning=metadata)
        probe = replace(probe, reasoning=metadata)
        if model not in models:
            raise ContentFailure("MODEL_DENIED")
        if key == preflight_key(self.executable, self.experimental_profile, self.fixture_transport):
            self.preflight_cache.remember(epoch, key, probe, models)
        self.check_effort(probe, model, effort)
        return probe

    @staticmethod
    def check_effort(probe, model, effort):
        if effort is not None and (model not in probe.reasoning or effort not in probe.reasoning[model].supported):
            raise ContentFailure("MODEL_DENIED")

    def _run(self, files: OperationFiles, args: tuple[str, ...], deadline: float,
             cancel: threading.Event, *, login_status: bool = False,
             **kwargs: object) -> tuple[bytes, bytes]:
        try:
            return self.process.run(files, args, deadline=deadline, cancel=cancel, **kwargs)
        except ProcessExit as error:
            if login_status and (error.stdout + error.stderr).strip().lower() == b"not logged in":
                raise ContentFailure("AUTH_REQUIRED") from None
            raise ContentFailure("CLI_FAILED") from None
        except SpikeError as error:
            raise ContentFailure(error.code) from None
        except ExperimentalProfileError as error:
            raise ContentFailure(str(error)) from None

    def _config(self, files: OperationFiles) -> list[str]:
        return self.experimental_profile.config(files.path) if self.experimental_profile else overrides(files.path)

    def probe(self, files: OperationFiles, cancel: threading.Event, *, deadline: float | None = None) -> Probe:
        end = deadline if deadline is not None else self.clock() + 15
        version_raw, _ = self._run(files, ("--version",), end, cancel)
        try:
            version = version_raw.decode("utf-8", "strict").strip()
        except UnicodeError:
            raise ContentFailure("CLI_UNSUPPORTED") from None
        try:
            qualify(version)
        except QualificationError:
            raise ContentFailure("CLI_UNSUPPORTED") from None
        help_raw, _ = self._run(files, ("exec", "--help"), end, cancel)
        if missing_flags(help_raw.decode("utf-8", "replace"), REQUIRED_FLAGS):
            raise ContentFailure("CLI_PROFILE_UNSAFE")
        listing, _ = self._run(files, ("features", "list", *self._config(files)), end, cancel)
        try:
            check_features(listing.decode("utf-8", "replace"))
        except QualificationError:
            raise ContentFailure("CLI_PROFILE_UNSAFE") from None
        stdout, stderr = self._run(files, ("login", "status"), end, cancel, login_status=True)
        status = (stdout + stderr).decode("utf-8", "replace").lower()
        if "api key" in status or "api-key" in status:
            raise ContentFailure("AUTH_MODE_MISMATCH")
        if "logged in using chatgpt" not in status:
            raise ContentFailure("AUTH_REQUIRED")
        fixture_ready = (self.fixture_transport is not None
                         and self.fixture_transport.executable.absolute() == self.executable
                         and version == FIXTURE_VERSION)
        experimental_ready = self.experimental_profile is not None
        return Probe(version, "chatgpt", fixture_ready or experimental_ready,
                     () if fixture_ready or experimental_ready else GAPS)

    def list_models(self, files: OperationFiles, cancel: threading.Event, *, deadline: float | None = None, reasoning=None) -> tuple[str, ...]:
        end = deadline if deadline is not None else self.clock() + 15
        state = {"id": 0, "models": ()}

        def request(identifier: int, method: str, params: dict[str, object]) -> bytes:
            return (json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode()

        def accept(raw: bytes) -> bytes | None:
            event = strict_json(raw)
            if not isinstance(event, dict):
                raise ContentFailure("METADATA_FAILED")
            if "method" in event:
                if event.get("method") == "remoteControl/status/changed" and "id" not in event:
                    return None
                if event.get("method") == "account/updated" and "id" not in event:
                    params = event.get("params")
                    if isinstance(params, dict) and params.get("authMode") == "chatgpt":
                        return None
                    raise ContentFailure("AUTH_MODE_MISMATCH")
                raise ContentFailure("METADATA_FAILED")
            if event.get("id") != state["id"] or "error" in event or not isinstance(event.get("result"), dict):
                raise ContentFailure("METADATA_FAILED")
            result = event["result"]
            if state["id"] == 0:
                state["id"] = 1
                return b'{"method":"initialized"}\n' + request(1, "account/read", {"refreshToken": False})
            if state["id"] == 1:
                account = result.get("account")
                if not isinstance(account, dict) or account.get("type") != "chatgpt":
                    raise ContentFailure("AUTH_MODE_MISMATCH")
                state["id"] = 2
                return request(2, "model/list", {"includeHidden": False, "limit": 100})
            if state["id"] != 2 or result.get("nextCursor") is not None:
                raise ContentFailure("METADATA_FAILED")
            values = result.get("data")
            if not isinstance(values, list) or not values:
                raise ContentFailure("METADATA_FAILED")
            models: list[str] = []
            for item in values:
                name = item.get("model") if isinstance(item, dict) else None
                if not isinstance(name, str) or not MODEL.fullmatch(name) or name in models:
                    raise ContentFailure("METADATA_FAILED")
                models.append(name)
                if reasoning is not None:
                    try:
                        reasoning[name] = model_reasoning(item)
                    except ValueError:
                        raise ContentFailure("METADATA_FAILED") from None
            state["models"] = tuple(models)
            state["id"] = 3
            return b""

        if files.path is None:
            raise ContentFailure("TEMP_FAILED")
        config = self._config(files)
        self._run(files, ("app-server", "--strict-config", *config), end, cancel,
                  data=request(0, "initialize", {"clientInfo": {"name": "foldcv", "version": "0.1.0"}}),
                  on_line=accept, interactive=True)
        if state["id"] != 3:
            raise ContentFailure("METADATA_FAILED")
        return state["models"]

    def generate(self, request: ContentInput[ResultT], files: OperationFiles,
                 cancel: threading.Event) -> ContentResult[ResultT]:
        if not _GENERATION_LOCK.acquire(blocking=False):
            raise ContentFailure("PROCESS_CLEANUP_FAILED" if INFERENCE.blocked else "BUSY")
        try:
            with self._profile_owner(cancel, files.root):
                return self._generate(request, files, cancel)
        finally:
            _GENERATION_LOCK.release()

    def generate_queued(self, request: ContentInput[ResultT], files: OperationFiles,
                        cancel: threading.Event, admitted) -> ContentResult[ResultT]:
        try:
            waiting = time.perf_counter()
            with INFERENCE.hold(cancel):
                with self._profile_owner(cancel, files.root):
                    add_phase("account_queue", time.perf_counter() - waiting)
                    admitted()
                    return self._generate(request, files, cancel)
        except AdmissionBlocked:
            raise ContentFailure("PROCESS_CLEANUP_FAILED") from None

    @property
    def native(self):
        return self.fixture_transport is None

    def generate_owned(self, request, files, cancel, permit):
        try:
            with permit.hold(cancel):
                # Model calls share the profile, so import blocks and other model work run at once (CT10, D120).
                with self._profile_owner(cancel, files.root):
                    return self._generate(request, files, cancel)
        except AdmissionBlocked:
            raise ContentFailure("PROCESS_CLEANUP_FAILED") from None

    @contextmanager
    def _profile_owner(self, cancel, operations_root):
        try:
            with native_profile(self.experimental_profile, cancel, deadline=time.monotonic() + 30,
                    operations_root=operations_root, shared=True):
                yield
        except AdmissionBlocked:
            INFERENCE.block()
            raise ContentFailure("PROCESS_CLEANUP_FAILED") from None
        except AdmissionTimeout:
            raise ContentFailure("BUSY") from None
        except (StorageFailure, ExperimentalProfileError, OSError):
            raise ContentFailure("CLI_PROFILE_UNSAFE") from None

    def _generate(self, request: ContentInput[ResultT], files: OperationFiles,
                  cancel: threading.Event) -> ContentResult[ResultT]:
        start = self.clock()
        policy = request.policy
        if not MODEL.fullmatch(policy.model):
            raise ContentFailure("MODEL_DENIED")
        if not isinstance(request.text, str) or not request.text:
            raise ContentFailure("INVALID_INPUT")
        try:
            text = request.transport.encode(request.text) if request.transport else request.text
            original = text.encode("utf-8", "strict")
        except (UnicodeError, ValueError, TypeError):
            raise ContentFailure("INVALID_INPUT") from None
        if len(original) > policy.max_input_bytes:
            raise ContentFailure("INPUT_TOO_LARGE")
        dynamic = isinstance(request.result_type, DynamicResultSpec)
        if dynamic and (policy.allow_repair or request.transport is not None):
            raise ContentFailure("INVALID_INPUT")
        if request.on_return is not None and policy.allow_repair:
            raise ContentFailure('INVALID_INPUT')
        if not dynamic and (not isinstance(request.result_type, type) or not issubclass(request.result_type, BaseModel)
                or request.result_type.model_config.get("extra") != "forbid"):
            raise ContentFailure("INVALID_SCHEMA")
        try:
            plain = request.result_type is PlainTextReply
            result_schema = request.result_type.provider_schema if dynamic else request.result_type.model_json_schema()
            if request.transport is not None and hasattr(request.transport, "output_schema"):
                result_schema = request.transport.output_schema(result_schema)
            output_schema = StructuredSchema(result_schema)
            schema = json.dumps(output_schema.wire, ensure_ascii=False,
                                allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, KeyError, RecursionError):
            raise ContentFailure("INVALID_SCHEMA") from None
        if len(schema) > MAX_SCHEMA:
            raise ContentFailure("INVALID_SCHEMA")
        deadline = start + policy.timeout_seconds
        if request.transport and hasattr(request.transport, "bind_guard"):
            request.transport.bind_guard(lambda: self.process._check(deadline, cancel))
        attempts = 0
        usages: list[ReportedUsage] = []
        consumed_input = 0
        consumed_output = 0
        dispatch_witness = None
        effective_effort = policy.reasoning_effort
        raw_return, return_sent = None, False
        def observed(outcome, code=None):
            nonlocal return_sent
            if request.on_return is not None and not return_sent:
                return_sent = True
                request.on_return(ContentTransportReturn(raw_return, outcome, code, attempts, _combine(usages),
                    not files.cleanup_failed and files.process is None, dispatch_witness, effective_effort))
        try:
            with measure("preflight"):
                probe = self.preflight(files, cancel, policy.model, deadline=deadline, effort=policy.reasoning_effort)
            if dynamic and effective_effort is None:
                metadata = probe.reasoning.get(policy.model)
                if metadata is None or metadata.default not in metadata.supported:
                    raise ContentFailure("MODEL_DENIED")
                effective_effort = metadata.default
            if files.path is None:
                raise ContentFailure("TEMP_FAILED")
            if not plain:
                (files.path / "schema.json").write_bytes(schema)
            attempt_limit = 2 if policy.allow_repair and not plain else 1
            for index in range(attempt_limit):
                self.process._check(deadline, cancel)
                prompt = original if index == 0 else original + b"\n\n" + REPAIR_FEEDBACK.encode()
                consumed_input += len(prompt)
                if len(prompt) > policy.max_input_bytes or consumed_input > policy.max_total_input_bytes:
                    raise ContentFailure("BUDGET_EXCEEDED")
                if consumed_output >= policy.max_total_output_bytes:
                    raise ContentFailure("BUDGET_EXCEEDED")
                events = Events(max_bytes=policy.max_total_output_bytes - consumed_output)
                attempts += 1
                try:
                    try:
                        args = (self.experimental_profile.exec_arguments(files.path, policy.model)
                                if self.experimental_profile else tuple(exec_arguments(files.path, policy.model)))
                        if plain:
                            at = args.index("--output-schema")
                            args = args[:at] + args[at + 2:]
                        if effective_effort is not None:
                            args = (*args[:-1], "--config", "model_reasoning_effort=" + json.dumps(effective_effort), args[-1])
                        began, active = time.perf_counter(), None
                        def spawned():
                            nonlocal dispatch_witness
                            dispatch_witness = {"transport":"exec", "dispatched":True,
                                "pid":files.process.pid if files.process is not None else None}
                            if self.model_started is not None: self.model_started()
                        def accept(raw):
                            nonlocal active
                            events.accept(raw)
                            now = time.perf_counter()
                            if events.turn and active is None:
                                active = now
                                add_phase("cli_startup", now - began)
                            if events.complete and active is not None:
                                add_phase("model_turn", now - active)
                        with measure("cli_process"):
                            output, errors = self._run(files, args, deadline, cancel,
                                                       data=prompt, on_line=accept,
                                                       on_spawn=spawned,
                                                       max_line=policy.max_total_output_bytes - consumed_output,
                                                       max_output=policy.max_total_output_bytes - consumed_output)
                    finally:
                        usages.append(events.usage)
                        raw_return = events.text
                    consumed_output += len(output) + len(errors)
                    observed('completed' if events.complete else 'incomplete')
                    with measure("decode"):
                        value = events.result(request.result_type, output_schema, getattr(request.transport, "decode", None))
                    if request.transport:
                        try:
                            value = request.result_type.model_validate(request.transport.restore(value), strict=True)
                        except (ValidationError, ValueError):
                            raise InvalidFinal() from None
                    self.process._check(deadline, cancel)
                    return ContentResult(value, _combine(usages), probe.version, policy.model,
                                         self.clock() - start, attempts, cleanup_verified=not files.cleanup_failed and files.process is None,
                                         dispatch_witness=dispatch_witness, reasoning_effort=effective_effort, raw_return=raw_return)
                except InvalidFinal:
                    if index == attempt_limit - 1:
                        raise
            raise ContentFailure("INVALID_RESULT")
        except SpikeError as error:
            observed(outcome_state(error.code), error.code)
            raise ContentFailure(error.code, logical_attempts=attempts, usage=_combine(usages),
                cleanup_verified=not files.cleanup_failed and files.process is None, dispatch_witness=dispatch_witness, raw_return=raw_return) from None
        except OSError:
            observed('transport_failure', 'TEMP_FAILED')
            raise ContentFailure("TEMP_FAILED", logical_attempts=attempts, usage=_combine(usages),
                cleanup_verified=not files.cleanup_failed and files.process is None, dispatch_witness=dispatch_witness, raw_return=raw_return) from None
        except ContentFailure as error:
            observed(outcome_state(error.code), error.code)
            if error.code in {"AUTH_REQUIRED", "AUTH_MODE_MISMATCH", "MODEL_DENIED", "CLI_UNSUPPORTED",
                    "CLI_PROFILE_UNSAFE", "CLI_FAILED", "METADATA_FAILED", "PROCESS_CLEANUP_FAILED", "QUOTA_EXHAUSTED"}:
                self.invalidate_preflight()
            raise ContentFailure(error.code, logical_attempts=attempts, usage=_combine(usages),
                cleanup_verified=not files.cleanup_failed and files.process is None, dispatch_witness=dispatch_witness, raw_return=raw_return) from None
        except Exception:
            observed('transport_failure', 'CLI_FAILED')
            raise ContentFailure("CLI_FAILED", logical_attempts=attempts, usage=_combine(usages),
                cleanup_verified=not files.cleanup_failed and files.process is None, dispatch_witness=dispatch_witness, raw_return=raw_return) from None
