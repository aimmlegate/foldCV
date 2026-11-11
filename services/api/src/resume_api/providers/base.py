"""The connection records every provider adapter returns (its failure, the quota, the account metadata) and the
ports a provider fills: connection, content, native profile."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

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
    # The signed-in account as Settings names it; it never goes to a log.
    account: str | None = None


@dataclass(frozen=True)
class SignedOut:
    """A sign-out or clearing that the status check after it confirmed."""
    version: str | None = None


ACCOUNT_PART = 254


def _account_part(value: object) -> str | None:
    text = value.strip() if isinstance(value, str) else ""
    return text if 0 < len(text) <= ACCOUNT_PART and text.isprintable() else None


def account_label(email: object, organization: object = None) -> str | None:
    """The email, with the organisation when it says more; a value in another form is left out, not refused."""
    email, organization = _account_part(email), _account_part(organization)
    # Claude names a personal organisation after its email.
    if email is not None and organization is not None and email in organization:
        organization = None
    return " · ".join(item for item in (email, organization) if item) or None


# The roles a provider fills, as the service calls them; the Codex and Claude classes satisfy them structurally.
class ConnectionPort(Protocol):
    def inspect(self, files, cancel, *, full: bool = True) -> Metadata: ...

    def login(self, files, cancel, *args, **kwargs) -> None: ...

    # The CLI's own sign-out, in the profile the sign-in uses.
    def logout(self, files, cancel, *, output=None) -> None: ...


class ContentPort(Protocol):
    def generate(self, request, files, cancel): ...

    def invalidate_preflight(self) -> None: ...


class ProfilePort(Protocol):
    root: Path
    executable: Path

    def prepare(self) -> None: ...

    def clear(self) -> list[str]: ...
