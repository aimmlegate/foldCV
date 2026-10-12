"""Local service security and lifecycle checks with synthetic data only."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import time

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from resume_api import app as service
from resume_api.app import create_app
from resume_api.contracts import NormalizeResult, UsagePayload
from resume_api import lifecycle
from resume_api import launcher
from resume_api.lifecycle import OWNER, OperationFiles, reap_owned
from spikes.cli.runner import SpikeError, group_members, operation


ORIGIN = "http://127.0.0.1:39271"
SECRET = "synthetic-startup-secret-0123456789"
UNIT = {
    "id": "unit_1", "revision": 1, "order": 0, "text": "Synthetic engineer",
    "location": {"kind": "pasted", "index": 0, "row": None, "column": None},
    "disposition": "shown", "representedFactIds": [],
}
INPUT = {"baseRevision": 3, "sourceUnits": [{"sourceId": "src_1", "sourceRevision": 1, "unit": UNIT}], "language": "en"}


def make_app(tmp_path: Path, runner=None):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<html>synthetic shell</html>", encoding="utf-8")
    (dist / "asset.js").write_text("safe asset", encoding="utf-8")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist, runner=runner)


async def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)


async def login(client: httpx.AsyncClient):
    return await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})


@pytest.mark.asyncio
async def test_exact_host_origin_one_use_secret_and_cookie_scope(tmp_path):
    app = make_app(tmp_path)
    async with await client_for(app) as client:
        assert (await client.get("/v1/capabilities")).status_code == 401
        assert (await client.post("/v1/session/exchange", headers={"Origin": "http://evil.invalid"}, json={"secret": SECRET})).status_code == 403
        assert (await client.post("/v1/session/exchange", headers={"Origin": ORIGIN, "Host": "localhost:39271"}, json={"secret": SECRET})).status_code == 403
        reply = await login(client)
        assert reply.status_code == 200
        assert "HttpOnly" in reply.headers["set-cookie"] and "SameSite=strict" in reply.headers["set-cookie"]
        assert SECRET not in reply.text + reply.headers["set-cookie"]
        assert (await login(client)).status_code == 401
        cap = await client.get("/v1/capabilities")
        assert cap.status_code == 200
        assert cap.json()["generationReady"] is False
        assert cap.json()["renderers"] in ([], ["docx", "pdf"])
        assert cap.headers["cache-control"] == "no-store"
        assert (await client.post("/v1/normalize", json=INPUT)).status_code == 403
        assert (await client.post("/v1/normalize", headers={"Origin": "http://evil.invalid"}, json=INPUT)).status_code == 403
        assert (await client.get("/v1/capabilities", headers={"X-Forwarded-Host": "127.0.0.1:39271"})).status_code == 403
        assert (await client.get("/v1/capabilities?candidate=secret")).status_code == 403
        duplicate = await client.get("/v1/capabilities", headers=[("Host", "127.0.0.1:39271"), ("Host", "127.0.0.1:39271")])
        assert duplicate.status_code == 403


@pytest.mark.asyncio
async def test_malformed_oversized_and_unavailable_routes_are_safe(tmp_path):
    app = make_app(tmp_path)
    async with await client_for(app) as client:
        await login(client)
        headers = {"Origin": ORIGIN}
        bad = await client.post("/v1/normalize", headers=headers, json={**INPUT, "sourceUnits": [{"sourceId": "src_1", "sourceRevision": 1, "unit": {**UNIT, "text": "private-marker", "revision": "bad"}}]})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_REQUEST"
        assert "private-marker" not in bad.text
        large = await client.post("/v1/normalize", headers={**headers, "Content-Type": "application/json"}, content=b"x" * (service.MAX_BODY + 1))
        assert large.status_code == 413 and large.json()["error"]["code"] == "INPUT_TOO_LARGE"
        closed = await client.post("/v1/normalize", headers=headers, json=INPUT)
        assert closed.status_code == 501 and closed.json()["error"]["code"] == "FEATURE_UNAVAILABLE"
        assert closed.headers["cache-control"] == "no-store"
        assert (await client.post("/v1/host/login", headers=headers, json={"argv": ["codex", "login"]})).status_code == 422
        assert (await client.post("/v1/host/login", headers=headers, json={})).status_code == 409
        assert (await client.post("/v1/render", headers=headers, json={})).status_code == 422
        assert (await client.post("/v1/extract", headers=headers, json={})).status_code == 415
        assert (await client.post("/v1/extract", headers={**headers, "Content-Type": "multipart/form-data; boundary=fake"}, content=b"test")).status_code == 422
        assert (await client.get("/")).text == "<html>synthetic shell</html>"
        assert (await client.get("/asset.js")).text == "safe asset"


@pytest.mark.asyncio
async def test_static_fallback_and_assets_cannot_follow_escape_symlinks(tmp_path):
    app = make_app(tmp_path)
    outside = tmp_path / "private-marker"
    outside.write_text("private-marker", encoding="utf-8")
    index = tmp_path / "dist/index.html"
    index.unlink()
    index.symlink_to(outside)
    asset = tmp_path / "dist/asset.js"
    asset.unlink()
    asset.symlink_to(outside)
    async with await client_for(app) as client:
        for path in ("/", "/missing", "/asset.js"):
            result = await client.get(path)
            assert result.status_code == 404
            assert "private-marker" not in result.text


@pytest.mark.asyncio
async def test_duplicate_json_fields_and_method_errors_are_safe(tmp_path):
    app = make_app(tmp_path)
    async with await client_for(app) as client:
        headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
        duplicate_media = await client.post(
            "/v1/session/exchange",
            headers=[("Origin", ORIGIN), ("Content-Type", "application/json"),
                     ("Content-Type", "text/plain")],
            content=json.dumps({"secret": SECRET}),
        )
        assert duplicate_media.status_code == 422
        assert duplicate_media.json()["error"]["code"] == "INVALID_REQUEST"
        double_secret = await client.post("/v1/session/exchange", headers=headers,
                                          content=json.dumps({"secret": SECRET})[:-1] + ',"secret":"private-marker"}')
        assert double_secret.status_code == 422 and "private-marker" not in double_secret.text
        await login(client)
        for content in (
            '{"baseRevision":0,"baseRevision":3,"sourceUnits":[],"language":"en"}',
            '{"baseRevision":3,"sourceUnits":[],"language":"en","extra":{"x":1,"x":2}}',
        ):
            result = await client.post("/v1/normalize", headers=headers, content=content)
            assert result.status_code == 422 and result.json()["error"]["code"] == "INVALID_REQUEST"
            assert result.headers["cache-control"] == "no-store"
        duplicate_body = '{"baseRevision":0,"baseRevision":3,"sourceUnits":[],"language":"en"}'
        for media in ("application/vnd.foldcv+json", "Application/JSON", "application/json ; charset=utf-8"):
            result = await client.post("/v1/normalize", headers={"Origin": ORIGIN, "Content-Type": media},
                                       content=duplicate_body)
            assert result.status_code == 422 and result.json()["error"]["code"] == "INVALID_REQUEST"
            assert result.headers["cache-control"] == "no-store"
            accepted = await client.post("/v1/normalize", headers={"Origin": ORIGIN, "Content-Type": media},
                                         content=json.dumps(INPUT))
            assert accepted.status_code == 501 and accepted.json()["error"]["code"] == "FEATURE_UNAVAILABLE"
        missing_media = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, content=duplicate_body)
        assert missing_media.status_code == 415 and missing_media.json()["error"]["code"] == "INVALID_REQUEST"
        duplicate_media = await client.post(
            "/v1/normalize",
            headers=[("Origin", ORIGIN), ("Content-Type", "text/plain"),
                     ("Content-Type", "application/json")],
            content=duplicate_body,
        )
        assert duplicate_media.status_code == 422 and duplicate_media.json()["error"]["code"] == "INVALID_REQUEST"
        for result in (await client.post("/v1/capabilities", headers={"Origin": ORIGIN}, json={}),
                       await client.get("/v1/normalize")):
            assert result.status_code == 405
            assert result.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
            assert result.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_startup_and_deterministic_routes_never_invoke_text_runner(tmp_path):
    class ForbiddenRunner:
        calls = 0

        async def run(self, _kind, _request, _files):
            self.calls += 1
            raise AssertionError("unexpected content operation")

    runner = ForbiddenRunner()
    app = make_app(tmp_path, runner)
    async with await client_for(app) as client:
        await login(client)
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/asset.js")).status_code == 200
        status = await client.post("/v1/host/status", headers={"Origin": ORIGIN}, json={})
        assert status.status_code == 200 and status.json()["generationReady"] is False
        assert (await client.post("/v1/extract", headers={"Origin": ORIGIN, "Content-Type": "multipart/form-data; boundary=fake"}, content=b"synthetic")).status_code == 422
        assert (await client.post("/v1/validate", headers={"Origin": ORIGIN}, json={})).status_code == 422
        assert (await client.post("/v1/render", headers={"Origin": ORIGIN}, json={})).status_code == 422
    assert runner.calls == 0


class ResultRunner:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.raise_marker = False

    async def run(self, kind, request, files):
        assert kind == "normalize"
        assert files.path is not None
        (files.path / "synthetic.txt").write_text(request.sourceUnits[0].unit.text, encoding="utf-8")
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.raise_marker:
            raise ValueError("private-marker")
        return NormalizeResult(facts=[], unresolved=[]), UsagePayload(logicalAttempts=0)


@pytest.mark.asyncio
async def test_stream_envelopes_cleanup_failure_and_no_completed_retention(tmp_path):
    runner = ResultRunner()
    runner.release.set()
    app = make_app(tmp_path, runner)
    async with await client_for(app) as client:
        await login(client)
        response = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        events = [json.loads(line) for line in response.text.splitlines()]
        assert [event["type"] for event in events] == ["operation.started", "operation.completed"]
        assert [event["sequence"] for event in events] == [1, 2]
        assert all(event["requestId"] == events[0]["requestId"] and event["baseRevision"] == 3 for event in events)
        assert events[1]["payload"]["result"] == {"facts": [], "unresolved": []}
        assert list((tmp_path / "operations").iterdir()) == []
        runner.raise_marker = True
        failed = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert [json.loads(line)["type"] for line in failed.text.splitlines()] == ["operation.started", "operation.failed"]
        assert "private-marker" not in failed.text
        assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_timeout_and_operation_limit_release_workspace(tmp_path, monkeypatch):
    runner = ResultRunner()
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(service, "MAX_OPERATIONS", 1)
    app = make_app(tmp_path, runner)
    async with await client_for(app) as client:
        await login(client)
        first = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert [json.loads(line)["type"] for line in first.text.splitlines()] == ["operation.started", "operation.failed"]
        assert json.loads(first.text.splitlines()[1])["payload"]["code"] == "OPERATION_TIMEOUT"
        assert runner.cancelled
        assert list((tmp_path / "operations").iterdir()) == []
        second = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert json.loads(second.text)["payload"]["code"] == "OPERATION_LIMIT"


@pytest.mark.asyncio
async def test_timeout_bounds_cooperative_cancellation_and_stops_child_first(tmp_path, monkeypatch):
    class DelayedRunner:
        process = None
        stopped_before_cleanup = False

        async def run(self, _kind, _request, files):
            self.process = files.spawn(Path(sys.executable), ("-c", "import time; time.sleep(30)"))
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.stopped_before_cleanup = self.process.poll() is not None
                await asyncio.sleep(0.1)
                raise

    runner = DelayedRunner()
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(service, "CANCEL_GRACE_SECONDS", 0.3)
    app = make_app(tmp_path, runner)
    async with await client_for(app) as client:
        await login(client)
        start = time.monotonic()
        result = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert time.monotonic() - start < 2
        assert json.loads(result.text.splitlines()[-1])["payload"]["code"] == "OPERATION_TIMEOUT"
        assert runner.stopped_before_cleanup
        assert runner.process.stdin.closed and runner.process.stdout.closed and runner.process.stderr.closed
        assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_residual_runner_keeps_lease_and_workspace_until_it_exits(tmp_path, monkeypatch):
    class ResidualRunner:
        def __init__(self):
            self.release = asyncio.Event()
            self.cancelled = asyncio.Event()
            self.calls = 0

        async def run(self, _kind, _request, files):
            self.calls += 1
            if self.calls > 1:
                return NormalizeResult(facts=[], unresolved=[]), UsagePayload(logicalAttempts=0)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                await self.release.wait()
                return NormalizeResult(facts=[], unresolved=[]), UsagePayload(logicalAttempts=0)

    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(service, "CANCEL_GRACE_SECONDS", 0.02)
    assert service.MAX_CONCURRENT == 2
    runner = ResidualRunner()
    app = make_app(tmp_path, runner)
    async with await client_for(app) as client:
        await login(client)
        first = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert json.loads(first.text.splitlines()[-1])["payload"]["code"] == "OPERATION_TIMEOUT"
        assert runner.cancelled.is_set()
        assert len(list((tmp_path / "operations").iterdir())) == 1
        second = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert json.loads(second.text)["payload"]["code"] == "BUSY"
        runner.release.set()
        deadline = time.monotonic() + 1
        while list((tmp_path / "operations").iterdir()) and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert list((tmp_path / "operations").iterdir()) == []
        third = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert json.loads(third.text.splitlines()[-1])["type"] == "operation.completed"
        assert runner.calls == 2


@pytest.mark.asyncio
async def test_cancellation_closes_spawn_permission_before_runner_resumes(tmp_path, monkeypatch):
    class LateSpawnRunner:
        denied = False

        async def run(self, _kind, _request, files):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                try:
                    files.spawn(Path(sys.executable), ("-c", "import time; time.sleep(30)"))
                except RuntimeError:
                    self.denied = True
                raise

    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.02)
    runner = LateSpawnRunner()
    app = make_app(tmp_path, runner)
    async with await client_for(app) as client:
        await login(client)
        await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
    assert runner.denied
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_cancel_before_execute_starts_releases_lease_and_registry(tmp_path, monkeypatch):
    class CountingRunner:
        calls = 0

        async def run(self, _kind, _request, _files):
            self.calls += 1
            return NormalizeResult(facts=[], unresolved=[]), UsagePayload(logicalAttempts=0)

    runner = CountingRunner()
    monkeypatch.setattr(service, "MAX_CONCURRENT", 1)
    app = make_app(tmp_path, runner)
    original_create_task = asyncio.create_task
    cancelled_before_start = False

    def cancel_execute(coroutine):
        nonlocal cancelled_before_start
        task = original_create_task(coroutine)
        code = getattr(coroutine, "cr_code", None)
        if code is not None and code.co_name == "execute" and not cancelled_before_start:
            cancelled_before_start = True
            task.cancel()
        return task

    async with await client_for(app) as client:
        await login(client)
        monkeypatch.setattr(service.asyncio, "create_task", cancel_execute)
        try:
            await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        except (asyncio.CancelledError, AssertionError):
            # HTTPX asserts when a cancelled stream never sends its final body.
            pass
        finally:
            monkeypatch.setattr(service.asyncio, "create_task", original_create_task)
        await asyncio.sleep(0)
        assert cancelled_before_start
        assert runner.calls == 0
        next_result = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert json.loads(next_result.text.splitlines()[-1])["type"] == "operation.completed"
        assert runner.calls == 1
        assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_concurrent_bound_and_disconnect_cancel_active_work(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "MAX_CONCURRENT", 1)
    runner = ResultRunner()
    app = make_app(tmp_path, runner)
    async with await client_for(app) as client:
        exchange = await login(client)
        first = asyncio.create_task(client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT))
        await asyncio.wait_for(runner.started.wait(), 1)
        second = await client.post("/v1/normalize", headers={"Origin": ORIGIN}, json=INPUT)
        assert json.loads(second.text)["payload"]["code"] == "BUSY"
        runner.release.set()
        assert (await first).status_code == 200
        assert list((tmp_path / "operations").iterdir()) == []

        runner2 = ResultRunner()
        app2 = make_app(tmp_path, runner2)
        async with await client_for(app2) as client2:
            exchange2 = await login(client2)
            cookie = exchange2.headers["set-cookie"].split(";", 1)[0]
            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
            await queue.put({"type": "http.request", "body": json.dumps(INPUT).encode(), "more_body": False})
            sent: list[dict[str, object]] = []

            async def receive():
                return await queue.get()

            async def send(message):
                sent.append(message)

            scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
                "scheme": "http", "path": "/v1/normalize", "raw_path": b"/v1/normalize", "query_string": b"",
                "headers": [(b"host", b"127.0.0.1:39271"), (b"origin", ORIGIN.encode()),
                            (b"content-type", b"application/json"), (b"cookie", cookie.encode())],
                "client": ("127.0.0.1", 23456), "server": ("127.0.0.1", 39271),
            }
            call = asyncio.create_task(app2(scope, receive, send))
            await asyncio.wait_for(runner2.started.wait(), 1)
            await queue.put({"type": "http.disconnect"})
            await asyncio.wait_for(call, 1)
            assert runner2.cancelled
            assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_stalled_request_body_and_unexpected_error_are_sanitized(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(service, "BODY_TIMEOUT_SECONDS", 0.02)
    app = make_app(tmp_path)
    async with await client_for(app) as client:
        exchange = await login(client)
        cookie = exchange.headers["set-cookie"].split(";", 1)[0]
        app.app.router.routes.insert(0, APIRoute("/v1/boom", lambda: (_ for _ in ()).throw(ValueError("private-marker")), methods={"GET"}))
        failure = await client.get("/v1/boom")
        assert failure.status_code == 500 and failure.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "private-marker" not in failure.text
        assert "private-marker" not in "".join(capsys.readouterr())

        async def stalled():
            await asyncio.Event().wait()

        sent: list[dict[str, object]] = []

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
            "scheme": "http", "path": "/v1/normalize", "raw_path": b"/v1/normalize", "query_string": b"",
            "headers": [(b"host", b"127.0.0.1:39271"), (b"origin", ORIGIN.encode()),
                        (b"content-type", b"application/json"), (b"cookie", cookie.encode())],
            "client": ("127.0.0.1", 23456), "server": ("127.0.0.1", 39271),
        }
        await app(scope, stalled, send)
        assert sent[0]["status"] == 408
        assert b"REQUEST_TIMEOUT" in sent[1]["body"]


@pytest.mark.asyncio
async def test_invalid_header_bytes_and_late_stream_failure_do_not_log_candidate(tmp_path, capsys):
    app = make_app(tmp_path)

    async def receive():
        await asyncio.Event().wait()

    async def invoke(path, headers):
        sent = []

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
                 "query_string": b"", "headers": headers,
                 "client": ("127.0.0.1", 23456), "server": ("127.0.0.1", 39271)}
        await asyncio.wait_for(app(scope, receive, send), 1)
        return sent

    for headers in ([(b"host", b"\xff"), (b"origin", ORIGIN.encode())],
                    [(b"host", b"127.0.0.1:39271"), (b"origin", b"\xff")]):
        sent = await invoke("/v1/capabilities", headers)
        assert sent[0]["status"] == 403
        assert b"private-marker" not in sent[1]["body"]

    async def broken_stream():
        yield b"safe chunk"
        raise ValueError("private-marker")

    app.app.router.routes.insert(0, APIRoute("/v1/stream-boom", lambda: StreamingResponse(broken_stream()), methods={"GET"}))
    async with await client_for(app) as client:
        exchange = await login(client)
    cookie = exchange.headers["set-cookie"].split(";", 1)[0].encode()
    sent = await invoke("/v1/stream-boom", [(b"host", b"127.0.0.1:39271"), (b"cookie", cookie)])
    assert sent[0]["status"] == 200
    assert any(message.get("body") == b"safe chunk" for message in sent)
    assert all(b"private-marker" not in message.get("body", b"") for message in sent)
    assert "private-marker" not in "".join(capsys.readouterr())


def test_reaper_removes_only_owned_stale_dirs(tmp_path):
    root = tmp_path / "ops"
    root.mkdir()
    with operation(root, owner=OWNER) as stale:
        stale_name = stale.name
        (stale / "private.txt").write_text("synthetic", encoding="utf-8")
    # Build one stale directory with the reviewed marker format.
    stale = root / stale_name
    stale.mkdir()
    (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": stale_name[3:]}), encoding="utf-8")
    (stale / ".lock").touch()
    (stale / "private.txt").write_text("synthetic", encoding="utf-8")
    unrelated = root / "other"
    unrelated.mkdir()
    (unrelated / "private.txt").write_text("keep", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    (root / ("op-" + "f" * 32)).symlink_to(target, target_is_directory=True)
    with operation(root, owner=OWNER) as active:
        assert reap_owned(root) == 1
        assert active.is_dir()
    assert reap_owned(root) == 0
    assert list(root.glob(".cleanup-intent-op-*.json")) == []
    assert unrelated.joinpath("private.txt").read_text(encoding="utf-8") == "keep"
    assert target.is_dir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(SpikeError, match="UNSAFE_TEMP_ROOT"):
        reap_owned(alias)


@pytest.mark.asyncio
async def test_reaper_partial_cleanup_intent_blocks_service_restart(tmp_path, monkeypatch):
    from spikes.cli import runner as spike_runner

    root = tmp_path / "operations"
    root.mkdir()
    identifier = "a" * 32
    stale = root / f"op-{identifier}"
    stale.mkdir()
    (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
    (stale / ".lock").touch()
    (stale / "synthetic.txt").write_text("synthetic")
    original_remove = spike_runner.shutil.rmtree

    def partial_remove(path, *args, **kwargs):
        if Path(path) == stale:
            (stale / ".owner").unlink()
            (stale / ".lock").unlink()
            raise OSError("synthetic partial reaping")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(spike_runner.shutil, "rmtree", partial_remove)
    with pytest.raises(SpikeError, match="CLEANUP_FAILED"):
        reap_owned(root)
    monkeypatch.setattr(spike_runner.shutil, "rmtree", original_remove)
    assert stale.is_dir() and (stale / "synthetic.txt").is_file()
    assert len(list(root.glob(".cleanup-intent-op-*.json"))) == 1
    app = make_app(tmp_path)
    async with await client_for(app) as client:
        await login(client)
        assert (await client.get("/v1/capabilities")).json()["renderers"] == []
    assert stale.is_dir()


def test_worker_cleanup_on_failure(tmp_path):
    files = OperationFiles(tmp_path / "ops")
    script = tmp_path / "worker.py"
    script.write_text("import subprocess, sys, time\n"
                      "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                      "open(sys.argv[1], 'w').write(str(child.pid))\n"
                      "time.sleep(30)\n", encoding="utf-8")
    child_pid = tmp_path / "child.pid"
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with files.open():
            process = files.spawn(Path(sys.executable), (str(script), str(child_pid)))
            assert process.poll() is None
            deadline = time.monotonic() + 2
            while not child_pid.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert child_pid.exists()
            raise RuntimeError("synthetic failure")
    assert group_members(process.pid) == []
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed
    assert list((tmp_path / "ops").iterdir()) == []


def test_unsupported_process_cleanup_host_fails_clearly(monkeypatch):
    monkeypatch.setattr(lifecycle.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="macOS arm64 only"):
        lifecycle.require_supported_host()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["startup", "shutdown"])
async def test_launcher_bounds_startup_and_shutdown(tmp_path, monkeypatch, phase):
    dist = tmp_path / "apps/web/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("synthetic shell", encoding="utf-8")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "trusted_temp_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(launcher, "require_supported_host", lambda: None)
    monkeypatch.setattr(launcher, "STARTUP_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(launcher, "SHUTDOWN_TIMEOUT_SECONDS", 0.02)

    class SlowServer:
        def __init__(self, _config):
            self.started = phase == "shutdown"
            self.should_exit = False

        async def serve(self, *, sockets):
            assert sockets
            if phase == "shutdown":
                self.should_exit = True
            await asyncio.Event().wait()

    monkeypatch.setattr(launcher.uvicorn, "Server", SlowServer)
    start = time.monotonic()
    with pytest.raises(RuntimeError, match=f"Service {phase} timed out"):
        await launcher.launch(open_browser=False)
    assert time.monotonic() - start < 0.5


@pytest.mark.asyncio
async def test_html_entries_are_fresh_and_static_assets_keep_the_existing_cache_policy(tmp_path):
    def forbidden(*_args):
        pytest.fail("Static entry started content work")
    app = make_app(tmp_path, forbidden)
    dist = tmp_path / "dist"
    for name in ("next.html", "legacy.html"):
        (dist / name).write_text(f"<html>{name}</html>", encoding="utf-8")
    async with await client_for(app) as client:
        for path in ("/", "/index.html", "/next.html", "/legacy.html", "/saved/project"):
            result = await client.get(path)
            assert result.status_code == 200
            assert result.headers["cache-control"] == "no-store"
        asset = await client.get("/asset.js")
        assert asset.status_code == 200
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        (dist / "index.html").unlink()
        unavailable = await client.get("/")
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "FRONTEND_UNAVAILABLE"
        assert (await client.get("/legacy.html")).status_code == 200
