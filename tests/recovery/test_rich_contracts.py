"""Rich authority, identity and bounded transport regressions."""

from copy import deepcopy
import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.models.rich_facts import WorkingFacts
from packages.resume_core.models.rich_mutations import DateCascadeProposal, RichMutation
from packages.resume_core.models.rich_workspace import ArchiveManifestV6, LocalImageAsset, WorkspaceV6
from packages.resume_core.rich_limits import ARCHIVE_EXPANDED_BYTES, ImageReferences, MIB, portable_payload, retained_image_bytes

FIXTURE = Path(__file__).parents[1] / "fixtures" / "rich_workspace.json"


def fixture():
    return WorkspaceV6.model_validate_json(FIXTURE.read_text()).model_dump()


def test_rich_workspace_round_trip_keeps_one_tree_and_typed_authority():
    workspace = WorkspaceV6.model_validate(fixture(), by_name=True)
    assert WorkspaceV6.model_validate_json(workspace.model_dump_json(by_alias=True)) == workspace
    project = workspace.project
    assert project is not None
    assert [region.role for region in project.document.regions] == ["header", "sidebar", "main"]
    assert {block.type for block in project.document.blocks()} == {
        "section", "paragraph", "heading", "bullet_list", "numbered_list", "check_list",
        "toggle_list", "quote", "code", "divider", "table", "image",
    }
    education = next(record for record in project.facts.records if record.kind == "education")
    assert education.completion.value.model_dump() == {"precision": "day", "year": 2018, "month": 5, "day": 23}
    language = next(record for record in project.facts.records if record.kind == "language")
    assert language.level.value is None and language.level.status == "unknown"
    serialized = workspace.model_dump_json(by_alias=True)
    for forbidden in ("undoSlots", "editSessions", "plainDocument", "previousBlock", "base64"):
        assert forbidden not in serialized


def test_rich_region_moves_preserve_identity_and_do_not_restrict_membership():
    data = fixture()["project"]["document"]
    job = data["regions"][2]["blocks"].pop(0)
    data["regions"][0]["blocks"].append(job)
    document = RichDocumentV1.model_validate(data, by_name=True)
    moved = document.regions[0].blocks[-1]
    assert moved.id == "job-section" and moved.props.record_id == "job-1"
    data["regions"][1]["blocks"].append(deepcopy(job))
    data["regions"][1]["blocks"][-1]["id"] = "duplicate-job-section"
    with pytest.raises(ValidationError, match="rich node|primary record owner"):
        RichDocumentV1.model_validate(data, by_name=True)


@pytest.mark.parametrize("mutate", [
    lambda d: d["regions"].reverse(),
    lambda d: d["regions"][0]["blocks"][0].update(type="video"),
    lambda d: d["regions"][0]["blocks"][0]["props"].update(invented=True),
    lambda d: d["regions"][0]["blocks"][0]["content"][0]["styles"].update(shadow=True),
    lambda d: d["regions"][0]["blocks"][0]["content"][0]["styles"].update(text_color="javascript:red"),
])
def test_rich_unknown_variants_are_explicit_errors_instead_of_loss(mutate):
    document = fixture()["project"]["document"]
    mutate(document)
    with pytest.raises(ValidationError):
        RichDocumentV1.model_validate(document, by_name=True)


def test_rich_table_cell_ids_and_field_binding_ids_are_unique():
    document = fixture()["project"]["document"]
    table = next(block for block in document["regions"][2]["blocks"] if block["type"] == "table")
    table["content"]["rows"][1]["cells"][0]["id"] = "cell-a"
    with pytest.raises(ValidationError, match="rich node"):
        RichDocumentV1.model_validate(document, by_name=True)


def test_rich_pending_fields_keep_last_known_value_and_removed_record_tombstone():
    facts = fixture()["project"]["facts"]
    name = facts["records"][0]["name"]
    name.update(status="pending", pending_raw_text="Uncertain edit")
    parsed = WorkingFacts.model_validate(facts, by_name=True)
    assert parsed.records[0].name.value == "Alex Example"
    assert parsed.records[0].name.status == "pending"
    facts["tombstones"] = [{"record_id": "candidate-1", "revision": 2, "action_id": "remove-1", "order_index": 0}]
    with pytest.raises(ValidationError, match="removed record"):
        WorkingFacts.model_validate(facts, by_name=True)
    facts["records"].pop(0)
    assert WorkingFacts.model_validate(facts, by_name=True).tombstones[0].record_id == "candidate-1"


@pytest.mark.parametrize("version", [5, 7])
def test_rich_workspace_rejects_legacy_and_unknown_future_without_migration(version):
    data = fixture()
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        WorkspaceV6.model_validate(data, by_name=True)


@pytest.mark.parametrize("field", ["undo_slots", "edit_sessions", "plain_document", "previous_block"])
def test_rich_workspace_cannot_persist_live_history_or_a_plain_shadow(field):
    data = fixture()
    data[field] = {}
    with pytest.raises(ValidationError, match="Extra inputs"):
        WorkspaceV6.model_validate(data, by_name=True)


def asset(asset_id, size, hash_digit="a"):
    return LocalImageAsset(id=asset_id, sha256=hash_digit * 64, path=f"images/{hash_digit * 64}.png",
                           mimeType="image/png", size=size, width=1000, height=1000)


def test_rich_image_retention_counts_union_history_and_inflight_before_admission():
    images = [asset("a", 10 * MIB), asset("b", 10 * MIB, "b"), asset("copy", 10 * MIB)]
    refs = ImageReferences(live=("a", "copy"), durable=("a",), history=("b",), in_flight=("b",))
    assert retained_image_bytes(images, refs) == 20 * MIB
    with pytest.raises(ValueError, match="retained image byte"):
        retained_image_bytes(images, refs, reserved_bytes=1)
    assert retained_image_bytes(images, ImageReferences(live=("a", "copy"))) == 10 * MIB
    with pytest.raises(ValueError, match="missing retained"):
        retained_image_bytes(images, ImageReferences(history=("missing",)))
    with pytest.raises(ValueError, match="live image"):
        retained_image_bytes(images, ImageReferences(live=("a",) * 20), reserved_blocks=1)


@pytest.mark.parametrize("patch", [
    {"size": 20 * MIB + 1}, {"width": 5001, "height": 5000},
    {"mime_type": "image/webp"}, {"path": "../image.png"}, {"path": "https://example.com/image.png"},
])
def test_rich_image_metadata_requires_bounded_normalized_owned_bytes(patch):
    data = asset("image-1", MIB).model_dump()
    data.update(patch)
    with pytest.raises(ValidationError):
        LocalImageAsset.model_validate(data, by_name=True)


def test_rich_archive_omits_only_optional_cache_and_retains_entry_boundaries():
    required = [32 * MIB] * 9 + [ARCHIVE_EXPANDED_BYTES - 9 * 32 * MIB - 100]
    assert portable_payload(required, MIB, manifest_size=100, render_manifest_size=200) == required
    assert portable_payload([MIB] * 47, MIB, manifest_size=100, render_manifest_size=200) == [MIB] * 47
    assert portable_payload([MIB], 32 * MIB, manifest_size=100, render_manifest_size=200) == [MIB, 32 * MIB]
    for required in ([32 * MIB + 1], [32 * MIB] * 9 + [ARCHIVE_EXPANDED_BYTES - 9 * 32 * MIB], [1] * 48):
        with pytest.raises(ValueError, match="required portable"):
            portable_payload(required, None, manifest_size=1)
    manifest = {"schema_version": 6, "app_version": "test", "project_id": "project-1", "entries": [
        {"role": "workspace", "path": "workspace.json", "sha256": "0" * 64, "size": 1},
        {"role": "user_image", "path": "images/" + "a" * 64 + ".png", "sha256": "a" * 64, "size": MIB},
    ]}
    assert ArchiveManifestV6.model_validate(manifest, by_name=True).entries[-1].role == "user_image"
    manifest["entries"][-1]["path"] = "images/aliased.png"
    with pytest.raises(ValidationError, match="invalid user image"):
        ArchiveManifestV6.model_validate(manifest, by_name=True)


def test_rich_mutations_bound_the_patch_instead_of_requiring_whole_workspace():
    block = fixture()["project"]["document"]["regions"][0]["blocks"][0]
    data = {"schema_version": 1, "project_id": "project-1", "client_mutation_id": "mutation-1", "action_id": "action-1",
            "kind": "typing", "capture": {"session_id": "s-1", "action_id": "action-1", "action_token": 0,
                                           "dependencies": []},
            "steps": [{"kind": "put_block", "parent_id": "header", "after_id": None, "before_revision": 1, "block": block}]}
    assert len(RichMutation.model_validate(data, by_name=True).steps) == 1
    block["content"][0]["text"] = "x" * (1024 * 1024)
    with pytest.raises(ValidationError, match="1 MiB"):
        RichMutation.model_validate(data, by_name=True)
    data["steps"] = [{"kind": "replace_inline_range", "block_id": "name", "cell_id": None,
                      "field": "content", "start": 1_000_000, "end": 1_000_000,
                      "before_revision": 1, "content": [{"type": "text", "text": "x", "styles": {}}]}]
    assert len(RichMutation.model_validate(data, by_name=True).model_dump_json()) < 1000


def test_rich_date_proposal_cannot_move_anchor_or_offer_a_partial_unavailable_chain():
    period = next(record for record in fixture()["project"]["facts"]["records"] if record["kind"] == "employment")["periods"][0]
    proposal = {"id": "cascade-1", "anchor_job_id": "job-1", "anchor_period_id": "period-1",
                "formatting_as_of": {"precision": "day", "year": 2026, "month": 10, "day": 14},
                "capture": {"session_id": "s-1", "action_id": "action-1", "action_token": 0, "dependencies": []},
                "period_order": ["period-1"], "shifts": [], "status": "unavailable", "reason": "MIXED_PRECISION", "warnings": []}
    assert DateCascadeProposal.model_validate(proposal, by_name=True).shifts == []
    proposal["shifts"] = [{"job_id": "job-1", "period_id": "period-1", "before": period,
                           "after": period, "unit": "month", "inclusive_span": 4}]
    with pytest.raises(ValidationError, match="anchor"):
        DateCascadeProposal.model_validate(proposal, by_name=True)
