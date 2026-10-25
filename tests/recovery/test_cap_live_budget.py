"""The CAP live proof charges each assistant turn before it starts and never exceeds its ceilings."""

import json

import pytest

from packages.resume_core.agent_store import AgentFailure
from spikes.agent import cap_live_proof as proof


def ledger(tmp_path, monkeypatch, *, attempts=()):
    path = tmp_path / "cap-live-ledger.json"
    path.write_text(json.dumps({"cap": 4, "phaseCap": {"rewrite_apply": 2, "check_only": 2}, "spent": len(attempts),
        "attempts": list(attempts)}))
    monkeypatch.setattr(proof, "BUDGET_LOCK", str(tmp_path / "budget.lock"))
    return path


def test_each_start_is_durable_before_the_turn_and_each_scenario_keeps_its_share(tmp_path, monkeypatch):
    path = ledger(tmp_path, monkeypatch)
    assert proof.charge(path, "rewrite_apply", run_id="run_1", continuation=False) == 1
    saved = json.loads(path.read_text())
    assert saved["spent"] == 1 and saved["attempts"][0]["status"] == "started"
    proof.settle(path, 1, "failed", error="AGENT_TIMEOUT")
    assert proof.charge(path, "rewrite_apply", run_id="run_2", continuation=True) == 2
    with pytest.raises(AgentFailure, match="AGENT_TOOL_LIMIT"):
        proof.charge(path, "rewrite_apply", run_id="run_3", continuation=True)
    assert proof.charge(path, "check_only", run_id="run_3", continuation=False) == 3
    assert proof.charge(path, "check_only", run_id="run_4", continuation=False) == 4
    with pytest.raises(AgentFailure, match="AGENT_TOOL_LIMIT"):
        proof.charge(path, "check_only", run_id="run_5", continuation=False)
    assert json.loads(path.read_text())["spent"] == 4


def test_auth_or_quota_stops_every_later_start_and_passed_scenarios_are_closed(tmp_path, monkeypatch):
    passed = {"number": 1, "phase": "rewrite_apply", "status": "passed"}
    path = ledger(tmp_path, monkeypatch, attempts=[passed])
    with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
        proof.charge(path, "rewrite_apply", run_id="run_2", continuation=False)
    assert proof.charge(path, "check_only", run_id="run_2", continuation=False) == 2
    proof.settle(path, 2, "failed", error="AGENT_QUOTA")
    with pytest.raises(AgentFailure, match="AGENT_QUOTA"):
        proof.charge(path, "check_only", run_id="run_3", continuation=False)
    assert json.loads(path.read_text())["spent"] == 2


@pytest.mark.parametrize("model,changes", [
    ("other-model", {}),
    (proof.MODEL, {"message": "Перепиши резюме"}),
    (proof.MODEL, {"allowWeb": True}),
])
def test_only_the_authorized_request_model_and_web_off_mode_are_admitted(model, changes):
    context = {"message": proof.REQUEST, "allowWeb": False, "allowEdits": True, "continuedDraft": None, **changes}
    with pytest.raises(AgentFailure, match="AGENT_TOOL_DENIED"):
        proof.admit(context, model)


def test_admitted_phase_follows_edit_permission_and_marks_continuation():
    base = {"message": proof.REQUEST, "allowWeb": False, "continuedDraft": None}
    assert proof.admit({**base, "allowEdits": True}, proof.MODEL) == ("rewrite_apply", False)
    assert proof.admit({**base, "allowEdits": False, "continuedDraft": {"proposalId": "p"}}, proof.MODEL) == ("check_only", True)
