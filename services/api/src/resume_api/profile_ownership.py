"""Cancellable cross-process ownership of the application-owned native profile."""

from contextlib import contextmanager
import fcntl
import json
import os
import re
import time

from packages.resume_core.project_store import owned_file, strict_json
from packages.resume_core.storage import StorageFailure, private_file, atomic_write
from .inference_admission import AdmissionCancelled, AdmissionTimeout, AdmissionBlocked
from .lifecycle import has_blocked_owned, SpikeError

BLOCKED = ".foldcv-inference-blocked"
SHARED = ".foldcv-shared-server-v1"


def process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class SharedOwnership:
    def __init__(self, marker, operations_root):
        self.marker, self.root = marker, operations_root
        self.pending, self.hosts = 0, set()
        self.save()

    def save(self):
        atomic_write(self.marker, json.dumps({"schemaVersion": 2, "operationsRoot": str(self.root.absolute()),
            "hostState": "unverified" if self.pending else "verified", "hostPids": sorted(self.hosts)}).encode())

    def thread_pending(self):
        self.pending += 1
        self.save()

    def thread_ready(self, hosts):
        self.hosts.update(hosts)
        self.pending -= 1
        self.save()

    def generation_closed(self, hosts):
        if any(process_alive(pid) for pid in hosts):
            raise SpikeError("CLEANUP_FAILED")
        self.hosts.difference_update(hosts)
        self.save()

    def verify_closed(self):
        if self.pending or any(process_alive(pid) for pid in self.hosts):
            raise SpikeError("CLEANUP_FAILED")


def shared_operations_pending(root):
    if root.is_symlink():
        return True
    return root.exists() and any(re.fullmatch(r"op-[0-9a-f]{32}", item.name) for item in root.iterdir())


def recover_profile(profile, operations_root):
    if profile is None:
        return False
    marker = profile.root / BLOCKED
    shared = profile.root / SHARED
    records = [path for path in (marker, shared) if path.exists() or path.is_symlink()]
    if not records:
        return False
    try:
        for path in records:
            owned_file(path, 4096)
            record = strict_json(path.read_bytes())
            expected = {"schemaVersion": 1, "operationsRoot": str(operations_root.absolute())}
            if path == shared and isinstance(record, dict) and record.get("schemaVersion") == 2:
                if (set(record) != {"schemaVersion", "operationsRoot", "hostState", "hostPids"}
                        or record["operationsRoot"] != expected["operationsRoot"] or record["hostState"] != "verified"
                        or not isinstance(record["hostPids"], list) or len(record["hostPids"]) > 8
                        or any(type(pid) is not int or not 1 < pid < 2**31 or process_alive(pid) for pid in record["hostPids"])):
                    return True
            elif record != expected:
                return True
        if has_blocked_owned(operations_root) or shared in records and shared_operations_pending(operations_root):
            return True
        path = profile.root / ".foldcv-inference.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            private_file(path)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for path in records:
                path.unlink()
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
                if (profile.root / SHARED).exists() or (profile.root / SHARED).is_symlink():
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


@contextmanager
def shared_profile(profile, cancel, *, deadline, operations_root):
    with native_profile(profile, cancel, deadline=deadline, blocking=False, operations_root=operations_root):
        marker = profile.root / SHARED
        ownership = SharedOwnership(marker, operations_root)
        yield ownership
        ownership.verify_closed()
        if has_blocked_owned(operations_root) or shared_operations_pending(operations_root):
            raise SpikeError("CLEANUP_FAILED")
        marker.unlink()
        directory = os.open(profile.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
