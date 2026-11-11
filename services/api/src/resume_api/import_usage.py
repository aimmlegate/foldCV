"""One diagnostics file per import with each call's usage and the coordinator's timing (T0.1, R1).

`<data root>/diagnostics/import-usage/<operation id>.json` is written by the import's coordinator: after each returned
call and once at the end of a run. It holds numbers, ids, codes, model names and times only, never text of the source,
a prompt or a reply. A failed write is dropped and never changes the import.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
import json
import logging
import os
from pathlib import Path
import re
import threading
import time

from packages.resume_core.storage import atomic_write, locked_root, private_directory
from resume_api import rewrite_timing


LOG = logging.getLogger(__name__)
MAX_BYTES = 256 * 1024
KEPT = 40
NAME = re.compile(r"[A-Za-z0-9_-]{1,128}")
# The phases the providers report through rewrite_timing's add_phase and measure, as this file names them.
PHASES = {"preflight": "preflight", "cli_startup": "cliStartup", "model_turn": "modelTurn",
          "cli_process": "cliProcess", "decode": "decode"}
STEP_PARTS = ("lockWait", "poolWait", "transition", "validation", "write")
TASK_PARTS = ("taskInput", "derive", "makeReviewInput", "parseProposal")
_CURRENT: ContextVar[ImportUsage | None] = ContextVar("import_usage", default=None)
_STEP: ContextVar[_Step | None] = ContextVar("import_usage_step", default=None)


def _seconds(value: float) -> float:
    return round(max(0.0, value), 6)


def _rounded(value):
    """A provider's numbers with float sums cut to nine places."""
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    return round(value, 9) if isinstance(value, float) else value


def _row(attempt, task) -> dict:
    """The attempt as the import record holds it; `reported` is the record's usage."""
    usage = attempt.usage
    return {"attemptId": attempt.id, "taskId": attempt.task_id, "blockId": task.block_id if task else None,
            "entry": task is not None and task.entry is not None, "slot": attempt.slot,
            "provider": attempt.model.adapter, "model": attempt.model.model, "effort": attempt.model.effort,
            "outcome": attempt.outcome, "errorCode": attempt.error_code,
            "dispatchedAt": attempt.dispatched_at, "returnedAt": attempt.returned_at,
            "reported": {"inputTokens": usage.input_tokens, "cachedInputTokens": usage.cached_input_tokens,
                         "outputTokens": usage.output_tokens}}


def _dumps(value) -> bytes:
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"


class ImportUsage:
    """What one run of an import collects. Calls, steps and the end write run on other threads, so every change and
    read holds `lock`."""

    def __init__(self, root: Path, project: str, operation_id: str, started_at: str):
        self.folder = root / "diagnostics" / "import-usage"
        self.path = self.folder / (operation_id + ".json")
        self.project, self.operation_id = project, operation_id
        self.started_at, self.ended_at, self.state = started_at, None, None
        self.lock = threading.Lock()
        self.rows: dict[str, dict] = {}
        self.details: dict[str, dict] = {}
        self.phases: dict[str, dict[str, float]] = {}
        self.steps: dict[str, dict] = {}
        self.sums = {"tasks": dict.fromkeys(TASK_PARTS, 0.0), "finalization": {}}
        self.warned = False

    def observe(self, operation, attempt_id: str | None = None) -> None:
        """One attempt's row as the record now holds it; without an id every row, in the record's order."""
        tasks = {task.id: task for task in operation.tasks}
        rows = {attempt.id: _row(attempt, tasks.get(attempt.task_id)) for attempt in operation.attempts
                if attempt_id is None or attempt.id == attempt_id}
        with self.lock:
            self.state = operation.state
            if attempt_id is None:
                self.rows = rows
            else:
                self.rows.update(rows)

    def returned(self, attempt_id: str, detail: dict | None, operation) -> None:
        with self.lock:
            self.details[attempt_id] = detail or {}
        self.observe(operation, attempt_id)

    def end(self, ended_at: str) -> None:
        with self.lock:
            self.ended_at = ended_at

    def started(self, attempt_id: str, pool_wait: float) -> None:
        with self.lock:
            self.phases[attempt_id] = {"poolWait": max(0.0, pool_wait), **dict.fromkeys(PHASES.values(), 0.0)}

    def phase(self, attempt_id: str, name: str, seconds: float) -> None:
        with self.lock:
            self.phases[attempt_id][name] += max(0.0, seconds)

    def step(self, kind: str, parts: dict[str, float]) -> None:
        with self.lock:
            sums = self.steps.setdefault(kind, {"count": 0, **dict.fromkeys(STEP_PARTS, 0.0)})
            sums["count"] += 1
            for part, seconds in parts.items():
                sums[part] += max(0.0, seconds)

    def add(self, group: str, part: str, seconds: float) -> None:
        with self.lock:
            self.sums[group][part] = self.sums[group].get(part, 0.0) + max(0.0, seconds)

    def value(self) -> dict:
        with self.lock:
            attempts = []
            for identifier, row in self.rows.items():
                detail, phases = self.details.get(identifier, {}), self.phases.get(identifier)
                attempts.append({**row, "claude": _rounded(detail.get("claude")), "codex": _rounded(detail.get("codex")),
                                 "phases": {name: _seconds(seconds) for name, seconds in phases.items()} if phases else None})
            return {"version": 1, "operationId": self.operation_id, "projectId": self.project,
                    "startedAt": self.started_at, "endedAt": self.ended_at, "state": self.state, "attempts": attempts,
                    "steps": {kind: {part: value if part == "count" else _seconds(value) for part, value in sums.items()}
                              for kind, sums in self.steps.items()},
                    "tasks": {part: _seconds(value) for part, value in self.sums["tasks"].items()},
                    "finalization": {part: _seconds(value) for part, value in self.sums["finalization"].items()}}

    def encode(self) -> bytes:
        value = self.value()
        raw = _dumps(value)
        if len(raw) > MAX_BYTES:
            # The oldest rows go first; the count says how many, so sums read from the file are not taken as whole.
            rows = value["attempts"]
            excess, dropped = len(raw) - MAX_BYTES + 64, 0
            while dropped < len(rows) and excess > 0:
                excess -= len(_dumps(rows[dropped]))
                dropped += 1
            value["attempts"], value["droppedAttempts"] = rows[dropped:], dropped
            raw = _dumps(value)
        if len(raw) > MAX_BYTES:
            raise ValueError("import usage too large")
        return raw

    def save(self) -> None:
        try:
            private_directory(self.folder.parent)
            with locked_root(self.folder, ".import-usage.lock"):
                created = not self.path.exists()
                atomic_write(self.path, self.encode())
                if created:
                    self.prune()
        except Exception as error:
            # Diagnostics never change the import, as rewrite timings never change an edit.
            if not self.warned:
                self.warned = True
                LOG.warning("import usage file not written: %s", type(error).__name__)

    def prune(self) -> None:
        """The newest KEPT files stay, this one among them; the oldest beyond them go."""
        files = []
        with os.scandir(self.folder) as entries:
            for entry in entries:
                if (entry.name != self.path.name and entry.name.endswith(".json") and NAME.fullmatch(entry.name[:-5])
                        and entry.is_file(follow_symlinks=False)):
                    files.append((entry.stat(follow_symlinks=False).st_mtime_ns, entry.name))
        for _changed, name in sorted(files, reverse=True)[KEPT - 1:]:
            (self.folder / name).unlink(missing_ok=True)


class _Step:
    def __init__(self, submitted: float | None):
        self.mark = time.perf_counter()
        self.parts = {"poolWait": self.mark - submitted if submitted is not None else 0.0}

    def lap(self, part: str) -> None:
        now = time.perf_counter()
        self.parts[part] = self.parts.get(part, 0.0) + now - self.mark
        self.mark = now


class _Phases:
    """rewrite_timing's collector for one call: the provider's phases go to the attempt's row."""

    def __init__(self, usage: ImportUsage, attempt_id: str):
        self.usage, self.attempt_id = usage, attempt_id

    def add(self, phase: str, seconds: float) -> None:
        if phase in PHASES:
            self.usage.phase(self.attempt_id, PHASES[phase], seconds)


@asynccontextmanager
async def collecting(root: Path | None, project: str, operation_id: str, wall, read):
    """The collector of one run of an import; `wall()` stamps its start and end. When the run ends, the last write
    takes every row from the record `read()` gives, in a worker thread."""
    usage = ImportUsage(root, project, operation_id, wall()) if root is not None and NAME.fullmatch(operation_id) else None
    token = _CURRENT.set(usage)
    try:
        yield usage
    finally:
        _CURRENT.reset(token)
        if usage is not None:
            try:
                await asyncio.to_thread(_last, usage, wall, read)
            except Exception:
                pass


def _last(usage: ImportUsage, wall, read) -> None:
    try:
        usage.observe(read())
    except Exception:
        pass  # the record could not be read: the rows stay as the run saw them
    usage.end(wall())
    usage.save()


@contextmanager
def call(attempt_id: str, pool_wait: float):
    """One model call of the open import: the phases its provider reports go to the attempt's row."""
    usage = _CURRENT.get()
    if usage is None:
        yield
        return
    usage.started(attempt_id, pool_wait)
    token = rewrite_timing._CURRENT.set(_Phases(usage, attempt_id))
    try:
        yield
    finally:
        rewrite_timing._CURRENT.reset(token)


def returned(attempt_id: str, detail: dict | None, operation) -> None:
    """A call came back: its provider's numbers and its row are kept and the file is written."""
    usage = _CURRENT.get()
    if usage is None:
        return
    try:
        usage.returned(attempt_id, detail, operation)
    except Exception:
        pass
    usage.save()


@contextmanager
def step(kind: str, submitted: float | None = None):
    """One operation step of the open import: its parts (see `lap`) are summed under `kind` when it ends; `submitted`
    is when it was handed to a worker thread."""
    usage = _CURRENT.get()
    if usage is None:
        yield
        return
    current = _Step(submitted)
    token = _STEP.set(current)
    try:
        yield
    finally:
        _STEP.reset(token)
        usage.step(kind, current.parts)


def lap(part: str) -> None:
    """The time since the open step's last mark goes to its `part`."""
    current = _STEP.get()
    if current is not None:
        current.lap(part)


@contextmanager
def timed(group: str, part: str):
    """Time the block into `part` of the open import's `tasks` or `finalization`."""
    started = time.perf_counter()
    try:
        yield
    finally:
        usage = _CURRENT.get()
        if usage is not None:
            usage.add(group, part, time.perf_counter() - started)
