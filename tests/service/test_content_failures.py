"""Scoped text routes preserve sanitized provider failures and retry advice."""

import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from resume_api.app import create_app
from resume_api.lifecycle import SpikeError
from resume_api.lifecycle import OperationFiles
from resume_api.providers.content import ContentFailure
from tests.draft.test_rewriting import request as rewrite_request


ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "http://127.0.0.1:39317"
SECRET = "synthetic-content-secret-0123456789"


@pytest.mark.parametrize(("stage", "example"), [
    ("normalize", "fact_request"), ("draft", "draft_request"), ("rewrite", "rewrite_request"),
])
@pytest.mark.parametrize(("error", "code", "retryable"), [
    (ContentFailure("AUTH_REQUIRED"), "AUTH_REQUIRED", False),
    (ContentFailure("RATE_LIMITED"), "RATE_LIMITED", True),
    (ContentFailure("BUSY"), "BUSY", True),
    (ContentFailure("MODEL_DENIED"), "MODEL_DENIED", False),
    (ContentFailure("CANCELLED"), "CANCELLED", False),
    (InterruptedError("cancelled"), "CANCELLED", False),
    (SpikeError("CANCELLED"), "CANCELLED", False),
    (SpikeError("PROCESS_CLEANUP_FAILED"), "PROCESS_CLEANUP_FAILED", False),
    (asyncio.TimeoutError(), "OPERATION_TIMEOUT", True),
    (ValueError("private provider detail"), "INVALID_RESULT", False),
])
@pytest.mark.asyncio
async def test_text_failure_preserves_code_retryability_and_cleanup(tmp_path, stage, example, error, code, retryable):
    class Runner:
        def run(self, request, files, cancel):
            raise error

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("synthetic shell")
    options = {"semantic_runner" if stage == "normalize" else f"{stage}_runner": Runner()}
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist, **options)
    data = (rewrite_request().model_dump(mode="json", by_alias=True) if stage == "rewrite" else
            json.loads((ROOT / f"contracts/examples/{example}.json").read_text()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        response = await client.post(f"/v1/facts/{stage}", headers={"Origin": ORIGIN}, json=data)
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["operation.started", "operation.failed"]
    assert events[-1]["payload"] == {"code": code, "retryable": retryable, "stage": stage}
    assert "private provider detail" not in response.text
    remaining = list((tmp_path / "operations").iterdir())
    if code == "PROCESS_CLEANUP_FAILED":
        assert len(remaining) == 1
        assert (remaining[0] / ".cleanup-blocked").exists()
    else:
        assert remaining == []


@pytest.mark.parametrize("stage", ["normalize", "draft", "rewrite"])
@pytest.mark.asyncio
async def test_cleanup_failure_overrides_worker_cancellation_and_blocks_retry(tmp_path, monkeypatch, stage):
    class Runner:
        def run(self, request, files, cancel):
            raise InterruptedError("cancelled")

    def fail_cleanup(self, **kwargs):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    monkeypatch.setattr(OperationFiles, "stop_worker", fail_cleanup)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("synthetic shell")
    options = {"semantic_runner" if stage == "normalize" else f"{stage}_runner": Runner()}
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist, **options)
    data = (rewrite_request().model_dump(mode="json", by_alias=True) if stage == "rewrite" else
            json.loads((ROOT / f"contracts/examples/{'fact' if stage == 'normalize' else stage}_request.json").read_text()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        failed = await client.post(f"/v1/facts/{stage}", headers={"Origin": ORIGIN}, json=data)
        retry = await client.post(f"/v1/facts/{stage}", headers={"Origin": ORIGIN}, json=data)
    payload = json.loads(failed.text.splitlines()[-1])["payload"]
    assert payload == {"code": "PROCESS_CLEANUP_FAILED", "retryable": False, "stage": stage}
    assert json.loads(retry.text.splitlines()[-1])["payload"]["code"] == "BUSY"
