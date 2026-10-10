"""Deterministic test inputs; these helpers are not runtime providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
import random
from typing import Callable


FROZEN_DATE = date(2026, 10, 10)
FROZEN_INSTANT = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
FIXTURE_SEED = 20261010


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
