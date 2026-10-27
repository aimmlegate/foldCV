"""Transport models of the host, connection and settings routes, and the shared error envelope."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.resume_core.reasoning import ModelReasoning, ReasoningEffort
from packages.resume_core.models.connection import CliInstallationPayload
from packages.resume_core.models.settings import ProviderKind


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


class HostRequest(Transport):
    # Names the provider the screen shows; a request for an inactive one is refused.
    provider: ProviderKind | None = None


class SelectModelRequest(HostRequest):
    model: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class SelectProviderRequest(Transport):
    provider: ProviderKind


class ProviderSummary(Transport):
    kind: ProviderKind
    display: str = Field(min_length=1, max_length=40)
    subscription: str = Field(min_length=1, max_length=40)
    publisher: str = Field(min_length=1, max_length=40)
    # Inactive providers: binary and publisher signature only, never a CLI process.
    installed: bool


class SelectReasoningRequest(Transport):
    model: str = Field(min_length=1, max_length=80)
    effort: ReasoningEffort | None


class QuotaPayload(Transport):
    state: Literal["unknown", "available", "exhausted", "not_provided"]
    usedPercent: float | None = Field(default=None, ge=0, le=100)
    resetsAt: int | None = Field(default=None, ge=0)


class ConnectionPayload(Transport):
    provider: ProviderKind = "codex_cli"
    providers: list[ProviderSummary] = Field(default_factory=list, max_length=8)
    # Set when a stored provider choice is no longer offered and Codex was selected instead.
    providerNotice: Literal["provider_unavailable"] | None = None
    state: Literal["unchecked", "detached", "cli_missing", "launcher_unsupported", "unsupported_version", "login_required",
                   "api_key_mode", "metadata_failed", "quota_exhausted", "unknown_limits",
                   "connected", "login_pending", "login_failed", "cleanup_blocked"]
    version: str | None = None
    versionStatus: Literal["supported", "graceful"] | None = None
    plan: str | None = None
    models: list[str] = Field(default_factory=list, max_length=100)
    selectedModel: str | None = None
    modelReasoning: dict[str, ModelReasoning] = Field(default_factory=dict)
    quota: QuotaPayload = Field(default_factory=lambda: QuotaPayload(state="unknown"))
    metadataReady: bool = False
    generationReady: bool = False
    experimentalMode: bool = False
    installation: CliInstallationPayload | None = None
