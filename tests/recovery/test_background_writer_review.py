"""Review regressions for pin integrity, later reads and durable retention clocks."""

import json
import asyncio

import pytest

from packages.resume_core.background_assets import JobAssets
from packages.resume_core.background_events import JobEvents
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_retention import JobRetention
from packages.resume_core.background_store import BackgroundFailure, JobStore, expiration
from packages.resume_core.models.agent import AgentQuery
from packages.resume_core.project_store import encoded
from packages.resume_core.storage import atomic_write
from tests.recovery.test_background_assets import Time, image_fixture, reclaim
from tests.recovery.test_background_inverse import mutation, put
from tests.recovery.test_background_store import capture
from tests.recovery.test_rich_images_service import capture as image_capture, png, refs
from tests.support.background_publication import PublicationFixture


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["job-pin", "job-reference", "inverse-pin"])
async def test_missing_or_changed_asset_ownership_is_fenced_before_gc(tmp_path, fault):
    fixture, service, clock, _aid, path = await image_fixture(tmp_path)
    if fault == "inverse-pin":
        job, proposal, _batch = fixture.accepted()
        fixture.publish(job, proposal)
        kind = "inverse"
    else:
        fixture.jobs.submit(capture(fixture.jobs.load(fixture.project), "pinned-job"))
        kind = "job"
    state_path = fixture.jobs.projects / fixture.project / "state.json"
    value = json.loads(state_path.read_bytes())
    pin = next(item for item in value["assetPins"] if item["kind"] == kind)
    if fault == "job-reference":
        pin["references"].clear()
    else:
        value["assetPins"].remove(pin)
    raw = encoded(value)
    atomic_write(state_path, raw)
    fresh = JobStore(fixture.root, clock=clock)
    with pytest.raises(BackgroundFailure, match="JOB_STORE_CORRUPT"):
        fresh.load(fixture.project)
    with pytest.raises(BackgroundFailure, match="JOB_STORE_CORRUPT"):
        JobAssets(fresh).collectable(fixture.project, set())
    assert state_path.read_bytes() == raw and path.exists()


@pytest.mark.asyncio
async def test_new_asset_seen_after_dispatch_extends_pins_without_releasing_prior_reads(tmp_path):
    fixture, service, clock, old, old_path = await image_fixture(tmp_path)
    job, _created = fixture.jobs.submit(capture(fixture.jobs.load(fixture.project), "later-reader"))
    events = JobEvents(fixture.jobs)
    events.append(job)
    refs(service, fixture.project, 3)
    new = await service.ingest_image(fixture.project, png("blue"), image_capture(3, "later-upload"))
    service.image_sessions[(fixture.project, "session")].pending.clear()
    refs(service, fixture.project, 4)
    def read(workspace):
        captured = fixture.capture(workspace, AgentQuery(kind="context"))
        return captured, captured.dependencies
    fixture.history.observe(fixture.project, read, job_id=job.id)
    current = fixture.jobs.read(fixture.project, job.id)
    assert current.event_cursor > job.event_cursor and current.asset_pins_sha256 != job.asset_pins_sha256
    events.append(current)
    assert {old, new} <= JobAssets(fixture.jobs).bytes_for(fixture.project, "job", job.id)[0].keys()
    clock.advance(LIMITS.orphan_asset_seconds)
    reclaim(fixture, service)
    assert old_path.exists() and len(fixture.current().project.assets) == 2
    assert events.replay(fixture.project, job.id, after=0, generation=1)[-1].snapshot == current


def test_receipt_inverse_and_resolved_retention_start_at_durable_completion(tmp_path):
    fixture = PublicationFixture(tmp_path)
    clock = Time(fixture.jobs.clock()); fixture.jobs.clock = clock
    prepared_at = clock()
    job, proposal, _batch = fixture.accepted()
    def delayed(name, _project):
        if name == "before_receipt_stored":
            clock.advance(LIMITS.resolved_seconds + 10)
    fixture.coordinator.observer = delayed
    saved = fixture.publish(job, proposal)
    state = fixture.jobs.load(fixture.project)
    assert saved.receipt.persisted_at == clock() != prepared_at
    assert state.inverses[0].expires_at == expiration(clock(), LIMITS.inverse_seconds)
    assert state.intents[0].resolved_at == clock()
    swept = JobRetention(fixture.jobs).sweep(fixture.project)
    assert swept.jobs[0].id == job.id and swept.inverses and not swept.jobs[0].undo_expired


def test_pruned_manual_candidate_keeps_exact_canonical_id_hash_replay(tmp_path):
    fixture = PublicationFixture(tmp_path)
    clock = Time(fixture.jobs.clock()); fixture.jobs.clock = clock
    before = fixture.current()
    request = mutation(before, [put(before, "narrative", text="Original manual save")], "manual-original")
    saved, replayed = fixture.coordinator.manual(fixture.project, request)
    assert not replayed
    clock.advance(LIMITS.resolved_seconds)
    assert not JobRetention(fixture.jobs).sweep(fixture.project).manual_intents
    assert not list((fixture.jobs.projects / fixture.project / "canonical-candidates").glob("*.json"))
    repeated, replayed = fixture.coordinator.manual(fixture.project, request)
    assert replayed and repeated == saved and len(repeated.mutation_replay) == 1
    assert fixture.jobs.load(fixture.project).history.workspace_sha256 == digest_bytes(saved)
    changed = request.model_copy(deep=True)
    changed.steps[0].block.content[0].text = "Reused ID with another payload"
    with pytest.raises(BackgroundFailure, match="JOB_IDEMPOTENCY_CONFLICT"):
        fixture.coordinator.manual(fixture.project, changed)


def test_repeated_manual_saves_compact_completed_snapshots_before_new_admission(tmp_path):
    fixture = PublicationFixture(tmp_path)
    for index in range(200):
        fixture.edit("narrative", "Repeated acknowledged input " + str(index), "typing-" + str(index))
    state = fixture.jobs.load(fixture.project)
    folder = fixture.jobs.projects / fixture.project / "canonical-candidates"
    assert len(state.manual_intents) == len(list(folder.glob("*.json"))) == 1
    assert len(fixture.current().mutation_replay) == 200
    assert fixture.jobs._extra_bytes(fixture.project) < LIMITS.sidecar_project_bytes


def test_loss_of_history_and_activation_file_cannot_reset_the_retained_namespace(tmp_path):
    fixture = PublicationFixture(tmp_path)
    with fixture.jobs.guard(fixture.project) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        namespace = state.history_namespace
        state.history, state.generations = None, []
        (directory / "history-activation.json").unlink()
        fixture.jobs._write(directory, state, fixture.jobs._all())
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fixture.history.open(fixture.project)
    assert fixture.jobs.load(fixture.project).history_namespace == namespace
    assert fixture.jobs.load(fixture.project).history is None


@pytest.mark.asyncio
async def test_explicit_delete_clears_owned_private_payloads_after_verified_cleanup(tmp_path):
    from tests.recovery.test_background_fixed_storage import accepted_fixed
    fixture = PublicationFixture(tmp_path)
    service, job, proposal, _record = accepted_fixed(fixture)
    assert fixture.publish(job, proposal).receipt.durable
    async def stop(project):
        fixture.jobs.mark_deleted(project)
    service.background_jobs.stop_project = stop
    assert (await service.delete_project(fixture.project)).status == "deleted"
    with fixture.jobs.guard(fixture.project, deleted=True) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        assert state.tombstoned and not state.jobs and not state.proposals and not state.intents and state.history is None
        assert {path.name for path in directory.iterdir()} <= {"state.json", ".canonical.lock"}


def test_another_project_can_write_during_fixed_project_tombstone_cleanup(tmp_path):
    from tests.recovery.test_background_fixed_storage import accepted_fixed
    fixture = PublicationFixture(tmp_path)
    _service, _job, _proposal, _record = accepted_fixed(fixture)
    other = fixture.initial.model_copy(deep=True)
    other.project_id = other.project.project_id = "still-writable"
    fixture.canonical.save(other, {}, {})
    fixture.jobs.open(other.project_id)
    fixture.canonical.tombstone(fixture.project)
    request = mutation(other, [put(other, "narrative", text="Another project remains writable")], "independent-delete")
    result, replay = fixture.coordinator.manual(other.project_id, request)
    assert not replay and result.project_revision == other.project_revision + 1


def test_rich_manual_commands_keep_their_existing_domain_identifiers(tmp_path):
    fixture = PublicationFixture(tmp_path)
    before = fixture.current()
    request = mutation(before, [put(before, "narrative")], "manual:1")
    request.action_id = request.capture.action_id = "editor:action/one"
    request.capture.session_id = "session:one"
    saved, replay = fixture.coordinator.manual(fixture.project, request)
    assert not replay and saved.mutation_replay[-1].client_mutation_id == "manual:1"
    assert fixture.coordinator.manual(fixture.project, request) == (saved, True)


@pytest.mark.asyncio
async def test_late_legacy_result_cannot_reopen_an_explicitly_closed_record(tmp_path):
    from packages.resume_core.rich_sync import RichRewriteRequest
    from tests.recovery.test_background_writer_routes import HeldProvider, independent
    from tests.recovery.test_background_writers import projects_for
    from tests.recovery.test_rich_synchronization import selection
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    provider = HeldProvider()
    service.provider_factory = lambda: (provider, "synthetic")
    request = RichRewriteRequest(selection=selection(service.read(fixture.project)), instruction="Clarify")
    task = asyncio.create_task(service.rewrite_rich(fixture.project, request))
    assert await asyncio.to_thread(provider.entered.wait, 10)
    identifier = service.read(fixture.project).sync_records[-1].id
    service.disposition(fixture.project, identifier, "stale")
    committed = independent(fixture)
    provider.release.set()
    result = await asyncio.wait_for(task, 10)
    record = next(item for item in result.workspace.sync_records if item.id == identifier)
    assert record.status == "stale" and not record.ready and not record.proposed_steps
    assert fixture.current().project.document == committed.project.document and len(provider.calls) == 1


@pytest.mark.parametrize("age", [0, LIMITS.resolved_seconds + 1], ids=["immediate", "past-retention"])
def test_legacy_applied_requires_the_saved_witness_after_full_candidate_compaction(tmp_path, age):
    from packages.resume_core.models.rich_workspace import RichSyncRecord
    from resume_api.gui_projects import ProjectFailure
    from tests.recovery.test_background_writers import projects_for
    fixture = PublicationFixture(tmp_path)
    clock = Time(fixture.jobs.clock()); fixture.jobs.clock = clock
    service = projects_for(fixture, tmp_path)
    record = RichSyncRecord(id="legacy-review", status="conflict", actionId="legacy-action",
        blockIds=["narrative"], fieldKeys=[], factIds=[], dependencies=[], errorCode="SEMANTIC_WARNING",
        kind="rewrite", ready=True, proposedSteps=[put(fixture.current(), "narrative", text="Saved legacy result")])
    service.workspaces[fixture.project].sync_records.append(record)
    assert service.persist(fixture.project) == "durable"
    before = fixture.current()
    with pytest.raises(ProjectFailure, match="JOB_SCOPE_INVALID"):
        service.disposition(fixture.project, record.id, "applied")
    assert fixture.current() == before
    request = mutation(before, record.proposed_steps, "legacy-manual-save")
    request.action_id = request.capture.action_id = record.action_id
    assert service.mutate(fixture.project, request).durability == "durable"
    fixture.snapshot(lambda workspace: setattr(workspace, "title", "Independent metadata"), "after-legacy-save")
    state = fixture.jobs.load(fixture.project)
    witness = next(item for item in state.manual_intents if item.client_mutation_id == request.client_mutation_id)
    assert witness.candidate_pruned and witness.action_id == record.action_id and witness.steps_sha256
    path = fixture.jobs.projects / fixture.project / "canonical-candidates" / (witness.candidate_ref + ".json")
    assert not path.exists()
    clock.advance(age)
    assert witness in JobRetention(fixture.jobs).sweep(fixture.project).manual_intents
    response = service.disposition(fixture.project, record.id, "applied")
    saved_record = next(item for item in response.workspace.sync_records if item.id == record.id)
    assert saved_record.status == "conflict" and not saved_record.ready and not saved_record.proposed_steps
    assert saved_record.error_code is None and response.workspace.title == "Independent metadata"
    assert fixture.coordinator.manual(fixture.project, request)[1]


@pytest.mark.parametrize("collision", [False, True], ids=["independent", "same-id"])
def test_concurrent_metadata_additions_merge_or_reject_the_exact_record(tmp_path, collision):
    from packages.resume_core.models.rich_workspace import RichOperation
    from tests.recovery.test_background_writers import projects_for
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    operation = RichOperation(id="review-operation", kind="render", status="queued",
        errorCode=None, actionId=None, dependencies=[])
    service.workspaces[fixture.project].project.operations.append(operation)
    def concurrent(workspace):
        workspace.project.operations.append(RichOperation(id=operation.id if collision else "other-operation",
            kind="render", status="completed", errorCode=None, actionId=None, dependencies=[]))
    fixture.snapshot(concurrent, "other-metadata")
    operation.status = "failed"
    outcome = service.persist(fixture.project)
    current = fixture.current()
    assert outcome == ("failed" if collision else "durable")
    if collision:
        assert service.save_errors[fixture.project] == "DEPENDENCY_CHANGED"
        assert current.project.operations[-1].status == "completed"
    else:
        assert {item.id: item.status for item in current.project.operations} == {
            operation.id: "failed", "other-operation": "completed"}
