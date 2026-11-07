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
