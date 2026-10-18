"""Catalog operations preserve identity and do not decode old workspaces."""

import json
from pathlib import Path

import pytest

from packages.resume_core.project_catalog import ProjectCatalog
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.rules import RulesStore
from resume_api.gui_projects import ProjectFailure
from resume_api.rich_projects import RichProjectService
from tests.recovery.test_rich_persistence import without_sources


def setup(root):
    store = RichProjectStore(root)
    workspace = without_sources()
    store.save(workspace, {}, {})
    other = workspace.model_copy(deep=True)
    other.project_id = other.project.project_id = "other"
    store.save(other, {}, {})
    service = RichProjectService(root / "operations", RulesStore(root), lambda: None, storage=store)
    return service, workspace, other


def test_explicit_open_alone_updates_recency_and_archive_survives_restart(tmp_path):
    service, first, other = setup(tmp_path)
    service.activate(first.project_id)
    initial = service.catalog.get(first.project_id).last_opened_at
    service.response(first.project_id); service.persist(first.project_id); service.listing()
    assert service.catalog.get(first.project_id).last_opened_at == initial
    service.activate(other.project_id)
    assert service.listing()["entries"][0]["projectId"] == other.project_id
    service.archive_entry(first.project_id, True)
    restarted = RichProjectService(tmp_path / "restart", RulesStore(tmp_path), lambda: None)
    entries = {entry["projectId"]: entry for entry in restarted.listing()["entries"]}
    assert entries[first.project_id]["archived"] and not entries[other.project_id]["archived"]
    before = restarted.storage.read_committed(first.project_id)[0]
    restarted.archive_entry(first.project_id, False)
    assert restarted.storage.read_committed(first.project_id)[0] == before
    assert restarted.catalog.get(first.project_id).last_opened_at == initial


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [5, 99, "unreadable"])
async def test_old_and_unreadable_owned_entries_archive_delete_without_opening(version, tmp_path):
    service, first, other = setup(tmp_path)
    target = tmp_path / "projects" / first.project_id / "workspace.json"
    if version == "unreadable":
        target.write_bytes(b"broken workspace")
    else:
        value = json.loads(target.read_bytes()); value["schemaVersion"] = version
        target.write_text(json.dumps(value))
    before = target.read_bytes()
    service = RichProjectService(tmp_path / "restart", RulesStore(tmp_path), lambda: None)
    with pytest.raises(ProjectFailure):
        service.activate(first.project_id)
    assert service.catalog.get(first.project_id).last_opened_at is None
    service.archive_entry(first.project_id, True)
    assert target.read_bytes() == before
    result = await service.delete_project(first.project_id)
    assert result.status == "deleted" and not target.exists()
    assert service.read(other.project_id) == other


@pytest.mark.asyncio
async def test_cleanup_is_retryable_and_an_unrelated_file_never_becomes_a_delete_target(tmp_path):
    service, first, other = setup(tmp_path)
    directory = tmp_path / "projects" / first.project_id
    extra = directory / "unknown-user-file.txt"
    extra.write_text("Keep until inspected")
    result = await service.delete_project(first.project_id)
    assert result.status == "cleanup_incomplete" and extra.read_text() == "Keep until inspected"
    assert service.read(other.project_id) == other
    extra.unlink()
    assert (await service.delete_project(first.project_id)).status == "deleted"


def test_catalog_access_and_archive_never_follow_project_symlinks(tmp_path):
    service, first, _ = setup(tmp_path / "owned")
    outside = tmp_path / "outside"; outside.mkdir(); sentinel = outside / "keep.txt"; sentinel.write_text("Keep")
    target = service.storage.projects / "linked"
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectStoreFailure):
        service.catalog.update("linked", archived=True)
    assert sentinel.read_text() == "Keep"
