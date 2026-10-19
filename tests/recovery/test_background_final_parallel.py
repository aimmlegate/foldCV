"""Exercise final-proof orchestration with synthetic peers and copied counters."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from spikes.background import native_integrated
from tests.recovery.test_background_appserver import shared_peer, shared_tool, complete_shared
from spikes.background.parallel_metrics import SCOPES, ORDERS, measure


@pytest.mark.parametrize("fault", ["failed-gate", "wrong-run", "changed-report", "stale-sources"])
def test_final_native_proof_rejects_incomplete_current_fast_before_profile_access(tmp_path, monkeypatch, fault):
    import uuid
    source = "spikes/background/native_integrated.py"
    hashes = {source: hashlib.sha256(Path(source).read_bytes()).hexdigest()}
    monkeypatch.setattr(native_integrated, "background_spec", lambda: {"sources": [source]})
    monkeypatch.setattr(native_integrated.ExperimentalCliProfile, "check_binary", lambda _self: pytest.fail("No profile access before green current fast"))
    (tmp_path / "execution.json").write_text("synthetic report")
    context = dict(sourceHashes=hashes, runId="frozen-run")
    validation = dict(outcome="passed", runId="frozen-run", sourceSha256=native_integrated.source_digest(hashes),
        reportSha256=hashlib.sha256((tmp_path / "execution.json").read_bytes()).hexdigest())
    if fault == "failed-gate": validation["outcome"] = "failed"
    elif fault == "wrong-run": validation["runId"] = "other-run"
    elif fault == "changed-report": validation["reportSha256"] = "0" * 64
    else: context["sourceHashes"] = {source: "0" * 64}
    for name, value in (("context", context), ("validation", validation)):
        (tmp_path / (name + ".json")).write_text(json.dumps(value))
    root = Path("/private/tmp") / ("foldcv-nb07b-native-rejected-" + uuid.uuid4().hex)
    with pytest.raises(ValueError, match="complete current fast"):
        native_integrated.IntegratedProof(root, tmp_path)
    assert not root.exists()


@pytest.mark.parametrize("fault", ["equal-fragments", "outside-text", "style", "other-block", "fact"])
def test_exact_final_document_accepts_equal_text_fragments_and_rejects_other_changes(tmp_path, fault):
    from types import SimpleNamespace
    from packages.resume_core.models.rich_document import StyledText
    from tests.support.agent import isolated_project
    _journal, _store, before, _conversation = isolated_project(tmp_path)
    block = next(b for b in before.project.document.blocks() if b.id == "narrative")
    block.content = [StyledText(type="text", text="Built REST APIs.", styles={})]
    current = before.model_copy(deep=True)
    edited = next(b for b in current.project.document.blocks() if b.id == "narrative")
    edited.content = [StyledText(type="text", text="Developed", styles={}), StyledText(type="text", text=" REST APIs.", styles={})]
    if fault == "outside-text": edited.content[1].text = " REST APIs and invented facts."
    elif fault == "style": edited.content[0].styles.bold = True
    elif fault == "other-block": next(b for b in current.project.document.blocks() if b.id == "quote").content[0].text = "Changed outside the scope"
    elif fault == "fact": current.project.facts.records[0].name.raw_text = "Changed fact"
    if fault == "equal-fragments":
        native_integrated.IntegratedProof.exact_document(SimpleNamespace(workspace=before), current, "Built", "Developed")
    else:
        with pytest.raises(ValueError, match="more than its exact requested text"):
            native_integrated.IntegratedProof.exact_document(SimpleNamespace(workspace=before), current, "Built", "Developed")


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("order", ORDERS, ids=["first-second", "second-first"])
def test_final_conflict_measurement_keeps_narrow_independence_and_actual_rejection_reasons(tmp_path, scope, order):
    result = measure(tmp_path, scope, order)
    assert result["order"] == list(order)
    assert result["outcomes"][0]["outcome"] == "saved"
    assert (result["outcomes"][1]["reason"] is None) == (scope == "narrow-independent")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True], ids=["both-triples", "invalid-structured-result"])
async def test_integrated_native_harness_closes_resources_and_keeps_real_counters_unchanged(tmp_path, monkeypatch, failure):
    import httpx
    from packages.resume_core.models.agent import AgentReadSnapshot
    from packages.resume_core.rich_sync import RichReconcileProposal
    from packages.resume_core.text_rewrite import PlainTextReply
    from resume_api.jobs.appserver import CapabilityClient, SharedAgentRuntime, SharedContentProvider
    from tests.recovery.test_agent_edits import command, replace
    from tools.background_evidence import assert_native_bindings
    real_ledger = native_integrated.LEDGER
    original = real_ledger.read_bytes()
    copied = tmp_path / "docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json"
    copied.parent.mkdir(parents=True)
    fixture_ledger = json.loads(original)
    fixture_ledger["attempts"] = [row for row in fixture_ledger["attempts"] if row["pool"] != "NB07b"]
    fixture_ledger["pools"]["NB07b"].update(spent=0, dispatchClosed=False)
    copied.write_text(json.dumps(fixture_ledger))
    monkeypatch.setattr(native_integrated, "LEDGER", copied)
    monkeypatch.setattr(native_integrated, "HANDOFF", tmp_path / "retained")
    monkeypatch.setattr(native_integrated, "assert_native_bindings",
        lambda bindings, required, _root, **options: assert_native_bindings(bindings, required, tmp_path, **options))
    source = "spikes/background/native_integrated.py"
    hashes = {source: hashlib.sha256(Path(source).read_bytes()).hexdigest()}
    proof = native_integrated.IntegratedProof.__new__(native_integrated.IntegratedProof)
    mappings = json.loads(Path("tests/requirements.json").read_text())["backgroundExecution"]["nativeBindings"]
    proof.initialize(tmp_path / "proof", tmp_path / "controlled", {"sources": [source], "nativeBindings": mappings}, hashes)
    def client(value):
        session = proof.service.supervisor.controls[value.job_id].owned.session
        return CapabilityClient(value, transport=httpx.ASGITransport(app=session))
    monkeypatch.setattr("resume_api.jobs.parallel.SharedAgentRuntime",
        lambda server, native: SharedAgentRuntime(server, native=native, client_factory=client))
    created = asyncio.Queue()
    outputs = {}
    class Structured(SharedContentProvider):
        async def execute(self, request, cancel):
            if request.result_type is PlainTextReply:
                text = request.text.split("\n\nSelected text:\n", 1)[1]
                value = PlainTextReply(text=text.replace("Python. Wrote", "Python; Wrote"))
                outputs[self.job_id] = " " if failure else value.text
            else:
                assert request.result_type is RichReconcileProposal
                value = RichReconcileProposal(updates=[dict(recordId="candidate-1", fieldKey="title", text="Python API Engineer")])
                outputs[self.job_id] = "invalid structured result" if failure else value.model_dump_json(by_alias=True)
            return await super().execute(request, cancel)
    monkeypatch.setattr("resume_api.jobs.parallel.SharedContentProvider", Structured)
    def server(root, _connection, *, wire_audit):
        peer = shared_peer(root)
        peer.verify_host = lambda pipe: (pipe.process.pid,)
        peer.wire_audit = wire_audit
        created.put_nowait(peer)
        return peer
    monkeypatch.setattr(native_integrated.SharedAppServer, "native", server)
    def exclusion():
        assert proof.server.owner_context is not None
        proof.exclusion_checks.extend(dict(variant=proof.variant, action=action, result="BUSY", synthetic=True)
            for action in ("second-api", "maintenance", "login"))
    monkeypatch.setattr(proof, "check_exclusion", exclusion)
    groups = native_integrated.GROUPS[:1] if failure else native_integrated.GROUPS
    try:
        for variant in groups:
            task = asyncio.create_task(proof.group(variant))
            peer = await asyncio.wait_for(created.get(), 10)
            await asyncio.wait_for(proof.overlap.wait(), 15)
            assert len(proof.service.supervisor.active_controls) == len(peer.live) == 3
            assert len(proof.service.parallel_owner.permits) == 3
            assert len({live.server_pid for live in peer.live.values()}) == 1
            for index, participant in enumerate(proof.participants):
                if not participant.role.startswith("agent-"):
                    continue
                read = await shared_tool(peer, participant.job.id, "get_resume_context",
                    {"query": {"kind": "document", "ids": ["narrative"]}}, 100 + index * 10)
                if variant == "NB-X03:v03":
                    snapshot = AgentReadSnapshot.model_validate(read["snapshot"])
                    start = len(participant.marker) + 2
                    prepared = await shared_tool(peer, participant.job.id, "prepare_edit_batch",
                        {"request": command(replace(snapshot, "narrative", start, start + 5, "Developed")).model_dump(by_alias=True)},
                        101 + index * 10)
                    assert prepared["disposition"] == "prepared", prepared
                    result = await shared_tool(peer, participant.job.id, "apply_edit_batch",
                        {"request": {"batchId": prepared["batchId"]}}, 102 + index * 10)
                    assert result["disposition"] == ("waiting_for_sync" if participant.role == "agent-B" else "saved")
                else:
                    await shared_tool(peer, participant.job.id, "get_working_facts", {}, 101 + index * 10)
                complete_shared(peer, participant.job.id, participant.marker + ": completed synthetic tool sequence")
            for participant in proof.participants:
                if participant.role.startswith("structured-"):
                    complete_shared(peer, participant.job.id, outputs[participant.job.id])
            if failure:
                with pytest.raises(ValueError, match="Final native execution failed"):
                    await asyncio.wait_for(task, 20)
                assert proof.failed and json.loads((proof.directory / "failure.json").read_text())["noRetry"]
                assert all(row["status"] == "failed" for row in json.loads(copied.read_text())["attempts"] if row["pool"] == "NB07b")
            else:
                await asyncio.wait_for(task, 20)
                assert not proof.failed
            assert proof.service.parallel_owner.login_allowed() and not proof.service.admission.locked()
            shutdown = json.loads((proof.directory / "owner-shutdown.json").read_text())
            assert shutdown["ownedPidsGone"] and shutdown["operationRemoved"] and shutdown["profileLockReleased"]
            assert all(row["ownedGroupCleanupVerified"] for row in peer.shutdowns)
        ledger = json.loads(copied.read_text())
        assert ledger["pools"]["NB07b"]["spent"] == (3 if failure else 6)
        if not failure:
            proof.finalize()
            retained = json.loads((tmp_path / "retained/nb07b-native.json").read_text())
            assert set(retained["variants"]) == {"NB-X03:v01", "NB-X03:v02", "NB-X03:v03", "NB-X03:v04"}
            assert retained["nativeStarts"] == 6 and retained["schedulerIntegrationAccepted"]
        assert real_ledger.read_bytes() == original
    finally:
        for service in proof.services:
            await service.shutdown()
        if "task" in locals():
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("fault", ["none", "different-parent-turn", "unvalidated-parent", "multiple-prepare",
    "not-durable", "new-turn", "early-save", "canonical-changed"])
def test_final_publication_alias_requires_the_same_actual_deferred_turn(tmp_path, fault):
    from tests.recovery.test_background_native_proof import proof_fixture
    from tools.background_evidence import assert_native_bindings
    sources, _bindings, report, ledger, runtimes, _shutdown, _wire, save = proof_fixture(tmp_path)
    parent = report["variants"].pop("NB-R05:v01")
    report["variants"]["NB-X03:v03"] = parent
    ledger["pools"] = {"NB07b": dict(authorized=True, cap=6, spent=2)}
    for row in ledger["attempts"]:
        row.update(pool="NB07b", variant="NB-X03:v03")
    alias = "NB-X03:v02"
    report["variants"][alias] = {**parent, "turns": [parent["turns"][1]], "coveredBy": "NB-X03:v03"}
    runtime = runtimes["turn-1.json"]
    runtime["publication"] = dict(exactRequestedText=True, onePreparedBatch=True, oneApply=True,
        durableReceipt=True, noNewTurnForSave=True, factsAndOtherContentUnchanged=True,
        turnResourcesExitedBeforeSave=True, canonicalUnchangedUntilReturn=True)
    if fault == "different-parent-turn":
        parent["turns"] = parent["turns"][:1]
    elif fault == "unvalidated-parent": parent["outcome"] = "pending"
    elif fault != "none":
        key = {"multiple-prepare": "onePreparedBatch", "not-durable": "durableReceipt", "new-turn": "noNewTurnForSave",
            "early-save": "turnResourcesExitedBeforeSave", "canonical-changed": "canonicalUnchangedUntilReturn"}[fault]
        runtime["publication"][key] = False
    bindings = {alias: dict(evidence="proof.json", pool="NB07b", transport="shared_appserver_v1", roles=["agent-B"],
        attemptVariant="NB-X03:v03", attemptRole="agent-B", coveredBySameActualTurn=True)}
    save()
    if fault == "none":
        assert_native_bindings(bindings, {alias}, tmp_path, sources=sources, require_pass=True)
    else:
        with pytest.raises(SystemExit):
            assert_native_bindings(bindings, {alias}, tmp_path, sources=sources, require_pass=True)
