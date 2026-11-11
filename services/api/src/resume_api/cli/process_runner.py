"""Bounded child I/O under the service's operation ownership."""

from __future__ import annotations

import math
import os
from pathlib import Path
import queue
import re
import selectors
import subprocess
import threading
import time
from typing import Callable

from packages.resume_core import host
from resume_api.app_log import EVENTS, failure, masked
from resume_api.lifecycle import OperationFiles, SpikeError


MAX_OUTPUT = 262_144
MAX_LINE = 65_536
# The log names a run by its program and leading words such as `auth status` or `-p`; prompts and values never match.
WORD = re.compile(r"-{0,2}[a-z][a-z0-9-]{0,30}")
# Runs whose error output is about the program, not about content: version, help, sign-in and sign-out, flags,
# downloads.
TOLD = frozenset({"--version", "--help", "auth", "login", "logout", "features"})
TOLD_PROGRAMS = frozenset({"curl"})
TAIL = 1000


class ProcessExit(SpikeError):
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int | None = None):
        super().__init__("CLI_FAILED")
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def command_words(arguments: tuple[str, ...]) -> str:
    words = []
    for argument in arguments[:2]:
        if not WORD.fullmatch(argument):
            break
        words.append(argument)
    return " ".join(words)


class ProcessRunner:
    def __init__(self, executable: Path, *, clock: Callable[[], float] = time.monotonic,
                 launch: Callable[[Path, tuple[str, ...], Path],
                                  tuple[Path, tuple[str, ...], dict[str, str]]] | None = None,
                 workdir: Path | None = None):
        self.executable = executable
        self.clock = clock
        self.launch = launch
        # The process cwd; None runs each call in its own operation directory.
        self.workdir = workdir

    def run(self, files: OperationFiles, arguments: tuple[str, ...], **options) -> tuple[bytes, bytes]:
        """One child run (see `_run`), with a line in the app log: the program, its leading words, the outcome and
        the time; a failed run of a program in TOLD adds the end of its error output."""
        started = time.monotonic()
        try:
            stdout, stderr = self._run(files, arguments, **options)
        except BaseException as error:
            outcome, told = failure(error), b""
            if isinstance(error, ProcessExit):
                outcome, told = f"exit {error.returncode}", error.stderr
            self._log(arguments, outcome, time.monotonic() - started, told)
            raise
        self._log(arguments, "ok", time.monotonic() - started, b"")
        return stdout, stderr

    def _log(self, arguments: tuple[str, ...], outcome: str, seconds: float, told: bytes) -> None:
        program = Path(str(self.executable)).name
        line = f"{program} {command_words(arguments)}".rstrip() + f": {outcome} in {seconds:.1f} s"
        words = command_words(arguments).split()
        if told and (Path(program).stem.lower() in TOLD_PROGRAMS or (words and words[0] in TOLD)):
            text = masked(told[-TAIL:].decode("utf-8", "replace")).strip()
            line += "\n" + text
        EVENTS.getChild("cli").info("%s", line)

    def _run(self, files: OperationFiles, arguments: tuple[str, ...], *, data: bytes = b"",
            deadline: float, cancel: threading.Event,
            on_line: Callable[[bytes], bytes | None] | None = None,
            interactive: bool = False, max_output: int = MAX_OUTPUT,
            max_line: int = MAX_LINE, max_stdout: int | None = None,
            max_stderr: int | None = None,
            poll_input: Callable[[], bytes | None] | None = None,
            before_cleanup: Callable[[], None] | None = None,
            on_spawn: Callable[[], None] | None = None,
            on_output: Callable[[str, bytes], None] | None = None,
            idle_seconds: float | None = None) -> tuple[bytes, bytes]:
        """`idle_seconds`: the longest silence the child may keep (no byte on either stream) before the run ends
        as STALLED; a model call that hangs on its connection stops here, not at the operation's deadline."""
        if idle_seconds is not None and (not math.isfinite(idle_seconds) or idle_seconds <= 0):
            raise SpikeError("INVALID_LIMIT")
        if (not math.isfinite(deadline) or any(type(value) is not int or value <= 0
                for value in (max_output, max_line, max_stdout, max_stderr) if value is not None)):
            raise SpikeError("INVALID_LIMIT")
        self._check(deadline, cancel)
        process: subprocess.Popen[bytes] | None = None
        output = bytearray()
        errors = bytearray()
        pending = bytearray(data)
        line = bytearray()
        close_input = not interactive
        try:
            executable, args, environment = (self.launch(self.executable, arguments, files.path)
                                             if self.launch is not None and files.path is not None
                                             else (self.executable, arguments, None))
            process = files.spawn(executable, args, environment=environment, cwd=self.workdir)
            if on_spawn is not None:
                on_spawn()
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None
            if host.WINDOWS:
                return self._exchange_threads(process, pending, close_input, deadline, cancel, on_line,
                                              poll_input, max_output, max_line, max_stdout, max_stderr, on_output,
                                              idle_seconds)
            with selectors.DefaultSelector() as selector:
                for stream, kind in ((process.stdin, "stdin"), (process.stdout, "stdout"), (process.stderr, "stderr")):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_WRITE if kind == "stdin" else selectors.EVENT_READ, kind)
                heard = self.clock()
                while selector.get_map() or process.poll() is None:
                    self._check(deadline, cancel)
                    if idle_seconds is not None and self.clock() - heard >= idle_seconds:
                        raise SpikeError("STALLED")
                    if poll_input is not None:
                        reply = poll_input()
                        if reply is not None:
                            pending.extend(reply)
                            close_input = not reply
                            if process.stdin.closed:
                                raise SpikeError("INVALID_RESULT")
                            if process.stdin not in [entry.fileobj for entry in selector.get_map().values()]:
                                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
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
                        heard = self.clock()
                        if len(output) + len(errors) > max_output:
                            raise SpikeError("OUTPUT_TOO_LARGE")
                        if ((max_stdout is not None and len(output) > max_stdout)
                                or (max_stderr is not None and len(errors) > max_stderr)):
                            raise SpikeError("OUTPUT_TOO_LARGE")
                        if on_output is not None:
                            on_output(kind, chunk)
                        if kind == "stdout" and on_line is not None:
                            line.extend(chunk)
                            while b"\n" in line:
                                raw, _, rest = line.partition(b"\n")
                                line = bytearray(rest)
                                if not raw:
                                    raise SpikeError("INVALID_RESULT")
                                if len(raw) > max_line:
                                    raise SpikeError("OUTPUT_TOO_LARGE")
                                reply = on_line(bytes(raw))
                                if reply is not None:
                                    pending.extend(reply)
                                    close_input = not reply
                                    if stream.closed or process.stdin.closed:
                                        raise SpikeError("INVALID_RESULT")
                                    if process.stdin not in [entry.fileobj for entry in selector.get_map().values()]:
                                        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
                            if len(line) > max_line:
                                raise SpikeError("OUTPUT_TOO_LARGE")
                self._check(deadline, cancel)
                if line:
                    raise SpikeError("INCOMPLETE_STREAM")
                if process.returncode:
                    raise ProcessExit(bytes(output), bytes(errors), process.returncode)
                return bytes(output), bytes(errors)
        except FileNotFoundError:
            raise SpikeError("CLI_MISSING") from None
        except (OSError, ValueError):
            raise SpikeError("CLI_FAILED") from None
        finally:
            if process is not None:
                try:
                    if before_cleanup is not None:
                        before_cleanup()
                finally:
                    files.stop_worker(final=False)

    def _exchange_threads(self, process, pending, close_input, deadline, cancel, on_line, poll_input,
                          max_output, max_line, max_stdout, max_stderr, on_output=None,
                          idle_seconds=None) -> tuple[bytes, bytes]:
        """The selector loop above for Windows, where select() takes only sockets: threads move the pipe data.
        A reply after stdin was asked to close is refused, as one after the close is on macOS."""
        events: queue.Queue[tuple[str, bytes]] = queue.Queue()
        writes: queue.Queue[bytes | None] = queue.Queue()

        def read(stream, kind):
            try:
                while chunk := os.read(stream.fileno(), 4096):
                    events.put((kind, chunk))
            except (OSError, ValueError):
                pass  # Closed by the cleanup.
            events.put((kind, b""))

        def write():
            while (item := writes.get()) is not None:
                try:
                    view = memoryview(item)
                    while view:
                        view = view[os.write(process.stdin.fileno(), view[:65536]):]
                except (OSError, ValueError):
                    pass  # The child stopped reading; the rest is dropped, as BrokenPipeError does above.
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass

        closing = False

        def send(reply: bytes) -> None:
            nonlocal closing
            if closing:
                raise SpikeError("INVALID_RESULT")
            if reply:
                writes.put(reply)
            else:
                writes.put(None)
                closing = True

        for target, arguments in ((read, (process.stdout, "stdout")), (read, (process.stderr, "stderr")),
                                  (write, ())):
            threading.Thread(target=target, args=arguments, daemon=True).start()
        if pending:
            writes.put(bytes(pending))
        if close_input:
            send(b"")
        try:
            return self._pump(process, events, send, deadline, cancel, on_line, poll_input, max_output, max_line,
                              max_stdout, max_stderr, on_output, idle_seconds)
        finally:
            if not closing:
                writes.put(None)

    def _pump(self, process, events, send, deadline, cancel, on_line, poll_input, max_output, max_line, max_stdout,
              max_stderr, on_output=None, idle_seconds=None) -> tuple[bytes, bytes]:
        output, errors, line = bytearray(), bytearray(), bytearray()
        open_streams = {"stdout", "stderr"}
        heard = self.clock()
        while open_streams or process.poll() is None:
            self._check(deadline, cancel)
            if idle_seconds is not None and self.clock() - heard >= idle_seconds:
                raise SpikeError("STALLED")
            if poll_input is not None:
                reply = poll_input()
                if reply is not None:
                    send(reply)
            try:
                kind, chunk = events.get(timeout=min(0.02, max(0, deadline - self.clock())))
            except queue.Empty:
                continue
            if not chunk:
                open_streams.discard(kind)
                continue
            target = output if kind == "stdout" else errors
            target.extend(chunk)
            heard = self.clock()
            if len(output) + len(errors) > max_output:
                raise SpikeError("OUTPUT_TOO_LARGE")
            if ((max_stdout is not None and len(output) > max_stdout)
                    or (max_stderr is not None and len(errors) > max_stderr)):
                raise SpikeError("OUTPUT_TOO_LARGE")
            if on_output is not None:
                on_output(kind, chunk)
            if kind == "stdout" and on_line is not None:
                line.extend(chunk)
                while b"\n" in line:
                    raw, _, rest = line.partition(b"\n")
                    line = bytearray(rest)
                    if not raw:
                        raise SpikeError("INVALID_RESULT")
                    if len(raw) > max_line:
                        raise SpikeError("OUTPUT_TOO_LARGE")
                    reply = on_line(bytes(raw))
                    if reply is not None:
                        send(reply)
                if len(line) > max_line:
                    raise SpikeError("OUTPUT_TOO_LARGE")
        self._check(deadline, cancel)
        if line:
            raise SpikeError("INCOMPLETE_STREAM")
        if process.returncode:
            raise ProcessExit(bytes(output), bytes(errors), process.returncode)
        return bytes(output), bytes(errors)

    def _check(self, deadline: float, cancel: threading.Event) -> None:
        if cancel.is_set():
            raise SpikeError("CANCELLED")
        if self.clock() >= deadline:
            raise SpikeError("DEADLINE_EXCEEDED")
