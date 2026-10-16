"""Real publication cutpoints and fresh-object recovery, including owned process death."""

import json
from pathlib import Path

import pytest

from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_store import BackgroundFailure, expiration
from packages.resume_core.models.background import PublicationBarrierV1
from spikes.background.fixtures import TIME
from spikes.background.harness import OfflineGuard
from tests.support.background_publication import PublicationFixture

EXCEPTION_CUTS = [(f"NB-D01:v{number:02d}", boundary, side, writer)
    for start, boundary in [(9, "intent_stored"), (17, "workspace_replaced"), (21, "workspace_durable"),
        (25, "generation_history_durable"), (29, "receipt_stored"), (33, "response_event_delivery")]
    for number, side, writer in [(start, "before", "clean_detached"), (start + 1, "before", "attached_uncertain"),
        (start + 2, "after", "clean_detached"), (start + 3, "after", "attached_uncertain")]]
PROCESS_CUTS = [(f"NB-D01:v{number:02d}", phase, writer)
    for start, phase in [(49, "workspace_durable"), (51, "generation_history_durable"), (53, "receipt_stored")]
    for number, writer in [(start, "clean_detached"), (start + 1, "attached_uncertain")]]


def attach(fixture):
    fixture.coordinator.authority.clock = ControlledDeadlines()
    with fixture.jobs.guard(fixture.project) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        writer = state.writer
        writer.status, writer.barrier_generation = "attached", 1
        writer.acknowledged_cursor, writer.touch_generation = 2, 3
        writer.acknowledged_revision = fixture.canonical._read_committed_unlocked(fixture.project)[0].project_revision
        barrier = PublicationBarrierV1(schemaVersion=1, projectId=fixture.project, lineage=state.lineage,
            writerEpoch=writer.epoch, incarnation=writer.incarnation, generation=writer.barrier_generation,
            token="synthetic_fresh_barrier_acknowledgment", acknowledgedRevision=writer.acknowledged_revision,
            actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation,
            expiresAt=expiration(TIME, 1), state="acked")
        state.barrier = barrier
        fixture.jobs._write(directory, state, fixture.jobs._all())
        fixture.coordinator.authority.acknowledged(writer, barrier)
    return barrier


@pytest.mark.parametrize("variant,phase,side,writer", EXCEPTION_CUTS, ids=[item[0] for item in EXCEPTION_CUTS])
def test_publication_exception_cut_has_only_the_exact_old_saved_or_fenced_outcome(tmp_path, variant, phase, side, writer):
    reached = []
    target = "before_" + phase if side == "before" else phase
    def fail(name, project):
        if name == target:
            reached.append(project)
            raise OSError("Synthetic exception at " + target)
    fixture = PublicationFixture(tmp_path, observer=fail)
    job, proposal, _batch = fixture.accepted()
    if writer == "attached_uncertain":
        attach(fixture)
    original_payload = fixture.artifacts.payload_for(fixture.project, proposal.payload)
    try:
        fixture.publish(job, proposal)
    except (OSError, BackgroundFailure):
        pass
    assert reached == [fixture.project], variant
    restarted = fixture.fresh()
    state = restarted.coordinator.recover(fixture.project)
    current = restarted.current()
    saved = phase not in {"intent_stored"} and not (phase == "workspace_replaced" and side == "before")
    known = restarted.jobs.read(fixture.project, job.id)
    assert (known.publication == "saved") == saved
    assert len(current.mutation_replay) == int(saved)
    assert restarted.artifacts.payload_for(fixture.project, proposal.payload) == original_payload
    assert restarted.coordinator.recover(fixture.project) == state
    if writer == "attached_uncertain":
        assert state.writer.status == "attached" and restarted.coordinator.authority.acks == {}
    if saved:
        assert known.receipt.request_sha256 == current.mutation_replay[0].request_sha256
        assert restarted.publish(job, proposal).receipt == known.receipt
    elif state.intents:
        assert known.publication == "save_failed" and not state.inverses
    else:
        assert known.publication == "waiting_for_sync" and not state.inverses


@pytest.mark.parametrize("variant,phase,writer", PROCESS_CUTS, ids=[item[0] for item in PROCESS_CUTS])
def test_owned_process_termination_recovers_exact_durable_proof(tmp_path, variant, phase, writer):
    fixture = PublicationFixture(tmp_path / "store")
    job, proposal, _batch = fixture.accepted()
    barrier = attach(fixture) if writer == "attached_uncertain" else None
    guard = OfflineGuard(tmp_path / "peer", role="publication")
    child = guard.spawn(guard.child)
    try:
        command = {"sourceRoot": str(Path(__file__).resolve().parents[2]), "dataRoot": str(fixture.root),
            "phase": phase, "project": fixture.project, "job": job.id, "proposalSha256": proposal.payload_sha256,
            "barrierAck": barrier.model_dump(mode="json", by_alias=True) if barrier else None}
        child.process.stdin.write(json.dumps(command) + "\n")
        child.process.stdin.flush()
        reached = child.read()
        assert reached == {"type": "cut", "name": phase, "project": fixture.project, "pid": child.process.pid}, variant
        child.process.kill()
        child.close()
        assert child.closed and child.process.returncode is not None
    finally:
        guard.close()
    restarted = fixture.fresh()
    recovered = restarted.coordinator.recover(fixture.project)
    known = restarted.jobs.read(fixture.project, job.id)
    assert known.receipt.durable and len(restarted.current().mutation_replay) == 1
    assert len(recovered.inverses) == 1 and recovered.inverses[0].owner == "backend"
    assert restarted.coordinator.recover(fixture.project) == recovered
    assert restarted.publish(job, proposal).receipt == known.receipt


@pytest.mark.parametrize("variant", [f"NB-D03:v{index:02d}" for index in range(1, 6)])
def test_recovery_can_itself_crash_and_never_reapply_or_reset_history(tmp_path, variant):
    def fail(name, _project):
        if name == "workspace_durable":
            raise OSError("Original synthetic crash")
    fixture = PublicationFixture(tmp_path, observer=fail)
    job, proposal, _batch = fixture.accepted()
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fixture.publish(job, proposal)
    phases = {"NB-D03:v01": "before_proof_recovery", "NB-D03:v02": "after_generation_recovery",
        "NB-D03:v03": "after_receipt_recovery"}
    if variant in phases:
        reached = []
        def interrupt(name, _project):
            if name == phases[variant]:
                reached.append(name)
                raise OSError("Synthetic recovery interruption")
        repair = fixture.fresh(observer=interrupt)
        with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
            repair.coordinator.recover(fixture.project)
        assert reached == [phases[variant]]
        del repair
    root, project = fixture.root, fixture.project
    del fixture
    from packages.resume_core.agent_artifacts import JobArtifacts
    from packages.resume_core.background_history import ScopeHistory
    from packages.resume_core.background_publication import CanonicalCoordinator
    from packages.resume_core.background_store import JobStore
    from packages.resume_core.rich_project_store import RichProjectStore
    from resume_api.agent.context import query_fingerprint
    receipts = []
    for _index in range(3 if variant == "NB-D03:v04" else 2):
        jobs, canonical = JobStore(root), RichProjectStore(root)
        artifacts = JobArtifacts(jobs)
        coordinator = CanonicalCoordinator(jobs, ScopeHistory(jobs, query_fingerprint), canonical, artifacts.payload_unlocked)
        state = coordinator.recover(project)
        known = jobs.read(project, job.id)
        receipts.append(known.receipt)
        assert known.receipt.durable and len(canonical.read_committed(project)[0].mutation_replay) == 1
        assert len(state.inverses) == 1
    assert all(receipt == receipts[0] for receipt in receipts)
