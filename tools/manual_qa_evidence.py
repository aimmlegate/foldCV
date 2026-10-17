"""Current repair evidence stays separate from retained NB native acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from tools.background_evidence import assert_report, source_hashes

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs/gui/handoffs/MANUAL-QA-REPAIR"
HISTORICAL_REVISION = "dad17565c05b600b3965c3fad9329ff7b3958390"
CASE_IDS = frozenset("IN01 IN02 IN03 IN04 IN05 FA01 FA02 FA03 FM01 FM02 FM03 FM04 AG01 AG02 AG03 AG04 AG05 AG06 LC01 LC02 LC03 LC04 UI01 DX01 DX02 E2E01 E2E02".split())


def historical_sources(paths: list[str]) -> dict[str, str]:
    return {name: hashlib.sha256(subprocess.check_output(
        ["git", "show", f"{HISTORICAL_REVISION}:{name}"], cwd=ROOT)).hexdigest() for name in paths}


def validate_bindings(value: dict, collected: set[str]) -> dict[str, list[str]]:
    cases = value.get("cases", {})
    if set(cases) != CASE_IDS:
        raise SystemExit("QA bindings must cover exactly all 27 repair cases")
    mapped = {}
    for case_id, case in cases.items():
        nodes = case.get("tests", [])
        if not nodes and not case.get("observations"):
            raise SystemExit(f"QA case has no executable or observation binding: {case_id}")
        for node in nodes:
            if node not in collected:
                raise SystemExit(f"QA mapped test was not collected: {node}")
        if nodes:
            mapped[case_id] = nodes
    return mapped


def current_sources() -> dict[str, str]:
    paths = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    prefixes = ("packages/", "services/api/src/", "apps/web/src/", "apps/web/unit/", "contracts/", "templates/", "tools/", "tests/")
    return source_hashes(sorted({name for name in paths if name.startswith(prefixes)
        and (ROOT / name).is_file() and not (ROOT / name).is_symlink()}))


def validate_execution(path: Path, context: dict, bindings: dict[str, list[str]]) -> dict:
    return assert_report(path, run_id=context["runId"], suite="fast", sources=context["sourceHashes"],
        started_at=context["startedAt"], bindings=bindings, required_traces={}, required_actions=set(), required_orders=set())


def validate_observation(record: dict, expected_sources: dict[str, str], root: Path = ROOT) -> None:
    if record.get("status") != "passed" or record.get("sourceHashes") != expected_sources:
        raise SystemExit("QA observation is missing, pending or source-stale")
    artifacts = record.get("artifacts", {})
    if not artifacts:
        raise SystemExit("QA observation has no retained evidence")
    for name, checksum in artifacts.items():
        path = root / name
        if (not path.resolve().is_relative_to(root.resolve()) or path.is_symlink()
                or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum):
            raise SystemExit("QA observation artifact is missing, unsafe or changed")
