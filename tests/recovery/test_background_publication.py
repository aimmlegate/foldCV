"""Actual canonical publication, exact receipts and restart reconciliation."""

import hashlib

import pytest

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.project_store import strict_json
from packages.resume_core.rich_mutations import mutation_sha256
from tests.recovery.test_background_inverse import block
from tests.support.background_publication import PublicationFixture


def test_conditional_save_keeps_original_payload_and_proves_the_actual_mutation(tmp_path):
    fixture = PublicationFixture(tmp_path)
    job, proposal, batch = fixture.accepted()
    original = fixture.artifacts.payload_for(fixture.project, proposal.payload)
    saved = fixture.publish(job, proposal)
    assert saved.publication == "saved" and saved.receipt.durable
    assert saved.receipt.request_sha256 != saved.receipt.proposal_sha256
    assert saved.receipt.proposal_sha256 == hashlib.sha256(original).hexdigest()
    assert fixture.artifacts.payload_for(fixture.project, proposal.payload) == original
    assert mutation_sha256(batch.mutation) != saved.receipt.request_sha256
    assert fixture.current().mutation_replay[0].request_sha256 == saved.receipt.request_sha256
    assert block(fixture.current(), "narrative").content[0].text == "Changed"
    state = fixture.jobs.load(fixture.project)
    assert state.intents[0].phase == "receipt_stored" and state.inverses[0].owner == "backend"
    assert fixture.fresh().publish(job, proposal).receipt == saved.receipt


@pytest.mark.parametrize("targeted", [False, True])
def test_independent_manual_input_survives_and_targeted_input_requires_review(tmp_path, targeted):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    fixture.edit("narrative" if targeted else "quote", "User input")
    result = fixture.publish(job, proposal)
    assert result.publication == ("needs_review" if targeted else "saved")
    assert block(fixture.current(), "narrative" if targeted else "quote").content[0].text == "User input"


@pytest.mark.parametrize("phase", ["intent_stored", "commit_claimed", "workspace_replaced", "workspace_durable",
    "generation_history_durable", "receipt_stored"])
def test_exact_candidate_recovers_without_reapplication_at_each_real_cut(tmp_path, phase):
    reached = []
    def fail(name, project):
        if name == phase:
            reached.append(project)
            raise OSError("Synthetic interruption at " + name)
    fixture = PublicationFixture(tmp_path, observer=fail)
    job, proposal, _batch = fixture.accepted()
    try:
        fixture.publish(job, proposal)
    except (OSError, BackgroundFailure):
        pass
    assert reached == [fixture.project]
    restarted = fixture.fresh()
    state = restarted.coordinator.recover(fixture.project)
    known = restarted.jobs.read(fixture.project, job.id)
    expected_saved = phase not in {"intent_stored", "commit_claimed"}
    assert known.publication == ("saved" if expected_saved else "save_failed")
    assert len(restarted.current().mutation_replay) == int(expected_saved)
    assert restarted.coordinator.recover(fixture.project) == state
    if expected_saved:
        assert restarted.publish(job, proposal).receipt == known.receipt


def test_changed_payload_hash_cannot_change_a_known_receipt(tmp_path):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    saved = fixture.publish(job, proposal)
    fixture.edit("quote", "Later input")
    with pytest.raises(BackgroundFailure, match="JOB_IDEMPOTENCY_CONFLICT"):
        fixture.coordinator.publish(fixture.project, job.id, "b" * 64)
    assert fixture.fresh().publish(job, proposal).receipt == saved.receipt
    assert len(fixture.current().mutation_replay) == 2
