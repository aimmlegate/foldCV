"""MP02: the Claude connection through the app routes, with the offline Claude stand-in and Claude in preview."""

import asyncio
import json
from pathlib import Path
import sys

import pytest

from resume_api.app import ProviderSlot
from resume_api.connection_claude import ClaudeConnectionAdapter
from resume_api.providers.claude_cli import FixtureTransport
from resume_api.providers.registry import ProviderRegistry
from tests.settings.support import MetadataAdapter, application, client_session

SOURCE = Path(__file__).resolve().parents[1] / "providers" / "fake_claude.py"


@pytest.fixture
def claude(tmp_path):
    directory = tmp_path / "claude stand-in"
    directory.mkdir()
    cli = directory / "claude"
    cli.write_text("#!" + sys.executable + "\n" + SOURCE.read_text().split("\n", 1)[1])
    cli.chmod(0o700)

    def configure(case="valid", **extra):
        (directory / "fixture.json").write_text(json.dumps({"case": case, "value": {}, **extra}))
        for name in ("calls", "audit.jsonl", "signed-in"):
            (directory / name).unlink(missing_ok=True)

    def audit():
        path = directory / "audit.jsonl"
        return [json.loads(line)["args"] for line in path.read_text().splitlines()] if path.exists() else []
    configure()
    return cli, configure, audit


def app_with(tmp_path, adapter):
    return application(tmp_path, MetadataAdapter(), provider_registry=ProviderRegistry(frozenset({"claude_cli"})),
                       provider_slots={"claude_cli": ProviderSlot(adapter)})


async def on_claude(client):
    state = (await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})).json()
    assert state["provider"] == "claude_cli" and state["providers"][1]["enabled"]
    return state


def summary(entry):
    return {key: entry[key] for key in ("kind", "display", "subscription", "publisher", "loginCode", "installed")}


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "version", "state"), [
    ("valid", "2.1.308 (Claude Code)", "connected"),
    ("valid", "2.1.200 (Claude Code)", "unsupported_version"),
    ("bad_help", "2.1.308 (Claude Code)", "unsupported_version"),
    ("logged_out", "2.1.308 (Claude Code)", "login_required"),
    ("api_key", "2.1.308 (Claude Code)", "api_key_mode"),
])
async def test_claude_connection_states(tmp_path, claude, case, version, state):
    cli, configure, audit = claude
    configure(case, version=version)
    app = app_with(tmp_path, ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)))
    async with client_session(app) as client:
        await on_claude(client)
        assert audit() == []
        result = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
        assert result["state"] == state
        if state == "connected":
            assert result["versionStatus"] == "supported" and result["plan"] == "max"
            assert result["quota"] == {"state": "not_provided", "usedPercent": None, "resetsAt": None}
            assert "claude-sonnet-5-5" in result["models"] and result["modelReasoning"]["claude-sonnet-5-5"]["default"]
        assert summary(result["providers"][1]) == {"kind": "claude_cli", "display": "Claude", "subscription": "Claude",
                                                   "publisher": "Anthropic", "loginCode": True,
                                                   "installed": state != "cli_missing"}
        assert result["providers"][1]["state"] == state
    assert not any(args[:1] == ["-p"] for args in audit())


@pytest.mark.asyncio
async def test_missing_claude_cli_is_reported_without_a_process(tmp_path):
    app = app_with(tmp_path, ClaudeConnectionAdapter(None))
    async with client_session(app) as client:
        await on_claude(client)
        result = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
        assert result["state"] == "cli_missing" and result["providers"][1]["installed"] is False


@pytest.mark.asyncio
async def test_sign_in_takes_the_pasted_code_once_and_never_logs_out(tmp_path, claude):
    cli, configure, audit = claude
    configure("login_code")
    app = app_with(tmp_path, ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)))
    async with client_session(app) as client:
        await on_claude(client)
        refused = await client.post("/v1/host/login-code", json={"provider": "claude_cli", "code": "synthetic-code"})
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "LOGIN_NOT_AVAILABLE"
        assert (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()["state"] == "login_required"
        login = asyncio.create_task(client.post("/v1/host/login", json={"provider": "claude_cli"}))
        for _ in range(400):
            if ["auth", "login", "--claudeai"] in audit():
                break
            await asyncio.sleep(0.01)
        pending = (await client.get("/v1/settings/connection")).json()
        assert pending["providers"][1]["state"] == "login_pending" and pending["providers"][0]["state"] == "unchecked"
        assert (await client.post("/v1/host/login-code", json={"code": "bad code"})).status_code == 422
        assert (await client.post("/v1/host/login-code", json={"provider": "codex_cli", "code": "x"})).status_code == 409
        sent = await client.post("/v1/host/login-code", json={"provider": "claude_cli", "code": "synthetic-code"})
        assert sent.status_code == 200
        assert (await asyncio.wait_for(login, 10)).json()["state"] == "login_required"
        assert (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()["state"] == "connected"
    assert ["auth", "logout"] not in audit() and "synthetic-code" not in json.dumps(audit())
