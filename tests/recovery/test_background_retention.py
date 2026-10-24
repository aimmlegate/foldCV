"""Frozen byte, record and age boundaries preserve unresolved authority and replay."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.resume_core.background_limits import LIMITS, background_global_bytes, background_project_bytes
from packages.resume_core.background_proposals import JobProposals
from packages.resume_core.background_retention import JobRetention
from packages.resume_core.background_store import BackgroundFailure, JobStore, records
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.background import AssetPinV1
from packages.resume_core.project_store import encoded
from packages.resume_core.storage import atomic_write
from tests.recovery.test_background_assets import Time, image_fixture, reclaim
from tests.recovery.test_background_proposals import proposal
from tests.recovery.test_background_store import capture
from tests.recovery.test_background_supervisor import environment
from tests.support.background_publication import PublicationFixture

BOUNDARIES = [(f"NB-A04:v{start + index:02d}", kind, scope, offset)
    for start, kind, scope in ((1, "bytes", "global"), (4, "bytes", "project"),
        (7, "records", "global"), (10, "records", "project")) for index, offset in enumerate((-1, 0, 1))]


def namespaces(fixture, count):
    states = [fixture.jobs.load(fixture.project)]
    for index in range(count - 1):
        workspace = fixture.initial.model_copy(deep=True)
        workspace.project_id = workspace.project.project_id = "capacity-" + str(index)
        fixture.canonical.save(workspace, {}, {})
        states.append(fixture.jobs.open(workspace.project_id))
    return states


@pytest.mark.parametrize("variant,kind,scope,offset", BOUNDARIES, ids=[item[0] for item in BOUNDARIES])
def test_real_private_storage_enforces_the_frozen_exact_boundary(tmp_path, variant, kind, scope, offset):
    fixture = PublicationFixture(tmp_path)
    jobs = fixture.jobs
    # Byte budgets follow Settings under the LIMITS ceilings; the global one is eight project budgets.
    limit = ((background_global_bytes() if scope == "global" else background_project_bytes()) if kind == "bytes"
        else getattr(LIMITS, "metadata_" + scope + "_records"))
    count = 1 if scope == "project" else 9 if kind == "bytes" else 17
    states = namespaces(fixture, count)
    target = limit + offset
    if kind == "bytes":
        existing = {state.project_id: len(encoded(state.model_dump(mode="json", by_alias=True))) + jobs._extra_bytes(state.project_id)
            for state in states}
        remaining = target - sum(existing.values())
        for state in states:
            length = min(background_project_bytes() - existing[state.project_id], remaining)
            path = jobs.projects / state.project_id / "capacity-padding.bin"
            with path.open("wb") as stream:
                stream.truncate(length)
            path.chmod(0o600)
            remaining -= length
        if remaining:
            path = jobs.projects / states[-1].project_id / "capacity-padding.bin"
            with path.open("r+b") as stream:
                stream.truncate(path.stat().st_size + remaining)
        assert sum(existing.values()) + sum((jobs.projects / state.project_id / "capacity-padding.bin").stat().st_size for state in states) == target
        selected = states[-1]
    else:
        remaining = target - sum(records(state) for state in states)
        for state in states:
            amount = min(LIMITS.metadata_project_records - records(state), remaining)
            state.asset_pins += [AssetPinV1(kind="export", owner="synthetic-owner-" + str(index), references=[]) for index in range(amount)]
            remaining -= amount
        if remaining:
            states[0].asset_pins.append(AssetPinV1(kind="export", owner="overflow-owner", references=[]))
            remaining -= 1
        assert remaining == 0
        assert sum(records(state) for state in states) == target
        for state in states[1:]:
            with jobs.guard(state.project_id) as directory:
                jobs._write(directory, state, jobs._all())
        selected = states[0]
    with jobs.guard(selected.project_id):
        if offset == 1:
            with pytest.raises(BackgroundFailure, match="JOB_STORAGE_FULL"):
                jobs._capacity(selected, jobs._all())
        else:
            jobs._capacity(selected, jobs._all())


@pytest.mark.asyncio
@pytest.mark.parametrize("variant,offset", [("NB-A04:v13", -1), ("NB-A04:v14", 0), ("NB-A04:v15", 1)],
    ids=["NB-A04:v13", "NB-A04:v14", "NB-A04:v15"])
async def test_proposal_byte_boundary_rejects_the_first_extra_byte_without_retry(tmp_path, variant, offset):
    store, state, clock, factory, supervisor = await environment(tmp_path)
    payload = b'{"synthetic":"' + b"x" * (LIMITS.proposal_bytes + offset - 16) + b'"}'
    assert len(payload) == LIMITS.proposal_bytes + offset
    manager = JobProposals(supervisor, lambda _reference: payload)
    async def execute(control, _actor):
        if offset == 1:
            with pytest.raises(ValidationError):
                proposal(control, payload)
            value = proposal(control, b"valid").model_copy(update={"payload_bytes": len(payload)})
            with pytest.raises(BackgroundFailure, match="PROTOCOL"):
                await manager.accept(control, value)
        else:
            assert (await manager.accept(control, proposal(control, payload))).proposal_stored
        return ExecutionOutcome(finished_at=clock.now())
    factory.callbacks["proposal-boundary"] = execute
    try:
        job, _ = await supervisor.submit(capture(state, "proposal-boundary"))
        await factory.actor(job)
        await supervisor.controls[job.id].task
        assert len(factory.calls) == 1
        assert bool(store.load(state.project_id).proposals) == (offset <= 0)
    finally:
        await supervisor.shutdown(); await manager.shutdown()
        factory.verify(); clock.verify()


@pytest.mark.parametrize("variant,offset", [("NB-A04:v22", -1), ("NB-A04:v23", 0), ("NB-A04:v24", 1)],
    ids=["NB-A04:v22", "NB-A04:v23", "NB-A04:v24"])
def test_resolved_history_ages_from_completion_and_retains_the_exact_replay(tmp_path, variant, offset):
    fixture = PublicationFixture(tmp_path)
    clock = Time(fixture.jobs.clock()); fixture.jobs.clock = clock
    request = capture(fixture.jobs.load(fixture.project))
    job, _ = fixture.jobs.submit(request)
    clock.advance(100)
    terminal = fixture.jobs.update(fixture.project, job.id, lambda _state, current: setattr(current, "execution", "completed"))
    clock.advance(LIMITS.resolved_seconds + offset)
    state = JobRetention(fixture.jobs).sweep(fixture.project)
    assert bool(state.jobs) == (offset < 0)
    assert state.requests[0].archived_result == (terminal if offset >= 0 else None)
    replayed, created = fixture.jobs.submit(request)
    assert not created and replayed == terminal


@pytest.mark.asyncio
@pytest.mark.parametrize("variant,offset", [("NB-A04:v34", -1), ("NB-A04:v35", 0), ("NB-A04:v36", 1)],
    ids=["NB-A04:v34", "NB-A04:v35", "NB-A04:v36"])
async def test_orphan_grace_boundary_uses_the_last_owner_release(tmp_path, variant, offset):
    fixture, service, clock, _aid, path = await image_fixture(tmp_path)
    clock.advance(LIMITS.orphan_asset_seconds + offset)
    reclaim(fixture, service)
    assert path.exists() == (offset < 0)
    assert bool(fixture.current().project.assets) == (offset < 0)


@pytest.mark.parametrize("variant,offset", [("NB-A04:v37", -1), ("NB-A04:v38", 0), ("NB-A04:v39", 1)],
    ids=["NB-A04:v37", "NB-A04:v38", "NB-A04:v39"])
def test_replay_horizon_persists_the_expired_epoch_floor_before_forgetting_the_id(tmp_path, variant, offset):
    fixture = PublicationFixture(tmp_path)
    clock = Time(fixture.jobs.clock()); fixture.jobs.clock = clock
    request = capture(fixture.jobs.load(fixture.project))
    job, _ = fixture.jobs.submit(request)
    terminal = fixture.jobs.update(fixture.project, job.id, lambda _state, current: setattr(current, "execution", "completed"))
    clock.advance(LIMITS.request_replay_seconds + offset)
    JobRetention(fixture.jobs).sweep(fixture.project)
    fresh = JobStore(fixture.root, clock=clock)
    if offset < 0:
        assert fresh.submit(request) == (terminal, False)
    else:
        state = fresh.load(fixture.project)
        assert not state.requests and state.expired_through_epoch >= request.identity.request_epoch
        with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
            fresh.submit(request)


@pytest.mark.parametrize("variant", ["NB-A04:v40", "NB-A04:v44"])
def test_old_unresolved_intent_or_proposal_is_never_pruned_to_satisfy_retention(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    clock = Time(fixture.jobs.clock()); fixture.jobs.clock = clock
    job, proposal, _batch = fixture.accepted()
    if variant == "NB-A04:v40":
        def fail(name, _project):
            if name == "before_workspace_replaced":
                raise OSError("Synthetic uncertain commit claim")
        fixture.coordinator.observer = fail
        with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
            fixture.publish(job, proposal)
    before = fixture.jobs.load(fixture.project)
    clock.advance(100 * 24 * 60 * 60)
    after = JobRetention(fixture.jobs).sweep(fixture.project)
    assert after.jobs == before.jobs and after.proposals == before.proposals and after.intents == before.intents
    assert after.requests == before.requests and fixture.artifacts.payload_for(fixture.project, proposal.payload)


@pytest.mark.parametrize("variant", ["NB-A04:v42", "NB-A04:v43"])
def test_pruned_saved_request_cannot_reexecute_even_when_file_cleanup_fails(tmp_path, monkeypatch, variant):
    fixture = PublicationFixture(tmp_path)
    clock = Time(fixture.jobs.clock()); fixture.jobs.clock = clock
    job, proposal, _batch = fixture.accepted()
    assert fixture.publish(job, proposal).receipt.durable
    before = fixture.current()
    clock.advance(LIMITS.request_replay_seconds)
    original = Path.unlink
    if variant == "NB-A04:v43":
        def full(path, *args, **kwargs):
            if path.parent.name == "canonical-candidates":
                raise OSError("Synthetic disk full at private cleanup")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "unlink", full)
        with pytest.raises(BackgroundFailure, match="JOB_STORE_UNAVAILABLE"):
            JobRetention(fixture.jobs).sweep(fixture.project)
        assert fixture.jobs.load(fixture.project).cleanup_refs
        monkeypatch.setattr(Path, "unlink", original)
    else:
        JobRetention(fixture.jobs).sweep(fixture.project)
    fresh = JobStore(fixture.root, clock=clock)
    with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
        fresh.submit(job.submission)
    assert fixture.current() == before and len(before.mutation_replay) == 1
    assert not JobRetention(fresh).sweep(fixture.project).cleanup_refs
