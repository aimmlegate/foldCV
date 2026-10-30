"""The extraction worker (`resume_api.extracting.run_extract`) called directly and through the template upload
POST /v1/rich/projects/template-input: source bytes and hash, memory guard, crash sanitizing, cancel and cleanup latch."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
import threading

import pytest

from resume_api import extracting
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.projects import intake as intake_module
from tests.service.app_fixtures import HealthyConnection, make_app, operations, signed_in, status
from tests.support.foundation import ForbiddenContentProvider

FIXTURES = Path(__file__).resolve().parents[2] / "tests/fixtures/synthetic/import"


def uploads(tmp_path):
    return make_app(tmp_path, connection_adapter=HealthyConnection(), content_provider=ForbiddenContentProvider(),
                    template_import_call_cap=4)


async def upload(client, name, data, field="file"):
    reply = await client.post("/v1/rich/projects/template-input", files={field: (name, data)})
    assert reply.status_code == 201, reply.text[:300]
    return reply.json()["workspace"]["preDraft"]


async def extract(tmp_path, data, name, pasted=False):
    files = OperationFiles(tmp_path / "operations")
    with files.open():
        return await extracting.run_extract(data, name, pasted, files)


@pytest.mark.parametrize(("name", "kind"), [("unicode.txt", "txt"), ("notes.md", "markdown"), ("rich.docx", "docx"),
                                            ("mixed-columns.pdf", "pdf")])
@pytest.mark.asyncio
async def test_the_real_worker_keeps_the_source_identity_and_cleans(tmp_path, name, kind):
    data = (FIXTURES / name).read_bytes()
    result = await extract(tmp_path, data, name)
    assert result.source_kind == kind
    assert result.byte_sha256 == hashlib.sha256(data).hexdigest() and result.byte_length == len(data)
    assert result.byte_ref == "memory:sha256:" + result.byte_sha256
    assert operations(tmp_path) == []


@pytest.mark.asyncio
async def test_an_upload_stores_the_exact_bytes_and_never_calls_the_model(tmp_path):
    app = uploads(tmp_path)
    data = (FIXTURES / "rich.docx").read_bytes()
    paste = b"First\r\n\xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82"
    async with signed_in(app) as client:
        for field, name, raw in (("file", "rich.docx", data), ("paste", "pasted.txt", paste)):
            reply = await client.post("/v1/rich/projects/template-input", files={field: (name, raw)})
            assert reply.status_code == 201, reply.text[:300]
            workspace = reply.json()["workspace"]
            pre = workspace["preDraft"]
            source = pre["sources"][0]
            assert source["byteSha256"] == hashlib.sha256(raw).hexdigest() and source["units"]
            assert "NO_USABLE_TEXT" not in pre["warnings"]
            original = await client.get(f"/v2/projects/{workspace['projectId']}/sources/{source['id']}/original")
            assert original.status_code == 200 and original.content == raw
        assert pre["selectedInput"] == "text"
        assert [unit["text"] for unit in source["units"]] == ["First\n", "Привет"]
    assert operations(tmp_path) == []


@pytest.mark.asyncio
async def test_the_upload_fails_closed_on_auth_origin_body_and_format(tmp_path):
    import httpx
    from tests.service.app_fixtures import ORIGIN
    app = uploads(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN,
                                 headers={"Origin": ORIGIN}) as anonymous:
        denied = await anonymous.post("/v1/rich/projects/template-input", files={"file": ("x.txt", b"x")})
        assert denied.status_code == 401
    async with signed_in(app) as client:
        foreign = await client.post("/v1/rich/projects/template-input", headers={"Origin": "http://evil.invalid"},
                                    files={"file": ("x.txt", b"x")})
        assert foreign.status_code == 403
        unsupported = await upload(client, "legacy.doc", b"legacy")
        assert unsupported["warnings"] == ["EXTRACT_UNSUPPORTED", "NO_USABLE_TEXT"]
        two_parts = await client.post("/v1/rich/projects/template-input",
            headers={"Content-Type": "multipart/form-data; boundary=x"},
            content=b"--x\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.txt\"\r\n\r\nx\r\n--x\r\n"
                    b"Content-Disposition: form-data; name=\"file\"; filename=\"y.txt\"\r\n\r\ny\r\n--x--\r\n")
        assert two_parts.status_code == 422 and two_parts.json()["error"]["code"] == "INVALID_REQUEST"
        oversized = await client.post("/v1/rich/projects/template-input",
                                      files={"file": ("big.txt", b"a" * (extracting.MAX_BODY + 1))})
        assert oversized.status_code == 413 and oversized.json()["error"]["code"] == "INPUT_TOO_LARGE"
    assert operations(tmp_path) == []


@pytest.mark.asyncio
async def test_a_low_memory_threshold_kills_the_real_worker_and_reaps(tmp_path, monkeypatch):
    monkeypatch.setattr(extracting, "MAX_RSS_KB", 1)
    app = uploads(tmp_path)
    async with signed_in(app) as client:
        stored = await upload(client, "unicode.txt", (FIXTURES / "unicode.txt").read_bytes())
        assert stored["warnings"] == ["EXTRACT_MEMORY_LIMIT", "NO_USABLE_TEXT"]
    assert operations(tmp_path) == []


@pytest.mark.asyncio
async def test_a_crashed_worker_is_sanitized_and_keeps_unrelated_files(tmp_path, monkeypatch, capsys):
    worker = tmp_path / "synthetic-crash.py"
    worker.write_text('import sys\nsys.stderr.write("private-crash-marker")\nsys.exit(7)\n', encoding="utf-8")
    monkeypatch.setattr(extracting, "WORKER", worker)
    app = uploads(tmp_path)
    async with signed_in(app) as client:
        reply = await client.post("/v1/rich/projects/template-input", files={"file": ("source.txt", b"private-source-marker")})
        assert reply.status_code == 201
        assert reply.json()["workspace"]["preDraft"]["warnings"] == ["EXTRACT_FAILED", "NO_USABLE_TEXT"]
        assert "private-crash-marker" not in reply.text
    assert operations(tmp_path) == []
    assert worker.is_file()
    assert "private-crash-marker" not in "".join(capsys.readouterr())


@pytest.mark.asyncio
async def test_cancel_stops_the_real_worker_and_keeps_no_source(tmp_path, monkeypatch):
    original_rss = extracting._rss_kb
    loop = asyncio.get_running_loop()
    entered, release = asyncio.Event(), threading.Event()

    def held_rss(pid: int) -> int | None:
        # Holds the monitor thread so the cancel lands while the real worker runs.
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        return original_rss(pid)

    monkeypatch.setattr(extracting, "_rss_kb", held_rss)
    task = asyncio.create_task(extract(tmp_path, (FIXTURES / "rich.docx").read_bytes(), "rich.docx"))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert operations(tmp_path) == []
    finally:
        release.set()


@pytest.mark.asyncio
async def test_a_cleanup_failure_blocks_later_uploads(tmp_path, monkeypatch):
    calls = []

    async def broken(_data, _name, _pasted, _files):
        calls.append(_name)
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(intake_module, "run_extract", broken)
    app = uploads(tmp_path)
    async with signed_in(app) as client:
        first = await upload(client, "x.txt", b"safe")
        assert first["warnings"] == ["PROCESS_CLEANUP_FAILED", "NO_USABLE_TEXT"]
        assert await status(client) == "cleanup_blocked"
        second = await upload(client, "y.txt", b"safe")
        assert second["warnings"] == ["PROCESS_CLEANUP_FAILED", "NO_USABLE_TEXT"]
    assert calls == ["x.txt"]


@pytest.mark.asyncio
async def test_a_worker_past_the_deadline_is_stopped_with_its_own_code_and_frees_the_upload(tmp_path, monkeypatch):
    worker = tmp_path / "synthetic-stuck.py"
    worker.write_text("import time\nwhile True:\n    time.sleep(0.05)\n", encoding="utf-8")
    monkeypatch.setattr(extracting, "WORKER", worker)
    monkeypatch.setattr(extracting, "MAX_SECONDS", 0.2)
    app = uploads(tmp_path)
    async with signed_in(app) as client:
        reply = await client.post("/v1/rich/projects/template-input", files={"file": ("source.txt", b"text")})
        assert reply.status_code == 201
        assert reply.json()["workspace"]["preDraft"]["warnings"] == ["EXTRACT_TIMEOUT", "NO_USABLE_TEXT"]
    assert operations(tmp_path) == []
