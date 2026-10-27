"""The project registry file: one entry per project, tombstones kept."""

from __future__ import annotations

from typing import Literal

from .contracts import Id, Wire


class RegistryEntry(Wire):
    project_id: Id
    title: str
    updated_at: str
    tombstoned: bool
    cleanup_status: Literal["none", "pending", "complete", "failed"]


class Registry(Wire):
    schema_version: Literal[1]
    entries: list[RegistryEntry]
