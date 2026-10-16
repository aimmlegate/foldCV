"""A durable inverse has one owner across adoption ACKs, reload and crash cuts."""

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_writers import WriterSessions
from packages.resume_core.models.background import WriterBarrierAckV1, WriterHistoryRequestV1, WriterOpenV1, WriterProofV1
from tests.recovery.test_background_writer_sessions import WriterFixture


def saved_background(root, *, attached=False):
    fixture = WriterFixture(root)
    job, proposal, _batch = fixture.publication.accepted()
    if attached:
        fixture.writers.barrier(fixture.project, WriterBarrierAckV1(**fixture.flush_request().model_dump(by_alias=True),
            generation=fixture.view.writer.barrier_generation + 1, token="synthetic_barrier_token_012345678901234",
            touchGeneration=fixture.view.writer.touch_generation))
    else:
        fixture.writers.detach(fixture.project, fixture.flush_request())
    assert fixture.publication.publish(job, proposal).receipt.durable
    if not attached:
        current = fixture.publication.current()
        fixture.view = fixture.writers.open(fixture.project, fixture.open_request.model_copy(update={
            "incarnation": "adopting-connection", "canonical_revision": current.project_revision,
            "canonical_sha256": digest_bytes(current)}))
        fixture.proof = WriterProofV1(schemaVersion=1, lineage=fixture.view.writer.lineage, epoch=fixture.view.writer.epoch,
            sessionId=fixture.view.writer.session_id, incarnation=fixture.view.writer.incarnation,
            credential=fixture.open_request.credential)
    return fixture, job, proposal


def transfer_request(fixture, job, proposal):
    inverse = next(item for item in fixture.publication.jobs.load(fixture.project).inverses if item.job_id == job.id)
    return WriterHistoryRequestV1(**fixture.flush_request().model_dump(by_alias=True), jobId=job.id,
        proposalId=proposal.id, transferId=inverse.transfer_id)


@pytest.mark.parametrize("attached", [False, True], ids=["headless", "mounted"])
def test_offer_preserves_exact_saved_proof_and_transfers_one_inverse_owner(tmp_path, attached):
    fixture, job, proposal = saved_background(tmp_path, attached=attached)
    request = transfer_request(fixture, job, proposal)
    before = fixture.publication.current()
    offer = fixture.writers.history_offer(fixture.project, request)
    assert fixture.writers.history_offer(fixture.project, request) == offer
    assert offer.job.receipt.durable and offer.saved.workspace == before
    assert offer.preview.workspace.project.document != before.project.document
    assert offer.preview.durability == "pending" and offer.batch_id == proposal.payload.batch_id
    assert fixture.publication.current() == before
    prepared = fixture.writers.begin_history_transfer(fixture.project, request)
    assert prepared.owner == "transferring"
    assert fixture.writers.begin_history_transfer(fixture.project, request) == prepared
    owned = fixture.writers.acknowledge_history_transfer(fixture.project, request)
    assert owned.owner == "session" and (owned.writer_epoch, owned.incarnation) == (fixture.proof.epoch, fixture.proof.incarnation)
    assert fixture.writers.acknowledge_history_transfer(fixture.project, request) == owned
    assert fixture.publication.current() == before and len(before.mutation_replay) == 1
    assert len(fixture.publication.jobs.load(fixture.project).inverses) == 1


@pytest.mark.parametrize("variant,attached,cut", [
    ("NB-D01:v41", False, "before_undo_owner_transfer"), ("NB-D01:v42", True, "before_undo_owner_transfer"),
    ("NB-D01:v43", False, "undo_owner_transfer"), ("NB-D01:v44", True, "undo_owner_transfer")],
    ids=[f"NB-D01:v{number}" for number in range(41, 45)])
def test_transfer_crash_cut_retains_one_recoverable_owner_without_another_edit(tmp_path, variant, attached, cut):
    fixture, job, proposal = saved_background(tmp_path, attached=attached)
    request = transfer_request(fixture, job, proposal)
    fixture.writers.begin_history_transfer(fixture.project, request)
    before = fixture.publication.current()
    reached = []
    def fail(name, _project):
        if name == cut:
            reached.append(name)
            raise OSError("Synthetic ownership ACK cut")
    fixture.writers.observer = fail
    with pytest.raises(BackgroundFailure, match="JOB_STORE_UNAVAILABLE"):
        fixture.writers.acknowledge_history_transfer(fixture.project, request)
    assert reached == [cut]
    stored = fixture.publication.jobs.load(fixture.project).inverses[0]
    assert stored.owner == ("transferring" if cut.startswith("before_") else "session")
    fresh = fixture.publication.fresh(); fresh.jobs.clock = fixture.wall; fresh.coordinator.authority.clock = fixture.elapsed
    writers = WriterSessions(fresh.coordinator)
    writers.recover_all()
    current = fresh.current()
    resumed = writers.open(fixture.project, WriterOpenV1(schemaVersion=1, sessionId=fixture.proof.session_id,
        incarnation="after-crash", credential=fixture.proof.credential, previousEpoch=fixture.proof.epoch,
        previousIncarnation=fixture.proof.incarnation, canonicalRevision=current.project_revision,
        canonicalSha256=digest_bytes(current), actionCursor=0))
    assert resumed.inverses[0].owner == "backend" and resumed.inverses[0].transfer_id != request.transfer_id
    proof = fixture.proof.model_copy(update={"incarnation": "after-crash"})
    fixture.publication, fixture.writers, fixture.proof = fresh, writers, proof
    recovered = transfer_request(fixture, job, proposal)
    assert writers.begin_history_transfer(fixture.project, recovered).owner == "transferring"
    assert writers.acknowledge_history_transfer(fixture.project, recovered).owner == "session"
    assert fresh.current() == before and len(fresh.jobs.load(fixture.project).inverses) == 1
    with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
        writers.acknowledge_history_transfer(fixture.project, request)


@pytest.mark.parametrize("boundary", ["detach", "suspend", "restart"])
def test_leaving_the_writer_returns_its_inverse_to_the_journal(tmp_path, boundary):
    fixture, job, proposal = saved_background(tmp_path)
    request = transfer_request(fixture, job, proposal)
    fixture.writers.begin_history_transfer(fixture.project, request)
    fixture.writers.acknowledge_history_transfer(fixture.project, request)
    if boundary == "detach":
        fixture.writers.detach(fixture.project, fixture.flush_request())
    elif boundary == "suspend":
        fixture.writers.suspend(fixture.project, fixture.proof)
    else:
        fixture.writers.recover_all()
    inverse = fixture.publication.jobs.load(fixture.project).inverses[0]
    assert inverse.owner == "backend" and inverse.writer_epoch is None and inverse.incarnation is None
    assert inverse.transfer_id != request.transfer_id
    with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
        fixture.writers.acknowledge_history_transfer(fixture.project, request)


def test_duplicate_reload_has_one_connection_and_one_idempotent_inverse_ack(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    fixture, job, proposal = saved_background(tmp_path)
    request = transfer_request(fixture, job, proposal)
    fixture.writers.begin_history_transfer(fixture.project, request)
    fixture.writers.acknowledge_history_transfer(fixture.project, request)
    fixture.writers.suspend(fixture.project, fixture.proof)
    before = fixture.publication.current()
    gate = threading.Barrier(2)
    def resume(incarnation):
        writers = WriterSessions(fixture.publication.coordinator)
        gate.wait(timeout=10)
        try:
            view = writers.open(fixture.project, WriterOpenV1(schemaVersion=1, sessionId=fixture.proof.session_id,
                incarnation=incarnation, credential=fixture.proof.credential, previousEpoch=fixture.proof.epoch,
                previousIncarnation=fixture.proof.incarnation, canonicalRevision=before.project_revision,
                canonicalSha256=digest_bytes(before), actionCursor=0))
            return writers, view
        except BackgroundFailure as error:
            assert error.code == "WRITER_UNKNOWN"
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(resume, ["reload-one", "reload-two"]))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    fixture.writers, fixture.view = winners[0]
    fixture.proof = fixture.proof.model_copy(update={"incarnation": fixture.view.writer.incarnation})
    fresh = transfer_request(fixture, job, proposal)
    fixture.writers.begin_history_transfer(fixture.project, fresh)
    ack = fixture.writers.acknowledge_history_transfer(fixture.project, fresh)
    assert fixture.writers.acknowledge_history_transfer(fixture.project, fresh) == ack
    assert len(fixture.publication.jobs.load(fixture.project).inverses) == 1
    assert fixture.publication.current() == before
