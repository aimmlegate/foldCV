"""One local entry point for the same test groups used by CI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.background_evidence import (ExecutionReportV1, assert_report as assert_background_report,
    failure_history, merge_reports, read_report, source_hashes as background_source_hashes)

WEB = ROOT / "apps/web"
PYTHON = ROOT / ".venv/bin/python"
SOFFICE = ROOT / ".tools/LibreOffice.app/Contents/MacOS/soffice"
PYTHON_SUITES = {
    "fast": ["tests/contracts", "tests/core", "tests/draft", "tests/extract", "tests/foundation", "tests/normalize", "tests/service", "tests/devloop", "tests/devloop_antigravity", "tests/recovery", "tests/docx", "skills/format-resume/tests"],
    "integration-render": ["tests/cli_spike", "tests/render_spike", "tests/render"],
}
PROTOTYPE_TESTS = (
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_valid_case",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_source_and_selection_fail_closed",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_missing_source_unit",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_changed_source_bytes",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_changed_extraction_in_both_copies",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_overlapping_months_count_once",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_global_or_undated_technology_has_no_duration",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_invented_dates_are_rejected",
    "skills/format-resume/tests/test_policy.py::PolicyTests::test_cutoff_and_year_precision",
)


def run(argv: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, env=env or safe_env(), text=True, check=True)
    return result.stdout or ""


def safe_env() -> dict[str, str]:
    blocked = ("OPENAI_", "CODEX_", "T3CODE_", "ANTHROPIC_", "GEMINI_", "AZURE_OPENAI_", "MISTRAL_")
    return {key: value for key, value in os.environ.items()
            if not key.startswith(blocked) and key != "GOOGLE_API_KEY"}


def require_python() -> None:
    if not PYTHON.is_file():
        raise SystemExit("Missing .venv; install requirements-dev.txt into project .venv")
    for module in ("pytest", "pytest_cov", "pytest_asyncio", "coverage", "pydantic", "pymupdf", "docx", "PIL", "fastapi", "uvicorn", "httpx"):
        if importlib.util.find_spec(module) is None:
            raise SystemExit(f"Missing Python dependency: {module}; install requirements-dev.txt")


def require_node() -> None:
    run(["node", "--version"], WEB)
    if not (WEB / "node_modules/.bin/tsc").is_file():
        raise SystemExit("Missing web dependencies; run npm ci in apps/web")


def require_converter() -> None:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("Pinned render suite is supported only on macOS arm64")
    if not SOFFICE.is_file():
        raise SystemExit("Missing pinned converter; run tools/install-local-renderer.sh")
    result = subprocess.run([str(SOFFICE), "--version"], cwd=ROOT, env=safe_env(),
                            capture_output=True, text=True, check=True, timeout=15)
    if "26.2.6.3" not in result.stdout:
        raise SystemExit(f"Wrong LibreOffice version: {result.stdout.strip()}")
    for font in sorted((ROOT / "skills/format-resume/assets/fonts").glob("SourceSansPro-*.ttf")):
        installed = ROOT / ".tools/LibreOffice.app/Contents/Resources/fonts/truetype" / font.name
        if not installed.is_file() or font.read_bytes() != installed.read_bytes():
            raise SystemExit(f"Missing or changed app-local font: {font.name}")


def background_spec() -> dict:
    from tools.background_evidence import assert_manual_bindings
    data = json.loads((ROOT / "tests/requirements.json").read_text())
    spec = data["backgroundExecution"]
    report_schema = json.loads((ROOT / spec["reportSchema"]).read_text())
    if report_schema != ExecutionReportV1.model_json_schema():
        raise SystemExit("NB execution report schema drift")
    matrix = json.loads((ROOT / "docs/gui/handoffs/BACKGROUND-WORK/test-matrix.json").read_text())
    due = {v["id"] for c in matrix["cases"] for v in c["requiredVariants"] if v["requiredBy"] in spec["coveredSlices"]}
    manual = {v["id"] for c in matrix["cases"] if c["layers"] == ["t3"] for v in c["requiredVariants"] if v["requiredBy"] in spec["coveredSlices"]}
    if set(spec["bindings"]) != due - manual or not due:
        raise SystemExit("NB matrix due variants do not match execution bindings")
    assert_manual_bindings(spec.get("manualBindings", {}), manual, ROOT)
    matrix_bindings = {b["variant"]: b["nodes"] for c in matrix["cases"] for b in c["testBindings"] if b["suite"] == "fast"}
    if any(matrix_bindings.get(variant) != nodes for variant, nodes in spec["bindings"].items()):
        raise SystemExit("NB matrix executable identities do not match the runner")
    assert_mapped_python_suites([{"tests": [node for nodes in spec["bindings"].values() for node in nodes]}])
    return spec


def background_context(root: Path, suite: str, sources: dict[str, str]) -> dict:
    return {"runId": uuid.uuid4().hex, "suite": suite, "sourceHashes": sources,
        "startedAt": datetime.now(timezone.utc).isoformat(), "reportPath": str(root.resolve() / "execution.json")}


def pytest_group(name: str, evidence_dir: Path | None = None, diagnosis: Path | None = None, *, prepared: dict | None = None) -> None:
    require_python()
    targets = PYTHON_SUITES[name]
    with tempfile.TemporaryDirectory(prefix="foldcv-coverage-") as temp:
        temp_root = Path(temp).resolve()
        env = safe_env()
        env["COVERAGE_FILE"] = str(temp_root / ".coverage")
        arguments = []
        spec = background_spec() if name == "fast" else None
        history = []
        retained = []
        if spec is not None:
            context = prepared["context"] if prepared else background_context(temp_root, name, background_source_hashes(spec["sources"]))
            history_root = ROOT / "tmp/checks-background"
            history = prepared["history"] if prepared else failure_history(history_root, context["sourceHashes"], diagnosis)
            if not prepared and evidence_dir is not None and evidence_dir.parent != history_root:
                history.extend(failure_history(evidence_dir.parent, context["sourceHashes"], diagnosis))
            history = list({item["runId"]: item for item in history}.values())
            retained = [history_root / context["runId"]]
            context_file = temp_root / "context.json"
            context_file.write_text(json.dumps(context))
            python_context = {**context, "reportPath": str(temp_root / "execution-python.json")}
            python_context_file = temp_root / "context-python.json"
            python_context_file.write_text(json.dumps(python_context))
            env["FOLDCV_BACKGROUND_CONTEXT"] = str(python_context_file)
            arguments = ["-p", "tools.background_pytest"]
        if evidence_dir is not None:
            retained.append(evidence_dir)
        for directory in retained:
            if prepared:
                if (directory / "validation.json").exists() or (directory / "context.json").read_bytes() != context_file.read_bytes():
                    raise SystemExit("NB retained context already exists or changed")
            else:
                directory.mkdir(parents=True, exist_ok=False)
            if spec is not None:
                (directory / "context.json").write_bytes(context_file.read_bytes())
        failure = None
        try:
            run([str(PYTHON), "-m", "pytest", "-q", *targets, *arguments, "--cov=packages", "--cov=spikes",
                 "--cov=tools", "--cov=services/api/src/resume_api", "--cov-branch",
                 "--cov-report=term-missing:skip-covered", "--cov-report=json:" + str(temp_root / "branches.json")], env=env)
        except BaseException as error:
            failure = error
        finally:
            if spec is not None and (temp_root / "execution-python.json").is_file():
                raw = [Path(prepared["nodeReport"])] if prepared else []
                merge_reports([*raw, temp_root / "execution-python.json"], Path(context["reportPath"]))
            for directory in retained:
                for filename in ("execution.json", "execution-python.json", "branches.json", "context.json"):
                    path = Path(context["reportPath"]) if filename == "execution.json" and spec is not None else temp_root / filename
                    if path.is_file():
                        (directory / filename).write_bytes(path.read_bytes())
                (directory / "history.json").write_text(json.dumps(history, indent=2) + "\n")
        if failure is not None:
            raise failure
        if spec is not None:
            current = background_source_hashes(spec["sources"])
            if current != context["sourceHashes"]:
                raise SystemExit("NB source changed during execution")
            coverage = assert_background_report(Path(context["reportPath"]), run_id=context["runId"], suite=name,
                sources=current, started_at=context["startedAt"], bindings={**spec["bindings"], **spec["checks"]},
                required_traces=spec["requiredTraces"], required_actions=set(spec["requiredActions"]),
                required_orders=set(spec["requiredOrders"]))
            for directory in retained:
                (directory / "variant-results.json").write_text(json.dumps(coverage, indent=2) + "\n")
                (directory / "validation.json").write_text(json.dumps({"runId": context["runId"], "outcome": "passed",
                    "sourceSha256": hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                    "reportSha256": hashlib.sha256((directory / "execution.json").read_bytes()).hexdigest()}) + "\n")
            print(f"NB executed evidence: {len(spec['bindings'])} due variants, {len(spec['requiredTraces'])} reference traces", flush=True)


def assert_prototype_collection(mapped: object, collected: set[str]) -> None:
    if not isinstance(mapped, list) or mapped != list(PROTOTYPE_TESTS):
        raise SystemExit("Prototype requirement map must pin all nine regression test IDs")
    missing = set(PROTOTYPE_TESTS) - collected
    if missing:
        raise SystemExit("Missing required prototype regression: " + ", ".join(sorted(missing)))


def assert_mapped_python_suites(entries: list[dict[str, object]]) -> None:
    targets = {target for group in PYTHON_SUITES.values() for target in group}
    for entry in entries:
        for node in entry["tests"]:
            file = node.split("::", 1)[0]
            if file.startswith(("apps/web/unit/", "apps/web/tests/")):
                continue
            if not any(file == target or file.startswith(target + "/") for target in targets):
                raise SystemExit(f"Mapped Python test is outside required gates: {node}")


def assert_partial_checks(entries: list[dict[str, object]], checks: object) -> None:
    partial = {entry["id"] for entry in entries if entry["status"] == "partial"}
    if not isinstance(checks, dict) or set(checks) != partial:
        raise SystemExit("Each partial requirement needs exactly one remaining check")
    for requirement, detail in checks.items():
        if not isinstance(detail, dict) or any(not isinstance(detail.get(key), str) or not detail[key].strip()
                                               for key in ("unproved", "owner", "check")):
            raise SystemExit(f"Incomplete remaining check: {requirement}")


def validate_map(node_context: Path | None = None) -> None:
    require_python()
    data = json.loads((ROOT / "tests/requirements.json").read_text(encoding="utf-8"))
    entries = data["entries"]
    ids = {entry["id"] for entry in entries}
    expected = {"C01", "X01", "X02", "F01", "P01", "P02", "G01", "G02", "G03", "S01",
                "U01", "U02", "D01", "D02", "A01", "A02", "E01", "E02", "R01", "B01", "N01", "L01",
                "NE-RICH", "NE-HISTORY", "NE-ASSETS", "NE-SYNC", "NE-FACTS", "NE-DATES", "NE-TEMPLATE",
                "AG-RUNTIME", "AG-MODELS", "AG-WEB", "AG-EDITS", "AG-HISTORY", "AG-STORAGE", "AG-UI",
                "NB-CONTRACTS", "NB-JOBS", "NB-PUBLICATION", "NB-WRITER", "NB-FIXED", "NB-UI", "NB-PARALLEL"}
    if ids != expected or len(entries) != len(expected):
        raise SystemExit("Requirement map IDs do not match docs/gui/testing.md")
    assert_partial_checks(entries, data.get("partialChecks"))
    assert_mapped_python_suites(entries)
    collection = subprocess.run([str(PYTHON), "-m", "pytest", "--collect-only", "-q", "tests",
                                 "skills/format-resume/tests"], cwd=ROOT, env=safe_env(), text=True,
                                capture_output=True, check=True).stdout
    collected = {line for line in collection.splitlines() if "::" in line}
    assert_prototype_collection(data["foundation"].get("prototypeRegressions"), collected)
    # A function ID maps its parametrized cases without matching longer function names.
    mapped_ids = collected | {node.partition("[")[0] for node in collected}
    state_env = safe_env()
    if node_context is not None:
        state_env["FOLDCV_BACKGROUND_NODE_CONTEXT"] = str(node_context)
    state_result = subprocess.run(["npm", "run", "test:state"], cwd=WEB, env=state_env,
                                  capture_output=True, text=True)
    if state_result.returncode != 0:
        raise SystemExit(state_result.stdout + state_result.stderr)
    state_names = set(re.findall(r"^# Subtest: (.+)$", state_result.stdout, re.MULTILINE))
    if not state_names or not re.search(r"^# fail 0$", state_result.stdout, re.MULTILINE):
        raise SystemExit("State suite did not report passing tests")
    exact_state_nodes = set()
    if node_context is not None:
        scope = json.loads(node_context.read_text())
        report = read_report(Path(scope["reportPath"]))
        binding = next((node for node in report.collected if node.startswith("apps/web/unit/background-")), None)
        if binding is None:
            raise SystemExit("NB Node suite did not collect its exact test files")
        assert_background_report(Path(scope["reportPath"]), run_id=scope["runId"], suite="fast", sources=scope["sourceHashes"],
            started_at=scope["startedAt"], bindings={"node-state": [binding]}, required_traces={}, required_actions=set(), required_orders=set())
        exact_state_nodes = set(report.collected)
    browser_listing = subprocess.run(["npm", "run", "test:browser", "--", "--list"], cwd=WEB,
                                     env=safe_env(), capture_output=True, text=True, check=True).stdout
    browser_names = set(re.findall(r"^\s+([\w.-]+\.spec\.ts):\d+:\d+ › (.+)$",
                                   browser_listing, re.MULTILINE))
    if not browser_names:
        raise SystemExit("Browser suite collected zero tests")
    for entry in entries:
        if entry["status"] not in {"implemented", "partial", "unimplemented"}:
            raise SystemExit(f"Invalid status for {entry['id']}")
        if (entry["status"] == "unimplemented") != (not entry["tests"]):
            raise SystemExit(f"Invalid test mapping for {entry['id']}")
        for node in entry["tests"]:
            if entry["id"].startswith("NB-") and node.startswith("apps/web/tests/"):
                raise SystemExit("NB browser evidence is manual T3")
            if node.startswith("apps/web/unit/"):
                file, _, name = node.partition("::")
                found = (ROOT / file).is_file() and (node in exact_state_nodes if entry["id"].startswith("NB-") else name in state_names)
            elif node.startswith("apps/web/tests/"):
                file, _, name = node.partition("::")
                found = (ROOT / file).is_file() and (Path(file).name, name) in browser_names
            else:
                found = node in (collected if entry["id"].startswith("NB-") else mapped_ids)
            if not found:
                raise SystemExit(f"Missing mapped test: {node}")
    for name, node in data["foundation"].items():
        if name == "prototypeRegressions":
            continue
        if name == "browserShell":
            if not (ROOT / node).is_file():
                raise SystemExit(f"Missing browser shell test: {node}")
        elif node not in mapped_ids:
            raise SystemExit(f"Missing foundation test: {node}")
    gaps = [entry["id"] for entry in entries if entry["status"] != "implemented"]
    print("Unimplemented or partial requirements: " + ", ".join(gaps), flush=True)


def browser() -> None:
    require_node()
    listing = subprocess.run(["npm", "run", "test:browser", "--", "--list"], cwd=WEB,
                             env=safe_env(), capture_output=True, text=True, check=True).stdout
    count = re.search(r"Total: (\d+) tests?", listing)
    if count is None or int(count.group(1)) == 0:
        raise SystemExit("Browser suite collected zero tests")
    run(["npm", "run", "test:browser"], WEB)


def fast(evidence_dir: Path | None, diagnosis: Path | None) -> None:
    require_node()
    spec = background_spec()
    with tempfile.TemporaryDirectory(prefix="foldcv-fast-") as folder:
        root = Path(folder).resolve()
        context = background_context(root, "fast", background_source_hashes(spec["sources"]))
        history_root = ROOT / "tmp/checks-background"
        history = failure_history(history_root, context["sourceHashes"], diagnosis)
        if evidence_dir is not None and evidence_dir.parent != history_root:
            history.extend(failure_history(evidence_dir.parent, context["sourceHashes"], diagnosis))
        retained = [history_root / context["runId"], *([evidence_dir] if evidence_dir else [])]
        for directory in retained:
            directory.mkdir(parents=True, exist_ok=False)
            (directory / "context.json").write_text(json.dumps(context))
        node_report = root / "execution-node.json"
        node_context = root / "context-node.json"
        node_context.write_text(json.dumps({**context, "reportPath": str(node_report)}))
        try:
            validate_map(node_context)
            for command in (["npm", "run", "typecheck"], ["npm", "run", "lint"],
                            ["npm", "run", "contracts:check"], ["npm", "run", "test:contracts"],
                            ["npm", "run", "build"]):
                run(command, WEB)
            pytest_group("fast", evidence_dir, diagnosis,
                prepared={"context": context, "nodeReport": str(node_report), "history": history})
        finally:
            for directory in retained:
                for path in (node_context, node_report, node_report.with_suffix(".json.events.jsonl")):
                    if path.is_file():
                        (directory / path.name).write_bytes(path.read_bytes())
                history_file = directory / "history.json"
                if not history_file.exists():
                    history_file.write_text(json.dumps(history, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=["fast", "integration-render", "browser"])
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--nb-diagnosis", type=Path)
    args = parser.parse_args()
    if args.group == "fast":
        fast(args.evidence_dir, args.nb_diagnosis)
    elif args.group == "integration-render":
        require_converter()
        pytest_group("integration-render", args.evidence_dir)
    else:
        browser()


if __name__ == "__main__":
    main()
