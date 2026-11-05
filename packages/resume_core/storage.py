"""Private data-root and atomic file primitives reused by local settings/projects."""

from __future__ import annotations

import json

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

from . import host


class StorageFailure(Exception):
    pass


def data_root(override: Path | None = None) -> Path:
    return (override if override is not None else
            Path.home() / "Library/Application Support/FoldCV").absolute()


def private_directory(path: Path) -> Path:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise StorageFailure("UNSAFE_STORAGE")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir() or not host.owned(path.stat()):
        raise StorageFailure("UNSAFE_STORAGE")
    path.chmod(0o700)
    return path


def private_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or not host.owned(path.stat()):
        raise StorageFailure("UNSAFE_STORAGE")
    if not host.private_mode(path.stat(), 0o600):
        raise StorageFailure("UNSAFE_STORAGE")


@contextmanager
def locked_root(root: Path, name: str):
    private_directory(root)
    path = root / name
    if path.is_symlink():
        raise StorageFailure("UNSAFE_STORAGE")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | host.O_NOFOLLOW | host.O_BINARY, 0o600)
    try:
        private_file(path)
        host.lock(fd)
        yield
    finally:
        host.unlock(fd)
        os.close(fd)


def atomic_write(path: Path, content: bytes, *, after_replace=None) -> None:
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
        host.replace(temp, path)
        if after_replace is not None:
            after_replace()
        host.sync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


class ProjectStoreFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def invalid(_value):
        raise ValueError("invalid constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def owned_file(path, limit=MAX_SNAPSHOT_BYTES):
    if any(parent.is_symlink() for parent in path.parents):
        raise StorageFailure("UNSAFE_STORAGE")
    private_file(path)
    if path.stat().st_nlink != 1 or path.stat().st_size > limit:
        raise StorageFailure("UNSAFE_STORAGE")


class RepositoryFailure(Exception):
    """A refused repository operation; `code` is a public error code, `details` go into the reply body."""

    def __init__(self, code, **details):
        self.code = code
        self.details = details
        super().__init__(code)
