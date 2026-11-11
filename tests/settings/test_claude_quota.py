"""T9 of D158: Claude's quota in Settings is the last window the CLI sent with a call or an assistant run, with the
time it was read. It is only shown: the gate keeps the status check's `not_provided`. Offline stand-ins only."""

import asyncio
import json
import logging
from pathlib import Path
import sys
import threading
import time

from pydantic import BaseModel, ConfigDict
import pytest

from resume_api.agent.base import RuntimeInput
from resume_api.app import ProviderSlot
from resume_api.inference_admission import InferenceAdmission
from resume_api.lifecycle import OperationFiles
from resume_api.providers.base import Metadata, Quota
from resume_api.providers.claude.connection import ClaudeConnectionAdapter
from resume_api.providers.claude.content import ClaudeCliProvider, FixtureTransport
from resume_api.providers.claude.runtime import ClaudeAgentRuntime
from resume_api.providers.content import ContentInput, GenerationPolicy
from tests.assistant.test_claude_runtime import TOOLS, Listener, stand_in as agent_stand_in
from tests.settings.support import MetadataAdapter, application, client_session

FAKE = Path(__file__).resolve().parents[1] / "providers" / "fake_claude.py"
MODEL = "claude-sonnet-5-5"
# 2026-11-11 12:00 UTC: the service's clock in these tests.
NOW = 1_794_398_400
NONE = {"state": "not_provided", "usedPercent": None, "resetsAt": None, "readAt": None}


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str


def claude_cli(tmp_path, **config):
    """The offline Claude stand-in: status checks and structured calls, with the windows `detail` names."""
    directory = tmp_path / "claude stand-in"
    directory.mkdir()
    cli = directory / "claude"
    cli.write_text("#!" + sys.executable + "\n" + FAKE.read_text().split("\n", 1)[1])
    cli.chmod(0o700)
    configure(cli, **config)
    return cli


def configure(cli, case="valid", **extra):
    (cli.parent / "fixture.json").write_text(json.dumps({"case": case, "value": {"summary": "Synthetic summary"},
                                                         **extra}))


def host_of(app):
    routes = app.app.routes if hasattr(app, "app") else app.routes
    return next(route.endpoint.__self__ for route in routes if getattr(route, "path", "") == "/v1/host/status")


def entry(reply, kind="claude_cli"):
    return next(item for item in reply["providers"] if item["kind"] == kind)


async def shown(client, kind="claude_cli"):
    return entry((await client.get("/v1/settings/connection")).json(), kind)["quota"]


def call(provider, root):
    """One structured call on the slot's own provider, as an import or a rewrite makes it."""
    root.mkdir(exist_ok=True)
    request = ContentInput("Synthetic prompt", Summary, GenerationPolicy(MODEL, timeout_seconds=5, allow_repair=False))
    with OperationFiles(root).open() as files:
        return provider.generate(request, files, threading.Event())


@pytest.mark.asyncio
async def test_the_quota_is_not_provided_until_a_call_sends_a_window_then_the_last_one_shows_with_its_time(tmp_path,
                                                                                                            caplog):
    caplog.set_level(logging.INFO, logger="foldcv")
    cli = claude_cli(tmp_path, detail="malformed")
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    app = application(tmp_path, MetadataAdapter(), provider_slots={"claude_cli": ProviderSlot(
        ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)), provider)})
    host = host_of(app)
    host.wall = lambda: NOW
    async with client_session(app) as client:
        await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
        checked = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
        assert checked["state"] == "connected" and checked["quota"] == entry(checked)["quota"] == NONE
        # A window the event does not name readably is no reading: nothing is guessed.
        await asyncio.to_thread(call, provider, tmp_path / "calls")
        assert await shown(client) == NONE
        configure(cli)
        await asyncio.to_thread(call, provider, tmp_path / "calls")
        # The two windows fold as Codex's do: the five-hour window's higher use and its nearer reset.
        reading = {"state": "available", "usedPercent": 25.0, "resetsAt": 1800000000, "readAt": NOW}
        assert await shown(client) == reading
        # The status check reads no usage and leaves the reading; the gate keeps reading the check's quota.
        host.wall = lambda: NOW + 600
        again = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
        assert again["quota"] == entry(again)["quota"] == reading
        assert host.states["claude_cli"].quota.state == "not_provided" and host.connected("claude_cli")
        # A later run whose event names no window keeps the last reading and its time.
        configure(cli, detail="none")
        await asyncio.to_thread(call, provider, tmp_path / "calls")
        assert await shown(client) == reading
        assert (await shown(client, "codex_cli"))["state"] == "unknown"
    lines = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("foldcv"))
    assert lines and "1800000000" not in lines and str(NOW) not in lines


@pytest.mark.asyncio
async def test_a_detach_hides_the_reading_and_the_next_check_shows_it_with_its_time(tmp_path):
    cli = claude_cli(tmp_path)
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    app = application(tmp_path, MetadataAdapter(), provider_slots={"claude_cli": ProviderSlot(
        ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)), provider)})
    host = host_of(app)
    host.wall = lambda: NOW
    reading = {"state": "available", "usedPercent": 25.0, "resetsAt": 1800000000, "readAt": NOW}
    async with client_session(app) as client:
        await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
        await client.post("/v1/host/status", json={"provider": "claude_cli"})
        await asyncio.to_thread(call, provider, tmp_path / "calls")
        assert await shown(client) == reading
        # A detach signs nobody out: the reading stays, hidden while no check says the account is connected.
        detached = (await client.post("/v1/host/detach", json={"provider": "claude_cli"})).json()
        assert entry(detached)["state"] == "detached" and entry(detached)["quota"]["state"] == "unknown"
        host.wall = lambda: NOW + 600
        again = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
        assert again["state"] == "connected" and entry(again)["quota"] == reading


@pytest.mark.asyncio
async def test_an_imports_calls_refresh_the_reading(tmp_path):
    from resume_api.importer.template_transport import JOB_PERMIT
    from resume_api.inference_admission import INFERENCE
    from tests.providers.claude_relay import RelayTransport, stand_in as relay_stand_in
    from tests.templates.template_runtime_fixtures import RuntimeFixture
    from tests.templates.test_import_usage import satisfied
    directory, operations = tmp_path / "relay stand-in", tmp_path / "relay operations"
    cli = relay_stand_in(directory)
    operations.mkdir(mode=0o700)
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    app = application(tmp_path, MetadataAdapter(), provider_slots={"claude_cli": ProviderSlot(
        ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)), provider)})
    host_of(app).wall = lambda: NOW
    # The slot's own provider runs the import's calls, as the import task's transport does.
    fixture = RuntimeFixture(tmp_path / "import")
    fixture.transport = RelayTransport(provider, operations, satisfied(fixture), directory / "answers")
    fixture.pipeline = fixture.fresh_pipeline()
    async with client_session(app) as client:
        await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
        assert (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()["quota"] == NONE
        permit = await INFERENCE.reserve(asyncio.Event())
        token = JOB_PERMIT.set(permit)
        try:
            result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        finally:
            JOB_PERMIT.reset(token)
            permit.release()
        assert result.state == "published" and len(result.attempts) == 2
        assert await shown(client) == {"state": "available", "usedPercent": 25.0, "resetsAt": 1800000000, "readAt": NOW}


@pytest.mark.asyncio
async def test_an_assistant_run_refreshes_the_reading(tmp_path):
    cli = claude_cli(tmp_path)
    agent = agent_stand_in(tmp_path, "complete", {"seven_day": {"utilization": 0.61, "resetsAt": 1794459600}})
    operations = tmp_path / "operations"
    operations.mkdir(mode=0o700, exist_ok=True)
    runtime = ClaudeAgentRuntime(None, operations, fixture_executable=agent, admission=InferenceAdmission())
    app = application(tmp_path, MetadataAdapter(), provider_slots={"claude_cli": ProviderSlot(
        ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)), runtime=runtime)})
    host_of(app).wall = lambda: NOW
    listener = Listener()
    await listener.start()
    try:
        async with client_session(app) as client:
            await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
            assert (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()["quota"] == NONE
            value = RuntimeInput(model=MODEL, prompt="Проверь резюме.", url=listener.url, token=listener.token,
                                 tools=TOOLS, allow_web=False, reasoning_effort="high",
                                 revoke=lambda: setattr(listener, "active", False))
            result = await runtime.run(value, threading.Event(), lambda _kind, _payload: None)
            assert result.state == "completed"
            # The Max account's events name the seven-day window only.
            assert await shown(client) == {"state": "available", "usedPercent": 61.0, "resetsAt": 1794459600,
                                           "readAt": NOW}
    finally:
        await listener.close()


class Unknown(MetadataAdapter):
    def inspect(self, _files, _cancel, *, full=True):
        self.inspections += 1
        return Metadata("fixture-cli", ("model-a",), "plus", Quota(), {})


@pytest.mark.asyncio
@pytest.mark.parametrize(("adapter", "quota"), [
    (MetadataAdapter, {"state": "available", "usedPercent": 25.0, "resetsAt": None, "readAt": NOW}),
    # A check that found no limits has no reading, so no time either.
    (Unknown, {"state": "unknown", "usedPercent": None, "resetsAt": None, "readAt": None}),
])
async def test_codexs_quota_carries_the_time_of_its_status_check(tmp_path, adapter, quota):
    app = application(tmp_path, adapter())
    host_of(app).wall = lambda: NOW
    async with client_session(app) as client:
        checked = (await client.post("/v1/host/status", json={"provider": "codex_cli"})).json()
        assert checked["quota"] == entry(checked, "codex_cli")["quota"] == quota


@pytest.mark.asyncio
async def test_a_claude_import_starts_while_the_reading_says_the_window_is_spent_and_after_its_reset(tmp_path):
    from tests.templates.test_template_import_app import upload
    from tests.templates.test_template_fallback_model import run_import
    from tests.templates.test_template_mixed_providers import ClaudeRecorder, mixed

    class Reporting(ClaudeRecorder):
        quota_read = None

    claude = Reporting()
    async with mixed(tmp_path, claude) as (client, app):
        await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
        for kind in ("codex_cli", "claude_cli"):
            assert (await client.post("/v1/host/status", json={"provider": kind})).json()["state"] == "connected"
        assert (await client.post("/v1/host/select", json={"model": MODEL})).status_code == 200
        assert (await client.put("/v1/settings/import-model", json={"model": MODEL})).status_code == 200
        for request_id, reset in (("spent", time.time() + 3600), ("reset", time.time() - 60)):
            claude.quota_read(Quota("exhausted", 100.0, int(reset)))
            state = (await client.get("/v1/settings/connection")).json()
            assert entry(state)["quota"]["state"] == "exhausted" and entry(state)["state"] == "connected"
            # Only shown: the processing model stays ready and the import runs on Claude.
            assert state["generationReady"] is True
            calls = len(claude.models)
            project = (await upload(client)).json()["workspace"]["projectId"]
            operation, done = await run_import(client, app, project, request_id)
            assert done["state"] == "succeeded", done
            assert operation.capture.primary.adapter == "claude_cli" and len(claude.models) > calls
