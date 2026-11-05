"""Installation changes only owned runtime files and never starts inference."""

import asyncio
from contextlib import contextmanager
import hashlib
import gzip
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import threading

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from resume_api import release_checks
from resume_api.app import create_app
from resume_api.cli import distribution as release
from resume_api.cli.experimental_profile import ExperimentalCliProfile, ExperimentalProfileError, installed_profile
from resume_api.cli.installation import CliInstallation, InstallationFailure, MARKER
from resume_api.cli.releases import Release
from resume_api.connection import ConnectionAdapter
from resume_api.providers.base import Metadata, Quota
from resume_api.lifecycle import OperationFiles
from tests.settings.test_providers import running_rewrite

ORIGIN = "http://127.0.0.1:39281"
SECRET = "synthetic-cli-installation-0123456789"


VERSION = "0.166.0"


def manifest(version=VERSION, **changes):
    return (json.dumps({"layoutVersion": 1, "version": version, "target": release.TARGET, "variant": "codex",
                        "entrypoint": release.CLI, **changes}) + "\n").encode()


def write_package(archive, payloads):
    with tarfile.open(archive, "w:gz") as target:
        for name, value in payloads.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            member.mode = 0o755 if name.startswith("bin/") else 0o644
            target.addfile(member, io.BytesIO(value))


class Listing:
    """GitHub's latest release, served from a local archive; `publish` replaces it."""

    def __init__(self, archive):
        self.archive = archive
        self.current = None

    def publish(self, payloads, version=VERSION):
        write_package(self.archive, payloads)
        self.current = Release(version, release.DOWNLOAD_URL + "rust-v" + version + "/" + release.package_name(),
                               self.archive.stat().st_size, hashlib.sha256(self.archive.read_bytes()).hexdigest())


@pytest.fixture
def package(tmp_path, monkeypatch):
    """A synthetic package published as the newest release; its signature and capability checks are tested on their
    own."""
    payloads = {release.CLI: b"synthetic-codex", release.HOST: b"synthetic-host",
                release.PACKAGE_MANIFEST: manifest()}
    listing = Listing(tmp_path / "source.tar.gz")
    listing.publish(payloads)
    monkeypatch.setattr(CliInstallation, "lookup", lambda _self, _fetch: listing.current)
    monkeypatch.setattr(CliInstallation, "download",
                        lambda _self, _files, destination, _release: shutil.copyfile(listing.archive, destination))
    monkeypatch.setattr(CliInstallation, "publisher", lambda _self, _package: None)
    monkeypatch.setattr(release_checks, "codex", lambda _root: None)
    return listing.archive, payloads, listing


def install(installer, tmp_path):
    with OperationFiles(tmp_path / "operations").open() as files:
        return installer.install(files)


def test_verified_install_and_restart_preserve_existing_profile(package, tmp_path):
    installer = CliInstallation(tmp_path / "cli-runtime")
    profile = tmp_path / "cli-experiment"
    profile.mkdir(mode=0o700)
    sentinel = profile / "existing-credential-marker"
    sentinel.write_bytes(b"keep-existing-profile")
    assert not installer.root.exists()
    assert install(installer, tmp_path) == installer.executable
    assert installer.executable.read_bytes() == package[1]["bin/codex"]
    assert installer.snapshot()["state"] == "ready"
    assert installer.executable.stat().st_mode & 0o777 == 0o700
    assert installed_profile(profile).executable == installer.executable
    assert sentinel.read_bytes() == b"keep-existing-profile"
    assert not list((tmp_path / "operations").iterdir())
    assert not list(installer.root.glob(".staging-*"))


@pytest.mark.parametrize("damage", ["checksum", "truncated", "network", "cancelled"])
def test_failed_download_keeps_previous_runtime(package, tmp_path, monkeypatch, damage):
    installer = CliInstallation(tmp_path / "cli-runtime")
    assert install(installer, tmp_path)
    original = installer.executable.read_bytes()
    if damage == "checksum":
        listing = package[2]
        listing.current = Release(VERSION, listing.current.url, listing.current.size, "0" * 64)
    elif damage == "truncated":
        package[0].write_bytes(b"truncated")
    elif damage == "network":
        def fail(*_args):
            raise InstallationFailure("download_failed")
        monkeypatch.setattr(installer, "download", fail)
    else:
        installer.cancel.set()
    assert install(installer, tmp_path) is None
    assert installer.snapshot()["state"] == ("cancelled" if damage == "cancelled" else "failed")
    assert installer.executable.read_bytes() == original
    assert not list((tmp_path / "operations").iterdir())


@pytest.mark.parametrize("kind", ["traversal", "absolute", "symlink", "hardlink", "device", "duplicate", "large"])
def test_unsafe_archives_cannot_write_outside_staging(tmp_path, kind):
    archive = tmp_path / "unsafe.tar.gz"
    member = tarfile.TarInfo("../escape" if kind == "traversal" else "/escape" if kind == "absolute" else "bin/codex")
    if kind in {"symlink", "hardlink"}:
        member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
        member.linkname = "../../escape"
    elif kind == "device":
        member.type = tarfile.CHRTYPE
    elif kind == "large":
        member.size = 400_000_001
    if kind == "large":
        with gzip.open(archive, "wb") as target:
            target.write(member.tobuf() + b"\0" * 1024)
    else:
        with tarfile.open(archive, "w:gz") as target:
            target.addfile(member)
            if kind == "duplicate":
                target.addfile(member)
    staging = tmp_path / "staging"
    staging.mkdir()
    with pytest.raises((InstallationFailure, tarfile.TarError)):
        CliInstallation(tmp_path / "runtime").unpack(archive, staging)
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("kind", ["foreign", "symlink", "bad_marker", "lock_symlink"])
def test_install_rejects_unowned_paths(package, tmp_path, kind):
    root = tmp_path / "runtime"
    if kind == "symlink":
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        root.symlink_to(target)
    else:
        root.mkdir(mode=0o700)
        if kind != "foreign":
            (root / MARKER).write_text("invalid\n" if kind == "bad_marker" else "foldcv-cli-runtime-v1\n")
        if kind == "lock_symlink":
            (root / ".install.lock").symlink_to(tmp_path / "untouched")
    installer = CliInstallation(root)
    assert install(installer, tmp_path) is None
    assert not installer.executable.exists()
    assert not (tmp_path / "untouched").exists()


def test_second_installer_is_blocked_by_process_lock(package, tmp_path):
    first = CliInstallation(tmp_path / "runtime")
    second = CliInstallation(first.root)
    with first.owned():
        assert install(second, tmp_path) is None
    assert second.snapshot()["error"] == "busy"


@pytest.mark.parametrize("stage", ["verifying", "extracting"])
def test_cancel_during_verification_or_extraction_keeps_previous(package, tmp_path, monkeypatch, stage):
    installer = CliInstallation(tmp_path / "runtime")
    assert install(installer, tmp_path)
    original = installer.executable.read_bytes()
    update = installer.update
    def cancel_on_stage(**values):
        update(**values)
        if values.get("state") == stage:
            installer.cancel.set()
    monkeypatch.setattr(installer, "update", cancel_on_stage)
    assert install(installer, tmp_path) is None
    assert installer.snapshot()["state"] == "cancelled"
    assert installer.executable.read_bytes() == original


@pytest.mark.parametrize("change", [{"version": "0.165.0"}, {"variant": "codex-provisioned"}, {"target": "x86_64-unknown-linux-musl"},
                                    {"entrypoint": "bin/other"}, {"host": None}, {"record": True}])
def test_package_failure_and_publish_failure_preserve_previous(package, tmp_path, monkeypatch, change):
    installer = CliInstallation(tmp_path / "runtime")
    assert install(installer, tmp_path)
    original = installer.executable.read_bytes()
    _archive, payloads, listing = package
    broken = dict(payloads)
    if "host" in change:
        del broken[release.HOST]
    elif "record" in change:
        # A package may not bring FoldCV's record of itself.
        broken["foldcv-release.json"] = b"{}"
    else:
        broken[release.PACKAGE_MANIFEST] = manifest(**change)
    listing.publish(broken)
    assert install(installer, tmp_path) is None
    assert installer.snapshot()["error"] == "invalid_package"
    assert installer.executable.read_bytes() == original
    listing.publish(payloads)
    rename = Path.rename
    def fail_staging(path, target):
        if path.name.startswith(".staging-"):
            raise OSError("synthetic rename failure")
        return rename(path, target)
    monkeypatch.setattr(Path, "rename", fail_staging)
    assert install(installer, tmp_path) is None
    assert installer.executable.read_bytes() == original
    assert not list(installer.root.glob(".previous-*"))


def test_relocated_agent_uses_the_pinned_local_companion(package, tmp_path, monkeypatch):
    from resume_api.agent.profile import AgentProfile
    from resume_api.agent import host_profile as agent

    installer = CliInstallation(tmp_path / "cli-runtime")
    assert install(installer, tmp_path)
    agent.check_host(installer.executable.parent.parent, managed=True)
    current = ExperimentalCliProfile(tmp_path / "profile", installer.executable)
    adapter = ConnectionAdapter(current.executable, experimental_profile=current)
    relocated = AgentProfile.from_connection(adapter)
    assert relocated.managed
    assert relocated.host_path == installer.executable.parent / "codex-code-mode-host"
    policy = relocated._policy(tmp_path, agent.APP_SERVER_PREFIX)
    assert '(allow process-exec (literal "' + str(relocated.host_path) + '"))' in policy
    assert str(agent.CODE_MODE_HOST) not in policy
    relocated.host_path.write_bytes(b"changed-host")
    with pytest.raises(ExperimentalProfileError, match="AGENT_CODE_MODE_HOST_UNSUPPORTED"):
        agent.check_host(installer.executable.parent.parent, managed=True)


class InstalledMetadata(ConnectionAdapter):
    def inspect(self, files, cancel, *, full=True):
        if not self.executable.is_file():
            from resume_api.providers.base import ConnectionFailure
            raise ConnectionFailure("CLI_MISSING")
        return Metadata("codex-cli " + VERSION, ("gpt-6-luna",), "plus", Quota("available", 25, 1800000000))


def make_app(tmp_path):
    root = tmp_path / "store"
    profile = ExperimentalCliProfile(root / "cli-experiment", release.managed_executable(root / "cli-runtime"))
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("fixture")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
        data_root=root, experimental_profile=profile,
        connection_adapter=InstalledMetadata(profile.executable, experimental_profile=profile))


async def post(client, path):
    return await client.post("/v1/host/" + path, headers={"Origin": ORIGIN}, json={})


@pytest.mark.asyncio
async def test_install_routes_require_session_and_connect_without_restart(package, tmp_path):
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await post(client, "install")).status_code == 401
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await client.post("/v1/host/install", headers={"Origin": "http://evil.invalid"}, json={})).status_code == 403
        assert (await client.post("/v1/host/install", headers={"Origin": ORIGIN}, json={"url": "https://evil.invalid"})).status_code == 422
        assert (await post(client, "status")).json()["state"] == "cli_missing"
        result = (await post(client, "install")).json()
        assert result["installation"]["state"] == "ready" and result["state"] == "unchecked"
        assert (await post(client, "status")).json()["state"] == "connected"
        assert (await post(client, "install")).status_code == 409
        assert (await post(client, "cancel-install")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel-install", "detach"])
async def test_cancellation_stops_download_and_discards_late_completion(package, tmp_path, monkeypatch, action):
    started = threading.Event()
    def wait_for_cancel(installer, files, archive, _release):
        started.set()
        assert installer.cancel.wait(3)
        installer.check_cancel()
    monkeypatch.setattr(CliInstallation, "download", wait_for_cancel)
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        await post(client, "status")
        pending = asyncio.create_task(post(client, "install"))
        assert await asyncio.to_thread(started.wait, 2)
        assert (await post(client, "install")).status_code == 429
        assert (await client.get("/v1/settings/connection")).json()["installation"]["state"] == "downloading"
        cancelled = (await post(client, action)).json()
        assert cancelled["installation"]["state"] == "cancelled"
        assert (await pending).json()["state"] == ("detached" if action == "detach" else "cli_missing")
        assert not release.managed_executable(tmp_path / "store/cli-runtime").exists()


@pytest.mark.asyncio
async def test_cancel_before_download_starts_has_a_terminal_state(package, tmp_path, monkeypatch):
    from resume_api.inference_admission import AdmissionCancelled, INFERENCE
    started = threading.Event()
    @contextmanager
    def held(cancel, **_options):
        started.set()
        assert cancel.wait(3)
        raise AdmissionCancelled()
        yield
    monkeypatch.setattr(INFERENCE, "hold", held)
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        await post(client, "status")
        pending = asyncio.create_task(post(client, "install"))
        assert await asyncio.to_thread(started.wait, 2)
        assert (await post(client, "cancel-install")).json()["installation"]["state"] == "cancelled"
        assert (await pending).json()["installation"]["state"] == "cancelled"


@pytest.mark.asyncio
async def test_install_stops_model_work_and_then_takes_the_permit(package, tmp_path):
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        assert (await post(client, "status")).json()["state"] == "cli_missing"
        with running_rewrite(app) as cancel:
            reply = await post(client, "install")
            assert reply.status_code == 200 and cancel.is_set()
        assert reply.json()["installation"]["state"] == "ready"


@pytest.mark.asyncio
async def test_changed_installed_binary_offers_install_again(package, tmp_path):
    app = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post("/v1/session/exchange", headers={"Origin": ORIGIN}, json={"secret": SECRET})
        await post(client, "status")
        await post(client, "install")
        binary = release.managed_executable(tmp_path / "store/cli-runtime")
        binary.write_bytes(b"changed-runtime")
        status = (await post(client, "status")).json()
        assert status["state"] == "unsupported_version" and status["installation"]["available"]
        assert (await post(client, "install")).json()["installation"]["state"] == "ready"
        assert binary.read_bytes() == package[1]["bin/codex"]


def test_discovery_rechecks_path_after_external_install(tmp_path, monkeypatch):
    selected = [None]
    monkeypatch.setattr("resume_api.connection.shutil.which", lambda _: selected[0])
    adapter = ConnectionAdapter()
    cli = tmp_path / "codex"
    cli.write_bytes(b"native binary fixture")
    selected[0] = str(cli)
    assert adapter._launcher() == (cli, ())


def test_a_newer_codex_release_replaces_the_installed_package(package, tmp_path):
    _archive, payloads, listing = package
    listing.publish({**payloads, release.PACKAGE_MANIFEST: manifest("0.165.0")}, "0.165.0")
    installer = CliInstallation(tmp_path / "cli-runtime")
    assert install(installer, tmp_path) == installer.root / "0.165.0" / release.CLI
    newer = {**payloads, release.CLI: b"synthetic-codex 0.166.0"}
    listing.publish(newer)
    installer.found_at = None
    with OperationFiles(tmp_path / "operations").open() as files:
        installer.check(files, threading.Event())
    assert (installer.snapshot()["installed"], installer.snapshot()["latest"], installer.snapshot()["update"]) == (
        "0.165.0", VERSION, True)
    assert install(installer, tmp_path) == installer.root / VERSION / release.CLI
    assert installer.executable.read_bytes() == newer[release.CLI]
    assert not (installer.root / "0.165.0").exists()
    profile = ExperimentalCliProfile(tmp_path / "cli-profile", installer.executable)
    assert profile.managed
    profile.check_binary()


def test_the_package_pinned_before_updates_still_counts(tmp_path, monkeypatch):
    runtime = tmp_path / "cli-runtime"
    payloads = {release.CLI: b"pinned codex", release.HOST: b"pinned host", release.PACKAGE_MANIFEST: b"{}"}
    for name, value in payloads.items():
        path = runtime / release.RELEASE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    (runtime / release.RELEASE / release.CLI).chmod(0o700)
    for attribute, name in (("CLI_SHA256", release.CLI), ("HOST_SHA256", release.HOST),
                            ("MANIFEST_SHA256", release.PACKAGE_MANIFEST)):
        monkeypatch.setattr(release, attribute, hashlib.sha256(payloads[name]).hexdigest())
    installer = CliInstallation(runtime)
    assert installer.installed() == release.RELEASE and installer.executable == runtime / release.RELEASE / release.CLI
    assert installed_profile(tmp_path / "cli-profile", managed_only=True).managed


def test_on_macos_the_package_must_carry_openais_signature(tmp_path, monkeypatch):
    from resume_api.cli import qualification
    from resume_api.cli.profile import HOST_IDENTIFIER, IDENTIFIER, TEAM_ID
    signed = []

    def publisher(path, team, identifier):
        signed.append((path.name, team, identifier))
        if path.name.startswith("codex-code-mode-host"):
            raise qualification.QualificationError("CLI_UNSUPPORTED")
    monkeypatch.setattr("resume_api.cli.installation.require_publisher", publisher)
    monkeypatch.setattr("resume_api.cli.installation.host.WINDOWS", False)
    with pytest.raises(InstallationFailure, match="invalid_package"):
        CliInstallation(tmp_path / "runtime").publisher(tmp_path / "package")
    assert signed == [(Path(release.CLI).name, TEAM_ID, IDENTIFIER), (Path(release.HOST).name, TEAM_ID, HOST_IDENTIFIER)]


@pytest.mark.parametrize(("failure", "code"), [
    (None, None), ("banner", "incompatible_release"), ("UNSUPPORTED_VERSION", "incompatible_release"),
    ("CLI_FAILED", "incompatible_release"), ("CANCELLED", "cancelled"), ("DEADLINE_EXCEEDED", "install_failed"),
    ("CLI_PROFILE_UNSAFE", "install_failed"),
])
def test_the_codex_capability_check_refuses_only_what_the_cli_cannot_do(tmp_path, monkeypatch, failure, code):
    from resume_api.providers.base import ConnectionFailure
    checked = []

    def version(_adapter, _files, _cancel, _deadline):
        if failure not in {None, "banner"}:
            raise ConnectionFailure(failure)
        return "codex-cli 0.165.0" if failure == "banner" else "codex-cli " + VERSION
    monkeypatch.setattr(ConnectionAdapter, "version", version)
    monkeypatch.setattr(ConnectionAdapter, "check_profile", lambda *_args: checked.append("profile"))
    monkeypatch.setattr(release_checks, "check_host", lambda package, managed: checked.append(("host", managed)))
    qualify = release_checks.codex(tmp_path / "cli-profile")
    executable = tmp_path / "cli-runtime" / VERSION / release.CLI
    if code is None:
        qualify(None, executable, VERSION, threading.Event())
        assert checked == ["profile", ("host", True)]
        return
    with pytest.raises(InstallationFailure) as raised:
        qualify(None, executable, VERSION, threading.Event())
    assert raised.value.code == code
