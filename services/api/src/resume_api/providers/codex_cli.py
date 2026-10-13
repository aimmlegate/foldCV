"""Versioned Codex CLI adapter. Real generation remains closed by D004."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Callable

from pydantic import BaseModel, ValidationError

from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.cli.experimental_profile import ExperimentalCliProfile, ExperimentalProfileError, VERSION as EXPERIMENTAL_VERSION
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.providers.content import (ContentFailure, ContentInput, ContentResult,
                                          ReportedUsage, ResultT)
from spikes.cli.profile import FIXTURE_VERSION, GAPS, REQUIRED_FLAGS, VERSION, exec_arguments, overrides


MODEL = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")
MAX_SCHEMA = 65_536
MAX_RESULT = 65_536
MAX_DEPTH = 32
REPAIR_FEEDBACK = "The completed response was invalid JSON or did not match the schema. Return only a valid JSON object matching the schema."
_GENERATION_LOCK = threading.Lock()


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
    def __init__(self):
        self.thread = False
        self.turn = False
        self.complete = False
        self.text: str | None = None
        self.message_ids: set[str] = set()
        self.usage = ReportedUsage()

    def accept(self, raw: bytes) -> None:
        event = strict_json(raw)
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
            code = detail.get("code") if isinstance(detail, dict) else None
            mapped = {"rate_limit_exceeded": "RATE_LIMITED", "authentication_error": "AUTH_REQUIRED",
                      "model_not_supported": "MODEL_DENIED"}
            raise ContentFailure(mapped.get(code, "CLI_FAILED") if isinstance(code, str) else "CLI_FAILED")
        else:
            raise ContentFailure("INVALID_RESULT")

    def result(self, model: type[ResultT]) -> ResultT:
        if not self.complete or self.text is None:
            raise ContentFailure("INCOMPLETE_STREAM")
        try:
            value = strict_json(self.text)
            if not isinstance(value, dict):
                raise InvalidFinal()
            return model.model_validate(value, strict=True)
        except (ContentFailure, ValidationError, ValueError):
            raise InvalidFinal() from None


@dataclass(frozen=True)
class Probe:
    version: str
    auth_mode: str
    generation_ready: bool
    gaps: tuple[str, ...]


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
        self.process = ProcessRunner(self.executable, clock=clock,
                                     launch=experimental_profile.launch if experimental_profile else None)

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

    def probe(self, files: OperationFiles, cancel: threading.Event, *, deadline: float | None = None) -> Probe:
        end = deadline if deadline is not None else self.clock() + 15
        version_raw, _ = self._run(files, ("--version",), end, cancel)
        try:
            version = version_raw.decode("utf-8", "strict").strip()
        except UnicodeError:
            raise ContentFailure("CLI_UNSUPPORTED") from None
        expected = {EXPERIMENTAL_VERSION} if self.experimental_profile else {VERSION, FIXTURE_VERSION}
        if version not in expected:
            raise ContentFailure("CLI_UNSUPPORTED")
        help_raw, _ = self._run(files, ("exec", "--help"), end, cancel)
        if any(flag.encode() not in help_raw for flag in REQUIRED_FLAGS):
            raise ContentFailure("CLI_PROFILE_UNSAFE")
        stdout, stderr = self._run(files, ("login", "status"), end, cancel, login_status=True)
        status = (stdout + stderr).decode("utf-8", "replace").lower()
        if "api key" in status or "api-key" in status:
            raise ContentFailure("AUTH_MODE_MISMATCH")
        if "logged in using chatgpt" not in status:
            raise ContentFailure("AUTH_REQUIRED")
        fixture_ready = (self.fixture_transport is not None
                         and self.fixture_transport.executable.absolute() == self.executable
                         and version == FIXTURE_VERSION)
        experimental_ready = self.experimental_profile is not None and version == EXPERIMENTAL_VERSION
        return Probe(version, "chatgpt", fixture_ready or experimental_ready,
                     () if fixture_ready or experimental_ready else GAPS)

    def list_models(self, files: OperationFiles, cancel: threading.Event, *, deadline: float | None = None) -> tuple[str, ...]:
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
            state["models"] = tuple(models)
            state["id"] = 3
            return b""

        if files.path is None:
            raise ContentFailure("TEMP_FAILED")
        config = (self.experimental_profile.config(files.path) if self.experimental_profile
                  else overrides(files.path))
        self._run(files, ("app-server", "--strict-config", *config), end, cancel,
                  data=request(0, "initialize", {"clientInfo": {"name": "foldcv", "version": "0.1.0"}}),
                  on_line=accept, interactive=True)
        if state["id"] != 3:
            raise ContentFailure("METADATA_FAILED")
        return state["models"]

    def generate(self, request: ContentInput[ResultT], files: OperationFiles,
                 cancel: threading.Event) -> ContentResult[ResultT]:
        if not _GENERATION_LOCK.acquire(blocking=False):
            raise ContentFailure("BUSY")
        try:
            return self._generate(request, files, cancel)
        finally:
            _GENERATION_LOCK.release()

    def generate_queued(self, request: ContentInput[ResultT], files: OperationFiles,
                        cancel: threading.Event, admitted) -> ContentResult[ResultT]:
        while not _GENERATION_LOCK.acquire(timeout=0.025):
            if cancel.is_set():
                from ..gui_admission import AdmissionCancelled
                raise AdmissionCancelled()
        try:
            if cancel.is_set():
                from ..gui_admission import AdmissionCancelled
                raise AdmissionCancelled()
            admitted()
            return self._generate(request, files, cancel)
        finally:
            _GENERATION_LOCK.release()

    def _generate(self, request: ContentInput[ResultT], files: OperationFiles,
                  cancel: threading.Event) -> ContentResult[ResultT]:
        start = self.clock()
        policy = request.policy
        if not MODEL.fullmatch(policy.model):
            raise ContentFailure("MODEL_DENIED")
        if not isinstance(request.text, str) or not request.text:
            raise ContentFailure("INVALID_INPUT")
        try:
            original = request.text.encode("utf-8", "strict")
        except UnicodeError:
            raise ContentFailure("INVALID_INPUT") from None
        if len(original) > policy.max_input_bytes:
            raise ContentFailure("INPUT_TOO_LARGE")
        if (not isinstance(request.result_type, type) or not issubclass(request.result_type, BaseModel)
                or request.result_type.model_config.get("extra") != "forbid"):
            raise ContentFailure("INVALID_SCHEMA")
        try:
            schema = json.dumps(request.result_type.model_json_schema(), ensure_ascii=False,
                                allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, UnicodeError):
            raise ContentFailure("INVALID_SCHEMA") from None
        if len(schema) > MAX_SCHEMA:
            raise ContentFailure("INVALID_SCHEMA")
        deadline = start + policy.timeout_seconds
        attempts = 0
        usages: list[ReportedUsage] = []
        consumed_input = 0
        consumed_output = 0
        try:
            probe = self.probe(files, cancel, deadline=deadline)
            if not probe.generation_ready:
                raise ContentFailure("CLI_PROFILE_UNSAFE")
            if policy.model not in self.list_models(files, cancel, deadline=deadline):
                raise ContentFailure("MODEL_DENIED")
            if files.path is None:
                raise ContentFailure("TEMP_FAILED")
            (files.path / "schema.json").write_bytes(schema)
            attempt_limit = 2 if policy.allow_repair else 1
            for index in range(attempt_limit):
                self.process._check(deadline, cancel)
                prompt = original if index == 0 else original + b"\n\n" + REPAIR_FEEDBACK.encode()
                consumed_input += len(prompt)
                if len(prompt) > policy.max_input_bytes or consumed_input > policy.max_total_input_bytes:
                    raise ContentFailure("BUDGET_EXCEEDED")
                if consumed_output >= policy.max_total_output_bytes:
                    raise ContentFailure("BUDGET_EXCEEDED")
                events = Events()
                attempts += 1
                try:
                    try:
                        args = (self.experimental_profile.exec_arguments(files.path, policy.model)
                                if self.experimental_profile else tuple(exec_arguments(files.path, policy.model)))
                        output, errors = self._run(files, args, deadline, cancel,
                                                   data=prompt, on_line=events.accept,
                                                   max_output=policy.max_total_output_bytes - consumed_output)
                    finally:
                        usages.append(events.usage)
                    consumed_output += len(output) + len(errors)
                    value = events.result(request.result_type)
                    self.process._check(deadline, cancel)
                    return ContentResult(value, _combine(usages), probe.version, policy.model,
                                         self.clock() - start, attempts)
                except InvalidFinal:
                    if index == attempt_limit - 1:
                        raise
            raise ContentFailure("INVALID_RESULT")
        except SpikeError as error:
            raise ContentFailure(error.code, logical_attempts=attempts, usage=_combine(usages)) from None
        except OSError:
            raise ContentFailure("TEMP_FAILED", logical_attempts=attempts, usage=_combine(usages)) from None
        except ContentFailure as error:
            raise ContentFailure(error.code, logical_attempts=attempts, usage=_combine(usages)) from None
