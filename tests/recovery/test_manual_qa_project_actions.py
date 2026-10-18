"""Bound project operations share domain validation and live write authority."""

import base64
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

from packages.resume_core.agent_store import run_in
from packages.resume_core.models.agent import AgentProjectAction, AgentQuery
from tests.recovery.test_agent_tools import tools_setup


def complete_resources(session):
    query = AgentQuery(kind="resources")
    page = session.book.read(query)
    while page.snapshot.next_cursor:
        page = session.book.read(query.model_copy(update={"cursor": page.snapshot.next_cursor}))
    return page.snapshot.id


@pytest.mark.asyncio
@pytest.mark.parametrize("action,value", [("rename", "Updated project"), ("formatting_date", "2026-10-17"),
    ("add_source_text", "Explicit extra source 42."), ("archive", ""), ("restore", ""),
    ("export_docx", ""), ("export_project", ""), ("import_asset", "image")])
async def test_project_action_is_durable_bound_and_idempotent_without_inference(action, value, tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, message="Archive or restore this project and update its contents. " + value)
    if value == "image":
        image = BytesIO(); Image.new("RGB", (3, 2), "red").save(image, format="PNG")
        value = base64.b64encode(image.getvalue()).decode()
    try:
        before = workspace.project.document.model_dump_json()
        request = AgentProjectAction(key="operation", snapshotId=complete_resources(session), action=action, value=value)
        result = await session.call("project_action", request)
        assert result.get("durable") is True, result
        assert await session.call("project_action", request) == result
        retained = service.projects.storage.read_committed(workspace.project_id)[0]
        assert retained.project.document.model_dump_json() == before
        assert len(service.projects.catalog.actions()) == 1
        if action == "rename":
            assert retained.title == value
        if action == "add_source_text":
            assert retained.project.sources[-1].units[0].text == value
            assert service.projects.originals[(workspace.project_id, result["sourceId"])] == value.encode()
        if action == "import_asset":
            assert retained.project.assets[-1].id == result["assetId"]
        if action.startswith("export_"):
            target = service.projects.storage.projects / workspace.project_id / "renders" / result["downloadUrl"].rsplit("/", 1)[1]
            assert target.is_file() and target.stat().st_size == result["bytes"]
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["rename", "formatting_date", "add_source_text", "remove_source", "import_asset",
    "remove_asset", "export_docx", "export_project", "archive", "restore", "delete", "undo", "redo"])
async def test_read_only_rejects_every_indirect_project_write_without_changing_files(action, tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, allow_edits=False)
    try:
        snapshot = complete_resources(session)
        root = service.projects.storage.root
        before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*")
            if path.is_file() and not path.name.endswith(".lock")}
        result = await session.call("project_action", AgentProjectAction(key="blocked", snapshotId=snapshot, action=action))
        assert result["error"]["code"] == "AGENT_TOOL_DENIED"
        after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*")
            if path.is_file() and not path.name.endswith(".lock")}
        assert after == before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_explicit_delete_waits_for_turn_cleanup_and_uses_the_shared_lifecycle(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, message="Delete this project.")
    try:
        result = await session.call("project_action", AgentProjectAction(key="delete", snapshotId=complete_resources(session), action="delete"))
        assert result["durableIntent"] and not result["durable"]
        assert service.projects.storage.read_committed(workspace.project_id)[0].project is not None
        service.store.finish(workspace.project_id, session.run.id, "completed", native_completed=True)
        await service.projects.drain_catalog_actions(run_id=session.run.id)
        assert not (service.projects.storage.projects / workspace.project_id).exists()
        receipt = next(iter(service.projects.catalog.actions().values()))
        assert receipt["status"] == "deleted" and receipt["result"]["durable"]
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["stop", "read_only", "new_revision"])
async def test_deferred_delete_cannot_outlive_stop_permission_or_a_project_change(reason, tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, message="Delete this project.")
    try:
        result = await session.call("project_action", AgentProjectAction(key="delete", snapshotId=complete_resources(session), action="delete"))
        assert result["durableIntent"]
        service.store.finish(workspace.project_id, session.run.id, "cancelled" if reason == "stop" else "completed",
            error="AGENT_CANCELLED" if reason == "stop" else None, native_completed=reason != "stop")
        if reason == "read_only":
            service.projects.catalog.update(workspace.project_id, read_only=True)
        elif reason == "new_revision":
            workspace.project_revision += 1
            workspace.project.revision = workspace.project_revision
            service.projects.persist(workspace.project_id)
        await service.projects.drain_catalog_actions(run_id=session.run.id)
        assert (service.projects.storage.projects / workspace.project_id).exists()
        receipt = next(iter(service.projects.catalog.actions().values()))
        assert receipt["status"] == "cancelled" and not receipt["result"]["durable"]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_deferred_delete_preserves_project_when_its_run_cannot_be_recovered(tmp_path):
    from packages.resume_core.agent_store import AgentFailure
    session, service, workspace, _ = tools_setup(tmp_path, message="Delete this project.")
    try:
        result = await session.call("project_action", AgentProjectAction(key="delete", snapshotId=complete_resources(session), action="delete"))
        assert result["durableIntent"]
        with patch.object(service.store, "load", side_effect=AgentFailure("AGENT_NOT_FOUND")):
            await service.projects.drain_catalog_actions(run_id=session.run.id)
        assert service.projects.storage.read_committed(workspace.project_id)[0].project is not None
        receipt = next(iter(service.projects.catalog.actions().values()))
        assert receipt["status"] == "cancelled" and not receipt["result"]["durable"]
    finally:
        await session.close()
