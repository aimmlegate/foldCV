"""What differs between macOS, the reviewed platform, and Windows, where the desktop zip runs.

On Windows the per-user profile ACL of %LOCALAPPDATA% stands in for the POSIX owner and mode checks, and Job
Objects (`winjob`) stand in for process groups and for sandbox-exec's process rules.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

WINDOWS = sys.platform == "win32"
# os.open is text mode on Windows unless O_BINARY: os.write would turn every \n byte into \r\n.
O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
# Antivirus scans and readers hold new files for a moment; Windows then refuses to replace or delete them.
RETRY_SECONDS = 2.0

if WINDOWS:
    import msvcrt
else:
    import fcntl


@dataclass(frozen=True)
class Confined:
    """A Windows launch: the program and its Job Object limits, where macOS runs sandbox-exec with a policy."""

    program: Path
    children: int = 0  # other processes it may start inside its job
    breakaway: bool = False  # what it starts leaves the job, as the browser of a sign-in must
    memory: int | None = None  # committed bytes per process
    cpu_seconds: int | None = None  # user-mode CPU time per process

    def __str__(self) -> str:
        return str(self.program)


def owned(info: os.stat_result) -> bool:
    return WINDOWS or info.st_uid == os.getuid()


def private_mode(info: os.stat_result, mode: int) -> bool:
    """The exact POSIX mode (0o700 directories, 0o600 files); Windows has no mode bits to check."""
    return WINDOWS or stat.S_IMODE(info.st_mode) == mode


def shared_mode(info: os.stat_result) -> bool:
    return not WINDOWS and bool(info.st_mode & 0o077)


def sync_directory(path: Path) -> None:
    """Make a rename durable. NTFS journals its metadata, and Windows cannot open a directory to fsync it."""
    if WINDOWS:
        return
    descriptor = os.open(path, os.O_RDONLY | O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def lock(descriptor: int, *, blocking: bool = True) -> None:
    """Exclusive lock of an open lock file; BlockingIOError when not blocking and another holder has it."""
    if not WINDOWS:
        fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return
    while True:
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EDEADLOCK):
                raise
            if not blocking:
                raise BlockingIOError(errno.EWOULDBLOCK, "locked") from None
        time.sleep(0.02)


def unlock(descriptor: int) -> None:
    if not WINDOWS:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass  # Not held; flock(LOCK_UN) does not fail either.


def process_alive(pid: int) -> bool:
    if WINDOWS:
        from . import winjob
        return winjob.process_alive(pid)
    try:
        os.kill(pid, 0)  # On Windows this would end the process.
    except ProcessLookupError:
        return False
    return True


def resident_kb(process: subprocess.Popen) -> int | None:
    """The child's resident memory in KiB, None when it cannot be read."""
    if WINDOWS:
        from . import winjob
        return winjob.working_set_kb(process)
    try:
        result = subprocess.run(("/bin/ps", "-o", "rss=", "-p", str(process.pid)), capture_output=True,
                                timeout=0.5, check=False, text=True)
        return int(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip().isdigit() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _retry(action):
    deadline = time.monotonic() + RETRY_SECONDS
    while True:
        try:
            return action()
        except PermissionError:
            if not WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def replace(source: Path, target: Path) -> None:
    _retry(lambda: os.replace(source, target))


def remove_tree(path: Path) -> None:
    def writable(function, name, _error):
        # Windows refuses to delete read-only files, which some archives contain.
        os.chmod(name, stat.S_IWRITE)
        function(name)

    _retry(lambda: shutil.rmtree(path, onexc=writable if WINDOWS else None))


def windows_environment(temp: Path, home: Path) -> dict[str, str]:
    """What Windows programs need to run, with home, temp and app data inside FoldCV's own directories."""
    system = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    environment = {"SystemRoot": system, "WINDIR": system, "SystemDrive": os.environ.get("SystemDrive", "C:"),
                   "PATH": rf"{system}\System32;{system};{system}\System32\Wbem", "PATHEXT": ".COM;.EXE;.BAT;.CMD",
                   "COMSPEC": rf"{system}\System32\cmd.exe", "OS": "Windows_NT", "LANG": "en_US.UTF-8",
                   "TEMP": str(temp), "TMP": str(temp), "HOME": str(home), "USERPROFILE": str(home),
                   "APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local")}
    for name in ("NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "USERNAME", "USERDOMAIN", "COMPUTERNAME"):
        if os.environ.get(name):
            environment[name] = os.environ[name]
    return environment
