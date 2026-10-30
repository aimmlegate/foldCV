"""`resume_api.app.LocalBoundary` and the static frontend route: loopback host and origin, the one-use secret and its
cookie, body limits and deadline, strict JSON, duplicate headers and sanitized failures (G9)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.responses import StreamingResponse

from resume_api import app as service
from resume_api import extracting
from tests.service.app_fixtures import HealthyConnection, ORIGIN, PROJECT, SECRET, add_project, make_app


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)


async def login(client: httpx.AsyncClient):
    return await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})


def scope(path, cookie=b"", method="POST", headers=None):
    base = [(b"host", b"127.0.0.1:39281"), (b"origin", ORIGIN.encode()), (b"content-type", b"application/json")]
    return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
            "path": path, "raw_path": path.encode(), "query_string": b"",
            "headers": headers if headers is not None else base + ([(b"cookie", cookie)] if cookie else []),
            "client": ("127.0.0.1", 23456), "server": ("127.0.0.1", 39281)}


class CountingConnection(HealthyConnection):
    def __init__(self):
        self.calls = 0

    def inspect(self, files, cancel, *, full=True):
        self.calls += 1
        return super().inspect(files, cancel, full=full)


@pytest.mark.asyncio
async def test_exact_host_origin_one_use_secret_and_cookie_scope(tmp_path):
    app = make_app(tmp_path)
    async with client_for(app) as client:
        assert (await client.get("/v1/settings/connection")).status_code == 401
        assert (await client.get("/v2/projects")).status_code == 401
        assert (await client.post("/v1/session/exchange", headers={"Origin": "http://evil.invalid"},
                                  json={"secret": SECRET})).status_code == 403
        assert (await client.post("/v1/session/exchange", headers={"Origin": ORIGIN, "Host": "localhost:39281"},
                                  json={"secret": SECRET})).status_code == 403
        reply = await login(client)
        assert reply.status_code == 200
        cookie = reply.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
        assert SECRET not in reply.text + cookie
        assert (await login(client)).status_code == 401
        connection = await client.get("/v1/settings/connection")
        assert connection.status_code == 200 and connection.headers["cache-control"] == "no-store"
        assert connection.json()["generationReady"] is False
        assert (await client.get("/v2/projects")).status_code == 200
        assert (await client.post("/v1/host/status", json={})).status_code == 403
        assert (await client.post("/v1/host/status", headers={"Origin": "http://evil.invalid"}, json={})).status_code == 403
        assert (await client.post("/v2/projects/" + PROJECT + "/open", json={})).status_code == 403
        assert (await client.get("/v1/settings/connection", headers={"X-Forwarded-Host": "127.0.0.1:39281"})).status_code == 403
        assert (await client.get("/v1/settings/connection?candidate=secret")).status_code == 403
        duplicate = await client.get("/v1/settings/connection",
                                     headers=[("Host", "127.0.0.1:39281"), ("Host", "127.0.0.1:39281")])
        assert duplicate.status_code == 403


@pytest.mark.asyncio
async def test_malformed_oversized_and_unavailable_routes_are_safe(tmp_path):
    app = make_app(tmp_path)
    add_project(app)
    async with client_for(app) as client:
        await login(client)
        headers = {"Origin": ORIGIN}
        bad = await client.put("/v1/settings/rules", headers=headers, json={"markdown": "private-marker", "baseRevision": "bad"})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_REQUEST"
        assert "private-marker" not in bad.text
        json_headers = {**headers, "Content-Type": "application/json"}
        for path in ("/v1/host/status", f"/v2/projects/{PROJECT}/open"):
            large = await client.post(path, headers=json_headers, content=b"x" * (service.MAX_BODY + 1))
            assert large.status_code == 413 and large.json()["error"]["code"] == "INPUT_TOO_LARGE"
        edits = f"/v2/projects/{PROJECT}/edits"
        # An edit envelope may exceed 1 MiB by the token and base revision, not more.
        within = await client.post(edits, headers=json_headers, content=b"x" * (service.MAX_BODY + 1))
        assert within.status_code == 422 and within.json()["error"]["code"] == "INVALID_REQUEST"
        beyond = await client.post(edits, headers=json_headers, content=b"x" * (service.MAX_BODY + 64 * 1024 + 1))
        assert beyond.status_code == 413
        upload = await client.post("/v1/rich/projects/template-input", headers=headers,
                                   files={"file": ("big.txt", b"a" * (extracting.MAX_BODY + 1))})
        assert upload.status_code == 413 and upload.json()["error"]["code"] == "INPUT_TOO_LARGE"
        closed = await client.post("/v1/rich/projects/template-input", headers=headers, files={"file": ("x.txt", b"x")})
        assert closed.status_code == 409 and closed.json()["error"]["code"] == "JOB_DISABLED"
        assert closed.headers["cache-control"] == "no-store"
        # The upload with a chosen template has the upload limit, not the 1 MiB JSON one.
        chosen = await client.post("/v1/rich/projects/template-input/generic-two-column", headers=headers,
                                   files={"file": ("big.txt", b"a" * (service.MAX_BODY + 1))})
        assert chosen.status_code == 409 and chosen.json()["error"]["code"] == "JOB_DISABLED"
        too_big = await client.post("/v1/rich/projects/template-input/generic-two-column", headers=headers,
                                    files={"file": ("big.txt", b"a" * (extracting.MAX_BODY + 1))})
        assert too_big.status_code == 413 and too_big.json()["error"]["code"] == "INPUT_TOO_LARGE"
        assert (await client.post("/v1/host/login", headers=headers, json={"argv": ["codex", "login"]})).status_code == 422
        assert (await client.post("/v1/host/login", headers=headers, json={})).status_code == 409
        assert (await client.post(f"/v2/projects/{PROJECT}/export", headers=headers, json={})).status_code == 422
        not_multipart = await client.post("/v1/rich/projects/template-input", headers=headers, json={})
        assert not_multipart.status_code == 422 and not_multipart.json()["error"]["code"] == "INVALID_REQUEST"
        fake = await client.post("/v1/rich/projects/template-input",
                                 headers={**headers, "Content-Type": "multipart/form-data; boundary=fake"}, content=b"test")
        assert fake.status_code == 422
        assert (await client.get("/")).text == "<html>synthetic shell</html>"
        assert (await client.get("/asset.js")).text == "safe asset"


@pytest.mark.asyncio
async def test_static_fallback_and_assets_cannot_follow_escape_symlinks(tmp_path):
    app = make_app(tmp_path)
    outside = tmp_path / "private-marker"
    outside.write_text("private-marker", encoding="utf-8")
    for name in ("index.html", "asset.js"):
        target = tmp_path / "dist" / name
        target.unlink()
        target.symlink_to(outside)
    async with client_for(app) as client:
        for path in ("/", "/missing", "/asset.js"):
            result = await client.get(path)
            assert result.status_code == 404
            assert "private-marker" not in result.text


@pytest.mark.asyncio
async def test_duplicate_json_fields_media_types_and_method_errors_are_safe(tmp_path):
    app = make_app(tmp_path)
    add_project(app)
    async with client_for(app) as client:
        headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
        duplicate_media = await client.post("/v1/session/exchange", headers=[
            ("Origin", ORIGIN), ("Content-Type", "application/json"), ("Content-Type", "text/plain")],
            content=json.dumps({"secret": SECRET}))
        assert duplicate_media.status_code == 422 and duplicate_media.json()["error"]["code"] == "INVALID_REQUEST"
        double_secret = await client.post("/v1/session/exchange", headers=headers,
                                          content=json.dumps({"secret": SECRET})[:-1] + ',"secret":"private-marker"}')
        assert double_secret.status_code == 422 and "private-marker" not in double_secret.text
        await login(client)
        token = (await client.post(f"/v2/projects/{PROJECT}/open", headers={"Origin": ORIGIN}, json={})).json()["editorToken"]
        duplicates = {"/v1/host/select": ['{"model":"a","model":"b"}', '{"model":"a","extra":{"x":1,"x":2}}'],
                      f"/v2/projects/{PROJECT}/edits": ['{"editorToken":"%s","editorToken":"%s"}' % (token, token)]}
        for path, bodies in duplicates.items():
            for content in bodies:
                result = await client.post(path, headers=headers, content=content)
                assert result.status_code == 422 and result.json()["error"]["code"] == "INVALID_REQUEST"
                assert result.headers["cache-control"] == "no-store"
        duplicate_body = '{"model":"a","model":"b"}'
        for media in ("application/vnd.foldcv+json", "Application/JSON", "application/json ; charset=utf-8"):
            result = await client.post("/v1/host/select", headers={"Origin": ORIGIN, "Content-Type": media},
                                       content=duplicate_body)
            assert result.status_code == 422 and result.json()["error"]["code"] == "INVALID_REQUEST"
            accepted = await client.post("/v1/host/select", headers={"Origin": ORIGIN, "Content-Type": media},
                                         content='{"model":"gpt-6-luna"}')
            assert accepted.status_code == 409 and accepted.json()["error"]["code"] == "MODEL_DENIED"
        for path in ("/v1/host/select", f"/v2/projects/{PROJECT}/open"):
            missing_media = await client.post(path, headers={"Origin": ORIGIN}, content="{}")
            assert missing_media.status_code == 415 and missing_media.json()["error"]["code"] == "INVALID_REQUEST"
        swapped = await client.post("/v1/host/select", headers=[
            ("Origin", ORIGIN), ("Content-Type", "text/plain"), ("Content-Type", "application/json")], content="{}")
        assert swapped.status_code == 422 and swapped.json()["error"]["code"] == "INVALID_REQUEST"
        for result in (await client.post("/v1/settings/connection", headers={"Origin": ORIGIN}, json={}),
                       await client.get("/v1/host/status")):
            assert result.status_code == 405
            assert result.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
            assert result.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_startup_settings_and_static_routes_never_call_the_content_provider(tmp_path):
    class ForbiddenProvider:
        calls = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("unexpected content operation")

    provider = ForbiddenProvider()
    app = make_app(tmp_path, content_provider=provider, connection_adapter=HealthyConnection())
    async with client_for(app) as client:
        await login(client)
        headers = {"Origin": ORIGIN}
        assert (await client.get("/v1/settings/connection")).json()["generationReady"] is False
        assert (await client.get("/")).status_code == 200 and (await client.get("/asset.js")).status_code == 200
        status = await client.post("/v1/host/status", headers=headers, json={})
        assert status.status_code == 200 and status.json()["generationReady"] is False
        assert (await client.get("/v1/settings/rules")).status_code == 200
        assert (await client.get("/v1/rich/template-import")).json()["available"] is False
        assert (await client.post("/v1/rich/projects/template-input", headers=headers,
                                  files={"file": ("x.txt", b"synthetic")})).status_code == 409
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_a_stalled_body_times_out_by_the_deadline_and_unexpected_errors_are_sanitized(tmp_path, monkeypatch, capsys):
    app = make_app(tmp_path)
    async with client_for(app) as client:
        exchange = await login(client)
        cookie = exchange.headers["set-cookie"].split(";", 1)[0].encode()
        app.app.router.routes.insert(0, APIRoute("/v1/boom", lambda: (_ for _ in ()).throw(ValueError("private-marker")),
                                                 methods={"GET"}))
        failure = await client.get("/v1/boom")
        assert failure.status_code == 500 and failure.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "private-marker" not in failure.text

    class Clock:
        """Each reading is ten seconds after the previous one, so the body deadline has passed at the first check."""
        now = 0.0

        def monotonic(self):
            self.now += service.BODY_TIMEOUT_SECONDS
            return self.now

    monkeypatch.setattr(service, "time", Clock())
    received = []

    async def stalled():
        received.append(True)
        await asyncio.Event().wait()

    sent: list[dict[str, object]] = []

    async def send(message):
        sent.append(message)

    await asyncio.wait_for(app(scope("/v1/host/status", cookie), stalled, send), 1)
    assert sent[0]["status"] == 408 and b"REQUEST_TIMEOUT" in sent[1]["body"]
    assert received == []
    assert "private-marker" not in "".join(capsys.readouterr())


@pytest.mark.asyncio
async def test_a_disconnect_during_the_body_starts_no_work(tmp_path):
    connection = CountingConnection()
    app = make_app(tmp_path, connection_adapter=connection)
    async with client_for(app) as client:
        exchange = await login(client)
    cookie = exchange.headers["set-cookie"].split(";", 1)[0].encode()
    messages = [{"type": "http.request", "body": b"{", "more_body": True}, {"type": "http.disconnect"}]

    async def receive():
        return messages.pop(0)

    sent: list[dict[str, object]] = []

    async def send(message):
        sent.append(message)

    await asyncio.wait_for(app(scope("/v1/host/status", cookie), receive, send), 1)
    assert sent == [] and messages == [] and connection.calls == 0
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_invalid_header_bytes_and_late_stream_failure_do_not_log_candidate(tmp_path, capsys):
    app = make_app(tmp_path)

    async def receive():
        await asyncio.Event().wait()

    async def invoke(path, headers):
        sent = []

        async def send(message):
            sent.append(message)

        await asyncio.wait_for(app(scope(path, method="GET", headers=headers), receive, send), 1)
        return sent

    for headers in ([(b"host", b"\xff"), (b"origin", ORIGIN.encode())],
                    [(b"host", b"127.0.0.1:39281"), (b"origin", b"\xff")]):
        sent = await invoke("/v1/settings/connection", headers)
        assert sent[0]["status"] == 403
        assert b"private-marker" not in sent[1]["body"]

    async def broken_stream():
        yield b"safe chunk"
        raise ValueError("private-marker")

    app.app.router.routes.insert(0, APIRoute("/v1/stream-boom", lambda: StreamingResponse(broken_stream()), methods={"GET"}))
    async with client_for(app) as client:
        exchange = await login(client)
    cookie = exchange.headers["set-cookie"].split(";", 1)[0].encode()
    sent = await invoke("/v1/stream-boom", [(b"host", b"127.0.0.1:39281"), (b"cookie", cookie)])
    assert sent[0]["status"] == 200
    assert any(message.get("body") == b"safe chunk" for message in sent)
    assert all(b"private-marker" not in message.get("body", b"") for message in sent)
    assert "private-marker" not in "".join(capsys.readouterr())


@pytest.mark.asyncio
async def test_html_entries_are_fresh_and_static_assets_keep_the_existing_cache_policy(tmp_path):
    app = make_app(tmp_path)
    dist = tmp_path / "dist"
    for name in ("next.html", "legacy.html"):
        (dist / name).write_text(f"<html>{name}</html>", encoding="utf-8")
    async with client_for(app) as client:
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


@pytest.mark.asyncio
async def test_every_json_write_under_v1_refuses_duplicate_fields(tmp_path):
    app = make_app(tmp_path)
    routes = [route for route in app.app.routes if isinstance(route, APIRoute)]
    puts = [route.path for route in routes if "PUT" in route.methods]
    assert puts and all(service.takes_json("PUT", path) for path in puts)
    async with client_for(app) as client:
        await login(client)
        headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
        bodies = {"/v1/settings/limits": '{"importMinutes":5,"importMinutes":90,"projectMegabytes":64}',
                  "/v1/settings/preferences": '{"automaticAnalysis":true,"automaticAnalysis":false}',
                  "/v1/settings/import-model": '{"model":"a","model":"b"}', "/v1/settings/fallback-model": '{"model":"a","model":"b"}',
                  "/v1/settings/rewrite-model": '{"model":"a","model":"b"}',
                  "/v1/settings/rewrite-reasoning": '{"model":"a","model":"b","effort":"low"}',
                  "/v1/rich/template-default": '{"templateId":"a","templateId":"b"}',
                  "/v1/rich/template-config/generic-two-column": '{"text":"a","text":"b"}'}
        for path, content in bodies.items():
            result = await client.put(path, headers=headers, content=content)
            assert result.status_code == 422 and result.json()["error"]["code"] == "INVALID_REQUEST", path
        check = await client.post("/v1/rich/template-config/generic-two-column/check", headers=headers, content='{"text":"a","text":"b"}')
        assert check.status_code == 422 and check.json()["error"]["code"] == "INVALID_REQUEST"
        wrong = await client.put("/v1/settings/limits", headers={"Origin": ORIGIN, "Content-Type": "text/plain"},
                                 content='{"importMinutes":5,"projectMegabytes":64}')
        assert wrong.status_code == 415
        kept = (await client.get("/v1/settings/preferences")).json()
        assert kept["importMinutes"] == 60


@pytest.mark.asyncio
async def test_template_text_up_to_the_compiler_limit_reaches_the_compiler(tmp_path):
    from packages.resume_core.templates.loading import CONFIG_BYTES
    app = make_app(tmp_path)
    async with client_for(app) as client:
        await login(client)
        headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
        path = "/v1/rich/template-config/generic-two-column/check"
        allowed = await client.post(path, headers=headers, content=json.dumps({"text": "#\n" * (CONFIG_BYTES // 2)}))
        assert allowed.status_code != 413, allowed.text[:200]
        beyond = await client.post(path, headers=headers, content=b"x" * (2 * CONFIG_BYTES + 1))
        assert beyond.status_code == 413 and beyond.json()["error"]["code"] == "INPUT_TOO_LARGE"
