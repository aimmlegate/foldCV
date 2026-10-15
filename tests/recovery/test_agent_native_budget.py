"""The final proof guard reserves both outcomes and never extends native starts."""

import json
from types import SimpleNamespace

import pytest

from packages.resume_core.agent_store import AgentFailure
from spikes.agent import native_proof


def setup(tmp_path, monkeypatch, *, spent=0, attempts=()):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"nativeBudgets": {"AG00_AG02": {"spent": 3, "cap": 3},
        "AG08": {"spent": spent, "cap": 3, "attempts": list(attempts)}}}))
    monkeypatch.setattr(native_proof, "STATE", state)
    monkeypatch.setattr(native_proof, "source_manifest", lambda number: {"path": "synthetic-manifest", "sha256": "a" * 64})
    (tmp_path / "task-spec.json").write_text('{"synthetic":true}')
    runtime = object.__new__(native_proof.BoundedRuntime)
    runtime.root = tmp_path; runtime.exclusion = SimpleNamespace(check=lambda: None)
    return runtime, state


def test_final_native_spend_is_durable_and_auth_or_quota_stops_all_later_starts(tmp_path, monkeypatch):
    runtime, path = setup(tmp_path, monkeypatch)
    assert runtime.spend("research_edit", "run_1") == 1
    value = json.loads(path.read_text()); budget = value["nativeBudgets"]["AG08"]
    assert budget["spent"] == 1 and budget["attempts"][0]["status"] == "started"
    assert value["nativeBudgets"]["AG00_AG02"]["spent"] == 3
    budget["attempts"][0].update(status="failed", error="AGENT_QUOTA"); path.write_text(json.dumps(value))
    with pytest.raises(AgentFailure, match="AGENT_QUOTA"): runtime.spend("check_only", "run_2")
    assert json.loads(path.read_text())["nativeBudgets"]["AG08"]["spent"] == 1


def test_final_native_guard_preserves_both_required_outcomes_and_one_shared_repair(tmp_path, monkeypatch):
    runtime, path = setup(tmp_path, monkeypatch, spent=2, attempts=[{"phase": "research_edit", "status": "failed"}] * 2)
    with pytest.raises(AgentFailure, match="AGENT_TOOL_LIMIT"): runtime.spend("check_only", "run_3")
    runtime, path = setup(tmp_path, monkeypatch, spent=1, attempts=[{"phase": "research_edit", "status": "passed"}])
    assert runtime.spend("check_only", "run_2") == 2
    assert runtime.spend("check_only", "run_3") == 3
    with pytest.raises(AgentFailure, match="AGENT_TOOL_LIMIT"): runtime.spend("check_only", "run_4")
    assert json.loads(path.read_text())["nativeBudgets"]["AG08"]["spent"] == 3


def test_profile_monitor_distinguishes_real_service_commands_from_read_only_inline_code(monkeypatch):
    rows = "1 /usr/bin/python3 -c from spikes.agent.native_proof import RESEARCH\n2 /usr/bin/python3 -m spikes.agent.native_proof --root /private/tmp/foldcv-agent-ag08-other\n3 /usr/bin/python3 tools/gui_native_cycle.py --reuse-store\n4 /usr/bin/python3 -m resume_api.agent.web\n"
    monkeypatch.setattr(native_proof.subprocess, "check_output", lambda *args, **kwargs: rows)
    assert native_proof.competitors(99) == [2, 3]
    assert native_proof.competitors(2) == [3]


@pytest.mark.asyncio
async def test_proof_diagnostics_cannot_hide_a_saved_receipt_with_null_error_or_failed_log(monkeypatch):
    receipt = {"durable": True, "disposition": "saved", "error": None}
    async def saved(self, name, arguments): return receipt
    monkeypatch.setattr(native_proof.ToolSession, "call", saved)
    session = object.__new__(native_proof.EvidenceSession)
    session.run = SimpleNamespace(allow_edits=True, allow_web=True)
    rows = []; session.record = rows.append
    assert await session.call("apply_edit_batch", None) is receipt
    assert rows[0]["code"] is None
    def failed(row): raise OSError("Synthetic diagnostic failure")
    session.record = failed
    assert await session.call("apply_edit_batch", None) is receipt
    assert session.diagnostic_errors == 1
