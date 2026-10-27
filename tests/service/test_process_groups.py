"""Vanished macOS groups are distinguished from denied process inspection."""

import signal
import subprocess
from unittest.mock import Mock

import pytest

from tools import process_groups as groups


@pytest.mark.parametrize("sig", [0, signal.SIGTERM, signal.SIGKILL])
def test_permission_error_for_vanished_or_zombie_only_group_is_not_signaled(monkeypatch, sig):
    kill = Mock(side_effect=PermissionError())
    monkeypatch.setattr(groups.os, "killpg", kill)
    monkeypatch.setattr(groups.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, stdout=b"123 S\n456 Z\n"))
    assert groups.signal_group(456, sig) is False
    kill.assert_called_once_with(456, sig)


def test_live_group_permission_failure_stays_a_cleanup_error(monkeypatch):
    monkeypatch.setattr(groups.os, "killpg", Mock(side_effect=PermissionError()))
    monkeypatch.setattr(groups.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, stdout=b"456 S\n"))
    with pytest.raises(PermissionError):
        groups.signal_group(456, signal.SIGKILL)


@pytest.mark.parametrize("output", [b"", b"unknown\n", b"123\n", b"123 S extra\n", b"0 S\n" * 150_000])
def test_uncertain_group_inventory_fails_closed(monkeypatch, output):
    monkeypatch.setattr(groups.os, "killpg", Mock(side_effect=PermissionError()))
    monkeypatch.setattr(groups.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, stdout=output))
    with pytest.raises(OSError, match="inspection failed"):
        groups.signal_group(456, 0)


def test_failed_process_inventory_cannot_claim_cleanup(monkeypatch):
    monkeypatch.setattr(groups.os, "killpg", Mock(side_effect=PermissionError()))

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr(groups.subprocess, "run", fail)
    with pytest.raises(OSError, match="inspection failed"):
        groups.signal_group(456, 0)
