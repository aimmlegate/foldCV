"""Bounded job snapshot replay; gaps never masquerade as a complete event stream."""

from __future__ import annotations

import json

from .background_limits import LIMITS
from .background_store import BackgroundFailure, JobStore, job_in
from .models.background import JobEventV1, JobSnapshotV1
from .project_store import owned_file, strict_json
from .storage import StorageFailure, atomic_write, private_directory


def event_bytes(events) -> bytes:
    return json.dumps([item.model_dump(mode="json", by_alias=True) for item in events], ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()


def snapshot_event(job: JobSnapshotV1, *, gap=False) -> JobEventV1:
    return JobEventV1(schemaVersion=1, projectId=job.submission.identity.project_id,
        lineage=job.submission.identity.lineage, jobId=job.id, generation=job.execution_generation,
        cursor=job.event_cursor, type="cursor.gap" if gap else "job.snapshot", snapshot=job)


class JobEvents:
    def __init__(self, store: JobStore):
        self.store = store

    def _read(self, path):
        if not path.exists():
            return []
        try:
            owned_file(path, LIMITS.replay_bytes)
            raw = strict_json(path.read_bytes())
            if not isinstance(raw, list) or len(raw) > LIMITS.replay_events:
                raise ValueError("invalid replay window")
            events = [JobEventV1.model_validate(item) for item in raw]
            cursors = [item.cursor for item in events]
            if cursors != sorted(set(cursors)) or any(item.type != "job.snapshot" for item in events):
                raise ValueError("invalid replay order")
            return events
        except (OSError, StorageFailure, ValueError, RecursionError):
            return None

    def append(self, job: JobSnapshotV1):
        project_id = job.submission.identity.project_id
        with self.store.guard(project_id) as directory:
            state = self.store._read(project_id, directory)
            if job_in(state, job.id) != job:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            folder = private_directory(directory / "events")
            path = folder / (job.id + ".json")
            previous = self._read(path)
            events = previous or []
            if events and (events[-1].project_id != project_id or events[-1].lineage != job.submission.identity.lineage
                    or events[-1].job_id != job.id or events[-1].generation != job.execution_generation):
                events = []
            if events and events[-1].cursor >= job.event_cursor:
                if events[-1] == snapshot_event(job):
                    return
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            events.append(snapshot_event(job))
            while len(events) > LIMITS.replay_events or len(event_bytes(events)) > LIMITS.replay_bytes:
                events.pop(0)
            raw = event_bytes(events)
            self.store._capacity(state, self.store._all(), replacing=(path, len(raw)))
            try:
                atomic_write(path, raw)
                self.store._sync_namespace(path)
            except (OSError, StorageFailure):
                raise BackgroundFailure("JOB_EVENT_REPLAY_UNAVAILABLE") from None

    def replay(self, project_id: str, job_id: str, *, after: int, generation: int):
        with self.store.guard(project_id) as directory:
            state = self.store._read(project_id, directory)
            job = job_in(state, job_id)
            if type(after) is not int or after < 0 or type(generation) is not int or generation < 1:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            if generation != job.execution_generation or after > job.event_cursor:
                return [snapshot_event(job, gap=True)]
            if after == job.event_cursor:
                return []
            events = self._read(directory / "events" / (job_id + ".json"))
            if (not events or events[-1].cursor != job.event_cursor or events[-1].snapshot != job or events[0].cursor > after + 1 or
                    any(event.project_id != project_id or event.lineage != state.lineage or event.job_id != job_id
                        or event.generation != generation or event.snapshot.submission != job.submission
                        or event.snapshot.receipt is not None and event.snapshot.receipt != job.receipt for event in events)):
                return [snapshot_event(job, gap=True)]
            selected = [event for event in events if event.cursor > after]
            if [event.cursor for event in selected] != list(range(after + 1, job.event_cursor + 1)):
                return [snapshot_event(job, gap=True)]
            return selected
