"""Catalog actions keep durable receipts across capacity and uncertain writes."""

import json
import os
from unittest.mock import patch

import pytest

from packages.resume_core.agent_store import digest
from packages.resume_core.models.agent import AgentProjectAction
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.storage import atomic_write
from tests.recovery.test_agent_tools import tools_setup
from tests.recovery.test_manual_qa_project_actions import complete_resources
from tests.recovery.test_agent_edits import selection
from resume_api.agent.project_action_recovery import recover_actions
from resume_api.gui_projects import ProjectFailure


def request(session, **changes):
    return AgentProjectAction(key="rename-once", snapshotId=complete_resources(session), action="rename",
        value="Renamed project", **changes)


def fill_catalog(catalog, count, padding=0):
    state = catalog._read()
    state.actions = {str(index): json.dumps({"runId": "old", "status": "completed", "padding": "x" * padding})
        for index in range(count)}
    atomic_write(catalog.path, state.model_dump_json(by_alias=True).encode())


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["count", "bytes", "last-slot"])
async def test_catalog_reserves_capacity_before_changing_the_workspace(tmp_path, limit):
    session, service, workspace, _ = tools_setup(tmp_path)
    projects = service.projects
    try:
        command = request(session)
        fill_catalog(projects.catalog, 499 if limit == "last-slot" else 500 if limit == "count" else 1,
            4 * 1024 * 1024 - 700 if limit == "bytes" else 0)
        before, checksum = projects.storage.read_committed(workspace.project_id)
        result = await session.call("project_action", command)
        retained, after = projects.storage.read_committed(workspace.project_id)
        if limit == "last-slot":
            assert result["durable"] and retained.title == command.value
            assert len(projects.catalog.actions()) == 500
            assert await session.call("project_action", command) == result
        else:
            assert result["error"]["code"] == "AGENT_SAVE_FAILED", result
            assert after == checksum and retained == before
            assert projects.workspaces[workspace.project_id].title == before.title
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["before", "after"])
async def test_workspace_write_failure_is_resolved_without_repeating_the_mutation(tmp_path, failure):
    session, service, workspace, _ = tools_setup(tmp_path)
    projects = service.projects
    try:
        command = request(session)
        before = projects.storage.read_committed(workspace.project_id)[0]
        persist = projects.persist
        def fail(identifier):
            if failure == "after":
                persist(identifier)
            raise OSError("synthetic save interruption")
        with patch.object(projects, "persist", side_effect=fail):
            result = await session.call("project_action", command)
        assert result.get("durable", False) == (failure == "after"), result
        retained = projects.storage.read_committed(workspace.project_id)[0]
        assert retained.project_revision == before.project_revision + (failure == "after")
        assert projects.workspaces[workspace.project_id] == retained
        with patch.object(projects, "persist", side_effect=AssertionError("must replay the receipt")):
            assert await session.call("project_action", command) == result
        changed = command.model_copy(update={"snapshot_id": complete_resources(session)})
        assert (await session.call("project_action", changed))["error"]["code"] == "AGENT_IDEMPOTENCY_CONFLICT"
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["rename", "export_project"])
async def test_failed_directory_sync_never_claims_a_durable_result(tmp_path, action):
    session, service, workspace, _ = tools_setup(tmp_path)
    projects = service.projects
    try:
        command = request(session).model_copy(update={"action": action})
        target = projects.storage._directory(workspace.project_id)
        if action == "export_project":
            target = target / "renders"
            target.mkdir(mode=0o700)
        inode = target.stat().st_ino
        real_sync = os.fsync
        def sync(descriptor):
            if os.fstat(descriptor).st_ino == inode:
                raise OSError("synthetic directory sync failure")
            real_sync(descriptor)
        with patch("os.fsync", side_effect=sync):
            result = await session.call("project_action", command)
        assert result["error"]["code"] == "AGENT_OUTCOME_UNKNOWN", result
        assert workspace.project_id in projects.catalog_recovery_fences
        with pytest.raises(ProjectFailure, match="AGENT_OUTCOME_UNKNOWN"):
            projects.require_agent_writable(workspace.project_id)
        recover_actions(projects)
        assert workspace.project_id not in projects.catalog_recovery_fences
        assert (await session.call("project_action", command))["durable"]
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [False, True])
async def test_receipt_failure_recovers_before_restart_cleanup_even_when_read_only(tmp_path, saved):
    from packages.resume_core.rules import RulesStore
    from packages.resume_core.rich_project_store import RichProjectStore
    from resume_api.rich_projects import RichProjectService
    session, service, workspace, _ = tools_setup(tmp_path)
    projects = service.projects
    try:
        command = request(session)
        real_record = projects.catalog.record_action
        def record(key, value):
            if value["status"] != "applying":
                raise OSError("synthetic receipt failure")
            real_record(key, value)
        with patch.object(projects.catalog, "record_action", side_effect=record), patch.object(projects, "persist",
                wraps=projects.persist if saved else lambda _identifier: "failed"):
            result = await session.call("project_action", command)
        assert result["error"]["code"] == "AGENT_OUTCOME_UNKNOWN"
        projects.catalog.update(workspace.project_id, read_only=True)
        storage = RichProjectStore(projects.storage.root)
        restarted = RichProjectService(tmp_path / "restart-operations", RulesStore(storage.root), lambda: None, storage=storage)
        restarted.agent_recovery_fences.add(workspace.project_id)
        restarted.ensure_loaded()
        retained = restarted.storage.read_committed(workspace.project_id)[0]
        assert (retained.title == command.value) == saved
        receipt = restarted.catalog.actions()[digest([workspace.project_id, session.run.id, command.key])]
        assert receipt["status"] == ("completed" if saved else "failed")
        assert receipt["result"].get("durable", False) == saved
        assert workspace.project_id not in restarted.catalog_recovery_fences
        assert workspace.project_id in restarted.agent_recovery_fences
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["rename", "formatting_date", "archive", "restore", "delete", "undo", "redo", "export_project"])
async def test_project_actions_cannot_expand_a_selection_scope(tmp_path, action):
    session, service, workspace, _ = tools_setup(tmp_path, scope_builder=lambda ws: selection(ws, "title", 0, 8),
        message="Delete this project or archive and restore it.")
    try:
        before = service.projects.storage.read_committed(workspace.project_id)[1]
        result = await session.call("project_action", request(session).model_copy(update={"action": action}))
        assert result["error"]["code"] == "AGENT_SCOPE_INVALID", result
        assert not service.projects.catalog.actions()
        assert service.projects.storage.read_committed(workspace.project_id)[1] == before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_unproved_changed_workspace_remains_fenced_and_never_retries(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    projects = service.projects
    try:
        command = request(session)
        def uncertain(identifier):
            candidate = projects.read_memory(identifier)
            candidate.mutation_replay.clear()
            projects.storage.save(candidate, projects.originals, projects.artifacts, projects.images)
            raise OSError("synthetic unproved outcome")
        with patch.object(projects, "persist", side_effect=uncertain):
            result = await session.call("project_action", command)
        assert result["error"]["code"] == "AGENT_OUTCOME_UNKNOWN"
        recover_actions(projects)
        assert workspace.project_id in projects.catalog_recovery_fences
        with patch.object(projects, "persist", side_effect=AssertionError("must not repeat an uncertain write")):
            assert (await session.call("project_action", command))["error"]["code"] == "AGENT_OUTCOME_UNKNOWN"
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["export_docx", "add_source_text"])
async def test_revocation_during_async_preparation_cannot_commit_a_project_action(tmp_path, action):
    from resume_api.agent import project_actions
    session, service, workspace, _ = tools_setup(tmp_path, message="Add this source: Synthetic source text.")
    projects = service.projects
    try:
        command = request(session).model_copy(update={"action": action, "value": "Synthetic source text."})
        before = projects.storage.read_committed(workspace.project_id)[1]
        extract = project_actions.run_extract
        async def cancelled_extract(*args, **kwargs):
            result = await extract(*args, **kwargs)
            session.control.cancel.set()
            return result
        async def cancelled_render(*_args):
            session.control.cancel.set()
            return b"synthetic-docx-result"
        with patch.object(project_actions, "run_extract", side_effect=cancelled_extract), patch.object(
                projects.renderer, "render", side_effect=cancelled_render):
            result = await session.call("project_action", command)
        assert result["error"]["code"] == "AGENT_CANCELLED", result
        assert not projects.catalog.actions()
        assert projects.storage.read_committed(workspace.project_id)[1] == before
        assert not projects.originals
        assert not list((projects.storage._directory(workspace.project_id) / "renders").glob("*"))
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_failed_save_and_terminal_catalog_sync_restore_cache_before_replay(tmp_path):
    import stat
    session, service, workspace, _ = tools_setup(tmp_path)
    projects = service.projects
    try:
        command = request(session)
        before = projects.storage.read_committed(workspace.project_id)[0]
        real_sync, directories = os.fsync, []
        def sync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode) and os.fstat(descriptor).st_ino == projects.storage.root.stat().st_ino:
                directories.append(descriptor)
                if len(directories) == 2:
                    raise OSError("synthetic terminal catalog sync failure")
            real_sync(descriptor)
        with patch.object(projects, "persist", return_value="failed"), patch("os.fsync", side_effect=sync):
            result = await session.call("project_action", command)
        assert result["error"]["code"] == "AGENT_OUTCOME_UNKNOWN"
        assert projects.workspaces[workspace.project_id] == before
        replay = await session.call("project_action", command)
        assert replay["error"]["code"] == "AGENT_SAVE_FAILED"
        assert workspace.project_id not in projects.catalog_recovery_fences
        assert projects.persist(workspace.project_id) == "durable"
        assert projects.storage.read_committed(workspace.project_id)[0] == before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_background_project_action_preserves_the_canonical_coordinator(tmp_path):
    import asyncio
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from tests.recovery.test_background_agent import environment
    jobs, factory, workspace, payload, _connection, _foreground = await environment(tmp_path)
    results = []
    async def once(control, actor):
        session = jobs.tools.session(control)
        try:
            request_command = request(session)
            result = await session.call("project_action", request_command)
            assert result.get("durable"), result
            assert await session.call("project_action", request_command) == result
            results.append(result)
            return ExecutionOutcome(finished_at=jobs.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = once
    try:
        job, _ = await jobs.submit(workspace.project_id, payload)
        actor = await factory.actor(job)
        await asyncio.wait_for(actor.closed.wait(), 10)
        await asyncio.wait_for(jobs.supervisor.controls[job.id].task, 10)
        error = jobs.supervisor.controls[job.id].run_task.exception()
        if error is not None:
            raise error
        assert len(results) == 1
        assert jobs.projects.storage.read_committed(workspace.project_id)[0].title == "Renamed project"
        state = jobs.store.load(workspace.project_id)
        assert state.history is not None and state.manual_intents
        assert all(intent.phase in {"receipt_stored", "reconciled"} for intent in state.manual_intents)
    finally:
        await jobs.shutdown()
        factory.verify(); jobs.supervisor.clock.verify()
