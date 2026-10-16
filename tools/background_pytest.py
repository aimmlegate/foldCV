"""Pytest phase reporter, activated only by the existing runner's private context."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

_report = None
_path = None


def pytest_sessionstart(session):
    global _report, _path
    context = os.environ.get("FOLDCV_BACKGROUND_CONTEXT")
    if context is None:
        return
    from packages.resume_core.storage import atomic_write
    value = json.loads(Path(context).read_text())
    _path = Path(value.pop("reportPath"))
    _report = {**value, "schemaVersion": 1, "finishedAt": "", "complete": False, "exitStatus": -1,
        "collected": [], "records": [], "traces": []}
    atomic_write(_path, json.dumps(_report).encode())


def pytest_collection_finish(session):
    if _report is not None:
        _report["collected"] = [item.nodeid for item in session.items]


def pytest_runtest_logreport(report):
    if _report is None:
        return
    records = _report["records"]
    current = records[-1] if records and records[-1]["nodeId"] == report.nodeid else None
    if current is None or report.when in current["phases"]:
        attempt = 1 + sum(item["nodeId"] == report.nodeid for item in records)
        current = {"nodeId": report.nodeid, "phases": {}, "markers": [], "attempt": attempt}
        records.append(current)
    current["phases"][report.when] = report.outcome
    if getattr(report, "wasxfail", None) is not None:
        current["markers"].append("xpass" if report.outcome == "passed" else "xfail")
    if getattr(report, "rerun", 0):
        current["markers"].append("rerun")


@pytest.fixture
def background_evidence(request):
    def record(trace):
        if _report is not None:
            from tools.background_evidence import digest
            _report["traces"].append({**trace, "nodeId": request.node.nodeid, "sha256": digest(trace)})
    return record


def pytest_sessionfinish(session, exitstatus):
    if _report is not None:
        from packages.resume_core.storage import atomic_write
        _report.update(complete=True, exitStatus=int(exitstatus), finishedAt=datetime.now(timezone.utc).isoformat())
        atomic_write(_path, json.dumps(_report, ensure_ascii=False, indent=2).encode() + b"\n")
