#!/usr/bin/env python3
"""Run a text-only code review through T3's installed Antigravity ACP agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid


MODEL = "gemini-3.8-flash-medium"
MAX_LINE_BYTES = 256_000
AUTH_PREFIX = b"Open the following link to authenticate the ACP server: "
DROP_ENV = {
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_QUOTA_PROJECT",
    "GOOGLE_GENAI_USE_VERTEXAI", "GCLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT",
    "AGY_ACP_CCPA_PROJECT", "AGY_ACP_ENABLE_OAUTH", "GEMINI_HOME",
    "AGY_ACP_FORCE_FILE_STORAGE", "ANTIGRAVITY_HARNESS_PATH", "BROWSER",
    "PYTHONUNBUFFERED", "ELECTRON_RUN_AS_NODE",
}


class ReviewError(Exception):
    def __init__(self, code: str, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def _json_file(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewError("PROTOCOL_ERROR", f"Cannot read {path.name} metadata.") from exc
    if not isinstance(value, dict):
        raise ReviewError("PROTOCOL_ERROR", f"Invalid {path.name} metadata.")
    return value


def _profile_safe(profile: Path) -> None:
    if (profile / "config").is_symlink():
        raise ReviewError("UNSAFE_PROFILE", "Antigravity profile has unsafe config directory.")
    for name, section in (("hooks.json", "hooks"), ("mcp_config.json", "mcpServers")):
        path = profile / "config" / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000:
            raise ReviewError("UNSAFE_PROFILE", f"Antigravity profile has unsafe {name} configuration.")
        value = _json_file(path)
        configured = value.get(section, value)
        if not isinstance(configured, dict) or configured:
            raise ReviewError("UNSAFE_PROFILE", f"Antigravity profile has active {name} configuration.")


def discover(t3_home: Path) -> tuple[Path, Path, Path]:
    settings = _json_file(t3_home / "userdata" / "settings.json")
    instance = settings.get("providerInstances", {}).get("antigravity")
    if not isinstance(instance, dict) or instance.get("driver") != "antigravity" or instance.get("enabled") is not True:
        raise ReviewError("AUTH_REQUIRED", "T3 Antigravity is not enabled.")
    config = instance.get("config", {})
    if not isinstance(config, dict) or config.get("authMethod") != "oauth-personal":
        raise ReviewError("AUTH_REQUIRED", "T3 Antigravity must use personal Google sign-in.")
    if config.get("binaryPath") or instance.get("environment"):
        raise ReviewError("UNSAFE_PROFILE", "Custom Antigravity runtime or environment is unsupported.")
    key = hashlib.sha256(b"antigravity").hexdigest()
    profile = t3_home / "userdata" / "providers" / "antigravity" / key
    if not profile.is_dir() or profile.is_symlink():
        raise ReviewError("AUTH_REQUIRED", "T3 Antigravity profile is missing.")
    _profile_safe(profile)
    profile_settings = _json_file(profile / "antigravity-acp" / "settings.json")
    if profile_settings.get("auth", {}).get("type") != "oauth-personal":
        raise ReviewError("AUTH_REQUIRED", "T3 Antigravity profile is not using personal Google sign-in.")
    platform = "darwin-arm64" if sys.platform == "darwin" and os.uname().machine == "arm64" else None
    if platform is None:
        raise ReviewError("MODEL_UNAVAILABLE", "This adapter requires the installed macOS arm64 runtime.")
    managed = t3_home / "tools" / "antigravity-acp" / platform
    active = _json_file(managed / "active.json")
    release_id = active.get("releaseId")
    if not isinstance(release_id, str) or not re.fullmatch(r"[a-f0-9]{64}", release_id):
        raise ReviewError("PROTOCOL_ERROR", "Invalid Antigravity release metadata.")
    release = managed / "versions" / release_id
    binary = release / "agy_acp_server.par"
    harness = release / "localharness_external"
    if not binary.is_file() or not harness.is_file() or not os.access(binary, os.X_OK) or not os.access(harness, os.X_OK):
        raise ReviewError("PROTOCOL_ERROR", "Installed Antigravity runtime is incomplete.")
    return profile, binary, harness


def _environment(profile: Path, harness: Path, temp_dir: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key.upper() not in DROP_ENV}
    environment.update({
        "GEMINI_HOME": str(profile),
        "AGY_ACP_FORCE_FILE_STORAGE": "1",
        "ANTIGRAVITY_HARNESS_PATH": str(harness),
        "BROWSER": "/usr/bin/false",
        "PYTHONUNBUFFERED": "1",
        "ELECTRON_RUN_AS_NODE": "1",
        "TMPDIR": str(temp_dir),
    })
    return environment


def _error_from_rpc(error: object) -> ReviewError:
    if not isinstance(error, dict):
        return ReviewError("PROTOCOL_ERROR", "Antigravity returned an invalid ACP error.")
    message = str(error.get("message", ""))[:1000]
    data = error.get("data")
    status = data.get("status") if isinstance(data, dict) else None
    detail = data.get("code") if isinstance(data, dict) else None
    evidence = " ".join(str(part) for part in (message, status, detail) if part is not None)
    retry = None
    if isinstance(data, dict):
        candidate = data.get("retry_after", data.get("retryAfter"))
        if isinstance(candidate, (str, int, float)) and len(str(candidate)) <= 80:
            retry = str(candidate)
    if re.search(r"RESOURCE_EXHAUSTED|QUOTA_EXCEEDED|RATE_LIMITED|\b429\b", evidence, re.I):
        return ReviewError("QUOTA_EXHAUSTED", "Antigravity reported a quota limit.", retry)
    if error.get("code") == -32000 or re.search(r"AUTH_REQUIRED|UNAUTHENTICATED|SIGN.IN.REQUIRED|SUBSCRIPTION_REQUIRED", evidence, re.I):
        return ReviewError("AUTH_REQUIRED", "Antigravity requires personal Google sign-in.")
    if re.search(r"MODEL_NOT_FOUND|MODEL_UNAVAILABLE|UNSUPPORTED_MODEL", evidence, re.I):
        return ReviewError("MODEL_UNAVAILABLE", "The selected Antigravity model is unavailable.")
    return ReviewError("PROTOCOL_ERROR", "Antigravity returned an ACP error.")


class AcpClient:
    def __init__(self, process: subprocess.Popen[bytes], timeout: int, max_output_bytes: int):
        self.process = process
        self.deadline = time.monotonic() + timeout
        self.max_output_bytes = max_output_bytes
        self.max_wire_bytes = max(2_000_000, max_output_bytes * 8)
        self.messages: queue.Queue[object] = queue.Queue(maxsize=16)
        self.next_id = 1
        self.session_id: str | None = None
        self.chunks: list[str] = []
        self.output_bytes = 0
        self.tool_attempt = False
        self.startup_updates: list[dict] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        wire_bytes = 0
        try:
            while True:
                line = self.process.stdout.readline(MAX_LINE_BYTES + 1)
                if not line:
                    self.messages.put(EOFError())
                    return
                if len(line) > MAX_LINE_BYTES:
                    self.messages.put(ReviewError("PROTOCOL_ERROR", "ACP message exceeded the size limit."))
                    return
                wire_bytes += len(line)
                if wire_bytes > self.max_wire_bytes:
                    self.messages.put(ReviewError("PROTOCOL_ERROR", "ACP traffic exceeded the size limit."))
                    return
                if line.startswith(AUTH_PREFIX):
                    self.messages.put(ReviewError("AUTH_REQUIRED", "Antigravity requires personal Google sign-in."))
                    return
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    self.messages.put(ReviewError("PROTOCOL_ERROR", "Antigravity sent invalid ACP JSON."))
                    return
        except OSError:
            self.messages.put(EOFError())

    def _drain_stderr(self) -> None:
        try:
            while self.process.stderr.read(8192):
                pass
        except OSError:
            pass

    def _send(self, value: dict) -> None:
        data = (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ReviewError("PROTOCOL_ERROR", "Antigravity ACP connection closed.") from exc

    def _callback(self, message: dict) -> None:
        self.tool_attempt = True
        method = message["method"]
        if method == "session/request_permission":
            result = {"outcome": {"outcome": "cancelled"}}
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})
        elif method == "session/elicitation":
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": {"action": {"action": "decline"}}})
        else:
            self._send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Tools and user input are disabled."}})
        raise ReviewError("PROTOCOL_ERROR", "Antigravity requested a tool or user input.")

    def _notification(self, message: dict) -> None:
        if message.get("method") != "session/update":
            return
        params = message.get("params")
        if not isinstance(params, dict):
            raise ReviewError("PROTOCOL_ERROR", "Antigravity sent an invalid session update.")
        if self.session_id is None:
            self.startup_updates.append(message)
            return
        if params.get("sessionId") != self.session_id:
            raise ReviewError("PROTOCOL_ERROR", "Antigravity sent an update for another session.")
        update = params.get("update")
        if not isinstance(update, dict):
            raise ReviewError("PROTOCOL_ERROR", "Antigravity sent an invalid session update.")
        kind = update.get("sessionUpdate")
        if kind in ("tool_call", "tool_call_update"):
            self.tool_attempt = True
            raise ReviewError("PROTOCOL_ERROR", "Antigravity attempted tool work.")
        if kind == "agent_message_chunk":
            content = update.get("content")
            if isinstance(content, dict) and content.get("type") == "text" and isinstance(content.get("text"), str):
                chunk = content["text"]
                self.output_bytes += len(chunk.encode("utf-8"))
                if self.output_bytes > self.max_output_bytes:
                    raise ReviewError("PROTOCOL_ERROR", "Antigravity response exceeded the output limit.")
                self.chunks.append(chunk)

    def request(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise ReviewError("TIMEOUT", "Antigravity request timed out.")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise ReviewError("TIMEOUT", "Antigravity request timed out.") from exc
            if isinstance(message, ReviewError):
                raise message
            if isinstance(message, EOFError):
                raise ReviewError("PROTOCOL_ERROR", "Antigravity ACP connection closed early.")
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ReviewError("PROTOCOL_ERROR", "Antigravity sent an invalid ACP message.")
            if "method" in message:
                if "id" in message:
                    self._callback(message)
                else:
                    self._notification(message)
                continue
            if type(message.get("id")) is not int or message["id"] != request_id:
                raise ReviewError("PROTOCOL_ERROR", "Antigravity sent a mismatched or duplicate ACP response.")
            if ("result" in message) == ("error" in message):
                raise ReviewError("PROTOCOL_ERROR", "Antigravity sent an invalid ACP response.")
            if "error" in message:
                raise _error_from_rpc(message["error"])
            result = message["result"]
            if not isinstance(result, dict):
                raise ReviewError("PROTOCOL_ERROR", "Antigravity sent an invalid ACP result.")
            return result


def _model_options(setup: dict) -> set[str]:
    offered: set[str] = set()
    for option in setup.get("configOptions", []):
        if not isinstance(option, dict) or option.get("id") != "model" or option.get("type") != "select":
            continue
        for entry in option.get("options", []):
            if not isinstance(entry, dict):
                continue
            if isinstance(entry.get("value"), str):
                offered.add(entry["value"])
            for child in entry.get("options", []):
                if isinstance(child, dict) and isinstance(child.get("value"), str):
                    offered.add(child["value"])
    return offered


def _cleanup_session(profile: Path, session_id: str | None, cwd: Path) -> None:
    try:
        if not session_id or uuid.UUID(session_id).version != 4:
            return
        root = profile / "antigravity-acp"
        base = root / "conversations" / session_id
        meta = base.with_suffix(".meta")
        if _json_file(meta).get("cwd") != str(cwd):
            return
        for suffix in (".db", ".db-wal", ".db-shm", ".db-journal", ".meta"):
            base.with_suffix(suffix).unlink(missing_ok=True)
        shutil.rmtree(root / "brain" / session_id, ignore_errors=True)
    except (ReviewError, OSError, ValueError):
        pass


def run(mode: str, t3_home: Path, model: str, prompt: str | None, timeout: int, max_output_bytes: int, *,
        installation: tuple[Path, Path, Path] | None = None) -> dict:
    if model != MODEL:
        raise ReviewError("MODEL_UNAVAILABLE", "Only gemini-3.8-flash-medium is supported.")
    profile, binary, harness = installation or discover(t3_home)
    with tempfile.TemporaryDirectory(prefix="devloop-antigravity-") as temporary, \
            tempfile.TemporaryDirectory(prefix="devloop-antigravity-runtime-") as runtime_temporary:
        cwd = Path(temporary)
        runtime_temp = Path(runtime_temporary)
        process = subprocess.Popen(
            [str(binary)], cwd=cwd, env=_environment(profile, harness, runtime_temp),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        client = AcpClient(process, timeout, max_output_bytes)
        try:
            initialized = client.request("initialize", {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
                "clientInfo": {"name": "foldcv-devloop-review", "version": "1.0.0"},
            })
            if initialized.get("protocolVersion") != 1 or initialized.get("agentInfo", {}).get("name") != "antigravity-acp":
                raise ReviewError("PROTOCOL_ERROR", "Unexpected Antigravity ACP agent.")
            methods = initialized.get("authMethods", [])
            if not any(isinstance(item, dict) and item.get("id") == "oauth-personal" for item in methods):
                raise ReviewError("AUTH_REQUIRED", "Personal Google sign-in is unavailable.")
            client.request("authenticate", {"methodId": "oauth-personal"})
            setup = client.request("session/new", {"cwd": str(cwd), "mcpServers": []})
            session_id = setup.get("sessionId")
            try:
                if not isinstance(session_id, str) or uuid.UUID(session_id).version != 4:
                    raise ValueError()
            except ValueError as exc:
                raise ReviewError("PROTOCOL_ERROR", "Antigravity returned an invalid session ID.") from exc
            client.session_id = session_id
            for update in client.startup_updates:
                client._notification(update)
            client.startup_updates.clear()
            mode_result = client.request("session/set_config_option", {
                "sessionId": session_id, "configId": "mode", "value": "default",
            })
            if not any(isinstance(option, dict) and option.get("id") == "mode" and option.get("currentValue") == "default"
                       for option in mode_result.get("configOptions", [])):
                raise ReviewError("PROTOCOL_ERROR", "Antigravity did not select the restricted mode.")
            if model not in _model_options(setup):
                raise ReviewError("MODEL_UNAVAILABLE", "The Google account does not offer gemini-3.8-flash-medium.")
            selected = client.request("session/set_config_option", {
                "sessionId": session_id, "configId": "model", "value": model,
            })
            if not any(isinstance(option, dict) and option.get("id") == "model" and option.get("currentValue") == model
                       for option in selected.get("configOptions", [])):
                raise ReviewError("MODEL_UNAVAILABLE", "Antigravity did not select gemini-3.8-flash-medium.")
            if mode == "probe":
                return {"status": "ready", "model": model, "auth_mode": "oauth-personal"}
            review_prompt = "Use only the input below. Do not use tools, read or write files, run commands, or ask questions.\n\n" + prompt
            result = client.request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": review_prompt}]})
            if client.tool_attempt:
                raise ReviewError("PROTOCOL_ERROR", "Antigravity attempted tool work.")
            if result.get("stopReason") != "end_turn":
                raise ReviewError("PROTOCOL_ERROR", "Antigravity did not complete the review.")
            response = "".join(client.chunks).strip()
            if not response:
                raise ReviewError("PROTOCOL_ERROR", "Antigravity returned an empty review.")
            if any(cwd.iterdir()):
                raise ReviewError("PROTOCOL_ERROR", "Antigravity wrote files during the review.")
            usage = result.get("usage")
            return {"status": "completed", "response": response, "usage": usage if isinstance(usage, dict) else None, "model": model}
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    process.kill()
                process.wait()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            _cleanup_session(profile, client.session_id, cwd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("probe", "review"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--t3-home", type=Path, default=Path.home() / ".t3")
        sub.add_argument("--model", default=MODEL, required=command == "review")
        if command == "review":
            sub.add_argument("--prompt-file", required=True, type=Path)
            sub.add_argument("--timeout", type=int, default=300)
            sub.add_argument("--max-output-bytes", type=int, default=128_000)
    args = parser.parse_args(argv)
    try:
        model = getattr(args, "model", MODEL)
        timeout = getattr(args, "timeout", 30)
        max_output = getattr(args, "max_output_bytes", 128_000)
        if timeout < 1 or timeout > 900 or max_output < 1 or max_output > 1_000_000:
            raise ReviewError("PROTOCOL_ERROR", "Invalid time or output limit.")
        prompt = None
        if args.command == "review":
            prompt = args.prompt_file.read_text(encoding="utf-8")
            if not prompt.strip() or len(prompt.encode("utf-8")) > 1_000_000:
                raise ReviewError("PROTOCOL_ERROR", "Prompt file is empty or too large.")
        envelope = run(args.command, args.t3_home, model, prompt, timeout, max_output)
        status = 0
    except ReviewError as exc:
        error = {"code": exc.code, "message": str(exc)}
        if exc.retry_after is not None:
            error["retry_after"] = exc.retry_after
        envelope = {"status": "failed", "error": error}
        status = 1
    except (OSError, UnicodeError, KeyboardInterrupt):
        envelope = {"status": "failed", "error": {"code": "PROTOCOL_ERROR", "message": "Antigravity review could not start or was interrupted."}}
        status = 1
    except Exception:
        envelope = {"status": "failed", "error": {"code": "PROTOCOL_ERROR", "message": "Antigravity returned invalid setup data."}}
        status = 1
    print(json.dumps(envelope, ensure_ascii=False))
    return status


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda _signal, _frame: (_ for _ in ()).throw(KeyboardInterrupt()))
    raise SystemExit(main())
