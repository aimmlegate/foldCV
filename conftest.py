"""Reject socket calls from every ordinary Python test in this repository; verify repository commits (D109)."""

import os
import socket
import sys

import pytest

# Every repository commit and cache hit is cross-checked in tests (simplification plan 2.1).
os.environ.setdefault('FOLDCV_VERIFY', '1')


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = socket.socket.connect

    def blocked(*args: object, **kwargs: object) -> None:
        # Windows has no native socketpair: the standard library builds asyncio's self-pipe from a loopback connect.
        caller = sys._getframe(1).f_code
        if caller.co_filename == socket.__file__ and "socketpair" in caller.co_name:
            return connect(*args, **kwargs)
        raise AssertionError("network access is forbidden in routine tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
