"""MP02b, D146: the managed Claude install takes the newest signed release, through the installer and the app routes; an
update replaces the installed release only after the new one passes its checks."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading

import pytest

from resume_api import release_checks
from resume_api.app import ProviderSlot
from resume_api.cli import claude_distribution as release
from resume_api.cli.installation import ClaudeInstallation, CliInstallation, InstallationFailure
from resume_api.cli.profiles import claude
from resume_api.cli.profiles.claude import ClaudeCliProfile
from resume_api.cli.qualification import Version
from resume_api.cli.releases import RECORD, Release, ReleaseFailure
from resume_api.connection_claude import ClaudeConnectionAdapter
from resume_api.launcher import bind_claude, claude_slot
from resume_api.lifecycle import OperationFiles, SpikeError
from resume_api.providers.claude_cli import ClaudeCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure
from resume_api.providers.registry import CLAUDE, ProviderRegistry
from tests.settings.support import MetadataAdapter, application, client_session

STAND_IN = Path(__file__).resolve().parents[1] / "providers" / "fake_claude.py"


def stand_in(note: str = "") -> bytes:
    return ("#!" + sys.executable + "\n" + STAND_IN.read_text().split("\n", 1)[1] + note).encode()


class Releases:
    """The newest release the bucket names, served from local files; `offer` publishes another one."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.current = None
        self.offer("2.1.318", stand_in())

    def offer(self, version, payload):
        source = self.tmp_path / ("release-" + version)
        source.write_bytes(payload)
        self.current = Release(version, release.BASE_URL + version + "/" + release.PLATFORM + "/" + release.BINARY,
                               len(payload), hashlib.sha256(payload).hexdigest())
        self.source = source
        return payload


@pytest.fixture
def binary(tmp_path, monkeypatch):
    """The offline Claude stand-in published as the newest release; its own checks are tested on their own."""
    releases = Releases(tmp_path)
    monkeypatch.setattr(ClaudeInstallation, "lookup", lambda _self, _fetch: releases.current)
    monkeypatch.setattr(CliInstallation, "download",
                        lambda _self, _files, target, _release: shutil.copyfile(releases.source, target))
    monkeypatch.setattr(ClaudeInstallation, "publisher", lambda _self, _binary: None)
    monkeypatch.setattr(release_checks, "claude", lambda _root: None)
    monkeypatch.setattr(claude, "installed_executable", lambda: None)
    return releases


def install(installer, tmp_path):
    with OperationFiles(tmp_path / "operations").open() as files:
        return installer.install(files)


def check(installer, tmp_path):
    with OperationFiles(tmp_path / "operations").open() as files:
        installer.check(files, threading.Event())


def test_the_release_pinned_before_updates_is_a_supported_one():
    assert claude.COMPATIBILITY.status(Version.parse(release.RELEASE)) == "supported"
    assert CLAUDE.managed_install and len(release.BINARY_SHA256) == 64
    assert release.entry() == "bin/" + release.BINARY


def test_verified_install_publishes_the_newest_release_with_its_record(binary, tmp_path):
    installer = ClaudeInstallation(tmp_path / "cli-runtime-claude_cli")
    assert installer.snapshot() | {"available": True} == {"state": "idle", "downloadedBytes": 0, "totalBytes": 0,
                                                          "error": None, "available": True, "installed": None,
                                                          "latest": None, "update": False}
    assert install(installer, tmp_path) == installer.executable
    assert installer.executable == installer.root / "2.1.318" / "bin/claude"
    assert installer.executable.read_bytes() == binary.source.read_bytes()
    assert installer.executable.stat().st_mode & 0o777 == 0o700
    assert json.loads((installer.root / "2.1.318" / RECORD).read_text()) == {
        "version": "2.1.318", "files": {"bin/claude": binary.current.sha256}}
    snapshot = installer.snapshot()
    assert (snapshot["state"], snapshot["installed"], snapshot["latest"], snapshot["update"]) == (
        "ready", "2.1.318", "2.1.318", False)
    assert snapshot["totalBytes"] == binary.current.size
    assert sorted(path.name for path in installer.root.iterdir()) == [".foldcv-cli-runtime-v1", ".install.lock",
                                                                      "2.1.318"]
    assert not list((tmp_path / "operations").iterdir())


@pytest.mark.parametrize("damage", ["checksum", "size", "network", "listing", "cancelled", "copy"])
def test_a_failed_install_keeps_the_previous_runtime(binary, tmp_path, monkeypatch, damage):
    installer = ClaudeInstallation(tmp_path / "runtime")
    assert install(installer, tmp_path)
    original = installer.executable.read_bytes()
    if damage == "checksum":
        binary.current = Release(binary.current.version, binary.current.url, binary.current.size, "0" * 64)
    elif damage == "size":
        binary.source.write_bytes(original + b"\n")
    elif damage == "network":
        def fail(*_args):
            raise InstallationFailure("download_failed")
        monkeypatch.setattr(installer, "download", fail)
    elif damage == "listing":
        def unsigned(_fetch):
            raise ReleaseFailure("invalid_package")
        monkeypatch.setattr(installer, "lookup", unsigned)
    elif damage == "copy":
        stage = installer.stage

        def cancel_while_copying(download, staging, target):
            installer.cancel.set()
            return stage(download, staging, target)
        monkeypatch.setattr(installer, "stage", cancel_while_copying)
    else:
        installer.cancel.set()
    assert install(installer, tmp_path) is None
    assert installer.snapshot()["state"] == ("cancelled" if damage in {"cancelled", "copy"} else "failed")
    assert installer.snapshot()["error"] == {"checksum": "checksum_failed", "size": "checksum_failed",
                                             "network": "download_failed", "listing": "invalid_package"
                                             }.get(damage, "cancelled")
    assert installer.executable.read_bytes() == original
    assert not list(installer.root.glob(".staging-*")) and not list(installer.root.glob(".previous-*"))
    assert not list((tmp_path / "operations").iterdir())


def test_a_newer_release_is_offered_and_replaces_the_installed_one(binary, tmp_path):
    binary.offer("2.1.310", stand_in("# 2.1.310\n"))
    installer = ClaudeInstallation(tmp_path / "runtime")
    assert install(installer, tmp_path) == installer.root / "2.1.310" / "bin/claude"
    check(installer, tmp_path)
    assert installer.snapshot()["update"] is False
    newest = binary.offer("2.1.318", stand_in("# 2.1.318\n"))
    # One look serves for hours; a fresh look finds the newer release.
    check(installer, tmp_path)
    assert installer.snapshot()["latest"] == "2.1.310"
    installer.found_at -= 7 * 3600
    check(installer, tmp_path)
    assert (installer.snapshot()["installed"], installer.snapshot()["latest"], installer.snapshot()["update"]) == (
        "2.1.310", "2.1.318", True)
    assert install(installer, tmp_path) == installer.root / "2.1.318" / "bin/claude"
    assert installer.executable.read_bytes() == newest
    assert not (installer.root / "2.1.310").exists()
    assert installer.snapshot()["update"] is False


@pytest.mark.parametrize("failure", ["incompatible_release", "install_failed"])
def test_a_release_that_fails_its_checks_keeps_the_installed_one(binary, tmp_path, failure):
    calls = []

    def qualify(_files, executable, version, _cancel):
        calls.append((executable, version))
        if version == "2.1.318":
            raise InstallationFailure(failure)
    binary.offer("2.1.310", stand_in("# 2.1.310\n"))
    installer = ClaudeInstallation(tmp_path / "runtime", qualify=qualify)
    original = install(installer, tmp_path)
    assert calls == [(original, "2.1.310")]
    binary.offer("2.1.318", stand_in("# 2.1.318\n"))
    installer.found_at = None
    check(installer, tmp_path)
    assert installer.snapshot()["update"] is True
    assert install(installer, tmp_path) is None
    assert installer.snapshot()["error"] == failure and installer.executable == original
    assert not (installer.root / "2.1.318").exists() and original.is_file()
    # A refused release is not offered again in this run; a failure that says nothing about it is.
    assert installer.snapshot()["update"] is (failure == "install_failed")


def test_a_reinstall_of_the_same_release_restores_it_when_its_checks_fail(binary, tmp_path):
    installer = ClaudeInstallation(tmp_path / "runtime")
    original = install(installer, tmp_path)
    content = original.read_bytes()

    def refuse(*_args):
        raise InstallationFailure("incompatible_release")
    installer.qualify = refuse
    assert install(installer, tmp_path) is None
    assert original.read_bytes() == content and not list(installer.root.glob(".previous-*"))


def test_the_release_pinned_before_updates_still_counts_and_is_offered_an_update(binary, tmp_path, monkeypatch):
    payload = b"pinned 2.1.308"
    monkeypatch.setattr(release, "BINARY_SHA256", hashlib.sha256(payload).hexdigest())
    installer = ClaudeInstallation(tmp_path / "runtime")
    pinned = installer.root / release.RELEASE / "bin" / release.BINARY
    pinned.parent.mkdir(parents=True)
    pinned.write_bytes(payload)
    assert installer.executable == pinned and installer.installed() == release.RELEASE
    check(installer, tmp_path)
    assert installer.snapshot()["update"] is True


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
    assert claude_slot(store).profile.managed and not ClaudeCliProfile(missing.profile.root, native).managed


class Capabilities:
    def __init__(self, outcome):
        self.outcome = outcome

    def __call__(self, _files, _cancel, _end):
        if not self.outcome[0].isdigit():
            raise ContentFailure(self.outcome)
        return Version.parse(self.outcome), "supported"


@pytest.mark.parametrize(("outcome", "code"), [
    ("2.1.318 (Claude Code)", None), ("2.1.317 (Claude Code)", "incompatible_release"),
    ("CLI_UNSUPPORTED", "incompatible_release"), ("CANCELLED", "cancelled"), ("DEADLINE_EXCEEDED", "install_failed"),
    ("CLI_PROFILE_UNSAFE", "install_failed"), ("PROCESS_CLEANUP_FAILED", "PROCESS_CLEANUP_FAILED"),
])
def test_the_capability_check_refuses_only_what_the_cli_cannot_do(tmp_path, monkeypatch, outcome, code):
    monkeypatch.setattr(ClaudeCliProvider, "capabilities", Capabilities(outcome))
    qualify = release_checks.claude(tmp_path / "cli-profile-claude_cli")
    executable = tmp_path / "cli-runtime-claude_cli" / "2.1.318" / "bin/claude"
    if code is None:
        qualify(None, executable, "2.1.318", threading.Event())
        return
    with pytest.raises((InstallationFailure, SpikeError)) as failure:
        qualify(None, executable, "2.1.318", threading.Event())
    assert failure.value.code == code


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
async def test_settings_offers_a_newer_release_and_updates_a_connected_claude(binary, tmp_path):
    binary.offer("2.1.310", stand_in("# 2.1.310\n"))
    slot = claude_slot(tmp_path / "store")
    app = app_with(tmp_path, bind_stand_in(slot, slot.profile.executable))
    async with client_session(app) as client:
        await switch_to_claude(client)
        await client.post("/v1/host/install", json={"provider": "claude_cli"})
        (slot.installation.executable.parent / "fixture.json").write_text(json.dumps({"case": "valid", "value": {}}))
        assert (await client.post("/v1/host/status", json={"provider": "claude_cli"})).json()["state"] == "connected"
        binary.offer("2.1.318", stand_in("# 2.1.318\n"))
        slot.installation.found_at = None
        offered = (await client.post("/v1/host/release-check", json={"provider": "claude_cli"})).json()
        assert offered["state"] == "connected"
        assert {key: offered["installation"][key] for key in ("installed", "latest", "update")} == {
            "installed": "2.1.310", "latest": "2.1.318", "update": True}
        assert offered["providers"][1]["installation"]["update"] is True
        updated = (await client.post("/v1/host/install", json={"provider": "claude_cli"})).json()
        assert updated["state"] == "unchecked" and updated["installation"]["installed"] == "2.1.318"
        assert slot.installation.executable == slot.installation.root / "2.1.318" / "bin/claude"
        assert (await client.post("/v1/host/install", json={"provider": "claude_cli"})).status_code == 409


@pytest.mark.asyncio
async def test_a_release_check_needs_the_provider_on_and_starts_no_cli(binary, tmp_path, monkeypatch):
    slot = claude_slot(tmp_path / "store")
    looks = []
    monkeypatch.setattr(ClaudeInstallation, "lookup", lambda _self, _fetch: looks.append(1) or binary.current)
    async with client_session(app_with(tmp_path, bind_stand_in(slot, slot.profile.executable))) as client:
        refused = await client.post("/v1/host/release-check", json={"provider": "claude_cli"})
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "PROVIDER_INACTIVE"
        await client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
        found = (await client.post("/v1/host/release-check", json={"provider": "claude_cli"})).json()
        assert found["installation"]["latest"] == "2.1.318" and found["installation"]["update"] is False
        await client.post("/v1/host/release-check", json={"provider": "claude_cli"})
        assert looks == [1]
        assert (await client.get("/v1/host/release-check")).status_code == 405


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
