"""Automatic resume headings are projections, never a saved-project migration."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_projects import GuiProjectListResponse
from packages.resume_core.rich_identity import resume_identity
from packages.resume_core.rules import RulesStore
from resume_api.rich_projects import RichProjectService
from tests.recovery.test_rich_images_service import service
from tests.recovery.test_rich_persistence import without_sources


def test_resume_identity_uses_candidate_name_and_profession_with_safe_missing_values():
    workspace = without_sources()
    candidate = next(record for record in workspace.project.facts.records if record.kind == "candidate")
    candidate.name.raw_text = "  Anna\n Stone  "
    candidate.title.raw_text = " Platform  engineer "
    assert resume_identity(workspace).model_dump() == {"title": "Anna Stone", "subtitle": "Platform engineer"}
    candidate.name.raw_text = " \n "
    assert resume_identity(workspace).title == "Резюме без имени"
    candidate.title.raw_text = ""
    assert resume_identity(workspace).subtitle == ""
    workspace.project.facts.records = [record for record in workspace.project.facts.records if record.kind != "candidate"]
    assert resume_identity(workspace).model_dump() == {"title": "Резюме без имени", "subtitle": ""}
    assert resume_identity(SimpleNamespace(project=None, title="original.txt")).title == "original.txt"


def test_listing_and_response_ignore_manual_titles_without_rewriting_saved_workspace(tmp_path):
    api, identifier = service(tmp_path)
    workspace = api.workspaces[identifier]
    candidate = next(record for record in workspace.project.facts.records if record.kind == "candidate")
    candidate.name.raw_text = candidate.name.value = "Anna Stone"
    candidate.title.raw_text = candidate.title.value = "Platform engineer"
    workspace.title, workspace.title_manually_set = "Old manual label", True
    assert api.persist(identifier) == "durable"
    path = tmp_path / "store/projects" / identifier / "workspace.json"
    original = path.read_bytes()
    response = api.response(identifier)
    listed = GuiProjectListResponse.model_validate(api.listing()).entries[0]
    assert response.identity.title == listed.title == "Anna Stone"
    assert response.identity.subtitle == listed.subtitle == "Platform engineer"
    assert response.workspace.title == "Old manual label" and path.read_bytes() == original
    reopened = RichProjectService(tmp_path / "operations-2", RulesStore(tmp_path / "store"), lambda: None)
    assert reopened.response(identifier).identity == response.identity
    assert path.read_bytes() == original


def test_candidate_fact_updates_and_restoration_change_identity_without_cached_titles(tmp_path):
    api, identifier = service(tmp_path)
    record = next(record for record in api.workspaces[identifier].project.facts.records if record.kind == "candidate")
    before = record.model_copy(deep=True)
    record.name.raw_text = record.name.value = "Changed Name"
    record.title.raw_text = record.title.value = "New Role"
    assert api.response(identifier).identity.model_dump() == {"title": "Changed Name", "subtitle": "New Role"}
    assert api.listing()["entries"][0]["subtitle"] == "New Role"
    api.workspaces[identifier].project.facts.records = [before if entry.id == record.id else entry for entry in api.workspaces[identifier].project.facts.records]
    assert api.response(identifier).identity == resume_identity(api.workspaces[identifier])
    assert api.listing()["entries"][0]["title"] == before.name.raw_text
