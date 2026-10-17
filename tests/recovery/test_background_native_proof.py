"""Reject fabricated overlap, cleanup and charged-turn claims without models."""

import hashlib
import json
import asyncio

import pytest

from tools.background_evidence import assert_native_bindings


def proof_fixture(root):
    sources = {"runtime.py": "a" * 64}
    variant = "NB-R05:v01"
    artifacts, turns, attempts, wire = {}, [], [], []
    runtimes = {}
    for index, role in enumerate(("agent-A", "agent-B")):
        name = "turn-" + str(index)
        path = name + ".json"
        runtime = dict(transport="shared_appserver_v1", nativeStarted=True, jobId=name, role=role,
            state="completed", error=None, serverPid=123, hostPids=[124], sharedProcessDead=False,
            profileExclusionLost=False, toolsClosed=True, parserClosed=True, operationRemoved=True,
            turnResourcesClosed=True, cleanupVerified=True, mcpListenerClosed=True, toolCalls=3,
            startedAt=1.0 + index, endedAt=8.0 + index, threadId="thread_" + name, turnId=name,
            namespace="foldcv_" + name, toolNames=["read", "prepare", "apply"])
        runtimes[path] = runtime
        turns.append(dict(role=role, attemptId=name, runtimeArtifact=path))
        attempts.append(dict(id=name, pool="NB00", variant=variant, role=role, jobId=name,
            status="passed", sourceHashes=sources, model="gpt-6-luna", effort="medium",
            transport="one pinned multiplexed App Server"))
        params = {"threadId": runtime["threadId"]}
        wire.extend([dict(direction="client", at=runtime["startedAt"] - .1,
                frame={"method": "turn/start", "params": {**params, "input": []}}),
            dict(direction="server", at=runtime["startedAt"], frame={"method": "turn/started",
                "params": {**params, "turn": {"id": name}}}),
            dict(direction="server", at=runtime["endedAt"], frame={"method": "turn/completed",
                "params": {**params, "turn": {"id": name, "status": "completed"}}})])
        for number, tool in enumerate(runtime["toolNames"]):
            identifier = 100 + index * 10 + number
            wire.extend([dict(direction="server", at=3.0, frame={"method": "item/tool/call", "id": identifier,
                "params": {**params, "turnId": name, "namespace": runtime["namespace"], "tool": tool,
                    "callId": "call_" + str(identifier), "arguments": {}}}),
                dict(direction="client", at=3.1, frame={"id": identifier, "result": {"contentItems": [], "success": True}})])
    shutdown = dict(status="stopped", ownedPidsGone=True, operationRemoved=True,
        profileLockReleased=True, profileExclusionLost=False, serverPid=123, hostPids=[124])
    case = dict(outcome="passed", layer="native", turns=turns, artifacts=artifacts,
        shutdownArtifact="shutdown.json", ownerShutdownArtifact="shutdown.json", wireArtifact="wire.jsonl")
    report = dict(transport="shared_appserver_v1", sourceHashes=sources, variants={variant: case})
    ledger = dict(pools={"NB00": dict(authorized=True, cap=10, spent=2)}, attempts=attempts)
    binding = {variant: dict(evidence="proof.json", pool="NB00", transport="shared_appserver_v1",
        roles=["agent-A", "agent-B"])}
    def save():
        for path, data in {**runtimes, "shutdown.json": shutdown}.items():
            (root / path).write_text(json.dumps(data))
        (root / "wire.jsonl").write_text("\n".join(json.dumps(frame) for frame in wire) + "\n")
        for path in [*runtimes, "shutdown.json", "wire.jsonl"]:
            artifacts[path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
        (root / "proof.json").write_text(json.dumps(report))
        path = root / "docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ledger))
    return sources, binding, report, ledger, runtimes, shutdown, wire, save


@pytest.mark.parametrize("fault", ["none", "serial-process-claim", "cleanup", "shutdown", "wrong-pid", "no-host",
    "source", "charged-source", "wrong-role", "wrong-model", "uncharged", "duplicate-thread", "fake-overlap",
    "wrong-turn", "hidden-turn", "missing-wire", "missing-artifact", "wrong-pool", "pending", "bad-clock",
    "false-tool-count", "foreign-namespace", "missing-tool-reply"])
def test_shared_native_release_gate_requires_real_overlap_charged_turns_and_separate_shutdown(tmp_path, fault):
    sources, bindings, report, ledger, runtimes, shutdown, wire, save = proof_fixture(tmp_path)
    first, second = runtimes.values()
    if fault == "serial-process-claim": first["sharedProcessDead"] = True
    elif fault == "cleanup": first["turnResourcesClosed"] = False
    elif fault == "shutdown": shutdown["ownedPidsGone"] = False
    elif fault == "wrong-pid": first["serverPid"] = 999
    elif fault == "no-host": first["hostPids"] = []
    elif fault == "source": report["sourceHashes"] = {"other.py": "a" * 64}
    elif fault == "charged-source": ledger["attempts"][0]["sourceHashes"] = {"other.py": "a" * 64}
    elif fault == "wrong-role": ledger["attempts"][0]["role"] = "agent-B"
    elif fault == "wrong-model": ledger["attempts"][0]["model"] = "other"
    elif fault == "uncharged": ledger["attempts"][0]["status"] = "started"
    elif fault == "duplicate-thread": second["threadId"] = first["threadId"]
    elif fault == "fake-overlap":
        first["endedAt"] = 1.5
        wire[2]["at"] = 1.5
    elif fault == "wrong-turn": wire[2]["frame"]["params"]["turn"]["id"] = "foreign"
    elif fault == "hidden-turn": wire.append(dict(direction="client", at=3, frame={"method": "turn/start", "params": {"threadId": "hidden"}}))
    elif fault == "missing-wire": wire.clear()
    elif fault == "wrong-pool": ledger["pools"]["NB00"]["cap"] = 14
    elif fault == "pending": report["variants"]["NB-R05:v01"]["outcome"] = "awaiting_native_proof"
    elif fault == "bad-clock": first["startedAt"] = float("nan")
    elif fault == "false-tool-count": first["toolCalls"] = 4
    elif fault == "foreign-namespace": first["namespace"] = second["namespace"]
    elif fault == "missing-tool-reply": wire[:] = [row for row in wire if row["frame"].get("id") != 100 or row["direction"] != "client"]
    save()
    if fault == "missing-artifact": (tmp_path / "turn-0.json").unlink()
    if fault == "none":
        assert assert_native_bindings(bindings, {"NB-R05:v01"}, tmp_path, sources=sources, require_pass=True) == []
    else:
        with pytest.raises(SystemExit):
            assert_native_bindings(bindings, {"NB-R05:v01"}, tmp_path, sources=sources, require_pass=True)


def test_native_feasibility_refuses_a_stale_controlled_gate_before_profile_or_attempt(tmp_path):
    from pathlib import Path
    from uuid import uuid4
    from spikes.background.native_parallel import Feasibility
    (tmp_path / "context.json").write_text(json.dumps({"sourceHashes": {}}))
    (tmp_path / "validation.json").write_text(json.dumps({"outcome": "passed"}))
    root = Path("/private/tmp/foldcv-nb00b-native-stale-" + uuid4().hex)
    with pytest.raises(ValueError, match="complete current controlled gate"):
        Feasibility(root, tmp_path)
    assert not root.exists()


@pytest.mark.asyncio
async def test_native_matrix_retains_startup_failure_without_charging_a_turn(tmp_path):
    from spikes.background.native_parallel import Feasibility
    from spikes.background.appserver_protocol import TransportFailure
    class FailedServer:
        fence_code = "PROTOCOL"
        async def prepare(self, planned):
            raise TransportFailure(self.fence_code)
    proof = Feasibility.__new__(Feasibility)
    proof.root, proof.server, proof.hashes = tmp_path, FailedServer(), {"runtime.py": "a" * 64}
    marked = []
    proof.mark = lambda participants, status, error: marked.append((participants, status, error))
    with pytest.raises(TransportFailure, match="PROTOCOL"):
        await proof.group("NB-R05:v01")
    failure = json.loads((tmp_path / "failure.json").read_bytes())
    assert failure["chargedTurns"] == 0 and failure["transportCause"] == "PROTOCOL"
    assert proof.failed and marked == [([], "failed", "PROTOCOL")]


@pytest.mark.parametrize("fault", ["none", "pending", "wrong-authority", "changed-history"])
def test_native_retry_proof_requires_the_same_approved_extension_and_failed_history(tmp_path, fault):
    from pathlib import Path
    sources, bindings, _report, ledger, _runtimes, _shutdown, _wire, save = proof_fixture(tmp_path)
    handoff = Path("docs/gui/handoffs/BACKGROUND-WORK")
    target = tmp_path / handoff
    (target / "nb00b-evidence").mkdir(parents=True)
    grant = json.loads((handoff / "native-feasibility-retry-authorization.json").read_text())
    grant.update(authorized=fault != "pending", status="approved_by_user",
        userInstruction="Synthetic approval for a copied proof only", approvedAt="2026-10-17T00:00:00+00:00")
    authority = target / "native-feasibility-retry-authorization.json"
    authority.write_text(json.dumps(grant))
    (target / "nb00b-evidence/native-retry-proposal.md").write_bytes((handoff / "nb00b-evidence/native-retry-proposal.md").read_bytes())
    for attempt in ledger["attempts"]:
        attempt.update(historicalStarts=2, retryAuthoritySha256=hashlib.sha256(authority.read_bytes()).hexdigest())
    if fault == "wrong-authority": ledger["attempts"][0]["retryAuthoritySha256"] = "0" * 64
    historical = json.loads((handoff / "nb00b-evidence/failed-native-pair.json").read_text())
    if fault == "changed-history": historical[0]["status"] = "passed"
    ledger["attempts"] = historical + ledger["attempts"]
    ledger["pools"]["NB00"].update(cap=12, spent=4)
    save()
    if fault == "none":
        assert_native_bindings(bindings, set(bindings), tmp_path, sources=sources, require_pass=True)
    else:
        with pytest.raises(SystemExit, match="native release proof"):
            assert_native_bindings(bindings, set(bindings), tmp_path, sources=sources, require_pass=True)


@pytest.mark.asyncio
async def test_shared_native_witness_keeps_null_and_scalar_tool_arguments(tmp_path):
    from types import SimpleNamespace
    from spikes.background.native_parallel import Feasibility
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from packages.resume_core.models.agent import AgentQuery
    from tests.recovery.test_background_agent import environment
    service, factory, workspace, request, _connection, _old = await environment(tmp_path / "service")
    request.request.allow_web = False
    proof = Feasibility.__new__(Feasibility)
    proof.root, proof.variant = tmp_path / "proof", "NB-R05:v02"
    proof.root.mkdir()
    participant = SimpleNamespace(attempt=None)
    original = service.tools.session
    observed = []
    async def execute(control, _actor):
        participant.attempt = {"id": control.job.id}
        session = proof.session(participant, control, original)
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
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_native_matrix_captures_all_ten_requests_without_launching_a_model(tmp_path):
    from spikes.background.native_parallel import Feasibility, ROLES
    proof = Feasibility.__new__(Feasibility)
    proof.root, proof.server, proof.all_participants = tmp_path, object(), []
    captured = []
    try:
        for variant, roles in ROLES.items():
            if not variant.startswith("NB-R05:"):
                continue
            proof.variant = variant
            for role in roles:
                participant = await proof.participant(role)
                participant.service.supervisor.dispatch_enabled = False
                await proof.submit(participant)
                job = participant.service.store.read(participant.workspace.project_id, participant.job.id)
                assert job.execution == "queued" and not job.attempts
                assert job.submission.models[0].model == "gpt-6-luna"
                assert ":" not in job.submission.identity.request_id
                assert not participant.service.admission.locked()
                if not role.startswith("agent-"):
                    fixed = participant.service.fixed.input(job)
                    assert fixed.sync_id is not None
                    text = next(block for block in fixed.workspace.project.document.blocks() if block.id == "narrative").content[0].text
                    assert participant.marker in text
                    if role == "structured-sync-C":
                        assert "Current job title: Python API Engineer." in text
                        candidate = next(record for record in fixed.workspace.project.facts.records if record.id == "candidate-1")
                        assert candidate.title.value != "Python API Engineer"
                    else:
                        assert "Python. Wrote" in text
                        assert "Replace exactly 'Python. Wrote' with 'Python; Wrote'" in fixed.request.command.request.instruction
                captured.append((variant, role))
        assert len(captured) == 10 and len(set(captured)) == 10
    finally:
        for participant in proof.all_participants:
            await participant.service.shutdown()
