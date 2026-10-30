"""The macOS/Windows layer (packages/resume_core/host.py, winjob.py). Locks, liveness and the threaded runner run on
both; the Job Object rules run on Windows only, which the Windows workflow covers."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest

from packages.resume_core import host
from packages.resume_core.storage import atomic_write
from resume_api.cli.process_runner import ProcessRunner
from resume_api.lifecycle import OperationFiles, SpikeError

windows = pytest.mark.skipif(not host.WINDOWS, reason="Windows Job Objects")
PYTHON = Path(sys.executable)


def test_a_held_lock_refuses_a_second_holder_until_it_is_released(tmp_path):
    path = tmp_path / "lock"
    first = os.open(path, os.O_RDWR | os.O_CREAT | host.O_BINARY, 0o600)
    second = os.open(path, os.O_RDWR | host.O_BINARY)
    try:
        host.lock(first)
        with pytest.raises(BlockingIOError):
            host.lock(second, blocking=False)
        host.unlock(first)
        host.lock(second, blocking=False)
        host.unlock(second)
        host.unlock(second)  # Releasing twice is harmless, as with flock.
    finally:
        os.close(first)
        os.close(second)


def test_liveness_never_signals_the_process(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert host.process_alive(child.pid)
        # os.kill(pid, 0) would end the process on Windows; the probe must leave it running.
        assert child.poll() is None
    finally:
        child.kill()
        child.wait(timeout=10)
    assert not host.process_alive(child.pid)


def test_binary_open_keeps_newline_bytes(tmp_path):
    path = tmp_path / "journal"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | host.O_BINARY, 0o600)
    try:
        os.write(descriptor, b"{}\n{}\n")
    finally:
        os.close(descriptor)
    assert path.read_bytes() == b"{}\n{}\n"


def run(root: Path, source: str, *, executable=PYTHON, **options):
    with OperationFiles(root).open() as files:
        return ProcessRunner(executable).run(files, ("-c", source), cancel=options.pop("cancel", threading.Event()),
                                             deadline=time.monotonic() + options.pop("seconds", 20), **options)


def test_the_runner_answers_each_line_and_closes_stdin_on_an_empty_reply(tmp_path):
    source = ("import sys\n"
              "sys.stdout.buffer.write(b'ready\\n'); sys.stdout.flush()\n"
              "for line in sys.stdin.buffer:\n"
              "    sys.stdout.buffer.write(b'got ' + line); sys.stdout.flush()\n")
    replies = iter([b"one\n", b"two\n", b""])
    seen = []

    def answer(raw):
        seen.append(raw)
        return next(replies) if raw in (b"ready", b"got one", b"got two") else None

    stdout, _ = run(tmp_path, source, on_line=answer, interactive=True)
    assert seen == [b"ready", b"got one", b"got two"]
    assert stdout == b"ready\ngot one\ngot two\n"


def test_the_runner_stops_at_the_deadline_and_on_cancel(tmp_path):
    started = time.monotonic()
    with pytest.raises(SpikeError, match="DEADLINE_EXCEEDED"):
        run(tmp_path / "late", "import time; time.sleep(60)", seconds=1)
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    with pytest.raises(SpikeError, match="CANCELLED"):
        run(tmp_path / "cancelled", "import time; time.sleep(60)", cancel=cancel)
    assert time.monotonic() - started < 15


def test_a_replaced_file_waits_for_a_reader_on_windows(tmp_path):
    target = tmp_path / "data.json"
    atomic_write(target, b"old")
    reader = target.open("rb")
    threading.Timer(0.3, reader.close).start()
    # Windows refuses the replace while the reader has the file open; the retry outlasts the reader.
    atomic_write(target, b"new")
    assert target.read_bytes() == b"new"


@windows
def test_a_confined_program_cannot_start_another(tmp_path):
    source = "import subprocess, sys; subprocess.run([sys.executable, '-c', 'pass'], check=True)"
    with pytest.raises(SpikeError, match="CLI_FAILED"):
        run(tmp_path / "none", source)
    run(tmp_path / "one", source, executable=host.Confined(PYTHON, children=1))


@windows
def test_stopping_a_worker_ends_what_it_started(tmp_path):
    from packages.resume_core import winjob

    grandchild = tmp_path / "grandchild.pid"
    source = ("import subprocess, sys, time\n"
              "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
              f"open({str(grandchild)!r}, 'w').write(str(child.pid))\n"
              "time.sleep(60)\n")
    with OperationFiles(tmp_path / "operations").open() as files:
        process = files.spawn(host.Confined(PYTHON, children=1), ("-c", source), capture=False)
        deadline = time.monotonic() + 20
        while not grandchild.is_file() or not grandchild.read_text():
            assert time.monotonic() < deadline
            time.sleep(0.05)
        pid = int(grandchild.read_text())
        assert sorted(winjob.job_pids(process)) == sorted([process.pid, pid])
        assert winjob.image(pid) and Path(winjob.image(pid)).name.lower() == PYTHON.name.lower()
        files.stop_worker()
    assert not host.process_alive(pid)


@windows
def test_a_sign_in_lets_the_browser_leave_the_job(tmp_path):
    from packages.resume_core import winjob

    marker = tmp_path / "browser.pid"
    source = ("import subprocess, sys\n"
              "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
              f"open({str(marker)!r}, 'w').write(str(child.pid))\n")
    with OperationFiles(tmp_path / "operations").open() as files:
        process = files.spawn(host.Confined(PYTHON, breakaway=True), ("-c", source), capture=False)
        process.wait(timeout=20)
        files.stop_worker()
    pid = int(marker.read_text())
    try:
        assert winjob.process_alive(pid)
    finally:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


@windows
def test_the_job_caps_a_worker_memory(tmp_path):
    source = "x = bytearray(512 * 1024 * 1024)"
    with pytest.raises(SpikeError, match="CLI_FAILED"):
        run(tmp_path / "capped", source, executable=host.Confined(PYTHON, memory=128 * 1024 * 1024))


@windows
def test_listeners_and_working_set_are_read(tmp_path):
    from packages.resume_core import winjob

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        assert os.getpid() in winjob.listening_pids()
    with OperationFiles(tmp_path / "operations").open() as files:
        process = files.spawn(PYTHON, ("-c", "import time; time.sleep(5)"), capture=False)
        assert (host.resident_kb(process) or 0) > 1000
        files.stop_worker()
