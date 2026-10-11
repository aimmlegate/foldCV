"""Fixture-only two-operation service path and closed production gate."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.drafting import DraftProposal, DraftRequest
from packages.resume_core.normalization import FactRequest, FactSheet, literal_sheet
from resume_api.app import create_app
from resume_api.drafting_content import DraftingContentService
from resume_api.providers.content import ContentResult, ReportedUsage


ORIGIN = "http://127.0.0.1:39297"
SECRET = "synthetic-draft-secret-012345678901"
ROOT = Path(__file__).resolve().parents[2]


def app_for(tmp_path, semantic=None, draft=None, fixture_ready=False):
    dist = tmp_path / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("synthetic shell")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
                      semantic_runner=semantic, draft_runner=draft, fixture_generation_ready=fixture_ready)


def facts_request():
    return json.loads((ROOT / "contracts/examples/fact_request.json").read_text())


def events(response):
    return [json.loads(line) for line in response.text.splitlines()]


def test_fixture_capability_requires_both_internal_runners(tmp_path):
    with pytest.raises(ValueError, match="both injected runners"):
        app_for(tmp_path / "missing", semantic=object(), fixture_ready=True)
    app = app_for(tmp_path / "ready", semantic=object(), draft=object(), fixture_ready=True)
    route = next(item for item in app.app.routes if getattr(item, "path", None) == "/v1/capabilities")
    assert json.loads(asyncio.run(route.endpoint()).body)["generationReady"] is True


@pytest.mark.asyncio
async def test_production_draft_closed_and_two_fixture_operations(tmp_path):
    class Semantic:
        calls = 0

        def run(self, request, files, cancel):
            self.calls += 1
            sheet = literal_sheet(request)
            value = sheet.model_dump(mode="json", by_alias=True)
            value["facts"].append({"id": "fact_user_profile", "revision": 1, "kind": "text",
                                   "value": {"text": "Built reliable systems."}, "evidence": [], "origin": "user",
                                   "importance": "essential", "jobId": None, "subprojectId": None})
            return FactSheet.model_validate(value), {"logicalAttempts": 1, "inputTokens": 10,
                                                     "outputTokens": 8, "inferenceCount": None}

    class Provider:
        calls = 0

        def generate(self, request, files, cancel):
            self.calls += 1
            prompt = json.loads(request.text)
            assert list(prompt) == ["instructionVersion", "task", "sourceLanguage", "rules", "blocks"]
            assert prompt["task"] == "draft_prose"
            assert prompt["sourceLanguage"] == "mixed"
            assert "sourceFingerprint" not in request.text and "originalName" not in request.text
            return ContentResult(value=DraftProposal(blocks=[{"blockId": "profile",
                "text": "Built reliable systems.", "factIds": ["fact_user_profile"]}]),
                usage=ReportedUsage(input_tokens=12, output_tokens=5), cli_version="fixture",
                model="fixture", elapsed_seconds=0.01, logical_attempts=1,
                internal_inference_count=None)

    closed = app_for(tmp_path / "closed")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=closed), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        request = json.loads((ROOT / "contracts/examples/draft_request.json").read_text())
        assert (await client.post("/v1/facts/draft", headers={"Origin": ORIGIN}, json=request)).json()["error"]["code"] == "CLI_PROFILE_UNSAFE"
        assert (await client.get("/v1/capabilities")).json()["generationReady"] is False

    semantic = Semantic()
    provider = Provider()
    app = app_for(tmp_path / "open", semantic, DraftingContentService(provider, "fixture"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        normalized = events(await client.post("/v1/facts/normalize", headers={"Origin": ORIGIN}, json=facts_request()))
        assert [event["type"] for event in normalized] == ["operation.started", "operation.completed"]
        sheet = normalized[-1]["payload"]["result"]
        request = {"transportVersion": 1, "sheet": sheet, "sourceFingerprint": sheet["sourceFingerprint"],
                   "baseRevision": sheet["revision"], "sourceLanguage": "mixed",
                   "asOf": {"precision": "day", "year": 2026,
                                                                 "month": 10, "day": 11}}
        drafted = events(await client.post("/v1/facts/draft", headers={"Origin": ORIGIN}, json=request))
        assert [event["type"] for event in drafted] == ["operation.started", "operation.completed"]
        assert drafted[-1]["payload"]["result"]["blocks"][0]["text"] == "Built reliable systems."
        assert [normalized[-1]["payload"]["usage"]["logicalAttempts"],
                drafted[-1]["payload"]["usage"]["logicalAttempts"]] == [1, 1]
        assert normalized[-1]["payload"]["usage"]["inferenceCount"] is None
        assert drafted[-1]["payload"]["usage"]["inferenceCount"] is None
        stale = {**request, "baseRevision": request["baseRevision"] + 1}
        assert (await client.post("/v1/facts/draft", headers={"Origin": ORIGIN}, json=stale)).status_code == 422
        assert semantic.calls == 1 and provider.calls == 1


@pytest.mark.asyncio
async def test_failed_normalization_cannot_supply_a_draft(tmp_path):
    class Broken:
        def run(self, request, files, cancel):
            raise ValueError("fixture normalization failed")

    class ForbiddenDraft:
        calls = 0

        def run(self, request, files, cancel):
            self.calls += 1
            raise AssertionError("draft should not start")

    draft = ForbiddenDraft()
    app = app_for(tmp_path, Broken(), draft)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        failed = events(await client.post("/v1/facts/normalize", headers={"Origin": ORIGIN}, json=facts_request()))
        assert failed[-1]["type"] == "operation.failed"
        assert draft.calls == 0


@pytest.mark.asyncio
async def test_draft_stream_cancel_releases_slot(tmp_path):
    class Slow:
        def run(self, request, files, cancel):
            cancel.wait(1)
            raise InterruptedError("cancelled")

    app = app_for(tmp_path, draft=Slow())
    route = next(item for item in app.app.routes if getattr(item, "path", None) == "/v1/facts/draft")
    request = DraftRequest.model_validate(json.loads((ROOT / "contracts/examples/draft_request.json").read_text()))
    for _ in range(2):
        response = await route.endpoint(request)
        first = json.loads((await anext(response.body_iterator)).decode())
        assert first["type"] == "operation.started"
        await response.body_iterator.aclose()
        await asyncio.sleep(0)
    assert list((tmp_path / "operations").iterdir()) == []
