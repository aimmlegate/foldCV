"""T09 metadata and connection routes use only synthetic CLI processes."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from resume_api.app import create_app
from resume_api.connection import ConnectionAdapter, ConnectionFailure, Metadata, Quota, quota_from_result
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.cli.profile import VERSION


ORIGIN = "http://127.0.0.1:39272"
SECRET = "synthetic-connection-secret-0123456789"
SCRIPT = r'''
import json, os, sys, time
from pathlib import Path
base = Path(__file__).parent
config = json.loads((base / "config.json").read_text())
args = sys.argv[1:]
with (base / "audit.jsonl").open("a") as audit:
    audit.write(json.dumps({"args": args, "cwd": os.getcwd(), "env": sorted(os.environ)}) + "\n")
case = config["case"]
if args == ["--version"]:
    print(config.get("version", "codex-cli 0.162.0-alpha.2-fixture"))
    sys.exit(0)
if args == ["login", "status"]:
    if case in {"missing_login", "slow_login", "valid_login"}:
        print("Not logged in", file=sys.stderr); sys.exit(1)
    print("Logged in using an API key" if case == "api_key" else "Logged in using ChatGPT")
    sys.exit(0)
if args[:2] == ["login", "--config"]:
    assert len(args) == 3 and args[2].startswith('log_dir="')
    assert Path(args[2].split('"')[1]).is_relative_to(Path.cwd())
    assert not any(name.startswith(("OPENAI_", "CODEX_")) for name in os.environ)
    (base / "login_ready").touch()
    if case == "slow_login":
        while not (base / "login_release").exists(): time.sleep(0.01)
    if case == "valid_login":
        (base / "config.json").write_text(json.dumps({"case": "valid", "version": config["version"]}))
    sys.exit(0)
if args and args[0] == "app-server":
    assert "--strict-config" in args and any("log_dir=" in value for value in args)
    for raw in sys.stdin:
        message = json.loads(raw)
        method = message["method"]
        if method == "initialize":
            print(json.dumps({"id": 0, "result": {}}), flush=True)
        elif method == "initialized":
            pass
        elif method == "account/read":
            assert message["params"] == {"refreshToken": False}
            account = None if case == "expired_login" else {"type": "chatgpt", "planType": "plus", "email": "private@example.invalid"}
            print(json.dumps({"id": 1, "result": {"account": account}}), flush=True)
        elif method == "model/list":
            assert message["params"] == {"includeHidden": False, "limit": 100}
            if case == "slow_metadata":
                (base / "metadata_ready").touch()
                while not (base / "metadata_release").exists(): time.sleep(0.01)
            name = "bad token" if case == "bad_model" else "gpt-6-luna"
            print(json.dumps({"id": 2, "result": {"data": [{"model": name}], "nextCursor": None}}), flush=True)
        elif method == "account/rateLimits/read":
            if case == "no_quota":
                print(json.dumps({"id": 3, "error": {"code": -32601}}), flush=True)
            elif case in {"unauthorized_quota", "failed_quota"}:
                code = -32000 if case == "unauthorized_quota" else -32603
                print(json.dumps({"id": 3, "error": {"code": code, "message": "Unauthorized" if code == -32000 else "Internal error"}}), flush=True)
            else:
                used = 100 if case == "quota" else 25
                print(json.dumps({"id": 3, "result": {"rateLimits": {"primary": {"usedPercent": used, "resetsAt": 1800000000}, "secondary": None, "rateLimitReachedType": None}}}), flush=True)
        else:
            sys.exit(91)
    sys.exit(0)
sys.exit(92)
'''


@pytest.fixture
def cli(tmp_path: Path):
    path = tmp_path / "synthetic codex"
    path.write_text("#!" + sys.executable + "\n" + SCRIPT)
    path.chmod(0o700)
    def configure(case: str = "valid", version: str = VERSION + "-fixture") -> None:
        (tmp_path / "config.json").write_text(json.dumps({"case": case, "version": version}))
        (tmp_path / "audit.jsonl").unlink(missing_ok=True)
    configure()
    return path, configure


def inspect(cli, tmp_path: Path, case: str) -> tuple[Metadata | None, str | None]:
    path, configure = cli
    configure(case)
    adapter = ConnectionAdapter(path, allow_fixture=True)
    try:
        with OperationFiles(tmp_path / "operations").open() as files:
            value = adapter.inspect(files, threading.Event())
        return value, None
    except ConnectionFailure as error:
        return None, error.code


@pytest.mark.parametrize(("case", "expected"), [
    ("valid", "available"), ("quota", "exhausted"), ("no_quota", "unknown"),
])
def test_metadata_and_quota_are_bounded_and_generation_never_starts(cli, tmp_path, case, expected):
    result, error = inspect(cli, tmp_path, case)
    assert error is None and result is not None
    assert result.models == ("gpt-6-luna",) and result.plan == "plus" and result.quota.state == expected
    audit = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [entry["args"][0] for entry in audit] == ["--version", "login", "app-server"]
    assert all(entry["args"][0] != "exec" for entry in audit)
    assert not list((tmp_path / "operations").iterdir())


@pytest.mark.parametrize(("case", "expected"), [
    ("missing_login", "LOGIN_REQUIRED"), ("api_key", "API_KEY_MODE"),
    ("bad_model", "METADATA_FAILED"), ("expired_login", "LOGIN_REQUIRED"),
    ("unauthorized_quota", "METADATA_FAILED"), ("failed_quota", "METADATA_FAILED"),
])
def test_distinct_auth_and_metadata_failures(cli, tmp_path, case, expected):
    result, error = inspect(cli, tmp_path, case)
    assert result is None and error == expected
    assert not list((tmp_path / "operations").iterdir())


def test_missing_and_wrong_version_fail_before_auth(cli, tmp_path):
    path, configure = cli
    configure(version="codex-cli 0.0.1")
    with OperationFiles(tmp_path / "wrong").open() as files:
        with pytest.raises(ConnectionFailure, match="UNSUPPORTED_VERSION"):
            ConnectionAdapter(path, allow_fixture=True).inspect(files, threading.Event())
    audit = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == 1 and audit[0]["args"] == ["--version"]
    with OperationFiles(tmp_path / "missing").open() as files:
        with pytest.raises(ConnectionFailure, match="CLI_MISSING"):
            ConnectionAdapter(tmp_path / "absent").inspect(files, threading.Event())


def test_path_discovered_node_cli_uses_validated_interpreter_with_clean_environment(tmp_path, monkeypatch):
    node_name = shutil.which("node")
    assert node_name is not None
    node = Path(node_name).resolve(strict=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "codex"
    audit = tmp_path / "node-audit.json"
    cli.write_text("#!/usr/bin/env node\n" +
                   "const fs = require('fs');\n" +
                   f"fs.writeFileSync({json.dumps(str(audit))}, JSON.stringify({{argv: process.argv.slice(2), executable: process.execPath, path: process.env.PATH, env: Object.keys(process.env)}}));\n" +
                   f"console.log({json.dumps(VERSION + '-fixture')});\n")
    cli.chmod(0o700)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{node.parent}{os.pathsep}{os.defpath}")
    monkeypatch.setenv("NODE_OPTIONS", "--this-option-must-not-reach-child")
    monkeypatch.setenv("NODE_PATH", str(tmp_path / "untrusted"))
    with OperationFiles(tmp_path / "node-operations").open() as files:
        result = ConnectionAdapter(allow_fixture=True).inspect(files, threading.Event(), full=False)
    observed = json.loads(audit.read_text())
    assert result.version == VERSION + "-fixture"
    assert observed["argv"] == ["--version"] and Path(observed["executable"]).resolve() == node
    assert observed["path"] == os.defpath
    assert "NODE_OPTIONS" not in observed["env"] and "NODE_PATH" not in observed["env"]
    assert not any(name.startswith(("OPENAI_", "CODEX_")) for name in observed["env"])


@pytest.mark.asyncio
async def test_node_cli_without_valid_interpreter_has_actionable_state(tmp_path, monkeypatch):
    cli = tmp_path / "node codex"
    cli.write_text("#!/usr/bin/env node\n")
    cli.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    app = make_app(tmp_path, ConnectionAdapter(cli))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        status = (await post(client, "status")).json()
    assert status["state"] == "launcher_unsupported" and status["metadataReady"] is False
    assert status["generationReady"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "expected"), [
    ("no_quota", "unknown_limits"), ("unauthorized_quota", "metadata_failed"),
    ("failed_quota", "metadata_failed"),
])
async def test_quota_method_error_is_distinct_from_metadata_failure(cli, tmp_path, case, expected):
    path, configure = cli
    configure(case)
    app = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        status = (await post(client, "status")).json()
    assert status["state"] == expected
    assert status["metadataReady"] is (case == "no_quota")
    assert status["generationReady"] is False


def test_quota_invalid_values_fail_and_unknown_is_not_zero():
    assert quota_from_result({"rateLimits": None}) == Quota()
    assert quota_from_result({"rateLimits": {"spendControlReached": True}}).state == "exhausted"
    for value in (True, -1, 101, float("nan")):
        with pytest.raises(ConnectionFailure, match="METADATA_FAILED"):
            quota_from_result({"rateLimits": {"primary": {"usedPercent": value}}})


def make_app(tmp_path: Path, adapter: ConnectionAdapter):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<html>fixture</html>")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "service-operations",
                      dist=dist, connection_adapter=adapter)


async def post(client: httpx.AsyncClient, name: str, body: dict | None = None):
    return await client.post("/v1/host/" + name, headers={"Origin": ORIGIN}, json=body or {})


@pytest.mark.asyncio
async def test_protected_routes_select_detach_and_closed_generation(cli, tmp_path):
    path, _ = cli
    app = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await post(client, "status")).status_code == 401
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.post("/v1/host/status", headers={"Origin": "http://evil.invalid"}, json={})).status_code == 403
        status = (await post(client, "status")).json()
        assert status["state"] == "connected" and status["metadataReady"] is True
        assert status["generationReady"] is False and status["selectedModel"] is None
        assert (await post(client, "select", {"model": "other"})).status_code == 409
        selected = (await post(client, "select", {"model": "gpt-6-luna"})).json()
        assert selected["selectedModel"] == "gpt-6-luna"
        detached = (await post(client, "detach")).json()
        assert detached["state"] == "detached" and detached["models"] == [] and detached["selectedModel"] is None
        assert (await post(client, "select", {"model": "gpt-6-luna"})).status_code == 409
        assert (await post(client, "login", {"argv": ["codex", "login"]})).status_code == 422
        assert (await post(client, "login")).status_code == 409
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False
        assert (await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json={})).status_code == 422
    audit = (tmp_path / "audit.jsonl").read_text()
    assert "logout" not in audit and '"exec"' not in audit


@pytest.mark.asyncio
async def test_explicit_login_and_detach_cancel_owned_process(cli, tmp_path):
    path, configure = cli
    configure("missing_login")
    app = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await post(client, "status")).json()["state"] == "login_required"
        configure("slow_login")
        pending = asyncio.create_task(post(client, "login"))
        for _ in range(200):
            if (tmp_path / "login_ready").exists(): break
            await asyncio.sleep(0.01)
        assert (tmp_path / "login_ready").exists()
        detached = (await post(client, "detach")).json()
        assert detached["state"] == "detached"
        assert (await pending).json()["state"] == "detached"
        assert not list((tmp_path / "service-operations").iterdir())
        audit = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
        login_args = [entry["args"] for entry in audit if entry["args"][:2] == ["login", "--config"]]
        assert login_args == [["login", "--config", login_args[0][2]]]
        assert not any(name.startswith(("OPENAI_", "CODEX_")) for entry in audit for name in entry["env"])


@pytest.mark.asyncio
async def test_login_completes_only_after_click_and_refresh(cli, tmp_path):
    path, configure = cli
    configure("missing_login")
    app = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await post(client, "status")).json()["state"] == "login_required"
        assert not (tmp_path / "login_ready").exists()
        configure("valid_login")
        assert (await post(client, "login")).json()["state"] == "login_required"
        assert (tmp_path / "login_ready").exists()
        configure("valid")
        assert (await post(client, "status")).json()["state"] == "connected"
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False


@pytest.mark.asyncio
async def test_detach_rejects_late_metadata_result(cli, tmp_path):
    path, configure = cli
    configure("slow_metadata")
    app = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        pending = asyncio.create_task(post(client, "status"))
        for _ in range(200):
            if (tmp_path / "metadata_ready").exists(): break
            await asyncio.sleep(0.01)
        assert (tmp_path / "metadata_ready").exists()
        assert (await post(client, "detach")).json()["state"] == "detached"
        assert (await pending).json()["state"] == "detached"
        assert not list((tmp_path / "service-operations").iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize(("failure", "expected"), [
    ("TEMP_FAILED", "detached"), ("PROCESS_CLEANUP_FAILED", "cleanup_blocked"),
])
async def test_detach_rejects_late_failure_but_keeps_cleanup_block(failure, expected, tmp_path):
    started = threading.Event()

    class FailingAdapter(ConnectionAdapter):
        def inspect(self, files, cancel, *, full=True):
            started.set()
            assert cancel.wait(2)
            raise SpikeError(failure)

    app = make_app(tmp_path, FailingAdapter())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        pending = asyncio.create_task(post(client, "status"))
        for _ in range(200):
            if started.is_set(): break
            await asyncio.sleep(0.01)
        assert started.is_set()
        detached = (await post(client, "detach")).json()
        assert detached["state"] == expected
        assert (await pending).json()["state"] == expected
        assert (await post(client, "detach")).json()["state"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("late_failure", ["connection", "spike", "generic"])
async def test_detach_timeout_reports_cleanup_block_and_late_failure_stays_blocked(late_failure, tmp_path):
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    class HeldAdapter(ConnectionAdapter):
        def inspect(self, files, cancel, *, full=True):
            calls.append("inspect")
            started.set()
            assert release.wait(3)
            if late_failure == "connection":
                raise ConnectionFailure("PROCESS_CLEANUP_FAILED")
            if late_failure == "spike":
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            raise RuntimeError("synthetic late failure")

    app = make_app(tmp_path, HeldAdapter())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        pending = asyncio.create_task(post(client, "status"))
        for _ in range(200):
            if started.is_set(): break
            await asyncio.sleep(0.01)
        assert started.is_set()
        detached = (await post(client, "detach")).json()
        assert detached["state"] == "cleanup_blocked"
        assert detached["metadataReady"] is False and detached["generationReady"] is False
        release.set()
        assert (await pending).json()["state"] == "cleanup_blocked"
        assert (await post(client, "status")).json()["state"] == "cleanup_blocked"
        assert calls == ["inspect"]
    remaining = list((tmp_path / "service-operations").iterdir())
    if late_failure == "spike":
        assert remaining and any((path / ".cleanup-blocked").is_file() for path in remaining)
    else:
        assert not remaining


@pytest.mark.asyncio
async def test_cancel_login_stops_only_owned_sign_in(cli, tmp_path):
    path, configure = cli
    configure("missing_login")
    app = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await post(client, "status")).json()["state"] == "login_required"
        configure("slow_login")
        pending = asyncio.create_task(post(client, "login"))
        for _ in range(200):
            if (tmp_path / "login_ready").exists(): break
            await asyncio.sleep(0.01)
        assert (tmp_path / "login_ready").exists()
        assert (await post(client, "cancel-login")).json()["state"] == "login_required"
        assert (await pending).json()["state"] == "login_required"
        assert not list((tmp_path / "service-operations").iterdir())
        assert "logout" not in (tmp_path / "audit.jsonl").read_text()


@pytest.mark.asyncio
async def test_cleanup_failure_blocks_connection_and_survives_restart(cli, tmp_path, monkeypatch):
    path, _ = cli
    original = OperationFiles.stop_worker

    def fail_after_stop(self, *, final=True):
        original(self, final=final)
        if final:
            raise SpikeError("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(OperationFiles, "stop_worker", fail_after_stop)
    app = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await post(client, "status")).json()["state"] == "cleanup_blocked"
        before = (tmp_path / "audit.jsonl").read_text().count("--version")
        assert (await post(client, "status")).json()["state"] == "cleanup_blocked"
        assert (tmp_path / "audit.jsonl").read_text().count("--version") == before
    monkeypatch.setattr(OperationFiles, "stop_worker", original)
    restarted = make_app(tmp_path, ConnectionAdapter(path, allow_fixture=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await post(client, "status")).json()["state"] == "cleanup_blocked"
