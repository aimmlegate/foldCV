"""Owned nonblocking JSON-line pipes with bounded queues and verified cleanup."""

import asyncio
from collections import deque
import json
import os

from resume_api.lifecycle import OperationFiles
from .appserver_protocol import ProtocolLimits, TransportFailure


class OwnedRpcPipe:
    def __init__(self, root, launch, *, limits=ProtocolLimits(), queue_frames=72, queue_bytes=6 * 1024 * 1024):
        self.files = OperationFiles(root)
        self.launch, self.limits = launch, limits
        self.queue_frames, self.queue_bytes = queue_frames, queue_bytes
        self.frames, self.frame_bytes = deque(), 0
        self.stdout, self.stderr, self.input = bytearray(), bytearray(), bytearray()
        self.changed = asyncio.Event()
        self.error, self.process, self.operation = None, None, None
        self.loop, self.context, self.poller = None, None, None
        self.stdout_eof = self.stderr_eof = self.closed = False
        self.cleanup_verified = False
        self.exit_status = None
        self.witness = None

    async def start(self):
        if self.process is not None or self.closed:
            raise TransportFailure("DUPLICATE_START")
        self.loop = asyncio.get_running_loop()
        self.context = self.files.open()
        self.context.__enter__()
        self.operation = self.files.path
        try:
            with self.launch(self.operation) as (executable, arguments, environment):
                self.process = self.files.spawn(executable, arguments, environment=environment)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                os.set_blocking(stream.fileno(), False)
            self.loop.add_reader(self.process.stdout.fileno(), self.read_output)
            self.loop.add_reader(self.process.stderr.fileno(), self.read_error)
            self.poll()
        except BaseException:
            await self.close()
            raise
        return self

    def fail(self, code):
        if self.error is None:
            self.error = TransportFailure(code)
        if self.process is not None and self.loop is not None:
            for stream in (self.process.stdout, self.process.stderr):
                if not stream.closed:
                    self.loop.remove_reader(stream.fileno())
            if not self.process.stdin.closed:
                self.loop.remove_writer(self.process.stdin.fileno())
        self.changed.set()

    def read_output(self):
        try:
            chunk = os.read(self.process.stdout.fileno(), 4096)
            if not chunk:
                self.loop.remove_reader(self.process.stdout.fileno())
                self.stdout_eof = True
                if self.stdout:
                    self.fail("INCOMPLETE_FRAME")
                self.changed.set()
                return
            self.stdout.extend(chunk)
            while b"\n" in self.stdout:
                raw, _, rest = self.stdout.partition(b"\n")
                self.stdout = bytearray(rest)
                if not raw or len(raw) > self.limits.frame_bytes:
                    self.fail("FRAME_LIMIT")
                    return
                if len(self.frames) >= self.queue_frames or self.frame_bytes + len(raw) > self.queue_bytes:
                    self.fail("FRAME_QUEUE_LIMIT")
                    return
                self.frames.append(bytes(raw))
                self.frame_bytes += len(raw)
            if len(self.stdout) > self.limits.frame_bytes:
                self.fail("FRAME_LIMIT")
            self.changed.set()
        except (OSError, ValueError):
            self.fail("PIPE_READ_FAILED")

    def read_error(self):
        try:
            chunk = os.read(self.process.stderr.fileno(), 4096)
            if not chunk:
                self.loop.remove_reader(self.process.stderr.fileno())
                self.stderr_eof = True
                self.changed.set()
                return
            if len(self.stderr) + len(chunk) > 256 * 1024:
                self.fail("STDERR_LIMIT")
                return
            self.stderr.extend(chunk)
        except (OSError, ValueError):
            self.fail("PIPE_READ_FAILED")

    def poll(self):
        if self.closed:
            return
        self.exit_status = self.process.poll()
        if self.exit_status is not None:
            self.changed.set()
            return
        self.poller = self.loop.call_later(0.02, self.poll)

    def send(self, frame):
        if self.closed or self.error is not None or self.exit_status is not None:
            raise TransportFailure("SERVER_CLOSED")
        raw = json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        if len(raw) - 1 > self.limits.frame_bytes or len(self.input) + len(raw) > self.queue_bytes:
            raise TransportFailure("INPUT_LIMIT")
        self.input.extend(raw)
        self.loop.add_writer(self.process.stdin.fileno(), self.write_input)

    def write_input(self):
        try:
            if self.input:
                size = os.write(self.process.stdin.fileno(), self.input[:4096])
                del self.input[:size]
            if not self.input:
                self.loop.remove_writer(self.process.stdin.fileno())
        except BlockingIOError:
            pass
        except (OSError, ValueError):
            self.fail("PIPE_WRITE_FAILED")

    async def receive(self):
        while True:
            if self.frames:
                raw = self.frames.popleft()
                self.frame_bytes -= len(raw)
                return raw
            if self.error is not None:
                raise self.error
            if self.closed:
                raise TransportFailure("SERVER_CLOSED")
            if self.exit_status is not None and self.stdout_eof and self.stderr_eof:
                raise TransportFailure("SERVER_EXITED")
            self.changed.clear()
            if self.frames or self.error is not None or self.exit_status is not None and self.stdout_eof and self.stderr_eof:
                continue
            await self.changed.wait()

    async def close(self):
        if self.closed:
            return self.witness
        if self.poller is not None:
            self.poller.cancel()
        if self.loop is not None and self.process is not None:
            for stream in (self.process.stdout, self.process.stderr):
                if not stream.closed:
                    self.loop.remove_reader(stream.fileno())
            if not self.process.stdin.closed:
                self.loop.remove_writer(self.process.stdin.fileno())
        try:
            try:
                await asyncio.to_thread(self.files.stop_worker)
            finally:
                if self.context is not None:
                    context, self.context = self.context, None
                    await asyncio.to_thread(context.__exit__, None, None, None)
            self.cleanup_verified = self.process is None or self.process.poll() is not None
            self.cleanup_verified = self.cleanup_verified and (self.operation is None or not self.operation.exists())
            if not self.cleanup_verified:
                raise TransportFailure("CLEANUP_UNVERIFIED")
            self.closed = True
            self.frames.clear()
            self.frame_bytes = 0
            self.stdout.clear()
            self.stderr.clear()
            self.input.clear()
        except BaseException:
            self.fail("CLEANUP_FAILED")
            raise
        finally:
            self.changed.set()
        self.witness = {"processPid": self.process.pid if self.process is not None else None,
            "ownedGroupCleanupVerified": self.cleanup_verified, "operationRemoved": self.operation is None or not self.operation.exists()}
        return self.witness
