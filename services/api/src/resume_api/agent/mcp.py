"""A capability-only listener; browser cookies and Origins grant no access."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import hmac
import logging
import secrets
import socket

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse, Response
import uvicorn
from resume_api.providers.codex_cli import strict_json


class ListenerServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # The outer application owns process signals.
        yield


class PrivateMcp:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        self.token = secrets.token_urlsafe(32)
        self.token_sha256 = hashlib.sha256(self.token.encode()).hexdigest()
        self.active = True
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        self.host = "127.0.0.1:" + str(self.listener.getsockname()[1])
        self.url = "http://" + self.host + "/mcp"
        logging.getLogger("mcp").setLevel(logging.CRITICAL)
        self.sdk = FastMCP("foldcv", stateless_http=True, json_response=True, log_level="CRITICAL",
            max_request_body_size=65536, transport_security=TransportSecuritySettings(
                allowed_hosts=[self.host], allowed_origins=[]))
        self.application = None
        self.server = ListenerServer(uvicorn.Config(self, log_level="critical", access_log=False,
            server_header=False, timeout_graceful_shutdown=1, lifespan="on"))
        self.task, self.close_task = None, None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.application(scope, receive, send)
        pairs = scope["headers"]
        headers = {key.lower(): value for key, value in pairs}
        names = [key.lower() for key, value in pairs]
        authorization = headers.get(b"authorization", b"")
        authorized = hmac.compare_digest(hashlib.sha256(authorization).digest(),
            hashlib.sha256(("Bearer " + self.token).encode()).digest())
        if (not self.active or not self.token or headers.get(b"host") != self.host.encode()
                or b"origin" in names or not authorized or scope["path"] != "/mcp"
                or any(names.count(name) > 1 for name in (b"host", b"authorization", b"content-length"))
                or b"transfer-encoding" in names):
            return await Response(status_code=403)(scope, receive, send)
        if scope["method"] not in {"POST", "GET", "DELETE"}:
            return await Response(status_code=405)(scope, receive, send)
        if scope["method"] == "POST":
            declared = headers.get(b"content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > 65536):
                return await Response(status_code=413)(scope, receive, send)
            body = bytearray()
            try:
                async with asyncio.timeout(2):
                    while True:
                        part = await receive()
                        if part["type"] == "http.disconnect":
                            return
                        body.extend(part.get("body", b""))
                        if len(body) > 65536:
                            return await Response(status_code=413)(scope, receive, send)
                        if not part.get("more_body", False):
                            break
            except asyncio.TimeoutError:
                return await Response(status_code=408)(scope, receive, send)
            if declared is not None and int(declared) != len(body):
                return await Response(status_code=400)(scope, receive, send)
            try:
                payload = strict_json(bytes(body), max_bytes=65536)
            except (ValueError, UnicodeError, RecursionError):
                return await Response(status_code=400)(scope, receive, send)
            if not isinstance(payload, dict):
                return await Response(status_code=400)(scope, receive, send)
            if payload.get("method") == "tools/call":
                error = self.dispatcher.preflight(payload.get("params"))
                if error is not None:
                    identifier = payload.get("id")
                    if not (type(identifier) is int or isinstance(identifier, str) and len(identifier) <= 128):
                        return await Response(status_code=400)(scope, receive, send)
                    failure = self.dispatcher.preflight_failure(error)
                    result = self.dispatcher.wire(failure).model_dump(mode="json", by_alias=True, exclude_none=True)
                    return await JSONResponse({"jsonrpc": "2.0", "id": identifier, "result": result})(scope, receive, send)
            delivered = False
            original = receive
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original()
            receive = replay
        return await self.application(scope, receive, send)

    async def start(self):
        self.application = self.sdk.streamable_http_app()
        self.task = asyncio.create_task(self.server.serve(sockets=[self.listener]))
        try:
            async with asyncio.timeout(5):
                while not self.server.started:
                    if self.task.done():
                        await self.task
                        raise RuntimeError("MCP_START_FAILED")
                    await asyncio.sleep(0.01)
        except BaseException:
            await self.close()
            raise

    async def close(self):
        if self.close_task is None:
            self.close_task = asyncio.create_task(self._close())
        await asyncio.shield(self.close_task)

    async def _close(self):
        self.active = False
        self.token = ""
        self.dispatcher.revoke()
        self.server.should_exit = True
        try:
            await self.dispatcher.close()
            if self.task is not None:
                await asyncio.wait_for(self.task, 2)
        finally:
            self.listener.close()
