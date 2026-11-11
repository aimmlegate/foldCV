"""D158: the signed-in account in Settings, the sign-out (`/v1/host/logout`) and the clearing of a provider's data
(`/v1/host/clear-data`). The offline stand-ins run in profiles of the app's own under tmp_path; no real CLI or profile
is touched."""

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import threading

import pytest

from resume_api.app import ProviderSlot, create_app
from resume_api.lifecycle import OperationFiles
from resume_api.providers.base import ConnectionFailure, Quota, account_label
from resume_api.providers.claude.connection import ClaudeConnectionAdapter
from resume_api.providers.claude.content import ClaudeCliProvider, FixtureTransport
from resume_api.providers.claude import profile as claude_profile
from resume_api.providers.claude.profile import ClaudeCliProfile, ClaudeProfileError
from resume_api.providers.codex.connection import ConnectionAdapter
from resume_api.providers.codex import profile as codex_profile
from resume_api.providers.codex.profile import ExperimentalCliProfile, ExperimentalProfileError
from tests.settings.support import ORIGIN, SECRET, MetadataAdapter, application, client_session

FAKES = Path(__file__).resolve().parents[1] / "providers"
CATALOG = json.loads((Path(__file__).resolve().parents[2] / "contracts/error-messages.ru.json").read_text())
EMAIL, ORGANISATION, OTHER = "fictional@example.invalid", "Fictional Team", "second@example.invalid"
KINDS = ("claude_cli", "codex_cli")
SOURCES = {"claude_cli": ("fake_claude.py", "claude"), "codex_cli": ("fake_cli.py", "codex")}
PROFILES = {"claude_cli": "cli-profile-claude_cli", "codex_cli": "cli-experiment"}
RUNTIMES = {"claude_cli": "cli-runtime-claude_cli", "codex_cli": "cli-runtime"}
FOLDERS = {"claude_cli": ("claude", "cwd"), "codex_cli": ("home", "codex", "cwd")}
# The folder that holds the sign-in where it is a file: Claude's on Windows, CODEX_HOME.
SIGN_IN_FOLDERS = {"claude_cli": "claude", "codex_cli": "codex"}
MARKERS = {"claude_cli": claude_profile.MARKER, "codex_cli": codex_profile.MARKER}
LOGOUT = {"claude_cli": ["auth", "logout"], "codex_cli": ["logout"]}
LABELS = {"claude_cli": EMAIL + " · " + ORGANISATION, "codex_cli": EMAIL}


class StandIn:
    """One offline CLI in its own folder, with its fixture, its audit and its sign-in markers."""

    def __init__(self, tmp_path, kind):
        source, name = SOURCES[kind]
        self.kind, self.directory = kind, tmp_path / (name + " stand-in")
        self.directory.mkdir()
        self.cli = self.directory / name
        self.cli.write_text("#!" + sys.executable + "\n" + (FAKES / source).read_text().split("\n", 1)[1])
        self.cli.chmod(0o700)
        self.configure()

    def configure(self, case="valid", **extra):
        (self.directory / "fixture.json").write_text(json.dumps({"case": case, "value": {}, "prompt": "", **extra}))

    def runs(self, args):
        path = self.directory / "audit.jsonl"
        entries = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [entry for entry in entries if entry.get("args") == args]

    def logouts(self):
        """The profile folder each sign-out ran in: Claude's config directory, Codex's CODEX_HOME."""
        return [entry["config" if self.kind == "claude_cli" else "home"] for entry in self.runs(LOGOUT[self.kind])]


@pytest.fixture
def unconfined(monkeypatch):
    """The profiles launch the stand-ins with their own environment, without sandbox-exec (it would not let this Python
    run) and without the publisher check (no stand-in passes it)."""
    def claude(self, executable, args, operation, *, network=True):
        self.prepare()
        assert executable == self.executable
        return executable, args, self.environment(operation)

    def codex(self, executable, args, operation):
        self.prepare()
        assert executable == self.executable
        return executable, args, {"PATH": os.defpath, "HOME": str(self.home), "CODEX_HOME": str(self.codex_home),
                                  "TMPDIR": str(operation / "tmp")}
    monkeypatch.setattr(ClaudeCliProfile, "launch", claude)
    monkeypatch.setattr(ClaudeCliProfile, "check_binary", lambda _self: None)
    monkeypatch.setattr(ExperimentalCliProfile, "launch", codex)
    monkeypatch.setattr(ExperimentalCliProfile, "check_binary", lambda _self: None)


def app_for(tmp_path, stand_in, *, own=True):
    """The app with the stand-in as its provider, in a profile of the app's own unless `own` is false; then the CLI
    would run with the user's HOME."""
    root = tmp_path / "profiles" / PROFILES[stand_in.kind]
    if stand_in.kind == "claude_cli":
        if own:
            profile = ClaudeCliProfile(root, stand_in.cli, home=tmp_path / "home")
            slot = ProviderSlot(ClaudeConnectionAdapter(profile), ClaudeCliProvider(stand_in.cli, profile=profile), profile)
        else:
            profile, slot = None, ProviderSlot(ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(stand_in.cli)))
        return application(tmp_path, MetadataAdapter(), provider_slots={"claude_cli": slot}), profile
    profile = ExperimentalCliProfile(root, stand_in.cli) if own else None
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("fixture")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
                      data_root=tmp_path / "store", connection_adapter=ConnectionAdapter(stand_in.cli,
                                                                                         experimental_profile=profile),
                      experimental_profile=profile), profile


def host_of(app):
    return next(route.endpoint.__self__ for route in app.app.routes if getattr(route, "path", "") == "/v1/host/status")


def entry(reply, kind):
    return next(item for item in reply["providers"] if item["kind"] == kind)


async def post(client, path, kind, **body):
    return await client.post("/v1/host/" + path, json={"provider": kind, **body})


async def connect(client, kind):
    if kind == "claude_cli":
        await post(client, "enable", kind, enabled=True)
    reply = (await post(client, "status", kind)).json()
    assert reply["state"] == "connected", reply["state"]
    return reply


def sign_ins(tmp_path):
    path = tmp_path / "store" / "logs" / "sign-in.log"
    return path.read_text() if path.exists() else ""


def refused(reply, code):
    assert reply.status_code == 409 and reply.json()["error"]["code"] == code, reply.text
    # The card shows the catalog's plain Russian text for the code.
    assert "А" <= CATALOG["messages"][CATALOG["codes"][code]][0] <= "я"


@pytest.mark.parametrize(("email", "organisation", "label"), [
    (EMAIL, ORGANISATION, EMAIL + " · " + ORGANISATION), (EMAIL, EMAIL + "'s Organization", EMAIL),
    (EMAIL, None, EMAIL), (None, ORGANISATION, ORGANISATION), (" " + EMAIL + " ", "", EMAIL),
    ("fictional\n@example.invalid", None, None), ("x" * 255, ORGANISATION, ORGANISATION), (7, ["a"], None),
    (None, None, None),
])
def test_the_account_label_takes_only_values_it_can_show(email, organisation, label):
    assert account_label(email, organisation) == label


@pytest.mark.asyncio
async def test_a_sign_in_drops_the_snapshot_that_imports_and_api_errors_keep(tmp_path, unconfined):
    # R4 of D158 keeps the CLI's qualification while an import runs and through an overloaded reply, not a sign-in.
    stand_in = StandIn(tmp_path, "claude_cli")
    stand_in.configure("logged_out")
    app, _profile = app_for(tmp_path, stand_in)
    cache = host_of(app).slots["claude_cli"].provider.preflight_cache
    async with client_session(app) as client:
        await post(client, "enable", "claude_cli", enabled=True)
        assert (await post(client, "status", "claude_cli")).json()["state"] == "login_required"
        cache.remember(cache.epoch, ("synthetic",), object(), ("claude-sonnet-5-5",))
        reply = await post(client, "login", "claude_cli")
        assert reply.status_code == 200, reply.text
        assert cache.snapshot is None and len(stand_in.runs(["auth", "login", "--claudeai"])) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_a_sign_out_ends_the_apps_own_sign_in_and_another_account_signs_in(tmp_path, unconfined, caplog, kind):
    caplog.set_level(logging.INFO, logger="foldcv")
    stand_in = StandIn(tmp_path, kind)
    app, profile = app_for(tmp_path, stand_in)
    cache = host_of(app).slots[kind].provider.preflight_cache
    async with client_session(app) as client:
        connected = await connect(client, kind)
        assert entry(connected, kind)["account"] == LABELS[kind] and entry(connected, kind)["ownProfile"] is True
        models = entry(connected, kind)["models"]
        assert models and set(models) <= set(connected["models"])
        cache.remember(cache.epoch, ("synthetic",), object(), tuple(models))
        reply = await post(client, "logout", kind)
        assert reply.status_code == 200, reply.text
        state = entry(reply.json(), kind)
        assert state["state"] == "login_required" and state["account"] is None and state["models"] == []
        assert state["metadataReady"] is False and state["quota"]["state"] == "unknown"
        assert not set(models) & set(reply.json()["models"]) and cache.snapshot is None
        assert entry((await client.get("/v1/settings/connection")).json(), kind)["account"] is None
        # Only the profile's own sign-in went: the command ran in its folder, never with the user's own.
        assert stand_in.logouts() == [str(profile.config_dir if kind == "claude_cli" else profile.codex_home)]
        stand_in.configure(login_email=OTHER)
        assert (await post(client, "login", kind)).json()["state"] == "login_required"
        again = (await post(client, "status", kind)).json()
        assert again["state"] == "connected" and entry(again, kind)["account"] == LABELS[kind].replace(EMAIL, OTHER)
    log = sign_ins(tmp_path)
    assert f"{kind} sign-out: OK" in log and "page address found" not in log.split("sign-out: OK")[1].split("\n\n")[0]
    lines = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("foldcv"))
    assert f"logout {kind}: done in " in lines
    # The account label stays out of the app log.
    assert EMAIL not in lines and OTHER not in lines and ORGANISATION not in lines


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(("case", "code"), [("logout_fails", "SIGN_OUT_FAILED"), ("no_logout", "SIGN_OUT_UNSUPPORTED"),
                                            ("logout_ignored", "SIGN_OUT_FAILED")])
async def test_a_sign_out_the_cli_refuses_says_so_and_keeps_what_the_status_names(tmp_path, unconfined, kind, case, code):
    stand_in = StandIn(tmp_path, kind)
    app, _profile = app_for(tmp_path, stand_in)
    async with client_session(app) as client:
        await connect(client, kind)
        stand_in.configure(case)
        refused(await post(client, "logout", kind), code)
        state = entry((await client.get("/v1/settings/connection")).json(), kind)
        assert state["state"] == "connected" and state["account"] == LABELS[kind] and state["metadataReady"] is True
    # A CLI that does not list the command never gets it: Codex would take the word as a prompt.
    assert len(stand_in.runs(LOGOUT[kind])) == (0 if case == "no_logout" else 1)
    log = sign_ins(tmp_path)
    assert f"{kind} sign-out: {code}" in log
    if case == "logout_fails":
        assert "synthetic" in log.split(f"sign-out: {code}")[1]


@pytest.mark.asyncio
async def test_a_sign_out_and_a_clearing_drop_the_window_claudes_calls_sent(tmp_path, unconfined):
    # T9: the reading belongs to the account that signed out; the next account starts without one.
    stand_in = StandIn(tmp_path, "claude_cli")
    app, _profile = app_for(tmp_path, stand_in)
    read = host_of(app).slots["claude_cli"].provider.quota_read
    none = {"state": "not_provided", "usedPercent": None, "resetsAt": None, "readAt": None}

    async def sign_in_again(client):
        stand_in.configure(login_email=OTHER)
        await post(client, "login", "claude_cli")
        reply = (await post(client, "status", "claude_cli")).json()
        assert reply["state"] == "connected"
        return entry(reply, "claude_cli")["quota"]

    async with client_session(app) as client:
        await connect(client, "claude_cli")
        read(Quota("exhausted", 100.0, 1800000000))
        assert entry((await client.get("/v1/settings/connection")).json(), "claude_cli")["quota"]["usedPercent"] == 100
        assert (await post(client, "logout", "claude_cli")).status_code == 200
        assert await sign_in_again(client) == none
        assert (await post(client, "logout", "claude_cli")).status_code == 200
        # A reading kept while signed out goes with the clearing.
        read(Quota("available", 40.0, 1800000000))
        assert (await post(client, "clear-data", "claude_cli")).status_code == 200
        assert await sign_in_again(client) == none
        # So does one whose account a check finds gone, signed out outside the app.
        read(Quota("available", 40.0, 1800000000))
        (stand_in.directory / "signed-out").touch()
        assert (await post(client, "status", "claude_cli")).json()["state"] == "login_required"
        assert await sign_in_again(client) == none


@pytest.mark.asyncio
async def test_a_check_beside_a_running_sign_out_starts_nothing(tmp_path, unconfined):
    stand_in = StandIn(tmp_path, "claude_cli")
    app, _profile = app_for(tmp_path, stand_in)
    async with client_session(app) as client:
        await connect(client, "claude_cli")
        stand_in.configure("slow_logout")
        leaving = asyncio.create_task(post(client, "logout", "claude_cli"))
        for _ in range(500):
            if (stand_in.directory / "logout_ready").exists():
                break
            await asyncio.sleep(0.01)
        checks = len(stand_in.runs(["auth", "status", "--json"]))
        check = await post(client, "status", "claude_cli")
        assert check.status_code == 200 and check.json()["state"] == "unchecked"
        assert len(stand_in.runs(["auth", "status", "--json"])) == checks
        second = await post(client, "logout", "claude_cli")
        assert second.status_code == 429 and second.json()["error"]["code"] == "BUSY"
        assert (await post(client, "clear-data", "claude_cli")).status_code == 429
        (stand_in.directory / "logout_release").touch()
        assert (await leaving).json()["state"] == "login_required"
    assert len(stand_in.runs(["auth", "logout"])) == 1


def test_a_sign_out_during_an_import_stops_it_as_a_detach_and_the_project_reopens(tmp_path, unconfined):
    from tests.projects.support import Editor, v2_app
    from tests.projects.test_import_task import PROJECT, HoldingPipeline, papers, start, status
    stand_in = StandIn(tmp_path, "claude_cli")
    profile = ClaudeCliProfile(tmp_path / "profiles" / PROFILES["claude_cli"], stand_in.cli, home=tmp_path / "home")
    slot = ProviderSlot(ClaudeConnectionAdapter(profile), ClaudeCliProvider(stand_in.cli, profile=profile), profile)
    with v2_app(tmp_path, [papers()], provider_slots={"claude_cli": slot}) as (client, application):
        service = application.state.projects
        service.imports.pipeline, service.imports.commands = HoldingPipeline(), None
        client.post("/v1/host/enable", json={"provider": "claude_cli", "enabled": True})
        assert client.post("/v1/host/status", json={"provider": "claude_cli"}).json()["providers"][1]["state"] == "connected"
        task_id = start(client, "request-1").json()["id"]
        reply = client.post("/v1/host/logout", json={"provider": "claude_cli"})
        assert reply.status_code == 200 and reply.json()["providers"][1]["state"] == "login_required"
        assert status(client, task_id)["state"] == "cancelled" and not service.imports.runners
        assert Editor(client, PROJECT).token
    assert len(stand_in.runs(["auth", "logout"])) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_clearing_follows_a_confirmed_sign_out_and_keeps_the_root_and_the_runtime(tmp_path, unconfined, kind):
    stand_in = StandIn(tmp_path, kind)
    app, profile = app_for(tmp_path, stand_in)
    runtime = tmp_path / "profiles" / RUNTIMES[kind] / "release.json"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("synthetic runtime")
    async with client_session(app) as client:
        await connect(client, kind)
        sessions = profile.root / SIGN_IN_FOLDERS[kind] / "sessions.jsonl"
        sessions.write_text("synthetic session")
        refused(await post(client, "clear-data", kind), "SIGN_OUT_REQUIRED")
        assert sessions.read_text() == "synthetic session"
        assert (await post(client, "logout", kind)).status_code == 200
        # The status said signed out, then the account came back outside the app: the clearing checks again.
        (stand_in.directory / "signed-out").unlink()
        refused(await post(client, "clear-data", kind), "SIGN_OUT_REQUIRED")
        assert sessions.read_text() == "synthetic session"
        assert (await post(client, "logout", kind)).status_code == 200
        lock = (profile.root / ".foldcv-inference.lock").stat().st_ino
        cleared = await post(client, "clear-data", kind)
        assert cleared.status_code == 200 and entry(cleared.json(), kind)["state"] == "login_required"
        assert not sessions.exists() and all((profile.root / name).is_dir() for name in FOLDERS[kind])
        assert (profile.root / ".foldcv-inference.lock").stat().st_ino == lock
        assert sorted(path.name for path in profile.root.iterdir() if path.is_file()) == sorted(
            [".foldcv-inference.lock", MARKERS[kind]])
        assert runtime.read_text() == "synthetic runtime"
        assert entry((await post(client, "status", kind)).json(), kind)["state"] == "login_required"
        stand_in.configure(login_email=OTHER)
        await post(client, "login", kind)
        assert entry((await post(client, "status", kind)).json(), kind)["state"] == "connected"
    assert f"{kind} clearing: SIGN_OUT_REQUIRED" in sign_ins(tmp_path)
    assert f"{kind} clearing: OK" in sign_ins(tmp_path) and "cleared: " + ", ".join(FOLDERS[kind]) in sign_ins(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_a_provider_without_a_profile_of_its_own_refuses_both_on_the_server(tmp_path, kind):
    stand_in = StandIn(tmp_path, kind)
    app, _profile = app_for(tmp_path, stand_in, own=False)
    async with client_session(app) as client:
        if kind == "claude_cli":
            await post(client, "enable", kind, enabled=True)
        status = (await post(client, "status", kind)).json()
        assert entry(status, kind)["ownProfile"] is False
        for path in ("logout", "clear-data"):
            refused(await post(client, path, kind), "SIGN_OUT_NOT_AVAILABLE")
        assert entry((await client.get("/v1/settings/connection")).json(), kind)["state"] == status["state"]
    assert stand_in.runs(LOGOUT[kind]) == [] and sign_ins(tmp_path) == ""


def test_codex_without_the_apps_profile_never_runs_its_sign_out(tmp_path):
    stand_in = StandIn(tmp_path, "codex_cli")
    with pytest.raises(ConnectionFailure, match="SIGN_OUT_NOT_AVAILABLE"):
        with OperationFiles(tmp_path / "operations").open() as files:
            ConnectionAdapter(stand_in.cli).logout(files, threading.Event())
    assert not (stand_in.directory / "audit.jsonl").exists()


def profile_of(kind, tmp_path, monkeypatch):
    root = tmp_path / "profiles" / PROFILES[kind]
    if kind == "claude_cli":
        return ClaudeCliProfile(root, tmp_path / "claude", home=tmp_path / "home")
    monkeypatch.setattr(ExperimentalCliProfile, "check_binary", lambda _self: None)
    return ExperimentalCliProfile(root, tmp_path / "codex")


@pytest.mark.parametrize("kind", KINDS)
def test_clear_removes_only_the_clis_own_folders(tmp_path, monkeypatch, kind):
    profile = profile_of(kind, tmp_path, monkeypatch)
    profile.prepare()
    kept = {name: "synthetic" for name in (".foldcv-inference.lock", ".foldcv-inference-blocked",
                                           ".foldcv-shared-server-v1", "unknown-file")}
    for name, text in kept.items():
        (profile.root / name).write_text(text)
    for name in FOLDERS[kind]:
        (profile.root / name / "nested").mkdir(parents=True, exist_ok=True)
        (profile.root / name / "nested" / "file.json").write_text("synthetic")
    runtime = tmp_path / "profiles" / RUNTIMES[kind]
    runtime.mkdir()
    (runtime / "release.json").write_text("synthetic")
    assert sorted(profile.clear()) == sorted(FOLDERS[kind])
    assert not any((profile.root / name).exists() for name in FOLDERS[kind])
    assert all((profile.root / name).read_text() == text for name, text in kept.items())
    assert (profile.root / MARKERS[kind]).is_file() and (runtime / "release.json").is_file()
    profile.prepare()
    assert all((profile.root / name).is_dir() for name in FOLDERS[kind])


@pytest.mark.parametrize("kind", KINDS)
def test_clear_refuses_a_linked_folder_or_a_foreign_root_and_removes_nothing(tmp_path, monkeypatch, kind):
    profile = profile_of(kind, tmp_path, monkeypatch)
    error = ClaudeProfileError if kind == "claude_cli" else ExperimentalProfileError
    profile.prepare()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "own.txt").write_text("synthetic")
    first, *_rest, last = FOLDERS[kind]
    (profile.root / first / "file.json").write_text("synthetic")
    (profile.root / last).rmdir()
    (profile.root / last).symlink_to(outside, target_is_directory=True)
    with pytest.raises(error):
        profile.clear()
    assert (outside / "own.txt").is_file() and (profile.root / first / "file.json").is_file()
    foreign = profile_of(kind, tmp_path / "foreign", monkeypatch)
    foreign.root.mkdir(parents=True, mode=0o700)
    (foreign.root / first).mkdir()
    with pytest.raises(error):
        foreign.clear()
    assert (foreign.root / first).is_dir()
