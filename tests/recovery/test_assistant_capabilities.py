"""Task readiness is local metadata and never grants publication authority."""

from typing import get_args
from types import SimpleNamespace
import asyncio

import httpx

import pytest
from pydantic import ValidationError

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.models.assistant_capabilities import (
    AssistantMessageCheckV1, AssistantTaskRequestV1, TaskId,
)
from tests.recovery.test_agent_lifecycle import setup
from tests.recovery.test_agent_routes import application, enabled
from tests.recovery.test_agent_tools import tools_setup
from resume_api.agent.capabilities import TASKS, catalog, check_message, check_task
from resume_api.agent.service import AgentConnection


def by_id(value):
    return {task.id: task for task in value.tasks}


def test_read_only_catalog_separates_generation_preparation_and_apply(tmp_path):
    service, runtime, _, workspace, _, _, _ = setup(tmp_path, None)
    service.assistant_protocol_enabled = True
    value = catalog(service, workspace.project_id, allow_edits=False, allow_web=False)
    tasks = by_id(value)
    assert set(tasks) == set(get_args(TaskId)) == {task.id for task in TASKS}
    assert value.protocol_enabled and value.editor_family == "ordinary"
    for name in ("read_resume", "check_resume", "draft_text", "rewrite_resume"):
        assert tasks[name].generation.state == tasks[name].preparation.state == "available"
    assert tasks["rewrite_resume"].apply.state == "permission_disabled"
    assert tasks["read_public_page"].preparation.state == "permission_disabled"
    assert "Вставьте" in tasks["read_public_page"].preparation.remedy
    assert tasks["export_docx"].apply.state == "permission_disabled"
    assert tasks["export_docx"].generation.state == "permission_disabled"
    assert not runtime.calls


def test_provider_unavailable_does_not_disable_local_review_or_preparation(tmp_path):
    service, runtime, projects, workspace, _, request, connection = setup(tmp_path, None)
    first = catalog(service, workspace.project_id)
    connection["value"] = AgentConnection(False, (), "account_1", "AGENT_CONNECTION_UNAVAILABLE")
    tasks = by_id(catalog(service, workspace.project_id))
    assert tasks["rewrite_resume"].generation.state == "temporarily_unavailable"
    assert tasks["rewrite_resume"].preparation.state == tasks["rewrite_resume"].review.state == "available"
    assert tasks["rewrite_resume"].apply.state == "available"
    connection["value"] = AgentConnection(False, (), "account_2", "AGENT_CONNECTION_CHANGED")
    second = catalog(service, workspace.project_id)
    assert second.catalog_revision != first.catalog_revision
    assert by_id(second)["rewrite_resume"].apply.state == "permission_disabled"
    service.leases.close(workspace.project_id, request.owner)
    connection["value"] = AgentConnection(True, ("assistant-model",), "account_1")
    assert by_id(catalog(service, workspace.project_id))["rewrite_resume"].apply.reason_code == "ASSISTANT_OWNER_REQUIRED"
    projects.agent_recovery_fences.add(workspace.project_id)
    assert by_id(catalog(service, workspace.project_id))["rewrite_resume"].apply.reason_code == "AGENT_OUTCOME_UNKNOWN"
    assert not runtime.calls


@pytest.mark.parametrize("message,task", [("Экспортируй резюме в PDF", "export_pdf"),
    ("Run shell", "shell"), ("Открой приложение Word", "apps"), ("Send application", "send_application")])
def test_unambiguous_unsupported_request_is_rejected_before_runtime(tmp_path, message, task):
    service, runtime, _, workspace, _, request, _ = setup(tmp_path, None)
    service.assistant_protocol_enabled = True
    result = check_message(catalog(service, workspace.project_id), AssistantMessageCheckV1(
        protocolVersion=1, message=message, allowEdits=True, allowWeb=True))
    assert result.task_id == task and result.availability.state == "unsupported"
    assert result.availability.remedy and not result.needs_planning
    with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
        service.submit(workspace.project_id, request.model_copy(update={"message": message}))
    assert not runtime.calls


def test_ambiguous_prose_needs_planning_and_task_checks_are_precise(tmp_path):
    service, runtime, _, workspace, _, _, _ = setup(tmp_path, None)
    value = catalog(service, workspace.project_id)
    result = check_message(value, AssistantMessageCheckV1(
        protocolVersion=1, message="Объясни упоминание PDF в моём резюме", allowEdits=False, allowWeb=False))
    assert result.task_id is None and result.needs_planning and result.availability.state == "available"
    missing = check_task(value, AssistantTaskRequestV1(protocolVersion=1, taskId="correct_facts", inputAvailable=False))
    assert missing.availability.state == "missing_input"
    wrong_scope = check_task(value, AssistantTaskRequestV1(protocolVersion=1, taskId="format_document", scope="selection"))
    assert wrong_scope.availability.reason_code == "ASSISTANT_SCOPE_UNSUPPORTED"
    for supplied in ({"taskId": "invented"}, {"taskId": "read_resume", "protocolVersion": 2},
                     {"taskId": "read_resume", "protocolVersion": True}):
        with pytest.raises(ValidationError):
            AssistantTaskRequestV1.model_validate(supplied)
    assert not runtime.calls


def test_template_catalog_is_explicit_without_mounting_a_partial_chat_adapter(tmp_path, monkeypatch):
    service, runtime, projects, workspace, _, _, _ = setup(tmp_path, None)
    monkeypatch.setattr(projects, "read", lambda _project: SimpleNamespace(schema_version=7,
        project=workspace.project, project_id=workspace.project_id, created_at=workspace.created_at))
    value = catalog(service, workspace.project_id)
    assert value.editor_family == "template"
    assert all(task.generation.state == task.preparation.state == task.apply.state == "unsupported" for task in value.tasks)
    assert all(task.review.reason_code == "ASSISTANT_TEMPLATE_UNAVAILABLE" and task.review.remedy for task in value.tasks)
    assert not runtime.calls


@pytest.mark.asyncio
async def test_background_admission_and_raw_apply_share_the_catalog_fence(tmp_path):
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from packages.resume_core.models.agent import AgentApplyRequest
    from tests.recovery.test_background_agent import environment, hold_writer
    jobs, factory, workspace, payload, _, service = await environment(tmp_path)
    service.assistant_protocol_enabled = True
    before = jobs.projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    try:
        unsupported = payload.model_copy(deep=True)
        unsupported.request.message = "Run shell"
        with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
            await jobs.submit(workspace.project_id, unsupported)
        assert not factory.calls
        first = catalog(service, workspace.project_id)
        hold_writer(jobs, workspace)
        changed = catalog(service, workspace.project_id)
        assert changed.catalog_revision != first.catalog_revision
        assert by_id(changed)["rewrite_resume"].apply.state == "temporarily_unavailable"

        async def execute(control, _actor):
            session = jobs.tools.session(control)
            try:
                result = await session.call("apply_edit_batch", AgentApplyRequest(batchId="forged_batch"))
                assert result["error"]["code"] == "AGENT_TOOL_DENIED"
                return ExecutionOutcome(finished_at=jobs.supervisor.clock.now())
            finally:
                await session.close()
        factory.callbacks[payload.request.client_request_id] = execute
        job, _ = await jobs.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(jobs.supervisor.controls[job.id].task, 10)
        assert jobs.projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
    finally:
        await jobs.shutdown()
        factory.verify(); jobs.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_raw_invocation_cannot_bypass_catalog_or_supply_approval(tmp_path):
    session, service, workspace, fetcher = tools_setup(tmp_path, allow_edits=False, allow_web=False, protocol=True)
    try:
        assert (await session.call("check_resume", None))["error"]["code"] == "AGENT_TOOL_DENIED"
        task = await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId="rewrite_resume"))
        assert task["availability"]["state"] == "available"
        assert not fetcher.calls
        result = await session.call("read_public_page", "https://example.org")
        assert result["error"]["code"] == "AGENT_WEB_DISABLED"
        assert (await session.call("apply_edit_batch", {}))["error"]["code"] == "AGENT_TOOL_DENIED"
        await session.start()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host,
                headers={"Authorization": "Bearer " + session.token,
                "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}) as client:
            denied = await client.post(session.url, json={"jsonrpc": "2.0", "id": 1,
                "method": "tools/call", "params": {"name": "get_project_resources",
                    "arguments": {"task": {"protocolVersion": 1, "taskId": "shell"}}}})
            assert denied.status_code == 200 and "unsupported" in denied.text
            raw = await client.post(session.url, json={"jsonrpc": "2.0", "id": 2,
                "method": "tools/call", "params": {"name": "check_resume", "arguments": {}}})
            assert raw.status_code == 200 and "AGENT_TOOL_DENIED" in raw.text
        from packages.resume_core import agent_limits as limits
        session.calls = limits.TOOL_CALLS - 1
        assert (await session.call("check_resume", None))["error"]["code"] == "AGENT_TOOL_DENIED"
        assert session.calls == limits.TOOL_CALLS
        assert (await session.call("check_resume", None))["error"]["code"] == "AGENT_TOOL_LIMIT"
        assert not fetcher.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_catalog_routes_require_cookie_protocol_and_strict_flags_without_inference(tmp_path):
    async with application(tmp_path, None) as (client, _, service, workspace, _, prefix, runtime, _):
        await enabled(client)
        service.assistant_protocol_enabled = True
        headers = {"X-FoldCV-Assistant-Protocol": "1", "X-FoldCV-Agent-Edits": "0", "X-FoldCV-Agent-Web": "0"}
        result = await client.get(prefix + "/tasks", headers=headers)
        assert result.status_code == 200
        assert result.json()["projectId"] == workspace.project_id
        assert (await client.get(prefix + "/tasks")).status_code == 409
        assert (await client.get(prefix + "/tasks", headers={**headers, "X-FoldCV-Agent-Web": "yes"})).status_code == 409
        duplicate = [("X-FoldCV-Assistant-Protocol", "1"), ("X-FoldCV-Assistant-Protocol", "1")]
        assert (await client.get(prefix + "/tasks", headers=duplicate)).status_code == 409
        body = {"schemaVersion": 1, "protocolVersion": 1, "message": "Экспортируй PDF", "allowEdits": False, "allowWeb": False}
        checked = await client.post(prefix + "/tasks/check-message", json=body, headers=headers)
        assert checked.status_code == 200 and checked.json()["availability"]["state"] == "unsupported"
        assert (await client.post(prefix + "/tasks/check-message", json={**body, "protocolVersion": 2}, headers=headers)).status_code == 422
        client.cookies.clear()
        assert (await client.get(prefix + "/tasks", headers=headers)).status_code == 401
        assert not runtime.calls
