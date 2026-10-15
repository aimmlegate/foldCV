"""Cancellable cross-process ownership of the application-owned native profile."""

from contextlib import contextmanager
import fcntl
import os
import time

from packages.resume_core.project_store import owned_file, strict_json
from packages.resume_core.storage import StorageFailure, private_file, atomic_write
from .inference_admission import AdmissionCancelled, AdmissionTimeout, AdmissionBlocked
from .lifecycle import has_blocked_owned, SpikeError

BLOCKED = ".foldcv-inference-blocked"


def recover_profile(profile, operations_root):
    if profile is None:
        return False
    marker = profile.root / BLOCKED
    if not marker.exists() and not marker.is_symlink():
        return False
    try:
        owned_file(marker, 4096)
        data = strict_json(marker.read_bytes())
        if data != {"schemaVersion": 1, "operationsRoot": str(operations_root.absolute())}:
            return True
        if has_blocked_owned(operations_root):
            return True
        path = profile.root / ".foldcv-inference.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            private_file(path)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            marker.unlink()
            directory = os.open(profile.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            os.close(descriptor)
        return False
    except (StorageFailure, OSError, ValueError, SpikeError):
        return True


@contextmanager
def native_profile(profile, cancel, *, deadline, blocking=True, operations_root=None):
    if profile is None:
        yield
        return
    profile.prepare()
    path = profile.root / ".foldcv-inference.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    acquired = False
    try:
        private_file(path)
        if path.stat().st_nlink != 1:
            raise StorageFailure("UNSAFE_STORAGE")
        while True:
            if (profile.root / BLOCKED).exists() or (profile.root / BLOCKED).is_symlink():
                raise AdmissionBlocked()
            if cancel.is_set():
                raise AdmissionCancelled()
            if time.monotonic() >= deadline:
                raise AdmissionTimeout()
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                if (profile.root / BLOCKED).exists() or (profile.root / BLOCKED).is_symlink():
                    raise AdmissionBlocked()
                break
            except BlockingIOError:
                if not blocking:
                    raise AdmissionTimeout() from None
                cancel.wait(0.025)
        try:
            yield
        except BaseException as error:
            if getattr(error, "code", None) in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "AGENT_CLEANUP_FAILED"}:
                import json
                try:
                    atomic_write(profile.root / BLOCKED, json.dumps({"schemaVersion": 1,
                        "operationsRoot": str(operations_root.absolute()) if operations_root is not None else None}).encode())
                except (StorageFailure, OSError):
                    pass
            raise
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
