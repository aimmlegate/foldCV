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
    # The provider the action is for (D119: each has its own connection); None is Codex. One that is off is refused.
    provider: ProviderKind | None = None


class SelectModelRequest(HostRequest):
    model: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class EnableProviderRequest(Transport):
    provider: ProviderKind
    enabled: bool


class LoginCodeRequest(HostRequest):
    # The one-time code from the provider's sign-in page; held in memory for the running sign-in only.
    code: str = Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9._~#-]+$")


class SelectReasoningRequest(Transport):
    model: str = Field(min_length=1, max_length=80)
    effort: ReasoningEffort | None


class QuotaPayload(Transport):
    state: Literal["unknown", "available", "exhausted", "not_provided"]
    usedPercent: float | None = Field(default=None, ge=0, le=100)
    resetsAt: int | None = Field(default=None, ge=0)


ConnectionState = Literal["unchecked", "detached", "cli_missing", "launcher_unsupported", "unsupported_version",
                          "login_required", "api_key_mode", "metadata_failed", "quota_exhausted", "unknown_limits",
                          "connected", "login_pending", "login_failed", "cleanup_blocked"]


class ProviderState(Transport):
    """One provider's own connection (D119: each provider keeps its own at the same time)."""
    state: ConnectionState
    version: str | None = None
    versionStatus: Literal["supported", "graceful"] | None = None
    plan: str | None = None
    models: list[str] = Field(default_factory=list, max_length=100)
    modelReasoning: dict[str, ModelReasoning] = Field(default_factory=dict)
    quota: QuotaPayload = Field(default_factory=lambda: QuotaPayload(state="unknown"))
    metadataReady: bool = False


class ProviderSummary(ProviderState):
    kind: ProviderKind
    display: str = Field(min_length=1, max_length=40)
    subscription: str = Field(min_length=1, max_length=40)
    publisher: str = Field(min_length=1, max_length=40)
    loginCode: bool = False
    # A provider that is off: binary and publisher signature only, never a CLI process.
    installed: bool
    enabled: bool = False
    installation: CliInstallationPayload | None = None


class ConnectionPayload(Transport):
    """`provider` and its `state`, `version`, `versionStatus`, `plan`, `quota` and `installation` describe the provider the
    request named; `models`, `modelReasoning`, `selectedModel` (the processing model), `metadataReady` and
    `generationReady` describe the catalog of every provider that is on."""
    provider: ProviderKind = "codex_cli"
    providers: list[ProviderSummary] = Field(default_factory=list, max_length=8)
    state: ConnectionState
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
