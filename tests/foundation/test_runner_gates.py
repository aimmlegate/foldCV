"""The CI runner keeps the public prototype suite required and guarded."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import checks
from tools.checks import PROTOTYPE_TESTS, assert_mapped_python_suites, assert_partial_checks, assert_prototype_collection


ROOT = Path(__file__).resolve().parents[2]


def test_missing_prototype_regression_fails_collection_gate() -> None:
    data = json.loads((ROOT / "tests/requirements.json").read_text(encoding="utf-8"))
    mapped = data["foundation"]["prototypeRegressions"]
    assert_prototype_collection(mapped, set(PROTOTYPE_TESTS))
    removed = PROTOTYPE_TESTS[-1]
    with pytest.raises(SystemExit, match="Missing required prototype regression") as error:
        assert_prototype_collection(mapped, set(PROTOTYPE_TESTS) - {removed})
    assert removed in str(error.value)
    with pytest.raises(SystemExit, match="pin all nine"):
        assert_prototype_collection(mapped[:-1], set(PROTOTYPE_TESTS))


def test_all_prototype_regressions_receive_network_guard() -> None:
    result = subprocess.run([sys.executable, "-m", "pytest", "--fixtures-per-test", "-q",
                             "skills/format-resume/tests/test_policy.py"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    assert result.stdout.count("fixtures used by test_") == len(PROTOTYPE_TESTS)
    assert result.stdout.count("deny_network -- conftest.py") == len(PROTOTYPE_TESTS)


def test_requirement_map_cannot_claim_collected_python_tests_outside_required_gates(monkeypatch) -> None:
    data = json.loads((ROOT / "tests/requirements.json").read_text(encoding="utf-8"))
    assert_mapped_python_suites(data["entries"])
    assert (ROOT / "tests/normalize/test_normalization.py").is_file()
    monkeypatch.setitem(checks.PYTHON_SUITES, "fast", [target for target in checks.PYTHON_SUITES["fast"]
                                                  if target != "tests/normalize"])
    with pytest.raises(SystemExit, match="outside required gates"):
        assert_mapped_python_suites(data["entries"])


def test_partial_requirement_cannot_lose_its_remaining_check() -> None:
    data = json.loads((ROOT / "tests/requirements.json").read_text(encoding="utf-8"))
    assert_partial_checks(data["entries"], data["partialChecks"])
    missing = {key: value for key, value in data["partialChecks"].items() if key != "F01"}
    with pytest.raises(SystemExit, match="exactly one remaining check"):
        assert_partial_checks(data["entries"], missing)
    incomplete = {**data["partialChecks"], "F01": {**data["partialChecks"]["F01"], "check": ""}}
    with pytest.raises(SystemExit, match="Incomplete remaining check: F01"):
        assert_partial_checks(data["entries"], incomplete)
