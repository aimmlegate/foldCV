"""Offline, length-prefixed protocol probe for the pinned local companion."""

from __future__ import annotations

from contextlib import contextmanager
import argparse
import json
import os
from pathlib import Path
import selectors
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/api/src"), str(ROOT)]

from resume_api.lifecycle import OperationFiles
from resume_api.cli.experimental_profile import BINARY
from resume_api.cli.process_runner import ProcessRunner
from spikes.agent.profile import AgentProofProfile, APP_SERVER_PREFIX, CODE_MODE_HOST, check_host
from spikes.agent.proof import frame

READ_TOOL = {"name": "mcp__foldcv__get_resume_context",
             "tool_name": {"namespace": "foldcv", "name": "get_resume_context"},
             "description": "Read synthetic context.", "kind": "function",
             "input_schema": {"type": "object", "properties": {}}, "output_schema": None}


class HostClient:
    def __init__(self, files, profile):
        check_host()
        policy = profile._policy(files.path, APP_SERVER_PREFIX) + "\n(deny network*)"
        environment = {"PATH": os.defpath, "HOME": str(profile.home),
                       "CODEX_HOME": str(profile.codex_home), "TMPDIR": str(files.path),
                       "LANG": "en_US.UTF-8", "FOLDCV_SYNTHETIC_SECRET": "ENV_CANARY"}
        self.process = files.spawn(Path("/usr/bin/sandbox-exec"),
                                   ("-p", policy, str(CODE_MODE_HOST)), environment=environment)
        self.selector = selectors.DefaultSelector()
        self.buffer = bytearray()
        self.stderr = bytearray()
        self.stdout_bytes = 0
        self.events = []
        for stream, name in ((self.process.stdout, "stdout"), (self.process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, name)

    def send(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode()
        if len(raw) > 65536:
            raise RuntimeError("HOST_INPUT_LIMIT")
        self.process.stdin.write(struct.pack("<I", len(raw)) + raw)
        self.process.stdin.flush()

    def receive(self, *, seconds=5):
        deadline = time.monotonic() + seconds
        while True:
            if len(self.buffer) >= 4:
                size = struct.unpack("<I", self.buffer[:4])[0]
                if size > 65536:
                    raise RuntimeError("HOST_FRAME_LIMIT")
                if len(self.buffer) >= size + 4:
                    raw = bytes(self.buffer[4:size + 4])
                    del self.buffer[:size + 4]
                    return json.loads(raw)
            if time.monotonic() >= deadline:
                raise TimeoutError("HOST_DEADLINE")
            for key, _ in self.selector.select(max(0, deadline - time.monotonic())):
                raw = os.read(key.fileobj.fileno(), 4096)
                if not raw:
                    self.selector.unregister(key.fileobj)
                    if key.data == "stdout":
                        raise RuntimeError("HOST_CLOSED: " + self.stderr.decode(errors="replace")[:1000])
                    continue
                if key.data == "stdout":
                    self.stdout_bytes += len(raw)
                    self.buffer.extend(raw)
                else:
                    self.stderr.extend(raw)
                if self.stdout_bytes > 8 * 1024 * 1024 or len(self.stderr) > 256 * 1024:
                    raise RuntimeError("HOST_OUTPUT_LIMIT")

    def request(self, identifier, request):
        self.send({"type": "operation/request", "id": identifier, "request": request})
        return self.until(lambda value: value.get("type") == "operation/response"
                          and value.get("id") == identifier)

    def until(self, predicate, *, seconds=5):
        deadline = time.monotonic() + seconds
        while True:
            value = self.receive(seconds=max(0, deadline - time.monotonic()))
            if predicate(value):
                return value
            self.events.append(value)
            if len(self.events) > 128:
                raise RuntimeError("HOST_EVENT_LIMIT")

    def close(self):
        self.selector.close()

    def execute(self, identifier, source, *, tools=()):
        started = self.request(identifier, {"method": "session/execute", "sessionId": "proof",
                               "request": {"tool_call_id": "proof-" + str(identifier),
                                           "enabled_tools": list(tools), "source": source,
                                           "max_output_tokens": 2000}})
        if started["result"]["status"] != "ok":
            raise RuntimeError("HOST_EXECUTION_REJECTED")
        delegated = []
        deadline = time.monotonic() + 5
        while True:
            event = self.receive(seconds=max(0, deadline - time.monotonic()))
            if event.get("type") == "execute/initialResponse" and event.get("id") == identifier:
                return event["result"], delegated
            if event.get("type") == "delegate/request":
                invocation = event["request"].get("invocation")
                if (not invocation or invocation["tool_name"] != READ_TOOL["tool_name"]
                        or invocation["input"] != {} or READ_TOOL not in tools):
                    raise RuntimeError("HOST_FOREIGN_DELEGATE")
                delegated.append(invocation["tool_name"])
                self.send({"type": "delegate/response", "id": event["id"],
                           "result": {"status": "ok", "value": {"type": "tool/result",
                                      "result": {"text": "SYNTHETIC_RESUME", "revision": 1}}}})
            else:
                self.events.append(event)


def result_text(result):
    value = result["value"]["Result"]
    if result["status"] != "ok" or value["error_text"] is not None:
        raise RuntimeError("HOST_CELL_FAILED: " + str(value.get("error_text")))
    return "\n".join(item["text"] for item in value["content_items"] if item["type"] == "input_text")


def isolation_probe(root):
    report = {"nativeTurnStarts": 0, "networkDenied": True, "cases": []}
    with host_client(root) as client:
        pid = client.process.pid
        client.send({"type": "connection/hello", "supportedVersions": [1],
                     "requiredCapabilities": [], "optionalCapabilities": []})
        report["hello"] = client.receive()
        report["session"] = client.request(1, {"method": "session/open", "sessionId": "proof"})
        source = """const names = ['process', 'Deno', 'Bun', 'require', 'fetch', 'WebSocket', 'XMLHttpRequest'];
const globals = Object.fromEntries(names.map(name => [name, typeof globalThis[name]]));
const imports = {};
for (const name of ['node:fs', 'node:child_process', 'node:net', 'file:///synthetic-canary', 'http://127.0.0.1/']) {
  try { await import(name); imports[name] = 'ALLOWED'; } catch (error) { imports[name] = String(error); }
}
text({globals, imports, constructorProcess: typeof Function('return this')().process,
  tools: ALL_TOOLS.map(tool => tool.name)});"""
        result, delegated = client.execute(2, source)
        capabilities = json.loads(result_text(result))
        if (any(value != "undefined" for value in capabilities["globals"].values())
                or capabilities["constructorProcess"] != "undefined"
                or any(value == "ALLOWED" for value in capabilities["imports"].values())
                or capabilities["tools"] or delegated):
            raise RuntimeError("HOST_CAPABILITY_ESCAPE")
        report["cases"].append({"name": "filesystem_environment_process_network_denied", "result": capabilities})
        result, delegated = client.execute(3, "text(await tools.mcp__foldcv__get_resume_context({}));",
                                           tools=(READ_TOOL,))
        if json.loads(result_text(result)) != {"text": "SYNTHETIC_RESUME", "revision": 1} or len(delegated) != 1:
            raise RuntimeError("HOST_DECLARED_TOOL_FAILED")
        report["cases"].append({"name": "declared_tool_round_trip", "delegated": delegated})
        result, delegated = client.execute(4, "text({names: ALL_TOOLS.map(t => t.name), edit: typeof tools.prepare_edit_batch, web: typeof tools.web__run});")
        if json.loads(result_text(result)) != {"names": [], "edit": "undefined", "web": "undefined"} or delegated:
            raise RuntimeError("HOST_TOOL_CONFIGURATION_LEAK")
        report["cases"].append({"name": "undeclared_edit_and_web_tools_absent", "passed": True})
        report["stdoutBytes"] = client.stdout_bytes
        report["stderrBytes"] = len(client.stderr)
    report["ownedHostPid"] = pid
    report["hostStopped"] = not process_alive(pid)
    report["operationDirectoryRemoved"] = not any((root / "host-operations").glob("op-*"))
    if not report["hostStopped"] or not report["operationDirectoryRemoved"]:
        raise RuntimeError("HOST_CLEANUP_FAILED")
    return report


def process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def lifecycle_probe(root):
    result = {"nativeTurnStarts": 0}
    with host_client(root) as client:
        pid = client.process.pid
        client.send({"type": "connection/hello", "supportedVersions": [1],
                     "requiredCapabilities": [], "optionalCapabilities": []})
        client.receive()
        client.request(1, {"method": "session/open", "sessionId": "proof",
                           "cellExecutionLimits": {"maxYieldTimeMs": 100}})
        client.request(2, {"method": "session/execute", "sessionId": "proof", "request": {
            "tool_call_id": "busy-cell", "enabled_tools": [], "source": "while (true) {}",
            "max_output_tokens": 100}})
        initial = client.until(lambda event: event.get("type") == "execute/initialResponse")
        result["activeCell"] = initial
        started = time.monotonic()
        result["terminate"] = client.request(3, {"method": "session/terminate",
                                                 "sessionId": "proof", "cellId": "1"})
        result["terminateSeconds"] = round(time.monotonic() - started, 4)
    result["cancelledHostStopped"] = not process_alive(pid)
    with host_client(root) as client:
        pid = client.process.pid
        client.send({"type": "unexpected-hello"})
        try:
            client.receive()
        except RuntimeError as error:
            result["invalidHelloRejected"] = str(error).startswith("HOST_CLOSED")
        else:
            raise RuntimeError("HOST_INVALID_HELLO_ACCEPTED")
    result["failedHostStopped"] = not process_alive(pid)
    result["operationsRemoved"] = not any((root / "host-operations").glob("op-*"))
    if not all(result[name] for name in ("cancelledHostStopped", "invalidHelloRejected",
                                        "failedHostStopped", "operationsRemoved")):
        raise RuntimeError("HOST_LIFECYCLE_FAILED")
    return result


def prewarm_probe(root):
    import threading
    profile = AgentProofProfile(root / "profile")
    result = {"nativeTurnStarts": 0, "networkDenied": True, "notifications": []}
    owned_children = []

    def launch(executable, arguments, operation):
        wrapper, command, environment = profile.launch(executable, arguments, operation)
        environment["RUST_LOG"] = "codex_code_mode_client=trace,codex_core::code_mode=trace"
        return wrapper, (command[0], command[1] + "\n(deny network*)", *command[2:]), environment

    with OperationFiles(root / "prewarm-operations").open() as files:
        def accept(raw):
            message = json.loads(raw)
            if "method" in message:
                result["notifications"].append(message["method"])
                return None
            if "error" in message:
                raise RuntimeError("HOST_PREWARM_RPC_FAILED")
            if message["id"] == 0:
                return b'{"method":"initialized"}\n' + frame(1, "thread/start", {
                    "model": "gpt-6-luna", "cwd": str(files.path), "ephemeral": True,
                    "allowProviderModelFallback": False, "sandbox": "read-only",
                    "approvalPolicy": "never", "approvalsReviewer": "user",
                    "baseInstructions": "Synthetic offline host proof.", "environments": []})
            if message["id"] == 1:
                result["threadStarted"] = message["result"]["thread"]["ephemeral"]
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    rows = subprocess.check_output(["/bin/ps", "-axo", "pid=,ppid=,command="], text=True)
                    for row in rows.splitlines():
                        parts = row.strip().split(None, 2)
                        if len(parts) == 3 and int(parts[1]) == files.process.pid:
                            if parts[2] != str(CODE_MODE_HOST):
                                raise RuntimeError("HOST_UNEXPECTED_CHILD")
                            owned_children.append(int(parts[0]))
                    if owned_children:
                        break
                    time.sleep(0.02)
                if not owned_children:
                    raise RuntimeError("HOST_PREWARM_NOT_STARTED")
                time.sleep(0.1)
                result["hostChildRunning"] = all(process_alive(pid) for pid in owned_children)
                return b""
            return None

        started = time.monotonic()
        _, stderr = ProcessRunner(BINARY, launch=launch).run(
            files, (*APP_SERVER_PREFIX, *profile.config(files.path),
                    "--config", "features.code_mode_prewarm=true"),
            data=frame(0, "initialize", {"clientInfo": {"name": "foldcv-offline-host", "version": "1"},
                                       "capabilities": {"experimentalApi": True, "requestAttestation": False}}),
            interactive=True, on_line=accept, cancel=threading.Event(), deadline=started + 15)
        result["stderr"] = stderr.decode(errors="replace")
        result["elapsedSeconds"] = round(time.monotonic() - started, 4)
        traces = []
        for path in (files.path / "logs").glob("**/*"):
            if path.is_file() and path.stat().st_size <= 262144:
                traces.extend(line for line in path.read_text(errors="replace").splitlines()
                              if "code_mode" in line.lower() or "prewarm" in line.lower())
        result["hostTraces"] = traces[:30]
    deadline = time.monotonic() + 5
    while any(process_alive(pid) for pid in owned_children) and time.monotonic() < deadline:
        time.sleep(0.02)
    result["ownedHostChildrenStopped"] = all(not process_alive(pid) for pid in owned_children)
    result["operationDirectoryRemoved"] = not any((root / "prewarm-operations").glob("op-*"))
    if not result["ownedHostChildrenStopped"] or not result["operationDirectoryRemoved"]:
        raise RuntimeError("HOST_PREWARM_CLEANUP_FAILED")
    return result


@contextmanager
def host_client(root):
    profile = AgentProofProfile(root / "profile")
    profile.prepare()
    with OperationFiles(root / "host-operations").open() as files:
        client = HostClient(files, profile)
        try:
            yield client
        finally:
            client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    args.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    results = {"isolation": isolation_probe(args.root), "lifecycle": lifecycle_probe(args.root),
               "appServer": prewarm_probe(args.root)}
    (args.root / "host-proof.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
