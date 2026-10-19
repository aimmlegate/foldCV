"""Repair bindings reject missing execution and stale observations."""

import hashlib
import json
from io import BytesIO
from types import SimpleNamespace
import tarfile
from pathlib import Path
import sys
from copy import deepcopy

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from tools.manual_qa_evidence import CASE_IDS, validate_bindings, validate_execution, validate_observation, validate_retained_native
from tools.background_evidence import assert_report
from tests.foundation.test_runner_gates import nb_report_fixture
from tools.manual_qa_evidence import observe_provider_generation


@pytest.mark.parametrize("fault", ["none", "binding", "sources"])
def test_retained_native_guard_uses_its_whole_revision_and_rejects_rebound_cases(tmp_path, monkeypatch, fault):
    from tools import manual_qa_evidence as evidence
    spec = {"sources": ["runtime.py"], "nativeBindings": {"NB-X03:v01": {"evidence": "proof.json"}}}
    historical = deepcopy(spec)
    if fault == "binding": spec["nativeBindings"]["NB-X03:v01"]["evidence"] = "foreign.json"
    if fault == "sources": spec["sources"].append("unbound.py")
    calls = []
    def output(argv, **_options):
        if argv[1] == "show":
            assert argv == ["git", "show", f"{evidence.HISTORICAL_REVISION}:tests/requirements.json"]
            return json.dumps({"backgroundExecution": historical}).encode()
        assert argv == ["git", "rev-parse", "--absolute-git-dir"]
        return str(tmp_path / ".git") + "\n"
    def run(argv, **options):
        calls.append(argv)
        if argv[0] == "git":
            assert argv == ["git", "archive", "--format=tar", evidence.HISTORICAL_REVISION]
            with tarfile.open(fileobj=options["stdout"], mode="w") as archive:
                data = b"pinned runtime\n"; entry = tarfile.TarInfo("runtime.py"); entry.size = len(data)
                archive.addfile(entry, BytesIO(data))
        else:
            assert "background_spec()['pendingNative']" in argv[-1]
            assert (options["cwd"] / "runtime.py").read_bytes() == b"pinned runtime\n"
            assert options["env"]["GIT_DIR"] == str(tmp_path / ".git")
            assert options["env"]["PYTHONPATH"].endswith(str(options["cwd"]))
            return SimpleNamespace(stdout="[]")
    monkeypatch.setattr(evidence.subprocess, "check_output", output)
    monkeypatch.setattr(evidence.subprocess, "run", run)
    if fault == "none":
        assert validate_retained_native(spec) == [] and len(calls) == 2
    else:
        with pytest.raises(SystemExit, match="Historical native bindings"):
            validate_retained_native(spec)
        assert not calls


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


@pytest.mark.parametrize("path", ["direct", "queued", "owned"])
def test_native_observer_counts_before_every_real_provider_entry_once(tmp_path, path):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import threading
    from resume_api.gui_admission import QueuedProvider
    from resume_api.providers.codex_cli import CodexCliProvider
    events = []
    class Provider(CodexCliProvider):
        def __init__(self):
            pass
        @contextmanager
        def _profile_owner(self, *_args):
            yield
        def _generate(self, *_args):
            events.append("native_start")
            return "result"
    def wrap(original):
        def observed(*args):
            events.append("counted")
            return original(*args)
        return observed
    provider = Provider()
    assert observe_provider_generation(provider, wrap) is provider
    observe_provider_generation(provider, wrap)
    files, cancel = SimpleNamespace(root=tmp_path), threading.Event()
    if path == "queued":
        result = QueuedProvider(provider, lambda: events.append("admitted")).generate(None, files, cancel)
        assert events.pop(0) == "admitted"
    elif path == "owned":
        class Permit:
            @contextmanager
            def hold(self, *_args):
                yield
        result = provider.generate_owned(None, files, cancel, Permit())
    else:
        result = provider.generate(None, files, cancel)
    assert result == "result" and events == ["counted", "native_start"]


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
