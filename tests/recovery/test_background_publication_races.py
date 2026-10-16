"""Revocation and canonical commitment have one observable winner."""

import threading

import pytest

from packages.resume_core.background_events import JobEvents
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.project_store import ProjectStoreFailure
from tests.recovery.test_background_inverse import block
from tests.support.background_publication import PublicationFixture


@pytest.mark.parametrize("variant", ["NB-J05:v01", "NB-J05:v02", "NB-J05:v05"])
def test_discard_and_old_event_delivery_cannot_reverse_the_winner(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    events = JobEvents(fixture.jobs)
    events.append(job)
    if variant == "NB-J05:v02":
        saved = fixture.publish(job, proposal)
        result = fixture.jobs.discard(fixture.project, job.id)
        assert result.receipt == saved.receipt and result.publication == "saved"
    else:
        result = fixture.jobs.discard(fixture.project, job.id)
        if variant == "NB-J05:v05":
            with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
                events.append(job)
            replay = events.replay(fixture.project, job.id, after=0, generation=1)
            assert replay[0].snapshot == result and replay[0].snapshot.publication == "discarded"
        with pytest.raises(BackgroundFailure, match="CANCELLED"):
            fixture.publish(job, proposal)
        assert not fixture.current().mutation_replay


def revoke(fixture, job, cause):
    if cause == "stop":
        return fixture.jobs.cancel(fixture.project, job.id)
    if cause == "account":
        return fixture.jobs.replace_account(2)
    fixture.canonical.tombstone(fixture.project)
    fixture.canonical.cleanup_deleted(fixture.project)


@pytest.mark.parametrize("variant", [f"NB-P10:v{index:02d}" for index in range(3, 9)])
def test_stop_account_and_delete_orders_keep_saved_truth_or_the_tombstone(tmp_path, variant):
    for cause in ("stop", "account", "delete"):
        fixture = PublicationFixture(tmp_path / cause)
        job, proposal, _batch = fixture.accepted()
        if variant in {"NB-P10:v03", "NB-P10:v07"}:
            revoke(fixture, job, cause)
            with pytest.raises(BackgroundFailure, match="CANCELLED|ACCOUNT_CHANGED|PROJECT_DELETED"):
                fixture.publish(job, proposal)
            if cause != "delete":
                assert not fixture.current().mutation_replay
            continue
        if variant == "NB-P10:v08":
            reached = []
            def fail(name, _project):
                if name == "workspace_replaced":
                    reached.append(name)
                    raise OSError("Synthetic uncertain replacement")
            fixture.coordinator.observer = fail
            with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
                fixture.publish(job, proposal)
            assert reached == ["workspace_replaced"]
            revoke(fixture, job, cause)
            if cause != "delete":
                assert fixture.jobs.read(fixture.project, job.id).publication == "outcome_unknown"
                fresh = fixture.fresh()
                fresh.coordinator.recover(fixture.project)
                assert fresh.jobs.read(fixture.project, job.id).receipt.durable
            else:
                with pytest.raises(BackgroundFailure, match="PROJECT_DELETED"):
                    fixture.coordinator.recover(fixture.project)
            continue
        phase = {"NB-P10:v04": "before_commit_claim", "NB-P10:v05": "commit_claimed",
            "NB-P10:v06": "workspace_durable"}[variant]
        reached, attempted, finished = threading.Event(), threading.Event(), threading.Event()
        failures = []
        def worker():
            assert reached.wait(10)
            attempted.set()
            try:
                revoke(fixture, job, cause)
            except BaseException as error:
                failures.append(error)
            finally:
                finished.set()
        thread = threading.Thread(target=worker)
        thread.start()
        def observe(name, _project):
            if name == phase:
                reached.set()
                assert attempted.wait(10)
                if phase == "before_commit_claim":
                    assert finished.wait(10)
        fixture.coordinator.observer = observe
        try:
            try:
                result = fixture.publish(job, proposal)
            except BackgroundFailure as error:
                assert phase == "before_commit_claim" and cause == "delete" and error.code == "PROJECT_DELETED"
                result = None
        finally:
            thread.join(timeout=10)
        assert reached.is_set() and finished.is_set() and not thread.is_alive() and not failures
        if phase == "before_commit_claim":
            if result is not None:
                assert result.publication == "cancelled" and result.receipt is None
                assert not fixture.current().mutation_replay
        else:
            assert result.receipt.durable
            if cause != "delete":
                assert fixture.jobs.read(fixture.project, job.id).receipt == result.receipt
        if cause == "delete":
            with pytest.raises(ProjectStoreFailure, match="PROJECT_DELETED"):
                fixture.current()
            assert not (fixture.canonical.projects / fixture.project).exists()
