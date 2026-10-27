"""Bundled skills (assistant/skills): exact text of every listed resource, an allowlist, explicit missing files."""

from dataclasses import replace

import pytest

from packages.resume_core.assistant_store import AgentFailure
from resume_api.assistant import skills
from resume_api.assistant.skills import SKILLS, read_skill


def test_every_bundled_resource_reads_exactly_and_unicode_text_is_unchanged(tmp_path, monkeypatch):
    for skill in SKILLS:
        for resource, path in skill.resources.items():
            value = read_skill(skill.id, resource)
            assert value["content"] == path.read_text("utf-8") and value["resources"] == list(skill.resources)
    path = tmp_path / "SKILL.md"
    original = 'Русский 😀 "\\\n\t' * 4000
    path.write_bytes(original.encode())
    monkeypatch.setattr(skills, "SKILLS", (replace(SKILLS[0], resources={"SKILL.md": path}),))
    assert read_skill("import-resume")["content"] == original


@pytest.mark.parametrize(("name", "resource"), [("import-resume", "../../../../auth.json"), ("import-resume", "/etc/passwd"),
    ("import-resume", "scripts/render.py"), ("import-resume", "references/data-contract.md"), ("unknown-skill", "SKILL.md")])
def test_only_listed_resources_of_known_skills_are_readable(name, resource):
    with pytest.raises(AgentFailure, match="AGENT_NOT_FOUND"):
        read_skill(name, resource)


def test_a_missing_bundled_resource_is_explicit_and_names_no_path(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setattr(skills, "SKILLS", (replace(SKILLS[0], resources={"SKILL.md": missing}),))
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_UNAVAILABLE") as error:
        read_skill("import-resume")
    assert str(missing) not in repr(error.value)
