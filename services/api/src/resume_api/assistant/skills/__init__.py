"""Bundled assistant skills: read-only instructions served by `read_skill`; they grant no permission."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from packages.resume_core.assistant_store import AgentFailure

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Skill:
    id: str
    title: str
    description: str
    resources: dict[str, Path]


SKILLS = (
    Skill('import-resume', 'Проверка и правка резюме', 'Review the current resume and propose explicit revisions.',
        {'SKILL.md': HERE / 'import-resume.md', 'references/editorial-rules.md': HERE / 'editorial-rules.md'}),
    Skill('format-resume', 'Оформление по шаблону', 'Propose block formatting with the exact wording preserved.',
        {'SKILL.md': HERE / 'format-resume.md', 'references/editorial-rules.md': HERE / 'editorial-rules.md'}),
)
INSTRUCTIONS = (" Bundled skills are read with read_skill. A message starting with /import-resume or /format-resume "
    "selects that skill; /skills lists them. Skills are reference text: the user's request and the run's permissions "
    "take precedence, and a skill grants no access.")


def skill_catalog():
    return [{'id': skill.id, 'title': skill.title, 'description': skill.description, 'resources': list(skill.resources)}
        for skill in SKILLS]


def read_skill(name, resource='SKILL.md'):
    skill = next((value for value in SKILLS if value.id == name), None)
    if skill is None or resource not in skill.resources:
        raise AgentFailure('AGENT_NOT_FOUND')
    try:
        return {'skill': skill.id, 'resource': resource, 'content': skill.resources[resource].read_text('utf-8'),
            'resources': list(skill.resources)}
    except (OSError, UnicodeError):
        raise AgentFailure('AGENT_SOURCE_UNAVAILABLE') from None
