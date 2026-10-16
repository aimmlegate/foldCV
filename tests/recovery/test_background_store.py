"""Real private job transactions beside synthetic canonical projects."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from packages.resume_core.background_store import BackgroundFailure, JobStore
from packages.resume_core.models.background import JobSubmissionV1
from packages.resume_core import background_store as persistence
from spikes.background.fixtures import TIME, submission
from tests.support.agent import isolated_project


def capture(state, key="request-one", **changes):
    value = submission()
    value["identity"].update(projectId=state.project_id, lineage=state.lineage,
        requestEpoch=state.active_request_epoch, requestId=key)
    value["accountGeneration"] = state.account_generation
    value.update(changes)
    return JobSubmissionV1.model_validate(value)


@pytest.fixture
def projects(tmp_path):
    _, canonical, workspace, _ = isolated_project(tmp_path)
    second = workspace.model_copy(deep=True)
    second.project_id = "second-project"
    second.project.project_id = second.project_id
    canonical.save(second, {}, {})
    return tmp_path, workspace.project_id, second.project_id


@pytest.mark.parametrize("variant", ["NB-J01:v01", "NB-J01:v02", "NB-J01:v03"])
def test_concurrent_submit_replays_exact_identity_or_conflicts(projects, variant):
    root, first, second = projects
    store = JobStore(root, clock=lambda: TIME)
    one = store.open(first)
    two = store.open(second)
    request_one = capture(one)
    request_two = capture(two if variant == "NB-J01:v03" else one,
        payloadSha256="b" * 64 if variant == "NB-J01:v02" else request_one.payload_sha256)
    barrier = threading.Barrier(2, timeout=10)

    def send(request):
        barrier.wait()
        try:
            return JobStore(root, clock=lambda: TIME).submit(request)
        except BackgroundFailure as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(send, [request_one, request_two]))
    if variant == "NB-J01:v01":
        assert results[0][0].id == results[1][0].id
        assert sorted(result[1] for result in results) == [False, True]
    elif variant == "NB-J01:v02":
        assert results.count("JOB_IDEMPOTENCY_CONFLICT") == 1
    else:
        assert results[0][0].id != results[1][0].id
        assert all(result[1] for result in results)
    fresh = JobStore(root, clock=lambda: TIME)
    assert len(fresh.load(first).jobs) == 1
    assert len(fresh.load(second).jobs) == int(variant == "NB-J01:v03")


def test_lost_submit_reply_replays_original_capture_after_restart(projects):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    context = store.open(first)
    original = capture(context)
    job, created = store.submit(original)
    assert created
    changed_capture = original.model_dump(by_alias=True)
    changed_capture["models"][0]["model"] = "new-selection"
    changed_capture["tools"] = ["get_resume_context"]
    replayed, created = JobStore(root, clock=lambda: TIME).submit(JobSubmissionV1.model_validate(changed_capture))
    assert not created
    assert replayed == job
    assert replayed.submission.models[0].model == "synthetic-model"


def test_missing_or_corrupt_private_state_is_not_reset(projects):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    context = store.open(first)
    path = root / "background/projects" / first / "state.json"
    original = path.read_bytes()
    path.unlink()
    with pytest.raises(BackgroundFailure, match="JOB_STORE_CORRUPT"):
        JobStore(root, clock=lambda: TIME).open(first)
    assert not path.exists()
    path.write_bytes(original)
    path.chmod(0o600)
    assert JobStore(root, clock=lambda: TIME).load(first) == context


def test_missing_account_header_cannot_reset_a_project_to_an_older_account(projects):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    store.open(first)
    store.replace_account(2)
    path = root / "background/dispatch.json"
    path.unlink()
    fresh = JobStore(root, clock=lambda: TIME)
    with pytest.raises(BackgroundFailure, match="JOB_STORE_CORRUPT"):
        fresh.dispatch_state()
    with pytest.raises(BackgroundFailure, match="JOB_STORE_CORRUPT"):
        fresh.submit(capture(fresh.load(first)))
    assert not path.exists()


def test_project_tombstone_rejects_new_jobs_and_reads(projects):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(first)
    request = capture(state)
    store.canonical.tombstone(first)
    with pytest.raises(BackgroundFailure, match="PROJECT_DELETED"):
        store.submit(request)
    with pytest.raises(BackgroundFailure, match="PROJECT_DELETED"):
        store.load(first)


@pytest.mark.parametrize("allow_edits", [True, False])
def test_queued_cancel_is_idempotent_and_reuses_admission_place(projects, allow_edits):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(first)
    value = capture(state).model_dump(by_alias=True)
    if not allow_edits:
        value.update(allowEdits=False, tools=["get_resume_context"])
        value["guards"]["writes"] = []
    job, _ = store.submit(JobSubmissionV1.model_validate(value))
    cancelled = store.cancel(first, job.id)
    assert cancelled.execution == "cancelled"
    assert cancelled.publication == ("cancelled" if allow_edits else "none")
    assert store.cancel(first, job.id) == cancelled
    replacement, created = store.submit(capture(state, key="explicit-new-request"))
    assert created and replacement.id != cancelled.id


def test_restart_interrupts_queued_work_and_retains_request_without_dispatch(projects):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(first)
    request = capture(state)
    job, _ = store.submit(request)
    restarted = JobStore(root, clock=lambda: TIME)
    recovered = restarted.recover(first)
    assert recovered.jobs[0].id == job.id
    assert recovered.jobs[0].execution == "interrupted"
    assert recovered.jobs[0].error.code == "INTERRUPTED"
    assert restarted.submit(request)[0] == recovered.jobs[0]
    assert restarted.recover(first) == recovered


def test_expired_epoch_rejects_unknown_ids_but_replays_retained_requests(projects):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(first)
    request = capture(state)
    job, _ = store.submit(request)
    expired = JobStore(root, clock=lambda: "2026-11-16T12:00:00Z")
    assert expired.submit(request) == (job, False)
    with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
        expired.submit(capture(state, key="unknown-old-request"))
    rotated = expired.rotate_request_epoch(first)
    assert rotated.active_request_epoch == 2 and rotated.expired_through_epoch == 1
    assert expired.submit(request) == (job, False)
    with pytest.raises(BackgroundFailure, match="REQUEST_EXPIRED"):
        expired.submit(capture(state, key="another-old-request"))
    current, created = expired.submit(capture(rotated, key="explicit-new-epoch"))
    assert created and current.submission.identity.request_epoch == 2


@pytest.mark.parametrize("variant", ["NB-J02:v01", "NB-J02:v02", "NB-J02:v03"])
def test_submit_persistence_cutpoints_have_one_recoverable_identity(projects, monkeypatch, variant):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(first)
    request = capture(state)
    original = persistence.atomic_write
    reached = []

    def broken(path, raw):
        reached.append(str(path))
        if variant != "NB-J02:v01":
            original(path, raw)
        raise OSError("synthetic persistence reply lost")

    with monkeypatch.context() as patch:
        patch.setattr(persistence, "atomic_write", broken)
        if variant == "NB-J02:v01":
            with pytest.raises(BackgroundFailure, match="JOB_STORE_UNAVAILABLE"):
                store.submit(request)
        else:
            first_result, created = store.submit(request)
            assert created
    assert len(reached) == 1
    restarted = JobStore(root, clock=lambda: TIME)
    if variant == "NB-J02:v03":
        restarted.recover(first)
    replayed, created = restarted.submit(request)
    assert created == (variant == "NB-J02:v01")
    if variant != "NB-J02:v01":
        assert replayed.id == first_result.id
    assert len(restarted.load(first).jobs) == len(restarted.load(first).requests) == 1


def test_unproved_write_reply_replays_only_after_exact_durability_is_confirmed(projects, monkeypatch):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(first)
    request = capture(state)
    original = persistence.atomic_write

    with monkeypatch.context() as patch:
        def lost_reply(path, raw):
            original(path, raw)
            patch.setattr(persistence.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("synthetic unproved fsync")))
            raise OSError("synthetic lost reply")
        patch.setattr(persistence, "atomic_write", lost_reply)
        with pytest.raises(BackgroundFailure, match="JOB_STORE_UNAVAILABLE"):
            store.submit(request)
    assert store.fences[first] == "JOB_STORE_UNAVAILABLE"
    stored = JobStore(root, clock=lambda: TIME).load(first).jobs
    assert len(stored) == 1
    job, created = JobStore(root, clock=lambda: TIME).submit(request)
    assert not created and job == stored[0]
    assert JobStore(root, clock=lambda: TIME).submit(request) == (job, False)


@pytest.mark.parametrize("field,value", [("account_generation", 2), ("allow_edits", False), ("scheduling_class", "interactive")])
def test_job_update_cannot_rewrite_captured_authority(projects, field, value):
    root, first, _ = projects
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(first)
    job, _ = store.submit(capture(state))
    def rewrite(_state, current):
        setattr(current.submission, field, value)
    with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
        store.update(first, job.id, rewrite)
    assert store.read(first, job.id) == job
