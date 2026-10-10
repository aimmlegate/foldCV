"""Protected import, real worker, memory guard and cleanup checks."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
import sys
import time

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api import app as service
from resume_api import extracting
from resume_api.app import create_app
from resume_api.lifecycle import OperationFiles, SpikeError
from tests.support.foundation import ForbiddenContentProvider

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/synthetic/import"
ORIGIN = "http://127.0.0.1:39280"
SECRET = "synthetic-extract-secret-01234567890123"


class ForbiddenRunner:
    calls = 0

    async def run(self, kind, request, files):
        self.calls += 1
        return ForbiddenContentProvider().generate(kind, request)


def make_app(tmp_path: Path, runner: ForbiddenRunner | None = None):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("synthetic shell")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist, runner=runner)


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)


@pytest.mark.asyncio
async def test_real_protected_extract_preserves_source_hash_and_cleans(tmp_path: Path) -> None:
    runner = ForbiddenRunner()
    app = make_app(tmp_path, runner)
    async with client_for(app) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        for name, expected_kind in (("unicode.txt", "txt"), ("notes.md", "markdown"),
                                    ("rich.docx", "docx"), ("mixed-columns.pdf", "pdf")):
            data = (FIXTURES / name).read_bytes()
            response = await client.post("/v1/extract", headers={"Origin": ORIGIN}, files={"file": (name, data)})
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["sourceKind"] == expected_kind
            assert result["byteSha256"] == hashlib.sha256(data).hexdigest()
            assert result["byteLength"] == len(data)
            assert result["byteRef"] == "memory:sha256:" + result["byteSha256"]
            assert response.headers["cache-control"] == "no-store"
        paste = b"First\r\n\xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82"
        response = await client.post("/v1/extract", headers={"Origin": ORIGIN}, files={"paste": ("pasted.txt", paste)})
        assert response.status_code == 200
        assert [unit["text"] for unit in response.json()["units"]] == ["First\r\n", "Привет"]
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False
    assert runner.calls == 0
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_extract_auth_origin_body_and_format_fail_closed(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        denied = await client.post("/v1/extract", headers={"Origin": ORIGIN}, files={"file": ("x.txt", b"x")})
        assert denied.status_code == 401
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        denied = await client.post("/v1/extract", headers={"Origin": "http://evil.invalid"}, files={"file": ("x.txt", b"x")})
        assert denied.status_code == 403
        unsupported = await client.post("/v1/extract", headers={"Origin": ORIGIN}, files={"file": ("legacy.doc", b"legacy")})
        assert unsupported.status_code == 422 and unsupported.json()["error"]["code"] == "EXTRACT_UNSUPPORTED"
        malformed = await client.post("/v1/extract", headers={"Origin": ORIGIN, "Content-Type": "multipart/form-data; boundary=x"},
                                      content=b"--x\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.txt\"\r\n\r\nx\r\n--x\r\nContent-Disposition: form-data; name=\"file\"; filename=\"y.txt\"\r\n\r\ny\r\n--x--\r\n")
        assert malformed.status_code == 422
        oversized = await client.post("/v1/extract", headers={"Origin": ORIGIN}, files={"file": ("big.txt", b"a" * (6 * 1024 * 1024 + 1))})
        assert oversized.status_code == 413
        json_limit = await client.post("/v1/prepare-render", headers={"Origin": ORIGIN}, json={"x": "a" * 1_048_576})
        assert json_limit.status_code == 413
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_real_child_low_rss_threshold_kills_and_reaps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extracting, "MAX_RSS_KB", 1)
    app = make_app(tmp_path)
    async with client_for(app) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        response = await client.post("/v1/extract", headers={"Origin": ORIGIN},
                                     files={"file": ("unicode.txt", (FIXTURES / "unicode.txt").read_bytes())})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "EXTRACT_MEMORY_LIMIT"
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_cancel_real_worker_keeps_no_process_or_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_rss = extracting._rss_kb
    entered = asyncio.Event()

    def slow_rss(pid: int) -> int | None:
        entered_loop.call_soon_threadsafe(entered.set)
        time.sleep(0.2)
        return original_rss(pid)

    entered_loop = asyncio.get_running_loop()
    monkeypatch.setattr(extracting, "_rss_kb", slow_rss)
    files = OperationFiles(tmp_path / "operations")

    async def operation():
        with files.open():
            return await extracting.run_extract((FIXTURES / "rich.docx").read_bytes(), "rich.docx", False, files)

    task = asyncio.create_task(operation())
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_cleanup_failure_blocks_later_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(_data, _name, _pasted, _files):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(service, "run_extract", broken)
    app = make_app(tmp_path)
    async with client_for(app) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        first = await client.post("/v1/extract", headers={"Origin": ORIGIN}, files={"file": ("x.txt", b"safe")})
        assert first.status_code == 503 and first.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"
        second = await client.post("/v1/extract", headers={"Origin": ORIGIN}, files={"file": ("x.txt", b"safe")})
        assert second.status_code == 429 and second.json()["error"]["code"] == "BUSY"
