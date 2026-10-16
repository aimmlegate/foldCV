"""Undo and Redo are conditional canonical commands with no model lifetime."""

import pytest

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.background import WriterHistoryCommandV1, WriterMutationV1
from tests.recovery.test_background_history_transfer import saved_background, transfer_request
from tests.recovery.test_background_inverse import block, mutation, put


def adopted(root):
    fixture, job, proposal = saved_background(root)
    request = transfer_request(fixture, job, proposal)
    fixture.writers.begin_history_transfer(fixture.project, request)
    fixture.writers.acknowledge_history_transfer(fixture.project, request)
    return fixture, job, proposal


def command(fixture, job, proposal, direction="undo", key="undo-one"):
    owner = next(item for item in fixture.publication.jobs.load(fixture.project).inverses if item.job_id == job.id)
    cursor = fixture.publication.jobs.load(fixture.project).writer.acknowledged_cursor + 1
    return WriterHistoryCommandV1(**fixture.flush_request(cursor, [{"cursor": cursor, "mutation": None}]).model_dump(by_alias=True),
        jobId=job.id, proposalId=proposal.id, transferId=owner.transfer_id, commandId=key, direction=direction)


def edit(fixture, target, text, key):
    current = fixture.publication.current()
    mutation_request = mutation(current, [put(current, target, text=text)], key)
    mutation_request.capture.session_id = fixture.proof.session_id
    cursor = fixture.publication.jobs.load(fixture.project).writer.acknowledged_cursor + 1
    request = WriterMutationV1(**fixture.flush_request(cursor, [{"cursor": cursor, "mutation": mutation_request}]).model_dump(by_alias=True),
        mutation=mutation_request)
    return fixture.writers.save(fixture.project, request)


def test_undo_redo_and_duplicate_commands_have_one_owner_and_exact_canonical_proof(tmp_path):
    fixture, job, proposal = adopted(tmp_path)
    saved = fixture.publication.current()
    original = fixture.publication.initial
    undo_request = command(fixture, job, proposal)
    undone = fixture.writers.history_command(fixture.project, undo_request)
    assert not undone.replayed and block(undone.view.workspace, "narrative").content == block(original, "narrative").content
    assert undone.receipt.resulting_revision == undone.view.workspace.project_revision
    state = fixture.publication.jobs.load(fixture.project)
    assert len(state.inverses) == len(state.history_commands) == 1 and state.inverses[0].direction == "redo"
    assert state.inverses[0].owner == "session" and state.inverses[0].command_ref
    replay = fixture.writers.history_command(fixture.project, undo_request)
    assert replay.replayed and replay.receipt == undone.receipt and replay.view.workspace == undone.view.workspace
    redone = fixture.writers.history_command(fixture.project, command(fixture, job, proposal, "redo", "redo-one"))
    assert block(redone.view.workspace, "narrative").content == block(saved, "narrative").content
    assert len(redone.view.workspace.mutation_replay) == 3
    assert len(fixture.publication.jobs.load(fixture.project).inverses) == 1
    assert fixture.publication.jobs.read(fixture.project, job.id).receipt.project_revision == saved.project_revision


@pytest.mark.parametrize("variant", ["NB-H02:v01", "NB-H02:v02", "NB-H02:v03", "NB-H02:v04"])
def test_compensation_preserves_independent_edits_rejects_overlap_aba_and_closes_redo(tmp_path, variant):
    fixture, job, proposal = adopted(tmp_path)
    if variant == "NB-H02:v04":
        fixture.writers.history_command(fixture.project, command(fixture, job, proposal))
        edit(fixture, "quote", "New branch input", "new-branch")
        before = fixture.publication.current()
        request = command(fixture, job, proposal, "redo", "closed-redo")
        with pytest.raises(BackgroundFailure, match="JOB_NOT_FOUND"):
            fixture.writers.history_command(fixture.project, request)
        assert fixture.publication.current() == before
        return
    target = "quote" if variant == "NB-H02:v01" else "narrative"
    previous = block(fixture.publication.current(), target).content[0].text
    edit(fixture, target, "Later local input", "later-input")
    if variant == "NB-H02:v03":
        edit(fixture, target, previous, "undo-local-input")
    before = fixture.publication.current()
    request = command(fixture, job, proposal)
    if variant == "NB-H02:v01":
        result = fixture.writers.history_command(fixture.project, request)
        assert block(result.view.workspace, "quote").content[0].text == "Later local input"
        assert block(result.view.workspace, "narrative").content == block(fixture.publication.initial, "narrative").content
    else:
        with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
            fixture.writers.history_command(fixture.project, request)
        assert fixture.publication.current() == before


def test_history_command_reuse_with_another_direction_is_an_idempotency_conflict(tmp_path):
    fixture, job, proposal = adopted(tmp_path)
    request = command(fixture, job, proposal)
    fixture.writers.history_command(fixture.project, request)
    changed = request.model_copy(update={"direction": "redo"})
    before = fixture.publication.current()
    with pytest.raises(BackgroundFailure, match="JOB_IDEMPOTENCY_CONFLICT"):
        fixture.writers.history_command(fixture.project, changed)
    assert fixture.publication.current() == before


def test_unreceipted_compensation_keeps_ownership_and_assets_until_exact_recovery(tmp_path):
    from packages.resume_core.background_limits import LIMITS
    from packages.resume_core.background_retention import JobRetention
    from packages.resume_core.background_writers import WriterSessions
    fixture, job, proposal = adopted(tmp_path)
    request = command(fixture, job, proposal)
    transfer_id = request.transfer_id
    reached = []
    def fail(name, _project):
        if name == "before_receipt_stored":
            reached.append(name)
            raise OSError("Synthetic compensation receipt cut")
    fixture.publication.coordinator.observer = fail
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fixture.writers.history_command(fixture.project, request)
    assert reached == ["before_receipt_stored"]
    committed = fixture.publication.current()
    assert len(committed.mutation_replay) == 2
    fixture.advance(LIMITS.inverse_seconds + 1)
    JobRetention(fixture.publication.jobs).sweep(fixture.project)
    fixture.writers.recover_all()
    state = fixture.publication.jobs.load(fixture.project)
    assert state.inverses[0].transfer_id == transfer_id and state.writer.status == "recovering"
    assert state.inverses[0].owner == "session" and len(state.inverses) == 1
    fresh = fixture.publication.fresh()
    fresh.jobs.clock = fixture.wall
    writers = WriterSessions(fresh.coordinator)
    repaired = fresh.coordinator.recover(fixture.project)
    assert repaired.manual_intents[-1].phase == "receipt_stored"
    assert repaired.inverses[0].direction == "redo" and len(repaired.history_commands) == 1
    assert writers.history_command(fixture.project, request).replayed
    assert fresh.current() == committed


def test_a_new_background_save_closes_the_previous_redo_branch(tmp_path):
    fixture, job, proposal = adopted(tmp_path)
    fixture.writers.history_command(fixture.project, command(fixture, job, proposal))
    fixture.writers.detach(fixture.project, fixture.flush_request(1))
    next_job, next_proposal, _batch = fixture.publication.accepted(key="next-background-action")
    assert fixture.publication.publish(next_job, next_proposal).receipt.durable
    rows = fixture.publication.jobs.load(fixture.project).inverses
    assert next(item for item in rows if item.job_id == job.id).direction == "closed"
    assert next(item for item in rows if item.job_id == next_job.id).direction == "undo"
