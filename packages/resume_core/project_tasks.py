"""In-memory registry of running work per project: imports, exports and rewrite previews (D109).

`GET /tasks` reads it for the activity view (stage, elapsed time, saved discoveries); nothing here is durable. An
import that the service lost resumes from its operation sidecar, not from this registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import itertools
import threading
import time

KINDS = frozenset({'import', 'export', 'rewrite'})
STATES = frozenset({'running', 'succeeded', 'failed', 'cancelled'})
FINISHED_KEPT = 50


class TaskFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass
class Task:
    id: str
    project_id: str
    kind: str
    state: str
    stage: str | None
    started_at: str
    started: float
    detail: dict = field(default_factory=dict)
    error: str | None = None
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    def status(self, now):
        end = self.finished if self.finished is not None else now
        return {'id': self.id, 'projectId': self.project_id, 'kind': self.kind, 'state': self.state, 'stage': self.stage,
            'startedAt': self.started_at, 'elapsed': round(max(0.0, end - self.started), 3), 'detail': dict(self.detail),
            'error': self.error}


class TaskRegistry:
    def __init__(self, *, clock=time.monotonic, wall=lambda: datetime.now(timezone.utc).isoformat()):
        self.clock, self.wall = clock, wall
        self.lock = threading.Lock()
        self.tasks: dict[str, Task] = {}
        self.counter = itertools.count(1)

    def start(self, project_id, kind, *, stage=None, detail=None, exclusive=True):
        """A running task; with `exclusive` a second running task of the same kind on the project is refused."""
        if kind not in KINDS:
            raise ValueError('unknown task kind')
        with self.lock:
            if exclusive and any(task.project_id == project_id and task.kind == kind and task.state == 'running'
                    for task in self.tasks.values()):
                raise TaskFailure('REQUEST_IN_PROGRESS')
            identifier = '%s_%d' % (kind, next(self.counter))
            task = Task(identifier, project_id, kind, 'running', stage, self.wall(), self.clock(), dict(detail or {}))
            self.tasks[identifier] = task
            return task

    def update(self, task_id, *, stage=None, detail=None):
        with self.lock:
            task = self._get(task_id)
            if task.state != 'running':
                return task
            if stage is not None:
                task.stage = stage
            if detail is not None:
                task.detail = {**task.detail, **detail}
            return task

    def finish(self, task_id, state, *, error=None, detail=None):
        if state not in STATES - {'running'}:
            raise ValueError('a finished task needs a final state')
        with self.lock:
            task = self._get(task_id)
            if task.state == 'running':
                task.state, task.error, task.finished = state, error, self.clock()
                if detail is not None:
                    task.detail = {**task.detail, **detail}
            self._trim()
            return task

    def cancel(self, task_id):
        with self.lock:
            task = self._get(task_id)
            task.cancel.set()
            return task

    def running(self, project_id, kind=None):
        with self.lock:
            return [task for task in self.tasks.values() if task.project_id == project_id and task.state == 'running'
                and (kind is None or task.kind == kind)]

    def list(self, project_id=None):
        now = self.clock()
        with self.lock:
            return [task.status(now) for task in self.tasks.values() if project_id is None or task.project_id == project_id]

    def forget(self, project_id):
        """Drop the finished tasks of a deleted project; running ones are cancelled by their owner first."""
        with self.lock:
            for identifier in [key for key, task in self.tasks.items() if task.project_id == project_id and task.state != 'running']:
                self.tasks.pop(identifier)

    def _get(self, task_id):
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskFailure('JOB_NOT_FOUND')
        return task

    def _trim(self):
        finished = sorted((task for task in self.tasks.values() if task.state != 'running'), key=lambda task: task.finished)
        for task in finished[:max(0, len(finished) - FINISHED_KEPT)]:
            self.tasks.pop(task.id)
