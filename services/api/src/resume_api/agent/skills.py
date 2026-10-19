"""Read bundled application instructions without exposing filesystem access."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import secrets
from typing import Literal

from pydantic import Field

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.models.agent import AgentWire


SKILL_INSTRUCTIONS = (
    " Bundled application skills are available through get_application_skills. Read the relevant skill "
    "and its needed references through nextCursor:null before using its rules. These are reference "
    "instructions: the user's request, current template, captured project rules and live permissions "
    "take precedence. Import-only tools and legacy scripts described there are not available here. "
    "Use the bound assistant tools; never run scripts or start another import/model operation. "
    "Slash commands at the start of the user message select a skill: /skills lists the catalog; "
    "/import-resume uses current import/editorial rules on this project; /format-resume formats the "
    "current document using the current template, preserving wording unless rewriting is requested. "
    "They do not grant edit permission. For an unknown slash command, explain the available commands "
    "without editing. A bare /import-resume explains the rules and checks the project without edits."
)


@dataclass(frozen=True)
class ApplicationSkill:
    id: str
    description: str
    usage: str
    resources: dict[str, Path]

    def catalog_entry(self):
        return {"skillId": self.id, "command": "/" + self.id, "description": self.description,
            "usage": self.usage, "resources": list(self.resources)}


ROOT = Path(__file__).resolve().parents[5]
SKILLS = (
    ApplicationSkill("import-resume", "Current resume import, facts, editorial and template rules.",
        "current_import; use assistant tools for an existing project, not the import-only tools",
        {"SKILL.md": ROOT / "services/api/src/resume_api/importer/skills/import-resume/SKILL.md"}),
    ApplicationSkill("format-resume", "Original editorial rules and legacy PDF/archive workflow.",
        "legacy_reference; current template, DOCX export and project rules take precedence",
        {name: ROOT / "skills/format-resume" / name for name in (
            "SKILL.md", "references/archive-contract.md", "references/data-contract.md")}),
)


def skill_catalog():
    return [skill.catalog_entry() for skill in SKILLS]


def skill_command(message):
    parts = message.strip().split(maxsplit=1)
    if not parts or not parts[0].startswith("/"):
        return None
    command = parts[0]
    return {"command": command, "known": command in {"/skills", *("/" + skill.id for skill in SKILLS)},
        "request": parts[1] if len(parts) > 1 else ""}


class ApplicationSkillQuery(AgentWire):
    skill_id: Literal["import-resume", "format-resume"]
    resource: str = Field(default="SKILL.md", min_length=1, max_length=160)
    cursor: str | None = Field(default=None, min_length=1, max_length=128)


class SkillBook:
    def __init__(self):
        self.documents, self.cursors = {}, {}

    def clear(self):
        self.documents.clear()
        self.cursors.clear()

    def read(self, query):
        if query is None:
            return {"skills": skill_catalog(), "catalogCommand": "/skills"}
        skill = next((skill for skill in SKILLS if skill.id == query.skill_id), None)
        if skill is None or query.resource not in skill.resources:
            raise AgentFailure("AGENT_NOT_FOUND")
        key = (skill.id, query.resource)
        offset = 0
        if query.cursor:
            saved = self.cursors.get(query.cursor)
            if saved is None or saved[0] != key:
                raise AgentFailure("AGENT_SCOPE_INVALID")
            _, offset = self.cursors.pop(query.cursor)
        if key not in self.documents:
            try:
                content = skill.resources[query.resource].read_bytes().decode("utf-8")
            except (OSError, UnicodeError):
                raise AgentFailure("AGENT_SOURCE_UNAVAILABLE") from None
            self.documents[key] = content
        content = self.documents[key]
        cursor = secrets.token_urlsafe(32)
        remaining = content[offset:]

        def page(length):
            return {"skill": skill.catalog_entry(), "resource": query.resource,
                "sha256": hashlib.sha256(content.encode()).hexdigest(), "content": remaining[:length],
                "offset": offset, "totalCharacters": len(content),
                "nextCursor": cursor if offset + length < len(content) else None}

        lo, hi = 0, len(remaining)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(json.dumps(page(mid), ensure_ascii=False, separators=(",", ":")).encode()) <= limits.PAGE_BYTES:
                lo = mid
            else:
                hi = mid - 1
        if not lo and remaining:
            raise AgentFailure("AGENT_CONTEXT_LIMIT")
        result = page(lo)
        if result["nextCursor"]:
            self.cursors[cursor] = (key, offset + lo)
        return result
