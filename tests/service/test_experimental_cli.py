"""The personal CLI mode is opt-in and remains closed after detach."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.extraction.parser import extract
from packages.resume_core.normalization import FactRequest, SourceInput, literal_sheet
from resume_api import app as app_module
from resume_api.app import create_app
from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile, ExperimentalProfileError, VERSION
from resume_api.connection import Metadata, Quota
from resume_api.contracts import EmptyRequest, SelectModelRequest


ORIGIN = "http://127.0.0.1:39279"
SECRET = "synthetic-personal-experiment-0123456789"


class MetadataOnly:
    def inspect(self, _files, _cancel, *, full=True):
        assert full
        return Metadata(VERSION, ("gpt-6-luna",), "plus", Quota("available", 25, 1800000000))


@pytest.mark.asyncio
async def test_readiness_requires_opt_in_status_and_selection_then_detaches(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>fixture</html>")
    profile = ExperimentalCliProfile(tmp_path / "profile")
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations",
                     dist=dist, connection_adapter=MetadataOnly(), experimental_profile=profile)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False
        status = (await client.post("/v1/host/status", headers={"Origin": ORIGIN}, json={})).json()
        assert status["experimentalMode"] is True and status["generationReady"] is False
        selected = (await client.post("/v1/host/select", headers={"Origin": ORIGIN},
                                      json={"model": "gpt-6-luna"})).json()
        assert selected["generationReady"] is True
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is True
        detached = (await client.post("/v1/host/detach", headers={"Origin": ORIGIN}, json={})).json()
        assert detached["generationReady"] is False and detached["state"] == "detached"
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False


def test_profile_rejects_an_existing_unowned_root(tmp_path: Path):
    root = tmp_path / "existing"
    root.mkdir(mode=0o700)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    with pytest.raises(ExperimentalProfileError, match="CLI_PROFILE_UNSAFE"):
        ExperimentalCliProfile(root).prepare()
    assert list(root.iterdir()) == []


def test_profile_policy_is_owned_and_env_isolated(tmp_path: Path, monkeypatch):
    if sys.platform != "darwin":
        pytest.skip("The macOS sandbox is required")
    monkeypatch.setattr(ExperimentalCliProfile, "check_binary", lambda _self: None)
    root = tmp_path.resolve() / "profile"
    profile = ExperimentalCliProfile(root)
    profile.prepare()
    operation = tmp_path.resolve() / "operation"
    operation.mkdir(mode=0o700)
    for name in ("tmp", "cache", "data", "state", "logs"):
        (operation / name).mkdir(mode=0o700)
    executable, args, env = profile.launch(BINARY, ("--version",), operation)
    assert executable == Path("/usr/bin/sandbox-exec")
    assert env["HOME"] == str(root / "home") and env["CODEX_HOME"] == str(root / "codex")
    assert not any(name.startswith(("OPENAI_", "ANTHROPIC_")) for name in env)
    policy = args[1]
    assert all(path in policy for path in ('(subpath "/Users")', '(subpath "/private/var")',
                                           '(subpath "/private/tmp")', '(deny process-exec)'))
    assert '(allow process-exec (literal "/usr/bin/open"))' not in policy
    assert str(operation) in policy and str(root) in policy
    assert os.stat(root / ".foldcv-cli-experiment-v1").st_mode & 0o777 == 0o600


def test_experimental_entrypoint_stops_on_unsafe_profile_before_server(tmp_path: Path):
    repo = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env.pop("FOLDCV_CODEX_EXECUTABLE", None)
    env["CODEX_HOME"] = str(Path.home() / "Library/Application Support/FoldCV/cli-experiment")
    result = subprocess.run([sys.executable, "tools/run-local.py", "--experimental-cli", "--no-open"],
                            cwd=repo, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "CLI_PROFILE_UNSAFE" in result.stderr
    assert "http://" not in result.stdout and "Traceback" not in result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "expected"), [("detach", "operation.failed"),
                                                    ("refresh", "operation.completed")])
async def test_completed_worker_publish_respects_detach_but_not_refresh(tmp_path: Path, monkeypatch,
                                                                          action: str, expected: str):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>fixture</html>")

    class SyntheticService:
        def __init__(self, _provider, _model):
            pass

        def run(self, request, _files, _cancel):
            return literal_sheet(request), {"logicalAttempts": 1, "inputTokens": 0,
                                            "outputTokens": 0, "inferenceCount": None}

    monkeypatch.setattr(app_module, "NormalizationContentService", SyntheticService)
    original_wait_for = asyncio.wait_for
    worker_complete = asyncio.Event()
    release = asyncio.Event()

    async def hold_publish(awaitable, timeout=None):
        result = await original_wait_for(awaitable, timeout)
        if timeout == app_module.TIMEOUT_SECONDS and isinstance(result, tuple):
            worker_complete.set()
            await release.wait()
        return result

    monkeypatch.setattr(app_module.asyncio, "wait_for", hold_publish)
    refresh_started = threading.Event()
    refresh_release = threading.Event()

    class RefreshingMetadata(MetadataOnly):
        calls = 0

        def inspect(self, files, cancel, *, full=True):
            self.calls += 1
            if self.calls == 2:
                refresh_started.set()
                assert refresh_release.wait(3)
            return super().inspect(files, cancel, full=full)

    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
                     connection_adapter=RefreshingMetadata(),
                     experimental_profile=ExperimentalCliProfile(tmp_path / "profile"))
    routes = {item.path: item.endpoint for item in app.app.router.routes if hasattr(item, "path")}
    await routes["/v1/host/status"](EmptyRequest())
    await routes["/v1/host/select"](SelectModelRequest(model="gpt-6-luna"))
    extracted = extract(b"Skills: Python\n", "pasted.txt", pasted=True)
    request = FactRequest(sources=[SourceInput(result=extracted, overlays={})])
    response = await routes["/v1/facts/normalize"](request)
    started = json.loads((await anext(response.body_iterator)).decode())
    assert started["type"] == "operation.started"
    pending = asyncio.create_task(anext(response.body_iterator))
    await original_wait_for(worker_complete.wait(), 3)
    status_task = None
    if action == "detach":
        detached = await routes["/v1/host/detach"](EmptyRequest())
        assert json.loads(detached.body)["generationReady"] is False
    else:
        status_task = asyncio.create_task(routes["/v1/host/status"](EmptyRequest()))
        assert await asyncio.to_thread(refresh_started.wait, 3)
    release.set()
    final = json.loads((await original_wait_for(pending, 3)).decode())
    assert final["type"] == expected
    refresh_release.set()
    if status_task is not None:
        await original_wait_for(status_task, 3)
    await response.body_iterator.aclose()
