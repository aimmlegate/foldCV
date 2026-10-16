"""Inverse bounds retain saved proof and expose expiry without another attempt."""

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_inverse import inverse_mutation
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_retention import JobRetention
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.project_store import encoded
from tests.recovery.test_background_history_transfer import saved_background, transfer_request
from tests.recovery.test_background_inverse import block, mutation, put
from tests.support.background_publication import PublicationFixture


@pytest.mark.parametrize("variant,offset", [(f"NB-A04:v{16 + index}", offset) for index, offset in enumerate((-1, 0, 1))],
    ids=[f"NB-A04:v{number}" for number in range(16, 19)])
def test_real_typed_inverse_enforces_its_exact_byte_boundary(tmp_path, variant, offset):
    fixture = PublicationFixture(tmp_path)
    before = fixture.current()
    after, _duplicate = fixture.coordinator.manual(fixture.project, mutation(before, [put(before, "narrative")]))
    sample = inverse_mutation(before, after, mutation_id="sized-inverse", session_id="session")
    initial = len(encoded(sample.model_dump(mode="json", by_alias=True)))
    span = block(before, "narrative").content[0]
    original = span.text
    span.text += "x" * (LIMITS.inverse_bytes + offset - initial)
    assert len(span.text) > len(original)
    if offset > 0:
        with pytest.raises(BackgroundFailure, match="JOB_STORAGE_FULL"):
            inverse_mutation(before, after, mutation_id="sized-inverse", session_id="session")
    else:
        result = inverse_mutation(before, after, mutation_id="sized-inverse", session_id="session")
        assert len(encoded(result.model_dump(mode="json", by_alias=True))) == LIMITS.inverse_bytes + offset
    assert digest_bytes(fixture.current()) == digest_bytes(after)


@pytest.mark.parametrize("variant,offset", [(f"NB-A04:v{25 + index}", offset) for index, offset in enumerate((-1, 0, 1))],
    ids=[f"NB-A04:v{number}" for number in range(25, 28)])
def test_inverse_expiry_keeps_the_original_receipt_and_never_extends_on_a_read(tmp_path, variant, offset):
    fixture, job, proposal = saved_background(tmp_path)
    before = fixture.publication.current()
    original = fixture.publication.jobs.read(fixture.project, job.id).receipt
    request = transfer_request(fixture, job, proposal)
    expiry = fixture.publication.jobs.load(fixture.project).inverses[0].expires_at
    fixture.advance(LIMITS.inverse_seconds + offset)
    state = JobRetention(fixture.publication.jobs).sweep(fixture.project)
    assert bool(state.inverses) == (offset < 0)
    assert state.jobs[0].undo_expired == (offset >= 0) and state.jobs[0].receipt == original
    resumed = fixture.resumed(canonical_revision=before.project_revision, canonical_sha256=digest_bytes(before))
    fixture.proof = fixture.proof.model_copy(update={"incarnation": resumed.writer.incarnation})
    request = request.model_copy(update={"proof": fixture.proof}, deep=True)
    if offset < 0:
        assert state.inverses[0].expires_at == expiry
        offer = fixture.writers.history_offer(fixture.project, request)
        assert offer.ownership.expires_at == expiry
    else:
        with pytest.raises(BackgroundFailure, match="JOB_NOT_FOUND"):
            fixture.writers.history_offer(fixture.project, request)
    assert fixture.publication.current() == before


@pytest.mark.parametrize("variant,offset", [(f"NB-A04:v{28 + index}", offset) for index, offset in enumerate((-1, 0, 1))],
    ids=[f"NB-A04:v{number}" for number in range(28, 31)])
def test_inverse_count_admission_keeps_all_existing_unexpired_owners(tmp_path, variant, offset):
    fixture = PublicationFixture(tmp_path)
    target = LIMITS.inverse_project_records + offset
    for index in range(target):
        key = "inverse-" + str(index)
        job, proposal, _batch = fixture.accepted(key, steps=[put(fixture.current(), "narrative", text=key)])
        before = fixture.current()
        if index == LIMITS.inverse_project_records:
            with pytest.raises(BackgroundFailure, match="JOB_STORAGE_FULL"):
                fixture.publish(job, proposal)
            assert fixture.jobs.read(fixture.project, job.id).receipt is None
            assert fixture.current() == before
        else:
            result = fixture.publish(job, proposal)
            assert result.receipt.durable
    state = fixture.jobs.load(fixture.project)
    assert len(state.inverses) == min(target, LIMITS.inverse_project_records)
    assert all(inverse.owner == "backend" for inverse in state.inverses)
    assert len(fixture.current().mutation_replay) == min(target, LIMITS.inverse_project_records)
