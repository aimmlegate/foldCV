"""Fake DNS and pinned sockets cover public fetch limits without public traffic."""

from email.message import Message
import gzip
from io import BytesIO
from pathlib import Path
import socket
import sys
import threading

import pytest

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.models.agent import wire_bytes
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api.agent.web import BODY_BYTES, PublicFetcher, destination, fetch_page


def public_dns(host, port, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]


class Response:
    def __init__(self, data=b"Public Python documentation.", *, status=200, headers=None):
        self.body, self.status = BytesIO(data), status
        self.headers = Message()
        for key, value in (headers or {"Content-Type": "text/plain; charset=utf-8"}).items():
            self.headers[key] = value

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, count):
        return self.body.read(count)


class Transport:
    def __init__(self, responses):
        self.responses, self.connections, self.requests, self.closed = list(responses), [], [], 0

    def __call__(self, host, port, address, secure, timeout):
        self.connections.append((host, port, address, secure, timeout))
        response = self.responses.pop(0)
        owner = self
        class Connection:
            def request(self, method, path, *, headers):
                owner.requests.append((method, path, headers))
            def getresponse(self):
                return response
            def close(self):
                owner.closed += 1
        return Connection()


def test_fetch_pins_validated_ip_and_extracts_text_without_script_or_credentials():
    transport = Transport([Response(b"<html><title>Python docs</title><script>steal()</script><p>Async APIs</p></html>",
        headers={"Content-Type": "text/html"})])
    source = fetch_page("https://public.example/guide#section", resolver=public_dns, connector=transport)
    assert source.text == "Python docs\nAsync APIs" and source.title == "Python docs"
    assert source.final_url == "https://public.example/guide"
    assert transport.connections[0][:4] == ("public.example", 443, "93.184.215.14", True)
    method, path, headers = transport.requests[0]
    assert method == "GET" and path == "/guide" and not {"Cookie", "Authorization", "Proxy-Authorization"} & headers.keys()
    assert transport.closed == 1 and source.content_sha256


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@public.example/", "https://public.example:444/",
    "http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/", "http://public.example/\nheader", "http://public.example\\@private/"])
def test_invalid_urls_and_nonpublic_destinations_are_denied(url):
    def dns(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host if host in {"127.0.0.1", "::1", "169.254.169.254"} else "93.184.215.14", port))]
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_DENIED"):
        destination(url, dns)


def test_mixed_dns_and_rebinding_redirect_are_denied_before_connecting_private_address():
    def mixed(host, port, **kwargs):
        return public_dns(host, port) + [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_DENIED"):
        destination("https://mixed.example", mixed)
    calls = []
    def rebinding(host, port, **kwargs):
        calls.append(host)
        return public_dns(host, port) if len(calls) == 1 else [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
    transport = Transport([Response(status=302, headers={"Location": "/next"})])
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_DENIED"):
        fetch_page("https://public.example/start", resolver=rebinding, connector=transport)
    assert len(transport.connections) == transport.closed == 1 and calls == ["public.example", "public.example"]


@pytest.mark.parametrize("data,headers,code", [
    (b"PDF", {"Content-Type": "application/pdf"}, "AGENT_SOURCE_UNAVAILABLE"),
    (b"\xff", {"Content-Type": "text/plain; charset=utf-8"}, "AGENT_SOURCE_UNAVAILABLE"),
    (b"text", {"Content-Type": "text/plain", "Content-Encoding": "gzip"}, "AGENT_SOURCE_UNAVAILABLE"),
    (b"text", {"Content-Type": "text/plain", "Content-Length": str(BODY_BYTES + 1)}, "AGENT_SOURCE_LIMIT"),
    (b"a" * (BODY_BYTES + 1), {"Content-Type": "text/plain"}, "AGENT_SOURCE_LIMIT"),
    (gzip.compress(b"a" * (BODY_BYTES + 1)), {"Content-Type": "text/plain", "Content-Encoding": "gzip"}, "AGENT_SOURCE_LIMIT"),
])
def test_media_decode_wire_and_expansion_failures_are_explicit(data, headers, code):
    transport = Transport([Response(data, headers=headers)])
    with pytest.raises(AgentFailure, match=code):
        fetch_page("https://public.example", resolver=public_dns, connector=transport)
    assert transport.closed == 1


def test_exact_wire_decoded_and_escaped_text_limits_are_readable_and_disclosed():
    for content in [b"a" * BODY_BYTES, gzip.compress(b"a" * BODY_BYTES), b"\x00" * 32768]:
        compressed = content.startswith(b"\x1f\x8b")
        transport = Transport([Response(content, headers={"Content-Type": "text/plain",
            "Content-Encoding": "gzip" if compressed else "identity"})])
        source = fetch_page("https://public.example", resolver=public_dns, connector=transport)
        assert len(source.text.encode()) <= 32768 and len(wire_bytes(source)) <= 65536
        assert source.truncated


def test_redirect_ceiling_loop_and_deadline_are_bounded():
    transport = Transport([Response(status=302, headers={"Location": "/"})])
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_DENIED"):
        fetch_page("https://public.example/", resolver=public_dns, connector=transport)
    transport = Transport([Response(status=302, headers={"Location": "/" + str(i)}) for i in range(4)])
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_DENIED"):
        fetch_page("https://public.example/start", resolver=public_dns, connector=transport)
    assert len(transport.connections) == 4
    ticks = iter([0, 21])
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_UNAVAILABLE"):
        fetch_page("https://public.example", clock=lambda: next(ticks))


@pytest.mark.asyncio
async def test_owned_worker_denies_private_url_and_removes_operation_files(tmp_path):
    fetcher = PublicFetcher(tmp_path / "operations")
    with pytest.raises(AgentFailure, match="AGENT_SOURCE_DENIED"):
        await fetcher.fetch("http://127.0.0.1/private", threading.Event())
    assert not list(fetcher.root.glob("op-*"))
