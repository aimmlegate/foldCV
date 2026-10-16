"""Writer saves bind authority at the real claim and recover exact durable replies."""

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_writers import WriterSessions
from packages.resume_core.models.background import WriterBarrierAckV1, WriterMutationV1
from tests.recovery.test_background_inverse import block, mutation, put
from tests.recovery.test_background_writer_drafts import checkpoint
from tests.recovery.test_background_writer_sessions import WriterFixture


def save_request(fixture):
    current = fixture.publication.current()
    command = mutation(current, [put(current, "narrative", text="Acknowledged local input")], "writer-save")
    command.capture.session_id = fixture.proof.session_id
    return WriterMutationV1(**fixture.flush_request(1, [{"cursor": 1, "mutation": command}]).model_dump(by_alias=True),
        mutation=command)


def test_writer_save_and_exact_replay_have_one_commit_and_one_touch_ack(tmp_path):
    fixture = WriterFixture(tmp_path)
    request = save_request(fixture)
    saved = fixture.writers.save(fixture.project, request)
    assert saved.canonical_ready and saved.response.durability == "durable" and not saved.replayed
    assert saved.writer.acknowledged_cursor == 1 and saved.writer.acknowledged_revision == saved.workspace.project_revision
    assert saved.writer.acknowledged_sha256 == saved.workspace_sha256 == digest_bytes(saved.workspace)
    again = fixture.writers.save(fixture.project, request)
    assert again.replayed and again.workspace == saved.workspace and again.writer == saved.writer
    assert len(saved.workspace.mutation_replay) == 1 and len(fixture.publication.jobs.load(fixture.project).writer_touches) == 1


def test_writer_save_preserves_independent_metadata_since_its_acknowledged_base(tmp_path):
    fixture = WriterFixture(tmp_path)
    request = save_request(fixture)
    fixture.publication.snapshot(lambda workspace: setattr(workspace, "title", "Independent render metadata"), "metadata-before-input")
    saved = fixture.writers.save(fixture.project, request)
    assert saved.workspace.title == "Independent render metadata"
    assert block(saved.workspace, "narrative").content[0].text == "Acknowledged local input"
    assert saved.writer.acknowledged_revision == saved.workspace.project_revision == 3


def test_expired_writer_before_claim_cannot_save_or_reuse_its_failed_identity(tmp_path):
    fixture = WriterFixture(tmp_path)
    request = save_request(fixture)
    before = fixture.publication.current()
    def expire(name, _project):
        if name == "before_commit_claim":
            fixture.advance(LIMITS.writer_lease_seconds)
    fixture.publication.coordinator.observer = expire
    for _ in range(2):
        with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
            fixture.writers.save(fixture.project, request)
    assert fixture.publication.current() == before and not before.mutation_replay
    intent = fixture.publication.jobs.load(fixture.project).manual_intents[-1]
    assert intent.phase == "reconciled" and intent.reconciled_reason.code == "WRITER_UNKNOWN"


def test_all_typed_manual_commands_are_refused_inside_the_acked_barrier(tmp_path):
    fixture = WriterFixture(tmp_path)
    request = save_request(fixture)
    fixture.writers.barrier(fixture.project, WriterBarrierAckV1(**fixture.flush_request().model_dump(by_alias=True),
        generation=fixture.view.writer.barrier_generation + 1, token="synthetic_barrier_token_012345678901234",
        touchGeneration=fixture.view.writer.touch_generation))
    before = fixture.publication.current()
    with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
        fixture.writers.save(fixture.project, request)
    assert fixture.publication.current() == before
    assert not fixture.publication.jobs.load(fixture.project).writer_touches


def test_draft_recovery_cannot_autosave_against_the_old_baseline(tmp_path):
    fixture = WriterFixture(tmp_path)
    request = save_request(fixture)
    draft = fixture.writers.checkpoint(fixture.project, checkpoint(fixture))
    before = fixture.publication.current()
    with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
        fixture.writers.save(fixture.project, request)
    assert fixture.publication.current() == before and fixture.publication.jobs.load(fixture.project).drafts == [draft]


def test_restart_recovers_the_saved_writer_watermark_without_reapplying_input(tmp_path):
    fixture = WriterFixture(tmp_path)
    request = save_request(fixture)
    reached = False
    def fail(name, _project):
        nonlocal reached
        if name == "before_receipt_stored":
            reached = True
            raise OSError("Synthetic lost writer receipt")
    fixture.publication.coordinator.observer = fail
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fixture.writers.save(fixture.project, request)
    assert reached and len(fixture.publication.current().mutation_replay) == 1
    fresh = fixture.publication.fresh()
    fresh.jobs.clock = fixture.wall
    fresh.coordinator.authority.clock = fixture.elapsed
    writers = WriterSessions(fresh.coordinator)
    writers.recover_all()
    state = fresh.coordinator.recover(fixture.project)
    assert state.writer.status == "recovering" and state.writer.acknowledged_cursor == 1
    assert state.writer.acknowledged_revision == fresh.current().project_revision == 2
    assert state.writer.acknowledged_sha256 == digest_bytes(fresh.current())
    assert len(fresh.current().mutation_replay) == 1
