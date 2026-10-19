"""Metadata-only Codex connection using the owned process lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time

from packages.resume_core.reasoning import ModelReasoning, model_reasoning
from resume_api.cli.process_runner import ProcessExit, ProcessRunner
from resume_api.cli.experimental_profile import ExperimentalCliProfile, ExperimentalProfileError, VERSION as EXPERIMENTAL_VERSION
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.providers.codex_cli import MODEL, strict_json
from spikes.cli.profile import VERSION, overrides


MAX_MODELS = 100
PLAN = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")


class ConnectionFailure(Exception):
    def __init__(self, code: str, version: str | None = None):
        super().__init__(code)
        self.code = code
        self.version = version


@dataclass(frozen=True)
class Quota:
    state: str = "unknown"
    used_percent: float | None = None
    resets_at: int | None = None


@dataclass(frozen=True)
class Metadata:
    version: str
    models: tuple[str, ...]
    plan: str | None
    quota: Quota
    reasoning: dict[str, ModelReasoning] = field(default_factory=dict)


def quota_from_result(raw: object) -> Quota:
    if not isinstance(raw, dict):
        raise ConnectionFailure("METADATA_FAILED")
    bucket = raw.get("rateLimits")
    if bucket is None:
        return Quota()
    if not isinstance(bucket, dict):
        raise ConnectionFailure("METADATA_FAILED")
    reached = bucket.get("rateLimitReachedType")
    if reached is not None and (not isinstance(reached, str) or not PLAN.fullmatch(reached)):
        raise ConnectionFailure("METADATA_FAILED")
    spend_reached = bucket.get("spendControlReached")
    if spend_reached is not None and type(spend_reached) is not bool:
        raise ConnectionFailure("METADATA_FAILED")
    windows = [bucket.get("primary"), bucket.get("secondary")]
    parsed: list[tuple[float, int | None]] = []
    for window in windows:
        if window is None:
            continue
        if not isinstance(window, dict):
            raise ConnectionFailure("METADATA_FAILED")
        used = window.get("usedPercent")
        reset = window.get("resetsAt")
        if (isinstance(used, bool) or not isinstance(used, (int, float)) or
                not math.isfinite(used) or not 0 <= used <= 100 or
                (reset is not None and (type(reset) is not int or not 0 <= reset <= 4_102_444_800))):
            raise ConnectionFailure("METADATA_FAILED")
        parsed.append((float(used), reset))
    if reached is not None or spend_reached is True or any(used >= 100 for used, _ in parsed):
        return Quota("exhausted", max((used for used, _ in parsed), default=None),
                     min((reset for _, reset in parsed if reset is not None), default=None))
    if parsed:
        return Quota("available", max(used for used, _ in parsed),
                     min((reset for _, reset in parsed if reset is not None), default=None))
    return Quota()


class ConnectionAdapter:
    def __init__(self, executable: Path | None = None, *, allow_fixture: bool = False,
                 node_executable: Path | None = None,
                 experimental_profile: ExperimentalCliProfile | None = None):
        selected = executable if executable is not None else shutil.which("codex")
        self.executable = Path(selected).absolute() if selected is not None else None
        self.allow_fixture = allow_fixture
        self.node_executable = node_executable
        self.experimental_profile = experimental_profile

    def _launcher(self) -> tuple[Path, tuple[str, ...]]:
        if self.executable is None or not self.executable.is_file():
            raise ConnectionFailure("CLI_MISSING")
        try:
            with self.executable.open("rb") as source:
                shebang = source.readline(128).rstrip(b"\r\n")
        except OSError:
            raise ConnectionFailure("CLI_MISSING") from None
        if shebang == b"#!/usr/bin/env node":
            selected = self.node_executable or shutil.which("node")
            if selected is None:
                raise ConnectionFailure("CLI_LAUNCH_UNSUPPORTED")
            try:
                node = Path(selected).resolve(strict=True)
                if node.name != "node" or not node.is_file() or not os.access(node, os.X_OK):
                    raise ConnectionFailure("CLI_LAUNCH_UNSUPPORTED")
            except (OSError, RuntimeError):
                raise ConnectionFailure("CLI_LAUNCH_UNSUPPORTED") from None
            return node, (str(self.executable),)
        if shebang.startswith(b"#!/usr/bin/env ") and b"node" in shebang.split():
            raise ConnectionFailure("CLI_LAUNCH_UNSUPPORTED")
        return self.executable, ()

    def _run(self, files: OperationFiles, args: tuple[str, ...], cancel: threading.Event,
             deadline: float, **kwargs: object) -> tuple[bytes, bytes]:
        launcher, prefix = self._launcher()
        try:
            return ProcessRunner(launcher, launch=self.experimental_profile.launch
                                 if self.experimental_profile is not None else None).run(files, (*prefix, *args), cancel=cancel,
                                                      deadline=deadline, **kwargs)
        except ExperimentalProfileError as error:
            raise ConnectionFailure(str(error)) from None
        except ProcessExit as error:
            if args == ("login", "status") and (error.stdout + error.stderr).strip().lower() == b"not logged in":
                raise ConnectionFailure("LOGIN_REQUIRED") from None
            raise ConnectionFailure("CLI_FAILED") from None
        except SpikeError as error:
            raise ConnectionFailure(error.code if error.code in {"CLI_MISSING", "CANCELLED", "DEADLINE_EXCEEDED",
                                                                  "PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "TEMP_FAILED"}
                                    else "CLI_FAILED") from None

    def version(self, files: OperationFiles, cancel: threading.Event, deadline: float) -> str:
        raw, _ = self._run(files, ("--version",), cancel, deadline)
        try:
            version = raw.decode("utf-8", "strict").strip()
        except UnicodeError:
            raise ConnectionFailure("UNSUPPORTED_VERSION") from None
        expected = EXPERIMENTAL_VERSION if self.experimental_profile is not None else VERSION
        if len(version) > 80 or version != expected and not (self.allow_fixture and version == VERSION + "-fixture"):
            raise ConnectionFailure("UNSUPPORTED_VERSION", version if len(version) <= 80 else None)
        return version

    def login_status(self, files: OperationFiles, cancel: threading.Event, deadline: float) -> None:
        stdout, stderr = self._run(files, ("login", "status"), cancel, deadline)
        status = (stdout + stderr).strip().lower()
        if b"api key" in status or b"api-key" in status:
            raise ConnectionFailure("API_KEY_MODE")
        if status != b"logged in using chatgpt":
            raise ConnectionFailure("LOGIN_REQUIRED" if status == b"not logged in" else "CLI_FAILED")

    def metadata(self, files: OperationFiles, cancel: threading.Event, deadline: float, version: str) -> Metadata:
        if files.path is None:
            raise ConnectionFailure("TEMP_FAILED")
        stage = 0
        models: tuple[str, ...] = ()
        reasoning = {}
        plan: str | None = None
        quota = Quota()

        def request(identifier: int, method: str, params: dict[str, object] | None = None) -> bytes:
            value: dict[str, object] = {"id": identifier, "method": method}
            if params is not None:
                value["params"] = params
            return (json.dumps(value, separators=(",", ":")) + "\n").encode()

        def accept(raw: bytes) -> bytes | None:
            nonlocal stage, models, plan, quota
            try:
                message = strict_json(raw)
            except Exception:
                raise ConnectionFailure("METADATA_FAILED") from None
            if not isinstance(message, dict):
                raise ConnectionFailure("METADATA_FAILED")
            if "method" in message:
                if message.get("method") in {"remoteControl/status/changed", "account/rateLimits/updated"} and "id" not in message:
                    return None
                if message.get("method") == "account/updated" and "id" not in message:
                    params = message.get("params")
                    if not isinstance(params, dict) or params.get("authMode") != "chatgpt":
                        raise ConnectionFailure("API_KEY_MODE")
                    return None
                raise ConnectionFailure("METADATA_FAILED")
            if message.get("id") != stage:
                raise ConnectionFailure("METADATA_FAILED")
            if stage == 3 and "error" in message:
                error = message["error"]
                if (isinstance(error, dict) and type(error.get("code")) is int and
                        error["code"] == -32601 and "result" not in message):
                    stage = 4
                    return b""
                raise ConnectionFailure("METADATA_FAILED")
            result = message.get("result")
            if "error" in message or not isinstance(result, dict):
                raise ConnectionFailure("METADATA_FAILED")
            if stage == 0:
                stage = 1
                return b'{"method":"initialized"}\n' + request(1, "account/read", {"refreshToken": False})
            if stage == 1:
                account = result.get("account")
                if account is None:
                    raise ConnectionFailure("LOGIN_REQUIRED")
                if not isinstance(account, dict) or account.get("type") != "chatgpt":
                    raise ConnectionFailure("API_KEY_MODE")
                raw_plan = account.get("planType")
                if raw_plan is not None:
                    if not isinstance(raw_plan, str) or not PLAN.fullmatch(raw_plan):
                        raise ConnectionFailure("METADATA_FAILED")
                    plan = raw_plan
                stage = 2
                return request(2, "model/list", {"includeHidden": False, "limit": MAX_MODELS})
            if stage == 2:
                data = result.get("data")
                if result.get("nextCursor") is not None or not isinstance(data, list) or not 0 < len(data) <= MAX_MODELS:
                    raise ConnectionFailure("METADATA_FAILED")
                names: list[str] = []
                for item in data:
                    name = item.get("model") if isinstance(item, dict) else None
                    if not isinstance(name, str) or not MODEL.fullmatch(name) or name in names or item.get("hidden") is True:
                        raise ConnectionFailure("METADATA_FAILED")
                    names.append(name)
                    try:
                        reasoning[name] = model_reasoning(item)
                    except ValueError:
                        raise ConnectionFailure("METADATA_FAILED") from None
                models = tuple(names)
                stage = 3
                return request(3, "account/rateLimits/read")
            if stage == 3:
                quota = quota_from_result(result)
                stage = 4
                return b""
            raise ConnectionFailure("METADATA_FAILED")

        config = (self.experimental_profile.config(files.path) if self.experimental_profile is not None
                  else overrides(files.path))
        self._run(files, ("app-server", "--strict-config", *config), cancel, deadline,
                  data=request(0, "initialize", {"clientInfo": {"name": "foldcv", "version": "0.1.0"}}),
                  on_line=accept, interactive=True)
        if stage != 4:
            raise ConnectionFailure("METADATA_FAILED")
        return Metadata(version, models, plan, quota, reasoning)

    def inspect(self, files: OperationFiles, cancel: threading.Event, *, full: bool = True) -> Metadata:
        deadline = time.monotonic() + 15
        version = self.version(files, cancel, deadline)
        if not full:
            return Metadata(version, (), None, Quota())
        try:
            self.login_status(files, cancel, deadline)
            return self.metadata(files, cancel, deadline, version)
        except ConnectionFailure as error:
            raise ConnectionFailure(error.code, version) from None

    def login(self, files: OperationFiles, cancel: threading.Event) -> None:
        if files.path is None:
            raise ConnectionFailure("TEMP_FAILED")
        deadline = time.monotonic() + 120
        self.version(files, cancel, deadline)
        try:
            self.login_status(files, cancel, deadline)
            return
        except ConnectionFailure as error:
            if error.code != "LOGIN_REQUIRED":
                raise
        logs = files.path / "logs"
        logs.mkdir(mode=0o700, exist_ok=True)
        # The CLI owns the browser flow and credential storage; only diagnostics are local.
        self._run(files, ("login", "--config", "log_dir=" + json.dumps(str(logs))), cancel,
                  deadline, max_output=65_536)
