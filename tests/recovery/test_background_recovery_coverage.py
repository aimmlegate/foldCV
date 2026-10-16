"""Corrupt proof stays scoped; persisted writer records never revive a runtime."""

import json

import pytest

from packages.resume_core.background_store import BackgroundFailure, JobStore, expiration
from packages.resume_core.models.background import ScopeGuardV1
from packages.resume_core.project_store import encoded
from packages.resume_core.rich_project_store import rich_snapshot_bytes
from packages.resume_core.storage import atomic_write
from tests.recovery.test_background_exports import HeldRenderer
from tests.recovery.test_background_inverse import block, mutation, put
from tests.recovery.test_background_publication_crashes import attach
from tests.recovery.test_background_writers import projects_for
from tests.support.background_publication import PublicationFixture


@pytest.mark.parametrize("variant", [f"NB-D02:v{index:02d}" for index in range(1, 7)])
def test_independently_broken_payload_or_proof_cannot_gain_publication_authority(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    directory = fixture.jobs.projects / fixture.project
    artifact = fixture.artifacts._path(directory, job.submission.input.id)
    state_path = directory / "state.json"
    before = fixture.current()
    if variant == "NB-D02:v01":
        with fixture.jobs.guard(fixture.project) as owned:
            state = fixture.jobs._read(fixture.project, owned)
            state.proposals.clear()
            state.jobs[0].proposal_id, state.jobs[0].publication = None, "none"
            fixture.jobs._write(owned, state, fixture.jobs._all())
    elif variant == "NB-D02:v02":
        artifact.unlink()
    elif variant == "NB-D02:v03":
        value = json.loads(artifact.read_bytes())
        value["batches"][0]["batch"]["previewSha256"] = "a" * 64
        atomic_write(artifact, encoded(value))
    elif variant == "NB-D02:v04":
        atomic_write(state_path, b'{"schemaVersion":1,')
    elif variant == "NB-D02:v05":
        def fail(name, _project):
            if name == "workspace_durable":
                raise OSError("Synthetic crash before receipt proof")
        fixture.coordinator.observer = fail
        with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
            fixture.publish(job, proposal)
        after = fixture.current()
        after.mutation_replay.clear()
        atomic_write(fixture.canonical.projects / fixture.project / "workspace.json", rich_snapshot_bytes(after))
    else:
        value = json.loads(state_path.read_bytes()); value["schemaVersion"] = 2
        atomic_write(state_path, encoded(value))
    raw = artifact.read_bytes() if artifact.exists() else None
    restarted = fixture.fresh()
    if variant == "NB-D02:v01":
        restarted.jobs.recover(fixture.project)
        restarted.coordinator.recover(fixture.project)
        with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
            restarted.publish(job, proposal)
        assert not restarted.jobs.load(fixture.project).proposals
    else:
        with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN|JOB_STORE_CORRUPT"):
            if variant == "NB-D02:v05":
                restarted.coordinator.recover(fixture.project)
            else:
                restarted.publish(job, proposal)
        assert fixture.project in restarted.jobs.fences
    assert (artifact.read_bytes() if artifact.exists() else None) == raw
    if variant != "NB-D02:v05":
        assert restarted.current() == before
    if variant not in {"NB-D02:v04", "NB-D02:v06"}:
        assert restarted.jobs.read(fixture.project, job.id).receipt is None


@pytest.mark.parametrize("variant", [f"NB-D05:v{index:02d}" for index in range(1, 6)])
def test_restart_uses_only_clean_detach_or_existing_exact_receipt(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    known = None
    if variant == "NB-D05:v01":
        with fixture.jobs.guard(fixture.project) as directory:
            state = fixture.jobs._read(fixture.project, directory)
            state.writer = None
            fixture.jobs._write(directory, state, fixture.jobs._all())
    elif variant in {"NB-D05:v03", "NB-D05:v04"}:
        attach(fixture)
        if variant == "NB-D05:v04":
            with fixture.jobs.guard(fixture.project) as directory:
                state = fixture.jobs._read(fixture.project, directory)
                state.writer.lease_expires_at = expiration(fixture.jobs.clock(), -1)
                fixture.jobs._write(directory, state, fixture.jobs._all())
    elif variant == "NB-D05:v05":
        known = fixture.publish(job, proposal).receipt
        fixture.edit("quote", "Newer input after a known receipt")
    before = fixture.current()
    restarted = fixture.fresh()
    restarted.jobs.recover(fixture.project)
    restarted.coordinator.recover(fixture.project)
    if variant == "NB-D05:v04":
        state = restarted.jobs.load(fixture.project)
        restarted.coordinator.authority.acknowledged(state.writer, state.barrier)
    result = restarted.publish(job, proposal)
    if variant in {"NB-D05:v02", "NB-D05:v05"}:
        assert result.receipt.durable
        if known is not None:
            assert result.receipt == known and restarted.current() == before
    else:
        assert result.publication == "waiting_for_sync" and result.receipt is None and restarted.current() == before
    assert result.attempts == job.attempts == []


def test_pre_history_interim_proposal_is_reviewed_without_fresh_generation_authority(tmp_path):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    with fixture.jobs.guard(fixture.project) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        state.history, state.generations = None, []
        state.history_namespace = None
        state.proposals[0].guards = ScopeGuardV1(schemaVersion=1, reads=[], writes=[])
        (directory / "history-activation.json").unlink()
        fixture.jobs._write(directory, state, fixture.jobs._all())
    before = fixture.current()
    fresh = fixture.fresh()
    fresh.history.open(fixture.project)
    result = fresh.publish(job, proposal)
    assert result.publication == "needs_review" and result.publication_error.code == "DEPENDENCY_CHANGED"
    assert fresh.current() == before and fresh.jobs.load(fixture.project).history.namespace


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-D04:v01", "NB-D04:v02"])
async def test_project_uncertainty_blocks_its_writes_and_export_but_not_another_project(tmp_path, variant):
    from resume_api.gui_projects import ProjectFailure
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    job, proposal, _batch = fixture.accepted()
    def fail(name, _project):
        if name == "workspace_durable" and _project == fixture.project:
            raise OSError("Synthetic uncertain canonical replacement")
    fixture.coordinator.observer = fail
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fixture.publish(job, proposal)
    if variant == "NB-D04:v02":
        state = fixture.jobs.load(fixture.project)
        path = fixture.jobs.projects / fixture.project / "canonical-candidates" / (state.intents[0].candidate_ref + ".json")
        atomic_write(path, b'{"unreadable":')
    buffered = service.workspaces[fixture.project]
    block(buffered, "quote").content[0].text = "Recoverable input in the existing cache"
    assert service.persist(fixture.project) == "failed"
    assert block(service.workspaces[fixture.project], "quote").content[0].text == "Recoverable input in the existing cache"
    with pytest.raises(ProjectFailure, match="OUTCOME_UNKNOWN"):
        await service.export(fixture.project)
    with pytest.raises(ProjectFailure, match="OUTCOME_UNKNOWN"):
        service.portable(fixture.project)
    other = fixture.initial.model_copy(deep=True)
    other.project_id = other.project.project_id = "unfenced-project"
    service.storage.save(other, {}, {})
    service.workspaces[other.project_id] = other
    service.saved_baselines[other.project_id] = other.model_copy(deep=True)
    request = mutation(other, [put(other, "quote", text="Other project input")], "unfenced-input")
    response = service.mutate(other.project_id, request)
    assert response.durability == "durable" and block(response.workspace, "quote").content[0].text == "Other project input"
    service.renderer = HeldRenderer(); service.renderer.release.set()
    snapshot, blob = await service.export(other.project_id)
    assert snapshot.document_revision == response.workspace.document_revision and blob
    assert not service.files and not service.tasks
