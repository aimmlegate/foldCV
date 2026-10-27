"""MP01: listed providers, provider-aware host routes and switching between providers."""

import json

import pytest

from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.reasoning import ModelReasoning
from packages.resume_core.rules import RulesStore
from packages.resume_core.storage import atomic_write
from resume_api.app import ProviderSlot
from resume_api.connection import Metadata, Quota
from resume_api.providers.registry import CODEX, ProviderRegistry
from tests.settings.support import MetadataAdapter, application, client_session


class ClaudeAdapter(MetadataAdapter):
    """Second provider: newer than tested, no usage read; counts every process it would start."""

    executable = None

    def inspect(self, _files, _cancel, *, full=True):
        self.inspections += 1
        reasoning = {"claude-sonnet-5-5": ModelReasoning(default="high", supported=["low", "medium", "high"])}
        return Metadata("2.1.320 (Claude Code)", ("claude-sonnet-5-5",), "max", Quota("not_provided"), reasoning,
                        "graceful")


def preview(tmp_path, codex=None, claude=None):
    return application(tmp_path, codex or MetadataAdapter(), provider_registry=ProviderRegistry(frozenset({"claude_cli"})),
                       provider_slots={"claude_cli": ProviderSlot(claude or ClaudeAdapter())})


async def host(client, path, body=None):
    return await client.post(f"/v1/host/{path}", json=body or {})


def test_registry_lists_complete_kinds_unless_previewed():
    assert [item.kind for item in ProviderRegistry().listed()] == ["codex_cli"]
    assert [item.kind for item in ProviderRegistry(frozenset({"claude_cli"})).listed()] == ["codex_cli", "claude_cli"]
    assert ProviderRegistry().resolve("claude_cli") == "codex_cli" and ProviderRegistry().resolve(None) == "codex_cli"
    assert CODEX.complete and CODEX.team_id == "2DC432GLL2"
    with pytest.raises(ValueError):
        ProviderRegistry(frozenset({"grok_cli"}))


@pytest.mark.asyncio
async def test_only_complete_providers_are_offered(tmp_path):
    app = application(tmp_path)
    async with client_session(app) as client:
        state = (await client.get("/v1/settings/connection")).json()
        assert state["provider"] == "codex_cli" and state["providerNotice"] is None
        assert state["providers"] == [{"kind": "codex_cli", "display": "Codex", "subscription": "ChatGPT",
                                       "publisher": "OpenAI", "installed": True}]
        refused = await host(client, "select-provider", {"provider": "claude_cli"})
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
        assert (await host(client, "select-provider", {"provider": "grok_cli"})).status_code == 422
        assert (await host(client, "select-provider", {"provider": "codex_cli"})).json()["provider"] == "codex_cli"


@pytest.mark.asyncio
async def test_switch_detaches_restores_choices_and_never_runs_the_inactive_provider(tmp_path):
    codex, claude = MetadataAdapter(), ClaudeAdapter()
    app = preview(tmp_path, codex, claude)
    async with client_session(app) as client:
        connected = (await host(client, "status", {"provider": "codex_cli"})).json()
        assert connected["state"] == "connected" and connected["versionStatus"] == "supported"
        assert [item["kind"] for item in connected["providers"]] == ["codex_cli", "claude_cli"]
        assert connected["providers"][1]["installed"] is False
        assert (await host(client, "select", {"model": "model-a", "provider": "codex_cli"})).status_code == 200
        assert (await client.put("/v1/settings/rewrite-reasoning", json={"model": "model-a", "effort": "high"})).status_code == 200
        AgentSettingsStore(tmp_path / "store").restore_model("model-b", "high")
        assert claude.inspections == 0

        switched = (await host(client, "select-provider", {"provider": "claude_cli"})).json()
        assert switched["provider"] == "claude_cli" and switched["state"] == "unchecked" and switched["models"] == []
        assert claude.inspections == 0 and codex.logins == claude.logins == 0
        stale = await host(client, "status", {"provider": "codex_cli"})
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "PROVIDER_INACTIVE"
        before = codex.inspections
        status = (await host(client, "status", {"provider": "claude_cli"})).json()
        assert status["state"] == "connected" and status["versionStatus"] == "graceful"
        assert status["quota"]["state"] == "not_provided" and status["generationReady"] is False
        assert codex.inspections == before and claude.inspections == 1
        preferences = (await client.get("/v1/settings/preferences")).json()
        assert preferences["selectedProvider"] == "claude_cli" and preferences["selectedModel"] is None
        assert AgentSettingsStore(tmp_path / "store").load().selected_agent_model is None
        assert AgentSettingsStore(tmp_path / "store").load().reasoning_effort is None
        assert (await host(client, "select", {"model": "claude-sonnet-5-5"})).status_code == 200

        back = (await host(client, "select-provider", {"provider": "codex_cli"})).json()
        assert back["provider"] == "codex_cli" and back["state"] == "unchecked"
        preferences = (await client.get("/v1/settings/preferences")).json()
        assert preferences["selectedModel"] == "model-a" and preferences["rewriteReasoningEffort"] == "high"
        assert preferences["providerSelections"]["claude_cli"]["selectedModel"] == "claude-sonnet-5-5"
        restored = AgentSettingsStore(tmp_path / "store").load()
        assert (restored.selected_agent_model, restored.reasoning_effort) == ("model-b", "high")
        assert claude.inspections == 1


@pytest.mark.asyncio
async def test_stored_unlisted_provider_falls_back_to_codex_with_a_notice(tmp_path):
    root = tmp_path / "store"
    RulesStore(root).load()
    atomic_write(root / "preferences.json", json.dumps({
        "schemaVersion": 1, "automaticAnalysis": True, "theme": "system", "selectedModel": "claude-sonnet-5-5",
        "selectedProvider": "claude_cli", "providerSelections": {"codex_cli": {"selectedModel": "model-a"}}}).encode())
    app = application(tmp_path)
    async with client_session(app) as client:
        state = (await client.get("/v1/settings/connection")).json()
        assert state["provider"] == "codex_cli" and state["providerNotice"] == "provider_unavailable"
        value = PreferencesStore(root).load()
        assert value.selected_provider == "codex_cli" and value.selected_model == "model-a"
        assert value.provider_selections["claude_cli"].selected_model == "claude-sonnet-5-5"


@pytest.mark.asyncio
async def test_a_stored_preview_provider_stays_active_on_restart(tmp_path):
    first = preview(tmp_path)
    async with client_session(first) as client:
        assert (await host(client, "select-provider", {"provider": "claude_cli"})).json()["provider"] == "claude_cli"
    restarted = preview(tmp_path)
    async with client_session(restarted) as client:
        state = (await client.get("/v1/settings/connection")).json()
        assert state["provider"] == "claude_cli" and state["providerNotice"] is None
