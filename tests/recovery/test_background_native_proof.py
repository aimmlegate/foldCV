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


def test_native_feasibility_refuses_a_stale_controlled_gate_before_profile_or_attempt(tmp_path, monkeypatch):
    from pathlib import Path
    from uuid import uuid4
    from spikes.background.native_parallel import Feasibility
    monkeypatch.setattr("spikes.background.native_parallel.background_spec",
        lambda: {"sources": ["services/api/src/resume_api/jobs/appserver.py"]})
    (tmp_path / "context.json").write_text(json.dumps({"sourceHashes": {}}))
    (tmp_path / "validation.json").write_text(json.dumps({"outcome": "passed"}))
    root = Path("/private/tmp/foldcv-nb00b-native-stale-" + uuid4().hex)
    with pytest.raises(ValueError, match="complete current controlled gate"):
        Feasibility(root, tmp_path)
    assert not root.exists()


@pytest.mark.parametrize("fault", ["none", "no-receipt", "not-saved", "not-durable", "foreign-job",
    "foreign-receipt", "wrong-change", "missing-job", "missing-output-schema"])
def test_structured_native_evidence_requires_its_own_durable_fixed_publication(tmp_path, fault):
    sources, bindings, report, ledger, runtimes, _shutdown, wire, save = proof_fixture(tmp_path)
    old, variant = "NB-R05:v01", "NB-R05:v02"
    case = report["variants"].pop(old)
    report["variants"][variant] = case
    binding = bindings.pop(old)
    bindings[variant] = binding
    binding["roles"][1] = "structured-rewrite-B"
    case["turns"][1]["role"] = "structured-rewrite-B"
    for attempt in ledger["attempts"]:
        attempt["variant"] = variant
    ledger["attempts"][1]["role"] = "structured-rewrite-B"
    runtime = list(runtimes.values())[1]
    runtime.update(role="structured-rewrite-B", toolCalls=0, toolNames=[], mcpListenerClosed=None,
        schemaValidated=True, logicalAttempts=1, repairTurns=0,
        fixedPublication=dict(exactRequestedChange=True, jobArtifact="fixed-job.json"))
    wire[:] = [row for row in wire if row["frame"].get("params", {}).get("threadId") != runtime["threadId"]
        or row["frame"].get("method") != "item/tool/call"]
    wire[:] = [row for row in wire if row["frame"].get("id") not in {110, 111, 112}]
    start = next(row["frame"] for row in wire if row["direction"] == "client"
        and row["frame"].get("params", {}).get("threadId") == runtime["threadId"])
    if fault != "missing-output-schema":
        start["params"]["outputSchema"] = {"type": "object"}
    job = dict(id=runtime["jobId"], execution="completed", publication="saved",
        receipt=dict(durable=True, jobId=runtime["jobId"]))
    if fault == "no-receipt": job["receipt"] = None
    elif fault == "not-saved": job["publication"] = "waiting_for_sync"
    elif fault == "not-durable": job["receipt"]["durable"] = False
    elif fault == "foreign-job": job["id"] = "foreign-job"
    elif fault == "foreign-receipt": job["receipt"]["jobId"] = "foreign-job"
    elif fault == "wrong-change": runtime["fixedPublication"]["exactRequestedChange"] = False
    path = tmp_path / "fixed-job.json"
    path.write_text(json.dumps(job))
    case["artifacts"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    save()
    if fault == "missing-job": path.unlink()
    if fault == "none":
        assert_native_bindings(bindings, {variant}, tmp_path, sources=sources, require_pass=True)
    else:
        with pytest.raises(SystemExit, match="native release proof"):
            assert_native_bindings(bindings, {variant}, tmp_path, sources=sources, require_pass=True)


@pytest.mark.parametrize("fault", ["none", "agent", "missing-features", "enabled-host", "enabled-prewarm",
    "tools", "foreign-thread", "duplicate-ack", "request-generation", "ack-generation", "runtime-generation",
    "owner-generation", "owner-pid", "host-cleanup", "group-cleanup", "missing-owner", "late-ack"])
def test_hostless_structured_proof_requires_disabled_thread_and_verified_generation(tmp_path, fault):
    from spikes.background.appserver_offline import structured_features
    sources, bindings, report, ledger, runtimes, shutdown, wire, save = proof_fixture(tmp_path)
    old, variant = "NB-R05:v01", "NB-R05:v02"
    case = report["variants"].pop(old)
    report["variants"][variant] = case
    bindings[variant] = bindings.pop(old)
    bindings[variant]["roles"][1] = "structured-rewrite-B"
    case["turns"][1]["role"] = "structured-rewrite-B"
    for attempt in ledger["attempts"]:
        attempt["variant"] = variant
    ledger["attempts"][1]["role"] = "structured-rewrite-B"
    runtime = list(runtimes.values())[1]
    runtime.update(role="structured-rewrite-B", toolCalls=0, toolNames=[], mcpListenerClosed=None,
        hostPids=[], generation=2, schemaValidated=True, logicalAttempts=1, repairTurns=0,
        fixedPublication=dict(exactRequestedChange=True, jobArtifact="fixed-job.json"))
    wire[:] = [row for row in wire if row["frame"].get("params", {}).get("threadId") != runtime["threadId"]
        or row["frame"].get("method") != "item/tool/call"]
    wire[:] = [row for row in wire if row["frame"].get("id") not in {110, 111, 112}]
    for row in wire:
        row["generation"] = 2
        if row["frame"].get("method") == "turn/start" and row["frame"]["params"]["threadId"] == runtime["threadId"]:
            row["frame"]["params"]["outputSchema"] = {"type": "object"}
    request = dict(direction="client", generation=2, at=.5, frame=dict(id=900, method="thread/start",
        params=dict(dynamicTools=[], ephemeral=True, sandbox="read-only",
            config=dict(web_search="disabled", features=structured_features()))))
    response = dict(direction="server", generation=2, at=.6,
        frame=dict(id=900, result=dict(thread=dict(id=runtime["threadId"])) ))
    wire[:0] = [request, response]
    owner = dict(generation=2, processPid=123, hostPids=[124], ownedGroupCleanupVerified=True,
        ownedHostPidsGone=True, operationRemoved=True)
    shutdown["serverGenerations"] = [owner]
    if fault == "agent": list(runtimes.values())[0]["hostPids"] = []
    elif fault == "missing-features": request["frame"]["params"]["config"].pop("features")
    elif fault == "enabled-host": request["frame"]["params"]["config"]["features"]["code_mode_host"] = True
    elif fault == "enabled-prewarm": request["frame"]["params"]["config"]["features"]["code_mode_prewarm"] = True
    elif fault == "tools": request["frame"]["params"]["dynamicTools"] = [{"name": "foreign"}]
    elif fault == "foreign-thread": response["frame"]["result"]["thread"]["id"] = "foreign"
    elif fault == "duplicate-ack": wire.append(response.copy())
    elif fault == "request-generation": request["generation"] = 1
    elif fault == "ack-generation": response["generation"] = 1
    elif fault == "runtime-generation": runtime["generation"] = 1
    elif fault == "owner-generation": owner["generation"] = 1
    elif fault == "owner-pid": owner["processPid"] = 999
    elif fault == "host-cleanup": owner["ownedHostPidsGone"] = False
    elif fault == "group-cleanup": owner["ownedGroupCleanupVerified"] = False
    elif fault == "missing-owner": shutdown.pop("serverGenerations")
    elif fault == "late-ack": response["at"] = 10
    job = dict(id=runtime["jobId"], execution="completed", publication="saved",
        receipt=dict(durable=True, jobId=runtime["jobId"]))
    path = tmp_path / "fixed-job.json"
    path.write_text(json.dumps(job))
    case["artifacts"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    save()
    if fault == "none":
        assert_native_bindings(bindings, {variant}, tmp_path, sources=sources, require_pass=True)
    else:
        with pytest.raises(SystemExit, match="native release proof"):
            assert_native_bindings(bindings, {variant}, tmp_path, sources=sources, require_pass=True)


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


@pytest.mark.parametrize("fault", ["none", "pending", "wrong-authority", "changed-history", "changed-prior-grant"])
def test_publication_retry_proof_requires_the_new_grant_and_unchanged_prior_approval(tmp_path, fault):
    from pathlib import Path
    sources, bindings, _report, ledger, _runtimes, _shutdown, _wire, save = proof_fixture(tmp_path)
    handoff = Path("docs/gui/handoffs/BACKGROUND-WORK")
    target = tmp_path / handoff
    (target / "nb00b-evidence").mkdir(parents=True)
    grant = json.loads((handoff / "native-feasibility-repair-authorization.json").read_text())
    grant.update(authorized=fault != "pending", status="approved_by_user",
        userInstruction="Synthetic copied-proof approval only", approvedAt="2026-10-17T00:00:00+00:00")
    authority = target / "native-feasibility-repair-authorization.json"
    authority.write_text(json.dumps(grant))
    (target / "native-feasibility-retry-authorization.json").write_bytes((handoff / "native-feasibility-retry-authorization.json").read_bytes())
    (target / "nb00b-evidence/publication-retry-proposal.md").write_bytes((handoff / "nb00b-evidence/publication-retry-proposal.md").read_bytes())
    for attempt in ledger["attempts"]:
        attempt.update(historicalStarts=6, retryAuthoritySha256=hashlib.sha256(authority.read_bytes()).hexdigest())
    if fault == "wrong-authority": ledger["attempts"][0]["retryAuthoritySha256"] = "0" * 64
    historical = json.loads((handoff / "nb00b-evidence/first-six-native-starts.json").read_text())
    if fault == "changed-history": historical[-1]["status"] = "passed"
    if fault == "changed-prior-grant":
        (target / "native-feasibility-retry-authorization.json").write_text("Changed original approval")
    ledger["attempts"] = historical + ledger["attempts"]
    ledger["pools"]["NB00"].update(cap=16, spent=8)
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
                        from packages.resume_core.rich_sync import selection_parts
                        parts = selection_parts(fixed.workspace, fixed.request.command.request.selection)
                        selected = "".join(span["text"] for span in parts[0][-1]["content"])
                        assert selected == text and participant.marker in selected and "Python. Wrote" in selected
                        assert "Python. Wrote" in text
                        assert "Replace exactly 'Python. Wrote' with 'Python; Wrote'" in fixed.request.command.request.instruction
                captured.append((variant, role))
        assert len(captured) == 10 and len(set(captured)) == 10
    finally:
        for participant in proof.all_participants:
            await participant.service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["execution-first", "publication-first"])
async def test_native_harness_waits_for_both_real_execution_and_fixed_publication(tmp_path, order):
    import threading
    from types import SimpleNamespace
    from spikes.background.native_parallel import Feasibility
    from tests.recovery.generation_fixtures import CreationProvider
    from tests.recovery.test_background_agent import environment
    from tests.recovery.test_background_fixed_jobs import fixed_request, rewrite_command
    service, factory, workspace, _payload, _connection, _old = await environment(tmp_path)
    service.projects.provider_factory = lambda: (CreationProvider(), "processing-model")
    loop = asyncio.get_running_loop()
    publisher_entered, published, execution_finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release_publisher, release_execution = threading.Event(), asyncio.Event()
    original = service.publish_waiting
    def publish(project):
        loop.call_soon_threadsafe(publisher_entered.set)
        if order == "execution-first" and not release_publisher.wait(10):
            raise AssertionError("The synthetic publisher was not released")
        result = original(project)
        loop.call_soon_threadsafe(published.set)
        return result
    service.publish_waiting = publish
    async def observe(name, _job):
        if name == "slot_released":
            execution_finished.set()
            if order == "publication-first":
                await release_execution.wait()
    service.supervisor.observer = observe
    waiter = None
    try:
        reply, _ = await service.fixed.submit(workspace.project_id, fixed_request(service, workspace.project_id,
            "publication-order", rewrite_command(workspace)))
        await asyncio.wait_for(publisher_entered.wait(), 5)
        await asyncio.wait_for(execution_finished.wait(), 5)
        control = service.supervisor.controls[reply.job.id]
        if order == "execution-first":
            await asyncio.wait_for(asyncio.shield(control.task), 5)
            snapshot = service.store.read(workspace.project_id, reply.job.id)
            assert snapshot.execution == "completed" and snapshot.publication == "waiting_for_sync" and snapshot.receipt is None
            assert snapshot.attempts[-1].cleanup_verified and not service.admission.locked()
        else:
            await asyncio.wait_for(published.wait(), 5)
            assert service.store.read(workspace.project_id, reply.job.id).receipt.durable
        participant = SimpleNamespace(service=service, job=reply.job, workspace=workspace, role="structured-rewrite-B")
        waiter = asyncio.create_task(Feasibility.__new__(Feasibility).completed(participant))
        checkpoint = loop.create_future()
        loop.call_soon(checkpoint.set_result, None)
        await checkpoint
        assert not waiter.done()
        release_publisher.set()
        release_execution.set()
        result = await asyncio.wait_for(waiter, 5)
        assert result.execution == "completed" and result.publication == "saved" and result.receipt.durable
        assert result == service.store.read(workspace.project_id, reply.job.id)
        assert not result.attempts[-1].native_started and not service.supervisor.listeners
    finally:
        release_publisher.set()
        release_execution.set()
        if waiter is not None:
            await asyncio.gather(waiter, return_exceptions=True)
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_native_harness_receipt_timeout_leaves_the_real_publisher_owned_until_shutdown(tmp_path, monkeypatch):
    import threading
    from dataclasses import replace
    from types import SimpleNamespace
    from spikes.background import native_parallel
    from tests.recovery.generation_fixtures import CreationProvider
    from tests.recovery.test_background_agent import environment
    from tests.recovery.test_background_fixed_jobs import fixed_request, rewrite_command
    service, factory, workspace, _payload, _connection, _old = await environment(tmp_path)
    service.projects.provider_factory = lambda: (CreationProvider(), "processing-model")
    loop, entered, release = asyncio.get_running_loop(), asyncio.Event(), threading.Event()
    original = service.publish_waiting
    def publish(project):
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(10):
            raise AssertionError("The synthetic publisher was not released")
        return original(project)
    service.publish_waiting = publish
    try:
        reply, _ = await service.fixed.submit(workspace.project_id, fixed_request(service, workspace.project_id,
            "publication-timeout", rewrite_command(workspace)))
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.wait_for(asyncio.shield(service.supervisor.controls[reply.job.id].task), 5)
        publication = service.publication_tasks[workspace.project_id]
        monkeypatch.setattr(native_parallel, "LIMITS", replace(native_parallel.LIMITS, receipt_seconds=0))
        participant = SimpleNamespace(service=service, job=reply.job, workspace=workspace, role="structured-rewrite-B")
        with pytest.raises(TimeoutError):
            await native_parallel.Feasibility.__new__(native_parallel.Feasibility).completed(participant)
        assert not publication.done() and not publication.cancelled() and not service.supervisor.listeners
        assert service.store.read(workspace.project_id, reply.job.id).receipt is None
        release.set()
        await asyncio.wait_for(asyncio.shield(publication), 5)
        result = service.store.read(workspace.project_id, reply.job.id)
        assert result.publication == "saved" and result.receipt.durable and not result.attempts[-1].native_started
    finally:
        release.set()
        await service.shutdown()
        factory.verify(); service.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant,role", [
    ("NB-R05:v02", "structured-rewrite-B"), ("NB-R05:v03", "structured-rewrite-C"),
    ("NB-R05:v04", "structured-rewrite-B"), ("NB-R05:v04", "structured-sync-C")])
async def test_every_native_fixed_fixture_publishes_its_exact_captured_change_without_a_model(tmp_path, variant, role):
    from pathlib import Path
    from spikes.background.native_parallel import Feasibility
    from resume_api.jobs.appserver import SharedContentProvider
    from packages.resume_core.rich_sync import RichRewriteProposal, RichReconcileProposal
    from tests.recovery.test_background_appserver import shared_peer, complete_shared
    ledger = Path("docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json")
    before = ledger.read_bytes()
    server = shared_peer(tmp_path / "transport")
    proof = Feasibility.__new__(Feasibility)
    proof.root, proof.server, proof.variant, proof.all_participants = tmp_path / "proof", server, variant, []
    ready = asyncio.Event()
    participant = await proof.participant(role)
    service, project = participant.service, participant.workspace.project_id
    provider = SharedContentProvider(server, native=False, audit=lambda value: setattr(participant, "runtime", value))
    service.projects.provider_factory = lambda: (provider, "gpt-6-luna")
    async def observe(name, _job):
        if name == "scripted_fixed_model_ready":
            ready.set()
    service.supervisor.observer = observe
    try:
        await proof.submit(participant)
        await asyncio.wait_for(ready.wait(), 5)
        live = server.live[participant.job.id]
        payload = json.loads(live.value.prompt)["input"]
        assert live.value.output_schema and not live.value.tools
        if role == "structured-sync-C":
            assert "Current job title: Python API Engineer." in live.value.prompt
            output = RichReconcileProposal(updates=[dict(recordId="candidate-1", fieldKey="title", text="Python API Engineer")])
        else:
            block = payload["selection"][0]
            text = "".join(span["text"] for span in block["content"])
            original = next(block for block in participant.workspace.project.document.blocks() if block.id == "narrative").content[0].text
            assert text == original and participant.marker in text and "Python. Wrote" in text
            block["content"][0]["text"] = text.replace("Python. Wrote", "Python; Wrote", 1)
            output = RichRewriteProposal(replacements=[dict(blockId=block["id"], blocks=[block])])
        complete_shared(server, participant.job.id, output.model_dump_json(by_alias=True))
        result = await asyncio.wait_for(proof.completed(participant), 10)
        assert result.execution == "completed" and result.publication == "saved" and result.receipt.durable
        current = service.projects.storage.read_committed(project)[0]
        if role == "structured-sync-C":
            from packages.resume_core.rich_fields import set_text
            expected_facts = participant.workspace.project.facts.model_copy(deep=True)
            candidate = next(record for record in expected_facts.records if record.id == "candidate-1")
            actual = next(record for record in current.project.facts.records if record.id == "candidate-1")
            set_text(candidate, "title", "Python API Engineer")
            candidate.revision, candidate.title.revision = actual.revision, actual.title.revision
            expected_facts.revision = current.project.facts.revision
            assert current.project.facts == expected_facts
        else:
            expected = participant.workspace.project.document.model_copy(deep=True)
            block = next(block for block in expected.blocks() if block.id == "narrative")
            block.content[0].text = original.replace("Python. Wrote", "Python; Wrote", 1)
            expected.revision = current.project.document.revision
            for before_region, after_region in zip(expected.regions, current.project.document.regions):
                before_region.revision = after_region.revision
            actual_blocks = {block.id: block for block in current.project.document.blocks()}
            for before_block in expected.blocks():
                before_block.revision = actual_blocks[before_block.id].revision
            assert current.project.document == expected and current.project.facts == participant.workspace.project.facts
        assert result.attempts[-1].cleanup_verified and not result.attempts[-1].native_started
        assert participant.runtime["schemaValidated"] and participant.runtime["logicalAttempts"] == 1
        assert participant.runtime["repairTurns"] == 0 and not participant.runtime["nativeStarted"]
        assert not service.admission.locked() and ledger.read_bytes() == before
    finally:
        await service.shutdown()
        await server.close()
