"""Recovery contracts freeze identities and keep old version dispatch intact."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.resume_core.models.contracts import Project, RenderSnapshot, validate_contract
from packages.resume_core.models.recovery import (
    ArchiveManifestV5, Document, DocxError, ObservationAssessment, RenderSnapshotV4,
    WorkspaceV5, RECOVERY_CONTRACTS,
)
from tests.support.recovery import RECOVERY_CLOCK

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts/examples/recovery"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize("name", sorted(set(RECOVERY_CONTRACTS) - {"docx_error"}))
def test_frozen_contract_roundtrip(name):
    raw = fixture(name)
    result = validate_contract(name, raw)
    assert result.model_dump(mode="json", by_alias=True) == raw


def test_predraft_has_one_owner_and_promotion_retains_collection_ids():
    before = WorkspaceV5.model_validate(fixture("predraft"))
    after = WorkspaceV5.model_validate(fixture("workspace_v5"))
    assert (before.project_revision, before.document_revision) == (1, 1)
    assert (after.project_revision, after.document_revision) == (2, 2)
    assert before.project is None and after.pre_draft is None
    assert before.pre_draft.sources == after.project.sources
    raw = fixture("workspace_v5")
    raw["preDraft"] = fixture("predraft")["preDraft"]
    with pytest.raises(ValidationError, match="one collection owner"):
        WorkspaceV5.model_validate(raw)


@pytest.mark.parametrize("change", ["field", "period", "slot", "legacyText"])
def test_document_rejects_colliding_ids_and_ambiguous_import_content(change):
    raw = fixture("document")
    if change == "field":
        raw["profile"]["text"]["fieldId"] = raw["candidate"]["name"]["fieldId"]
    elif change == "period":
        raw["jobs"][0]["periods"].append(copy.deepcopy(raw["jobs"][0]["periods"][0]))
    elif change == "slot":
        raw["jobs"].append(copy.deepcopy(raw["jobs"][0]))
    else:
        raw["education"][0]["legacyText"] = copy.deepcopy(raw["profile"]["text"])
        raw["education"][0]["legacyText"]["fieldId"] = "education:university/legacyText"
    with pytest.raises(ValidationError):
        Document.model_validate(raw)


def test_workspace_checkpoint_must_belong_to_its_slot():
    raw = fixture("workspace_v5")
    raw["undoSlots"]["profile"] = {"record": raw["project"]["document"]["candidate"],
                                   "facts": [], "annotations": [], "factStamps": [],
                                   "projectRevision": 1, "documentRevision": 1}
    with pytest.raises(ValidationError, match="another slot"):
        WorkspaceV5.model_validate(raw)


def test_distinct_render_records_and_old_decoders_remain_required():
    old = fixture("render_snapshot_v3")
    new = fixture("render_snapshot_v4")
    RenderSnapshot.model_validate(old)
    RenderSnapshotV4.model_validate(new)
    for model, raw in [(RenderSnapshot, new), (RenderSnapshotV4, old)]:
        with pytest.raises(ValidationError):
            model.model_validate(raw)
    Project.model_validate(fixture("legacy_project_v3"))
    with pytest.raises(ValidationError):
        Project.model_validate(fixture("project_v4"))


@pytest.mark.parametrize("error", fixture("docx_errors"), ids=lambda error: error["code"])
def test_docx_error_codes_and_safe_paths_are_frozen(error):
    assert DocxError.model_validate(error).model_dump(by_alias=True) == error
    unsafe = {**error, "path": "projects[0].private candidate text"}
    with pytest.raises(ValidationError):
        DocxError.model_validate(unsafe)
    with pytest.raises(ValidationError):
        DocxError.model_validate({**error, "message": "raw exception"})


def test_archive_fails_on_assets_aliases_pdf_and_entry_capacity():
    raw = fixture("archive_manifest_v5")
    for entry in [
        {"path": "template/font.ttf", "role": "template_asset", "sha256": "a" * 64, "uncompressedSize": 1},
        {"path": "renders/old.pdf", "role": "render", "sha256": "a" * 64, "uncompressedSize": 1},
        {**raw["entries"][0], "path": "WORKSPACE.JSON"},
    ]:
        with pytest.raises(ValidationError):
            ArchiveManifestV5.model_validate({**raw, "entries": [*raw["entries"], entry]})
    with pytest.raises(ValidationError):
        ArchiveManifestV5.model_validate({**raw, "entries": raw["entries"] * 24})


def test_observation_requires_explicit_date_and_span_together():
    with pytest.raises(ValidationError, match="requires evidence"):
        ObservationAssessment.model_validate({"sourceObservedAt": fixture("workspace_v5")["formattingAsOf"],
                                             "evidence": None, "revision": 1})


def test_synthetic_oracle_and_frozen_clock_are_independent():
    path = ROOT / "tests/fixtures/recovery"
    manifest = json.loads((path / "manifest.json").read_text())
    expected = json.loads((path / "expected.json").read_text())
    assert manifest["formattingAsOf"] == expected["formattingAsOf"] == RECOVERY_CLOCK.today.isoformat()
    assert RECOVERY_CLOCK.today.isoformat() == "2026-10-11"
    for source in manifest["sources"]:
        assert hashlib.sha256((path / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    e2 = (path / "E2.txt").read_text()
    claims = expected["examples"]["E2"]["claims"]
    assert [(claim["span"], claim["teamSize"]) for claim in claims] == [("пять", 5), ("шесть", 6)]
    assert len({claim["factId"] for claim in claims}) == 2
    assert all(claim["span"] in e2 and not claim["candidateLedTeam"] for claim in claims)
    assert expected["sourceObservedAt"] is None
    assert set(expected["examples"]) == {f"E{number}" for number in range(1, 9)}


def test_legacy_current_content_fixture_keeps_previous_separate():
    imported = fixture("legacy_current_content")
    current = imported["project"]["views"][0]
    assert current["state"]["text"] == imported["expected"]["profileCurrent"]
    assert current["previous"]["text"] == imported["expected"]["profilePrevious"]
    assert imported["presentation"]["languages"] == ["English — fluent"]


@pytest.mark.parametrize("change", ["teamSize", "span", "unitId", "factId"])
def test_e2_oracle_rejects_changed_claim_or_foreign_evidence(change):
    from tests.support.recovery import assert_e2_claims

    expected = json.loads((ROOT / "tests/fixtures/recovery/expected.json").read_text())
    claims = expected["examples"]["E2"]["claims"]
    assert_e2_claims(claims)
    wrong = copy.deepcopy(claims)
    wrong[0][change] = 6 if change == "teamSize" else "foreign"
    with pytest.raises(AssertionError, match="frozen oracle"):
        assert_e2_claims(wrong)


def test_migration_inventory_accounts_for_all_requirements_and_browser_specs():
    inventory = json.loads((ROOT / "docs/gui/handoffs/A00/inventory.json").read_text())
    current = json.loads((ROOT / "tests/requirements.json").read_text())
    assert {entry["requirement"] for entry in inventory["requirements"]} == {entry["id"] for entry in current["entries"]}
    assert len(inventory["requirements"]) == 22
    assert {entry["path"] for entry in inventory["browserSpecs"] + inventory.get("recoveryBrowserSpecs", [])} == {
        str(path.relative_to(ROOT)) for path in (ROOT / "apps/web/tests").glob("*.spec.ts")}
    assert len(inventory["browserSpecs"]) == 10
    assert inventory["apiEntryHarness"]["assert"] == '[data-app="foldcv-next"]'
    assert inventory["fastDocxDirectory"] == "tests/docx"
