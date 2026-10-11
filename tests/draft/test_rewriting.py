"""Scoped rewrite input, one content call and closed production route."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import threading

import httpx
import pytest

from packages.resume_core.rewriting import (RewriteProposal, RewriteRequest, rewrite_input,
                                            validate_rewrite, withheld_rewrite_issues)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api.app import create_app
from resume_api.lifecycle import OperationFiles
from resume_api.providers.content import ContentResult, ReportedUsage
from resume_api.rewriting_content import RewritingContentService


ORIGIN = "http://127.0.0.1:39298"
SECRET = "synthetic-rewrite-secret-012345678901"


def request() -> RewriteRequest:
    return RewriteRequest.model_validate({"transportVersion": 1, "baseRevision": 7,
        "blockId": "prose_recent", "blockKind": "job_prose", "blockRevision": 2,
        "dependencyHash": "a" * 64, "currentText": "Built a service.",
        "instruction": "Make this clearer without adding claims.", "sourceLanguage": "mixed",
        "contentPolicyVersion": "generic-1", "facts": [
            {"id": "safe", "revision": 1, "kind": "text", "value": {"text": "Built a service."},
             "evidence": [], "origin": "user", "importance": "essential", "jobId": "recent", "subprojectId": None},
            {"id": "private", "revision": 1, "kind": "metric", "value": {"number": 20,
             "upperNumber": None, "comparator": "exact", "unit": "teams", "period": None,
             "baseline": None, "result": None, "scope": "call 555-123-4567", "attribution": "team",
             "qualifiers": []}, "evidence": [], "origin": "user", "importance": "essential",
             "jobId": "recent", "subprojectId": None}],
        "requiredFactIds": ["safe", "private"], "excerpts": [
            {"factId": "safe", "text": "Built a service."},
            {"factId": "private", "text": "Call 555-123-4567."}]})


def test_prompt_scope_privacy_bounds_and_factual_issue():
    chosen = request()
    prompt = json.loads(rewrite_input(chosen))
    assert prompt["task"] == "rewrite_prose" and prompt["blockId"] == "prose_recent"
    assert prompt["baseRevision"] == 7 and prompt["dependencyHash"] == "a" * 64
    assert prompt["requiredFactIds"] == ["safe"]
    assert json.loads(rewrite_input(chosen.model_copy(update={"instruction": ""})))["instruction"] == ""
    assert [fact["id"] for fact in prompt["facts"]] == ["safe"]
    assert "555-123-4567" not in json.dumps(prompt) and "private" not in json.dumps(prompt)
    assert all("evidence" not in fact for fact in prompt["facts"])
    result = validate_rewrite(chosen, RewriteProposal(blockId="prose_recent",
        replacementText="Built a clearer service.", factIds=["safe"]))
    assert result.replacement_text == "Built a clearer service."
    assert [(issue.code, issue.fact_id) for issue in result.issues] == [("SOURCE_REVIEW", "private")]
    with pytest.raises(ValueError, match="reference mismatch"):
        validate_rewrite(chosen, RewriteProposal(blockId="other", replacementText="Other.", factIds=["safe"]))
    with pytest.raises(ValueError, match="reference mismatch"):
        validate_rewrite(chosen, RewriteProposal(blockId="prose_recent", replacementText="Other.", factIds=["private"]))
    huge = chosen.model_copy(update={"instruction": "x" * 2000, "current_text": "y" * 4000,
                              "excerpts": [chosen.excerpts[0].model_copy(update={"text": "z" * 4000})] * 20})
    with pytest.raises(ValueError, match="INPUT_TOO_LARGE"):
        rewrite_input(huge)
    all_private = chosen.model_copy(update={"facts": [chosen.facts[1]], "required_fact_ids": ["private"]})
    assert [(issue.block_id, issue.fact_id, issue.code) for issue in withheld_rewrite_issues(all_private)] == [
        ("prose_recent", "private", "SOURCE_REVIEW")]
    with pytest.raises(ValueError, match="NO_SAFE_CONTENT"):
        rewrite_input(all_private)


def test_single_content_call_uses_provider_repair_authority(tmp_path):
    class Provider:
        calls = 0

        def generate(self, input, files, cancel):
            self.calls += 1
            assert input.result_type is RewriteProposal
            assert input.policy.max_input_bytes == 65_536
            return ContentResult(value=RewriteProposal(blockId="prose_recent",
                replacementText="Built a clearer service.", factIds=["safe"]),
                usage=ReportedUsage(input_tokens=12, output_tokens=6), cli_version="fixture",
                model="fixture", elapsed_seconds=0.01, logical_attempts=2, internal_inference_count=None)

    provider = Provider()
    service = RewritingContentService(provider, "fixture")
    with OperationFiles(tmp_path).open() as files:
        result, usage = service.run(request(), files, threading.Event())
    assert provider.calls == 1 and usage["logicalAttempts"] == 2
    assert result.block_revision == 2 and result.dependency_hash == "a" * 64


@pytest.mark.asyncio
async def test_route_is_closed_without_runner_and_rejects_malformed_result(tmp_path):
    def app_at(name, runner=None):
        root = tmp_path / name
        dist = root / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("fixture")
        return create_app(origin=ORIGIN, secret=SECRET, temp_root=root / "operations", dist=dist,
                          rewrite_runner=runner)

    closed = app_at("closed")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=closed), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        response = await client.post("/v1/facts/rewrite", headers={"Origin": ORIGIN},
                                     json=request().model_dump(mode="json", by_alias=True))
        assert response.status_code == 503 and response.json()["error"]["code"] == "CLI_PROFILE_UNSAFE"
        assert (await client.get("/v1/capabilities")).json()["rewriteReady"] is False

    class BadRunner:
        calls = 0

        def run(self, payload, files, cancel):
            self.calls += 1
            result = validate_rewrite(payload, RewriteProposal(blockId="prose_recent",
                replacementText="Built a clearer service.", factIds=["safe"]))
            return result.model_copy(update={"dependency_hash": "b" * 64}), {
                "logicalAttempts": 1, "inputTokens": 1, "outputTokens": 1, "inferenceCount": None}

    bad = BadRunner()
    app = app_at("bad", bad)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        response = await client.post("/v1/facts/rewrite", headers={"Origin": ORIGIN},
                                     json=request().model_dump(mode="json", by_alias=True))
        assert [json.loads(line)["type"] for line in response.text.splitlines()] == [
            "operation.started", "operation.failed"]
        assert bad.calls == 1
        private = request().model_copy(update={"facts": [request().facts[1]], "required_fact_ids": ["private"],
                                               "excerpts": [request().excerpts[1]]})
        withheld = await client.post("/v1/facts/rewrite", headers={"Origin": ORIGIN},
                                     json=private.model_dump(mode="json", by_alias=True))
        body = withheld.json()
        assert withheld.status_code == 422 and body["error"] == {
            "code": "NO_SAFE_CONTENT", "retryable": False, "stage": "rewrite"}
        assert body["baseRevision"] == 7 and body["blockRevision"] == 2
        assert body["dependencyHash"] == "a" * 64
        assert body["issues"] == [{"code": "SOURCE_REVIEW", "blockId": "prose_recent",
                                   "factId": "private", "message": "Required fact or evidence withheld because it may contain contact information. Review manually."}]
        assert "555-123-4567" not in withheld.text
        assert bad.calls == 1


def test_cancelled_request_does_not_start_provider(tmp_path):
    class Forbidden:
        def generate(self, input, files, cancel):
            raise AssertionError("provider called after cancellation")

    cancel = threading.Event()
    cancel.set()
    with OperationFiles(tmp_path).open() as files:
        with pytest.raises(InterruptedError):
            RewritingContentService(Forbidden(), "fixture").run(request(), files, cancel)
