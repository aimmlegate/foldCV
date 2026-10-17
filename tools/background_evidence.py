"""Exact executed NB evidence. Collection and a later retry cannot imply a pass."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from packages.resume_core.models.contracts import Sha256, Wire
from packages.resume_core.models.agent import Timestamp

ROOT = Path(__file__).resolve().parents[1]


class ExecutedTest(Wire):
    node_id: str = Field(min_length=1)
    phases: dict[Literal["setup", "call", "teardown"], str]
    markers: list[str]
    attempt: int = Field(ge=1)


class ExecutedTrace(Wire):
    id: str
    node_id: str
    seed: int = Field(ge=0)
    capacity: Literal[1, 3]
    transitions: int = Field(ge=1)
    actions: list[str]
    orders: list[str]
    log: list[dict[str, str | int]]
    scope: Literal["specification_oracle_only", "production_integration"]
    sha256: Sha256


class ExecutionReportV1(Wire):
    schema_version: Literal[1]
    run_id: str = Field(min_length=1)
    suite: Literal["fast", "integration-render"]
    source_hashes: dict[str, Sha256]
    started_at: Timestamp
    finished_at: Timestamp
    complete: bool
    exit_status: int
    collected: list[str]
    records: list[ExecutedTest]
    traces: list[ExecutedTrace]


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def source_hashes(paths: list[str], root: Path = ROOT) -> dict[str, str]:
    result = {}
    for name in paths:
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise SystemExit(f"NB source is missing or unsafe: {name}")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:
        raise SystemExit("NB source manifest is empty")
    return result


def assert_manual_bindings(bindings: dict[str, str], required: set[str], root: Path = ROOT) -> None:
    if set(bindings) != required:
        raise SystemExit("NB manual variants do not match their evidence bindings")
    checked = {}
    def retained(name):
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise SystemExit("NB manual evidence is missing or outside the repository")
        if name not in checked:
            checked[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    for variant, name in bindings.items():
        record = json.loads(retained(name).read_text())
        case = record.get("cases", {}).get(variant)
        if not isinstance(case, dict) or case.get("status") not in {"passed", "accepted_user_amendment"}:
            raise SystemExit("NB manual case has no accepted observation")
        evidence = case.get("evidence")
        if not isinstance(evidence, dict) or not evidence:
            raise SystemExit("NB manual observation has no retained evidence")
        for artifact, checksum in evidence.items():
            retained(artifact)
            if checked[artifact] != checksum:
                raise SystemExit("NB manual evidence hash changed")
        if case["status"] == "accepted_user_amendment":
            authority = case.get("authority")
            if authority not in evidence:
                raise SystemExit("NB manual amendment has no retained authority")
            value = json.loads(retained(authority).read_text())
            if value.get("variant") != variant or not value.get("userText"):
                raise SystemExit("NB manual amendment has no exact user instruction")


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_report(path: Path) -> ExecutionReportV1:
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=strict_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int:
            raise ValueError("report version must be an integer")
        return ExecutionReportV1.model_validate(value)
    except (OSError, ValueError, ValidationError) as error:
        raise SystemExit(f"NB execution report is missing or malformed: {type(error).__name__}") from error


def merge_reports(paths: list[Path], target: Path) -> None:
    reports = [read_report(path) for path in paths]
    if not reports:
        raise SystemExit("NB report merge is empty")
    first = reports[0]
    if any((report.run_id, report.suite, report.source_hashes, report.started_at) !=
            (first.run_id, first.suite, first.source_hashes, first.started_at) for report in reports):
        raise SystemExit("NB raw reports have different run/source identity")
    finished = max(reports, key=lambda report: datetime.fromisoformat(report.finished_at.replace("Z", "+00:00"))).finished_at
    combined = first.model_copy(update={"finished_at": finished,
        "complete": all(report.complete for report in reports),
        "exit_status": next((report.exit_status for report in reports if report.exit_status), 0),
        "collected": [node for report in reports for node in report.collected],
        "records": [record for report in reports for record in report.records],
        "traces": [trace for report in reports for trace in report.traces]})
    if target.exists():
        raise SystemExit("NB combined evidence already exists; never rewrite a validated report")
    target.write_text(combined.model_dump_json(by_alias=True, indent=2) + "\n")


def failure_history(root: Path, sources: dict[str, str], diagnosis: Path | None = None) -> list[dict]:
    history = []
    for path in sorted(root.glob("*/context.json")):
        try:
            context = json.loads(path.read_bytes(), object_pairs_hook=strict_pairs)
            if not isinstance(context["sourceHashes"], dict) or not context["runId"]:
                raise ValueError("invalid previous context")
        except (OSError, ValueError, KeyError) as error:
            raise SystemExit("NB prior run context is malformed; preserve and diagnose it") from error
        validation = path.with_name("validation.json")
        marker = json.loads(validation.read_text()) if validation.is_file() else {}
        executed = path.with_name("execution.json")
        passed = (marker.get("outcome") == "passed" and marker.get("runId") == context["runId"]
            and marker.get("sourceSha256") == digest(context["sourceHashes"]) and executed.is_file()
            and marker.get("reportSha256") == hashlib.sha256(executed.read_bytes()).hexdigest())
        record = {"runId": context["runId"], "context": str(path), "outcome": "passed" if passed else "failed_or_incomplete",
            "sourceSha256": digest(context["sourceHashes"]), "sourceChanged": context["sourceHashes"] != sources}
        if not passed and context["sourceHashes"] == sources:
            try:
                value = json.loads(diagnosis.read_bytes()) if diagnosis is not None else {}
                if (value.get("previousRun") != context["runId"] or value.get("sourceSha256") != digest(sources)
                        or not value.get("reason", "").strip() or not value.get("evidence")):
                    raise ValueError("missing reproducible diagnosis")
                for artifact, expected_hash in value["evidence"].items():
                    if hashlib.sha256(Path(artifact).read_bytes()).hexdigest() != expected_hash:
                        raise ValueError("diagnostic artifact changed")
            except (OSError, ValueError, AttributeError, TypeError) as error:
                raise SystemExit("NB retry on unchanged source requires a retained reproducible diagnosis; keep the failed run") from error
            record["diagnosis"] = str(diagnosis)
            record["diagnosisSha256"] = hashlib.sha256(diagnosis.read_bytes()).hexdigest()
        history.append(record)
    return history


def assert_native_bindings(bindings: dict, expected: set[str], root: Path, *, sources: dict[str, str], require_pass=False):
    if set(bindings) != expected:
        raise SystemExit("NB native release bindings do not match the due native variants")
    pending = []
    for variant, binding in bindings.items():
        try:
            path = root / binding["evidence"]
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("foreign native proof")
            report = json.loads(path.read_bytes())
            case = report["variants"][variant]
            if case["outcome"] == "awaiting_native_proof":
                pending.append(variant)
                continue
            ledger = json.loads((root / "docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json").read_bytes())
            if binding.get("transport") == "shared_appserver_v1":
                from tools.background_shared_native import assert_shared_case
                assert_shared_case(binding, variant, report, ledger, root, sources)
                continue
            attempt = next(row for row in ledger["attempts"] if row["id"] == case["attemptId"])
            pool = ledger["pools"][binding["pool"]]
            if (case["outcome"] != "passed" or case["layer"] != "native" or report["sourceHashes"] != sources
                    or attempt["pool"] != binding["pool"] or attempt["variant"] != variant or attempt["status"] != "passed"
                    or not pool["authorized"] or type(pool["cap"]) is not int or not 0 < pool["spent"] <= pool["cap"]
                    or not case["artifacts"]):
                raise ValueError("unproved native execution")
            for name, checksum in case["artifacts"].items():
                artifact = root / name
                if not artifact.resolve().is_relative_to(root.resolve()) or hashlib.sha256(artifact.read_bytes()).hexdigest() != checksum:
                    raise ValueError("native evidence changed")
            runtime_path = case["runtimeArtifact"]
            if runtime_path not in case["artifacts"]:
                raise ValueError("native runtime witness is not retained")
            runtime = json.loads((root / runtime_path).read_bytes())
            if (runtime["nativeStarted"] is not True or runtime["state"] != "completed" or runtime["error"] is not None
                    or type(runtime["nativePid"]) is not int or runtime["nativePid"] <= 0
                    or runtime["ownedPidsGone"] is not True or runtime["mcpListenerClosed"] is not True
                    or runtime["operationRemoved"] is not True or runtime["profileExclusionLost"] is not False
                    or runtime["toolCalls"] < 3):
                raise ValueError("native runtime or cleanup was not proved")
        except (OSError, KeyError, TypeError, ValueError, StopIteration) as error:
            raise SystemExit("NB native release proof is missing, stale or not an authorized native execution") from error
    if require_pass and pending:
        raise SystemExit("NB native release proof is pending: " + ", ".join(sorted(pending)))
    return pending


def assert_report(path: Path, *, run_id: str, suite: str, sources: dict[str, str], started_at: str,
        bindings: dict[str, list[str]], required_traces: dict[str, dict], required_actions: set[str],
        required_orders: set[str]) -> dict:
    report = read_report(path)
    if (not report.complete or report.exit_status != 0 or report.run_id != run_id or report.suite != suite
            or report.started_at != started_at or not report.finished_at
            or datetime.fromisoformat(report.finished_at.replace("Z", "+00:00")) <
                datetime.fromisoformat(report.started_at.replace("Z", "+00:00"))):
        raise SystemExit("NB report has an old/wrong run, suite or incomplete execution")
    if not sources or report.source_hashes != sources:
        raise SystemExit("NB report source hashes do not match the executed source")
    if not report.collected or len(set(report.collected)) != len(report.collected):
        raise SystemExit("NB report has empty/duplicate collection")
    expected = {node for nodes in bindings.values() for node in nodes}
    if not bindings or any(not nodes for nodes in bindings.values()) or not expected:
        raise SystemExit("NB bindings are empty")
    if any(not node.startswith(("tests/recovery/test_background_", "tests/foundation/test_runner_gates.py::"))
            and re.fullmatch(r"apps/web/unit/background-[A-Za-z0-9_-]+\.test\.ts::.+", node) is None
            for node in expected):
        raise SystemExit("NB binding is outside its required Python/Node suite")
    results = {}
    for item in report.records:
        if item.node_id in results:
            raise SystemExit("NB report contains duplicate or retry-only execution")
        results[item.node_id] = item
        if item.node_id not in report.collected:
            raise SystemExit("NB result was not collected in this run")
    if not expected <= set(report.collected) or set(report.collected) != results.keys():
        raise SystemExit("NB report is missing an exact variant/parameter/file")
    # A failure elsewhere in the same run is not erased by reporting only the required nodes.
    for item in results.values():
        if item.attempt != 1 or item.markers or item.phases != {"setup": "passed", "call": "passed", "teardown": "passed"}:
            raise SystemExit(f"NB execution did not pass every phase without retry: {item.node_id}")
    traces = {}
    for trace in report.traces:
        if trace.id in traces or trace.node_id not in results:
            raise SystemExit("NB trace is duplicate or has no executed owner")
        traces[trace.id] = trace
    if not required_traces.keys() <= traces.keys():
        raise SystemExit("NB report is missing required seed coverage")
    from spikes.background.corpus import reached_orders
    for identity, expected_trace in required_traces.items():
        trace = traces[identity]
        raw = trace.model_dump(by_alias=True, exclude={"node_id", "sha256"})
        if (digest(raw) != trace.sha256 or trace.seed != expected_trace["seed"] or trace.capacity != expected_trace["capacity"]
                or trace.transitions != expected_trace["transitions"] or len(trace.log) != trace.transitions
                or trace.scope != expected_trace["scope"] or trace.node_id != expected_trace["nodeId"]):
            raise SystemExit("NB trace has incorrect seed, source scope, length or hash")
        actions = {row.get("action") for row in trace.log if row.get("result") != "rejected"}
        orders = set(reached_orders(trace.log))
        if (not required_actions <= actions or not required_orders <= orders or set(trace.actions) != actions
                or set(trace.orders) != orders):
            raise SystemExit("NB report is missing required action/order coverage")
    return {variant: {"nodes": nodes, "outcome": "passed", "runId": run_id} for variant, nodes in bindings.items()}
