"""The CI runner keeps the public prototype suite required and guarded."""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys

import pytest

from tools import checks
from tools.checks import PROTOTYPE_TESTS, assert_mapped_python_suites, assert_partial_checks, assert_prototype_collection
from tools.background_evidence import assert_report, digest, failure_history, merge_reports, read_report
from tools.background_evidence import assert_manual_bindings, assert_native_bindings
from tools.background_corpus import run_shards, retain_raw
from spikes.background.corpus import ACTIONS, ORDERS, reached_orders, trace


ROOT = Path(__file__).resolve().parents[2]


def test_portable_background_checks_keep_private_acceptance_separate(monkeypatch):
    from tools import background_evidence
    calls = []
    def unavailable(*_args, **_kwargs):
        calls.append("manual")
        raise SystemExit("private screenshot missing")
    def native(*_args, **_kwargs):
        calls.append("native")
        raise AssertionError("portable checks must not accept historical native evidence")
    monkeypatch.setattr(background_evidence, "assert_manual_bindings", unavailable)
    monkeypatch.setattr(background_evidence, "assert_native_bindings", native)
    portable = checks.background_spec(acceptance=False)
    assert not calls and set(portable["pendingNative"]) == set(portable["nativeBindings"])
    assert portable["bindings"] and portable["manualBindings"]
    with pytest.raises(SystemExit, match="private screenshot missing"):
        checks.background_spec(require_native=True)
    assert calls == ["manual"]


def test_portable_background_checks_still_require_exact_manual_binding_ids(tmp_path, monkeypatch):
    data = json.loads((ROOT / "tests/requirements.json").read_text())
    spec = data["backgroundExecution"]
    spec["manualBindings"].pop(next(iter(spec["manualBindings"])))
    for name in ["tests/requirements.json", spec["reportSchema"], "docs/gui/handoffs/BACKGROUND-WORK/test-matrix.json"]:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    (tmp_path / "tests/requirements.json").write_text(json.dumps(data))
    monkeypatch.setattr(checks, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="manual/native variants"):
        checks.background_spec(acceptance=False)


def test_retained_native_acceptance_cannot_be_selected_for_portable_fast(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["checks.py", "fast", "--retained-native"])
    with pytest.raises(SystemExit) as error:
        checks.main()
    assert error.value.code == 2


@pytest.mark.parametrize("fault", ["none", "failed-worker"])
def test_background_corpus_shards_retain_every_exact_node_and_failed_worker(tmp_path, fault):
    probe = tmp_path / "test_corpus_probe.py"
    probe.write_text("import pytest\n@pytest.mark.parametrize('index', range(8))\ndef test_case(index):\n"
        + ("    assert index != 3\n" if fault == "failed-worker" else "    assert index >= 0\n"))
    nodes = [probe.name + f"::test_case[{index}]" for index in range(8)]
    root, retained = tmp_path / "reports", tmp_path / "retained"
    root.mkdir(); retained.mkdir()
    context = checks.background_context(root, "fast", {probe.name: hashlib.sha256(probe.read_bytes()).hexdigest()})
    env = {**checks.safe_env(), "PYTHONPATH": str(ROOT)}
    def execute():
        run_shards(Path(sys.executable), nodes, context=context, root=root, cwd=tmp_path, env=env,
            coverage_arguments=["--cov=tools.background_pytest", "--cov-branch"], retained=[retained])
    if fault == "failed-worker":
        with pytest.raises(subprocess.CalledProcessError):
            execute()
    else:
        execute()
    retain_raw(root, [retained])
    paths = sorted(retained.glob("execution-corpus-*.json"))
    assert len(paths) == 4 and len(list(retained.glob("corpus-*.log"))) == 4
    merge_reports(paths, retained / "combined.json")
    report = read_report(retained / "combined.json")
    assert len(report.collected) == len(set(report.collected)) == 8 and set(report.collected) == set(nodes)
    assert len(report.records) == 8 and report.complete
    assert report.exit_status == (1 if fault == "failed-worker" else 0)
    failures = [record for record in report.records if record.phases["call"] == "failed"]
    assert len(failures) == int(fault == "failed-worker")
    assert all(record.phases["setup"] == record.phases["teardown"] == "passed" for record in report.records)


@pytest.mark.parametrize("fault", ["missing", "pending", "scripted", "source", "pool", "ungranted", "changed", "cleanup"])
def test_background_native_gate_rejects_unproved_or_wrong_authority_results(tmp_path, fault):
    variant = "NB-X03:v01"
    runtime = dict(nativeStarted=True, state="completed", error=None, nativePid=123,
        ownedPidsGone=True, mcpListenerClosed=True, operationRemoved=True, profileExclusionLost=False, toolCalls=3)
    if fault == "cleanup": runtime["ownedPidsGone"] = False
    artifact = tmp_path / "runtime.json"; artifact.write_text(json.dumps(runtime))
    sources = {"runtime.py": "a" * 64}
    case = dict(outcome="passed", layer="native", attemptId="test-attempt", runtimeArtifact=artifact.name,
        artifacts={artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()})
    if fault == "pending": case["outcome"] = "awaiting_native_proof"
    if fault == "scripted": case["layer"] = "python"
    proof = tmp_path / "proof.json"
    proof.write_text(json.dumps(dict(sourceHashes={} if fault == "source" else sources, variants={variant: case})))
    ledger = tmp_path / "docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps(dict(pools={"NB07a": dict(authorized=fault != "ungranted", cap=2, spent=1)},
        attempts=[dict(id="test-attempt", pool="NB00" if fault == "pool" else "NB07a", variant=variant, status="passed")])))
    if fault == "changed": artifact.write_text("changed")
    bindings = {} if fault == "missing" else {variant: dict(evidence=proof.name, pool="NB07a")}
    with pytest.raises(SystemExit):
        assert_native_bindings(bindings, {variant}, tmp_path, sources=sources, require_pass=True)
    if fault == "pending":
        assert assert_native_bindings(bindings, {variant}, tmp_path, sources=sources) == [variant]


@pytest.mark.parametrize("fault", ["none", "missing-binding", "missing-case", "skipped", "changed-evidence", "missing-authority"])
def test_background_manual_gate_keeps_unavailable_or_stale_cases_out(tmp_path, fault):
    variant = "NB-X02:v01"
    artifact = tmp_path / "observation.json"
    artifact.write_text('{"observed":true}')
    case = {"status": "passed", "evidence": {artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()}}
    if fault == "skipped": case["status"] = "skipped"
    if fault == "missing-authority": case["status"] = "accepted_user_amendment"
    record = tmp_path / "manual.json"
    record.write_text(json.dumps({"cases": {} if fault == "missing-case" else {variant: case}}))
    if fault == "changed-evidence": artifact.write_text('{"observed":false}')
    bindings = {} if fault == "missing-binding" else {variant: record.name}
    if fault == "none":
        assert_manual_bindings(bindings, {variant}, tmp_path)
    else:
        with pytest.raises(SystemExit, match="NB manual"):
            assert_manual_bindings(bindings, {variant}, tmp_path)


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
    python_nodes.update(node for name, nodes in data["foundation"].items() if name != "browserShell"
                        for node in (nodes if isinstance(nodes, list) else [nodes]))
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


@pytest.mark.parametrize("fault", ["file", "parameter", "parent", "skip", "todo", "hook", "retry", "suite", "empty", "browser"])
def test_background_node_binding_requires_exact_execution_identity_and_phases(tmp_path, fault):
    path, report, options = nb_report_fixture(tmp_path)
    node = "apps/web/unit/background-writer.test.ts::writer suite::barrier [case=one]"
    report["collected"], report["traces"] = [node], []
    report["records"][0]["nodeId"] = node
    options.update(bindings={"variant-one": [node]}, required_traces={}, required_actions=set(), required_orders=set())
    path.write_text(json.dumps(report))
    assert assert_report(path, **options)["variant-one"]["nodes"] == [node]
    changed = deepcopy(report)
    if fault in {"file", "parameter", "parent"}:
        wrong = node.replace("background-writer.test.ts", "background-other.test.ts") if fault == "file" else (
            node.replace("case=one", "case=two") if fault == "parameter" else node.replace("writer suite", "other suite"))
        changed["collected"], changed["records"][0]["nodeId"] = [wrong], wrong
    elif fault in {"skip", "todo"}:
        changed["records"][0]["markers"] = [fault]
    elif fault == "hook":
        changed["records"][0]["phases"]["teardown"] = "unknown"
    elif fault == "retry":
        changed["records"].append(deepcopy(changed["records"][0]))
    elif fault == "suite":
        changed["suite"] = "integration-render"
    elif fault == "empty":
        changed["collected"], changed["records"] = [], []
    else:
        wrong = node.replace("unit/background-writer.test.ts", "tests/background.spec.ts")
        changed["collected"], changed["records"][0]["nodeId"] = [wrong], wrong
        options["bindings"] = {"variant-one": [wrong]}
    path.write_text(json.dumps(changed))
    with pytest.raises(SystemExit):
        assert_report(path, **options)


def test_background_node_reporter_retains_real_hook_failures_skips_and_nested_names(tmp_path):
    probe = tmp_path / "node-proof.test.mjs"
    probe.write_text('''import { test, beforeEach, afterEach } from "node:test";
beforeEach(t => { if (t.name === "setup failure") throw new Error("Setup cut"); });
afterEach(t => { if (t.name === "teardown failure") throw new Error("Teardown cut"); });
test("exact name [case=A]", () => {});
test("exact name [case=B]", () => {});
test("setup failure", () => {});
test("teardown failure", () => {});
test("skipped", { skip: true }, () => {});
test("todo", { todo: true }, () => {});
test("parent", async t => { await t.test("child [case=A]", () => {}); });
test("concurrent parent", { concurrency: 2 }, async t => {
  let release; const held = new Promise(resolve => { release = resolve; });
  await Promise.all([t.test("first", async () => { await held; }), t.test("second", () => { release(); })]);
});
''')
    context = checks.background_context(tmp_path, "fast", {"node-proof.test.mjs": hashlib.sha256(probe.read_bytes()).hexdigest()})
    context_file = tmp_path / "context-node.json"
    context_file.write_text(json.dumps(context))
    env = {**checks.safe_env(), "FOLDCV_BACKGROUND_NODE_CONTEXT": str(context_file)}
    result = subprocess.run(["node", "--test", "--test-reporter=" + str(ROOT / "tools/background_node_reporter.mjs"), str(probe)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    report = read_report(Path(context["reportPath"]))
    assert report.complete and report.exit_status != 0 and len(report.records) == 11
    outcomes = {record.node_id.split("::", 1)[1]: record for record in report.records}
    assert outcomes["exact name [case=A]"].phases == outcomes["exact name [case=B]"].phases == {
        "setup": "passed", "call": "passed", "teardown": "passed"}
    assert outcomes["skipped"].markers == ["skip"] and outcomes["todo"].markers == ["todo"]
    assert outcomes["skipped"].phases == {"setup": "skipped", "call": "skipped", "teardown": "skipped"}
    assert outcomes["setup failure"].phases != outcomes["exact name [case=A]"].phases
    assert outcomes["teardown failure"].phases != outcomes["exact name [case=A]"].phases
    assert "parent::child [case=A]" in outcomes
    assert "concurrent parent::first" in outcomes and "concurrent parent::second" in outcomes
    raw = Path(context["reportPath"] + ".events.jsonl").read_text()
    assert "Setup cut" in raw and "Teardown cut" in raw


def test_background_raw_report_merge_preserves_files_and_refuses_rewrite_or_source_drift(tmp_path):
    first, report, _options = nb_report_fixture(tmp_path)
    node = deepcopy(report)
    report["finishedAt"] = (datetime.fromisoformat(report["finishedAt"]) + timedelta(seconds=30)).isoformat()
    first.write_text(json.dumps(report))
    identity = "apps/web/unit/background-writer.test.ts::exact parameter [case=A]"
    node["collected"], node["records"][0]["nodeId"], node["traces"] = [identity], identity, []
    second = tmp_path / "node.json"; second.write_text(json.dumps(node))
    combined = tmp_path / "combined.json"
    original = first.read_bytes(), second.read_bytes()
    merge_reports([first, second], combined)
    assert len(read_report(combined).records) == 2
    assert read_report(combined).finished_at == report["finishedAt"]
    assert original == (first.read_bytes(), second.read_bytes())
    with pytest.raises(SystemExit, match="never rewrite"):
        merge_reports([first, second], combined)
    node["sourceHashes"] = {"node-proof.test.mjs": "b" * 64}; second.write_text(json.dumps(node))
    with pytest.raises(SystemExit, match="different run/source identity"):
        merge_reports([first, second], tmp_path / "wrong.json")


@pytest.mark.parametrize("fault", ["none", "malformed-python"])
def test_background_fast_uses_one_context_and_retains_raw_reports_before_combining(tmp_path, monkeypatch, fault):
    node = "apps/web/unit/background-proof.test.ts::exact [case=A]"
    python = "tests/recovery/test_background_probe.py::exact_python"
    spec = {"sources": ["probe.py"], "bindings": {"node": [node], "python": [python]}, "checks": {},
        "requiredTraces": {}, "requiredActions": [], "requiredOrders": [], "pendingNative": []}
    (tmp_path / "probe.py").write_text("retained source\n")
    source_sha = hashlib.sha256((tmp_path / "probe.py").read_bytes()).hexdigest()
    monkeypatch.setattr(checks, "ROOT", tmp_path)
    monkeypatch.setattr(checks, "require_node", lambda: None)
    monkeypatch.setattr(checks, "require_python", lambda: None)
    monkeypatch.setattr(checks, "background_spec", lambda **_options: spec)
    monkeypatch.setattr(checks, "background_source_hashes", lambda _names: {"probe.py": source_sha})
    calls = []
    def write_report(context, identity):
        path = Path(context["reportPath"])
        value = {**{key: val for key, val in context.items() if key != "reportPath"}, "schemaVersion": 1,
            "finishedAt": context["startedAt"], "complete": True, "exitStatus": 0, "collected": [identity],
            "records": [{"nodeId": identity, "phases": {"setup": "passed", "call": "passed", "teardown": "passed"},
                "markers": [], "attempt": 1}], "traces": []}
        path.write_text(json.dumps(value))
    def validate(context_file):
        write_report(json.loads(context_file.read_text()), node)
    def run(argv, cwd=checks.ROOT, env=None):
        calls.append(argv)
        if "pytest" in argv:
            context = json.loads(Path(env["FOLDCV_BACKGROUND_CONTEXT"]).read_text())
            write_report(context, python)
            if fault == "malformed-python":
                Path(context["reportPath"]).write_text('{"partial":')
        return ""
    monkeypatch.setattr(checks, "validate_map", validate)
    monkeypatch.setattr(checks, "run", run)
    evidence = tmp_path / "retained" / "proof"
    if fault == "malformed-python":
        with pytest.raises(SystemExit, match="missing or malformed"):
            checks.fast(evidence, None)
        assert (evidence / "execution-python.json").read_text() == '{"partial":'
        assert read_report(evidence / "execution-node.json").complete
        assert not (evidence / "validation.json").exists()
        return
    checks.fast(evidence, None)
    combined = read_report(evidence / "execution.json")
    raw_node, raw_python = read_report(evidence / "execution-node.json"), read_report(evidence / "execution-python.json")
    assert combined.collected == [node, python]
    assert raw_node.run_id == raw_python.run_id == combined.run_id
    assert raw_node.source_hashes == raw_python.source_hashes == {"probe.py": source_sha}
    assert raw_node.started_at == raw_python.started_at == combined.started_at
    validation = json.loads((evidence / "validation.json").read_text())
    assert validation["outcome"] == "passed" and validation["reportSha256"] == hashlib.sha256((evidence / "execution.json").read_bytes()).hexdigest()
    assert len(calls) == 6


def test_background_report_cannot_finish_before_its_bound_start(tmp_path):
    path, report, options = nb_report_fixture(tmp_path)
    report["finishedAt"] = "2026-10-16T11:59:59Z"
    path.write_text(json.dumps(report))
    with pytest.raises(SystemExit, match="old/wrong run"):
        assert_report(path, **options)


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
