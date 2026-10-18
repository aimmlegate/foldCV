"""Current repair evidence stays separate from retained NB native acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import os
import tarfile
import tempfile

from tools.background_evidence import assert_report, source_hashes

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs/gui/handoffs/MANUAL-QA-REPAIR"
HISTORICAL_REVISION = "dad17565c05b600b3965c3fad9329ff7b3958390"
CASE_IDS = frozenset("IN01 IN02 IN03 IN04 IN05 FA01 FA02 FA03 FM01 FM02 FM03 FM04 AG01 AG02 AG03 AG04 AG05 AG06 LC01 LC02 LC03 LC04 UI01 DX01 DX02 E2E01 E2E02".split())


def observe_provider_generation(provider, wrap):
    if not getattr(provider, "_manual_qa_observed", False):
        provider._generate = wrap(provider._generate)
        provider._manual_qa_observed = True
    return provider


def historical_sources(paths: list[str]) -> dict[str, str]:
    return {name: hashlib.sha256(subprocess.check_output(
        ["git", "show", f"{HISTORICAL_REVISION}:{name}"], cwd=ROOT)).hexdigest() for name in paths}


def validate_retained_native(spec: dict) -> list[str]:
    historical = json.loads(subprocess.check_output(["git", "show",
        f"{HISTORICAL_REVISION}:tests/requirements.json"], cwd=ROOT))["backgroundExecution"]
    if spec["nativeBindings"] != historical["nativeBindings"] or spec["sources"] != historical["sources"]:
        raise SystemExit("Historical native bindings or source inventory changed")
    git_dir = subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip()
    with tempfile.TemporaryDirectory(prefix="foldcv-retained-native-") as folder:
        retained = Path(folder).resolve()
        with tempfile.TemporaryFile() as archive:
            subprocess.run(["git", "archive", "--format=tar", HISTORICAL_REVISION], cwd=ROOT,
                stdout=archive, check=True)
            archive.seek(0)
            with tarfile.open(fileobj=archive) as files:
                files.extractall(retained, filter="data")
        # The original guard also checks milestone-critical files and Git objects.
        env = {**os.environ, "GIT_DIR": git_dir,
            "PYTHONPATH": str(retained / "services/api/src") + os.pathsep + str(retained)}
        result = subprocess.run([str(ROOT / ".venv/bin/python"), "-c",
            "import json; from tools.checks import background_spec; print(json.dumps(background_spec()['pendingNative']))"],
            cwd=retained, env=env, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)


def validate_bindings(value: dict, collected: set[str]) -> dict[str, list[str]]:
    cases = value.get("cases", {})
    if set(cases) != CASE_IDS:
        raise SystemExit("QA bindings must cover exactly all 27 repair cases")
    mapped = {}
    for case_id, case in cases.items():
        nodes = case.get("tests", [])
        if not nodes and not case.get("observations"):
            raise SystemExit(f"QA case has no executable or observation binding: {case_id}")
        expanded = set()
        for node in nodes:
            matches = {item for item in collected if item == node or item.partition("[")[0] == node}
            if not matches:
                raise SystemExit(f"QA mapped test was not collected: {node}")
            expanded.update(matches)
        if nodes:
            mapped[case_id] = sorted(expanded)
    return mapped


def current_sources() -> dict[str, str]:
    paths = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    prefixes = ("packages/", "services/api/src/", "apps/web/src/", "apps/web/unit/", "contracts/", "templates/", "tools/", "tests/")
    return source_hashes(sorted({name for name in paths if name.startswith(prefixes)
        and (ROOT / name).is_file() and not (ROOT / name).is_symlink()}))


def validate_execution(path: Path, context: dict, bindings: dict[str, list[str]]) -> dict:
    return assert_report(path, run_id=context["runId"], suite="fast", sources=context["sourceHashes"],
        started_at=context["startedAt"], bindings=bindings, required_traces={}, required_actions=set(), required_orders=set(),
        binding_scope="manual-qa")


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
