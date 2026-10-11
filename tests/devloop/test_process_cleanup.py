"""An unreaped leader pins its group until descendant cleanup completes."""

import signal
import subprocess
import sys
from unittest.mock import Mock

import pytest

from tools import devloop


def test_stop_group_cannot_signal_a_reused_group_after_reaping(monkeypatch):
    process = Mock(pid=98765, returncode=None)
    process.poll.side_effect = lambda: setattr(process, "returncode", 0)
    live = True
    sent = []

    def killpg(pid, sig):
        nonlocal live
        assert process.returncode is None, "Group ownership was lost by reaping the leader"
        if not live:
            raise ProcessLookupError()
        if sig:
            sent.append(sig)
            live = False

    monkeypatch.setattr(devloop.os, "killpg", killpg)
    devloop.stop_group(process)
    assert sent == [signal.SIGTERM]
    process.wait.assert_called_once()


def test_stop_group_does_not_signal_a_disappeared_group(monkeypatch):
    process = Mock(pid=98765, returncode=None)
    sent = []

    def killpg(pid, sig):
        sent.append(sig)
        raise ProcessLookupError()

    monkeypatch.setattr(devloop.os, "killpg", killpg)
    devloop.stop_group(process)
    assert sent and all(sig == 0 for sig in sent)
    process.wait.assert_called_once()


def test_stop_group_rejects_lost_ownership_without_signaling(monkeypatch):
    kill = Mock()
    monkeypatch.setattr(devloop.os, "killpg", kill)
    with pytest.raises(devloop.DevloopError, match="cleanup_failed"):
        devloop.stop_group(Mock(pid=98765, returncode=0))
    kill.assert_not_called()


def test_timeout_cleans_descendants_after_their_leader_exits(tmp_path):
    child_pid = tmp_path / "child.pid"
    child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)"
    leader = ("import subprocess,sys; from pathlib import Path; "
              f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
              f"Path({str(child_pid)!r}).write_text(str(p.pid))")
    with pytest.raises(devloop.DevloopError, match="timeout"):
        devloop.run_bounded([sys.executable, "-c", leader], tmp_path, timeout=0.3)
    pid = int(child_pid.read_text())
    status = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], text=True, capture_output=True).stdout.strip()
    assert not status or status.startswith("Z")
