"""MP07: a project made on Codex rewrites and exports on Claude without reprocessing (plan section 6, item 4), through
the real Claude connection and provider over the CLI stand-in; Claude is listed without a preview switch. No fixture
`content_provider`: that override would answer for every provider, so the active slot's provider must run."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from resume_api.app import ProviderSlot
from resume_api.cli.profiles.claude import ClaudeCliProfile
from resume_api.connection_claude import ClaudeConnectionAdapter
from resume_api.providers.claude_cli import ClaudeCliProvider, FixtureTransport
from tests.service.app_fixtures import PROJECT, HealthyConnection, add_project, export, make_app, open_project, signed_in

STAND_IN = Path(__file__).resolve().parents[1] / "providers" / "fake_claude.py"


def stand_in(tmp_path):
    directory = tmp_path / "claude stand-in"
    directory.mkdir()
    cli = directory / "claude"
    cli.write_text("#!" + sys.executable + "\n" + STAND_IN.read_text().split("\n", 1)[1])
    cli.chmod(0o700)
    (directory / "fixture.json").write_text(json.dumps({"case": "valid", "value": {}, "text": "Rewritten line"}))
    return cli, lambda: [json.loads(line)["args"] for line in (directory / "audit.jsonl").read_text().splitlines()]


@pytest.mark.asyncio
async def test_a_codex_project_rewrites_and_exports_on_claude_without_reprocessing(tmp_path):
    cli, audit = stand_in(tmp_path)
    claude = ProviderSlot(ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)),
                          ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli)),
                          ClaudeCliProfile(tmp_path / "claude profile", cli))
    app = make_app(tmp_path, connection_adapter=HealthyConnection(), provider_slots={"claude_cli": claude})
    add_project(app)
    repository = app.app.state.projects.repository
    before = repository.read(PROJECT)
    async with signed_in(app) as client:
        assert (await client.post("/v1/host/select-provider", json={"provider": "claude_cli"})).json()["provider"] == "claude_cli"
        assert (await client.post("/v1/host/status", json={})).json()["state"] == "connected"
        assert (await client.post("/v1/host/select", json={"model": "claude-sonnet-5-5"})).status_code == 200
        editor = await open_project(client)
        token, snapshot = editor
        preview = await client.post(f"/v2/projects/{PROJECT}/rewrite/preview", json={
            "editorToken": token, "requestId": "rewrite-1", "snapshot": snapshot, "instruction": "Make clearer.",
            "range": {"blockId": "block-paper-a", "beforeRevision": 1, "cellId": None, "field": "content",
                      "start": 0, "end": 6}})
        assert preview.status_code == 200, preview.text[:300]
        assert "Rewritten line" in preview.text
        exported = await export(client, editor)
        assert exported.status_code == 200 and exported.content[:2] == b"PK"
    generations = [args for args in audit() if args[:1] == ["-p"]]
    assert len(generations) == 1 and "--json-schema" not in generations[0]
    after = repository.read(PROJECT)
    # Nothing was processed again: the project keeps its import operations and its document.
    assert after.project.template_operations == before.project.template_operations
    assert after.project.document == before.project.document
