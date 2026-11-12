"""Bounded child I/O in cli/process_runner: large assistant frames and separate stdout and stderr limits."""

from pathlib import Path
import sys
import threading
import time

import pytest

from resume_api.cli.process_runner import ProcessRunner
from resume_api.lifecycle import OperationFiles, SpikeError


def run(root, source, **options):
    with OperationFiles(root).open() as files:
        return ProcessRunner(Path(sys.executable)).run(files, ("-c", source),
            cancel=threading.Event(), deadline=time.monotonic() + 5, **options)


def test_large_agent_frames_do_not_enlarge_default_metadata_frames(tmp_path):
    source = "import sys;sys.stdout.buffer.write(b'x'*70000+b'\\n')"
    with pytest.raises(SpikeError, match="OUTPUT_TOO_LARGE|INVALID_RESULT"):
        run(tmp_path / "old", source, on_line=lambda _raw: None)
    frames = []
    result, _ = run(tmp_path / "agent", source, max_line=131072,
                    on_line=lambda raw: frames.append(raw))
    assert frames == [b"x" * 70000]
    assert result == b"x" * 70000 + b"\n"


@pytest.mark.parametrize(("descriptor", "option"), [(1, "max_stdout"), (2, "max_stderr")])
def test_each_stream_has_its_own_byte_boundary(tmp_path, descriptor, option):
    result = run(tmp_path / "exact", f"import os;os.write({descriptor},b'x'*1024)",
                 max_output=10000, **{option: 1024})
    assert result[descriptor - 1] == b"x" * 1024
    with pytest.raises(SpikeError, match="OUTPUT_TOO_LARGE"):
        run(tmp_path / "over", f"import os;os.write({descriptor},b'x'*1025)",
            max_output=10000, **{option: 1024})


def test_a_windows_cleanup_does_not_wait_for_a_pipe_another_program_holds(monkeypatch, tmp_path):
    from resume_api import lifecycle

    release = threading.Event()

    class Held:
        closed = False

        def close(self):
            release.wait(5)
            self.closed = True

    class Worker:
        stdin, stdout, stderr = Held(), Held(), Held()

    monkeypatch.setattr(lifecycle.host, "WINDOWS", True)
    monkeypatch.setattr(lifecycle, "stop_group", lambda _process: None)
    files = OperationFiles(tmp_path)
    files.process = Worker()
    started = time.monotonic()
    files.stop_worker(final=False)
    assert time.monotonic() - started < 1 and files.process is None
    release.set()
    for _ in range(100):
        if all(stream.closed for stream in (Worker.stdin, Worker.stdout, Worker.stderr)):
            break
        time.sleep(0.01)
    assert all(stream.closed for stream in (Worker.stdin, Worker.stdout, Worker.stderr))


def test_a_child_silent_for_the_idle_limit_ends_as_stalled_and_a_talking_one_runs_on(tmp_path):
    """A model call that hangs on its connection ends at the idle limit, long before the operation's deadline."""
    started = time.monotonic()
    with pytest.raises(SpikeError, match="STALLED"):
        run(tmp_path / "silent", "import time;time.sleep(4)", idle_seconds=0.5)
    assert time.monotonic() - started < 3
    # Bytes, not text: a text stdout on Windows writes \r\n.
    result, _ = run(tmp_path / "talking", "import sys,time\nfor _ in range(4):\n sys.stdout.buffer.write(b'tick\\n');sys.stdout.buffer.flush();time.sleep(0.2)",
                    idle_seconds=0.5)
    assert result == b"tick\n" * 4


def test_the_idle_limit_must_be_a_positive_finite_number(tmp_path):
    for value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(SpikeError, match="INVALID_LIMIT"):
            run(tmp_path / "limit", "print(1)", idle_seconds=value)


def test_the_windows_pipe_threads_end_a_silent_child_as_stalled_too():
    """Windows reads the pipes on threads (select() takes only sockets): the idle limit holds there as well."""
    import subprocess
    runner = ProcessRunner(Path(sys.executable))

    def exchange(source):
        process = subprocess.Popen([sys.executable, "-c", source], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            return runner._exchange_threads(process, bytearray(), True, time.monotonic() + 5, threading.Event(), None,
                                            None, 10_000, 10_000, None, None, idle_seconds=0.5)
        finally:
            process.kill()
            process.wait(5)
    started = time.monotonic()
    with pytest.raises(SpikeError, match="STALLED"):
        exchange("import time;time.sleep(4)")
    assert time.monotonic() - started < 3
    result, _ = exchange("import sys,time\nfor _ in range(4):\n sys.stdout.buffer.write(b'tick\\n');sys.stdout.buffer.flush();time.sleep(0.2)")
    assert result == b"tick\n" * 4
