"""MP01 and MP08 (D119): listed providers, provider-aware host routes and both providers at once."""

import asyncio
from contextlib import contextmanager
from dataclasses import replace
import json
import sys
import threading

import pytest

from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.rules import RulesStore
from packages.resume_core.storage import atomic_write
from packages.resume_core.text_rewrite import PlainTextReply
from resume_api import app as service
from resume_api.app import ProviderSlot
from resume_api.cli.profiles.claude import ClaudeCliProfile
from resume_api.connection import ConnectionFailure, Metadata, Quota
from resume_api.inference_admission import INFERENCE
from resume_api.providers import registry as providers
from resume_api.providers.content import ContentResult, ReportedUsage
from resume_api.providers.registry import CLAUDE, CODEX, ProviderRegistry
from tests.service.app_fixtures import HealthyConnection, PROJECT, add_project, make_app, open_project, signed_in
from tests.settings.support import MetadataAdapter, application, client_session


class ClaudeAdapter(MetadataAdapter):
    """Second provider: newer than tested, no usage read; counts every process it would start."""

    executable = None

    def inspect(self, _files, _cancel, *, full=True):
        self.inspections += 1
        reasoning = {"claude-sonnet-5-5": ModelReasoning(default="high", supported=["low", "medium", "high"])}
        return Metadata("2.1.320 (Claude Code)", ("claude-sonnet-5-5",), "max", Quota("not_provided"), reasoning,
                        "graceful")


def both(tmp_path, codex=None, claude=None):
    return application(tmp_path, codex or MetadataAdapter(), provider_slots={"claude_cli": ProviderSlot(claude or ClaudeAdapter())})


async def host(client, path, body=None):
    return await client.post(f"/v1/host/{path}", json=body or {})


@pytest.fixture
def incomplete(monkeypatch):
    """Claude as it was before MP07, to keep the rules for a provider that is not offered yet."""
    monkeypatch.setitem(providers.DESCRIPTORS, "claude_cli", replace(CLAUDE, complete=False))


def test_claude_is_listed_after_mp07():
    assert CLAUDE.complete and [item.kind for item in ProviderRegistry().listed()] == ["codex_cli", "claude_cli"]
    assert ProviderRegistry().resolve("claude_cli") == "claude_cli"


def test_registry_lists_complete_kinds_unless_previewed(incomplete):
    assert [item.kind for item in ProviderRegistry().listed()] == ["codex_cli"]
    assert [item.kind for item in ProviderRegistry(frozenset({"claude_cli"})).listed()] == ["codex_cli", "claude_cli"]
    assert ProviderRegistry().resolve("claude_cli") == "codex_cli" and ProviderRegistry().resolve(None) == "codex_cli"
    assert CODEX.complete and CODEX.team_id == "2DC432GLL2"
    with pytest.raises(ValueError):
        ProviderRegistry(frozenset({"grok_cli"}))


@pytest.mark.asyncio
async def test_only_complete_providers_are_offered(tmp_path, incomplete):
    app = application(tmp_path, provider_slots={"claude_cli": ProviderSlot(ClaudeAdapter())})
    async with client_session(app) as client:
        state = (await client.get("/v1/settings/connection")).json()
        assert state["provider"] == "codex_cli" and [item["kind"] for item in state["providers"]] == ["codex_cli"]
        assert state["providers"][0]["installed"] and state["providers"][0]["enabled"]
        for path, body in (("enable", {"provider": "claude_cli", "enabled": True}), ("status", {"provider": "claude_cli"})):
            refused = await host(client, path, body)
            assert refused.status_code == 409 and refused.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
        assert (await host(client, "enable", {"provider": "grok_cli", "enabled": True})).status_code == 422
        assert (await host(client, "enable", {"provider": "codex_cli", "enabled": True})).json()["provider"] == "codex_cli"


@pytest.mark.asyncio
async def test_both_providers_connect_at_once_and_every_choice_takes_either_providers_model(tmp_path):
    codex, claude = MetadataAdapter(), ClaudeAdapter()
    app = both(tmp_path, codex, claude)
    async with client_session(app) as client:
        state = (await host(client, "status", {"provider": "codex_cli"})).json()
        assert state["state"] == "connected" and state["models"] == ["model-a", "model-b"]
        assert [(item["kind"], item["enabled"]) for item in state["providers"]] == [("codex_cli", True), ("claude_cli", False)]
        assert claude.inspections == 0
        assert (await host(client, "enable", {"provider": "claude_cli", "enabled": True})).json()["providers"][1]["enabled"]
        assert claude.inspections == 0 and codex.logins == claude.logins == 0
        state = (await host(client, "status", {"provider": "claude_cli"})).json()
        assert state["provider"] == "claude_cli" and state["state"] == "connected" and state["versionStatus"] == "graceful"
        assert state["quota"]["state"] == "not_provided" and state["providers"][0]["state"] == "connected"
        assert state["providers"][0]["quota"]["usedPercent"] == 25
        assert state["models"] == ["model-a", "model-b", "claude-sonnet-5-5"] and codex.inspections == 1
        assert state["modelReasoning"]["claude-sonnet-5-5"]["supported"] == ["low", "medium", "high"]
        assert (await host(client, "select", {"model": "claude-sonnet-5-5"})).status_code == 200
        for path, model in (("import-model", "model-b"), ("fallback-model", "claude-sonnet-5-5"), ("rewrite-model", "model-a")):
            assert (await client.put(f"/v1/settings/{path}", json={"model": model})).status_code == 200, path
        assert (await client.put("/v1/settings/rewrite-reasoning", json={"model": "model-a", "effort": "high"})).status_code == 200
        preferences = (await client.get("/v1/settings/preferences")).json()
        assert (preferences["selectedModel"], preferences["selectedImportModel"], preferences["selectedFallbackModel"],
                preferences["selectedRewriteModel"]) == ("claude-sonnet-5-5", "model-b", "claude-sonnet-5-5", "model-a")
        assert preferences["enabledProviders"] == ["codex_cli", "claude_cli"]
        assert (await client.get("/v1/settings/connection")).json()["selectedModel"] == "claude-sonnet-5-5"


@pytest.mark.asyncio
async def test_a_provider_that_is_off_runs_nothing_and_offers_no_model(tmp_path):
    codex, claude = MetadataAdapter(), ClaudeAdapter()
    app = both(tmp_path, codex, claude)
    async with client_session(app) as client:
        for path in ("status", "discover", "login", "detach", "install"):
            refused = await host(client, path, {"provider": "claude_cli"})
            assert refused.status_code == 409 and refused.json()["error"]["code"] == "PROVIDER_INACTIVE", path
        assert claude.inspections == claude.logins == 0
        await host(client, "enable", {"provider": "claude_cli", "enabled": True})
        await host(client, "status", {"provider": "claude_cli"})
        assert (await host(client, "select", {"model": "claude-sonnet-5-5"})).status_code == 200
        off = (await host(client, "enable", {"provider": "claude_cli", "enabled": False})).json()
        assert off["providers"][1]["enabled"] is False and off["providers"][1]["state"] == "unchecked"
        assert off["models"] == [] and off["selectedModel"] is None and claude.logins == 0
        assert (await client.put("/v1/settings/import-model", json={"model": "claude-sonnet-5-5"})).status_code == 409
        assert (await client.get("/v1/settings/preferences")).json()["enabledProviders"] == ["codex_cli"]
        # Codex may be off too; then nothing is offered.
        await host(client, "status", {"provider": "codex_cli"})
        off = (await host(client, "enable", {"provider": "codex_cli", "enabled": False})).json()
        assert off["models"] == [] and (await host(client, "status", {})).status_code == 409


@pytest.mark.asyncio
async def test_detaching_one_provider_keeps_the_other_connected(tmp_path):
    app = both(tmp_path)
    async with client_session(app) as client:
        await host(client, "enable", {"provider": "claude_cli", "enabled": True})
        await host(client, "status", {"provider": "codex_cli"})
        await host(client, "status", {"provider": "claude_cli"})
        detached = (await host(client, "detach", {"provider": "claude_cli"})).json()
        assert detached["state"] == "detached" and detached["providers"][0]["state"] == "connected"
        assert detached["models"] == ["model-a", "model-b"]
        again = (await host(client, "detach", {"provider": "codex_cli"})).json()
        assert again["state"] == "detached" and again["models"] == []


@pytest.mark.asyncio
async def test_stored_choices_of_the_one_active_design_turn_claude_on(tmp_path):
    root = tmp_path / "store"
    RulesStore(root).load()
    atomic_write(root / "preferences.json", json.dumps({
        "schemaVersion": 1, "automaticAnalysis": True, "theme": "system", "selectedModel": "claude-sonnet-5-5",
        "selectedProvider": "claude_cli", "providerSelections": {"codex_cli": {"selectedModel": "model-a"}}}).encode())
    app = both(tmp_path)
    async with client_session(app) as client:
        state = (await client.get("/v1/settings/connection")).json()
        assert [item["enabled"] for item in state["providers"]] == [True, True]
        await host(client, "status", {"provider": "claude_cli"})
        assert (await client.get("/v1/settings/connection")).json()["selectedModel"] == "claude-sonnet-5-5"
    value = PreferencesStore(root).load()
    assert value.selected_model == "claude-sonnet-5-5" and value.enabled_providers == ["codex_cli", "claude_cli"]


@pytest.mark.asyncio
async def test_a_stored_provider_that_is_no_longer_listed_is_not_offered(tmp_path, incomplete):
    root = tmp_path / "store"
    RulesStore(root).load()
    PreferencesStore(root).enable_provider("claude_cli", True)
    app = application(tmp_path, provider_slots={"claude_cli": ProviderSlot(ClaudeAdapter())})
    async with client_session(app) as client:
        state = (await client.get("/v1/settings/connection")).json()
        assert state["provider"] == "codex_cli" and [item["kind"] for item in state["providers"]] == ["codex_cli"]
        assert (await host(client, "status", {"provider": "claude_cli"})).json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


class SignedOut(ClaudeAdapter):
    """Needs a sign-in until `login` ran, and records who held the inference permit when it did."""

    def __init__(self):
        super().__init__()
        self.signed_in, self.permit_at_login = False, None

    def inspect(self, files, cancel, *, full=True):
        if not self.signed_in:
            raise ConnectionFailure("LOGIN_REQUIRED", "2.1.320")
        return super().inspect(files, cancel, full=full)

    def login(self, _files, _cancel, code=None):
        self.logins += 1
        self.signed_in, self.permit_at_login = True, (INFERENCE.shared, INFERENCE.exclusive)


class Checks(ClaudeAdapter):
    """Reports back only after the test lets the check end."""

    def __init__(self):
        super().__init__()
        self.hold, self.entered = None, threading.Event()

    def inspect(self, files, cancel, *, full=True):
        if self.hold is not None:
            self.entered.set()
            self.hold.wait(5)
        return super().inspect(files, cancel, full=full)


class Plain:
    template_adapter = "claude_cli"

    def __init__(self):
        self.invalidated = 0

    def generate(self, request, _files, _cancel):
        return ContentResult(PlainTextReply(text="Clear"), ReportedUsage(), "fixture", request.policy.model, .01, 1)

    def invalidate_preflight(self):
        self.invalidated += 1


@contextmanager
def running_rewrite(app):
    """A model call holding a shared permit until the rewrite cancel path stops it."""
    rewrite, cancel, entered = app.app.state.projects.rewrite_cancel.__self__, threading.Event(), threading.Event()
    rewrite.cancels["project", "request"] = cancel

    def work():
        with INFERENCE.hold(threading.Event()):
            entered.set()
            cancel.wait(5)

    thread = threading.Thread(target=work)
    thread.start()
    assert entered.wait(5)
    try:
        yield cancel
    finally:
        cancel.set()
        thread.join(5)
        del rewrite.cancels["project", "request"]


async def queued(task):
    """Wait until `task` waits behind the permit, or ended instead."""
    for _ in range(500):
        if INFERENCE.waiting or task.done():
            return
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["codex_cli", "claude_cli"])
async def test_a_sign_in_stops_model_work_on_either_provider_then_runs_alone(tmp_path, monkeypatch, kind):
    adapter = SignedOut()
    app = both(tmp_path, **{"codex" if kind == "codex_cli" else "claude": adapter})
    stopped = []
    monkeypatch.setattr(app.app.state.assistant, "stop_all", lambda: stopped.append("assistant"))
    monkeypatch.setattr(app.app.state.projects.imports, "stop_all", lambda: stopped.append("imports"))
    async with client_session(app) as client:
        await host(client, "enable", {"provider": "claude_cli", "enabled": True})
        assert (await host(client, "status", {"provider": kind})).json()["state"] == "login_required"
        with running_rewrite(app) as cancel:
            reply = await host(client, "login", {"provider": kind})
            assert reply.status_code == 200 and cancel.is_set()
        assert sorted(stopped) == ["assistant", "imports"]
        assert adapter.logins == 1 and adapter.permit_at_login == (0, True)


@pytest.mark.asyncio
async def test_a_sign_in_that_cannot_get_the_permit_goes_back_to_login_required(tmp_path, monkeypatch):
    adapter = SignedOut()
    monkeypatch.setattr(service, "MODEL_STOP_SECONDS", 0.05)
    app = application(tmp_path, adapter)
    async with client_session(app) as client:
        await host(client, "status")
        # A permit no stop reaches, as an import keeps it after unverified cleanup.
        with INFERENCE.hold(threading.Event()):
            refused = (await host(client, "login")).json()
        assert refused["state"] == "login_required" and refused["version"] == "2.1.320" and adapter.logins == 0
        assert (await host(client, "login")).status_code == 200 and adapter.logins == 1


@pytest.mark.asyncio
async def test_a_check_during_model_work_waits_for_the_permit_and_then_runs(tmp_path):
    claude = ClaudeAdapter()
    async with client_session(both(tmp_path, claude=claude)) as client:
        await host(client, "enable", {"provider": "claude_cli", "enabled": True})
        with INFERENCE.hold(threading.Event()):
            check = asyncio.create_task(host(client, "status", {"provider": "claude_cli"}))
            await queued(check)
            assert not check.done() and claude.inspections == 0
        reply = await check
        assert reply.status_code == 200 and reply.json()["state"] == "connected" and claude.inspections == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("job", ["status", "discover"])
async def test_a_check_past_its_wait_answers_busy_and_leaves_the_metadata_alone(tmp_path, monkeypatch, job):
    claude, provider = ClaudeAdapter(), Plain()
    monkeypatch.setattr(service, "CHECK_WAIT_SECONDS", 0.05)
    app = application(tmp_path, MetadataAdapter(), provider_slots={"claude_cli": ProviderSlot(claude, provider)})
    async with client_session(app) as client:
        await host(client, "enable", {"provider": "claude_cli", "enabled": True})
        with INFERENCE.hold(threading.Event()):
            reply = await host(client, job, {"provider": "claude_cli"})
        assert reply.status_code == 429
        assert reply.json()["error"]["code"] == "BUSY" and reply.json()["error"]["retryable"] is True
        assert claude.inspections == 0 and provider.invalidated == 0
        assert (await host(client, job, {"provider": "claude_cli"})).status_code == 200
        assert claude.inspections == 1 and provider.invalidated == 1


@pytest.mark.asyncio
async def test_new_model_work_queues_behind_a_check_of_its_provider(tmp_path):
    executable = tmp_path / "cli"
    executable.write_text("#!" + sys.executable + "\n")
    executable.chmod(0o700)
    adapter = Checks()
    app = make_app(tmp_path, connection_adapter=HealthyConnection(), provider_slots={"claude_cli": ProviderSlot(
        adapter, Plain(), ClaudeCliProfile(tmp_path / "claude profile", executable))})
    add_project(app)
    selection = {"blockId": "block-paper-a", "beforeRevision": 1, "cellId": None, "field": "content", "start": 0, "end": 6}
    async with signed_in(app) as client:
        await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
        assert (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()["state"] == "connected"
        await client.post("/v1/host/select", json={"provider": "claude_cli", "model": "claude-sonnet-5-5"})
        token, snapshot = await open_project(client)
        adapter.hold = threading.Event()
        check = asyncio.create_task(client.post("/v1/host/status", json={"provider": "claude_cli"}))
        assert await asyncio.to_thread(adapter.entered.wait, 5)
        assert (await client.get("/v1/settings/connection")).json()["generationReady"] is True
        assert "claude-sonnet-5-5" in app.app.state.assistant.connection().models
        rewrite = asyncio.create_task(client.post(f"/v2/projects/{PROJECT}/rewrite/preview", json={
            "editorToken": token, "requestId": "during-check", "snapshot": snapshot, "instruction": "x", "range": selection}))
        await queued(rewrite)
        assert not rewrite.done()
        adapter.hold.set()
        assert (await check).status_code == 200
        reply = await rewrite
        assert reply.status_code == 200 and "Clear" in reply.text
