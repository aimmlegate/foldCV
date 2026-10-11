"""Frozen recovery clock; the older fixture clock remains unchanged."""

from datetime import date, datetime, timezone

from tests.support.foundation import FrozenClock


RECOVERY_CLOCK = FrozenClock(date(2026, 10, 11), datetime(2026, 10, 11, 12, tzinfo=timezone.utc))


def assert_e2_claims(claims: list[dict[str, object]]) -> None:
    """Fixed evidence oracle; this does not parse source number words."""
    from pathlib import Path
    import json

    fixture_root = Path(__file__).resolve().parents[1] / "fixtures/recovery"
    expected = json.loads((fixture_root / "expected.json").read_text())["examples"]["E2"]["claims"]
    assert claims == expected, "controlled example E2 evidence differs from the frozen oracle"
    source = (fixture_root / "E2.txt").read_text()
    assert all(claim["span"] in source for claim in expected)
