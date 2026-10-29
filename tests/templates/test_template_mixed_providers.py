"""MP08 (D119): an import whose model and fallback belong to different providers captures each model's adapter and runs
on the provider that lists its model. No fixture `content_provider`, which would answer for every provider."""

from contextlib import asynccontextmanager
import sys

import httpx
import pytest

from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.templates.store import TemplateStore
from resume_api.app import ProviderSlot, create_app
from resume_api.cli.profiles.claude import ClaudeCliProfile
from resume_api.connection import Metadata, Quota
from tests.templates.employment_fixtures import employment_package
from tests.templates.test_template_fallback_model import ModelRecorder, run_import
from tests.templates.test_template_import_app import ORIGIN, SECRET, CatalogAdapter, upload


class ClaudeCatalog:
    def inspect(self, _files, _cancel, *, full=True):
        return Metadata("2.1.308 (Claude Code)", ("claude-sonnet-5-5",), "max", Quota("not_provided"),
                        {"claude-sonnet-5-5": ModelReasoning(supported=["medium"], default="medium")}, "supported")


class ClaudeRecorder(ModelRecorder):
    template_adapter = "claude_cli"

    def invalidate_preflight(self):
        pass


@asynccontextmanager
async def mixed(tmp_path, claude):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("Synthetic template import boundary")
    # The CLI file only has to exist: the scripted catalog and provider never start it.
    cli = tmp_path / "claude stand-in"
    cli.write_text("#!" + sys.executable + "\n")
    cli.chmod(0o700)
    slot = ProviderSlot(ClaudeCatalog(), claude, ClaudeCliProfile(tmp_path / "claude profile", cli))
    wrapped = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
                         data_root=tmp_path / "data", connection_adapter=CatalogAdapter(), template_import_call_cap=4,
                         template_import_concurrency=1, provider_slots={"claude_cli": slot})
    TemplateStore(wrapped.app.state.projects.repository.root).activate(employment_package())
    app = wrapped.app
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url=ORIGIN,
                                     headers={"Origin": ORIGIN}) as client:
            assert (await client.post("/v1/session/exchange", json={"secret": SECRET})).status_code == 200
            yield client, app


@pytest.mark.asyncio
async def test_an_import_on_claude_with_a_codex_fallback_captures_both_adapters(tmp_path):
    claude = ClaudeRecorder()
    async with mixed(tmp_path, claude) as (client, app):
        assert (await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})).status_code == 200
        for kind in ("codex_cli", "claude_cli"):
            assert (await client.post("/v1/host/status", json={"provider": kind})).json()["state"] == "connected"
        assert (await client.post("/v1/host/select", json={"model": "processing-model"})).status_code == 200
        assert (await client.put("/v1/settings/import-model", json={"model": "claude-sonnet-5-5"})).status_code == 200
        assert (await client.put("/v1/settings/fallback-model", json={"model": "processing-model"})).status_code == 200
        project = (await upload(client)).json()["workspace"]["projectId"]
        operation, done = await run_import(client, app, project, "mixed")
        assert done["state"] == "succeeded", done
        capture = operation.capture
        assert (capture.primary.adapter, capture.primary.model) == ("claude_cli", "claude-sonnet-5-5")
        assert (capture.fallback.adapter, capture.fallback.model) == ("codex_cli", "processing-model")
        assert claude.models and set(claude.models) == {"claude-sonnet-5-5"}
