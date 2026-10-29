"""Typed boundary for code-owned, scoped text operations."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Callable, Generic, Protocol, TypeVar

from pydantic import BaseModel, JsonValue

from .dynamic_result import DynamicResultSpec

from packages.resume_core.reasoning import EFFORTS, ReasoningEffort
from resume_api.lifecycle import OperationFiles
from packages.resume_core.project_limits import IMPORT_CEILING_SECONDS


ResultT = TypeVar("ResultT", bound=BaseModel)
# One call may run as long as the longest import limit Settings allow (D114: no call limit of its own).
MAX_GENERATION_SECONDS = IMPORT_CEILING_SECONDS
CONTENT_INPUT_BYTES = 256 * 1024


class ContentTransport(Protocol[ResultT]):
    def encode(self, text: str) -> str: ...
    def restore(self, value: ResultT) -> ResultT: ...


@dataclass(frozen=True)
class GenerationPolicy:
    model: str
    timeout_seconds: float = 30
    max_input_bytes: int = CONTENT_INPUT_BYTES
    max_total_input_bytes: int = 2 * CONTENT_INPUT_BYTES
    max_total_output_bytes: int = 262_144
    allow_repair: bool = True
    reasoning_effort: ReasoningEffort | None = None

    def __post_init__(self) -> None:
        if (not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= MAX_GENERATION_SECONDS
                or not 0 < self.max_input_bytes <= CONTENT_INPUT_BYTES
                or not 0 < self.max_total_input_bytes <= 2 * CONTENT_INPUT_BYTES
                or not 0 < self.max_total_output_bytes <= 262_144
                or type(self.allow_repair) is not bool
                or self.reasoning_effort is not None and self.reasoning_effort not in EFFORTS):
            raise ValueError("invalid generation limits")


@dataclass(frozen=True)
class ContentInput(Generic[ResultT]):
    text: str
    result_type: type[ResultT] | DynamicResultSpec
    policy: GenerationPolicy
    transport: ContentTransport[ResultT] | None = None
    on_return: Callable[[ContentTransportReturn], None] | None = None
    # The captured request the text was projected from; only transports that do not send text read it.
    request_value: dict | None = None


@dataclass(frozen=True)
class ReportedUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    complete: bool = False


@dataclass(frozen=True)
class ContentResult(Generic[ResultT]):
    value: ResultT
    usage: ReportedUsage
    cli_version: str
    model: str
    elapsed_seconds: float
    logical_attempts: int
    internal_inference_count: int | None = None
    cleanup_verified: bool | None = None
    dispatch_witness: dict[str, JsonValue] | None = None
    reasoning_effort: str | None = None
    raw_return: str | None = None


@dataclass(frozen=True)
class ContentTransportReturn:
    raw_return: str | None
    outcome: str
    original_code: str | None
    logical_attempts: int
    usage: ReportedUsage
    cleanup_verified: bool | None
    dispatch_witness: dict[str, JsonValue] | None
    reasoning_effort: str | None


class ContentFailure(Exception):
    def __init__(self, code: str, *, logical_attempts: int = 0,
                 usage: ReportedUsage = ReportedUsage(),
                 cleanup_verified: bool | None = None,
                 dispatch_witness: dict[str, JsonValue] | None = None, raw_return: str | None = None):
        self.code = code
        self.logical_attempts = logical_attempts
        self.usage = usage
        self.cleanup_verified = cleanup_verified
        self.dispatch_witness = dispatch_witness
        self.raw_return = raw_return
        super().__init__(code)


class ContentProvider(Protocol):
    def generate(self, request: ContentInput[ResultT], files: OperationFiles,
                 cancel: threading.Event) -> ContentResult[ResultT]: ...


def outcome_state(code: str) -> str:
    if code in {"INVALID_RESULT", "INVALID_PAYLOAD"}: return "invalid_payload"
    if code in {"REFUSED", "REFUSAL"}: return "refused"
    if code in {"INCOMPLETE_STREAM", "INCOMPLETE"}: return "incomplete"
    if code in {"DEADLINE", "DEADLINE_EXCEEDED", "TIMEOUT"}: return "timed_out"
    if code == "CANCELLED": return "cancelled"
    if code in {"CLEANUP_FAILED", "PROCESS_CLEANUP_FAILED"}: return "cleanup_failure"
    return "transport_failure"
