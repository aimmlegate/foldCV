"""Bundled skill reads preserve permissions, complete text and command context."""

import asyncio
from dataclasses import replace
import hashlib
import json

import httpx
import pytest

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure, run_in
from tests.recovery.test_agent_tools import tools_setup
from resume_api.agent.skills import ApplicationSkillQuery, CHAT_SKILLS, SKILLS, SkillBook, skill_catalog, skill_command


async def read_skill(session, skill_id, resource="SKILL.md"):
    query = ApplicationSkillQuery(skillId=skill_id, resource=resource)
    parts, pages, digest = [], 0, None
    while True:
        reply = await session.call("get_application_skills", query)
        assert "error" not in reply, reply
        assert len(json.dumps(reply, ensure_ascii=False, separators=(",", ":")).encode()) <= limits.PAGE_BYTES
        assert reply["offset"] == sum(len(part) for part in parts)
        assert digest is None or digest == reply["sha256"]
        digest = reply["sha256"]
        parts.append(reply["content"]); pages += 1
        if reply["nextCursor"] is None:
            result = "".join(parts).encode()
            assert len(result.decode()) == reply["totalCharacters"]
            assert hashlib.sha256(result).hexdigest() == digest
            return result, pages
        query = query.model_copy(update={"cursor": reply["nextCursor"]})


@pytest.mark.asyncio
async def test_read_only_assistant_discovers_both_skills_and_reads_every_resource_exactly(tmp_path):
    session, service, workspace, fetcher = tools_setup(tmp_path, allow_edits=False, allow_web=False,
        message="/import-resume Проверь структуру")
    try:
        before = workspace.model_dump_json()
        service.projects.catalog.update(workspace.project_id, read_only=True)
        catalog = await session.call("get_application_skills", None)
        assert {skill["skillId"] for skill in catalog["skills"]} == {"import-resume", "format-resume"}
        assert catalog["skills"][1]["usage"].startswith("legacy_reference")
        for skill in SKILLS:
            for resource, path in skill.resources.items():
                result, _ = await read_skill(session, skill.id, resource)
                assert result == path.read_bytes()
        _, run, journal = run_in(service.store.load(workspace.project_id), session.run.id)
        prompt = json.loads(session.book.initial(run, journal).split("\n", 1)[1])
        assert prompt["applicationSkills"]["command"] == {
            "command": "/import-resume", "known": True, "request": "Проверь структуру"}
        assert prompt["message"] == "/import-resume Проверь структуру"
        assert workspace.model_dump_json() == before and not fetcher.calls
        assert (await session.call("apply_edit_batch", {}))["error"]["code"] == "AGENT_TOOL_DENIED"
    finally:
        await session.close()
        assert not session.skills.documents and not session.skills.cursors


@pytest.mark.asyncio
async def test_protocol_off_keeps_the_pre_cap_model_surface(tmp_path):
    from resume_api.agent.runtime import BASE_INSTRUCTIONS, DEVELOPER_INSTRUCTIONS
    from resume_api.jobs.tools import PROTOCOL_V2_SHA256
    # Values from main before CAP: the rollout flag must leave the legacy assistant unchanged.
    assert hashlib.sha256((BASE_INSTRUCTIONS + DEVELOPER_INSTRUCTIONS).encode()).hexdigest() == (
        "49db726a4ceb575b530f3ed00849a428a77820a392aec1c82f1c487cd9c436ef")
    assert PROTOCOL_V2_SHA256 == "4cac457979542e1b7a6a310c327a06333861bc63c26e127082ab13127ab1cbdb"
    session, service, workspace, _ = tools_setup(tmp_path, allow_edits=True, allow_web=False, message="/format-resume")
    try:
        assert not service.assistant_protocol_enabled and "apply_edit_batch" in session.names
        tools = {tool.name: tool for tool in await session.sdk.list_tools()}
        assert set(tools["get_project_resources"].inputSchema["properties"]) == {"query"}
        assert "protocolVersion" not in json.dumps([tool.inputSchema for tool in tools.values()])
        task = {"protocolVersion": 1, "taskId": "rewrite_resume", "stage": "generation", "scope": "document"}
        for arguments in ({"task": task}, {"draft": {"protocolVersion": 1, "proposalId": "p", "version": 1, "cursor": None}}):
            assert session.preflight({"name": "get_project_resources", "arguments": arguments}) == "AGENT_ARGUMENT_INVALID"
        catalog = await session.call("get_application_skills", None)
        assert catalog["skills"] == skill_catalog() and all("tasks" not in skill for skill in catalog["skills"])
        _, run, journal = run_in(service.store.load(workspace.project_id), session.run.id)
        prompt = json.loads(session.book.initial(run, journal).split("\n", 1)[1])
        assert prompt["applicationSkills"]["skills"] == catalog["skills"]
        assert "continuedDraft" not in prompt and "capturedNativeHistory" not in prompt
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_protocol_mode_uses_chat_skill_adapters_and_reads_every_resource_exactly(tmp_path):
    from resume_api.agent.capabilities import proposal_instructions
    from resume_api.agent.skills import CHAT_SKILL_INSTRUCTIONS, SKILL_INSTRUCTIONS
    from tests.recovery.test_assistant_proposals import environment
    from packages.resume_core.models.assistant_capabilities import AssistantTaskRequestV1
    service, _, _, workspace, session = environment(tmp_path, message="/format-resume")
    try:
        await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId="format_document"))
        catalog = await session.call("get_application_skills", None)
        assert catalog["skills"] == skill_catalog(True)
        assert catalog["skills"][1]["usage"].startswith("chat_format")
        assert catalog["skills"][1]["tasks"][0]["taskId"] == "format_document"
        assert all("archive-contract" not in name and "data-contract" not in name for skill in catalog["skills"] for name in skill["resources"])
        for skill in CHAT_SKILLS:
            for resource, path in skill.resources.items():
                result, _ = await read_skill(session, skill.id, resource)
                assert result == path.read_bytes()
        tools = {tool.name: tool for tool in await session.sdk.list_tools()}
        assert {"query", "task", "draft"} <= set(tools["get_project_resources"].inputSchema["properties"])
        _, run, journal = run_in(service.store.load(workspace.project_id), session.run.id)
        prompt = json.loads(session.book.initial(run, journal).split("\n", 1)[1])
        assert prompt["applicationSkills"]["skills"] == catalog["skills"] and "continuedDraft" in prompt
        assert CHAT_SKILL_INSTRUCTIONS in proposal_instructions() and SKILL_INSTRUCTIONS not in proposal_instructions()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_skill_pages_keep_unicode_escapes_crlf_and_a_stable_snapshot(tmp_path, monkeypatch):
    from resume_api.agent import skills
    path = tmp_path / "SKILL.md"
    original = ('Русский 😀 "\\\r\n' * 4000).encode()
    path.write_bytes(original)
    monkeypatch.setattr(skills, "SKILLS", (replace(SKILLS[0], resources={"SKILL.md": path}),))
    session, _, _, _ = tools_setup(tmp_path, allow_edits=False, allow_web=False)
    try:
        first = await session.call("get_application_skills", ApplicationSkillQuery(skillId="import-resume"))
        assert first["nextCursor"]
        path.write_text("Changed after the read began")
        result, pages = await read_skill(session, "import-resume")
        assert result == original and pages > 1
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_skill_allowlist_cursor_binding_revocation_and_budgets(tmp_path, monkeypatch):
    from resume_api.agent import skills
    path = tmp_path / "SKILL.md"
    path.write_text("Bundled instructions.\n" * 2000)
    monkeypatch.setattr(skills, "SKILLS", (replace(SKILLS[0], resources={"SKILL.md": path}), SKILLS[1]))
    session, _, _, _ = tools_setup(tmp_path, allow_edits=False, allow_web=False)
    foreign = SkillBook()
    query = ApplicationSkillQuery(skillId="import-resume")
    try:
        for resource in ("../../../../auth.json", "/etc/passwd", "scripts/render.py", "references/data-contract.md"):
            denied = await session.call("get_application_skills", query.model_copy(update={"resource": resource}))
            assert denied == {"error": {"code": "AGENT_NOT_FOUND"}}
        page = await session.call("get_application_skills", query)
        continuation = query.model_copy(update={"cursor": page["nextCursor"]})
        assert (await session.call("get_application_skills", continuation.model_copy(update={"skill_id": "format-resume"})))["error"]["code"] == "AGENT_SCOPE_INVALID"
        with pytest.raises(AgentFailure, match="AGENT_SCOPE_INVALID"):
            foreign.read(continuation)
        assert "error" not in await session.call("get_application_skills", continuation)
        assert (await session.call("get_application_skills", continuation))["error"]["code"] == "AGENT_SCOPE_INVALID"
        session.calls = limits.TOOL_CALLS
        assert (await session.call("get_application_skills", None))["error"]["code"] == "AGENT_TOOL_LIMIT"
        session.calls = 0; session.result_bytes = limits.TOOL_TOTAL_BYTES
        assert (await session.call("get_application_skills", None))["error"]["code"] == "AGENT_TOOL_LIMIT"
        session.result_bytes = 0; session.control.cancel.set()
        assert (await session.call("get_application_skills", None))["error"]["code"] == "AGENT_CANCELLED"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_missing_bundled_resource_is_explicit_and_does_not_return_a_path(tmp_path, monkeypatch):
    from resume_api.agent import skills
    monkeypatch.setattr(skills, "SKILLS", (replace(SKILLS[0], resources={"SKILL.md": tmp_path / "missing"}),))
    session, _, _, _ = tools_setup(tmp_path, allow_edits=False, allow_web=False)
    try:
        assert await session.call("get_application_skills", ApplicationSkillQuery(skillId="import-resume")) == {
            "error": {"code": "AGENT_SOURCE_UNAVAILABLE"}}
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_authenticated_mcp_advertises_and_validates_skill_reads(tmp_path):
    session, _, _, _ = tools_setup(tmp_path, allow_edits=False, allow_web=False)
    session.application = session.sdk.streamable_http_app()
    headers = {"Authorization": "Bearer " + session.token, "Accept": "application/json, text/event-stream"}
    try:
        async with session.application.router.lifespan_context(session.application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host, headers=headers) as client:
                listed = (await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})).json()
                tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "get_application_skills")
                assert "skillId" in json.dumps(tool["inputSchema"])
                for arguments in ({"skillId": "import-resume"}, {"query": {"skillId": "PRIVATE_CANARY"}},
                        {"query": {"skillId": "import-resume", "path": "PRIVATE_CANARY"}}):
                    reply = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "get_application_skills", "arguments": arguments}})
                    assert reply.json()["result"]["isError"] and "PRIVATE_CANARY" not in reply.text
                    assert "skillId" in json.loads(reply.json()["result"]["content"][0]["text"])["format"]
                for arguments in ({}, {"query": {"skillId": "import-resume"}}):
                    reply = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "get_application_skills", "arguments": arguments}})
                    assert not reply.json()["result"].get("isError")
                    assert "PRIVATE_CANARY" not in reply.text
    finally:
        await session.close()


@pytest.mark.parametrize("message,expected", [
    ("/skills", {"command": "/skills", "known": True, "request": ""}),
    (" /format-resume\nТолько выделенный блок", {"command": "/format-resume", "known": True, "request": "Только выделенный блок"}),
    ("/unknown", {"command": "/unknown", "known": False, "request": ""}),
    ("Объясни /skills", None),
])
def test_commands_only_apply_at_the_start_and_preserve_arguments(message, expected):
    assert skill_command(message) == expected


@pytest.mark.asyncio
async def test_queued_check_only_skill_command_reads_instructions_without_publication(tmp_path):
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from tests.recovery.test_background_agent import environment
    from resume_api.agent.runtime import DEVELOPER_INSTRUCTIONS
    from resume_api.jobs.tools import DEVELOPER_INSTRUCTIONS_V2

    service, factory, workspace, payload, _, _ = await environment(tmp_path)
    payload.request.allow_edits = payload.request.allow_web = False
    payload.request.message = "/format-resume"
    checked = []
    before = service.projects.storage.read_committed(workspace.project_id)[0]

    async def execute(control, _actor):
        session = service.tools.session(control)
        try:
            assert "get_application_skills" in session.names and "apply_edit_batch" not in session.names
            context = json.loads(session.prompt.split("\n", 1)[1])
            assert context["applicationSkills"]["command"]["command"] == "/format-resume"
            result, _ = await read_skill(session, "format-resume")
            checked.append(result == SKILLS[1].resources["SKILL.md"].read_bytes())
            for instructions in (DEVELOPER_INSTRUCTIONS, DEVELOPER_INSTRUCTIONS_V2):
                assert "get_application_skills" in instructions and "They do not grant edit permission" in instructions
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()

    factory.callbacks[payload.request.client_request_id] = execute
    try:
        job, _ = await service.submit(workspace.project_id, payload)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        failure = service.supervisor.controls[job.id].run_task.exception()
        if failure is not None:
            raise failure
        assert checked == [True]
        assert service.projects.storage.read_committed(workspace.project_id)[0] == before
    finally:
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()
