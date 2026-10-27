"""Inspect effective pinned configuration in a network-denied empty profile."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from resume_api.cli.experimental_profile import BINARY
from resume_api.cli.process_runner import ProcessRunner
from resume_api.lifecycle import OperationFiles
from resume_api.agent.host_profile import AgentProofProfile, APP_SERVER_PREFIX, CODE_MODE_HOST
from resume_api.cli.profile import DISABLED_FEATURES


class ProbeFinished(Exception):
    pass


class OfflineProfile(AgentProofProfile):
    def _policy(self, operation, args):
        return super()._policy(operation, args) + "\n(deny network*)"


def structured_features():
    return {**dict.fromkeys(DISABLED_FEATURES, False), "code_mode_prewarm": False,
        "guardian_approval": False, "skip_host_skill_discovery": True}


def validate_config(result):
    config = result.get("config", {})
    features = config.get("features", {})
    enabled = {"code_mode", "code_mode_host"}
    if (config.get("mcp_servers", {}) != {} or config.get("model_provider") != "openai"
            or config.get("forced_login_method") != "chatgpt" or config.get("model_providers")
            or config.get("openai_base_url") is not None or config.get("project_doc_max_bytes") != 0
            or config.get("model_instructions_file") is not None or config.get("developer_instructions") != ""
            or config.get("history", {}).get("persistence") != "none" or config.get("web_search") != "disabled"
            or any(features.get(name) is not False for name in DISABLED_FEATURES if name not in enabled)
            or any(features.get(name) is not True for name in (*enabled, "code_mode_prewarm", "skip_host_skill_discovery"))
            or features.get("guardian_approval") is not False
            or any(layer.get("name", {}).get("type") != "sessionFlags" and layer.get("config")
                for layer in result.get("layers", []))):
        raise ValueError("Effective configuration does not isolate tools and discovery")
    return config


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def probe(root: Path, evidence: Path):
    root.mkdir(mode=0o700)
    profile = OfflineProfile(root / "empty-profile")
    ledger = Path("docs/gui/handoffs/BACKGROUND-WORK/native-attempts.json")
    before = ledger.read_bytes()
    frames, native_pids, host_pids = [], [], []
    captured = {}
    operation = None
    with OperationFiles(root / "operations").open() as files:
        operation = files.path
        arguments = (*APP_SERVER_PREFIX, *profile.config(operation, allow_web=False))
        def encode(value):
            return json.dumps(value, separators=(",", ":")).encode() + b"\n"
        def on_line(raw):
            if len(frames) >= 64:
                raise ValueError("Offline metadata frame bound exceeded")
            frame = json.loads(raw)
            frames.append(frame)
            if "method" in frame:
                if "id" in frame:
                    return encode({"id": frame["id"], "error": {"code": -32601, "message": "Offline probe denies requests"}})
                return None
            if frame.get("error") is not None:
                raise ValueError("Offline metadata request failed: " + str(frame["error"]))
            if frame.get("id") == 1:
                return encode({"method": "initialized", "params": {}}) + encode({"id": 2, "method": "config/read", "params": {"includeLayers": True}})
            if frame.get("id") == 2:
                captured.update(frame["result"])
                validate_config(captured)
                raise ProbeFinished()
            raise ValueError("Unsolicited offline response")
        def ownership():
            native_pids.append(files.process.pid)
            rows = subprocess.check_output(["ps", "-axo", "pid=,ppid=,command="], text=True)
            children = [parts for line in rows.splitlines() if len(parts := line.strip().split(None, 2)) == 3
                and int(parts[1]) == files.process.pid]
            if any(parts[2] != str(CODE_MODE_HOST) for parts in children):
                raise ValueError("Unexpected offline child")
            host_pids.extend(int(parts[0]) for parts in children)
        try:
            ProcessRunner(BINARY, launch=profile.launch).run(files, arguments,
                data=encode({"id": 1, "method": "initialize", "params": {
                    "clientInfo": {"name": "foldcv_offline_protocol", "version": "1.0"},
                    "capabilities": {"experimentalApi": True}}}),
                deadline=time.monotonic() + 20, cancel=threading.Event(), on_line=on_line,
                interactive=True, before_cleanup=ownership, max_output=2 * 1024 * 1024,
                max_line=2 * 1024 * 1024)
        except ProbeFinished:
            pass
        finally:
            (evidence / "effective-config-frames.json").write_text(json.dumps(frames, indent=2) + "\n")
    assert ledger.read_bytes() == before
    if not captured or operation.exists() or any(alive(pid) for pid in [*native_pids, *host_pids]):
        raise ValueError("Offline probe did not close its owned resources")
    report = dict(at=datetime.now(timezone.utc).isoformat(), status="effective_config_passed",
        networkDenied=True, emptyProfile=True, authenticatedProfileAccess=False, modelTurns=0,
        threadStarts=0, nativePids=native_pids, hostPids=host_pids, ownedPidsGone=True,
        operationRemoved=True, nativeLedgerUnchanged=True,
        limitation="No model, thread tool-routing or native overlap evidence; scripted and native gates remain.")
    (evidence / "effective-config-result.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(probe(options.root, options.evidence)))
