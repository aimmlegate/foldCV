"""Replay is bounded private data, never another job authority."""

import json

import pytest

from packages.resume_core.background_events import JobEvents
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_store import BackgroundFailure, JobStore
from packages.resume_core.models.background import JobFailure
from spikes.background.fixtures import TIME, examples
from tests.recovery.test_background_store import capture
from tests.support.agent import isolated_project


def setup(root):
    _, _, workspace, _ = isolated_project(root)
    store = JobStore(root, clock=lambda: TIME)
    state = store.open(workspace.project_id)
    job, _ = store.submit(capture(state))
    return store, JobEvents(store), job


def advance(store, job):
    def progress(_state, current):
        current.error = JobFailure(code="BUSY") if current.error is None else None
    return store.update(job.submission.identity.project_id, job.id, progress)


@pytest.mark.parametrize("variant,offset", [("NB-A04:v19", -1), ("NB-A04:v20", 0), ("NB-A04:v21", 1)],
    ids=["NB-A04:v19", "NB-A04:v20", "NB-A04:v21"])
def test_event_window_bounds_return_an_explicit_gap_and_latest_snapshot(tmp_path, variant, offset):
    store, events, job = setup(tmp_path)
    count = LIMITS.replay_events + offset
    events.append(job)
    for _ in range(count - 1):
        job = advance(store, job)
        events.append(job)
    path = tmp_path / "background/projects" / job.submission.identity.project_id / "events" / (job.id + ".json")
    raw = json.loads(path.read_text())
    assert len(raw) <= LIMITS.replay_events and path.stat().st_size <= LIMITS.replay_bytes
    assert raw[-1]["cursor"] == job.event_cursor == count
    gap = events.replay(job.submission.identity.project_id, job.id, after=0, generation=1)
    assert len(gap) == 1 and gap[0].type == "cursor.gap" and gap[0].snapshot == job
    tail = events.replay(job.submission.identity.project_id, job.id, after=count - 1, generation=1)
    assert len(tail) == 1 and tail[0].type == "job.snapshot" and tail[0].snapshot == job
    assert events.replay(job.submission.identity.project_id, job.id, after=count, generation=1) == []


def test_replay_duplicate_append_and_lost_event_reply_do_not_change_job_authority(tmp_path):
    store, events, job = setup(tmp_path)
    events.append(job)
    events.append(job)
    current = advance(store, job)
    # State is durable while event delivery/storage is absent.
    gap = events.replay(job.submission.identity.project_id, job.id, after=1, generation=1)
    assert gap[0].type == "cursor.gap" and gap[0].snapshot == current
    events.append(current)
    replay = events.replay(job.submission.identity.project_id, job.id, after=0, generation=1)
    assert [event.cursor for event in replay] == [1, 2]
    assert store.read(job.submission.identity.project_id, job.id) == current
    with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
        events.append(job)
    assert events.replay(job.submission.identity.project_id, job.id, after=0, generation=2)[0].type == "cursor.gap"


def test_forged_saved_event_cannot_override_the_authoritative_pending_job(tmp_path):
    store, events, job = setup(tmp_path)
    events.append(job)
    current = advance(store, job)
    events.append(current)
    project = job.submission.identity.project_id
    path = tmp_path / "background/projects" / project / "events" / (job.id + ".json")
    raw = json.loads(path.read_text())
    proof = examples()["background_receipt_v1"]
    proof.update(projectId=project, lineage=job.submission.identity.lineage, jobId=job.id, proposalId="forged-proposal")
    raw[0]["snapshot"].update(publication="saved", proposalId="forged-proposal", receipt=proof)
    path.write_text(json.dumps(raw))
    assert events._read(path) is not None
    replay = events.replay(project, job.id, after=0, generation=1)
    assert replay[0].type == "cursor.gap" and replay[0].snapshot == current
    assert replay[0].snapshot.receipt is None


def test_offline_fixture_blocks_native_factories_and_unregistered_processes(tmp_path):
    import subprocess
    from resume_api.agent.runtime import CodexAgentRuntime
    with pytest.raises(AssertionError, match="production runtime"):
        CodexAgentRuntime(None, tmp_path)
    with pytest.raises(AssertionError, match="unregistered child"):
        subprocess.Popen(["/usr/bin/true"])
