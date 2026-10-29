"""The private MCP listener (agent/mcp) of a run: bearer-only access, envelope checks before the SDK, owned socket."""

import asyncio
import json

import httpx
import pytest

from packages.resume_core import agent_limits as limits
from resume_api.agent.runtime import DEVELOPER_INSTRUCTIONS
from resume_api.assistant.tools import TOOL_NAMES
from tests.support.assistant_tools import mcp_client, tool_call, tool_session

INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "fixture", "version": "1"}}}


@pytest.mark.asyncio
async def test_owned_listener_start_and_concurrent_close_revoke_token_and_release_socket():
    session = tool_session()
    await session.start()
    token = session.token
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host) as client:
            rejected = await client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
            assert rejected.status_code == 403 and session.calls == 0
    finally:
        await asyncio.gather(session.close(), session.close())
    assert not session.token and token and session.task.done() and session.listener.fileno() == -1


@pytest.mark.asyncio
async def test_private_mcp_rejects_host_origin_duplicate_auth_and_oversized_body_before_sdk():
    session = tool_session()
    try:
        async with mcp_client(session) as client:
            assert (await client.post("/mcp", json=INITIALIZE)).json()["result"]["serverInfo"]["name"] == "foldcv"
            for invalid in ({"Host": "localhost"}, {"Origin": "null"}, {"Authorization": "Bearer wrong"}):
                assert (await client.post("/mcp", json=INITIALIZE, headers=invalid)).status_code == 403
            duplicate = list(client.headers.items()) + [("Authorization", "Bearer " + session.token)]
            assert (await client.post("/mcp", json=INITIALIZE, headers=duplicate)).status_code == 403
            assert (await client.post("/mcp", content=b"x" * (limits.CALL_READ_BYTES + 1))).status_code == 413
            tools = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            assert {tool["name"] for tool in tools.json()["result"]["tools"]} == set(TOOL_NAMES)
            unknown = await client.post("/mcp", json=tool_call(3, "get_working_facts", {"query": {"projectId": "foreign"}}))
            assert unknown.json()["result"]["isError"] and session.calls == 1
            malicious = await client.post("/mcp", json=tool_call(4, "get_working_facts",
                {"unknown_" + str(index): "CANDIDATE_CANARY" for index in range(1000)}))
            assert malicious.json()["result"]["isError"] and len(malicious.content) < 512
            assert "CANDIDATE_CANARY" not in malicious.text
            good = await client.post("/mcp", json=tool_call(5, "read_resume", {}))
            result = json.loads(good.json()["result"]["content"][0]["text"])
            assert result["page"] == 0 and result["items"] and session.calls == 3
            assert "structuredContent" not in good.json()["result"]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_an_oversized_tool_call_gets_a_tool_error_with_the_limit_and_counts_as_a_call():
    session = tool_session()
    try:
        async with mcp_client(session) as client:
            ops = [{"op": "set_block_text", "blockId": "block-paper-a", "text": "Я" * 15000} for _ in range(3)]
            reply = await client.post("/mcp", json=tool_call(7, "propose_changes", {"request": {"summary": "Правка", "ops": ops}}))
            result = reply.json()["result"]
            failure = json.loads(result["content"][0]["text"])
            assert reply.status_code == 200 and result["isError"] and failure["error"]["code"] == "AGENT_CALL_TOO_LARGE"
            assert str(limits.CALL_BYTES) in failure["detail"][0] and "Я" * 100 not in reply.text and session.calls == 1
            # Anything else over the call limit, and any body over the read limit, is still refused outright.
            padded = {**INITIALIZE, "params": {**INITIALIZE["params"], "padding": "x" * limits.CALL_BYTES}}
            assert (await client.post("/mcp", json=padded)).status_code == 413
            assert (await client.post("/mcp", content=b"x" * (limits.CALL_READ_BYTES + 1))).status_code == 413
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_the_model_is_told_the_call_limits_and_may_split_a_large_edit():
    session = tool_session()
    try:
        async with mcp_client(session) as client:
            tools = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            described = {tool["name"]: " ".join(tool["description"].split()) for tool in tools.json()["result"]["tools"]}
    finally:
        await session.close()
    assert f"{limits.CALL_BYTES // 1024} KiB of JSON and {limits.EDIT_OPERATIONS} ops" in described["propose_changes"]
    assert f"{limits.CALL_BYTES // 1024} KiB" in described["publish_findings"]
    # The old one-batch rule made the model squeeze a whole-resume edit into one proposal.
    assert "at most one successful batch" not in DEVELOPER_INSTRUCTIONS and "several proposals" in DEVELOPER_INSTRUCTIONS


@pytest.mark.xfail(strict=True, reason="SDK argument validation errors echo input values; the old listener answered with the shape only")
@pytest.mark.asyncio
async def test_argument_errors_of_a_known_tool_explain_the_shape_without_echoing_values():
    session = tool_session()
    try:
        async with mcp_client(session) as client:
            for name, arguments in (("read_skill", {"name": "PRIVATE_CANARY"}), ("read_facts", {"page": "PRIVATE_CANARY"}),
                    ("propose_changes", {"request": {"ops": [{"op": "set_block_text", "blockId": "PRIVATE_CANARY"}]}})):
                reply = await client.post("/mcp", json=tool_call(6, name, arguments))
                assert reply.json()["result"]["isError"]
                assert "PRIVATE_CANARY" not in reply.text
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"{", b'{"duplicate":1,"duplicate":2}', b"\xff"])
async def test_private_mcp_bad_json_returns_client_error(body):
    session = tool_session()
    try:
        async with mcp_client(session) as client:
            response = await client.post("/mcp", content=body)
        assert response.status_code == 400 and session.calls == 0
    finally:
        await session.close()
