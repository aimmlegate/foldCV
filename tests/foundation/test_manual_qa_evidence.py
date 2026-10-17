"""Repair bindings reject missing execution and stale observations."""

import hashlib
from copy import deepcopy

import pytest

from tools.manual_qa_evidence import CASE_IDS, validate_bindings, validate_observation


def test_qa_cases_require_collected_tests_or_explicit_observations():
    node = "tests/recovery/test_rich_import.py::test_example"
    value = {"cases": {key: {"tests": [node]} for key in CASE_IDS}}
    assert set(validate_bindings(value, {node})) == CASE_IDS
    for fault in ("case", "binding", "collection"):
        broken = deepcopy(value)
        if fault == "case": broken["cases"].pop("FM01")
        if fault == "binding": broken["cases"]["FM01"]["tests"] = []
        with pytest.raises(SystemExit, match="QA"):
            validate_bindings(broken, set() if fault == "collection" else {node})


@pytest.mark.parametrize("fault", ["none", "pending", "source", "missing", "changed", "empty"])
def test_qa_observation_requires_exact_source_and_artifact(tmp_path, fault):
    artifact = tmp_path / "result.json"
    artifact.write_text('{"observed":true}')
    sources = {"import.py": "a" * 64}
    record = {"status": "passed", "sourceHashes": sources,
        "artifacts": {artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()}}
    if fault == "pending": record["status"] = "awaiting_manual_word"
    if fault == "source": record["sourceHashes"] = {"import.py": "b" * 64}
    if fault == "missing": artifact.unlink()
    if fault == "changed": artifact.write_text("changed")
    if fault == "empty": record["artifacts"] = {}
    if fault == "none": validate_observation(record, sources, tmp_path)
    else:
        with pytest.raises(SystemExit, match="QA observation"):
            validate_observation(record, sources, tmp_path)
