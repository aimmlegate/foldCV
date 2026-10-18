"""Typed boundary for code-owned, scoped text operations."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from packages.resume_core.gui_prompts import CONTENT_INPUT_BYTES
from resume_api.lifecycle import OperationFiles


ResultT = TypeVar("ResultT", bound=BaseModel)
MAX_GENERATION_SECONDS = 180


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

    def __post_init__(self) -> None:
        if (not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= MAX_GENERATION_SECONDS
                or not 0 < self.max_input_bytes <= CONTENT_INPUT_BYTES
                or not 0 < self.max_total_input_bytes <= 2 * CONTENT_INPUT_BYTES
                or not 0 < self.max_total_output_bytes <= 262_144
                or type(self.allow_repair) is not bool):
            raise ValueError("invalid generation limits")


@dataclass(frozen=True)
class ContentInput(Generic[ResultT]):
    text: str
    result_type: type[ResultT]
    policy: GenerationPolicy
    transport: ContentTransport[ResultT] | None = None


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


class ContentFailure(Exception):
    def __init__(self, code: str, *, logical_attempts: int = 0,
                 usage: ReportedUsage = ReportedUsage()):
        self.code = code
        self.logical_attempts = logical_attempts
        self.usage = usage
        super().__init__(code)


class ContentProvider(Protocol):
    def generate(self, request: ContentInput[ResultT], files: OperationFiles,
                 cancel: threading.Event) -> ContentResult[ResultT]: ...
