"""Scripted native framing and SDK MCP calls use synthetic data only."""

import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from tests.support.agent import ScriptedMcp, fake_agent_cli


def test_scripted_cli_preserves_fragmented_rpc_ids_and_real_interrupt_exchange(tmp_path):
    executable = fake_agent_cli(tmp_path / "peer", [
        {"method": "initialize", "send": [{"id": "$id", "result": {"userAgent": "fixture"}}]},
        {"method": "initialized"},
        {"method": "thread/start", "send": [{"id": "$id", "result": {"thread": {"id": "thread_1"}}}]},
        {"method": "turn/start", "send": [{"id": "$id", "result": {"turn": {"id": "turn_1", "status": "inProgress"}}},
            {"method": "turn/started", "params": {"threadId": "thread_1", "turn": {"id": "turn_1", "status": "inProgress"}}}]},
        {"method": "turn/interrupt", "params": {"threadId": "thread_1", "turnId": "turn_1"},
            "send": [{"id": "$id", "result": {}}, {"method": "turn/completed", "params": {
                "threadId": "thread_1", "turn": {"id": "turn_1", "status": "interrupted"}}}]},
    ], fragment_bytes=1)
    frames = [{"id": 7, "method": "initialize", "params": {}}, {"method": "initialized"},
        {"id": 11, "method": "thread/start", "params": {}}, {"id": 12, "method": "turn/start", "params": {}},
        {"id": 13, "method": "turn/interrupt", "params": {"threadId": "thread_1", "turnId": "turn_1"}}]
    completed = subprocess.run([sys.executable, str(executable), "app-server"],
        input="".join(json.dumps(frame) + "\n" for frame in frames), capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0 and completed.stderr == ""
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [frame["id"] for frame in replies if "id" in frame] == [7, 11, 12, 13]
    assert replies[-1]["params"]["turn"]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_scripted_mcp_uses_sdk_initialize_list_and_typed_synthetic_result():
    peer = ScriptedMcp([{"text": "Synthetic Python evidence", "revision": 1}])
    headers = {"Accept": "application/json, text/event-stream"}
    async with peer.application.router.lifespan_context(peer.application):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=peer.application),
                                    base_url="http://fixture", headers=headers) as client:
            response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "fixture", "version": "1"}}})
            assert response.json()["result"]["serverInfo"]["name"] == "foldcv-scripted"
            tools = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            assert [tool["name"] for tool in tools.json()["result"]["tools"]] == ["get_resume_context"]
            result = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "get_resume_context", "arguments": {}}})
            content = result.json()["result"]
            assert not content.get("isError", False)
            assert json.loads(content["content"][0]["text"])["revision"] == 1
            assert peer.calls == ["get_resume_context"]
