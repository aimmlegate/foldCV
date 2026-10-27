"""Reuse the reviewed POSIX operation lock, reaper and process-tree cleanup."""

from __future__ import annotations

from contextlib import contextmanager
import gc
import json
import platform
from pathlib import Path
import re
import subprocess
import sys

from spikes.cli.runner import SpikeError, cleanup_intent_ids, operation, reap_owned as spike_reap_owned, safe_environment, stop_group, strict_json


OWNER = "foldcv-service-v1"


# D108: collections of the long-lived project objects were 35-40 % of an edit; freeze them and collect less often.
GC_THRESHOLD = (50000, 20, 20)


def tune_garbage_collector() -> tuple[int, int, int]:
    """Freeze what startup allocated and raise the thresholds; returns the previous thresholds."""
    previous = gc.get_threshold()
    gc.collect()
    gc.freeze()
    gc.set_threshold(*GC_THRESHOLD)
    return previous


def require_supported_host() -> None:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("Local service process cleanup supports macOS arm64 only")


def reap_owned(root: Path) -> int:
    return spike_reap_owned(root, owner=OWNER)


def has_blocked_owned(root: Path) -> bool:
    if cleanup_intent_ids(root, owner=OWNER):
        return True
    try:
        for path in root.iterdir():
            if path.is_symlink() or not path.is_dir() or not re.fullmatch(r"op-[0-9a-f]{32}", path.name):
                continue
            marker, lock, blocked = path / ".owner", path / ".lock", path / ".cleanup-blocked"
            if any(item.is_symlink() for item in (marker, lock, blocked)):
                continue
            try:
                if not marker.is_file() or not lock.is_file() or not blocked.is_file() or marker.stat().st_size > 256:
                    continue
                if strict_json(marker.read_bytes()) == {"owner": OWNER, "id": path.name[3:]}:
                    return True
            except (OSError, SpikeError):
                continue
    except OSError:
        raise SpikeError("TEMP_FAILED") from None
    return False


class OperationFiles:
    def __init__(self, root: Path):
        self.root = root
        self.path: Path | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.closed = False
        self.cleanup_failed = False

    def spawn(self, executable: Path, arguments: tuple[str, ...], *, capture: bool = True,
              environment: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
        """Start one test worker with an ambiguous crash marker before Popen."""
        if self.closed or self.path is None or self.process is not None:
            raise RuntimeError("Operation has no free worker slot")
        marker = self.path / ".worker"
        marker.write_text('{"state":"spawning"}', encoding="utf-8")
        try:
            process = subprocess.Popen([str(executable), *arguments], cwd=self.path,
                                       env=environment if environment is not None else safe_environment(self.path),
                                       stdin=subprocess.PIPE if capture else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                       stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
                                       start_new_session=True, shell=False)
        except Exception:
            marker.unlink(missing_ok=True)
            raise
        self.process = process
        marker.write_text(json.dumps({"pid": process.pid}), encoding="utf-8")
        return process

    def stop_worker(self, *, final: bool = True) -> None:
        if final:
            self.closed = True
        if self.cleanup_failed:
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        process = self.process
        if process is None:
            return
        try:
            try:
                stop_group(process)
            except SpikeError:
                self.cleanup_failed = True
                self.closed = True
                raise
            except OSError:
                self.cleanup_failed = True
                self.closed = True
                raise SpikeError("PROCESS_CLEANUP_FAILED") from None
            try:
                if self.path is not None:
                    (self.path / ".worker").unlink(missing_ok=True)
            except OSError:
                self.cleanup_failed = True
                self.closed = True
                raise SpikeError("CLEANUP_FAILED") from None
            self.process = None
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass

    @contextmanager
    def open(self):
        with operation(self.root, owner=OWNER) as directory:
            self.path = directory
            try:
                yield self
            finally:
                try:
                    self.stop_worker()
                except SpikeError:
                    raise
                finally:
                    self.path = None
                    self.process = None
