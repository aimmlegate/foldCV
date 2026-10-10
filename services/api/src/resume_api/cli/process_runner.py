"""Bounded child I/O under the service's operation ownership."""

from __future__ import annotations

import math
import os
from pathlib import Path
import selectors
import subprocess
import threading
import time
from typing import Callable

from resume_api.lifecycle import OperationFiles, SpikeError


MAX_OUTPUT = 262_144
MAX_LINE = 65_536


class ProcessExit(SpikeError):
    def __init__(self, stdout: bytes, stderr: bytes):
        super().__init__("CLI_FAILED")
        self.stdout = stdout
        self.stderr = stderr


class ProcessRunner:
    def __init__(self, executable: Path, *, clock: Callable[[], float] = time.monotonic):
        self.executable = executable
        self.clock = clock

    def run(self, files: OperationFiles, arguments: tuple[str, ...], *, data: bytes = b"",
            deadline: float, cancel: threading.Event,
            on_line: Callable[[bytes], bytes | None] | None = None,
            interactive: bool = False, max_output: int = MAX_OUTPUT) -> tuple[bytes, bytes]:
        if not math.isfinite(deadline):
            raise SpikeError("INVALID_LIMIT")
        self._check(deadline, cancel)
        process: subprocess.Popen[bytes] | None = None
        output = bytearray()
        errors = bytearray()
        pending = bytearray(data)
        line = bytearray()
        close_input = not interactive
        try:
            process = files.spawn(self.executable, arguments)
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None
            with selectors.DefaultSelector() as selector:
                for stream, kind in ((process.stdin, "stdin"), (process.stdout, "stdout"), (process.stderr, "stderr")):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_WRITE if kind == "stdin" else selectors.EVENT_READ, kind)
                while selector.get_map() or process.poll() is None:
                    self._check(deadline, cancel)
                    for key, _ in selector.select(min(0.02, max(0, deadline - self.clock()))):
                        stream = key.fileobj
                        kind = key.data
                        if kind == "stdin":
                            if pending:
                                try:
                                    sent = os.write(stream.fileno(), pending[:4096])
                                    del pending[:sent]
                                except BrokenPipeError:
                                    pending.clear()
                            if not pending:
                                selector.unregister(stream)
                                if close_input:
                                    stream.close()
                            continue
                        chunk = os.read(stream.fileno(), 4096)
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        target = output if kind == "stdout" else errors
                        target.extend(chunk)
                        if len(output) + len(errors) > max_output:
                            raise SpikeError("OUTPUT_TOO_LARGE")
                        if kind == "stdout" and on_line is not None:
                            line.extend(chunk)
                            while b"\n" in line:
                                raw, _, rest = line.partition(b"\n")
                                line = bytearray(rest)
                                if not raw or len(raw) > MAX_LINE:
                                    raise SpikeError("INVALID_RESULT")
                                reply = on_line(bytes(raw))
                                if reply is not None:
                                    pending.extend(reply)
                                    close_input = not reply
                                    if stream.closed or process.stdin.closed:
                                        raise SpikeError("INVALID_RESULT")
                                    if process.stdin not in [entry.fileobj for entry in selector.get_map().values()]:
                                        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
                            if len(line) > MAX_LINE:
                                raise SpikeError("OUTPUT_TOO_LARGE")
                self._check(deadline, cancel)
                if line:
                    raise SpikeError("INCOMPLETE_STREAM")
                if process.returncode:
                    raise ProcessExit(bytes(output), bytes(errors))
                return bytes(output), bytes(errors)
        except FileNotFoundError:
            raise SpikeError("CLI_MISSING") from None
        except (OSError, ValueError):
            raise SpikeError("CLI_FAILED") from None
        finally:
            if process is not None:
                files.stop_worker(final=False)

    def _check(self, deadline: float, cancel: threading.Event) -> None:
        if cancel.is_set():
            raise SpikeError("CANCELLED")
        if self.clock() >= deadline:
            raise SpikeError("DEADLINE_EXCEEDED")
