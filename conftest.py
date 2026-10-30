"""Reject socket calls from every ordinary Python test in this repository; verify repository commits (D109)."""

import os
import socket

import pytest

# Every repository commit and cache hit is cross-checked in tests (simplification plan 2.1).
os.environ.setdefault('FOLDCV_VERIFY', '1')
# Tests see what a clean clone ships, whatever the ignored local template folder holds.
os.environ.setdefault('FOLDCV_PUBLIC_TEMPLATES', '1')


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden in routine tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
