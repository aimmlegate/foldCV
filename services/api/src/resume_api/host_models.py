"""Transport models of the host, connection and settings routes, and the shared error envelope."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.resume_core.reasoning import ModelReasoning, ReasoningEffort
from packages.resume_core.models.connection import CliInstallationPayload


class Transport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorPayload(Transport):
    code: str
    retryable: bool
    stage: str


class ErrorEnvelope(Transport):
    error: ErrorPayload


class EmptyRequest(Transport):
    pass


class SelectModelRequest(Transport):
    model: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class SelectReasoningRequest(Transport):
    model: str = Field(min_length=1, max_length=80)
    effort: ReasoningEffort | None


class QuotaPayload(Transport):
    state: Literal["unknown", "available", "exhausted"]
    usedPercent: float | None = Field(default=None, ge=0, le=100)
    resetsAt: int | None = Field(default=None, ge=0)


class ConnectionPayload(Transport):
    state: Literal["unchecked", "detached", "cli_missing", "launcher_unsupported", "unsupported_version", "login_required",
                   "api_key_mode", "metadata_failed", "quota_exhausted", "unknown_limits",
                   "connected", "login_pending", "login_failed", "cleanup_blocked"]
    version: str | None = None
    plan: str | None = None
    models: list[str] = Field(default_factory=list, max_length=100)
    selectedModel: str | None = None
    modelReasoning: dict[str, ModelReasoning] = Field(default_factory=dict)
    quota: QuotaPayload = Field(default_factory=lambda: QuotaPayload(state="unknown"))
    metadataReady: bool = False
    generationReady: bool = False
    experimentalMode: bool = False
    installation: CliInstallationPayload | None = None
