"""The design-template skill files: present, small enough for one read_skill call, template tools only."""

from pathlib import Path
import re

import pytest

SKILLS = Path(__file__).resolve().parents[2] / "services/api/src/resume_api/assistant/skills"
FILES = [SKILLS / "design-template.md", SKILLS / "template-authoring.md"]
TEMPLATE_TOOLS = ["list_templates", "read_template", "read_draft", "edit_draft", "check_draft", "propose_draft",
    "read_sample", "read_skill", "read_public_page"]
RESUME_TOOLS = ["read_resume", "find_text", "read_facts", "read_original", "check_resume", "export_document",
    "propose_changes", "publish_findings"]


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.name)
def test_skill_file_exists_and_fits_one_read(path):
    assert path.is_file()
    assert len(path.read_bytes()) < 48 * 1024


def test_skill_names_every_template_tool_and_no_resume_tool():
    text = "\n".join(path.read_text("utf-8") for path in FILES)
    assert [tool for tool in TEMPLATE_TOOLS if not re.search(rf"\b{tool}\b", text)] == []
    assert [tool for tool in RESUME_TOOLS if tool in text] == []
