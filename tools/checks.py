"""One local entry point for the same test groups used by CI."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web"
PYTHON = ROOT / ".venv/bin/python"
SOFFICE = ROOT / ".tools/LibreOffice.app/Contents/MacOS/soffice"
PYTHON_SUITES = {
    "fast": ["tests/contracts", "tests/core", "tests/foundation", "tests/service", "tests/devloop", "tests/devloop_antigravity", "skills/format-resume/tests"],
    "integration-render": ["tests/cli_spike", "tests/render_spike"],
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


def pytest_group(name: str) -> None:
    require_python()
    targets = PYTHON_SUITES[name]
    with tempfile.TemporaryDirectory(prefix="foldcv-coverage-") as temp:
        env = safe_env()
        env["COVERAGE_FILE"] = str(Path(temp) / ".coverage")
        run([str(PYTHON), "-m", "pytest", "-q", *targets, "--cov=packages", "--cov=spikes",
             "--cov=tools", "--cov-branch", "--cov-report=term-missing:skip-covered"], env=env)


def assert_prototype_collection(mapped: object, collected: set[str]) -> None:
    if not isinstance(mapped, list) or mapped != list(PROTOTYPE_TESTS):
        raise SystemExit("Prototype requirement map must pin all nine regression test IDs")
    missing = set(PROTOTYPE_TESTS) - collected
    if missing:
        raise SystemExit("Missing required prototype regression: " + ", ".join(sorted(missing)))


def validate_map() -> None:
    require_python()
    data = json.loads((ROOT / "tests/requirements.json").read_text(encoding="utf-8"))
    entries = data["entries"]
    ids = {entry["id"] for entry in entries}
    expected = {"C01", "X01", "X02", "F01", "P01", "P02", "G01", "G02", "G03", "S01",
                "U01", "U02", "D01", "D02", "A01", "A02", "E01", "E02", "R01", "B01", "N01", "L01"}
    if ids != expected or len(entries) != len(expected):
        raise SystemExit("Requirement map IDs do not match docs/gui/testing.md")
    collection = subprocess.run([str(PYTHON), "-m", "pytest", "--collect-only", "-q", "tests",
                                 "skills/format-resume/tests"], cwd=ROOT, env=safe_env(), text=True,
                                capture_output=True, check=True).stdout
    collected = {line for line in collection.splitlines() if "::" in line}
    assert_prototype_collection(data["foundation"].get("prototypeRegressions"), collected)
    for entry in entries:
        if entry["status"] not in {"implemented", "partial", "unimplemented"}:
            raise SystemExit(f"Invalid status for {entry['id']}")
        if (entry["status"] == "unimplemented") != (not entry["tests"]):
            raise SystemExit(f"Invalid test mapping for {entry['id']}")
        for node in entry["tests"]:
            if not any(item.startswith(node) for item in collected):
                raise SystemExit(f"Missing mapped test: {node}")
    for name, node in data["foundation"].items():
        if name == "prototypeRegressions":
            continue
        if name == "browserShell":
            if not (ROOT / node).is_file():
                raise SystemExit(f"Missing browser shell test: {node}")
        elif not any(item.startswith(node) for item in collected):
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=["fast", "integration-render", "browser"])
    args = parser.parse_args()
    if args.group == "fast":
        require_node()
        validate_map()
        for command in (["npm", "run", "typecheck"], ["npm", "run", "lint"],
                        ["npm", "run", "contracts:check"], ["npm", "run", "test:contracts"],
                        ["npm", "run", "build"]):
            run(command, WEB)
        pytest_group("fast")
    elif args.group == "integration-render":
        require_converter()
        pytest_group("integration-render")
    else:
        browser()


if __name__ == "__main__":
    main()
