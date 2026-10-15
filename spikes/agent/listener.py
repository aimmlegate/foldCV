"""Synthetic tools behind an authenticated, owned HTTP MCP listener."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from html.parser import HTMLParser
import secrets
import socket

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import Response
import uvicorn

PUBLIC_URL = "https://docs.python.org/3/library/asyncio.html"


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.text = []

    def handle_starttag(self, tag, _attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.text.append(data.strip())


class ProofMcp:
    def __init__(self, *, delayed_read: bool = False, allow_web: bool = True):
        self.token = secrets.token_urlsafe(32)
        self.allow_web = allow_web
        self.delayed_read = delayed_read
        self.active = True
        self.calls = []
        self.source = None
        self.read_started = asyncio.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(128)
        self.port = self.listener.getsockname()[1]
        self.host = f"127.0.0.1:{self.port}"
        self.url = f"http://{self.host}/mcp"
        self.sdk = FastMCP("foldcv", stateless_http=True, json_response=True,
                           max_request_body_size=65536,
                           transport_security=TransportSecuritySettings(
                               allowed_hosts=[self.host], allowed_origins=[]))

        @self.sdk.tool()
        async def get_resume_context() -> dict:
            """Read the bound synthetic resume and its current revisions."""
            self.record("get_resume_context")
            self.read_started.set()
            if self.delayed_read:
                await asyncio.sleep(25)
            return {"documentRevision": 1, "factRevision": 1,
                    "blocks": [{"id": "profile", "text": "Python developer. Built HTTP APIs."}],
                    "facts": ["Python", "HTTP APIs"], "scope": "whole_resume"}

        @self.sdk.tool()
        def check_resume() -> dict:
            """Run deterministic checks on the unchanged synthetic resume."""
            self.record("check_resume")
            return {"documentRevision": 1, "factRevision": 1,
                    "changed": False, "warnings": []}

        if allow_web:
            @self.sdk.tool()
            async def read_public_page(url: str) -> dict:
                """Retrieve the official asyncio reference; other URLs are denied in this proof."""
                self.record("read_public_page")
                if url != PUBLIC_URL:
                    raise ValueError("SOURCE_NOT_ALLOWED")
                async with httpx.AsyncClient(trust_env=False, timeout=15,
                                             follow_redirects=False) as client:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 2 * 1024 * 1024:
                                raise ValueError("SOURCE_TOO_LARGE")
                parser = PageText()
                parser.feed(body.decode("utf-8", "strict"))
                text = "\n".join(parser.text)
                self.source = {"id": "source-python-asyncio", "url": url,
                               "sha256": hashlib.sha256(body).hexdigest(),
                               "text": text[:12000], "truncated": len(text) > 12000}
                return self.source

        self.application = self.sdk.streamable_http_app()
        self.server = uvicorn.Server(uvicorn.Config(
            self, log_level="critical", access_log=False, server_header=False,
            timeout_graceful_shutdown=1, lifespan="on"))
        self.task = None

    def record(self, name):
        if not self.active:
            raise ValueError("RUN_REVOKED")
        if len(self.calls) >= 24:
            raise ValueError("TOOL_LIMIT")
        self.calls.append(name)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.application(scope, receive, send)
        headers = {key.lower(): value for key, value in scope["headers"]}
        authorized = hmac.compare_digest(headers.get(b"authorization", b""),
                                         ("Bearer " + self.token).encode())
        if (not self.active or headers.get(b"host") != self.host.encode()
                or b"origin" in headers or not authorized):
            return await Response(status_code=403)(scope, receive, send)
        return await self.application(scope, receive, send)

    async def start(self):
        self.task = asyncio.create_task(self.server.serve(sockets=[self.listener]))
        async with asyncio.timeout(5):
            while not self.server.started:
                if self.task.done():
                    await self.task
                    raise RuntimeError("MCP_START_FAILED")
                await asyncio.sleep(0.01)

    async def close(self):
        self.active = False
        self.server.should_exit = True
        if self.task is not None:
            await asyncio.wait_for(self.task, 3)
        self.listener.close()
