"""Portable sync explanations cannot restore local execution authority."""

import hashlib
import json

import pytest

from packages.resume_core.background_store import JobStore
from packages.resume_core.gui_archive_zip import json_bytes, read_zip, write_zip
from packages.resume_core.models.rich_workspace import RichSyncRecord
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.rules import RulesStore
from tests.recovery.test_background_inverse import mutation, put
from tests.support.agent import isolated_project


def pending(workspace, status):
    request = mutation(workspace, [put(workspace, "narrative", text="Unpublished portable patch")])
    return RichSyncRecord(id="local-sync", status=status, actionId="local-action", blockIds=["narrative"],
        fieldKeys=["role"], factIds=["job-1"], dependencies=[dependency(workspace, "block", "narrative")],
        errorCode="SEMANTIC_WARNING" if status == "conflict" else None, kind="rewrite", ready=True,
        proposedSteps=request.steps, instruction="Keep the domain explanation for explicit review.",
        selection={"kind": "blocks", "anchor": {"blockId": "narrative", "cellId": None, "offset": 0},
            "head": {"blockId": "narrative", "cellId": None, "offset": 1}, "blockIds": ["narrative"],
            "capture": request.capture.model_dump(by_alias=True), "textSha256": "a" * 64})


def legacy_archive(data, workspace):
    files = read_zip(data)
    raw = json_bytes(workspace.model_dump(mode="json", by_alias=True))
    files["workspace.json"] = raw
    manifest = json.loads(files["manifest.json"])
    entry = next(item for item in manifest["entries"] if item["path"] == "workspace.json")
    entry["sha256"], entry["size"] = hashlib.sha256(raw).hexdigest(), len(raw)
    files["manifest.json"] = json_bytes(manifest)
    return write_zip(files)


@pytest.mark.parametrize("variant", ["NB-F04:v04", "NB-F04:v05"])
def test_portable_copies_and_old_ready_archives_keep_only_inert_domain_history(tmp_path, variant):
    from resume_api.rich_projects import RichProjectService
    for status in ("pending", "conflict", "applied", "failed"):
        root = tmp_path / status
        _old, canonical, workspace, _conversation = isolated_project(root / "original")
        workspace.sync_records = [pending(workspace, status)]
        canonical.save(workspace, {}, {})
        original = canonical.read_committed(workspace.project_id)[0]
        old_lineage = JobStore(canonical.root).open(workspace.project_id).lineage
        archive = export_rich_archive(workspace, {}, {}, {})
        if variant == "NB-F04:v05":
            archive = legacy_archive(archive, workspace)
        original_bytes = archive
        if variant == "NB-F04:v04":
            exported = json.loads(read_zip(archive)["workspace.json"])
            projected = exported["syncRecords"][0]
            assert projected["proposedSteps"] == projected["dependencies"] == []
            assert projected["ready"] is False and projected["selection"] is None
        imported, _sources, _renders, _images = open_rich_archive(archive, "imported")
        record = imported.sync_records[0]
        assert not record.ready and not record.proposed_steps and not record.dependencies and record.selection is None
        assert record.status == ("stale" if status == "pending" else status)
        assert record.instruction == workspace.sync_records[0].instruction and record.action_id == "local-action"
        assert record.fact_ids == ["job-1"] and record.field_keys == ["role"]
        if status == "conflict":
            assert record.error_code == "SEMANTIC_WARNING"
        assert archive == original_bytes and workspace == original
        assert canonical.read_committed(workspace.project_id)[0] == original
        destination = root / "destination"
        service = RichProjectService(root / "operations", RulesStore(destination), lambda: None,
            storage=RichProjectStore(destination))
        identifier = service.import_portable(archive)
        restored = service.storage.read_committed(identifier)[0]
        assert restored.schema_version == 6 and not restored.sync_records[0].ready and not restored.mutation_replay
        fresh = JobStore(destination).open(identifier)
        assert fresh.lineage != old_lineage and not fresh.jobs and not fresh.proposals and not fresh.intents
