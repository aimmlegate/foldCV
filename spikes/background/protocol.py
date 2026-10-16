"""Executable protocol fixture, deliberately separate from the future publisher."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from packages.resume_core.background_limits import LIMITS
from packages.resume_core.storage import atomic_write, private_directory

from .harness import Clock, Hooks


class ProtocolProbe:
    def __init__(self, root: Path, clock: Clock, hooks: Hooks):
        self.root = private_directory(root)
        self.clock, self.hooks = clock, hooks
        self.lock = asyncio.Lock()
        self.runtime_alive = True
        self.authority = True
        self.proposal = None
        self.barrier = "idle"
        self.generation = 0
        self.cursor = 0
        self.acked_cursor = 0
        self.deadline = 0
        self.visible = "original"
        self.draft = None
        self.callback_generation = 0
        self.saved = self.read("canonical", {"value": "original", "mutations": []})

    def read(self, name, default):
        path = self.root / (name + ".json")
        return json.loads(path.read_text()) if path.exists() else default

    def write(self, name, value):
        atomic_write(self.root / (name + ".json"), json.dumps(value, sort_keys=True).encode())

    async def propose(self, proposal="proposal-1"):
        if self.proposal is not None and self.proposal != proposal:
            raise ValueError("one accepted proposal per turn; no unsaved edit chain")
        self.proposal = proposal
        self.write("binding", {"proposal": proposal, "payloadRef": "single-journal-payload", "authority": "active"})
        await self.hooks.hit("proposal_durable")

    def finish_runtime(self):
        self.runtime_alive = False

    async def ack(self):
        await self.hooks.hit("composition_end")
        self.generation += 1
        self.callback_generation = self.generation
        self.barrier = "acked"
        self.deadline = self.clock.elapsed_ms + LIMITS.local_barrier_ms
        await self.hooks.hit("local_barrier_acquired")
        await self.hooks.hit("final_flush_started")
        self.acked_cursor = self.cursor
        self.write("touches", {"cursor": self.cursor, "generation": self.generation})
        await self.hooks.hit("touch_watermark_durable")
        await self.hooks.hit("barrier_acked")

    async def timeout(self):
        async with self.lock:
            if self.clock.elapsed_ms < self.deadline:
                return
            self.callback_generation += 1
            if self.barrier == "acked":
                self.barrier = "revoked"
            else:
                self.barrier = "recovering"

    async def type(self, text):
        if self.barrier in {"acked", "commit_claimed"}:
            raise ValueError("protected canonical buffer cannot accept input")
        self.cursor += 1
        self.visible = text
        if self.barrier == "recovering":
            self.draft = {"text": text, "cursor": self.cursor, "base": "original"}
            self.write("draft", self.draft)
            await self.hooks.hit("draft_checkpointed")

    async def apply(self):
        await self.hooks.hit("before_commit_claim")
        async with self.lock:
            if not self.authority or self.proposal is None:
                return "cancelled"
            if "mutation-1" in self.saved["mutations"]:
                return self.read("receipt", None)
            if self.barrier != "acked" or self.clock.elapsed_ms >= self.deadline:
                return "waiting_for_sync"
            self.barrier = "commit_claimed"
        await self.hooks.hit("commit_claimed")
        self.saved = {"value": "saved result", "mutations": ["mutation-1"]}
        self.write("canonical", self.saved)
        await self.hooks.hit("workspace_durable")
        receipt = {"mutation": "mutation-1", "sha256": hashlib.sha256(json.dumps(self.saved, sort_keys=True).encode()).hexdigest()}
        self.write("receipt", receipt)
        await self.hooks.hit("receipt_stored")
        return receipt

    async def adopt(self, receipt, callback_generation):
        await self.hooks.hit("adoption_started")
        if (receipt is None or callback_generation != self.callback_generation or self.cursor != self.acked_cursor
                or self.barrier == "recovering" or receipt != self.read("receipt", None)):
            return False
        self.visible = self.saved["value"]
        self.barrier = "resolved"
        return True
