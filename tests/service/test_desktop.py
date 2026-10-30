"""The desktop app's service entry (`resume_api.desktop`), its CLI trust and the frozen helper's worker modes.

The live service runs in a child process; curl talks to it outside the Python socket guard."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest

from resume_api import desktop, launcher, lifecycle
from resume_api.cli import distribution, experimental_profile
from resume_api.cli.experimental_profile import ExperimentalCliProfile, ExperimentalProfileError
from resume_api.cli.installation import ClaudeInstallation, curl as system_curl
from resume_api.cli.profiles import claude

ROOT = Path(__file__).resolve().parents[2]


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    return root


def curl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(system_curl()), "--silent", "--show-error", "--max-time", "5", *args],
                          text=True, capture_output=True, timeout=10)


def test_workers_run_their_scripts_from_source_and_helper_modes_when_frozen(monkeypatch):
    utf8 = ("-X", "utf8") if lifecycle.host.WINDOWS else ()
    assert lifecycle.python_worker("extract", "/w/worker.py") == (Path(sys.executable), (*utf8, "/w/worker.py"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert lifecycle.python_worker("public-fetch", "-m", "resume_api.agent.web") == (Path(sys.executable),
                                                                                     ("public-fetch",))


@pytest.mark.parametrize("arguments", [[], ["nope"], ["extract", "extra"], ["serve"], ["serve", "relative/root"]])
def test_the_helper_refuses_unknown_modes_and_arguments(arguments):
    result = subprocess.run([sys.executable, "packaging/helper_entry.py", *arguments], cwd=ROOT,
                            capture_output=True, timeout=60)
    assert result.returncode == 64


def test_the_service_keeps_the_last_port_while_it_is_free(tmp_path):
    root = private_root(tmp_path)
    (root / desktop.PORT_FILE).write_text("80\n")
    with desktop.listen(root) as first:
        port = first.getsockname()[1]
    assert port != 80 and (root / desktop.PORT_FILE).read_text() == f"{port}\n"
    with desktop.listen(root) as second:
        assert second.getsockname()[1] == port
        # A taken port moves the service to another one, saved for the next start.
        with desktop.listen(root) as third:
            moved = third.getsockname()[1]
    assert moved != port and (root / desktop.PORT_FILE).read_text() == f"{moved}\n"


macos_trust = pytest.mark.skipif(sys.platform == "win32", reason="the macOS certificate fix")


@macos_trust
def test_cli_launches_use_the_system_certificates_only_when_the_app_asks(tmp_path, monkeypatch):
    monkeypatch.setattr(experimental_profile, "_system_certificates", False)
    monkeypatch.setattr(ExperimentalCliProfile, "prepare", lambda _self: None)
    profile = ExperimentalCliProfile(tmp_path / "profile", tmp_path / "codex")
    operation = tmp_path / "operation"
    operation.mkdir(mode=0o700)
    for name in ("tmp", "cache", "data", "state", "logs"):
        (operation / name).mkdir(mode=0o700)
    assert "CODEX_CA_CERTIFICATE" not in profile.launch(profile.executable, ("--version",), operation)[2]
    experimental_profile.use_system_certificates()
    assert profile.launch(profile.executable, ("--version",), operation)[2]["CODEX_CA_CERTIFICATE"] == (
        "/private/etc/ssl/cert.pem")


@macos_trust
@pytest.mark.parametrize("content", [None, "not a system file"])
def test_a_missing_or_user_owned_certificate_file_stops_the_launch(tmp_path, monkeypatch, content):
    pem = tmp_path / "cert.pem"
    if content is not None:
        pem.write_text(content)
    monkeypatch.setattr(experimental_profile, "SYSTEM_CA", pem)
    with pytest.raises(ExperimentalProfileError, match="CLI_CA_UNAVAILABLE"):
        experimental_profile.system_certificates()


def test_windows_cli_launches_keep_their_own_certificate_store(monkeypatch):
    monkeypatch.setattr(experimental_profile, "_system_certificates", False)
    monkeypatch.setattr(experimental_profile.host, "WINDOWS", True)
    experimental_profile.use_system_certificates()
    assert experimental_profile._system_certificates is False


def test_the_app_uses_only_the_runtimes_it_installs(tmp_path, monkeypatch):
    profile = experimental_profile.installed_profile(tmp_path / "cli-profile", managed_only=True)
    assert profile.executable == distribution.managed_executable(tmp_path / "cli-runtime")
    # A native Claude install on the same machine is not used either.
    monkeypatch.setattr(claude, "installed_executable", lambda: tmp_path / "native/claude")
    slot = launcher.claude_slot(tmp_path, managed_only=True)
    assert slot.profile.executable == ClaudeInstallation(tmp_path / ("cli-runtime-" + claude.KIND)).executable


def test_the_service_serves_the_page_and_stops_when_its_shell_closes_stdin(tmp_path):
    root = private_root(tmp_path)
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<p>synthetic shell</p>", encoding="utf-8")
    environment = {**os.environ, "HOME": str(tmp_path / "home")}
    origins = []
    for _ in range(2):
        process = subprocess.Popen([sys.executable, "tests/service/desktop_fixture.py", str(root), str(frontend)],
                                   cwd=ROOT, env=environment, text=True,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        try:
            # select() cannot wait on a pipe on Windows.
            lines: queue.Queue[str] = queue.Queue()
            threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            line = lines.get(timeout=30)
            assert line, process.stderr.read()
            started = json.loads(line)
            origin, secret = started["origin"], started["secret"]
            assert curl(origin + "/").stdout == "<p>synthetic shell</p>"
            jar = str(tmp_path / "cookies")
            exchange = curl("-o", os.devnull, "-w", "%{http_code}", "-c", jar, "-X", "POST", "-H", "Origin: " + origin,
                            "-H", "Content-Type: application/json", "--data", json.dumps({"secret": secret}),
                            origin + "/v1/session/exchange")
            assert exchange.stdout == "200"
            preferences = curl("-w", "\n%{http_code}", "-b", jar, origin + "/v1/settings/preferences")
            assert preferences.stdout.endswith("\n200")
            process.stdin.close()
            assert process.wait(timeout=15) == 0
            assert secret not in process.stderr.read()
            origins.append(origin)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    # The second start keeps the origin, so the page finds the edits it stored but had not sent.
    assert origins[0] == origins[1]
