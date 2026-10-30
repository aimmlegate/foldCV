"""MP02b: the managed Claude install from the pinned release, through the installer and the app routes."""

import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

from resume_api.app import ProviderSlot
from resume_api.cli import claude_distribution as release
from resume_api.cli.installation import ClaudeInstallation, CliInstallation, InstallationFailure
from resume_api.cli.profiles import claude
from resume_api.cli.profiles.claude import ClaudeCliProfile
from resume_api.cli.qualification import Version
from resume_api.connection_claude import ClaudeConnectionAdapter
from resume_api.launcher import bind_claude, claude_slot
from resume_api.lifecycle import OperationFiles
from resume_api.providers.claude_cli import FixtureTransport
from resume_api.providers.registry import CLAUDE, ProviderRegistry
from tests.settings.support import MetadataAdapter, application, client_session

STAND_IN = Path(__file__).resolve().parents[1] / "providers" / "fake_claude.py"


@pytest.fixture
def binary(tmp_path, monkeypatch):
    """The offline Claude stand-in published as the pinned release binary."""
    payload = ("#!" + sys.executable + "\n" + STAND_IN.read_text().split("\n", 1)[1]).encode()
    source = tmp_path / "release-binary"
    source.write_bytes(payload)
    monkeypatch.setattr(release, "BINARY_BYTES", len(payload))
    monkeypatch.setattr(release, "BINARY_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(CliInstallation, "download", lambda _self, _files, target: shutil.copyfile(source, target))
    monkeypatch.setattr(claude, "installed_executable", lambda: None)
    return source, payload


def install(installer, tmp_path):
    with OperationFiles(tmp_path / "operations").open() as files:
        return installer.install(files)


def test_the_pin_is_one_supported_release_from_the_signed_manifest():
    assert release.BINARY_URL == ("https://downloads.claude.ai/claude-code-releases/" + release.RELEASE
                                  + "/darwin-arm64/claude")
    assert claude.COMPATIBILITY.status(Version.parse(release.RELEASE)) == "supported"
    assert CLAUDE.managed_install and len(release.BINARY_SHA256) == len(release.MANIFEST_SHA256) == 64


def test_verified_install_publishes_one_private_binary(binary, tmp_path):
    installer = ClaudeInstallation(tmp_path / "cli-runtime-claude_cli")
    assert installer.snapshot()["version"] == release.RELEASE
    assert installer.snapshot()["totalBytes"] == len(binary[1])
    assert install(installer, tmp_path) == installer.executable
    assert installer.executable == installer.root / release.RELEASE / "bin/claude"
    assert installer.executable.read_bytes() == binary[1]
    assert installer.executable.stat().st_mode & 0o777 == 0o700
    assert installer.snapshot()["state"] == "ready"
    assert sorted(path.name for path in installer.root.iterdir()) == [".foldcv-cli-runtime-v1", ".install.lock",
                                                                      release.RELEASE]
    assert not list((tmp_path / "operations").iterdir())


@pytest.mark.parametrize("damage", ["checksum", "size", "network", "cancelled", "copy"])
def test_a_failed_install_keeps_the_previous_runtime(binary, tmp_path, monkeypatch, damage):
    installer = ClaudeInstallation(tmp_path / "runtime")
    assert install(installer, tmp_path)
    original = installer.executable.read_bytes()
    if damage == "checksum":
        monkeypatch.setattr(release, "BINARY_SHA256", "0" * 64)
    elif damage == "size":
        binary[0].write_bytes(binary[1] + b"\n")
    elif damage == "network":
        def fail(*_args):
            raise InstallationFailure("download_failed")
        monkeypatch.setattr(installer, "download", fail)
    elif damage == "copy":
        stage = installer.stage

        def cancel_while_copying(download, staging):
            installer.cancel.set()
            stage(download, staging)
        monkeypatch.setattr(installer, "stage", cancel_while_copying)
    else:
        installer.cancel.set()
    assert install(installer, tmp_path) is None
    assert installer.snapshot()["state"] == ("cancelled" if damage in {"cancelled", "copy"} else "failed")
    assert installer.snapshot()["error"] == {"checksum": "checksum_failed", "size": "checksum_failed",
                                             "network": "download_failed"}.get(damage, "cancelled")
    assert installer.executable.read_bytes() == original
    assert not list(installer.root.glob(".staging-*")) and not list(installer.root.glob(".previous-*"))
    assert not list((tmp_path / "operations").iterdir())


def test_the_slot_prefers_the_managed_runtime_then_a_native_install(binary, tmp_path, monkeypatch):
    store = tmp_path / "store"
    missing = claude_slot(store)
    assert missing.profile.executable == missing.installation.executable and not missing.profile.executable.exists()
    assert missing.profile.root == store / "cli-profile-claude_cli"
    native = tmp_path / "native" / "claude"
    native.parent.mkdir()
    native.write_bytes(b"native")
    monkeypatch.setattr(claude, "installed_executable", lambda: native)
    assert claude_slot(store).profile.executable == native
    assert install(missing.installation, tmp_path)
    assert claude_slot(store).profile.executable == missing.installation.executable


def bind_stand_in(slot, executable):
    """Like the launcher's binding, with the stand-in's explicit test transport instead of the sandboxed CLI."""
    return ProviderSlot(ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(executable)), None,
                        ClaudeCliProfile(slot.profile.root, executable), slot.installation, rebind=bind_stand_in)


def app_with(tmp_path, slot):
    return application(tmp_path, MetadataAdapter(), provider_registry=ProviderRegistry(frozenset({"claude_cli"})),
                       provider_slots={"claude_cli": slot})


async def switch_to_claude(client):
    state = (await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})).json()
    assert state["provider"] == "claude_cli"
    missing = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
    assert missing["state"] == "cli_missing" and missing["installation"]["state"] == "idle"
    assert missing["providers"][1]["installed"] is False
    return missing


@pytest.mark.asyncio
async def test_install_from_settings_connects_without_a_restart(binary, tmp_path):
    slot = claude_slot(tmp_path / "store")
    app = app_with(tmp_path, bind_stand_in(slot, slot.profile.executable))
    async with client_session(app) as client:
        await switch_to_claude(client)
        # Codex stays on next to Claude; this fixture has no managed Codex install.
        refused = await client.post("/v1/host/install", json={"provider": "codex_cli"})
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "INSTALL_NOT_AVAILABLE"
        installed = (await client.post("/v1/host/install", json={"provider": "claude_cli"})).json()
        assert installed["state"] == "unchecked" and installed["installation"]["state"] == "ready"
        executable = slot.installation.executable
        (executable.parent / "fixture.json").write_text(json.dumps({"case": "valid", "value": {}}))
        connected = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
        assert connected["state"] == "connected" and connected["providers"][1]["installed"] is True
        assert (await client.post("/v1/host/install", json={"provider": "claude_cli"})).status_code == 409


@pytest.mark.asyncio
async def test_the_installed_binary_is_still_qualified_by_its_signature(binary, tmp_path):
    slot = claude_slot(tmp_path / "store")
    assert slot.rebind is bind_claude
    async with client_session(app_with(tmp_path, slot)) as client:
        await switch_to_claude(client)
        assert (await client.post("/v1/host/install", json={"provider": "claude_cli"})).json()["installation"]["state"] == "ready"
        # The unsigned stand-in fails the publisher check, so Settings offers the install again.
        status = (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()
        assert status["state"] == "unsupported_version" and status["installation"]["available"]
    assert not (slot.installation.executable.parent / "audit.jsonl").exists()
