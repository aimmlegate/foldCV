"""Reuse the reviewed POSIX operation lock, reaper and process-tree cleanup."""

from __future__ import annotations

from contextlib import contextmanager
import json
import platform
from pathlib import Path
import subprocess
import sys

from spikes.cli.runner import SpikeError, operation, reap_owned as spike_reap_owned, safe_environment, stop_group


OWNER = "foldcv-service-v1"


def require_supported_host() -> None:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("Local service process cleanup supports macOS arm64 only")


def reap_owned(root: Path) -> int:
    return spike_reap_owned(root, owner=OWNER)


class OperationFiles:
    def __init__(self, root: Path):
        self.root = root
        self.path: Path | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.closed = False

    def spawn(self, executable: Path, arguments: tuple[str, ...]) -> subprocess.Popen[bytes]:
        """Start one test worker with an ambiguous crash marker before Popen."""
        if self.closed or self.path is None or self.process is not None:
            raise RuntimeError("Operation has no free worker slot")
        marker = self.path / ".worker"
        marker.write_text('{"state":"spawning"}', encoding="utf-8")
        try:
            process = subprocess.Popen([str(executable), *arguments], cwd=self.path,
                                       env=safe_environment(self.path),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True, shell=False)
        except Exception:
            marker.unlink(missing_ok=True)
            raise
        self.process = process
        marker.write_text(json.dumps({"pid": process.pid}), encoding="utf-8")
        return process

    def stop_worker(self) -> None:
        self.closed = True
        process = self.process
        if process is None:
            return
        try:
            stop_group(process)
            if self.path is not None:
                (self.path / ".worker").unlink(missing_ok=True)
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
