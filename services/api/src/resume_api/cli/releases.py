"""Managed CLI releases: the newest official release, and the record FoldCV writes next to each installed one.

A runtime directory holds one directory per installed release. FoldCV writes `foldcv-release.json` into it after the
download passed its publisher's checks; later checks compare the files with that record. The release pinned before
updates existed has no record: its hashes in code stand for one."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
from typing import Callable

from .qualification import QualificationError, Version


RECORD = "foldcv-release.json"
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.]+)?")
SHA256 = re.compile(r"[0-9a-f]{64}")
# One binary or archive; the Claude binary was 342 MB and the Codex Windows archive 203 MB on 2026-11-04.
MAX_DOWNLOAD = 1_500_000_000
Fetch = Callable[[str, int], bytes]


class ReleaseFailure(Exception):
    """`download_failed` when a source cannot be read, `invalid_package` when what it says does not check out."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Record:
    version: str
    files: dict[str, str]

    def encode(self) -> bytes:
        return (json.dumps({"version": self.version, "files": self.files}, indent=2, sort_keys=True) + "\n").encode()


def checked_version(value: object) -> str:
    if not isinstance(value, str) or not VERSION.fullmatch(value) or len(value) > 60:
        raise ReleaseFailure("invalid_package")
    return value


def checked_size(value: object) -> int:
    if type(value) is not int or not 0 < value <= MAX_DOWNLOAD:
        raise ReleaseFailure("invalid_package")
    return value


def strict_json(raw: bytes) -> object:
    def refuse(_value):
        raise ValueError("constant")
    try:
        return json.loads(raw.decode("utf-8", "strict"), parse_constant=refuse)
    except ValueError:
        raise ReleaseFailure("invalid_package") from None


def newer(candidate: str | None, current: str | None) -> bool:
    if candidate is None or current is None:
        return False
    try:
        return Version.parse(current) < Version.parse(candidate)
    except QualificationError:
        return False


def _safe_name(name: object) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or len(name) > 200:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and str(path) == name


def read_record(package: Path) -> Record | None:
    path = package / RECORD
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16_384:
            return None
        value = strict_json(path.read_bytes())
    except (OSError, ReleaseFailure):
        return None
    if not isinstance(value, dict) or set(value) != {"version", "files"} or value["version"] != package.name:
        return None
    files = value["files"]
    if (not isinstance(files, dict) or not files or len(files) > 20
            or not all(_safe_name(name) and isinstance(digest, str) and SHA256.fullmatch(digest)
                       for name, digest in files.items())):
        return None
    return Record(package.name, dict(files))


_DIGESTS: dict[tuple, str] = {}
_DIGEST_LOCK = threading.Lock()


def file_digest(path: Path, check: Callable[[], None] = lambda: None) -> str:
    """SHA-256 of a regular file, kept while its identity and times stay the same."""
    info = path.stat()
    key = (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    with _DIGEST_LOCK:
        if key in _DIGESTS:
            return _DIGESTS[key]
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check()
            value.update(chunk)
    with _DIGEST_LOCK:
        _DIGESTS[key] = value.hexdigest()
    return _DIGESTS[key]


@dataclass(frozen=True)
class Runtime:
    """One managed CLI's runtime directory. `entry` is the program inside a release directory, `names` the files
    every check compares with the record; `legacy` stands for the record of the release pinned before updates."""

    root: Path
    entry: str
    names: tuple[str, ...]
    legacy: Record

    def record(self, package: Path) -> Record | None:
        found = read_record(package)
        if found is None and package.name == self.legacy.version and not (package / RECORD).exists():
            found = self.legacy
        if found is None or any(name not in found.files for name in self.names):
            return None
        return found

    def current(self) -> tuple[str, Path] | None:
        """The newest installed release with a record, and its directory."""
        best = None
        try:
            entries = list(os.scandir(self.root))
        except OSError:
            return None
        for item in entries:
            if item.name.startswith(".") or not VERSION.fullmatch(item.name) or not item.is_dir(follow_symlinks=False):
                continue
            package = self.root / item.name
            if self.record(package) is None:
                continue
            version = Version.parse(item.name)
            if best is None or best[0] < version:
                best = (version, package)
        return (best[1].name, best[1]) if best else None

    def executable(self) -> Path:
        """The newest release's program, else where the pinned release would be, so a missing CLI reads as missing."""
        found = self.current()
        return (found[1] if found else self.root / self.legacy.version).joinpath(*PurePosixPath(self.entry).parts)

    def package_of(self, executable: Path) -> Path | None:
        """The release directory whose program `executable` is, when it has a record."""
        depth = len(PurePosixPath(self.entry).parts)
        try:
            package = executable.parents[depth - 1]
        except IndexError:
            return None
        if (package.parent != self.root or package.joinpath(*PurePosixPath(self.entry).parts) != executable
                or package.name.startswith(".")):
            return None
        return package if self.record(package) is not None else None

    def intact(self, package: Path, names: tuple[str, ...] | None = None) -> bool:
        """Every named file is a regular file with the record's hash, and no part of its path is a link."""
        record = self.record(package)
        if record is None:
            return False
        for name in names or self.names:
            path = package.joinpath(*PurePosixPath(name).parts)
            try:
                if (any(part.is_symlink() for part in (path, *path.parents)) or not stat.S_ISREG(path.lstat().st_mode)
                        or file_digest(path) != record.files.get(name)):
                    return False
            except OSError:
                return False
        return True
