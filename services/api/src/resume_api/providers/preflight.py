"""Short-lived metadata reuse scoped to the CLI and credential-file identity."""

from dataclasses import dataclass
import os
from pathlib import Path
import threading
import time
from typing import Callable, Generic, TypeVar


ResultT = TypeVar("ResultT")
TTL_SECONDS = 300
# A model call has the import's remaining time (D114); qualifying the CLI stays as short as in a connection check.
QUALIFICATION_SECONDS = 15


def _stamp(path):
    try:
        link = path.lstat()
    except FileNotFoundError:
        return None
    try:
        target = path.stat()
    except FileNotFoundError:
        target = None
    return tuple((value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        value.st_mode, value.st_uid) if value is not None else None for value in (link, target))


def preflight_key(executable, profile, fixture):
    try:
        home = profile.home if profile is not None else Path.home()
        codex = profile.codex_home if profile is not None else Path(os.environ.get("CODEX_HOME") or home / ".codex")
        return (str(executable), _stamp(executable), str(home), str(codex.absolute()),
            _stamp(codex / "auth.json"), str(fixture.executable) if fixture is not None else None)
    except OSError:
        return None


@dataclass(frozen=True)
class Snapshot(Generic[ResultT]):
    key: tuple
    result: ResultT
    models: tuple[str, ...]
    expires: float


class PreflightCache(Generic[ResultT]):
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock, self.epoch, self.snapshot = clock, 0, None
        self.lock = threading.Lock()

    def invalidate(self):
        with self.lock:
            self.epoch += 1
            self.snapshot = None

    def read(self, key, model):
        with self.lock:
            saved = self.snapshot
            if (key is not None and saved is not None and saved.key == key
                    and model in saved.models and self.clock() < saved.expires):
                return self.epoch, saved.result
            return self.epoch, None

    def remember(self, epoch, key, result, models):
        with self.lock:
            if key is not None and epoch == self.epoch:
                self.snapshot = Snapshot(key, result, tuple(models), self.clock() + TTL_SECONDS)
