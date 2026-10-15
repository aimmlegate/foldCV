"""AG00 checks protect the private MCP and deny interactive native requests."""

import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api/src"))

from spikes.agent.listener import ProofMcp
from spikes.agent import proof
from spikes.agent.proof import Probe, proof_passed


@pytest.mark.asyncio
async def test_private_mcp_rejects_foreign_host_origin_and_token_before_tools():
    listener = ProofMcp()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "foldcv-test", "version": "1"}}}
    headers = {"Authorization": "Bearer " + listener.token,
               "Accept": "application/json, text/event-stream"}
    try:
        async with listener.application.router.lifespan_context(listener.application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=listener),
                                         base_url="http://" + listener.host) as client:
                for changed in [{"Authorization": "Bearer wrong"}, {"Host": "foreign.test"},
                                {"Origin": "http://localhost"}]:
                    response = await client.post("/mcp", headers={**headers, **changed}, json=payload)
                    assert response.status_code == 403
                assert (await client.post("/mcp", json=payload)).status_code == 403
                accepted = await client.post("/mcp", headers=headers, json=payload)
                assert accepted.status_code == 200
                assert accepted.json()["result"]["serverInfo"]["name"] == "foldcv"
                listener.active = False
                assert (await client.post("/mcp", headers=headers, json=payload)).status_code == 403
                assert listener.calls == []
    finally:
        await listener.close()


@pytest.mark.parametrize("method", json.loads((ROOT /
    "docs/gui/handoffs/AGENT-ASSISTANT/pinned-protocol.json").read_text())[
        "schemas"]["experimental"]["serverRequests"])
def test_native_server_requests_never_receive_auth_approval_or_code(tmp_path, method):
    probe = Probe(tmp_path, "inspect", None)
    response = json.loads(probe.accept(json.dumps({
        "id": "request-1", "method": method, "params": {"token": "untrusted"}}).encode()))
    assert response == {"id": "request-1", "error": {
        "code": -32601, "message": "Client requests are disabled"}}
    assert "untrusted" not in json.dumps(response)


@pytest.mark.parametrize(("method", "code"), [
    ("model/rerouted", "AGENT_MODEL_REROUTED"),
    ("thread/compacted", "AGENT_UNEXPECTED_COMPACTION"),
])
def test_reroute_and_compaction_end_the_probe(tmp_path, method, code):
    with pytest.raises(RuntimeError, match=code):
        Probe(tmp_path, "inspect", None).accept(json.dumps({"method": method, "params": {}}).encode())


def test_native_final_text_without_tools_does_not_pass_capability():
    assert not proof_passed({"phase": "capability", "turnStatus": "completed",
                             "ownedProcessCleaned": True, "operationCleaned": True,
                             "answer": "I cannot access the tools.", "items": [], "toolCalls": []})


def test_failed_repair_cannot_spend_the_last_required_proof_slot(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"status": "AG00_in_progress", "nativeBudgets": {
        "AG00_AG02": {"cap": 3, "spent": 2, "attempts": [
            {"phase": "capability", "status": "failed_capability"},
            {"phase": "capability", "status": "failed_capability"}]}}}))
    monkeypatch.setattr(proof, "STATE", state)
    with pytest.raises(RuntimeError, match="AGENT_REQUIRED_PROOF_BUDGET_EXHAUSTED"):
        proof.spend("interrupt")
    assert json.loads(state.read_text())["nativeBudgets"]["AG00_AG02"]["spent"] == 2
