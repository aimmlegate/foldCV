"""POST /v2/projects/{id}/rewrite/preview (`resume_api.template_rewrite.TemplateRewrite`): provider failures reach the
reply as their public code without provider text, and the worker directory is removed or retained for cleanup."""

from __future__ import annotations

import pytest

from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.providers.content import ContentFailure
from tests.service.app_fixtures import HealthyConnection, add_project, make_app, open_project, operations, signed_in, status

PROJECT = "template-project"


class FailingProvider:
    def __init__(self, error):
        self.error, self.calls = error, 0

    def generate(self, _request, _files, _cancel):
        self.calls += 1
        raise self.error


async def preview(client, editor):
    token, snapshot = editor
    return await client.post(f"/v2/projects/{PROJECT}/rewrite/preview", json={
        "editorToken": token, "requestId": "rewrite-1", "snapshot": snapshot, "instruction": "Make clearer.",
        "range": {"blockId": "block-paper-a", "beforeRevision": 1, "cellId": None, "field": "content", "start": 0, "end": 6}})


@pytest.mark.parametrize(("error", "status_code", "code"), [
    (ContentFailure("AUTH_REQUIRED"), 502, "AUTH_REQUIRED"),
    (ContentFailure("RATE_LIMITED"), 502, "RATE_LIMITED"),
    (ContentFailure("MODEL_DENIED"), 502, "MODEL_DENIED"),
    (ContentFailure("DEADLINE_EXCEEDED"), 502, "DEADLINE_EXCEEDED"),
    (ContentFailure("CANCELLED"), 409, "CANCELLED"),
    (ValueError("private provider detail"), 500, "INTERNAL_ERROR"),
])
@pytest.mark.asyncio
async def test_a_provider_failure_keeps_its_public_code_and_removes_the_directory(tmp_path, error, status_code, code):
    provider = FailingProvider(error)
    app = make_app(tmp_path, content_provider=provider, connection_adapter=HealthyConnection())
    add_project(app)
    async with signed_in(app) as client:
        failed = await preview(client, await open_project(client))
        assert failed.status_code == status_code and failed.json()["error"]["code"] == code
        assert "private provider detail" not in failed.text
        tasks = (await client.get(f"/v2/projects/{PROJECT}/tasks")).json()["tasks"]
        assert [(task["kind"], task["error"]) for task in tasks] == [("rewrite", code if code != "INTERNAL_ERROR" else
                                                                       "PROCESS_FAILED")]
    assert provider.calls == 1
    assert operations(tmp_path) == []


@pytest.mark.asyncio
async def test_a_cleanup_failure_overrides_the_provider_failure_and_blocks_a_retry(tmp_path, monkeypatch):
    provider = FailingProvider(ContentFailure("CANCELLED"))

    def failed_cleanup(self, **_options):
        raise SpikeError("PROCESS_CLEANUP_FAILED")

    app = make_app(tmp_path, content_provider=provider, connection_adapter=HealthyConnection())
    add_project(app)
    async with signed_in(app) as client:
        editor = await open_project(client)
        monkeypatch.setattr(OperationFiles, "stop_worker", failed_cleanup)
        failed = await preview(client, editor)
        monkeypatch.undo()
        owned = operations(tmp_path)
        assert len(owned) == 1 and (owned[0] / ".cleanup-blocked").is_file()
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "PROCESS_CLEANUP_FAILED"
        assert await status(client) == "cleanup_blocked"
        # The latched service withdraws the provider, so the retry is refused before any model call.
        retry = await preview(client, editor)
        assert retry.status_code == 409 and retry.json()["error"]["code"] == "CONNECTION_REQUIRED" and provider.calls == 1
