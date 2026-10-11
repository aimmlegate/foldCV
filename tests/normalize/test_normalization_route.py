"""Protected deterministic and test-injected semantic routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.extraction.parser import extract
from packages.resume_core.normalization import FactRequest, SourceInput, literal_sheet
from resume_api.app import create_app
from resume_api.lifecycle import SpikeError


ORIGIN = "http://127.0.0.1:39296"
SECRET = "synthetic-facts-secret-012345678901"


def payload(text: str = "Skills: Python\n") -> dict:
    result = extract(text.encode(), "pasted.txt", pasted=True)
    return FactRequest(sources=[SourceInput(result=result, overlays={})]).model_dump(mode="json", by_alias=True)


def app_for(tmp_path: Path, runner=None):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("synthetic shell")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
                      semantic_runner=runner)


@pytest.mark.asyncio
async def test_real_imported_source_fact_route_is_protected_and_generation_closed(tmp_path):
    app = app_for(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        data = payload()
        assert (await client.post("/v1/facts", headers={"Origin": ORIGIN}, json=data)).status_code == 401
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.post("/v1/facts", headers={"Origin": "http://elsewhere.test"}, json=data)).status_code == 403
        result = await client.post("/v1/facts", headers={"Origin": ORIGIN}, json=data)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        assert result.json()["facts"][0]["value"]["display"] == "Python"
        assert result.json()["units"][0]["disposition"] == "facts"
        assert (await client.post("/v1/facts/normalize", headers={"Origin": ORIGIN}, json=data)).json()["error"]["code"] == "CLI_PROFILE_UNSAFE"
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False


@pytest.mark.asyncio
async def test_test_injected_semantic_emits_validated_events_once_and_rejects_oversize(tmp_path):
    class Runner:
        calls = 0

        def run(self, request, files, cancel):
            self.calls += 1
            return literal_sheet(request), {"logicalAttempts": 1, "inputTokens": 30,
                                            "outputTokens": 10, "inferenceCount": None}

    runner = Runner()
    app = app_for(tmp_path, runner)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        result = await client.post("/v1/facts/normalize", headers={"Origin": ORIGIN}, json=payload())
        events = [json.loads(line) for line in result.text.splitlines()]
        assert [event["type"] for event in events] == ["operation.started", "operation.completed"]
        assert events[1]["payload"]["result"]["facts"][0]["value"]["display"] == "Python"
        assert runner.calls == 1
        too_large = await client.post("/v1/facts/normalize", headers={"Origin": ORIGIN}, json=payload("A" * 70_000))
        assert too_large.status_code == 413 and runner.calls == 1
        assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_closing_stream_after_started_releases_semantic_slot(tmp_path):
    class Runner:
        def run(self, request, files, cancel):
            cancel.wait(1)
            return literal_sheet(request), {"logicalAttempts": 1, "inputTokens": 0,
                                            "outputTokens": 0, "inferenceCount": None}

    app = app_for(tmp_path, Runner())
    route = next(item for item in app.app.routes if getattr(item, "path", None) == "/v1/facts/normalize")
    request = FactRequest.model_validate(payload())
    for _ in range(3):
        response = await route.endpoint(request)
        first = json.loads((await anext(response.body_iterator)).decode())
        assert first["type"] == "operation.started"
        await response.body_iterator.aclose()
        await asyncio.sleep(0)
    assert list((tmp_path / "operations").iterdir()) == []


@pytest.mark.asyncio
async def test_cancelled_semantic_cleanup_failure_blocks_later_operations(tmp_path):
    class Runner:
        calls = 0

        def run(self, request, files, cancel):
            self.calls += 1
            assert cancel.wait(2)
            raise SpikeError("PROCESS_CLEANUP_FAILED")

    runner = Runner()
    app = app_for(tmp_path, runner)
    route = next(item for item in app.app.routes if getattr(item, "path", None) == "/v1/facts/normalize")
    request = FactRequest.model_validate(payload())
    response = await route.endpoint(request)
    assert json.loads((await anext(response.body_iterator)).decode())["type"] == "operation.started"
    await response.body_iterator.aclose()
    retry = await route.endpoint(request)
    failure = json.loads((await anext(retry.body_iterator)).decode())
    assert failure["type"] == "operation.failed"
    assert failure["payload"]["code"] == "BUSY"
    await retry.body_iterator.aclose()
    assert runner.calls == 1
