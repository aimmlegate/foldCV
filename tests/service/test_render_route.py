"""Protected render transport, bounds and lifecycle without a converter in fast checks."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from contextlib import contextmanager

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api import app as service
from resume_api.app import create_app
from resume_api.rendering import DocumentRenderer
from resume_api.lifecycle import SpikeError
from resume_api import lifecycle
from resume_api.contracts import NormalizeResult, UsagePayload

ROOT = Path(__file__).resolve().parents[2]
REQUEST = json.loads((ROOT / "contracts/examples/render_request.json").read_text(encoding="utf-8"))
ORIGIN = "http://127.0.0.1:39279"
SECRET = "synthetic-render-secret-01234567890123"


def make_app(tmp_path, runner=None):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("synthetic shell")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist, runner=runner)


@pytest.mark.asyncio
async def test_render_route_validates_snapshot_and_cleans_workspace(tmp_path, monkeypatch):
    calls = []

    async def fake_render(self, request, files):
        calls.append(request.snapshot.snapshot_sha256)
        assert files.path is not None and (files.path / ".lock").is_file()
        return b"synthetic ZIP bytes"

    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 401
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        invalid = json.loads(json.dumps(REQUEST))
        invalid["document"]["candidate"]["title"] = "Changed without new hash"
        rejected = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=invalid)
        assert rejected.status_code == 422 and rejected.json()["error"]["code"] == "INVALID_REQUEST"
        assert calls == []
        response = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert response.status_code == 200 and response.content == b"synthetic ZIP bytes"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-type"] == "application/zip"
    assert calls == [REQUEST["snapshot"]["snapshotSha256"]]
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_render_route_timeout_releases_operation(tmp_path, monkeypatch):
    cancelled = asyncio.Event()

    async def slow_render(self, request, files):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(DocumentRenderer, "render", slow_render)
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.05)
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        response = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "OPERATION_TIMEOUT"
    assert cancelled.is_set()
    await asyncio.sleep(0)
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_cleanup_failure_retains_owned_workspace_and_blocks_new_work(tmp_path, monkeypatch):
    async def failed_cleanup(self, request, files):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    class Runner:
        calls = 0

        async def run(self, kind, request, files):
            self.calls += 1
            raise AssertionError("new work must stay blocked")

    runner = Runner()
    monkeypatch.setattr(DocumentRenderer, "render", failed_cleanup)
    app = make_app(tmp_path, runner=runner)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        failed = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"
        assert "Мария Примерова" not in failed.text
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []
        busy = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert busy.status_code == 429 and busy.json()["error"]["code"] == "BUSY"
        text = await client.post("/v1/normalize", headers={"Origin": ORIGIN},
                                 json={"baseRevision": 1, "sourceUnits": [], "language": "en"})
        assert '"code":"BUSY"' in text.text
    assert runner.calls == 0
    owned = list((tmp_path / "operations").iterdir())
    assert len(owned) == 1
    assert (owned[0] / ".owner").is_file()
    assert (owned[0] / ".cleanup-blocked").is_file()


@pytest.mark.asyncio
async def test_render_does_not_spend_text_budget_and_still_obeys_concurrency(tmp_path, monkeypatch):
    class Runner:
        calls = 0

        async def run(self, kind, request, files):
            self.calls += 1
            return NormalizeResult(facts=[], unresolved=[]), UsagePayload(logicalAttempts=0)

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_render(self, request, files):
        started.set()
        await release.wait()
        return b"synthetic ZIP bytes"

    runner = Runner()
    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    monkeypatch.setattr(service, "MAX_CONCURRENT", 1)
    app = make_app(tmp_path, runner)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        first = asyncio.create_task(client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST))
        await started.wait()
        denied = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert denied.status_code == 429 and denied.json()["error"]["code"] == "BUSY"
        release.set()
        assert (await first).status_code == 200
        for _ in range(21):
            assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 200
        text = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json={
            "baseRevision": 1, "sourceUnits": [], "language": "en"})
        assert '"operation.completed"' in text.text and runner.calls == 1
        assert (await client.get("/v1/capabilities")).json()["limits"]["maxTextOperations"] == service.MAX_OPERATIONS


@pytest.mark.asyncio
async def test_temporary_failure_recovers_but_unsafe_root_latches(tmp_path, monkeypatch):
    async def fake_render(self, request, files):
        return b"synthetic ZIP bytes"

    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    app = make_app(tmp_path)
    original = lifecycle.OperationFiles.open

    @contextmanager
    def failed_open(self):
        raise SpikeError("TEMP_FAILED")
        yield self

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        monkeypatch.setattr(lifecycle.OperationFiles, "open", failed_open)
        failed = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "TEMP_FAILED"
        assert (await client.get("/v1/capabilities")).json()["renderers"] == ["docx", "pdf"]
        monkeypatch.setattr(lifecycle.OperationFiles, "open", original)
        assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 200

        @contextmanager
        def unsafe_open(self):
            raise SpikeError("UNSAFE_TEMP_ROOT")
            yield self

        monkeypatch.setattr(lifecycle.OperationFiles, "open", unsafe_open)
        unsafe = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert unsafe.status_code == 503 and unsafe.json()["error"]["code"] == "UNSAFE_TEMP_ROOT"
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []


@pytest.mark.asyncio
async def test_real_child_stop_failure_blocks_text_and_restart(tmp_path, monkeypatch):
    class Runner:
        process = None

        async def run(self, kind, request, files):
            self.process = files.spawn(Path(sys.executable), ("-c", "import time; time.sleep(30)"), capture=False)
            return NormalizeResult(facts=[], unresolved=[]), UsagePayload(logicalAttempts=0)

    runner = Runner()
    original_stop = lifecycle.stop_group

    def failed_stop(process):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(lifecycle, "stop_group", failed_stop)
    app = make_app(tmp_path, runner)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
            failed = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json={
                "baseRevision": 1, "sourceUnits": [], "language": "en"})
            assert '"code":"PROCESS_CLEANUP_FAILED"' in failed.text
            assert runner.process is not None and runner.process.poll() is None
            assert (await client.get("/v1/capabilities")).json()["renderers"] == []
            assert '"code":"BUSY"' in (await client.post("/v1/normalize", headers={"Origin": ORIGIN},
                json={"baseRevision": 1, "sourceUnits": [], "language": "en"})).text
            assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 429
        owned = list((tmp_path / "operations").iterdir())
        assert len(owned) == 1 and (owned[0] / ".owner").is_file() and (owned[0] / ".cleanup-blocked").is_file()
        restarted = make_app(tmp_path)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN) as client:
            await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
            assert (await client.get("/v1/capabilities")).json()["renderers"] == []
            assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 429
        assert owned[0].is_dir()
    finally:
        monkeypatch.setattr(lifecycle, "stop_group", original_stop)
        if runner.process is not None:
            original_stop(runner.process)


@pytest.mark.asyncio
async def test_unrelated_blocked_marker_does_not_disable_new_service(tmp_path):
    root = tmp_path / "operations"
    root.mkdir()
    unrelated = root / ("op-" + "a" * 32)
    unrelated.mkdir()
    (unrelated / ".owner").write_text(json.dumps({"owner": "another-app", "id": "a" * 32}))
    (unrelated / ".lock").touch()
    (unrelated / ".cleanup-blocked").touch()
    foreign_intent = root / (".cleanup-intent-op-" + "b" * 32 + ".json")
    foreign_intent.write_text(json.dumps({"owner": "another-app", "id": "b" * 32}))
    private = tmp_path / "private-marker"
    private.write_text("synthetic private data")
    linked_intent = root / (".cleanup-intent-op-" + "c" * 32 + ".json")
    linked_intent.symlink_to(private)
    fifo_intent = root / (".cleanup-intent-op-" + "d" * 32 + ".json")
    os.mkfifo(fifo_intent)
    oversized_intent = root / (".cleanup-intent-op-" + "e" * 32 + ".json")
    oversized_intent.write_text("x" * 257)
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.get("/v1/capabilities")).json()["renderers"] == ["docx", "pdf"]
    assert unrelated.is_dir() and foreign_intent.is_file() and linked_intent.is_symlink() and fifo_intent.exists() and oversized_intent.is_file()
    assert private.read_text() == "synthetic private data"


@pytest.mark.asyncio
async def test_artifact_cleanup_failure_latches_service(tmp_path, monkeypatch):
    from spikes.cli import runner as spike_runner

    async def fake_render(self, request, files):
        return b"synthetic ZIP bytes"

    original_remove = spike_runner.shutil.rmtree

    def failed_remove(path, *args, **kwargs):
        if Path(path).name.startswith("op-"):
            raise OSError("synthetic cleanup failure")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    monkeypatch.setattr(spike_runner.shutil, "rmtree", failed_remove)
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        failed = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CLEANUP_FAILED"
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []
        assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 429


@pytest.mark.asyncio
async def test_partial_artifact_cleanup_keeps_intent_and_blocks_restart(tmp_path, monkeypatch):
    from spikes.cli import runner as spike_runner

    async def fake_render(self, request, files):
        return b"synthetic ZIP bytes"

    unrelated = tmp_path / "operations" / ("op-" + "a" * 32)
    unrelated.mkdir(parents=True)
    (unrelated / ".owner").write_text(json.dumps({"owner": "another-app", "id": "a" * 32}))
    (unrelated / ".lock").touch()
    original_remove = spike_runner.shutil.rmtree

    def partial_remove(path, *args, **kwargs):
        if Path(path).name.startswith("op-"):
            (Path(path) / ".owner").unlink()
            (Path(path) / ".lock").unlink()
            raise OSError("synthetic partial removal")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    app = make_app(tmp_path)
    monkeypatch.setattr(spike_runner.shutil, "rmtree", partial_remove)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        failed = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CLEANUP_FAILED"
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []
    root = tmp_path / "operations"
    intents = list(root.glob(".cleanup-intent-op-*.json"))
    assert len(intents) == 1
    record = json.loads(intents[0].read_text())
    assert record == {"owner": lifecycle.OWNER, "id": intents[0].name.removeprefix(".cleanup-intent-op-").removesuffix(".json")}
    damaged = root / ("op-" + record["id"])
    assert damaged.is_dir() and not (damaged / ".owner").exists()
    restarted = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []
        assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 429
    assert damaged.is_dir() and unrelated.is_dir() and intents[0].is_file()


@pytest.mark.asyncio
async def test_intent_setup_failure_does_not_start_deletion(tmp_path, monkeypatch):
    from spikes.cli import runner as spike_runner

    async def fake_render(self, request, files):
        return b"synthetic ZIP bytes"

    def failed_intent(root, identifier, owner):
        raise OSError("synthetic intent failure")

    original_remove = spike_runner.shutil.rmtree
    deletion_attempts = []

    def tracked_remove(path, *args, **kwargs):
        if Path(path).name.startswith("op-"):
            deletion_attempts.append(path)
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    app = make_app(tmp_path)
    monkeypatch.setattr(spike_runner, "_write_cleanup_intent", failed_intent)
    monkeypatch.setattr(spike_runner.shutil, "rmtree", tracked_remove)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        failed = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CLEANUP_FAILED"
    assert deletion_attempts == []
    owned = [path for path in (tmp_path / "operations").iterdir() if path.name.startswith("op-")]
    assert len(owned) == 1 and (owned[0] / ".owner").is_file() and (owned[0] / ".cleanup-blocked").is_file()
    restarted = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []


@pytest.mark.asyncio
async def test_intent_unlink_failure_blocks_restart_without_directory(tmp_path, monkeypatch):
    async def fake_render(self, request, files):
        return b"synthetic ZIP bytes"

    original_unlink = Path.unlink

    def failed_unlink(path, *args, **kwargs):
        if path.name.startswith(".cleanup-intent-op-"):
            raise OSError("synthetic marker unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    app = make_app(tmp_path)
    monkeypatch.setattr(Path, "unlink", failed_unlink)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        failed = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CLEANUP_FAILED"
    root = tmp_path / "operations"
    assert list(root.glob("op-*")) == [] and len(list(root.glob(".cleanup-intent-op-*.json"))) == 1
    restarted = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["render", "normalize"])
async def test_late_artifact_failure_latches_after_timeout(tmp_path, monkeypatch, kind):
    from spikes.cli import runner as spike_runner

    started = asyncio.Event()
    release = asyncio.Event()
    removed = asyncio.Event()

    async def delayed():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()

    async def fake_render(self, request, files):
        await delayed()
        return b"synthetic ZIP bytes"

    class Runner:
        async def run(self, operation, request, files):
            await delayed()
            return NormalizeResult(facts=[], unresolved=[]), UsagePayload(logicalAttempts=0)

    original_remove = spike_runner.shutil.rmtree

    def partial_remove(path, *args, **kwargs):
        if Path(path).name.startswith("op-"):
            (Path(path) / ".owner").unlink()
            (Path(path) / ".lock").unlink()
            removed.set()
            raise OSError("synthetic late removal failure")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(DocumentRenderer, "render", fake_render)
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(service, "CANCEL_GRACE_SECONDS", 0.01)
    app = make_app(tmp_path, Runner())
    monkeypatch.setattr(spike_runner.shutil, "rmtree", partial_remove)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        if kind == "render":
            response = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
            assert response.status_code == 504 and response.json()["error"]["code"] == "OPERATION_TIMEOUT"
        else:
            response = await client.post("/v1/normalize", headers={"Origin": ORIGIN},
                                         json={"baseRevision": 1, "sourceUnits": [], "language": "en"})
            assert '"code":"OPERATION_TIMEOUT"' in response.text
        assert started.is_set()
        release.set()
        await asyncio.wait_for(removed.wait(), timeout=2)
        await asyncio.sleep(0)
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []
        assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 429
        text = await client.post("/v1/normalize", headers={"Origin": ORIGIN},
                                 json={"baseRevision": 1, "sourceUnits": [], "language": "en"})
        assert '"code":"BUSY"' in text.text
    restarted = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []


@pytest.mark.asyncio
async def test_real_render_child_stop_failure_on_timeout_retains_workspace(tmp_path, monkeypatch):
    process = None
    original_stop = lifecycle.stop_group

    async def waiting_render(self, request, files):
        nonlocal process
        process = files.spawn(Path(sys.executable), ("-c", "import time; time.sleep(30)"), capture=False)
        await asyncio.Event().wait()
        raise AssertionError("cancelled render resumed")

    def failed_stop(child):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(DocumentRenderer, "render", waiting_render)
    monkeypatch.setattr(lifecycle, "stop_group", failed_stop)
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.05)
    app = make_app(tmp_path)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
            failed = await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)
            assert failed.status_code == 503 and failed.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"
            assert (await client.get("/v1/capabilities")).json()["renderers"] == []
            assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json=REQUEST)).status_code == 429
        owned = list((tmp_path / "operations").iterdir())
        assert len(owned) == 1 and (owned[0] / ".cleanup-blocked").is_file()
    finally:
        monkeypatch.setattr(lifecycle, "stop_group", original_stop)
        if process is not None:
            original_stop(process)
