"""Final native allowance accounting is exercised only with a copied ledger."""

import json
import asyncio

import pytest

from packages.resume_core.background_store import BackgroundFailure
from spikes.background.native_serial import spend
from spikes.background.native_serial import SerialProof


@pytest.mark.parametrize("fault", ["unauthorized", "exhausted", "count-mismatch", "auth", "quota", "duplicate"])
def test_final_native_dispatch_refuses_an_invalid_or_spent_allowance_before_launch(tmp_path, fault):
    attempt = dict(id="NB07a-1", pool="NB07a", variant="NB-X03:v01", status="failed", error=None)
    ledger = dict(pools={"NB07a": dict(authorized=True, cap=2, spent=0)}, attempts=[])
    if fault == "unauthorized": ledger["pools"]["NB07a"]["authorized"] = False
    elif fault == "exhausted": ledger["pools"]["NB07a"]["cap"] = 0
    elif fault == "count-mismatch": ledger["pools"]["NB07a"]["spent"] = 1
    else:
        ledger["attempts"].append(attempt)
        ledger["pools"]["NB07a"]["spent"] = 1
        if fault in {"auth", "quota"}: attempt["error"] = "AGENT_AUTH_REQUIRED" if fault == "auth" else "AGENT_QUOTA"
    path = tmp_path / "ledger.json"; path.write_text(json.dumps(ledger))
    before = path.read_bytes()
    with pytest.raises(BackgroundFailure):
        spend(path, variant="NB-X03:v01", job="synthetic-job", project="synthetic-project", hashes={"test": "a" * 64})
    assert path.read_bytes() == before


def test_final_native_dispatch_counts_failed_starts_without_borrowing_another_pool(tmp_path):
    ledger = dict(pools={"NB07a": dict(authorized=True, cap=2, spent=0),
        "NB00": dict(authorized=True, cap=10, spent=0), "NB07b": dict(authorized=True, cap=6, spent=0)}, attempts=[])
    path = tmp_path / "ledger.json"; path.write_text(json.dumps(ledger))
    first = spend(path, variant="NB-X03:v01", job="synthetic-first", project="synthetic-project", hashes={"test": "a" * 64})
    value = json.loads(path.read_bytes()); value["attempts"][0]["status"] = "failed"
    path.write_text(json.dumps(value))
    second = spend(path, variant="NB-X03:v02", job="synthetic-second", project="synthetic-project", hashes={"test": "a" * 64})
    assert (first, second) == ("NB07a-1", "NB07a-2")
    with pytest.raises(BackgroundFailure):
        spend(path, variant="not-a-reserve", job="synthetic-third", project="synthetic-project", hashes={"test": "a" * 64})
    final = json.loads(path.read_bytes())
    assert final["pools"]["NB07a"]["spent"] == 2 and len(final["attempts"]) == 2
    assert final["pools"]["NB00"] == ledger["pools"]["NB00"] and final["pools"]["NB07b"] == ledger["pools"]["NB07b"]


@pytest.mark.asyncio
async def test_native_evidence_wraps_real_empty_string_and_model_tool_arguments_without_affecting_results(tmp_path):
    from packages.resume_core.models.agent import AgentQuery
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from tests.recovery.test_background_agent import environment
    service, factory, workspace, request, _connection, _old = await environment(tmp_path / "service")
    request.request.allow_web = False
    proof = SerialProof.__new__(SerialProof)
    proof.root = tmp_path / "evidence"; proof.root.mkdir()
    proof.original_session, proof.sessions = service.tools.session, {}
    observed = []
    async def execute(control, _actor):
        session = proof.session(control)
        try:
            observed.append(await session.call("check_resume", None))
            observed.append(await session.call("read_public_page", "https://example.com/"))
            observed.append(await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"])))
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[request.request.client_request_id] = execute
    try:
        job, _ = await service.submit(workspace.project_id, request)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        assert service.store.read(workspace.project_id, job.id).execution == "completed"
        assert observed[0].get("error") is None and observed[2].get("snapshot") is not None
        assert observed[1]["error"]["code"] == "AGENT_TOOL_DENIED"
        rows = [json.loads(line) for line in (proof.root / (job.id + "-tools.jsonl")).read_text().splitlines()]
        assert [row["arguments"] for row in rows[:2]] == [None, "https://example.com/"]
        assert rows[2]["arguments"]["kind"] == "document"
        assert [row["result"] for row in rows] == observed
        assert not service.admission.locked()
    finally:
        await service.shutdown(); factory.verify(); service.supervisor.clock.verify()
