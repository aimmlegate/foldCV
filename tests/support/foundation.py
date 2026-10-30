"""Deterministic test inputs; these helpers are not runtime providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
from pathlib import Path
import random
import subprocess
import sys
from typing import Callable


FROZEN_DATE = date(2026, 10, 10)
FROZEN_INSTANT = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
FIXTURE_SEED = 20261010
ROOT = Path(__file__).resolve().parents[2]
LOCAL_MANIFEST = json.loads((ROOT / "docs/gui/local-version-manifest.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class FrozenClock:
    today: date = FROZEN_DATE
    instant: datetime = FROZEN_INSTANT

    def now(self) -> datetime:
        return self.instant


@dataclass
class CountingContentProvider:
    response: object
    calls: list[tuple[str, object]] = field(default_factory=list)

    def generate(self, operation: str, payload: object) -> object:
        self.calls.append((operation, payload))
        return self.response

    def count(self, operation: str) -> int:
        return sum(name == operation for name, _ in self.calls)


class ForbiddenContentProvider:
    def generate(self, operation: str, payload: object) -> object:
        raise AssertionError(f"unexpected content operation: {operation}")


def isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "foldcv isolated ' Юникод $(literal)"
    root.mkdir()
    return root


def seeded_random() -> random.Random:
    return random.Random(FIXTURE_SEED)


def assert_no_content_calls(action: Callable[[ForbiddenContentProvider], object]) -> object:
    return action(ForbiddenContentProvider())


def run_local(*args: str, python_flags: tuple[str, ...] = (), ready: bool = False,
              env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """`tools/run-local.py` in a child process on the manifest's host; `ready` also passes the frontend and renderer."""
    script = (f"import platform, runpy, sys\n"
              f"platform.system = lambda: 'Darwin'\n"
              f"platform.machine = lambda: {LOCAL_MANIFEST['architecture']!r}\n"
              f"platform.mac_ver = lambda: ({LOCAL_MANIFEST['macos']!r}, (), '')\n"
              f"platform.python_version = lambda: {LOCAL_MANIFEST['python']!r}\n")
    if ready:
        script += "import tools.local_readiness\ntools.local_readiness.check_local = lambda: None\n"
    script += "sys.argv[0] = 'tools/run-local.py'\nrunpy.run_path('tools/run-local.py', run_name='__main__')\n"
    return subprocess.run([sys.executable, *python_flags, "-c", script, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=10)
