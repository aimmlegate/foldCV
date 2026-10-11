"""Bounded render transport, separate from saved project version 3."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class RenderWire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, alias_generator=to_camel)


class Candidate(RenderWire):
    name: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(max_length=12000)


class FocusItem(RenderWire):
    label: str = Field(min_length=1, max_length=100)
    duration: str = Field(max_length=100)
    icon: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9]+$")


class SidebarSection(RenderWire):
    title: str = Field(min_length=1, max_length=100)
    items: list[str] = Field(max_length=100)


class Project(RenderWire):
    company: str = Field(min_length=1, max_length=200)
    period: str = Field(min_length=1, max_length=100)
    stack: str = Field(max_length=1000)
    description: str = Field(max_length=4000)
    role: str = Field(min_length=1, max_length=300)
    tasks: list[str] = Field(max_length=100)
    results: list[str] = Field(max_length=100)


class SkillGroup(RenderWire):
    title: str = Field(min_length=1, max_length=100)
    items: str = Field(min_length=1, max_length=4000)


class RenderDocument(RenderWire):
    source_language: Literal["ru", "en", "mixed"] = "ru"
    candidate: Candidate
    focus: list[FocusItem] = Field(max_length=8)
    sidebar: list[SidebarSection] = Field(max_length=40)
    projects: list[Project] = Field(max_length=60)
    achievements: list[str] = Field(max_length=100)
    skill_groups: list[SkillGroup] = Field(max_length=40)
    footer: str = Field(max_length=200)

    @model_validator(mode="after")
    def bounded_text(self) -> RenderDocument:
        payload = self.model_dump(mode="json")
        strings: list[str] = []

        def collect(value: object) -> None:
            if isinstance(value, str):
                strings.append(value)
            elif isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(payload)
        if sum(len(value) for value in strings) > 100_000:
            raise ValueError("render text exceeds limit")
        if any(any(ord(character) < 32 and character not in "\n\t" for character in value) for value in strings):
            raise ValueError("unsupported control character")
        if any(len(value) > 4000 for section in self.sidebar for value in section.items):
            raise ValueError("sidebar item exceeds limit")
        if any(len(value) > 4000 for project in self.projects for value in project.tasks + project.results):
            raise ValueError("project item exceeds limit")
        if any(len(value) > 4000 for value in self.achievements):
            raise ValueError("achievement exceeds limit")
        return self


class RenderIdentity(RenderWire):
    id: str = Field(min_length=1, max_length=100)
    project_revision: int = Field(ge=1)
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    template_id: Literal["generic"]
    template_version: Literal["1.0.0"]
    template_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    renderer_version: Literal["1.0.0"]
    renderer_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RenderRequest(RenderWire):
    base_revision: int = Field(ge=1)
    snapshot: RenderIdentity
    document: RenderDocument

    @model_validator(mode="after")
    def matching_snapshot(self) -> RenderRequest:
        if self.base_revision != self.snapshot.project_revision:
            raise ValueError("render revision mismatch")
        if snapshot_digest(self) != self.snapshot.snapshot_sha256:
            raise ValueError("render snapshot hash mismatch")
        return self


def snapshot_digest(request: RenderRequest) -> str:
    data = {
        "baseRevision": request.base_revision,
        "document": request.document.model_dump(mode="json", by_alias=True),
        "snapshot": request.snapshot.model_dump(mode="json", by_alias=True, exclude={"snapshot_sha256"}),
    }
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
