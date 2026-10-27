"""Rich document, facts, image and mutation models: identity, ownership and bounds the validators add."""

from copy import deepcopy

from pydantic import ValidationError
import pytest

from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.models.rich_facts import WorkingFacts
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.models.rich_workspace import LocalImageAsset, WorkspaceV6
from packages.resume_core.rich_limits import MIB
from tests.support.rich import fixture as workspace


def fixture():
    return workspace().model_dump()


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


def test_rich_document_requires_the_fixed_region_reading_order():
    document = fixture()["project"]["document"]
    document["regions"].reverse()
    with pytest.raises(ValidationError, match="fixed region reading order"):
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


def asset(asset_id, size, hash_digit="a"):
    return LocalImageAsset(id=asset_id, sha256=hash_digit * 64, path=f"images/{hash_digit * 64}.png",
                           mimeType="image/png", size=size, width=1000, height=1000)


@pytest.mark.parametrize("patch,message", [({"width": 5001, "height": 5000}, "25 megapixels"),
    ({"path": "../image.png"}, "hash and format"), ({"path": "https://example.com/image.png"}, "hash and format"),
    ({"path": "images/" + "a" * 64 + ".jpg"}, "hash and format")])
def test_rich_image_path_follows_its_hash_and_format_and_pixels_are_bounded(patch, message):
    data = asset("image-1", MIB).model_dump()
    LocalImageAsset.model_validate(data, by_name=True)
    data.update(patch)
    with pytest.raises(ValidationError, match=message):
        LocalImageAsset.model_validate(data, by_name=True)


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


@pytest.mark.parametrize("status,value,pending,revision", [
    ("conflict", None, None, 1), ("pending", None, "2 years", 1),
    ("known", "2 years", None, 1), ("unresolved", None, None, 2),
])
def test_experience_nondefault_state_survives_json(status, value, pending, revision):
    from packages.resume_core.models.rich_facts import TechnologyRecord, TextField
    field = TextField(value=value, rawText="", status=status, revision=revision, pendingRawText=pending)
    record = TechnologyRecord(id="technology", kind="technology", revision=revision, origin="source", evidence=[],
        jobId=None, subprojectId=None, display=field.model_copy(update={"value": "Python", "status": "known", "pending_raw_text": None}),
        canonicalId=field.model_copy(update={"value": "python", "status": "known", "pending_raw_text": None}), experience=field)
    assert TechnologyRecord.model_validate_json(record.model_dump_json(by_alias=True)).experience == field


@pytest.mark.parametrize("value", ["", " \n\t"])
def test_known_text_must_be_nonblank(value):
    from packages.resume_core.models.rich_facts import TextField
    with pytest.raises(ValidationError):
        TextField(value=value, rawText=value, status="known", revision=1, pendingRawText=None)
