"""Qualify a user-installed CLI by publisher signature and a version table, not by exact pins."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Literal


Status = Literal["supported", "graceful", "unsupported", "broken"]
_VERSION = re.compile(r"(?:^|\s)v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\s|$)")


class QualificationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, order=False)
class Version:
    major: int
    minor: int
    patch: int
    pre: tuple[int | str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> "Version":
        """Read `2.1.308 (Claude Code)` or `codex-cli 0.163.0-alpha.11.1`."""
        match = _VERSION.search(text.strip())
        if match is None:
            raise QualificationError("CLI_UNSUPPORTED")
        pre = tuple(int(part) if part.isdigit() else part
                    for part in (match.group(4) or "").split(".") if part)
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), pre)

    def key(self) -> tuple:
        # Semver: a pre-release sorts before its release; numeric parts sort before text parts.
        pre = tuple((0, part, "") if isinstance(part, int) else (1, 0, part) for part in self.pre)
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, pre)

    def __lt__(self, other: "Version") -> bool:
        return self.key() < other.key()

    def __le__(self, other: "Version") -> bool:
        return self.key() <= other.key()

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        return core + ("-" + ".".join(map(str, self.pre)) if self.pre else "")


@dataclass(frozen=True)
class Compatibility:
    floor: str
    last_tested: str
    broken: tuple[str, ...] = ()

    def status(self, version: Version) -> Status:
        if any(version.key() == Version.parse(item).key() for item in self.broken):
            return "broken"
        if version < Version.parse(self.floor):
            return "unsupported"
        return "supported" if version <= Version.parse(self.last_tested) else "graceful"


@dataclass(frozen=True)
class Signature:
    team_id: str
    identifier: str


_SIGNATURES: dict[tuple, Signature] = {}


def resolve(executable: Path) -> Path:
    resolved = Path(os.path.realpath(executable))
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise QualificationError("CLI_MISSING")
    return resolved


def signature(executable: Path, *, codesign: Path = Path("/usr/bin/codesign")) -> Signature:
    """Strictly verify the code signature of the resolved binary and read its publisher."""
    resolved = resolve(executable)
    info = resolved.stat()
    key = (str(resolved), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if key in _SIGNATURES:
        return _SIGNATURES[key]
    try:
        subprocess.run([str(codesign), "--verify", "--strict", str(resolved)], check=True,
                       capture_output=True, timeout=60, env={"PATH": os.defpath})
        shown = subprocess.run([str(codesign), "-d", "--verbose=2", str(resolved)], check=True,
                               capture_output=True, timeout=60, env={"PATH": os.defpath})
    except (OSError, subprocess.SubprocessError):
        raise QualificationError("CLI_UNSUPPORTED") from None
    fields = dict(line.split("=", 1) for line in shown.stderr.decode("utf-8", "replace").splitlines()
                  if "=" in line)
    team, identifier = fields.get("TeamIdentifier", ""), fields.get("Identifier", "")
    if not re.fullmatch(r"[A-Z0-9]{10}", team) or not identifier:
        raise QualificationError("CLI_UNSUPPORTED")
    _SIGNATURES[key] = Signature(team, identifier)
    return _SIGNATURES[key]


def require_publisher(executable: Path, team_id: str, identifier: str) -> Path:
    found = signature(executable)
    if found.team_id != team_id or found.identifier != identifier:
        raise QualificationError("CLI_UNSUPPORTED")
    return resolve(executable)


def missing_flags(help_text: str, required: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(flag for flag in required
                 if not re.search(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])", help_text))
