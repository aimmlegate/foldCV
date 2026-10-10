"""The CI runner keeps the public prototype suite required and guarded."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.checks import PROTOTYPE_TESTS, assert_prototype_collection


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
