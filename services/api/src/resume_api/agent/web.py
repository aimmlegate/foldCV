"""Bounded public GETs with pinned DNS, isolated parsing and owned worker cleanup."""

from __future__ import annotations

import asyncio
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
import zlib
import certifi

from packages.resume_core.host import WINDOWS, Confined
from packages.resume_core.assistant_store import AgentFailure, identity, timestamp
from packages.resume_core.models.agent import AgentWebSource
from resume_api.cli.process_runner import ProcessRunner
from resume_api.lifecycle import OperationFiles, SpikeError, python_worker, safe_environment

BODY_BYTES = 2 * 1024 * 1024
TEXT_BYTES = 32 * 1024


def destination(url, resolver=socket.getaddrinfo):
    try:
        parsed = urlsplit(url)
        if (len(url) > 4096 or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 80, 443}
                or any(ord(char) < 33 or ord(char) == 127 for char in url) or "\\" in url or "%" in parsed.hostname):
            raise ValueError("invalid URL")
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        answers = resolver(host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError("nonpublic destination")
        # Reject transition forms that can embed a private IPv4 route.
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo):
                raise ValueError("ambiguous destination")
        return parsed, host, port, addresses[0]
    except (ValueError, UnicodeError, OSError):
        raise AgentFailure("AGENT_SOURCE_DENIED") from None


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, secure, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address, self.secure = address, secure

    def connect(self):
        ip = ipaddress.ip_address(self.address)
        stream = socket.socket(socket.AF_INET6 if ip.version == 6 else socket.AF_INET, socket.SOCK_STREAM)
        stream.settimeout(self.timeout)
        try:
            # Numeric connect never performs a second hostname lookup.
            stream.connect((self.address, self.port))
            self.sock = ssl.create_default_context(cafile=certifi.where()).wrap_socket(stream, server_hostname=self.host) if self.secure else stream
        except BaseException:
            stream.close()
            raise


class ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden, self.in_title, self.parts, self.title, self.size, self.truncated = 0, False, [], [], 0, False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.hidden or not data.strip():
            return
        value = " ".join(data.split())
        if self.in_title:
            self.title.append(value[:512])
        raw = (value + "\n").encode()
        room = max(0, TEXT_BYTES - self.size)
        self.parts.append(raw[:room].decode("utf-8", "ignore"))
        self.size += min(room, len(raw))
        self.truncated |= len(raw) > room


def extract(body, media, charset):
    try:
        text = body.decode(charset or "utf-8", "strict")
        if media == "text/plain":
            raw = text.encode()
            return "Public text", raw[:TEXT_BYTES].decode("utf-8", "ignore"), len(raw) > TEXT_BYTES
        parser = ReadableHTML()
        parser.feed(text)
        parser.close()
        content = "".join(parser.parts).strip()
        if not content:
            raise ValueError("no readable text")
        return " ".join(parser.title)[:512] or "Public page", content, parser.truncated
    except (ValueError, LookupError, RecursionError):
        raise AgentFailure("AGENT_SOURCE_UNAVAILABLE") from None


def fetch_page(url, *, resolver=socket.getaddrinfo, connector=PinnedConnection, clock=time.monotonic):
    deadline, current, seen = clock() + 20, url, set()
    try:
        for redirects in range(4):
            if clock() >= deadline:
                raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")
            parsed, host, port, address = destination(current, resolver)
            normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
            if normalized in seen:
                raise AgentFailure("AGENT_SOURCE_DENIED")
            seen.add(normalized)
            connection = connector(host, port, address, parsed.scheme == "https", max(0.01, deadline - clock()))
            try:
                target = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
                connection.request("GET", target, headers={"Accept": "text/html, text/plain", "Accept-Encoding": "gzip, deflate",
                    "User-Agent": "FoldCV/1.0", "Connection": "close"})
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if redirects == 3 or not location:
                        raise AgentFailure("AGENT_SOURCE_DENIED")
                    current = urljoin(normalized, location)
                    continue
                if response.status != 200:
                    raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")
                content_type = response.getheader("Content-Type", "").split(";")[0].strip().lower()
                if content_type not in {"text/html", "text/plain"}:
                    raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")
                encoding = response.getheader("Content-Encoding", "identity").lower().strip()
                if encoding not in {"identity", "gzip", "deflate"}:
                    raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")
                declared = response.getheader("Content-Length")
                if declared is not None and (not declared.isdigit() or int(declared) > BODY_BYTES):
                    raise AgentFailure("AGENT_SOURCE_LIMIT")
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS) if encoding != "identity" else None
                wire, body = 0, bytearray()
                while True:
                    if clock() >= deadline:
                        raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")
                    chunk = response.read(16384)
                    if not chunk:
                        break
                    wire += len(chunk)
                    if wire > BODY_BYTES:
                        raise AgentFailure("AGENT_SOURCE_LIMIT")
                    decoded = decompressor.decompress(chunk, BODY_BYTES + 1 - len(body)) if decompressor else chunk
                    body.extend(decoded)
                    if len(body) > BODY_BYTES or decompressor and decompressor.unconsumed_tail:
                        raise AgentFailure("AGENT_SOURCE_LIMIT")
                if decompressor and (not decompressor.eof or decompressor.unused_data):
                    raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")
                if declared is not None and wire != int(declared):
                    raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")
                charset = response.headers.get_content_charset() if hasattr(response, "headers") else "utf-8"
                title, text, truncated = extract(bytes(body), content_type, charset)
                source = dict(id=identity("source"), runId="unbound", requestedUrl=url, finalUrl=normalized,
                    title=title, retrievedAt=timestamp(), contentSha256=hashlib.sha256(body).hexdigest(),
                    text=text, truncated=truncated, originalBytes=len(body))
                # Escaping can make even a bounded text exceed the serialized source limit.
                while len(json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode()) > 65536:
                    source["text"] = source["text"][:len(source["text"]) // 2]
                    source["truncated"] = True
                return AgentWebSource.model_validate(source)
            finally:
                connection.close()
    except AgentFailure:
        raise
    except (OSError, ValueError, zlib.error, http.client.HTTPException):
        raise AgentFailure("AGENT_SOURCE_UNAVAILABLE") from None
    raise AgentFailure("AGENT_SOURCE_UNAVAILABLE")


class PublicFetcher:
    def __init__(self, root):
        self.root = root

    async def fetch(self, request, cancel):
        # The assistant passes its AgentFetchRequest; a plain URL string still works.
        url = getattr(request, "url", request)

        def work():
            module = Path(__file__).resolve()
            def launch(executable, args, operation):
                environment = safe_environment(operation)
                environment["PYTHONPATH"] = str(module.parents[5]) + os.pathsep + str(module.parents[2])
                # Windows: the job takes RLIMIT_CPU's place.
                return Confined(executable, cpu_seconds=3) if WINDOWS else executable, args, environment
            try:
                with OperationFiles(self.root).open() as files:
                    executable, arguments = python_worker("public-fetch", "-m", "resume_api.agent.web")
                    raw, _ = ProcessRunner(executable, launch=launch).run(files,
                        arguments, data=json.dumps({"url": url}).encode(),
                        deadline=time.monotonic() + 20, cancel=cancel, max_output=132096, max_stdout=131072, max_stderr=1024)
                result = json.loads(raw)
                if "error" in result:
                    raise AgentFailure(result["error"])
                return AgentWebSource.model_validate(result["source"])
            except SpikeError as error:
                raise AgentFailure("AGENT_CLEANUP_FAILED" if error.code == "CLEANUP_FAILED" else
                    "AGENT_CANCELLED" if cancel.is_set() else "AGENT_SOURCE_UNAVAILABLE") from None
        task = asyncio.create_task(asyncio.to_thread(work))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancel.set()
            await asyncio.shield(task)
            raise


def worker_main() -> int:
    if not WINDOWS:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    try:
        request = json.loads(sys.stdin.buffer.read(8193))
        value = {"source": fetch_page(request["url"]).model_dump(mode="json", by_alias=True)}
    except AgentFailure as error:
        value = {"error": error.code}
    except Exception:
        value = {"error": "AGENT_SOURCE_UNAVAILABLE"}
    sys.stdout.write(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(worker_main())
