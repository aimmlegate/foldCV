"""Local rewrite timings (rewrite_timing): phase totals only, separate per context, bounded, and never fatal."""

import asyncio
import json

import pytest

from resume_api.rewrite_timing import add_phase, rewrite_timing


def test_a_row_keeps_known_phase_totals_and_no_text(tmp_path):
    with rewrite_timing(tmp_path, 1) as timing:
        add_phase("model_turn", .025)
        add_phase("model_turn", .005)
        add_phase("private instruction", 100)
        timing.outcome = "pending"
    raw = (tmp_path / "diagnostics/rewrite-timings.json").read_text()
    row, = json.loads(raw)
    assert set(row) == {"at", "blocks", "outcome", "milliseconds"}
    assert row["outcome"] == "pending" and row["blocks"] == 1
    assert row["milliseconds"]["model_turn"] == 30 and set(row["milliseconds"]) == {"model_turn", "total"}
    assert "private instruction" not in raw
    add_phase("model_turn", 1)
    assert len(json.loads((tmp_path / "diagnostics/rewrite-timings.json").read_text())) == 1


@pytest.mark.asyncio
async def test_concurrent_timing_contexts_and_thread_handoffs_stay_separate(tmp_path):
    async def run(name, seconds):
        root = tmp_path / name
        with rewrite_timing(root, 1):
            await asyncio.sleep(0)
            await asyncio.to_thread(add_phase, "model_turn", seconds)
        return json.loads((root / "diagnostics/rewrite-timings.json").read_text())[0]
    first, second = await asyncio.gather(run("first", .01), run("second", .03))
    assert first["milliseconds"]["model_turn"] == 10
    assert second["milliseconds"]["model_turn"] == 30


def test_timing_retention_is_bounded_and_unwritable_diagnostics_do_not_fail_edits(tmp_path, monkeypatch):
    for index in range(53):
        with rewrite_timing(tmp_path, index):
            pass
    rows = json.loads((tmp_path / "diagnostics/rewrite-timings.json").read_text())
    assert len(rows) == 50 and rows[0]["blocks"] == 3 and rows[-1]["blocks"] == 52
    def failed(*_args):
        raise PermissionError("Unavailable diagnostics")
    monkeypatch.setattr("resume_api.rewrite_timing.atomic_write", failed)
    with rewrite_timing(tmp_path, 1):
        pass
