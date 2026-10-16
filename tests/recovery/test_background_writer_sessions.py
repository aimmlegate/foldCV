"""Writer authority and zero-diff touches use actual durable canonical stores."""

import pytest

from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_writers import WriterSessions
from packages.resume_core.models.background import (WriterAdvanceV1, WriterBarrierAckV1, WriterBarrierCommandV1,
    WriterOpenV1, WriterProofV1)
from tests.recovery.test_background_assets import Time
from tests.recovery.test_background_inverse import mutation, put
from tests.support.background_publication import PublicationFixture


class WriterFixture:
    def __init__(self, root):
        self.publication = PublicationFixture(root)
        self.wall = Time(self.publication.jobs.clock())
        self.elapsed = ControlledDeadlines()
        self.publication.jobs.clock = self.wall
        self.publication.coordinator.authority.clock = self.elapsed
        self.writers = WriterSessions(self.publication.coordinator)
        workspace = self.publication.current()
        self.open_request = WriterOpenV1(schemaVersion=1, sessionId="editor-session", incarnation="connection-one",
            credential="synthetic_writer_credential_0123456789", canonicalRevision=workspace.project_revision,
            canonicalSha256=digest_bytes(workspace), actionCursor=0)
        self.view = self.writers.open(self.project, self.open_request)
        self.proof = WriterProofV1(schemaVersion=1, lineage=self.view.writer.lineage, epoch=self.view.writer.epoch,
            sessionId=self.view.writer.session_id, incarnation=self.view.writer.incarnation,
            credential=self.open_request.credential)

    @property
    def project(self):
        return self.publication.project

    def advance(self, seconds):
        self.wall.advance(seconds); self.elapsed.advance(seconds)

    def flush_request(self, cursor=0, touches=()):
        current = self.publication.current()
        return WriterAdvanceV1(schemaVersion=1, proof=self.proof, canonicalRevision=current.project_revision,
            canonicalSha256=digest_bytes(current), actionCursor=cursor, touches=list(touches))

    def resumed(self, **changes):
        request = self.open_request.model_copy(update={"incarnation": "connection-two", "previous_epoch": self.proof.epoch,
            "previous_incarnation": self.proof.incarnation, **changes}, deep=True)
        return self.writers.open(self.project, request)


@pytest.mark.parametrize("variant", [f"NB-W07:v{index:02d}" for index in range(1, 7)])
def test_clean_resume_reconciles_a_new_incarnation_without_native_replay(tmp_path, variant):
    fixture = WriterFixture(tmp_path)
    if variant == "NB-W07:v06":
        fixture.writers.recover_all()
        fresh = fixture.publication.fresh()
        fresh.jobs.clock = fixture.wall
        fresh.coordinator.authority.clock = fixture.elapsed
        fixture.writers = WriterSessions(fresh.coordinator)
    else:
        fixture.writers.suspend(fixture.project, fixture.proof)
    if variant in {"NB-W07:v01", "NB-W07:v02", "NB-W07:v03"}:
        fixture.advance(LIMITS.writer_lease_seconds + {"NB-W07:v01": -0.001, "NB-W07:v02": 0, "NB-W07:v03": 0.001}[variant])
    resumed = fixture.resumed()
    assert resumed.canonical_ready and resumed.writer.status == "attached"
    assert resumed.writer.incarnation != fixture.proof.incarnation and resumed.workspace == fixture.publication.current()
    assert resumed.writer.acknowledged_revision == resumed.workspace.project_revision
    with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
        fixture.writers.heartbeat(fixture.project, fixture.proof)
    assert not fixture.publication.jobs.load(fixture.project).jobs


@pytest.mark.parametrize("variant", ["NB-W09:v01", "NB-W09:v02", "NB-W09:v03", "NB-W09:v04", "NB-W09:v05"])
def test_copied_identity_and_old_requests_never_gain_a_second_writer(tmp_path, variant):
    fixture = WriterFixture(tmp_path)
    if variant == "NB-W09:v01":
        with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
            fixture.resumed()
        assert fixture.writers.heartbeat(fixture.project, fixture.proof).writer.incarnation == fixture.proof.incarnation
        return
    fixture.writers.suspend(fixture.project, fixture.proof)
    winner = fixture.resumed()
    if variant == "NB-W09:v02":
        with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
            fixture.resumed(incarnation="losing-connection")
    elif variant == "NB-W09:v03":
        with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
            fixture.writers.heartbeat(fixture.project, fixture.proof)
    else:
        with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
            fixture.writers.flush(fixture.project, fixture.flush_request())
    assert fixture.publication.jobs.load(fixture.project).writer.incarnation == winner.writer.incarnation


@pytest.mark.parametrize("variant", [f"NB-W01:v{index:02d}" for index in range(1, 8)])
def test_real_writer_barrier_checks_expiry_revocation_and_exact_watermarks(tmp_path, variant):
    fixture = WriterFixture(tmp_path)
    job, proposal, _batch = fixture.publication.accepted()
    request = WriterBarrierAckV1(**fixture.flush_request().model_dump(by_alias=True),
        generation=fixture.view.writer.barrier_generation + 1,
        token="synthetic_barrier_token_012345678901234", touchGeneration=fixture.view.writer.touch_generation)
    barrier = fixture.writers.barrier(fixture.project, request)
    if variant in {"NB-W01:v01", "NB-W01:v02", "NB-W01:v03"}:
        fixture.advance(LIMITS.local_barrier_ms / 1000 + {"NB-W01:v01": -0.001, "NB-W01:v02": 0, "NB-W01:v03": 0.001}[variant])
    elif variant == "NB-W01:v04":
        fixture.writers.revoke(fixture.project, WriterBarrierCommandV1(schemaVersion=1, proof=fixture.proof,
            generation=barrier.generation, token=barrier.token))
    else:
        with fixture.publication.jobs.guard(fixture.project) as directory:
            state = fixture.publication.jobs._read(fixture.project, directory)
            if variant == "NB-W01:v05":
                state.writer.epoch += 1; state.writer_epoch = state.writer.epoch
            elif variant == "NB-W01:v06":
                state.writer.barrier_generation += 1
            else:
                state.writer.acknowledged_cursor += 1
            fixture.publication.jobs._write(directory, state, fixture.publication.jobs._all())
    before = fixture.publication.current()
    result = fixture.publication.publish(job, proposal)
    assert result.publication == ("saved" if variant == "NB-W01:v01" else "waiting_for_sync")
    if variant == "NB-W01:v01":
        assert result.receipt.durable and len(fixture.publication.current().mutation_replay) == 1
    else:
        assert result.receipt is None and fixture.publication.current() == before


def test_zero_diff_touch_is_durable_scoped_and_idempotent(tmp_path):
    fixture = WriterFixture(tmp_path)
    job, proposal, _batch = fixture.publication.accepted()
    before = fixture.publication.current()
    touched = mutation(before, [put(before, "narrative", text="Typed then undone")], "local-touch")
    touched.capture.session_id = fixture.proof.session_id
    request = fixture.flush_request(1, [{"cursor": 1, "mutation": touched}])
    first = fixture.writers.flush(fixture.project, request)
    first_generation = first.writer.touch_generation
    again = fixture.writers.flush(fixture.project, request)
    assert again.writer.touch_generation == first_generation and again.writer.acknowledged_cursor == 1
    assert fixture.publication.current() == before
    fixture.writers.detach(fixture.project, request)
    assert fixture.publication.publish(job, proposal).publication == "needs_review"
    assert fixture.publication.current() == before


@pytest.mark.parametrize("variant", [f"NB-W06:v{index:02d}" for index in range(1, 8)])
def test_zero_diff_watermarks_retain_each_scoped_edit_and_never_regress(tmp_path, variant):
    from packages.resume_core.models.agent import AgentQuery
    from tests.recovery.test_background_conflicts import record_step
    from tests.recovery.test_background_inverse import block
    fixture = WriterFixture(tmp_path)
    before = fixture.publication.current()
    queries = [AgentQuery(kind="document", ids=["narrative"])]
    steps = [put(before, "narrative", text="Typed then undone")]
    if variant == "NB-W06:v02":
        queries = [AgentQuery(kind="facts", ids=["candidate-1"])]
        steps = [record_step(before, "candidate-1")]
    elif variant == "NB-W06:v03":
        queries = [AgentQuery(kind="context")]
        steps = [{"kind": "move_block", "blockId": "quote", "parentId": "header", "afterId": None,
            "beforeRevision": block(before, "quote").revision}]
    elif variant == "NB-W06:v07":
        queries = [AgentQuery(kind="find", text="NEW_MATCH")]
        steps = [put(before, "quote", text="NEW_MATCH")]
    job, proposal, _batch = fixture.publication.accepted(queries=queries)
    edit = mutation(before, steps, "local-typed")
    edit.capture.session_id = fixture.proof.session_id
    first = fixture.flush_request(1, [{"cursor": 1, "mutation": edit}])
    ack = fixture.writers.flush(fixture.project, first)
    generation = ack.writer.touch_generation
    assert generation > fixture.view.writer.touch_generation and ack.writer.acknowledged_cursor == 1
    if variant == "NB-W06:v04":
        assert fixture.writers.flush(fixture.project, first).writer.touch_generation == generation
    elif variant in {"NB-W06:v05", "NB-W06:v06"}:
        undone = edit.model_copy(update={"kind": "undo", "client_mutation_id": "local-undone"}, deep=True)
        second = fixture.flush_request(2, [*first.touches, {"cursor": 2, "mutation": undone}])
        second = WriterAdvanceV1.model_validate(second.model_dump(by_alias=True))
        newest = fixture.writers.flush(fixture.project, second)
        assert newest.writer.touch_generation > generation and newest.writer.acknowledged_cursor == 2
        if variant == "NB-W06:v06":
            with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
                fixture.writers.flush(fixture.project, first)
        else:
            assert fixture.writers.flush(fixture.project, second).writer.touch_generation == newest.writer.touch_generation
        assert fixture.publication.jobs.load(fixture.project).writer.acknowledged_cursor == 2
    assert fixture.publication.current() == before
    cursor = fixture.publication.jobs.load(fixture.project).writer.acknowledged_cursor
    fixture.writers.detach(fixture.project, fixture.flush_request(cursor))
    assert fixture.publication.publish(job, proposal).publication == "needs_review"
    assert fixture.publication.current() == before


def test_clean_detach_can_publish_headlessly_without_a_browser_receipt(tmp_path):
    fixture = WriterFixture(tmp_path)
    job, proposal, _batch = fixture.publication.accepted()
    view = fixture.writers.detach(fixture.project, fixture.flush_request())
    assert view.writer.status == "clean_detached"
    assert fixture.publication.publish(job, proposal).receipt.durable
    reopened = fixture.writers.open(fixture.project, fixture.open_request.model_copy(update={"incarnation": "next-open"}))
    assert reopened.workspace == fixture.publication.current()
    assert reopened.writer.epoch > fixture.proof.epoch
