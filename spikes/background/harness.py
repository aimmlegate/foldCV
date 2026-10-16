"""Controlled hooks, fake clocks and strictly owned pipe peers for NB proofs."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import selectors
import shutil
import subprocess
import sys

from packages.resume_core.storage import atomic_write, locked_root, private_directory

DISPATCH_HOOKS = ("accepted_durable", "queue_eligible", "slot_granted", "before_spawn", "child_started",
    "proposal_durable", "cleanup_started", "children_verified_dead", "slot_released")
PUBLICATION_HOOKS = ("payload_stored", "binding_stored", "intent_stored", "before_commit_claim", "commit_claimed",
    "workspace_replaced", "workspace_durable", "generation_history_durable", "receipt_stored", "registry_updated", "event_emitted")
WRITER_HOOKS = ("composition_end", "local_barrier_acquired", "final_flush_started", "touch_watermark_durable",
    "barrier_acked", "adoption_started", "draft_checkpointed", "clean_detach_acked", "writer_resumed")
HOOKS = DISPATCH_HOOKS + PUBLICATION_HOOKS + WRITER_HOOKS
SYNTHETIC_SPAWN: ContextVar[tuple[str, ...] | None] = ContextVar("nb_synthetic_spawn", default=None)


class OfflineDenied(RuntimeError):
    pass


@dataclass
class Clock:
    elapsed_ms: int = 0
    wall_ms: int = 0

    def advance(self, elapsed_ms: int, *, wall_ms: int | None = None) -> None:
        if elapsed_ms < 0:
            raise ValueError("elapsed clock cannot go backwards")
        self.elapsed_ms += elapsed_ms
        self.wall_ms += elapsed_ms if wall_ms is None else wall_ms


@dataclass
class Hold:
    reached: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)


class Hooks:
    def __init__(self):
        self.holds: dict[str, Hold] = {}
        self.log: list[str] = []

    def hold(self, name: str) -> Hold:
        if name not in HOOKS or name in self.holds:
            raise AssertionError("unknown or duplicate controlled hook")
        result = self.holds[name] = Hold()
        return result

    async def hit(self, name: str) -> None:
        if name not in HOOKS:
            raise AssertionError("unknown boundary")
        self.log.append(name)
        if hold := self.holds.get(name):
            hold.reached.set()
            await hold.release.wait()

    def verify(self) -> None:
        if any(not hold.reached.is_set() or not hold.release.is_set() for hold in self.holds.values()):
            raise AssertionError("unreached or unreleased controlled boundary")


@dataclass
class ScriptedPeer:
    project: str
    job: str
    hooks: Hooks
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    calls: list[tuple[str, str]] = field(default_factory=list)
    tasks: set[asyncio.Task] = field(default_factory=set)

    async def call(self, project: str, job: str) -> str:
        if (project, job) != (self.project, self.job) or self.cancelled.is_set():
            raise OfflineDenied("synthetic capability scope or cancellation")
        self.calls.append((project, job))
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            await self.hooks.hit("proposal_durable")
            if self.cancelled.is_set():
                raise OfflineDenied("synthetic capability cancelled during call")
            return f"synthetic:{project}:{job}"
        finally:
            self.tasks.remove(task)


class PipeChild:
    def __init__(self, process: subprocess.Popen[str], cleanup_failure=lambda: None):
        self.process = process
        self.cleanup_failure = cleanup_failure
        self.closed = False
        self.stopped_ack = False
        if self.read() != {"type": "ready", "protocol": "NB00a-pipe-v1"}:
            self.close()
            raise OfflineDenied("unexpected synthetic handshake")

    def read(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(10):
                raise AssertionError("synthetic pipe watchdog expired")
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError("synthetic child closed its pipe")
        return json.loads(line)

    def command(self, command: str):
        self.process.stdin.write(json.dumps({"command": command}) + "\n")
        self.process.stdin.flush()
        response = self.read()
        self.stopped_ack = response == {"type": "stopped"}
        return response

    def close(self):
        try:
            self._close()
        except BaseException:
            self.cleanup_failure()
            raise

    def _close(self):
        if self.closed:
            return
        if self.process.poll() is None and not self.stopped_ack:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            pipe.close()
        self.closed = True


class OfflineGuard:
    def __init__(self, root: Path, *, role="pipe"):
        self.root = private_directory(root).resolve()
        source_name = {"pipe": "fake_child.py", "publication": "fake_publication_child.py"}.get(role)
        if source_name is None:
            raise OfflineDenied("unregistered synthetic role")
        self.source = Path(__file__).with_name(source_name)
        self.child = self.root / "nb-synthetic-child.py"
        shutil.copyfile(self.source, self.child)
        self.child.chmod(0o400)
        self.sha256 = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.peers: list[ScriptedPeer] = []
        self.children: list[PipeChild] = []
        self.spawns = 0
        self.cleanup_fenced = False

    def inject(self, peer: ScriptedPeer):
        if type(peer) is not ScriptedPeer:
            raise OfflineDenied("only a registered scripted peer is allowed")
        self.peers.append(peer)
        return peer

    def provider(self, peer: object):
        if not any(peer is registered for registered in self.peers):
            raise OfflineDenied("production or uninjected provider is forbidden")
        return peer

    def network(self, destination: str):
        raise OfflineDenied("external transport is forbidden; inject a pipe peer")

    def spawn(self, executable: Path, *, env: dict[str, str] | None = None) -> PipeChild:
        if self.cleanup_fenced:
            raise OfflineDenied("synthetic cleanup ownership is fenced")
        if executable != self.child or executable.is_symlink() or not executable.resolve().is_relative_to(self.root):
            raise OfflineDenied("unregistered executable")
        if hashlib.sha256(executable.read_bytes()).hexdigest() != self.sha256:
            raise OfflineDenied("synthetic executable changed")
        if env is not None and env:
            raise OfflineDenied("inherited environment is forbidden")
        child_env = {"HOME": str(self.root), "LANG": "C.UTF-8"}
        arguments = [sys.executable, "-I", "-S", "-u", str(executable)]
        token = SYNTHETIC_SPAWN.set(tuple(arguments))
        try:
            process = subprocess.Popen(arguments, cwd=self.root, env=child_env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        finally:
            SYNTHETIC_SPAWN.reset(token)
        self.spawns += 1
        try:
            child = PipeChild(process, lambda: setattr(self, "cleanup_fenced", True))
        except BaseException:
            process.kill()
            process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()
            raise
        self.children.append(child)
        return child

    def close(self):
        for peer in self.peers:
            peer.cancelled.set()
        for child in self.children:
            child.close()
        leaked = [task for peer in self.peers for task in peer.tasks if not task.done()]
        for task in leaked:
            task.cancel()
        if leaked:
            raise AssertionError("scripted peer task leaked")
        for peer in self.peers:
            peer.hooks.verify()
        if any(child.process.poll() is None for child in self.children):
            raise AssertionError("owned synthetic child leaked")


class SyntheticAttempts:
    """Offline accounting fixture only; never accepts the real native ledger path."""

    def __init__(self, owned_root: Path, cap: int = 10):
        self.root = private_directory(owned_root / "synthetic-attempts")
        self.path = self.root / "fake-ledger.json"
        self.cap = cap

    def read(self):
        if not self.path.exists():
            return {"kind": "synthetic", "cap": self.cap, "attempts": {}}
        value = json.loads(self.path.read_text())
        if value.get("kind") != "synthetic" or value.get("cap") != self.cap:
            raise OfflineDenied("not a synthetic ledger")
        return value

    def spend(self, attempt: str, *, lost_ack: bool = False) -> bool:
        with locked_root(self.root, ".attempt.lock"):
            value = self.read()
            if attempt in value["attempts"]:
                return False
            if len(value["attempts"]) >= self.cap:
                raise OfflineDenied("synthetic budget exhausted")
            value["attempts"][attempt] = {"state": "spent"}
            atomic_write(self.path, json.dumps(value, sort_keys=True).encode())
        if lost_ack:
            raise OSError("injected lost spend acknowledgment")
        return True

    def mark(self, attempt: str, state: str):
        with locked_root(self.root, ".attempt.lock"):
            value = self.read()
            if attempt not in value["attempts"]:
                raise AssertionError("spawn cannot precede durable spending")
            value["attempts"][attempt]["state"] = state
            atomic_write(self.path, json.dumps(value, sort_keys=True).encode())
