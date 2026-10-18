"""NB00a executable contracts, owned subprocesses and controlled protocol orders."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import get_args

import pytest
from pydantic import ValidationError

from packages.resume_core.background_limits import LIMITS, policy
from packages.resume_core.models.background import BACKGROUND_CONTRACTS, BackgroundSidecarV1, JobSubmissionV1, Tool
from spikes.background.corpus import ACTIONS, FIXED_SEEDS, ORDERS, ReferenceModel, trace
from spikes.background.fixtures import examples, submission
from spikes.background.harness import Clock, Hooks, OfflineDenied, OfflineGuard, ScriptedPeer, SyntheticAttempts
from spikes.background.protocol import ProtocolProbe

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def native_counter_unchanged():
    ledger = ROOT / "docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json"
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    yield
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before


@pytest.fixture
def offline(tmp_path):
    guard = OfflineGuard(tmp_path / "owned-pipes")
    yield guard
    guard.close()


@pytest.mark.parametrize("variant", [f"NB-R03:v{i:02}" for i in range(1, 7)])
def test_attempt_spending_survives_failures_and_restart(tmp_path, offline, monkeypatch, variant):
    ledger = SyntheticAttempts(tmp_path)
    if variant == "NB-R03:v02":
        with pytest.raises(OSError, match="lost spend"):
            ledger.spend("attempt-one", lost_ack=True)
    else:
        assert ledger.spend("attempt-one")
        if variant == "NB-R03:v01":
            def failed_spawn(*args, **kwargs):
                raise OSError("injected spawn failure")
            monkeypatch.setattr(subprocess, "Popen", failed_spawn)
            ledger.mark("attempt-one", "spawn_claimed")
            with pytest.raises(OSError, match="spawn failure"):
                offline.spawn(offline.child)
        elif variant != "NB-R03:v03":
            ledger.mark("attempt-one", "spawn_claimed")
            child = offline.spawn(offline.child)
            assert child.command("probe") == {"type": "alive"}
            ledger.mark("attempt-one", {"NB-R03:v05": "AUTH_REQUIRED", "NB-R03:v06": "RATE_LIMITED"}.get(variant, "child_started"))
            child.close()
    restarted = SyntheticAttempts(tmp_path)
    assert not restarted.spend("attempt-one")
    assert len(restarted.read()["attempts"]) == 1
    assert restarted.read()["kind"] == "synthetic"
    assert offline.spawns == int(variant in {"NB-R03:v04", "NB-R03:v05", "NB-R03:v06"})


@pytest.mark.parametrize("variant", [f"NB-G01:v{i:02}" for i in range(1, 6)])
def test_offline_guard_rejects_production_boundaries(offline, monkeypatch, variant):
    if variant != "NB-G01:v05":
        def forbidden(*args, **kwargs):
            raise AssertionError("production spawn was reached")
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        with pytest.raises(OfflineDenied):
            if variant == "NB-G01:v01":
                offline.spawn(Path("/usr/bin/true"))
            elif variant == "NB-G01:v02":
                offline.provider(forbidden)
            elif variant == "NB-G01:v03":
                offline.network("https://synthetic.invalid")
            else:
                offline.spawn(offline.child, env={"OPENAI_API_KEY": "synthetic-fixture"})
        assert offline.spawns == 0
    else:
        child = offline.spawn(offline.child)
        assert child.command("probe") == {"type": "alive"}
        assert child.command("stop") == {"type": "stopped"}
        child.close()
        assert child.process.returncode == 0


def test_fake_process_identity_and_neighbour_cleanup(offline):
    first = offline.spawn(offline.child)
    second = offline.spawn(offline.child)
    first.close()
    assert first.process.poll() is not None
    assert second.process.poll() is None
    assert second.command("probe") == {"type": "alive"}
    second.close()
    offline.child.chmod(0o600)
    offline.child.write_text("raise SystemExit('changed child')\n")
    with pytest.raises(OfflineDenied, match="changed"):
        offline.spawn(offline.child)
    offline.child.unlink()
    offline.child.symlink_to(offline.source)
    with pytest.raises(OfflineDenied, match="unregistered"):
        offline.spawn(offline.child)


def test_failed_fake_cleanup_retains_ownership_and_does_not_kill_a_neighbour(offline, monkeypatch):
    first = offline.spawn(offline.child)
    neighbour = offline.spawn(offline.child)
    with monkeypatch.context() as patch:
        def fail_owned_signal():
            raise PermissionError("synthetic owned cleanup failure")
        patch.setattr(first.process, "terminate", fail_owned_signal)
        with pytest.raises(PermissionError, match="owned cleanup failure"):
            first.close()
        assert not first.closed and first.process.poll() is None
        assert neighbour.command("probe") == {"type": "alive"}
        assert offline.cleanup_fenced
        with pytest.raises(OfflineDenied, match="fenced"):
            offline.spawn(offline.child)
    first.close()
    assert neighbour.command("probe") == {"type": "alive"}


@pytest.mark.asyncio
async def test_scripted_tools_are_isolated_and_cancelled_after_a_held_reply(offline):
    hooks = Hooks()
    hold = hooks.hold("proposal_durable")
    first = offline.inject(ScriptedPeer("A", "one", hooks))
    second = offline.inject(ScriptedPeer("B", "two", Hooks()))
    assert offline.provider(first) is first
    with pytest.raises(OfflineDenied, match="scope"):
        await first.call("B", "two")
    task = asyncio.create_task(first.call("A", "one"))
    try:
        await asyncio.wait_for(hold.reached.wait(), timeout=10)
        first.cancelled.set()
        assert await second.call("B", "two") == "synthetic:B:two"
        hold.release.set()
        with pytest.raises(OfflineDenied, match="during call"):
            await task
    finally:
        hold.release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    hooks.verify()
    assert first.calls == [("A", "one")]
    assert second.calls == [("B", "two")]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["timeout_before_claim", "claim_before_timeout"])
async def test_barrier_timeout_keeps_canonical_result_and_post_timeout_input(tmp_path, order):
    hooks, clock = Hooks(), Clock()
    probe = ProtocolProbe(tmp_path / "protocol", clock, hooks)
    await probe.propose()
    probe.finish_runtime()
    clock.advance(LIMITS.active_seconds * 1000, wall_ms=-5000)
    await probe.ack()
    with pytest.raises(ValueError, match="protected"):
        await probe.type("input between ACK and adoption")
    hold = hooks.hold("before_commit_claim" if order == "timeout_before_claim" else "workspace_durable")
    task = asyncio.create_task(probe.apply())
    try:
        await asyncio.wait_for(hold.reached.wait(), timeout=10)
        clock.advance(LIMITS.local_barrier_ms - 1)
        await probe.timeout()
        assert probe.barrier in {"acked", "commit_claimed"}
        clock.advance(1)
        await probe.timeout()
        if order == "claim_before_timeout":
            await probe.type("new draft after timeout")
        hold.release.set()
        receipt = await task
        restarted = ProtocolProbe(tmp_path / "protocol", clock, Hooks())
        if order == "timeout_before_claim":
            assert receipt == "waiting_for_sync"
            assert restarted.saved == {"value": "original", "mutations": []}
        else:
            assert restarted.saved == {"value": "saved result", "mutations": ["mutation-1"]}
            assert restarted.read("draft", None)["text"] == "new draft after timeout"
            assert not await probe.adopt(receipt, probe.generation)
            assert probe.visible == "new draft after timeout"
            assert await probe.apply() == receipt
        assert probe.authority and not probe.runtime_alive
        assert not probe.lock.locked()
    finally:
        hold.release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    hooks.verify()


@pytest.mark.asyncio
async def test_pending_proposal_is_single_copy_and_runtime_cleanup_does_not_revoke_it(tmp_path):
    probe = ProtocolProbe(tmp_path, Clock(), Hooks())
    await probe.propose()
    await probe.propose()
    with pytest.raises(ValueError, match="one accepted"):
        await probe.propose("unsaved-chain")
    probe.finish_runtime()
    await probe.ack()
    assert not await probe.adopt(None, probe.generation)
    receipt = await probe.apply()
    assert await probe.apply() == receipt
    assert await probe.adopt(receipt, probe.generation)
    assert probe.visible == "saved result"
    assert json.loads((tmp_path / "binding.json").read_text()) == {"proposal": "proposal-1",
        "payloadRef": "single-journal-payload", "authority": "active"}


@pytest.mark.asyncio
async def test_revoked_or_missing_protocol_authority_cannot_publish(tmp_path):
    probe = ProtocolProbe(tmp_path, Clock(), Hooks())
    assert await probe.apply() == "cancelled"
    await probe.propose()
    await probe.ack()
    probe.authority = False
    assert await probe.apply() == "cancelled"
    assert probe.read("canonical", None) is None


@pytest.mark.parametrize("name", list(BACKGROUND_CONTRACTS))
def test_versioned_background_contract_round_trip(name):
    value = examples()[name]
    model = BACKGROUND_CONTRACTS[name].model_validate(value)
    assert model.model_dump(mode="json", by_alias=True) == value


def test_check_only_capture_cannot_acquire_write_tools_or_use_interactive_admission():
    value = submission()
    value["allowEdits"] = False
    with pytest.raises(ValidationError, match="check-only"):
        JobSubmissionV1.model_validate(value)
    value["tools"] = ["get_resume_context"]
    value["guards"]["writes"] = []
    JobSubmissionV1.model_validate(value)
    value["schedulingClass"] = "interactive"
    with pytest.raises(ValidationError, match="server-assigned"):
        JobSubmissionV1.model_validate(value)


def test_job_tool_capture_uses_the_actual_bound_mcp_names():
    sys.path.insert(0, str(ROOT / "services/api/src"))
    from resume_api.agent.tools import TOOL_NAMES
    from packages.resume_core.models.importing import IMPORT_TOOLS
    assert set(get_args(Tool)) == set(TOOL_NAMES) | set(IMPORT_TOOLS)
    value = submission()
    value["tools"].append("read_public_page")
    with pytest.raises(ValidationError, match="web-disabled"):
        JobSubmissionV1.model_validate(value)
    value["allowWeb"] = True
    JobSubmissionV1.model_validate(value)
    for name in IMPORT_TOOLS:
        denied = {**value, "tools": [*value["tools"], name]}
        with pytest.raises(ValidationError, match="import tools are restricted"):
            JobSubmissionV1.model_validate(denied)


@pytest.mark.parametrize("fault", ["none", "foreign-project", "duplicate-request", "missing-request", "changed-hash",
    "metadata-full", "archived-resolved", "archived-pending", "archived-identity"])
def test_sidecar_keeps_request_identity_retention_and_foreign_authority_separate(fault):
    fixtures = examples()
    sidecar = fixtures["background_sidecar_v1"]
    job = fixtures["background_snapshot_v1"]
    request = {"identity": job["submission"]["identity"].copy(), "payloadSha256": job["submission"]["payloadSha256"],
        "jobId": job["id"], "expiresAt": "2026-11-15T12:00:00Z", "archivedResult": None}
    sidecar.update(jobs=[job], requests=[request])
    if fault == "foreign-project":
        sidecar["projectId"] = "another-project"
    elif fault == "duplicate-request":
        sidecar["requests"].append(request.copy())
    elif fault == "missing-request":
        sidecar["requests"] = []
    elif fault == "changed-hash":
        request["payloadSha256"] = "b" * 64
    elif fault == "metadata-full":
        from packages.resume_core.background_limits import LIMITS
        sidecar["generations"] = [fixtures["background_scope_guard_v1"]["reads"][0]] * LIMITS.metadata_project_records
    elif fault.startswith("archived-"):
        sidecar["jobs"] = []
        request["archivedResult"] = job
        if fault != "archived-pending":
            job.update(publication="no_change", proposalId=None)
        if fault == "archived-identity":
            request["identity"]["requestId"] = "another-request"
    if fault in {"none", "archived-resolved"}:
        BackgroundSidecarV1.model_validate(sidecar)
    else:
        with pytest.raises(ValidationError):
            BackgroundSidecarV1.model_validate(sidecar)


def test_policy_reserves_interactive_admission_and_bounds_retained_authority(offline):
    assert (LIMITS.pending_global, LIMITS.pending_project) == (20, 4)
    assert (LIMITS.pending_noninteractive_global, LIMITS.pending_noninteractive_project) == (16, 3)
    assert LIMITS.pending_global - LIMITS.pending_noninteractive_global == 4
    assert LIMITS.pending_project - LIMITS.pending_noninteractive_project == 1
    assert (LIMITS.executions, LIMITS.noninteractive_executions, LIMITS.serial_executions, LIMITS.render_workers) == (3, 2, 1, 2)
    assert LIMITS.reconciliation_dispatch_bound == 3
    assert LIMITS.local_barrier_ms == 750 < LIMITS.receipt_seconds * 1000
    assert LIMITS.proposal_bytes == LIMITS.inverse_bytes == 512 * 1024
    assert policy()["unresolvedPrunable"] is False
    assert policy()["queueConsumesActiveDeadline"] is False
    assert offline.spawns == 0


@pytest.mark.parametrize("seed", FIXED_SEEDS, ids=lambda seed: f"seed-{seed:02}")
def test_frozen_reference_corpus_is_reproducible_and_reaches_each_action(seed, background_evidence):
    result = trace(seed)
    assert result == trace(seed)
    assert result["transitions"] == len(result["log"]) == 200
    assert set(result["actions"]) == set(ACTIONS)
    assert set(result["orders"]) == set(ORDERS)
    background_evidence(result)


def test_unreached_controlled_hook_cannot_pass_teardown():
    hooks = Hooks()
    hooks.hold("commit_claimed")
    with pytest.raises(AssertionError, match="unreached"):
        hooks.verify()


@pytest.mark.parametrize("scenario", ["independent", "read-cycle", "edit-undo"])
def test_reference_oracle_uses_scoped_read_and_write_generations(scenario):
    oracle = ReferenceModel(1)
    for job, read, write in [("one", "Y" if scenario == "read-cycle" else "shared", "X"),
            ("two", "X" if scenario == "read-cycle" else "shared", "Y")]:
        assert oracle.step("submit", "A", job, read=read, write=write) == "accepted"
        assert oracle.step("start", "A", job) == "started"
        assert oracle.step("propose", "A", job) == "stored"
        assert oracle.step("runtime_exit", "A", job) == "released"
    if scenario == "edit-undo":
        oracle.step("touch", "A", "one", write="X")
        oracle.step("undo", "A", "one", write="X")
        assert oracle.projects["A"]["values"]["X"] == "original"
        assert oracle.step("claim", "A", "one") == "rejected"
        assert oracle.step("claim", "A", "two") == "claimed"
    else:
        assert oracle.step("claim", "A", "one") == "claimed"
        assert oracle.step("claim", "A", "two") == ("rejected" if scenario == "read-cycle" else "claimed")
