"""The personal CLI mode is opt-in and remains closed after detach."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.text_rewrite import PlainTextReply
from resume_api import app as app_module
from resume_api.app import create_app
from resume_api.cli import distribution
from resume_api.cli.experimental_profile import BINARY, ExperimentalCliProfile, ExperimentalProfileError
from resume_api.connection import Metadata, Quota
from resume_api.inference_admission import INFERENCE
from resume_api.providers.codex_cli import CodexCliProvider
from resume_api.providers.content import ContentResult, ReportedUsage
from tests.service.app_fixtures import add_project


ORIGIN = "http://127.0.0.1:39279"
SECRET = "synthetic-personal-experiment-0123456789"
VERSION = "codex-cli " + distribution.RELEASE


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
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", data_root=tmp_path / "store",
                     dist=dist, connection_adapter=MetadataOnly(), experimental_profile=profile)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.get("/v1/settings/connection")).json()["generationReady"] is False
        status = (await client.post("/v1/host/status", headers={"Origin": ORIGIN}, json={})).json()
        assert status["experimentalMode"] is True and status["generationReady"] is False
        selected = (await client.post("/v1/host/select", headers={"Origin": ORIGIN},
                                      json={"model": "gpt-6-luna"})).json()
        assert selected["generationReady"] is True
        assert (await client.get("/v1/settings/connection")).json()["generationReady"] is True
        detached = (await client.post("/v1/host/detach", headers={"Origin": ORIGIN}, json={})).json()
        assert detached["generationReady"] is False and detached["state"] == "detached"
        assert (await client.get("/v1/settings/connection")).json()["generationReady"] is False


@pytest.mark.asyncio
async def test_connection_refresh_login_detach_and_cancel_invalidate_content_preflight(tmp_path, monkeypatch):
    from resume_api.connection import ConnectionFailure
    calls = []
    invalidate = CodexCliProvider.invalidate_preflight
    def invalidated(provider):
        calls.append(provider)
        invalidate(provider)
    monkeypatch.setattr(CodexCliProvider, "invalidate_preflight", invalidated)
    class LoginMetadata(MetadataOnly):
        missing = False
        started = threading.Event()
        def inspect(self, files, cancel, *, full=True):
            if self.missing:
                raise ConnectionFailure("LOGIN_REQUIRED")
            return super().inspect(files, cancel) if full else Metadata(VERSION, (), None, Quota("unknown"))
        def login(self, _files, cancel):
            self.started.set()
            if cancel.wait(3):
                raise ConnectionFailure("CANCELLED")
    metadata = LoginMetadata()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("fixture")
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
        data_root=tmp_path / "store", connection_adapter=metadata,
        experimental_profile=ExperimentalCliProfile(tmp_path / "profile"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        async def post(action):
            return await client.post("/v1/host/" + action, headers={"Origin": ORIGIN}, json={})
        for action in ["discover", "status", "models", "detach"]:
            assert (await post(action)).status_code == 200
        assert len(calls) == 4
        metadata.missing = True
        assert (await post("status")).json()["state"] == "login_required"
        pending = asyncio.create_task(post("login"))
        assert await asyncio.to_thread(metadata.started.wait, 3)
        assert (await post("cancel-login")).status_code == 200
        assert (await pending).status_code == 200
    assert len(calls) == 7 and len({id(provider) for provider in calls}) == 1


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
    # A temporary home keeps the entrypoint away from the real FoldCV profile.
    env["HOME"] = str(tmp_path / "home")
    env["CODEX_HOME"] = str(tmp_path / "home/Library/Application Support/FoldCV/cli-experiment")
    result = subprocess.run([sys.executable, "tools/run-local.py", "--experimental-cli", "--no-open"],
                            cwd=repo, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "CLI_PROFILE_UNSAFE" in result.stderr
    assert "http://" not in result.stdout and "Traceback" not in result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "expected"), [("detach", 409), ("refresh", 200)])
async def test_a_generation_finished_after_detach_is_refused_but_a_refresh_keeps_it(tmp_path: Path, monkeypatch,
                                                                                    action: str, expected: int):
    started, release = threading.Event(), threading.Event()

    class HeldProvider:
        def __init__(self, _executable, *, experimental_profile=None):
            pass

        def invalidate_preflight(self):
            pass

        def generate(self, request, _files, _cancel):
            started.set()
            assert release.wait(5)
            return ContentResult(PlainTextReply(text="Clear"), ReportedUsage(), "fixture", request.policy.model, .01, 1)

    monkeypatch.setattr(app_module, "CodexCliProvider", HeldProvider)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>fixture</html>")
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
                     data_root=tmp_path / "store", connection_adapter=MetadataOnly(),
                     experimental_profile=ExperimentalCliProfile(tmp_path / "profile"))
    add_project(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN,
                                 headers={"Origin": ORIGIN}) as client:
        await client.post("/v1/session/exchange", json={"secret": SECRET})
        await client.post("/v1/host/status", json={})
        assert (await client.post("/v1/host/select", json={"model": "gpt-6-luna"})).json()["generationReady"] is True
        opened = (await client.post("/v2/projects/template-project/open", json={})).json()
        body = {"editorToken": opened["editorToken"], "requestId": "rewrite-1", "snapshot": opened["response"]["snapshot"],
                "range": {"blockId": "block-paper-a", "beforeRevision": 1, "cellId": None, "field": "content",
                          "start": 0, "end": 6}, "instruction": "Make clearer."}
        pending = asyncio.create_task(client.post("/v2/projects/template-project/rewrite/preview", json=body))
        assert await asyncio.to_thread(started.wait, 5)
        side = asyncio.create_task(client.post("/v1/host/" + ("detach" if action == "detach" else "status"), json={}))
        if action == "refresh":
            # The check queues behind the rewrite (D121) and runs once it ends.
            for _ in range(500):
                if INFERENCE.waiting:
                    break
                await asyncio.sleep(0.01)
            assert not side.done()
        else:
            for _ in range(500):
                if (await client.get("/v1/settings/connection")).json()["state"] == "detached":
                    break
                await asyncio.sleep(0.01)
        release.set()
        reply = await pending
        if action == "refresh":
            assert (await side).json()["state"] == "connected"
        assert reply.status_code == expected, reply.text[:300]
        if action == "detach":
            assert reply.json()["error"]["code"] == "CANCELLED"
            assert (await side).json()["generationReady"] is False
        else:
            assert reply.json()["text"] == "Clear"
    assert list((tmp_path / "operations").iterdir()) == []
