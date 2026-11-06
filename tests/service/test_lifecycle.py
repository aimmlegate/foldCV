"""`resume_api.lifecycle`: the owned-operation reaper, restart blocking by cleanup markers, worker group cleanup and the
supported-host check."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import time

import pytest

from resume_api import lifecycle
from resume_api.cli import runner as cli_runner
from resume_api.cli.runner import SpikeError, group_members, operation
from resume_api.lifecycle import OWNER, OperationFiles, reap_owned
from tests.service.app_fixtures import HealthyConnection, make_app, signed_in, status


def test_the_reaper_removes_only_owned_stale_directories(tmp_path):
    root = tmp_path / "ops"
    root.mkdir()
    with operation(root, owner=OWNER) as stale:
        stale_name = stale.name
    stale = root / stale_name
    stale.mkdir()
    (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": stale_name[3:]}), encoding="utf-8")
    (stale / ".lock").touch()
    (stale / "private.txt").write_text("synthetic", encoding="utf-8")
    unrelated = root / "other"
    unrelated.mkdir()
    (unrelated / "private.txt").write_text("keep", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    (root / ("op-" + "f" * 32)).symlink_to(target, target_is_directory=True)
    with operation(root, owner=OWNER) as active:
        assert reap_owned(root) == 1
        assert active.is_dir()
    assert reap_owned(root) == 0
    assert list(root.glob(".cleanup-intent-op-*.json")) == []
    assert unrelated.joinpath("private.txt").read_text(encoding="utf-8") == "keep"
    assert target.is_dir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(SpikeError, match="UNSAFE_TEMP_ROOT"):
        reap_owned(alias)


@pytest.mark.asyncio
async def test_a_partial_reaping_intent_blocks_the_service_restart(tmp_path, monkeypatch):
    root = tmp_path / "operations"
    root.mkdir()
    identifier = "a" * 32
    stale = root / f"op-{identifier}"
    stale.mkdir()
    (stale / ".owner").write_text(json.dumps({"owner": OWNER, "id": identifier}))
    (stale / ".lock").touch()
    (stale / "synthetic.txt").write_text("synthetic")
    original_remove = shutil.rmtree

    def partial_remove(path, *args, **kwargs):
        if Path(path) == stale:
            (stale / ".owner").unlink()
            (stale / ".lock").unlink()
            raise OSError("synthetic partial reaping")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", partial_remove)
    with pytest.raises(SpikeError, match="CLEANUP_FAILED"):
        reap_owned(root)
    monkeypatch.setattr(shutil, "rmtree", original_remove)
    assert stale.is_dir() and (stale / "synthetic.txt").is_file()
    assert len(list(root.glob(".cleanup-intent-op-*.json"))) == 1
    async with signed_in(make_app(tmp_path, connection_adapter=HealthyConnection())) as client:
        assert await status(client) == "cleanup_blocked"
    assert stale.is_dir()


@pytest.mark.asyncio
async def test_foreign_and_unsafe_markers_do_not_block_a_new_service(tmp_path):
    root = tmp_path / "operations"
    root.mkdir()
    unrelated = root / ("op-" + "a" * 32)
    unrelated.mkdir()
    (unrelated / ".owner").write_text(json.dumps({"owner": "another-app", "id": "a" * 32}))
    (unrelated / ".lock").touch()
    (unrelated / ".cleanup-blocked").touch()
    foreign_intent = root / (".cleanup-intent-op-" + "b" * 32 + ".json")
    foreign_intent.write_text(json.dumps({"owner": "another-app", "id": "b" * 32}))
    private = tmp_path / "private-marker"
    private.write_text("synthetic private data")
    linked_intent = root / (".cleanup-intent-op-" + "c" * 32 + ".json")
    linked_intent.symlink_to(private)
    fifo_intent = root / (".cleanup-intent-op-" + "d" * 32 + ".json")
    if hasattr(os, "mkfifo"):
        os.mkfifo(fifo_intent)
    else:
        fifo_intent.mkdir()  # Windows has no FIFO; a directory is the other non-file entry.
    oversized_intent = root / (".cleanup-intent-op-" + "e" * 32 + ".json")
    oversized_intent.write_text("x" * 257)
    async with signed_in(make_app(tmp_path, connection_adapter=HealthyConnection())) as client:
        assert await status(client) == "connected"
    assert unrelated.is_dir() and foreign_intent.is_file() and linked_intent.is_symlink()
    assert fifo_intent.exists() and oversized_intent.is_file()
    assert private.read_text() == "synthetic private data"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups; test_host.py covers the Windows job")
def test_a_failed_operation_stops_the_worker_group_and_removes_its_directory(tmp_path):
    files = OperationFiles(tmp_path / "ops")
    script = tmp_path / "worker.py"
    script.write_text("import signal, subprocess, sys\n"
                      "child = subprocess.Popen([sys.executable, '-c', 'import signal; signal.pause()'])\n"
                      "open(sys.argv[1], 'w').write(str(child.pid))\n"
                      "signal.pause()\n", encoding="utf-8")
    child_pid = tmp_path / "child.pid"
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with files.open():
            process = files.spawn(Path(sys.executable), (str(script), str(child_pid)))
            assert process.poll() is None
            # Waits for the real grandchild to start; the bound only stops a broken host from hanging the run.
            for _ in range(400):
                if child_pid.exists() and child_pid.read_text():
                    break
                time.sleep(0.01)
            assert child_pid.exists()
            raise RuntimeError("synthetic failure")
    assert group_members(process.pid) == []
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed
    assert list((tmp_path / "ops").iterdir()) == []


def test_an_unsupported_host_fails_clearly(monkeypatch):
    monkeypatch.setattr(lifecycle.sys, "platform", "linux")
    monkeypatch.setattr(lifecycle.host, "WINDOWS", False)
    with pytest.raises(RuntimeError, match="macOS arm64 and Windows x64 only"):
        lifecycle.require_supported_host()


def test_windows_runs_on_x64_only(monkeypatch):
    monkeypatch.setattr(lifecycle.host, "WINDOWS", True)
    monkeypatch.setattr(lifecycle.platform, "machine", lambda: "AMD64")
    lifecycle.require_supported_host()
    monkeypatch.setattr(lifecycle.platform, "machine", lambda: "ARM64")
    with pytest.raises(RuntimeError, match="Windows x64 only"):
        lifecycle.require_supported_host()


# Edge cases of the reaper and the worker group stop; until 2026-11-06 they ran through the deleted CLI spike's Runner.
CANARY = "synthetic canary — Alex Example ☃"


def stale_directory(root, identifier, *, owner=OWNER):
    stale = root / ("op-" + identifier)
    stale.mkdir(parents=True)
    (stale / ".owner").write_text(json.dumps({"owner": owner, "id": identifier}))
    (stale / ".lock").touch()
    return stale


def ended(pid):
    import subprocess
    state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
    return not state or state.startswith("Z")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX worker records")
@pytest.mark.parametrize("record", [b"", b"{bad", b'{"pid":0}', b'{"pid":2,"extra":true}'])
def test_a_corrupt_worker_record_is_quarantined(tmp_path, record):
    stale = stale_directory(tmp_path / "ops", "f" * 32)
    (stale / ".worker").write_bytes(record)
    (stale / "canary").write_text(CANARY, encoding="utf-8")
    reap_owned(tmp_path / "ops")
    assert (stale / ".worker").read_bytes() == record and (stale / "canary").read_text(encoding="utf-8") == CANARY
    assert (stale / ".cleanup-blocked").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_a_symlinked_worker_record_is_quarantined(tmp_path):
    stale = stale_directory(tmp_path / "ops", "f" * 32)
    (stale / ".worker").symlink_to(stale / "missing-worker")
    reap_owned(tmp_path / "ops")
    assert (stale / ".worker").is_symlink() and (stale / ".cleanup-blocked").exists()


def test_a_failed_process_cleanup_keeps_its_quarantined_directory(tmp_path):
    root = tmp_path / "ops"
    with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
        with operation(root, owner=OWNER) as directory:
            (directory / "synthetic-content").write_text(CANARY, encoding="utf-8")
            raise SpikeError("PROCESS_CLEANUP_FAILED")
    reap_owned(root)
    assert (directory / "synthetic-content").read_text(encoding="utf-8") == CANARY and (directory / ".cleanup-blocked").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_a_restart_reaps_only_owned_inactive_directories(tmp_path):
    root, outside = tmp_path / "ops", tmp_path / "outside"
    outside.mkdir()
    stale = stale_directory(root, "a" * 32)
    other = stale_directory(root, "b" * 32, owner="unrelated")
    link = root / ("op-" + "c" * 32)
    link.symlink_to(outside, target_is_directory=True)
    unrelated = root / "keep.txt"
    unrelated.write_text("unrelated")
    with operation(root, owner=OWNER) as active:
        (active / "canary").write_text(CANARY, encoding="utf-8")
        assert reap_owned(root) == 1 and active.exists()
    assert not stale.exists() and other.exists() and link.is_symlink() and unrelated.exists() and outside.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_a_crash_during_spawn_with_a_live_worker_is_quarantined(tmp_path):
    import subprocess
    stale = stale_directory(tmp_path / "ops", "6" * 32)
    (stale / ".worker").write_text('{"state":"spawning"}')
    (stale / "canary").write_text(CANARY, encoding="utf-8")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=stale, start_new_session=True)
    try:
        reap_owned(tmp_path / "ops")
        assert child.poll() is None and (stale / "canary").read_text(encoding="utf-8") == CANARY
        assert (stale / ".cleanup-blocked").exists()
        assert json.loads((stale / ".worker").read_text()) == {"state": "spawning"}
    finally:
        child.kill()
        child.wait(timeout=2)


def test_a_malformed_owner_does_not_block_independent_cleanup(tmp_path):
    root = tmp_path / "ops"
    bad_id, good_id = "7" * 32, "8" * 32
    bad, good = root / ("op-" + bad_id), root / ("op-" + good_id)
    for path in (bad, good):
        path.mkdir(parents=True)
        (path / ".lock").touch()
        (path / "canary").write_text(CANARY, encoding="utf-8")
    (bad / ".owner").write_text("{bad")
    (good / ".owner").write_text(json.dumps({"owner": OWNER, "id": good_id}))
    reap_owned(root)
    assert (bad / "canary").read_text(encoding="utf-8") == CANARY and not good.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_a_directory_with_a_surviving_worker_stays_until_the_worker_ends(tmp_path):
    import subprocess
    root = tmp_path / "ops"
    stale = stale_directory(root, "e" * 32)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    (stale / ".worker").write_text(json.dumps({"pid": child.pid}))
    try:
        reap_owned(root)
        assert stale.exists()
    finally:
        child.kill()
        child.wait(timeout=2)
    reap_owned(root)
    assert not stale.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_a_symlinked_or_unusable_temp_root_is_refused(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "root-link"
    link.symlink_to(target, target_is_directory=True)
    for call in (lambda: reap_owned(link), lambda: operation(link, owner=OWNER).__enter__()):
        with pytest.raises(SpikeError, match="UNSAFE_TEMP_ROOT"):
            call()
    afile = tmp_path / "a-file"
    afile.write_text("not a directory")
    with pytest.raises(SpikeError, match="TEMP_FAILED"):
        reap_owned(afile)
    assert list(target.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_a_group_whose_signal_is_denied_is_inspected_again_until_a_late_fork_is_stopped(tmp_path):
    # macOS may deny group signals after the leader exits; the stop then signals each member it can see, and looks
    # again, so a child forked between two inspections is stopped too.
    import signal
    import subprocess
    from unittest.mock import patch
    fork_now, forked = tmp_path / "fork_now", tmp_path / "forked_pid"
    script = ("import os, sys, time\n"
              f"while not os.path.exists({str(fork_now)!r}): time.sleep(0.005)\n"
              "if os.fork() == 0:\n"
              f"    open({str(forked)!r}, 'w').write(str(os.getpid())); time.sleep(30)\n"
              "time.sleep(30)\n")
    leader = subprocess.Popen([sys.executable, "-c", script], start_new_session=True)
    real_killpg, inspected = os.killpg, [0]

    def killpg(group_id, sig):
        if group_id == leader.pid:
            raise PermissionError()
        return real_killpg(group_id, sig)

    def members(group_id):
        snapshot = group_members(group_id)
        if group_id == leader.pid:
            inspected[0] += 1
            if inspected[0] == 1:
                fork_now.touch()
                deadline = time.monotonic() + 15
                while not forked.exists() and time.monotonic() < deadline:
                    time.sleep(0.005)
        return snapshot

    try:
        with patch("resume_api.cli.runner.os.killpg", side_effect=killpg), \
             patch("resume_api.cli.runner.group_members", side_effect=members):
            cli_runner.stop_group(leader)
        assert inspected[0] >= 2 and forked.exists() and ended(int(forked.read_text()))
    finally:
        try:
            real_killpg(leader.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_a_child_that_ignores_term_is_killed_with_its_group(tmp_path):
    import subprocess
    child_pid, term_seen = tmp_path / "child_pid", tmp_path / "term_seen"
    script = ("import os, signal, sys, time\n"
              "if os.fork() == 0:\n"
              f"    signal.signal(signal.SIGTERM, lambda *_: open({str(term_seen)!r}, 'w').close())\n"
              f"    open({str(child_pid)!r}, 'w').write(str(os.getpid())); time.sleep(30)\n"
              "time.sleep(30)\n")
    leader = subprocess.Popen([sys.executable, "-c", script], start_new_session=True)
    deadline = time.monotonic() + 15
    while not child_pid.exists() and time.monotonic() < deadline:
        time.sleep(0.005)
    pid = int(child_pid.read_text())
    cli_runner.stop_group(leader)
    assert ended(pid) and leader.poll() is not None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX spawn")
def test_the_spawning_marker_precedes_the_launch_and_a_failed_launch_removes_it(tmp_path):
    import subprocess
    from unittest.mock import patch
    markers, original = [], subprocess.Popen

    def checked(*args, **kwargs):
        markers.append(json.loads((Path(kwargs["cwd"]) / ".worker").read_text()))
        return original(*args, **kwargs)

    files = OperationFiles(tmp_path / "ops")
    with files.open():
        with patch("resume_api.lifecycle.subprocess.Popen", side_effect=checked):
            files.spawn(Path(sys.executable), ("-c", "pass"), capture=False).wait(timeout=10)
        assert markers == [{"state": "spawning"}]
    files = OperationFiles(tmp_path / "ops")
    with files.open():
        with patch("resume_api.lifecycle.subprocess.Popen", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                files.spawn(Path(sys.executable), ("-c", "pass"), capture=False)
        assert not (files.path / ".worker").exists()
    assert list((tmp_path / "ops").iterdir()) == []
