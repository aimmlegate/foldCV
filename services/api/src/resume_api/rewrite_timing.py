"""Bounded local phase timings without resume text, prompts or credentials."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import math
import threading
import time

from packages.resume_core.storage import StorageFailure, atomic_write, locked_root, private_file


_CURRENT = ContextVar("rewrite_timing", default=None)
_PHASES = {"prepare", "content", "worker_queue", "account_queue", "preflight", "cli_startup",
    "model_turn", "cli_process", "decode", "proposal", "publish", "response", "total"}


def _valid_row(row):
    if not isinstance(row, dict) or set(row) != {"at", "blocks", "outcome", "milliseconds"}:
        return False
    phases = row["milliseconds"]
    return (isinstance(row["at"], str) and len(row["at"]) <= 40
        and type(row["blocks"]) is int and 0 <= row["blocks"] <= 100
        and isinstance(row["outcome"], str) and row["outcome"] in {"pending", "failed", "conflict", "stale", "applied"}
        and isinstance(phases, dict) and phases.keys() <= _PHASES
        and all(type(value) in {int, float} and math.isfinite(value) and value >= 0 for value in phases.values()))


class RewriteTiming:
    def __init__(self, blocks):
        self.blocks, self.phases, self.outcome = blocks, {}, "failed"
        self.lock = threading.Lock()

    def add(self, phase, seconds):
        if phase in _PHASES:
            with self.lock:
                self.phases[phase] = self.phases.get(phase, 0) + max(0, seconds)

    def save(self, root):
        directory = root / "diagnostics"
        path = directory / "rewrite-timings.json"
        try:
            with locked_root(directory, ".timings.lock"):
                rows = []
                if path.exists():
                    private_file(path)
                    if path.stat().st_size <= 65536:
                        rows = json.loads(path.read_bytes())
                        if not isinstance(rows, list):
                            rows = []
                rows = [row for row in rows if _valid_row(row)][-49:]
                rows.append({"at": datetime.now(timezone.utc).isoformat(), "blocks": self.blocks,
                    "outcome": self.outcome, "milliseconds": {key: round(value * 1000, 2) for key, value in self.phases.items()}})
                atomic_write(path, (json.dumps(rows, indent=2) + "\n").encode())
        except (OSError, ValueError, StorageFailure):
            # Diagnostics must never change the edit or its save outcome.
            pass


def add_phase(phase, seconds):
    current = _CURRENT.get()
    if current is not None:
        current.add(phase, seconds)


@contextmanager
def measure(phase):
    started = time.perf_counter()
    try:
        yield
    finally:
        add_phase(phase, time.perf_counter() - started)


@contextmanager
def rewrite_timing(root, blocks):
    timing = RewriteTiming(blocks)
    token = _CURRENT.set(timing)
    try:
        with measure("total"):
            yield timing
    finally:
        _CURRENT.reset(token)
        timing.save(root)
