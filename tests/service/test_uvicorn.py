"""Real loopback server checks; curl runs outside the Python socket guard."""

from __future__ import annotations

import json
from pathlib import Path
import select
import subprocess
import sys
import time

from spikes.cli.runner import group_members


ROOT = Path(__file__).resolve().parents[2]
SECRET = "synthetic-startup-secret-0123456789"
INPUT = {"baseRevision": 0, "sourceUnits": [], "language": "en"}


def start_server(command: list[str]) -> tuple[subprocess.Popen[str], str]:
    process = subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    assert process.stdout is not None
    try:
        ready, _, _ = select.select([process.stdout], [], [], 5)
        assert ready, "server readiness timed out"
        origin = process.stdout.readline().strip()
        assert origin.startswith("http://127.0.0.1:")
        return process, origin
    except BaseException:
        process.terminate()
        process.wait(timeout=2)
        raise


def stop_server(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    assert process.stderr is not None
    assert "synthetic-startup-secret" not in process.stderr.read()


def curl(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/usr/bin/curl", "--silent", "--show-error", "--max-time", "2", *args],
                          input=input_data, text=True, capture_output=True, timeout=4)


def test_launcher_is_ready_before_no_open_url_is_printed():
    process, origin = start_server([sys.executable, "tools/run-local.py", "--no-open"])
    try:
        page = curl(origin + "/")
        assert page.returncode == 0 and "FoldCV" in page.stdout
        denied = curl(origin + "/v1/capabilities")
        assert json.loads(denied.stdout)["error"]["code"] == "AUTH_REQUIRED"
    finally:
        stop_server(process)


def test_uvicorn_disconnect_cancels_runner_and_cleans_files(tmp_path):
    process, origin = start_server([sys.executable, "tests/service/uvicorn_fixture.py", str(tmp_path)])
    cookie_file = tmp_path / "cookies"
    try:
        login = curl("-X", "POST", "-H", "Origin: " + origin, "-H", "Content-Type: application/json",
                     "-c", str(cookie_file), "--data-binary", "@-", origin + "/v1/session/exchange",
                     input_data=json.dumps({"secret": SECRET}))
        assert login.returncode == 0 and json.loads(login.stdout)["sessionReady"] is True
        stream = subprocess.run(["/usr/bin/curl", "--silent", "--no-buffer", "--max-time", "0.3",
                                 "-X", "POST", "-H", "Origin: " + origin,
                                 "-H", "Content-Type: application/json", "-b", str(cookie_file),
                                 "--data-binary", "@-", origin + "/v1/normalize"],
                                input=json.dumps(INPUT), text=True, capture_output=True, timeout=3)
        assert stream.returncode == 28
        assert '"type":"operation.started"' in stream.stdout
        deadline = time.monotonic() + 2
        while ((not (tmp_path / "cancelled").exists()) or list((tmp_path / "operations").iterdir())) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (tmp_path / "cancelled").exists()
        assert list((tmp_path / "operations").iterdir()) == []
    finally:
        stop_server(process)


def test_sigterm_during_live_child_cleans_group_and_workspace(tmp_path):
    process, origin = start_server([sys.executable, "tests/service/uvicorn_fixture.py", str(tmp_path), "child"])
    cookie_file = tmp_path / "cookies"
    stream: subprocess.Popen[str] | None = None
    terminated = False
    try:
        login = curl("-X", "POST", "-H", "Origin: " + origin, "-H", "Content-Type: application/json",
                     "-c", str(cookie_file), "--data-binary", "@-", origin + "/v1/session/exchange",
                     input_data=json.dumps({"secret": SECRET}))
        assert login.returncode == 0
        stream = subprocess.Popen(["/usr/bin/curl", "--silent", "--no-buffer", "--max-time", "5",
                                   "-X", "POST", "-H", "Origin: " + origin,
                                   "-H", "Content-Type: application/json", "-b", str(cookie_file),
                                   "--data-binary", "@-", origin + "/v1/normalize"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True)
        assert stream.stdin is not None
        stream.stdin.write(json.dumps(INPUT))
        stream.stdin.close()
        deadline = time.monotonic() + 2
        while not (tmp_path / "worker-pgid").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (tmp_path / "worker-pgid").exists()
        group_id = int((tmp_path / "worker-pgid").read_text(encoding="utf-8"))
        assert group_members(group_id)
        process.terminate()
        process.wait(timeout=5)
        terminated = True
        assert (tmp_path / "cancelled").exists()
        assert (tmp_path / "pipes-closed").exists()
        assert group_members(group_id) == []
        assert list((tmp_path / "operations").iterdir()) == []
    finally:
        if stream is not None and stream.poll() is None:
            stream.terminate()
            stream.wait(timeout=2)
        if not terminated:
            stop_server(process)
