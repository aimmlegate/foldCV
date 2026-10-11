"""Private data-root and atomic file primitives reused by local settings/projects."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import tempfile


class StorageFailure(Exception):
    pass


def data_root(override: Path | None = None) -> Path:
    return (override if override is not None else
            Path.home() / "Library/Application Support/FoldCV").absolute()


def private_directory(path: Path) -> Path:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise StorageFailure("UNSAFE_STORAGE")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise StorageFailure("UNSAFE_STORAGE")
    path.chmod(0o700)
    return path


def private_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
        raise StorageFailure("UNSAFE_STORAGE")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise StorageFailure("UNSAFE_STORAGE")


@contextmanager
def locked_root(root: Path, name: str):
    private_directory(root)
    path = root / name
    if path.is_symlink():
        raise StorageFailure("UNSAFE_STORAGE")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        private_file(path)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_write(path: Path, content: bytes) -> None:
    private_directory(path.parent)
    if path.is_symlink():
        raise StorageFailure("UNSAFE_STORAGE")
    fd, temporary = tempfile.mkstemp(prefix=".foldcv-write-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)
