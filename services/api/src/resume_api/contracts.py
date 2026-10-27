"""Transport version 1; persisted project contracts stay at version 3."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from packages.resume_core.models.contracts import Block, Fact, Proposal, SourceUnit
from packages.resume_core.rendering.models import RenderRequest

from .host_models import (ConnectionPayload, EmptyRequest, ErrorEnvelope, ErrorPayload, QuotaPayload,  # noqa: F401
    SelectModelRequest, SelectReasoningRequest, Transport)


class UsagePayload(Transport):
    inputTokens: int | None = Field(default=None, ge=0)
    outputTokens: int | None = Field(default=None, ge=0)
    logicalAttempts: int = Field(ge=0)
    inferenceCount: int | None = Field(default=None, ge=0)


class SourceUnitContext(Transport):
    sourceId: str = Field(min_length=1)
    sourceRevision: int = Field(ge=1)
    unit: SourceUnit


class NormalizeRequest(Transport):
    baseRevision: int = Field(ge=0)
    sourceUnits: list[SourceUnitContext] = Field(max_length=500)
    language: Literal["ru", "en"]


class DraftRequest(Transport):
    baseRevision: int = Field(ge=0)
    facts: list[Fact] = Field(max_length=500)
    language: Literal["ru", "en"]
    contentRules: str = Field(max_length=4096)


class RewriteRequest(Transport):
    baseRevision: int = Field(ge=0)
    block: Block
    facts: list[Fact] = Field(max_length=100)
    instruction: str = Field(min_length=1, max_length=2000)


class ValidateRequest(Transport):
    baseRevision: int = Field(ge=0)
    facts: list[Fact] = Field(max_length=500)
    blocks: list[Block] = Field(max_length=100)


TextRequest = NormalizeRequest | DraftRequest | RewriteRequest


class NormalizeResult(Transport):
    facts: list[Fact]
    unresolved: list[str]


class DraftResult(Transport):
    blocks: list[Block]


class RewriteResult(Transport):
    proposal: Proposal


OperationResult = NormalizeResult | DraftResult | RewriteResult


class StartedPayload(Transport):
    stage: Literal["normalize", "draft", "rewrite"]


class StagePayload(Transport):
    stage: Literal["validation", "execution", "cleanup"]


class CompletedPayload(Transport):
    result: OperationResult
    usage: UsagePayload


class EventBase(Transport):
    transportVersion: Literal[1] = 1
    requestId: str
    sequence: int = Field(ge=1)
    baseRevision: int = Field(ge=0)


class StartedEvent(EventBase):
    type: Literal["operation.started"]
    payload: StartedPayload


class StageEvent(EventBase):
    type: Literal["stage.changed"]
    payload: StagePayload


class ResultEvent(EventBase):
    type: Literal["result.ready"]
    payload: OperationResult


class UsageEvent(EventBase):
    type: Literal["usage.updated"]
    payload: UsagePayload


class CompletedEvent(EventBase):
    type: Literal["operation.completed"]
    payload: CompletedPayload


class FailedEvent(EventBase):
    type: Literal["operation.failed"]
    payload: ErrorPayload


EventEnvelope = Annotated[StartedEvent | StageEvent | ResultEvent | UsageEvent | CompletedEvent | FailedEvent,
                          Field(discriminator="type")]


class ProcessOptions(Transport):
    timeoutSeconds: int = Field(default=30, ge=1, le=120)
    maxOutputBytes: int = Field(default=262144, ge=1024, le=1048576)
