"""Check isolated agent and structured thread setup without any model turn."""

from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

from resume_api.agent.runtime import CodexAgentRuntime
from resume_api.cli.experimental_profile import BINARY
from resume_api.cli.process_runner import ProcessRunner
from resume_api.lifecycle import OperationFiles
from .appserver_offline import OfflineProfile, ProbeFinished, alive, validate_config, structured_features
from resume_api.agent.host_profile import APP_SERVER_PREFIX


def probe(root, evidence, label):
    root.mkdir(mode=0o700)
    profile = OfflineProfile(root / "empty-profile")
    ledger = Path("docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json")
    before = ledger.read_bytes()
    frames, responses, hosts, pids = [], [], [], []
    with ExitStack() as stack:
        turns = [stack.enter_context(OperationFiles(root / "turns").open()) for _ in range(3)]
        files = stack.enter_context(OperationFiles(root / "server").open())
        operation = files.path
        turn_paths = [turn.path for turn in turns]
        def encode(value):
            return json.dumps(value, separators=(",", ":")).encode() + b"\n"
        def thread(index):
            name = "foldcv_probe_" + str(index)
            request = {"id": 3 + index, "method": "thread/start", "params": {
                "model": "gpt-6-luna", "cwd": str(turn_paths[index]), "ephemeral": True,
                "allowProviderModelFallback": False, "approvalPolicy": "never", "approvalsReviewer": "user",
                "sandbox": "read-only", "baseInstructions": "Use only this synthetic probe context.",
                "developerInstructions": "Never invoke tools or a model during metadata setup.",
                "runtimeWorkspaceRoots": [], "environments": [], "config": {"web_search": "disabled"},
                "dynamicTools": [{"type": "namespace", "name": name, "description": name + " private synthetic tools",
                    "tools": [{"type": "function", "name": "read", "description": name + " synthetic read",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]}]}}
            if index == 2:
                request["params"]["dynamicTools"] = []
                request["params"]["config"]["features"] = structured_features()
            return request
        def accept(raw):
            if len(frames) >= 128:
                raise ValueError("Thread metadata frame bound exceeded")
            frame = json.loads(raw)
            frames.append(frame)
            if "method" in frame:
                if "id" in frame:
                    raise ValueError("A metadata-only probe requested an action")
                return None
            if "error" in frame:
                raise ValueError("Pinned metadata request failed: " + str(frame["error"]))
            identifier, result = frame.get("id"), frame.get("result")
            if identifier == 1:
                return encode({"method": "initialized"}) + encode({"id": 2, "method": "config/read", "params": {"includeLayers": True}})
            if identifier == 2:
                validate_config(result)
                return b"".join(encode(thread(index)) for index in range(3))
            if identifier in {3, 4, 5}:
                index = identifier - 3
                if (result.get("model") != "gpt-6-luna" or result.get("modelProvider") != "openai"
                        or result.get("approvalPolicy") != "never" or result.get("approvalsReviewer") != "user"
                        or result.get("sandbox", {}).get("type") != "readOnly" or result.get("instructionSources")
                        or result.get("runtimeWorkspaceRoots") or result.get("reasoningEffort") != "medium"
                        or result.get("cwd") != str(turn_paths[index])
                        or result.get("sandbox", {}).get("networkAccess") is not False
                        or result.get("thread", {}).get("ephemeral") is not True
                        or result.get("thread", {}).get("path") is not None):
                    raise ValueError("Pinned thread isolation metadata differs from the captured request")
                responses.append(result["thread"]["id"])
                if len(responses) == 3:
                    if len(set(responses)) != 3:
                        raise ValueError("Pinned threads share an identity")
                    raise ProbeFinished()
                return None
            raise ValueError("Unsolicited thread probe response")
        pid = None
        def ownership():
            pids.append(files.process.pid)
            hosts.extend(CodexAgentRuntime.check_owned_host(files))
        try:
            ProcessRunner(BINARY, launch=profile.launch).run(files,
                (*APP_SERVER_PREFIX, *profile.config(operation, allow_web=False)),
                data=encode({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "foldcv_thread_probe", "version": "1.0"},
                    "capabilities": {"experimentalApi": True}}}), on_line=accept,
                deadline=time.monotonic() + 30, cancel=threading.Event(), interactive=True,
                before_cleanup=ownership,
                max_line=2 * 1024 * 1024, max_output=4 * 1024 * 1024)
        except ProbeFinished:
            pass
        finally:
            pid = pids[0] if len(pids) == 1 else None
            (evidence / (label + "-frames.json")).write_text(json.dumps(frames, indent=2) + "\n")
    if ledger.read_bytes() != before or operation.exists() or any(path.exists() for path in turn_paths):
        raise ValueError("Probe changed the ledger or retained an operation")
    if len(responses) != 3 or pid is None or any(alive(number) for number in [pid, *hosts]):
        raise ValueError("Probe threads or owned cleanup are unproved")
    report = {"at": datetime.now(timezone.utc).isoformat(), "status": "pinned_thread_setup_passed",
        "networkDenied": True, "emptyProfile": True, "authenticatedProfileAccess": False,
        "threadIds": responses, "nativePid": pid, "hostPids": hosts, "ownedPidsGone": True,
        "operationsRemoved": True, "nativeLedgerUnchanged": True, "modelTurns": 0,
        "limitation": "Thread setup accepts separate namespaces and contexts. Actual tool routing, schema enforcement and overlap still require the authorized native matrix."}
    (evidence / (label + "-result.json")).write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.root, args.evidence, args.label)))
