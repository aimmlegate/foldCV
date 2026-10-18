"""Repair bindings reject missing execution and stale observations."""

import hashlib
import json
from copy import deepcopy

import pytest

from tools.manual_qa_evidence import CASE_IDS, ROOT, validate_bindings, validate_execution, validate_observation, validate_retained_native
from tools.background_evidence import assert_report
from tests.foundation.test_runner_gates import nb_report_fixture


def test_retained_native_guard_uses_its_whole_revision_and_rejects_rebound_cases():
    spec = json.loads((ROOT / "tests/requirements.json").read_text())["backgroundExecution"]
    assert validate_retained_native(spec) == []
    changed = deepcopy(spec)
    changed["nativeBindings"]["NB-X03:v01"]["evidence"] = "foreign.json"
    with pytest.raises(SystemExit, match="Historical native bindings"):
        validate_retained_native(changed)


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


def test_function_bindings_expand_only_their_actual_parameter_cases():
    node = "tests/recovery/test_example.py::test_parameterized"
    value = {"cases": {key: {"tests": [node]} for key in CASE_IDS}}
    collected = {node + "[one]", node + "[two]"}
    assert all(nodes == sorted(collected) for nodes in validate_bindings(value, collected).values())
    with pytest.raises(SystemExit, match="not collected"):
        validate_bindings(value, {node + "_different[one]"})


@pytest.mark.parametrize("fault", ["none", "unmapped_failure", "source", "retry"])
def test_qa_execution_uses_its_own_suite_scope_without_relaxing_nb(tmp_path, fault):
    path, report, options = nb_report_fixture(tmp_path)
    nodes = ["tests/recovery/test_rich_import.py::test_literal_import",
        "apps/web/unit/manual-qa-selection.test.ts::selection is context"]
    report["collected"], report["traces"] = nodes[:], []
    report["records"] = [{**deepcopy(report["records"][0]), "nodeId": node} for node in nodes]
    bindings = {"IN01": [nodes[0]], "AG01": [nodes[1]]}
    options.update(bindings=bindings, required_traces={}, required_actions=set(), required_orders=set())
    context = {"runId": report["runId"], "sourceHashes": report["sourceHashes"], "startedAt": report["startedAt"]}
    path.write_text(json.dumps(report))
    with pytest.raises(SystemExit, match="outside its required"):
        assert_report(path, **options)
    assert set(validate_execution(path, context, bindings)) == set(bindings)
    if fault == "none":
        return
    if fault == "unmapped_failure":
        node = "tests/recovery/test_rich_import.py::test_other_failure"
        report["collected"].append(node)
        report["records"].append({**deepcopy(report["records"][0]), "nodeId": node,
            "phases": {"setup": "passed", "call": "failed", "teardown": "passed"}})
    elif fault == "source":
        context["sourceHashes"] = {"test.py": "b" * 64}
    else:
        report["records"][0]["attempt"] = 2
    path.write_text(json.dumps(report))
    with pytest.raises(SystemExit):
        validate_execution(path, context, bindings)


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
