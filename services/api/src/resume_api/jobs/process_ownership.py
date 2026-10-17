"""Check process birth and operation ownership before each cleanup signal."""

import ctypes
from dataclasses import dataclass
import errno
import os
from pathlib import Path
import signal
import subprocess
import time

from spikes.cli.runner import group_members
from ..lifecycle import SpikeError


class BsdInfo(ctypes.Structure):
    # Darwin sys/proc_info.h, PROC_PIDTBSDINFO; names are never exposed.
    _fields_ = [("words", ctypes.c_uint32 * 12), ("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32),
        ("nfiles", ctypes.c_uint32), ("group", ctypes.c_uint32), ("job", ctypes.c_uint32),
        ("tty", ctypes.c_uint32), ("tty_group", ctypes.c_uint32), ("nice", ctypes.c_int32),
        ("seconds", ctypes.c_uint64), ("microseconds", ctypes.c_uint64)]


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    parent: int
    group: int
    uid: int
    seconds: int
    microseconds: int

    def same_process(self, other):
        # A known child can be reparented after its leader exits.
        return (other is not None and (self.pid, self.group, self.uid, self.seconds, self.microseconds)
            == (other.pid, other.group, other.uid, other.seconds, other.microseconds))


class ProcessInspector:
    def __init__(self):
        self.library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        self.library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self.library.proc_pidinfo.restype = ctypes.c_int
        if ctypes.sizeof(BsdInfo) != 136:
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        self.identity(os.getpid())

    def identity(self, pid):
        value = BsdInfo()
        ctypes.set_errno(0)
        count = self.library.proc_pidinfo(pid, 3, 0, ctypes.byref(value), ctypes.sizeof(value))
        if count == 0 and ctypes.get_errno() == errno.ESRCH:
            return None
        if count != ctypes.sizeof(value) or value.words[3] != pid:
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        return ProcessIdentity(pid, value.words[4], value.group, value.words[5], value.seconds, value.microseconds)


class OwnedProcess:
    def __init__(self, process, files, inspector, *, clock=time.monotonic, pause=time.sleep):
        self.process, self.files, self.inspector = process, files, inspector
        self.clock, self.pause = clock, pause
        self.directory = Path(files.path)
        self.marker = (self.directory / ".owner").read_bytes()
        self.leader = inspector.identity(process.pid)
        if (self.leader is None or self.leader.parent != os.getpid() or self.leader.group != process.pid
                or self.leader.uid != os.getuid()):
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        self.known = {process.pid: self.leader}

    def check(self):
        marker = self.directory / ".owner"
        if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != self.marker:
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        current = self.inspector.identity(self.process.pid)
        if current is not None and not self.leader.same_process(current):
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        members = []
        for pid in group_members(self.process.pid):
            identity = self.inspector.identity(pid)
            if identity is None:
                continue
            if identity.uid != self.leader.uid or identity.group != self.leader.group:
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            if self.leader.same_process(current):
                self.known.setdefault(pid, identity)
            if pid not in self.known or not self.known[pid].same_process(identity):
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            members.append(identity)
        return current, members

    def signal(self, sig):
        current, members = self.check()
        if not members:
            return
        if self.leader.same_process(current):
            try:
                os.killpg(self.process.pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                self.signal_members(sig, self.check()[1])
        else:
            self.signal_members(sig, members)

    def signal_members(self, sig, members):
        for member in members:
            if not member.same_process(self.inspector.identity(member.pid)):
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            try:
                os.kill(member.pid, sig)
            except ProcessLookupError:
                pass

    def stop_verified_process(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            self.signal(sig)
            deadline = self.clock() + .05
            try:
                self.process.wait(timeout=.05)
            except subprocess.TimeoutExpired:
                pass
            # A dead leader does not end the host's SIGTERM grace.
            if sig == signal.SIGTERM and (remaining := deadline - self.clock()) > 0:
                self.pause(remaining)
        deadline = self.clock() + 1.5
        while self.check()[1]:
            if self.clock() >= deadline:
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            self.signal(signal.SIGKILL)
            self.pause(.01)
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            raise SpikeError("PROCESS_CLEANUP_FAILED") from None

    def stop_worker(self, *, final=True):
        if final:
            self.files.closed = True
        if self.files.cleanup_failed:
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        if self.files.process is None:
            return
        try:
            self.stop_verified_process()
            (self.directory / ".worker").unlink(missing_ok=True)
            self.files.process = None
        except (OSError, SpikeError):
            self.files.cleanup_failed = True
            self.files.closed = True
            raise SpikeError("PROCESS_CLEANUP_FAILED") from None
        finally:
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()


class GuardedPipe:
    def __init__(self, pipe, inspector):
        self.pipe, self.inspector, self.ownership = pipe, inspector, None
        self.quarantined_process = None
        spawn = pipe.files.spawn
        def owned_spawn(*args, **kwargs):
            try:
                process = spawn(*args, **kwargs)
                self.ownership = OwnedProcess(process, pipe.files, inspector)
            except BaseException:
                if pipe.files.process is not None:
                    self.quarantined_process = pipe.files.process
                    pipe.files.cleanup_failed = pipe.files.closed = True
                    pipe.files.stop_worker = self.stop_quarantined
                raise
            pipe.files.stop_worker = self.ownership.stop_worker
            return process
        pipe.files.spawn = owned_spawn

    def stop_quarantined(self, *, final=True):
        # Missing birth evidence cannot fall back to process-group signals.
        for stream in (self.quarantined_process.stdin, self.quarantined_process.stdout, self.quarantined_process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    def __getattr__(self, name):
        return getattr(self.pipe, name)

    async def start(self):
        await self.pipe.start()
        return self


def guard_server(server):
    from spikes.background.appserver_driver import invoke
    if getattr(server, "process_ownership_guard", False):
        return server
    inspector = ProcessInspector()
    factory, verify_host = server.pipe_factory, server.verify_host
    server.pipe_factory = lambda: GuardedPipe(factory(), inspector)
    async def verified_hosts(pipe):
        result = await invoke(verify_host, pipe)
        pipe.ownership.check()
        return result
    server.verify_host = verified_hosts
    server.process_ownership_guard = True
    return server
