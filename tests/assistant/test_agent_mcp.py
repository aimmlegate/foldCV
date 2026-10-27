"""The private MCP listener (agent/mcp) of a run: bearer-only access, envelope checks before the SDK, owned socket."""

import asyncio
import json

import httpx
import pytest

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
            assert (await client.post("/mcp", content=b"x" * 65537)).status_code == 413
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
