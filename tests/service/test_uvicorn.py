"""Real uvicorn servers: the launcher is ready before it prints its URL, and SIGTERM during a live child process stops
its group and removes its operation directory. curl runs outside the Python socket guard.

No kept route streams: long work stops through its own cancel routes (sign-in, detach, rewrite, import, assistant
runs) or at shutdown, so a client disconnect after the body cancels nothing; a disconnect during the body is
tests/service/test_boundary.py::test_a_disconnect_during_the_body_starts_no_work."""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

from resume_api.cli.runner import group_members

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "tests/service/uvicorn_fixture.py"
SECRET = "synthetic-startup-secret-0123456789"


def start_server(arguments: list[str], home: Path) -> tuple[subprocess.Popen[str], str]:
    environment = {**os.environ, "HOME": str(home)}
    environment.pop("FOLDCV_CODEX_EXECUTABLE", None)
    process = subprocess.Popen([sys.executable, FIXTURE, *arguments], cwd=ROOT, text=True, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    assert process.stdout is not None
    try:
        ready, _, _ = select.select([process.stdout], [], [], 10)
        assert ready, "server readiness timed out"
        origin = process.stdout.readline().strip()
        assert origin.startswith("http://127.0.0.1:"), process.stderr.read() if process.poll() is not None else origin
        return process, origin
    except BaseException:
        process.terminate()
        process.wait(timeout=5)
        raise


def stop_server(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    assert process.stderr is not None
    assert "synthetic-startup-secret" not in process.stderr.read()


def curl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/usr/bin/curl", "--silent", "--show-error", "--max-time", "5", *args],
                          input=input_data, text=True, capture_output=True, timeout=10)


def wait_for(path: Path) -> None:
    # Waits for the real server process; the bound only keeps a broken host from hanging the run.
    for _ in range(500):
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"{path.name} never appeared")


def test_the_launcher_is_ready_before_it_prints_its_url(tmp_path):
    process, origin = start_server([str(tmp_path), "launcher"], tmp_path / "home")
    try:
        page = curl(origin + "/")
        assert page.returncode == 0 and "FoldCV" in page.stdout
        denied = curl(origin + "/v1/settings/connection")
        assert json.loads(denied.stdout)["error"]["code"] == "AUTH_REQUIRED"
    finally:
        stop_server(process)
    # The default data root follows HOME, so the run never reaches the user's store.
    assert (tmp_path / "home/Library/Application Support/FoldCV").is_dir()


def test_sigterm_during_a_live_child_stops_its_group_and_removes_the_directory(tmp_path):
    process, origin = start_server([str(tmp_path), "child"], tmp_path / "home")
    cookies = tmp_path / "cookies"
    request: subprocess.Popen[str] | None = None
    terminated = False
    try:
        login = curl("-X", "POST", "-H", "Origin: " + origin, "-H", "Content-Type: application/json",
                     "-c", str(cookies), "--data-binary", "@-", origin + "/v1/session/exchange",
                     input_data=json.dumps({"secret": SECRET}))
        assert login.returncode == 0 and json.loads(login.stdout)["sessionReady"] is True
        request = subprocess.Popen(["/usr/bin/curl", "--silent", "--max-time", "10", "-X", "POST",
                                    "-H", "Origin: " + origin, "-H", "Content-Type: application/json",
                                    "-b", str(cookies), "--data", "{}", origin + "/v1/host/status"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        wait_for(tmp_path / "worker-pgid")
        group_id = int((tmp_path / "worker-pgid").read_text(encoding="utf-8"))
        assert group_members(group_id)
        process.terminate()
        process.wait(timeout=10)
        terminated = True
        assert (tmp_path / "cancelled").exists()
        assert group_members(group_id) == []
        assert list((tmp_path / "operations").iterdir()) == []
    finally:
        if request is not None and request.poll() is None:
            request.terminate()
            request.wait(timeout=5)
        if not terminated:
            stop_server(process)
