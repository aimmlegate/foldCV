"""Private checkpoints preserve local input without asserting canonical durability."""

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_writers import WriterSessions
from packages.resume_core.models.background import (DraftPayloadV1, WriterAbandonV1, WriterCheckpointV1,
    WriterDraftCommandV1, WriterDraftReferenceV1)
from packages.resume_core.project_store import encoded
from packages.resume_core.storage import atomic_write
from tests.recovery.test_background_inverse import block, mutation, put
from tests.recovery.test_background_writer_sessions import WriterFixture


def checkpoint(fixture, sequence=1, text="Recoverable input"):
    before = fixture.publication.current()
    document = before.project.document.model_copy(deep=True)
    next(item for item in document.blocks() if item.id == "narrative").content[0].text = text
    request = mutation(before, [put(before, "narrative", text=text)], "outbox-" + str(sequence))
    request.capture.session_id = fixture.proof.session_id
    touches = [{"cursor": index, "mutation": request} for index in range(1, sequence + 1)]
    payload = DraftPayloadV1(schemaVersion=1, document=document, facts=before.project.facts,
        outbox=[request], assetPins=[], touches=touches)
    return WriterCheckpointV1(schemaVersion=1, proof=fixture.proof, id="recovery-input", sequence=sequence,
        actionCursor=sequence, baseRevision=before.project_revision, baseSha256=digest_bytes(before), payload=payload)


@pytest.mark.parametrize("variant", ["NB-D04:v03", "NB-D04:v04"])
def test_local_checkpoint_on_a_fenced_project_does_not_claim_a_canonical_save(tmp_path, monkeypatch, variant):
    fixture = WriterFixture(tmp_path)
    request = checkpoint(fixture)
    before = fixture.publication.current()
    fixture.publication.jobs.fences[fixture.project] = "OUTCOME_UNKNOWN"
    if variant == "NB-D04:v04":
        def fail(_directory, _state):
            raise OSError("Synthetic checkpoint persistence failure")
        monkeypatch.setattr(fixture.writers, "write", fail)
        with pytest.raises(BackgroundFailure, match="JOB_STORE_UNAVAILABLE"):
            fixture.writers.checkpoint(fixture.project, request)
        assert not fixture.publication.jobs.load(fixture.project).drafts
    else:
        saved = fixture.writers.checkpoint(fixture.project, request)
        fresh = WriterSessions(fixture.publication.fresh().coordinator)
        read = fresh.read_draft(fixture.project, WriterDraftReferenceV1(schemaVersion=1, proof=fixture.proof, id=saved.id))
        assert read.payload == request.payload and read.checkpoint.action_cursor == 1
        assert fixture.publication.jobs.load(fixture.project).writer.status == "recovering"
    assert fixture.publication.current() == before
    assert next(item for item in request.payload.document.blocks() if item.id == "narrative").content[0].text == "Recoverable input"
    assert request.payload.document == checkpoint(fixture).payload.document


def test_late_checkpoint_cannot_replace_a_newer_durable_payload_or_watermark(tmp_path):
    fixture = WriterFixture(tmp_path)
    older = checkpoint(fixture, 1, "First input")
    newer = checkpoint(fixture, 2, "Newer input")
    entered, released = threading.Event(), threading.Event()
    calls = 0
    def observe(name, _project):
        nonlocal calls
        if name == "before_draft_checkpoint":
            calls += 1
            if calls == 1:
                entered.set()
                assert released.wait(10)
    fixture.writers.observer = observe
    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(fixture.writers.checkpoint, fixture.project, older)
        try:
            assert entered.wait(10)
            newest = fixture.writers.checkpoint(fixture.project, newer)
        finally:
            released.set()
        late = held.result(timeout=10)
    assert late == newest and late.sequence == 2 and late.action_cursor == 2
    fresh = fixture.publication.fresh()
    read = WriterSessions(fresh.coordinator).read_draft(fixture.project,
        WriterDraftReferenceV1(schemaVersion=1, proof=fixture.proof, id=newest.id))
    assert read.payload == newer.payload and read.checkpoint == newest
    assert fixture.publication.current().project.document != newer.payload.document


@pytest.mark.parametrize("choice", ["discard", "use", "recover"])
def test_resolved_draft_floor_survives_late_checkpoint_and_service_reconstruction(tmp_path, choice):
    from packages.resume_core.models.background import WriterDraftResolveV1
    fixture = WriterFixture(tmp_path)
    older, newer = checkpoint(fixture, 1, "Old input"), checkpoint(fixture, 2, "Chosen input")
    if choice == "recover":
        newer.payload.document = fixture.publication.current().project.document.model_copy(deep=True)
        newer.payload.outbox = []
    entered, released = threading.Event(), threading.Event()
    def observe(name, _project):
        if name == "before_draft_checkpoint" and not entered.is_set():
            entered.set()
            assert released.wait(10)
    fixture.writers.observer = observe
    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(fixture.writers.checkpoint, fixture.project, older)
        try:
            assert entered.wait(10)
            record = fixture.writers.checkpoint(fixture.project, newer)
            current = fixture.publication.current()
            fields = dict(schemaVersion=1, proof=fixture.proof, id=record.id, sequence=record.sequence,
                payloadSha256=record.payload_sha256, canonicalRevision=current.project_revision, canonicalSha256=digest_bytes(current))
            if choice == "use":
                result = fixture.writers.use_draft(fixture.project, WriterDraftResolveV1(**fields, mutation=newer.payload.outbox[0]))
            else:
                command = WriterDraftCommandV1(**fields)
                result = (fixture.writers.discard_draft if choice == "discard" else fixture.writers.restore_saved_draft)(fixture.project, command)
            assert not result.drafts and result.writer.draft_id is None
            assert result.writer.draft_sequence_floor == 2 and result.writer.acknowledged_cursor == 2
        finally:
            released.set()
        with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
            held.result(timeout=10)
    fresh = WriterSessions(fixture.publication.fresh().coordinator)
    for request in [older, newer]:
        with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
            fresh.checkpoint(fixture.project, request)
    state = fixture.publication.jobs.load(fixture.project)
    assert not state.drafts and state.writer.status == "attached" and state.writer.acknowledged_cursor == 2
    assert fixture.publication.current() == result.workspace
    assert fresh.checkpoint(fixture.project, checkpoint(fixture, 3, "New input")).sequence == 3


@pytest.mark.parametrize("fault", ["missing", "changed", "unsupported", "partial"])
def test_invalid_private_draft_never_becomes_a_recovered_buffer(tmp_path, fault):
    fixture = WriterFixture(tmp_path)
    saved = fixture.writers.checkpoint(fixture.project, checkpoint(fixture))
    path = fixture.publication.jobs.projects / fixture.project / "drafts" / (saved.payload_ref + ".json")
    if fault == "missing":
        path.unlink()
    elif fault == "changed":
        atomic_write(path, b'{"changed":true}')
    else:
        value = checkpoint(fixture).payload.model_dump(mode="json", by_alias=True)
        value["schemaVersion"] = 2 if fault == "unsupported" else 1
        if fault == "partial":
            del value["document"]
        raw = encoded(value)
        atomic_write(path, raw)
        with fixture.publication.jobs.guard(fixture.project) as directory:
            state = fixture.publication.jobs._read(fixture.project, directory)
            state.drafts[0].payload_sha256, state.drafts[0].payload_bytes = hashlib.sha256(raw).hexdigest(), len(raw)
            fixture.publication.jobs._write(directory, state, fixture.publication.jobs._all())
    before = fixture.publication.current()
    with pytest.raises(BackgroundFailure, match="JOB_STORE_CORRUPT"):
        fixture.writers.read_draft(fixture.project, WriterDraftReferenceV1(schemaVersion=1, proof=fixture.proof, id=saved.id))
    assert fixture.publication.current() == before and fixture.publication.jobs.load(fixture.project).drafts


@pytest.mark.parametrize("dispose", [False, True])
def test_explicit_abandonment_revokes_the_old_epoch_and_preserves_available_input(tmp_path, dispose):
    fixture = WriterFixture(tmp_path)
    request = checkpoint(fixture)
    saved = fixture.writers.checkpoint(fixture.project, request)
    before = fixture.publication.current()
    view = fixture.writers.abandon(fixture.project, WriterAbandonV1(schemaVersion=1, sessionId="new-session",
        incarnation="new-connection", credential="synthetic_new_writer_credential_0123456789",
        canonicalRevision=before.project_revision, canonicalSha256=digest_bytes(before),
        discardDrafts=[saved.id] if dispose else []))
    assert view.writer.epoch > fixture.proof.epoch and view.writer.abandoned_epoch == fixture.proof.epoch
    assert view.writer.status == "attached" and view.writer.draft_id is None
    assert bool(view.drafts) == (not dispose) and view.workspace == before
    with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
        fixture.writers.checkpoint(fixture.project, request)
    assert request.payload.document == checkpoint(fixture).payload.document


def test_explicit_draft_discard_keeps_touch_invalidation_without_changing_canonical_text(tmp_path):
    fixture = WriterFixture(tmp_path)
    job, proposal, _batch = fixture.publication.accepted()
    request = checkpoint(fixture)
    saved = fixture.writers.checkpoint(fixture.project, request)
    before = fixture.publication.current()
    view = fixture.writers.discard_draft(fixture.project, WriterDraftCommandV1(schemaVersion=1, proof=fixture.proof,
        id=saved.id, sequence=saved.sequence, payloadSha256=saved.payload_sha256,
        canonicalRevision=before.project_revision, canonicalSha256=digest_bytes(before)))
    assert view.writer.status == "attached" and view.writer.acknowledged_cursor == saved.action_cursor
    assert not view.drafts and view.workspace == before
    fixture.writers.detach(fixture.project, fixture.flush_request(saved.action_cursor))
    assert fixture.publication.publish(job, proposal).publication == "needs_review"


@pytest.mark.parametrize("cut", [None, "before_receipt_stored"])
def test_explicit_use_draft_commits_conditionally_and_resolves_only_with_the_durable_receipt(tmp_path, cut):
    from packages.resume_core.models.background import WriterDraftResolveV1
    fixture = WriterFixture(tmp_path)
    request = checkpoint(fixture)
    record = fixture.writers.checkpoint(fixture.project, request)
    before = fixture.publication.current()
    use = WriterDraftResolveV1(schemaVersion=1, proof=fixture.proof, id=record.id, sequence=record.sequence,
        payloadSha256=record.payload_sha256, canonicalRevision=before.project_revision, canonicalSha256=digest_bytes(before),
        mutation=request.payload.outbox[0])
    if cut:
        def fail(name, _project):
            if name == cut:
                raise OSError("Synthetic draft resolution cut")
        fixture.publication.coordinator.observer = fail
        with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
            fixture.writers.use_draft(fixture.project, use)
        assert fixture.publication.jobs.load(fixture.project).drafts
        fresh = fixture.publication.fresh()
        repaired = fresh.coordinator.recover(fixture.project)
        assert not repaired.drafts and repaired.writer.draft_id is None
        assert repaired.writer.status == "attached"
    else:
        result = fixture.writers.use_draft(fixture.project, use)
        assert not result.drafts and result.writer.status == "attached"
        assert fixture.writers.use_draft(fixture.project, use).replayed
    assert block(fixture.publication.current(), "narrative").content[0].text == "Recoverable input"
    assert len(fixture.publication.current().mutation_replay) == 1


def test_use_draft_rejects_stale_canonical_and_a_different_selected_payload(tmp_path):
    from packages.resume_core.models.background import WriterDraftResolveV1
    fixture = WriterFixture(tmp_path)
    request = checkpoint(fixture)
    record = fixture.writers.checkpoint(fixture.project, request)
    before = fixture.publication.current()
    fields = dict(schemaVersion=1, proof=fixture.proof, id=record.id, sequence=record.sequence,
        payloadSha256=record.payload_sha256, canonicalRevision=before.project_revision, canonicalSha256=digest_bytes(before),
        mutation=request.payload.outbox[0])
    with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
        fixture.writers.use_draft(fixture.project, WriterDraftResolveV1(**{**fields, "canonicalSha256": "f" * 64}))
    changed = request.payload.outbox[0].model_copy(deep=True)
    changed.steps[0].block.content[0].text = "Unselected input"
    with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
        fixture.writers.use_draft(fixture.project, WriterDraftResolveV1(**{**fields, "mutation": changed}))
    assert fixture.publication.current() == before and fixture.publication.jobs.load(fixture.project).drafts


@pytest.mark.parametrize("choice", ["draft", "saved"])
def test_explicit_resolution_cannot_reactivate_a_late_pending_history_command(tmp_path, choice):
    from packages.resume_core.models.background import HistoryPendingV1, WriterDraftResolveV1
    from tests.recovery.test_background_history_commands import adopted, command
    fixture, job, proposal = adopted(tmp_path)
    pending = command(fixture, job, proposal)
    request = checkpoint(fixture)
    request.payload.history_outbox = [HistoryPendingV1(jobId=job.id, proposalId=proposal.id, transferId=pending.transfer_id,
        commandId=pending.command_id, direction=pending.direction, actionCursor=pending.action_cursor)]
    request = WriterCheckpointV1.model_validate(request.model_dump(by_alias=True))
    record = fixture.writers.checkpoint(fixture.project, request)
    before = fixture.publication.current()
    fields = dict(schemaVersion=1, proof=fixture.proof, id=record.id, sequence=record.sequence,
        payloadSha256=record.payload_sha256, canonicalRevision=before.project_revision, canonicalSha256=digest_bytes(before))
    if choice == "draft":
        view = fixture.writers.use_draft(fixture.project, WriterDraftResolveV1(**fields, mutation=request.payload.outbox[0]))
        assert block(view.workspace, "narrative").content[0].text == "Recoverable input"
    else:
        view = fixture.writers.discard_draft(fixture.project, WriterDraftCommandV1(**fields))
        assert view.workspace == before and view.writer.status == "recovering"
    committed = fixture.publication.current()
    with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED|WRITER_UNKNOWN"):
        fixture.writers.history_command(fixture.project, pending)
    assert fixture.publication.current() == committed
    assert not fixture.publication.jobs.load(fixture.project).drafts


@pytest.mark.asyncio
async def test_abandonment_moves_exact_image_pins_before_releasing_the_old_connection(tmp_path):
    from packages.resume_core.agent_store import digest
    from packages.resume_core.background_assets import JobAssets
    from packages.resume_core.background_limits import LIMITS
    from packages.resume_core.models.background import WriterOpenV1
    from tests.recovery.test_background_assets import image_fixture, reclaim
    fixture, service, clock, asset_id, path = await image_fixture(tmp_path)
    writers = WriterSessions(fixture.coordinator)
    current = fixture.current()
    view = writers.open(fixture.project, WriterOpenV1(schemaVersion=1, sessionId="before-abandon", incarnation="old-image-connection",
        credential="synthetic_image_writer_credential_0123456789", canonicalRevision=current.project_revision,
        canonicalSha256=digest_bytes(current), actionCursor=0))
    assets = JobAssets(fixture.jobs)
    previous = "session_" + digest(view.writer.incarnation)[:40]
    following = "session_" + digest("new-image-connection")[:40]
    assets.session(fixture.project, previous, {asset_id})
    expected = path.read_bytes()
    result = writers.abandon(fixture.project, WriterAbandonV1(schemaVersion=1, sessionId="after-abandon", incarnation="new-image-connection",
        credential="synthetic_replacement_credential_0123456789", canonicalRevision=current.project_revision,
        canonicalSha256=digest_bytes(current), discardDrafts=[]))
    assert result.writer.epoch > view.writer.epoch
    state = fixture.jobs.load(fixture.project)
    assert not any(pin.kind == "session" and pin.owner == previous for pin in state.asset_pins)
    assert assets.bytes_for(fixture.project, "session", following)[0][asset_id] == expected
    clock.advance(LIMITS.orphan_asset_seconds + 1); reclaim(fixture, service)
    assert path.read_bytes() == expected
    assets.release(fixture.project, "session", following)
    reclaim(fixture, service); clock.advance(LIMITS.orphan_asset_seconds + 1); reclaim(fixture, service)
    assert not path.exists()
