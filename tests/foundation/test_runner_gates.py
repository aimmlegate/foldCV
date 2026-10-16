"""The CI runner keeps the public prototype suite required and guarded."""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from tools import checks
from tools.checks import PROTOTYPE_TESTS, assert_mapped_python_suites, assert_partial_checks, assert_prototype_collection
from tools.background_evidence import assert_report, digest, failure_history, read_report
from spikes.background.corpus import ACTIONS, ORDERS, reached_orders, trace


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


@pytest.mark.parametrize("scope", ["entry", "foundation"])
def test_requirement_map_does_not_accept_a_test_name_prefix(monkeypatch, scope) -> None:
    data = json.loads((ROOT / "tests/requirements.json").read_text())
    python_nodes = {node for entry in data["entries"] for node in entry["tests"]
                    if not node.startswith("apps/web/")}
    python_nodes.update(node for name, node in data["foundation"].items()
                        if name not in {"browserShell", "prototypeRegressions"})
    python_nodes.update(PROTOTYPE_TESTS)
    node = (next(node for node in data["entries"][0]["tests"] if node.startswith("tests/"))
            if scope == "entry" else data["foundation"]["syntheticSources"])
    collected = (python_nodes - {node}) | {node + "_extra"}
    state_names = {node.split("::", 1)[1] for entry in data["entries"] for node in entry["tests"]
                   if node.startswith("apps/web/unit/")}
    browser_names = {node.split("::", 1)[0].rsplit("/", 1)[1] + ":1:1 › " + node.split("::", 1)[1]
                     for entry in data["entries"] for node in entry["tests"] if node.startswith("apps/web/tests/")}
    browser_names.add("default-entry.spec.ts:1:1 › retained collection fixture")

    def run(argv, **kwargs):
        if "--collect-only" in argv:
            output = "\n".join(sorted(collected))
        elif "test:state" in argv:
            output = "\n".join("# Subtest: " + name for name in state_names) + "\n# fail 0\n"
        else:
            output = "\n".join("  " + name for name in browser_names)
        return subprocess.CompletedProcess(argv, 0, stdout=output)

    monkeypatch.setattr(checks, "require_python", lambda: None)
    monkeypatch.setattr(checks.subprocess, "run", run)
    with pytest.raises(SystemExit, match="Missing mapped test|Missing foundation test"):
        checks.validate_map()


def nb_report_fixture(tmp_path):
    node = "tests/recovery/test_background_offline.py::test_frozen_reference_corpus_is_reproducible_and_reaches_each_action[seed-00]"
    corpus = trace(0)
    report = {"schemaVersion": 1, "runId": "current-run", "suite": "fast", "sourceHashes": {"test.py": "a" * 64},
        "startedAt": "2026-10-16T12:00:00Z", "finishedAt": "2026-10-16T12:00:01Z", "complete": True, "exitStatus": 0,
        "collected": [node], "records": [{"nodeId": node, "phases": {"setup": "passed", "call": "passed", "teardown": "passed"},
            "markers": [], "attempt": 1}], "traces": [{**corpus, "nodeId": node, "sha256": digest(corpus)}]}
    options = {"run_id": "current-run", "suite": "fast", "sources": {"test.py": "a" * 64},
        "started_at": report["startedAt"], "bindings": {"variant-one": [node]},
        "required_traces": {"fixed:1:0": {"seed": 0, "capacity": 1, "transitions": 200,
            "scope": "specification_oracle_only", "nodeId": node}}, "required_actions": set(ACTIONS), "required_orders": set(ORDERS)}
    return tmp_path / "execution-report.json", report, options


@pytest.mark.parametrize("variant", [f"NB-G02:v{i:02}" for i in range(1, 17)])
def test_background_report_rejects_false_coverage(tmp_path, variant):
    path, report, options = nb_report_fixture(tmp_path)
    path.write_text(json.dumps(report))
    assert assert_report(path, **options)["variant-one"]["outcome"] == "passed"
    bad = deepcopy(report)
    record = bad["records"][0]
    if variant == "NB-G02:v01":
        bad["records"] = []
    elif variant in {"NB-G02:v02", "NB-G02:v03", "NB-G02:v04", "NB-G02:v05"}:
        marker = {"NB-G02:v02": "skip", "NB-G02:v03": "xfail", "NB-G02:v04": "xpass", "NB-G02:v05": "todo"}[variant]
        record["markers"] = [marker]
        record["phases"]["call"] = "passed" if marker in {"xpass", "todo"} else "skipped"
    elif variant == "NB-G02:v06":
        record["phases"] = {"setup": "failed", "teardown": "passed"}
    elif variant == "NB-G02:v07":
        record["phases"]["teardown"] = "failed"
    elif variant == "NB-G02:v08":
        wrong = record["nodeId"].replace("test_background_offline.py", "test_background_another.py")
        record["nodeId"] = wrong
        bad["collected"] = [wrong]
    elif variant == "NB-G02:v09":
        bad["collected"] = []
        bad["records"] = []
    elif variant == "NB-G02:v10":
        bad["suite"] = "integration-render"
    elif variant == "NB-G02:v11":
        bad["sourceHashes"]["test.py"] = "b" * 64
    elif variant == "NB-G02:v12":
        bad["runId"] = "previous-run"
    elif variant == "NB-G02:v13":
        record["attempt"] = 2
    elif variant == "NB-G02:v14":
        bad["traces"] = []
    else:
        corpus = bad["traces"][0]
        for row in corpus["log"]:
            if ((variant == "NB-G02:v15" and row["action"] == "input") or
                    (variant == "NB-G02:v16" and row["action"] == "timeout" and row["job"] == "two")):
                row.update(action="tick", result="advanced")
        corpus["actions"] = sorted({row["action"] for row in corpus["log"] if row["result"] != "rejected"})
        corpus["orders"] = reached_orders(corpus["log"])
        corpus["sha256"] = digest({key: value for key, value in corpus.items() if key not in {"nodeId", "sha256"}})
    path.write_text(json.dumps(bad))
    with pytest.raises(SystemExit, match="NB "):
        assert_report(path, **options)


@pytest.mark.parametrize("fault", ["missing", "empty", "truncated", "duplicate-key", "missing-parameter",
    "off-suite", "cancelled", "timeout", "initial-failure", "incomplete", "empty-bindings", "uncollected-result",
    "duplicate-trace", "wrong-trace-hash", "wrong-trace-owner", "wrong-trace-seed", "wrong-trace-length"])
def test_background_report_rejects_broken_files_and_erased_failures(tmp_path, fault):
    path, report, options = nb_report_fixture(tmp_path)
    if fault == "missing":
        pass
    elif fault in {"empty", "truncated", "duplicate-key"}:
        path.write_text({"empty": "", "truncated": '{"schemaVersion":1,',
            "duplicate-key": '{"runId":"old","runId":"new"}'}[fault])
    else:
        if fault == "missing-parameter":
            report["collected"][0] = report["collected"][0].split("[")[0]
            report["records"][0]["nodeId"] = report["collected"][0]
        elif fault == "off-suite":
            options["bindings"] = {"variant-one": ["tests/cli_spike/test_background.py::same_name"]}
        elif fault in {"cancelled", "timeout"}:
            report["records"][0]["phases"]["call"] = fault
        elif fault == "initial-failure":
            failed = deepcopy(report["records"][0])
            failed["phases"]["call"] = "failed"
            report["records"].insert(0, failed)
        elif fault == "empty-bindings":
            options["bindings"] = {}
        elif fault == "uncollected-result":
            extra = deepcopy(report["records"][0])
            extra["nodeId"] = "tests/recovery/test_background_another.py::not_collected"
            report["records"].append(extra)
        elif fault == "duplicate-trace":
            report["traces"].append(deepcopy(report["traces"][0]))
        elif fault in {"wrong-trace-hash", "wrong-trace-owner", "wrong-trace-seed", "wrong-trace-length"}:
            corpus = report["traces"][0]
            if fault == "wrong-trace-hash":
                corpus["sha256"] = "b" * 64
            else:
                if fault == "wrong-trace-owner":
                    corpus["nodeId"] = "tests/recovery/test_background_another.py::not_executed"
                elif fault == "wrong-trace-seed":
                    corpus["seed"] = 99
                else:
                    corpus["log"].pop()
                corpus["sha256"] = digest({key: value for key, value in corpus.items() if key not in {"nodeId", "sha256"}})
        else:
            report["complete"] = False
        path.write_text(json.dumps(report))
    with pytest.raises(SystemExit, match="NB "):
        assert_report(path, **options)


def test_background_reporter_retains_real_skips_and_failed_phases(tmp_path):
    probe = tmp_path / "phase_probe.py"
    probe.write_text('''import pytest
@pytest.fixture
def broken_setup():
    raise RuntimeError("synthetic setup failure")
@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError("synthetic teardown failure")
def test_pass():
    pass
@pytest.mark.skip(reason="synthetic skip")
def test_skip():
    pass
@pytest.mark.xfail(reason="synthetic expected failure")
def test_xfail():
    assert False
@pytest.mark.xfail(reason="synthetic unexpected pass")
def test_xpass():
    pass
def test_setup(broken_setup):
    pass
def test_teardown(broken_teardown):
    pass
''')
    alias = tmp_path / "temp-alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    context = checks.background_context(alias, "fast", {"probe.py": "a" * 64})
    assert context["reportPath"] == str(tmp_path.resolve() / "execution.json")
    path = tmp_path / "context.json"
    path.write_text(json.dumps(context))
    env = checks.safe_env()
    env["FOLDCV_BACKGROUND_CONTEXT"] = str(path)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "tools.background_pytest", str(probe)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    report = read_report(tmp_path / "execution.json")
    assert report.complete and report.exit_status == 1
    records = {item.node_id.split("::")[-1]: item for item in report.records}
    assert records["test_pass"].phases == {"setup": "passed", "call": "passed", "teardown": "passed"}
    assert records["test_skip"].phases["setup"] == "skipped"
    assert records["test_xfail"].markers == ["xfail"]
    assert records["test_xpass"].markers == ["xpass"]
    assert records["test_setup"].phases["setup"] == "failed"
    assert "call" not in records["test_setup"].phases
    assert records["test_teardown"].phases["teardown"] == "failed"


def test_background_retry_cannot_forget_a_prior_failed_run(tmp_path):
    previous = tmp_path / "previous"
    previous.mkdir()
    sources = {"test.py": "a" * 64}
    (previous / "context.json").write_text(json.dumps({"runId": "failed-run", "sourceHashes": sources}))
    with pytest.raises(SystemExit, match="unchanged source"):
        failure_history(tmp_path, sources)
    changed = failure_history(tmp_path, {"test.py": "b" * 64})
    assert changed[0]["outcome"] == "failed_or_incomplete"
    artifact = tmp_path / "reproduction.json"
    artifact.write_text('{"syntheticFailure":"reproduced with a controlled boundary"}')
    diagnosis = tmp_path / "diagnosis.json"
    diagnosis.write_text(json.dumps({"previousRun": "failed-run", "sourceSha256": digest(sources),
        "reason": "A controlled reproduction isolates the failure; retain both runs.",
        "evidence": {str(artifact): hashlib.sha256(artifact.read_bytes()).hexdigest()}}))
    assert failure_history(tmp_path, sources, diagnosis)[0]["diagnosis"] == str(diagnosis)
    artifact.write_text("changed reproduction")
    with pytest.raises(SystemExit, match="unchanged source"):
        failure_history(tmp_path, sources, diagnosis)
