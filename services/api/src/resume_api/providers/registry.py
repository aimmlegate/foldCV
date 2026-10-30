"""Frozen provider descriptors and the preview switch (multi-provider plan sections 6 and 7)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from packages.resume_core.models.settings import DEFAULT_PROVIDER, ProviderKind
from resume_api.cli import profile as codex
from resume_api.cli.profiles import claude
from resume_api.cli.qualification import Compatibility, QualificationError, require_publisher


@dataclass(frozen=True)
class Descriptor:
    kind: ProviderKind
    display: str
    subscription: str
    publisher: str
    command: str
    team_id: str
    identifier: str
    compatibility: Compatibility
    auth_modes: tuple[str, ...]
    quota: Literal["cli", "not_provided"]
    managed_install: bool
    # Without a terminal the CLI may ask for the code shown after the browser sign-in.
    login_code: bool
    # Only MP07 sets this for a new provider, after its whole parity matrix passes.
    complete: bool


CODEX = Descriptor("codex_cli", "Codex", "ChatGPT", "OpenAI", "codex", codex.TEAM_ID, codex.IDENTIFIER, codex.COMPATIBILITY,
                   ("chatgpt",), "cli", True, False, True)
# Complete since MP07.
CLAUDE = Descriptor("claude_cli", "Claude", "Claude", "Anthropic", "claude", claude.TEAM_ID, claude.IDENTIFIER,
                    claude.COMPATIBILITY, (claude.ACCEPTED_AUTH,), "not_provided", True, True, True)
DESCRIPTORS: dict[str, Descriptor] = {item.kind: item for item in (CODEX, CLAUDE)}


class ProviderRegistry:
    """Lists complete kinds; `preview_kinds` adds incomplete ones for tests and local wiring only."""

    def __init__(self, preview_kinds: frozenset[str] = frozenset()):
        if not preview_kinds <= DESCRIPTORS.keys():
            raise ValueError("Unknown provider kind")
        self.preview_kinds = frozenset(preview_kinds)

    def listed(self) -> tuple[Descriptor, ...]:
        return tuple(item for item in DESCRIPTORS.values() if item.complete or item.kind in self.preview_kinds)

    def resolve(self, kind: str | None) -> ProviderKind:
        return next((item.kind for item in self.listed() if item.kind == kind), DEFAULT_PROVIDER)


def discovered(descriptor: Descriptor, executable: Path | None) -> bool:
    """Passive discovery of an inactive provider: its binary and publisher signature, no CLI process."""
    if executable is None:
        return False
    try:
        require_publisher(executable, descriptor.team_id, descriptor.identifier)
        return True
    except (OSError, QualificationError):
        return False
