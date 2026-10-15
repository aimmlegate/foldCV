"""Durable sequences wake one owner stream; disconnect never resumes inference."""

import asyncio
from datetime import datetime, timezone
import secrets

from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.models.agent import TERMINAL_RUNS, wire_bytes


class AgentEvents:
    def __init__(self):
        self.listeners = {}

    def changed(self, run_id):
        current = self.listeners.get(run_id)
        if current is not None:
            loop, event, _ = current
            if not loop.is_closed():
                loop.call_soon_threadsafe(event.set)

    def owner(self, service, project_id, run_id, request):
        service.leases.require(project_id, request.owner)
        _, run, journal = run_in(service.store.load(project_id), run_id)
        if request.owner.epoch != run.owner_epoch:
            raise AgentFailure("AGENT_OWNER_MISMATCH")
        latest = journal.events[-1].root.sequence if journal.events else 0
        if request.after_sequence > latest:
            raise AgentFailure("AGENT_RESYNC_REQUIRED")
        remaining = [item.root.sequence for item in journal.events if item.root.sequence > request.after_sequence]
        if remaining and remaining != list(range(request.after_sequence + 1, latest + 1)):
            raise AgentFailure("AGENT_RESYNC_REQUIRED")
        return run, journal

    async def stream(self, service, project_id, run_id, request):
        self.owner(service, project_id, run_id, request)
        key, event = secrets.token_hex(12), asyncio.Event()
        prior = self.listeners.get(run_id)
        if prior is not None:
            prior[0].call_soon_threadsafe(prior[1].set)
        self.listeners[run_id] = (asyncio.get_running_loop(), event, key)
        sequence, sent = request.after_sequence, 0
        try:
            while self.listeners.get(run_id, (None, None, None))[2] == key:
                event.clear()
                try:
                    run, journal = self.owner(service, project_id, run_id, request)
                except AgentFailure:
                    return
                for item in journal.events:
                    if item.root.sequence <= sequence:
                        continue
                    if item.root.sequence != sequence + 1:
                        return
                    raw = wire_bytes(item) + b"\n"
                    if sent + len(raw) > 256 * 1024:
                        return
                    sent += len(raw)
                    sequence = item.root.sequence
                    yield raw
                if run.state in TERMINAL_RUNS or datetime.now(timezone.utc) >= datetime.fromisoformat(run.deadline):
                    return
                try:
                    await asyncio.wait_for(event.wait(), 1)
                except asyncio.TimeoutError:
                    if sent >= 256 * 1024:
                        return
                    sent += 1
                    yield b"\n"
        finally:
            if self.listeners.get(run_id, (None, None, None))[2] == key:
                self.listeners.pop(run_id, None)
