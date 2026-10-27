"""`resume_api.lifecycle`: the owned-operation reaper, restart blocking by cleanup markers, worker group cleanup and the
supported-host check."""

from __future__ import annotations

import json
import os
from pathlib import Path
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
    original_remove = cli_runner.shutil.rmtree

    def partial_remove(path, *args, **kwargs):
        if Path(path) == stale:
            (stale / ".owner").unlink()
            (stale / ".lock").unlink()
            raise OSError("synthetic partial reaping")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(cli_runner.shutil, "rmtree", partial_remove)
    with pytest.raises(SpikeError, match="CLEANUP_FAILED"):
        reap_owned(root)
    monkeypatch.setattr(cli_runner.shutil, "rmtree", original_remove)
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
    os.mkfifo(fifo_intent)
    oversized_intent = root / (".cleanup-intent-op-" + "e" * 32 + ".json")
    oversized_intent.write_text("x" * 257)
    async with signed_in(make_app(tmp_path, connection_adapter=HealthyConnection())) as client:
        assert await status(client) == "connected"
    assert unrelated.is_dir() and foreign_intent.is_file() and linked_intent.is_symlink()
    assert fifo_intent.exists() and oversized_intent.is_file()
    assert private.read_text() == "synthetic private data"


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
    with pytest.raises(RuntimeError, match="macOS arm64 only"):
        lifecycle.require_supported_host()
