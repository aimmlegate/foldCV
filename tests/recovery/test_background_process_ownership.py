"""Keep independent synthetic peers alive across ambiguous cleanup identities."""

import asyncio
from dataclasses import replace
import json

import pytest

from resume_api.jobs.process_ownership import GuardedPipe, ProcessInspector
from resume_api.lifecycle import SpikeError
from spikes.cli.runner import group_members
from spikes.background.appserver_protocol import TransportFailure
from tests.recovery.test_background_appserver import pipe_peer


@pytest.mark.parametrize("leader_wait", [0, .02, .05], ids=["leader-already-exited", "leader-exits-during-grace", "leader-still-running"])
def test_owned_cleanup_keeps_the_host_grace_when_the_leader_exits_early(leader_wait):
    import signal
    from resume_api.jobs.process_ownership import OwnedProcess
    elapsed, signals = [0.0], []
    def advance(seconds):
        elapsed[0] += seconds
    class Process:
        first = True
        def wait(self, timeout):
            if self.first:
                self.first = False
                advance(min(timeout, leader_wait))
            return 0
    owner = OwnedProcess.__new__(OwnedProcess)
    owner.process = Process()
    owner.clock = lambda: elapsed[0]
    owner.pause = advance
    owner.signal = lambda sig: signals.append((sig, elapsed[0]))
    owner.check = lambda: (None, [])
    owner.stop_verified_process()
    assert [sig for sig, _when in signals] == [signal.SIGTERM, signal.SIGKILL]
    assert .05 - 1e-8 <= signals[1][1] - signals[0][1] <= .05 + 1e-8


async def echo(peer, identifier):
    peer.send({"id": identifier, "params": {"private": "neighbor"}})
    result = json.loads(await asyncio.wait_for(peer.receive(), 5))
    assert result["id"] == identifier and result["result"]["pid"] == peer.process.pid
    return result


@pytest.mark.asyncio
async def test_known_child_outliving_the_leader_is_cleaned_without_signaling_the_neighbor(tmp_path):
    first = await GuardedPipe(pipe_peer(tmp_path / "A"), ProcessInspector()).start()
    second = await GuardedPipe(pipe_peer(tmp_path / "B"), ProcessInspector()).start()
    try:
        first.send({"id": 100, "method": "fixture/fork-child"})
        child = json.loads(await asyncio.wait_for(first.receive(), 5))["result"]["childPid"]
        assert child in {row.pid for row in first.ownership.check()[1]}
        first.send({"method": "fixture/exit", "params": {"code": 7}})
        with pytest.raises(TransportFailure, match="SERVER_EXITED"):
            await asyncio.wait_for(first.receive(), 5)
        result = await first.close()
        assert result["ownedGroupCleanupVerified"] and result["operationRemoved"]
        assert not group_members(first.process.pid)
        await echo(second, 200)
        assert second.process.poll() is None and second.operation.exists()
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-R01:v02", "NB-R01:v03", "NB-R01:v07"])
async def test_unverified_pid_marker_or_group_never_signals_or_deletes_a_neighbor(tmp_path, monkeypatch, variant):
    import os
    first = await GuardedPipe(pipe_peer(tmp_path / "A"), ProcessInspector()).start()
    second = await GuardedPipe(pipe_peer(tmp_path / "B"), ProcessInspector()).start()
    owner = first.ownership
    identity = owner.inspector.identity
    marker = first.operation / ".owner"
    raw = marker.read_bytes()
    signals = []
    killpg = os.killpg
    def signal_group(pid, sig):
        signals.append((pid, sig))
        return killpg(pid, sig)
    monkeypatch.setattr(os, "killpg", signal_group)
    try:
        if variant == "NB-R01:v03":
            marker.unlink()
        else:
            def changed(pid):
                observed = identity(pid)
                if pid == first.process.pid and observed is not None:
                    return replace(observed, microseconds=observed.microseconds + 1) if variant == "NB-R01:v02" else replace(
                        observed, group=second.process.pid)
                return observed
            owner.inspector.identity = changed
        with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
            await first.close()
        assert owner.files.cleanup_failed and not first.cleanup_verified and not signals
        assert first.operation.exists() and second.operation.exists()
        await echo(second, 300)
        assert second.process.poll() is None
    finally:
        owner.inspector.identity = identity
        if not marker.exists():
            marker.write_bytes(raw)
        await asyncio.to_thread(owner.stop_verified_process)
        with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
            await first.close()
        assert first.process.poll() is not None
        assert (first.operation / ".cleanup-blocked").exists()
        await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing-identity", "foreign-parent", "group-mismatch", "inspector-error", "spawn-marker-failure"])
async def test_unverified_startup_never_falls_back_to_legacy_signals_or_directory_removal(tmp_path, monkeypatch, fault):
    import os
    from pathlib import Path
    from resume_api.jobs.process_ownership import OwnedProcess
    real = ProcessInspector()
    second = await GuardedPipe(pipe_peer(tmp_path / "B"), real).start()
    raw = pipe_peer(tmp_path / "A")
    spawn, captured = raw.files.spawn, {}
    def record_spawn(*args, **kwargs):
        try:
            return spawn(*args, **kwargs)
        finally:
            if raw.files.process is not None:
                captured["process"] = raw.files.process
                captured["owner"] = OwnedProcess(raw.files.process, raw.files, real)
    raw.files.spawn = record_spawn
    inspector = ProcessInspector()
    def ambiguous(pid):
        value = real.identity(pid)
        if fault == "missing-identity":
            return None
        if fault == "foreign-parent":
            return replace(value, parent=os.getpid() + 1000)
        if fault == "group-mismatch":
            return replace(value, group=second.process.pid)
        if fault == "inspector-error":
            raise SpikeError("PROCESS_CLEANUP_FAILED")
        return value
    inspector.identity = ambiguous
    first = GuardedPipe(raw, inspector)
    write_text = Path.write_text
    def marker_failure(path, data, *args, **kwargs):
        if fault == "spawn-marker-failure" and path.name == ".worker" and '"pid"' in data and path.parent == raw.files.path:
            raise OSError("synthetic marker write failure")
        return write_text(path, data, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", marker_failure)
    signals, killpg = [], os.killpg
    def observed_signal(pid, sig):
        signals.append((pid, sig))
        return killpg(pid, sig)
    monkeypatch.setattr(os, "killpg", observed_signal)
    try:
        with pytest.raises((OSError, SpikeError)):
            await first.start()
        assert not signals and first.files.cleanup_failed
        assert first.operation.exists() and (first.operation / ".worker").exists()
        assert (first.operation / ".cleanup-blocked").exists()
        await echo(second, 400)
        assert second.process.poll() is None and second.operation.exists()
    finally:
        try:
            process = captured.get("process")
            if process is not None and (process.poll() is None or group_members(process.pid)):
                await asyncio.to_thread(captured["owner"].stop_verified_process)
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
        finally:
            await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["live-group", "leader-exited", "identity-changed"])
async def test_denied_group_signal_rechecks_birth_before_fallback_and_keeps_the_neighbor(tmp_path, monkeypatch, fault):
    import os
    import signal
    first = await GuardedPipe(pipe_peer(tmp_path / "A"), ProcessInspector()).start()
    second = await GuardedPipe(pipe_peer(tmp_path / "B"), ProcessInspector()).start()
    killpg, kill = os.killpg, os.kill
    identity = first.ownership.inspector.identity
    individual = []
    def denied(pid, sig):
        if pid != first.process.pid:
            return killpg(pid, sig)
        if fault == "leader-exited" and first.process.poll() is None:
            kill(pid, signal.SIGTERM)
            first.process.wait(timeout=2)
        if fault == "identity-changed":
            first.ownership.inspector.identity = lambda current: replace(identity(current), microseconds=identity(current).microseconds + 1) if current == pid else identity(current)
        raise PermissionError("synthetic Darwin group denial")
    def observed(pid, sig):
        individual.append(pid)
        return kill(pid, sig)
    monkeypatch.setattr(os, "killpg", denied)
    monkeypatch.setattr(os, "kill", observed)
    try:
        if fault == "identity-changed":
            with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
                await first.close()
            assert not individual and first.files.cleanup_failed and first.operation.exists()
        else:
            result = await first.close()
            assert result["ownedGroupCleanupVerified"] and result["operationRemoved"]
            assert not group_members(first.process.pid)
            assert all(pid == first.process.pid for pid in individual)
        await echo(second, 500)
        assert second.process.poll() is None
    finally:
        monkeypatch.setattr(os, "killpg", killpg)
        first.ownership.inspector.identity = identity
        try:
            if fault == "identity-changed":
                await asyncio.to_thread(first.ownership.stop_verified_process)
            else:
                await first.close()
        finally:
            await second.close()
