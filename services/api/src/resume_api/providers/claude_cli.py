"""Claude Code CLI adapter for structured generation (MP02); same boundary and repair rule as Codex."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import json
import logging
from pathlib import Path
import shutil
import threading
import time
from typing import Callable

from pydantic import BaseModel, ValidationError

from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.storage import StorageFailure
from packages.resume_core.text_rewrite import PlainTextReply
from resume_api.cli import qualification
from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.cli.profiles import claude as profile_rules
from resume_api.cli.profiles.claude import ClaudeCliProfile, ClaudeProfileError
from resume_api.inference_admission import INFERENCE, AdmissionBlocked, AdmissionTimeout
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.profile_ownership import native_profile
from resume_api.providers import claude_catalog
from resume_api.providers.codex_cli import MAX_SCHEMA, MODEL, REPAIR_FEEDBACK, InvalidFinal, _combine, strict_json
from resume_api.providers.content import (ContentFailure, ContentInput, ContentResult, ContentTransportReturn,
                                          ReportedUsage, ResultT, outcome_state)
from resume_api.providers.dynamic_result import DynamicResultSpec
from resume_api.providers.preflight import QUALIFICATION_SECONDS, PreflightCache, _stamp
from resume_api.providers.structured_schema import StructuredSchema
from resume_api.rewrite_timing import add_phase, measure


_GENERATION_LOCK = INFERENCE
KEY_MODES = {"api_key", "api_key_helper", "oauth_token", "third_party"}
# Observed or documented assistant error kinds; anything else is a plain CLI failure.
ERRORS = {"authentication_failed": "AUTH_REQUIRED", "billing_error": "QUOTA_EXHAUSTED",
          "rate_limit": "RATE_LIMITED", "model_not_found": "MODEL_DENIED", "invalid_request": "CLI_FAILED",
          "overloaded": "CLI_FAILED", "server_error": "CLI_FAILED"}
# Notices that carry no model output; compaction and permission denials are never expected.
# `thinking_tokens` reports thinking progress; 2.1.308 sends it once a turn thinks for a while (MP05-2).
NOTICES = {"api_retry", "status", "rate_limit_event", "thinking_tokens"}
FORBIDDEN = {"compact_boundary", "permission_denied"}
LOG = logging.getLogger(__name__)


def _unknown(label: str) -> ContentFailure:
    # Names only the event kind, never its content: a new CLI event is otherwise just INVALID_RESULT.
    LOG.warning("Claude stream event refused: %s", label)
    return ContentFailure("INVALID_RESULT")


def _usage(raw: object) -> ReportedUsage:
    if not isinstance(raw, dict):
        return ReportedUsage()
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
    if any(type(raw.get(key, 0)) is not int or raw.get(key, 0) < 0 for key in keys):
        raise ContentFailure("INVALID_RESULT")
    cached = raw.get("cache_read_input_tokens", 0)
    total = raw.get("input_tokens", 0) + raw.get("cache_creation_input_tokens", 0) + cached
    return ReportedUsage(total, cached, raw.get("output_tokens", 0), "input_tokens" in raw and "output_tokens" in raw)


class ClaudeEvents:
    """Strict reader of one `-p --output-format stream-json --verbose` run."""

    def __init__(self, *, model: str, version: str, structured: bool, max_bytes: int,
                 check: Callable[[dict], None] | None = None):
        self.model, self.version, self.structured, self.max_bytes = model, version, structured, max_bytes
        self.check = check
        self.started = False
        self.complete = False
        self.text: str | None = None
        self.value: object = None
        self.usage = ReportedUsage()
        self.tool_ids: set[str] = set()
        self.error: str | None = None
        self.output = False

    @property
    def renewal(self) -> bool:
        """The run failed sign-in before any model output: the CLI renewed an expired sign-in in it (MP05)."""
        return self.error == "authentication_failed" and not self.output

    def accept(self, raw: bytes) -> None:
        event = strict_json(raw, max_bytes=self.max_bytes)
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or self.complete:
            raise ContentFailure("INVALID_RESULT")
        kind, subtype = event["type"], event.get("subtype")
        if kind == "system" and subtype == "init" and not self.started:
            try:
                if self.check is not None:
                    self.check(event)
                else:
                    profile_rules.check_init(event, model=self.model, version=self.version,
                                             tools=profile_rules.STRUCTURED_TOOLS if self.structured else ())
            except ClaudeProfileError as error:
                raise ContentFailure(error.code) from None
            self.started = True
        elif not self.started:
            raise ContentFailure("INVALID_RESULT")
        elif kind == "system" and subtype in FORBIDDEN:
            raise ContentFailure("UNEXPECTED_TOOL_ACTIVITY")
        elif kind in {"system", "rate_limit_event"}:
            if kind == "system" and subtype not in NOTICES:
                raise _unknown(f"system/{subtype}")
        elif kind == "assistant":
            self._assistant(event)
        elif kind == "user":
            self._user(event)
        elif kind == "result":
            self._result(event)
        else:
            raise _unknown(kind)

    def _assistant(self, event: dict) -> None:
        message = event.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            raise ContentFailure("INVALID_RESULT")
        if event.get("parent_tool_use_id") is not None:
            raise ContentFailure("UNEXPECTED_TOOL_ACTIVITY")
        if isinstance(event.get("error"), str):
            self.error = event["error"]
        else:
            self.output = True
        for block in message["content"]:
            kind = block.get("type") if isinstance(block, dict) else None
            if kind == "tool_use":
                identifier = block.get("id")
                if (not self.structured or block.get("name") not in profile_rules.STRUCTURED_TOOLS
                        or not isinstance(identifier, str)):
                    raise ContentFailure("UNEXPECTED_TOOL_ACTIVITY")
                self.tool_ids.add(identifier)
            elif kind not in {"text", "thinking", "redacted_thinking"}:
                raise _unknown(f"assistant block {kind}")

    def _user(self, event: dict) -> None:
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list) or event.get("parent_tool_use_id") is not None:
            raise ContentFailure("INVALID_RESULT")
        for block in content:
            # Only results of the CLI's own schema validation come back as user turns.
            if (not isinstance(block, dict) or block.get("type") != "tool_result"
                    or block.get("tool_use_id") not in self.tool_ids):
                raise ContentFailure("UNEXPECTED_TOOL_ACTIVITY")

    def _result(self, event: dict) -> None:
        self.usage = _usage(event.get("usage"))
        if event.get("permission_denials"):
            raise ContentFailure("UNEXPECTED_TOOL_ACTIVITY")
        subtype, failed = event.get("subtype"), event.get("is_error")
        text = event.get("result") if isinstance(event.get("result"), str) else ""
        if subtype in {"error_max_structured_output_retries", "error_max_turns"}:
            raise ContentFailure("INVALID_RESULT")
        if subtype != "success" or type(failed) is not bool:
            raise ContentFailure("CLI_FAILED")
        if failed:
            code = ERRORS.get(self.error or "", "CLI_FAILED")
            lowered = text.lower()
            if code == "RATE_LIMITED" and ("usage limit" in lowered or "hit your" in lowered):
                code = "QUOTA_EXHAUSTED"
            if self.error is None and "not logged in" in lowered:
                code = "AUTH_REQUIRED"
            raise ContentFailure(code)
        if self.structured:
            value = event.get("structured_output")
            if not isinstance(value, dict):
                raise InvalidFinal()
            self.value = value
            self.text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            if not isinstance(event.get("result"), str):
                raise InvalidFinal()
            self.text = event["result"]
        self.complete = True

    def result(self, model: type[ResultT], schema: StructuredSchema,
               decoder: Callable[[object], ResultT] | None = None) -> ResultT:
        if not self.complete or self.text is None:
            raise ContentFailure("INCOMPLETE_STREAM")
        try:
            if model is PlainTextReply:
                if len(self.text.encode()) > self.max_bytes:
                    raise InvalidFinal()
                return PlainTextReply(text=self.text)
            # Re-read through the strict decoder: duplicate keys, depth and size limits as for Codex.
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
    status: qualification.Status
    auth_mode: str
    plan: str | None
    generation_ready: bool
    reasoning: dict[str, ModelReasoning] = field(default_factory=dict)


@dataclass(frozen=True)
class FixtureTransport:
    """Explicit test-only pairing with a fake executable: no sandbox and no signature check."""
    executable: Path


def startup_failure(stderr: bytes) -> str:
    text = stderr.decode("utf-8", "replace").lower()
    if "is not a valid json schema" in text:
        return "INVALID_SCHEMA"
    if "unknown option" in text or "unknown argument" in text:
        return "CLI_PROFILE_UNSAFE"
    return "CLI_FAILED"


class ClaudeCliProvider:
    template_adapter = profile_rules.KIND

    def __init__(self, executable: Path | None = None, *, profile: ClaudeCliProfile | None = None,
                 fixture_transport: FixtureTransport | None = None,
                 clock: Callable[[], float] = time.monotonic):
        resolved = executable or (profile.executable if profile else None) or shutil.which("claude")
        if resolved is None:
            raise ContentFailure("CLI_MISSING")
        self.executable = Path(resolved).absolute()
        self.profile = profile
        self.fixture_transport = fixture_transport
        self.clock = clock
        self.preflight_cache = PreflightCache[Probe](clock)
        self.model_started = None
        self.process = ProcessRunner(self.executable, clock=clock, launch=profile.launch if profile else None)

    @property
    def native(self) -> bool:
        return self.fixture_transport is None

    def invalidate_preflight(self) -> None:
        self.preflight_cache.invalidate()

    def _key(self):
        try:
            config = self.profile.config_dir if self.profile else None
            return (str(self.executable), _stamp(self.executable), str(config),
                    _stamp(config / ".credentials.json") if config else None,
                    str(self.fixture_transport.executable) if self.fixture_transport else None)
        except OSError:
            return None

    def _run(self, files: OperationFiles, args: tuple[str, ...], deadline: float, cancel: threading.Event,
             **kwargs: object) -> tuple[bytes, bytes]:
        try:
            return self.process.run(files, args, deadline=deadline, cancel=cancel, **kwargs)
        except ProcessExit:
            raise
        except SpikeError as error:
            raise ContentFailure(error.code) from None
        except ClaudeProfileError as error:
            raise ContentFailure(error.code) from None

    def probe(self, files: OperationFiles, cancel: threading.Event, *, deadline: float | None = None) -> Probe:
        end = deadline if deadline is not None else self.clock() + QUALIFICATION_SECONDS
        fixture = self.fixture_transport is not None and self.fixture_transport.executable.absolute() == self.executable
        if not fixture:
            if self.profile is None:
                raise ContentFailure("CLI_PROFILE_UNSAFE")
            try:
                qualification.require_publisher(self.executable, profile_rules.TEAM_ID, profile_rules.IDENTIFIER)
            except qualification.QualificationError as error:
                raise ContentFailure(error.code) from None
        try:
            raw, _ = self._run(files, ("--version",), end, cancel)
            version = qualification.Version.parse(raw.decode("utf-8", "strict"))
            raw_help, _ = self._run(files, ("--help",), end, cancel)
        except (ProcessExit, UnicodeError, qualification.QualificationError):
            raise ContentFailure("CLI_UNSUPPORTED") from None
        status = profile_rules.COMPATIBILITY.status(version)
        if status in {"unsupported", "broken"}:
            raise ContentFailure("CLI_UNSUPPORTED")
        if qualification.missing_flags(raw_help.decode("utf-8", "replace"), profile_rules.REQUIRED_FLAGS):
            raise ContentFailure("CLI_PROFILE_UNSAFE")
        try:
            stdout, _ = self._run(files, ("auth", "status", "--json"), end, cancel)
        except ProcessExit as error:
            stdout = error.stdout  # exit 1 means signed out; the body still says why
        try:
            body = strict_json(stdout)
        except ContentFailure:
            raise ContentFailure("METADATA_FAILED") from None
        if not isinstance(body, dict) or type(body.get("loggedIn")) is not bool:
            raise ContentFailure("METADATA_FAILED")
        method = body.get("authMethod")
        if method in KEY_MODES or body.get("loggedIn") and method != profile_rules.ACCEPTED_AUTH:
            raise ContentFailure("AUTH_MODE_MISMATCH")
        if not body["loggedIn"]:
            raise ContentFailure("AUTH_REQUIRED")
        configured = body.get("configDirectory")
        if self.profile is not None and (not isinstance(configured, str)
                                         or Path(configured).resolve() != self.profile.config_dir.resolve()):
            raise ContentFailure("CLI_PROFILE_UNSAFE")
        plan = body.get("subscriptionType") if isinstance(body.get("subscriptionType"), str) else None
        return Probe(str(version), status, method, plan, True, claude_catalog.reasoning_for(version))

    def preflight(self, files, cancel, model, *, deadline, effort=None) -> Probe:
        self.process._check(deadline, cancel)
        key = self._key()
        epoch, cached = self.preflight_cache.read(key, model)
        if cached is not None:
            self.check_effort(cached, model, effort)
            return cached
        probe = self.probe(files, cancel, deadline=min(deadline, self.clock() + QUALIFICATION_SECONDS))
        if model not in probe.reasoning:
            raise ContentFailure("MODEL_DENIED")
        if key == self._key():
            self.preflight_cache.remember(epoch, key, probe, tuple(probe.reasoning))
        self.check_effort(probe, model, effort)
        return probe

    @staticmethod
    def check_effort(probe: Probe, model: str, effort: str | None) -> None:
        if effort is not None and (model not in probe.reasoning or effort not in probe.reasoning[model].supported):
            raise ContentFailure("MODEL_DENIED")

    def generate(self, request: ContentInput[ResultT], files: OperationFiles,
                 cancel: threading.Event) -> ContentResult[ResultT]:
        if not _GENERATION_LOCK.acquire(blocking=False):
            raise ContentFailure("PROCESS_CLEANUP_FAILED" if INFERENCE.blocked else "BUSY")
        try:
            with self._profile_owner(cancel, files.root):
                return self._generate(request, files, cancel)
        finally:
            _GENERATION_LOCK.release()

    def generate_queued(self, request, files, cancel, admitted):
        try:
            waiting = time.perf_counter()
            with INFERENCE.hold(cancel):
                with self._profile_owner(cancel, files.root):
                    add_phase("account_queue", time.perf_counter() - waiting)
                    admitted()
                    return self._generate(request, files, cancel)
        except AdmissionBlocked:
            raise ContentFailure("PROCESS_CLEANUP_FAILED") from None

    def generate_owned(self, request, files, cancel, permit):
        try:
            with permit.hold(cancel):
                with self._profile_owner(cancel, files.root):
                    return self._generate(request, files, cancel)
        except AdmissionBlocked:
            raise ContentFailure("PROCESS_CLEANUP_FAILED") from None

    @contextmanager
    def _profile_owner(self, cancel, operations_root):
        # Model calls share the profile (D121); sessions, caches and logs go once the last of them ends.
        wipe = self.profile.wipe if self.profile is not None else None
        try:
            with native_profile(self.profile, cancel, deadline=time.monotonic() + 30,
                                operations_root=operations_root, shared=True, cleanup=wipe):
                yield
        except AdmissionBlocked:
            INFERENCE.block()
            raise ContentFailure("PROCESS_CLEANUP_FAILED") from None
        except AdmissionTimeout:
            raise ContentFailure("BUSY") from None
        except (StorageFailure, ClaudeProfileError, OSError):
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
            raise ContentFailure("INVALID_INPUT")
        if not dynamic and (not isinstance(request.result_type, type) or not issubclass(request.result_type, BaseModel)
                            or request.result_type.model_config.get("extra") != "forbid"):
            raise ContentFailure("INVALID_SCHEMA")
        try:
            plain = request.result_type is PlainTextReply
            result_schema = request.result_type.provider_schema if dynamic else request.result_type.model_json_schema()
            if request.transport is not None and hasattr(request.transport, "output_schema"):
                result_schema = request.transport.output_schema(result_schema)
            output_schema = StructuredSchema(result_schema)
            schema = json.dumps(output_schema.wire, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except (ValueError, TypeError, UnicodeError, KeyError, RecursionError):
            raise ContentFailure("INVALID_SCHEMA") from None
        if len(schema.encode("utf-8")) > MAX_SCHEMA:
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

        def failure(code: str) -> ContentFailure:
            return ContentFailure(code, logical_attempts=attempts, usage=_combine(usages),
                                  cleanup_verified=not files.cleanup_failed and files.process is None,
                                  dispatch_witness=dispatch_witness, raw_return=raw_return)

        try:
            with measure("preflight"):
                probe = self.preflight(files, cancel, policy.model, deadline=deadline, effort=policy.reasoning_effort)
            if dynamic and effective_effort is None:
                metadata = probe.reasoning.get(policy.model)
                if metadata is None:
                    raise ContentFailure("MODEL_DENIED")
                effective_effort = metadata.default
            if files.path is None:
                raise ContentFailure("TEMP_FAILED")
            attempt_limit = 2 if policy.allow_repair and not plain else 1
            # The run that renews an expired sign-in ends "Not logged in" before any model call, and the
            # renewal is saved (MP05 finding 3): one more run follows, never counted as a repair.
            renew, index = True, 0
            while index < attempt_limit:
                self.process._check(deadline, cancel)
                prompt = original if index == 0 else original + b"\n\n" + REPAIR_FEEDBACK.encode()
                consumed_input += len(prompt)
                if len(prompt) > policy.max_input_bytes or consumed_input > policy.max_total_input_bytes:
                    raise ContentFailure("BUDGET_EXCEEDED")
                if consumed_output >= policy.max_total_output_bytes:
                    raise ContentFailure("BUDGET_EXCEEDED")
                events = ClaudeEvents(model=policy.model, version=probe.version, structured=not plain,
                                      max_bytes=policy.max_total_output_bytes - consumed_output)
                attempts += 1
                try:
                    try:
                        args = profile_rules.structured_arguments(None if plain else schema, policy.model,
                                                                  effective_effort)
                        began, active = time.perf_counter(), None

                        def spawned():
                            nonlocal dispatch_witness
                            dispatch_witness = {"transport": "print", "dispatched": True,
                                                "pid": files.process.pid if files.process is not None else None}
                            if self.model_started is not None:
                                self.model_started()

                        def accept(raw):
                            nonlocal active
                            events.accept(raw)
                            now = time.perf_counter()
                            if events.started and active is None:
                                active = now
                                add_phase("cli_startup", now - began)
                            if events.complete and active is not None:
                                add_phase("model_turn", now - active)

                        with measure("cli_process"):
                            try:
                                output, errors = self._run(files, args, deadline, cancel, data=prompt,
                                                           on_line=accept, on_spawn=spawned,
                                                           max_line=policy.max_total_output_bytes - consumed_output,
                                                           max_output=policy.max_total_output_bytes - consumed_output)
                            except ProcessExit as error:
                                if events.complete or not events.started:
                                    raise ContentFailure(startup_failure(error.stderr)
                                                         if not events.started else "CLI_FAILED") from None
                                raise ContentFailure("INCOMPLETE_STREAM") from None
                    finally:
                        usages.append(events.usage)
                        raw_return = events.text
                    consumed_output += len(output) + len(errors)
                    observed("completed" if events.complete else "incomplete")
                    with measure("decode"):
                        value = events.result(request.result_type, output_schema,
                                              getattr(request.transport, "decode", None))
                    if request.transport:
                        try:
                            value = request.result_type.model_validate(request.transport.restore(value), strict=True)
                        except (ValidationError, ValueError):
                            raise InvalidFinal() from None
                    self.process._check(deadline, cancel)
                    return ContentResult(value, _combine(usages), probe.version, policy.model, self.clock() - start,
                                         attempts, cleanup_verified=not files.cleanup_failed and files.process is None,
                                         dispatch_witness=dispatch_witness, reasoning_effort=effective_effort,
                                         raw_return=raw_return)
                except InvalidFinal:
                    if index == attempt_limit - 1:
                        raise
                except ContentFailure as error:
                    if error.code != "AUTH_REQUIRED" or not renew or not events.renewal:
                        raise
                    renew = False
                    consumed_input -= len(prompt)
                    continue
                index += 1
            raise ContentFailure("INVALID_RESULT")
        except SpikeError as error:
            observed(outcome_state(error.code), error.code)
            raise failure(error.code) from None
        except OSError:
            observed("transport_failure", "TEMP_FAILED")
            raise failure("TEMP_FAILED") from None
        except ContentFailure as error:
            observed(outcome_state(error.code), error.code)
            if error.code in {"AUTH_REQUIRED", "AUTH_MODE_MISMATCH", "MODEL_DENIED", "CLI_UNSUPPORTED",
                              "CLI_PROFILE_UNSAFE", "CLI_FAILED", "METADATA_FAILED", "PROCESS_CLEANUP_FAILED",
                              "QUOTA_EXHAUSTED"}:
                self.invalidate_preflight()
            raise failure(error.code) from None
        except Exception:
            observed("transport_failure", "CLI_FAILED")
            raise failure("CLI_FAILED") from None

