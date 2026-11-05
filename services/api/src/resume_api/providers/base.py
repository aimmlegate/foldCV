"""The connection records every provider adapter returns: its failure, the quota and the account metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.resume_core.reasoning import ModelReasoning


class ConnectionFailure(Exception):
    def __init__(self, code: str, version: str | None = None):
        super().__init__(code)
        self.code = code
        self.version = version


@dataclass(frozen=True)
class Quota:
    state: str = "unknown"
    used_percent: float | None = None
    resets_at: int | None = None


@dataclass(frozen=True)
class Metadata:
    version: str
    models: tuple[str, ...]
    plan: str | None
    quota: Quota
    reasoning: dict[str, ModelReasoning] = field(default_factory=dict)
    # "graceful": newer than the last tested version; shown as a notice (plan section 5).
    version_status: str = "supported"
