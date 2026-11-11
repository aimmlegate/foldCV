"""Short-lived metadata reuse scoped to the CLI and credential-file identity."""

from contextlib import contextmanager
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import threading
import time
from typing import Callable, Generic, TypeVar

from resume_api.inference_admission import INFERENCE, AdmissionTimeout
from resume_api.lifecycle import OperationFiles


ResultT = TypeVar("ResultT")
TTL_SECONDS = 300
# A model call has the import's remaining time (D114); qualifying the CLI inside one is bounded on its own. One
# qualification runs at a time (D153), and on a loaded machine its five probe processes took over 15 s together.
QUALIFICATION_SECONDS = 60
# R4 of D158: this long before a snapshot ends, a qualification starts beside the calls, which keep the snapshot until
# the new one replaces it.
RENEW_SECONDS = QUALIFICATION_SECONDS
LOG = logging.getLogger(__name__)


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
    def __init__(self, clock: Callable[[], float] = time.monotonic, *, held: Callable[[], bool] = lambda: False):
        self.clock, self.epoch, self.snapshot = clock, 0, None
        # While held(), an import holds its permit and the snapshot does not end (R4); a sign-in, a CLI change and an
        # auth failure still drop it.
        self.held = held
        self.lock = threading.Lock()
        # Held by the one call that qualifies the CLI while the snapshot is empty or stale; the others wait for it.
        self.qualifying = threading.Lock()
        # The snapshot a qualification beside the calls renewed, and that qualification's thread.
        self.renewed, self.renewing = None, None

    def invalidate(self):
        with self.lock:
            self.epoch += 1
            self.snapshot = None

    def read(self, key, model):
        with self.lock:
            saved = self.snapshot
            if (key is not None and saved is not None and saved.key == key
                    and model in saved.models and (self.clock() < saved.expires or self.held())):
                return self.epoch, saved.result
            return self.epoch, None

    def remember(self, epoch, key, result, models):
        with self.lock:
            if key is not None and epoch == self.epoch:
                self.snapshot = Snapshot(key, result, tuple(models), self.clock() + TTL_SECONDS)

    def renew(self, qualify):
        """Start `qualify(epoch)` in a thread of its own when the snapshot ends within RENEW_SECONDS, once per snapshot.
        It remembers the new snapshot; one that fails leaves the old one until it ends."""
        with self.lock:
            saved = self.snapshot
            if saved is None or saved is self.renewed or self.clock() < saved.expires - RENEW_SECONDS:
                return
            self.renewed, epoch = saved, self.epoch

        def run():
            try:
                qualify(epoch)
            except Exception as error:  # noqa: BLE001 - the calls go on with the snapshot they have
                LOG.warning("CLI qualification beside the calls failed: %s", getattr(error, "code", type(error).__name__))
        self.renewing = threading.Thread(target=run, name="foldcv-preflight", daemon=True)
        self.renewing.start()


@contextmanager
def beside(root, owner):
    """What a qualification beside the calls runs under (R4): a shared permit, taken only while nothing exclusive holds
    or waits for one (a sign-in, install or check qualifies on its own), a folder of its own under `root` and the
    profile's shared hold `owner(cancel, root)`. A process it could not stop blocks model work."""
    if not INFERENCE.acquire(blocking=False):
        raise AdmissionTimeout()
    files = OperationFiles(root)
    try:
        with files.open(), owner(threading.Event(), root):
            yield files
    except Exception:
        if files.cleanup_failed:
            INFERENCE.block()
        raise
    finally:
        INFERENCE.release()
