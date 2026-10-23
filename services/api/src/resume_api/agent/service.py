"""Supervise one captured assistant run, its editor owner and durable public events."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import threading
import time

from packages.resume_core.agent_store import AgentFailure, AgentStore, digest, identity, run_in
from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.models.agent import (
    AgentCapabilities, AgentError, AgentEvent, AgentModelCapability, AgentReference, AgentUsage, TERMINAL_RUNS,
)
from resume_api.cli.experimental_profile import BINARY_SHA256, VERSION
from resume_api.inference_admission import AdmissionCancelled, AdmissionTimeout, AdmissionBlocked, INFERENCE
from spikes.agent.profile import HOST_SHA256, MANIFEST_SHA256

from .leases import AgentLeases
from .runtime import RuntimeInput, RuntimeResult, BASE_INSTRUCTIONS, DEVELOPER_INSTRUCTIONS
from .admission import worker_slot

PROTOCOL_SHA256 = "26aaabfe28f09dc31c88045a92791b39c446918042a7f5b9c73960d29a0b091c"
CONFIG_SHA256 = digest({"runtime": "agent-v1", "host": "D086", "protocol": PROTOCOL_SHA256,
    "instructionsSha256": hashlib.sha256((BASE_INSTRUCTIONS + DEVELOPER_INSTRUCTIONS).encode()).hexdigest(),
    "hostSha256": HOST_SHA256, "manifestSha256": MANIFEST_SHA256,
    "approvals": "never/user", "sandbox": "read-only", "fallback": False})


@dataclass(frozen=True)
class AgentConnection:
    ready: bool
    models: tuple[str, ...]
    epoch: str
    reason: str | None = None


@dataclass
class RunControl:
    project_id: str
    run_id: str
    owner_epoch: int
    connection_epoch: str
    queued_at: float
    cancel: threading.Event = field(default_factory=threading.Event)
    revoked: threading.Event = field(default_factory=threading.Event)
    reason: str | None = None
    task: asyncio.Task | None = None
    result: RuntimeResult | None = None
    seed: object = None


class AgentService:
    def __init__(self, projects, runtime, connection, *, tools=None, cleanup_error=lambda _code: None,
                 lease_clock=time.monotonic):
        self.projects, self.runtime, self.connection, self.tools = projects, runtime, connection, tools
        self.store = AgentStore(projects.storage.root)
        self.settings = AgentSettingsStore(projects.storage.root)
        self.cleanup_error = cleanup_error
        self.controls = {}
        self.closed = False
        self.capability_states = {}
        self.startup_errors = {}
        self.unresolved = {}
        self.leases = AgentLeases(self.store, projects.state_lock, clock=lease_clock, active=self.active)
        from .publication import AgentPublication
        self.publication = AgentPublication(self)
        from .events import AgentEvents
        self.events = AgentEvents()

    def recover(self):
        self.unresolved, self.startup_errors = self.store.recover_all()
        self.leases.invalidate()
        self.publication.recover_all()

    def active(self, project_id):
        return any(control.project_id == project_id and control.task is not None and not control.task.done()
            for control in self.controls.values())

    def config_digest(self, allow_edits, allow_web):
        return digest({"base": CONFIG_SHA256, "allowEdits": allow_edits, "allowWeb": allow_web,
            "binary": self.binary_sha256, "tools": sorted(getattr(self.tools, "names", ()))})

    @property
    def binary_sha256(self):
        return getattr(getattr(self.runtime, "profile", None), "binary_sha256", BINARY_SHA256)

    def capability_key(self, epoch, model, allow_edits, allow_web):
        return (self.binary_sha256, PROTOCOL_SHA256, self.config_digest(allow_edits, allow_web), epoch, model)

    def capabilities(self, project_id=None, *, allow_edits=True, allow_web=True):
        connection = self.connection()
        settings = self.settings.load()
        reason = ("AGENT_DISABLED" if not settings.enabled else "AGENT_CLEANUP_FAILED" if INFERENCE.blocked else
            "AGENT_OUTCOME_UNKNOWN" if self.unresolved.get(project_id) else
            self.startup_errors.get(project_id) if project_id in self.startup_errors else
            "AGENT_RUNTIME_UNSUPPORTED" if self.runtime is None or self.tools is None else
            connection.reason or "AGENT_CONNECTION_UNAVAILABLE" if not connection.ready else
            "AGENT_MODEL_REQUIRED" if settings.selected_agent_model is None else
            "AGENT_MODEL_UNAVAILABLE" if settings.selected_agent_model not in connection.models else None)
        models = []
        for model in connection.models:
            state, error = self.capability_states.get(self.capability_key(connection.epoch, model, allow_edits, allow_web), ("unverified", None))
            models.append(AgentModelCapability(model=model, state=state, binarySha256=self.binary_sha256,
                protocolSha256=PROTOCOL_SHA256, configSha256=self.config_digest(allow_edits, allow_web), accountEpoch=connection.epoch,
                reason=AgentError(code=error) if error else None))
        selected = next((model for model in models if model.model == settings.selected_agent_model), None)
        if reason is None and selected is not None and selected.state == "incompatible":
            reason = "AGENT_MODEL_INCOMPATIBLE"
        return AgentCapabilities(schemaVersion=1, ready=reason is None, binaryVersion=getattr(getattr(self.runtime, "profile", None), "version", VERSION),
            binarySha256=self.binary_sha256, protocolSha256=PROTOCOL_SHA256, configSha256=self.config_digest(allow_edits, allow_web),
            connectionEpoch=connection.epoch, modes=["edit", "check_only"],
            tools=list(getattr(self.tools, "names", ())), webAvailable=self.runtime is not None,
            models=models, unavailable=AgentError(code=reason) if reason else None)

    def validate_new(self, project_id, request):
        if self.closed:
            raise AgentFailure("AGENT_CONNECTION_UNAVAILABLE")
        self.leases.require(project_id, request.owner)
        settings = self.settings.load()
        if settings.revision != request.settings_revision:
            raise AgentFailure("AGENT_SETTINGS_CONFLICT")
        capability = self.capabilities(project_id, allow_edits=request.allow_edits, allow_web=request.allow_web)
        if not capability.ready:
            raise AgentFailure(capability.unavailable.code)
        current = self.projects.read(project_id)
        if current.project is None or (current.project_revision, current.document_revision, current.project.facts.revision) != (
                request.project_revision, request.document_revision, request.facts_revision):
            raise AgentFailure("AGENT_STALE_READ")
        if self.projects.durability(project_id) != "durable":
            raise AgentFailure("AGENT_SAVE_FAILED")
        return settings, self.connection()

    def submit(self, project_id, request):
        with self.projects.state_lock:
            existing = self.store.find_request(project_id, request)
            if existing is not None:
                return existing, False
            # Catalog/project reads precede the store's non-reentrant file locks.
            settings, connection = self.validate_new(project_id, request)
            access = self.projects.catalog.get(project_id)
            if request.allow_edits and access.read_only:
                raise AgentFailure("AGENT_TOOL_DENIED")
            return self.store.submit(project_id, request, model=settings.selected_agent_model,
                connection_epoch=connection.epoch, access_revision=access.access_revision)

    def start(self, project_id, run_id, *, seed=None):
        if self.closed:
            raise AgentFailure("AGENT_CONNECTION_UNAVAILABLE")
        existing = self.controls.get(run_id)
        if existing is not None:
            return existing
        _, run, _ = run_in(self.store.load(project_id), run_id)
        if run.state in TERMINAL_RUNS:
            return None
        with self.projects.state_lock:
            self.leases.require(project_id, epoch=run.owner_epoch)
            control = RunControl(project_id, run_id, run.owner_epoch, run.connection_epoch, time.monotonic(), seed=seed)
            self.controls[run_id] = control
            control.task = asyncio.create_task(self._drive(control))
            return control

    def revoke(self, control, reason=None):
        with self.projects.state_lock:
            control.revoked.set()
            if reason is not None:
                control.reason = control.reason or reason
                control.cancel.set()

    def cancel(self, project_id, run_id, *, reason="AGENT_CANCELLED"):
        control = self.controls.get(run_id)
        if control is None:
            return self.store.finish(project_id, run_id, "cancelled", error=reason)
        if control is not None:
            if control.project_id != project_id:
                raise AgentFailure("AGENT_NOT_FOUND")
            self.revoke(control, reason)
        def cancelling(state):
            _, run, _ = run_in(state, run_id)
            if run.state not in TERMINAL_RUNS:
                run.state = "cancelling"
            return run
        return self.store.update(project_id, cancelling, terminal=True)

    def request_project_stop(self, project_id, *, reason="AGENT_PROJECT_DELETED"):
        with self.projects.state_lock:
            lease = self.leases.leases.get(project_id)
            if lease is not None:
                lease.expires = 0
            for control in self.controls.values():
                if control.project_id == project_id:
                    self.revoke(control, reason)

    def request_stop(self, *, reason="AGENT_CONNECTION_CHANGED"):
        self.leases.invalidate()
        for control in self.controls.values():
            self.revoke(control, reason)

    async def stop_project(self, project_id):
        tasks = [control.task for control in self.controls.values() if control.project_id == project_id
            and control.task is not None and control.task is not asyncio.current_task() and not control.task.done()]
        if tasks:
            await self._wait(tasks)

    async def stop_all(self, *, reason="AGENT_CONNECTION_CHANGED"):
        self.request_stop(reason=reason)
        await self._wait([control.task for control in self.controls.values() if control.task is not None and not control.task.done()])

    async def shutdown(self):
        self.closed = True
        await self.stop_all(reason="AGENT_INTERRUPTED")

    async def _wait(self, tasks):
        if not tasks:
            return
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.gather(*tasks, return_exceptions=True)), 5)
        except asyncio.TimeoutError:
            INFERENCE.block()
            self.cleanup_error("AGENT_CLEANUP_FAILED")
            raise AgentFailure("AGENT_CLEANUP_FAILED") from None

    def event(self, control, kind, payload, *, terminal=False):
        if control.cancel.is_set() and kind not in {"edit.result", "run.state_changed"}:
            return
        def append(state):
            _, run, journal = run_in(state, control.run_id)
            if run.state in TERMINAL_RUNS and not terminal:
                return
            if terminal and journal.events and journal.events[-1].root.type == kind and journal.events[-1].root.payload.model_dump(by_alias=True) == payload:
                return
            sequence = journal.events[-1].root.sequence + 1 if journal.events else 1
            event = AgentEvent.model_validate({"schemaVersion": 1, "id": identity("event"), "sequence": sequence,
                "projectId": control.project_id, "conversationId": run.conversation_id, "runId": run.id,
                "timestamp": datetime.now(timezone.utc).isoformat(), "type": kind, "payload": payload})
            if kind == "usage.reported":
                run.usage = AgentUsage.model_validate(payload)
            journal.events.append(event)
        self.store.update(control.project_id, append)
        self.events.changed(control.run_id)

    def before_start(self, control):
        with self.projects.state_lock:
            if control.revoked.is_set() or control.cancel.is_set():
                raise AgentFailure(control.reason or "AGENT_CANCELLED")
            self.leases.require(control.project_id, epoch=control.owner_epoch)
            current = self.connection()
            if not current.ready or current.epoch != control.connection_epoch:
                raise AgentFailure("AGENT_CONNECTION_CHANGED")
            def running(state):
                _, run, _ = run_in(state, control.run_id)
                if state.owner_epoch != control.owner_epoch:
                    raise AgentFailure("AGENT_OWNER_MISMATCH")
                if run.state != "queued":
                    raise AgentFailure("AGENT_INTERRUPTED")
                run.state = "running"
            self.store.update(control.project_id, running)
            self.event(control, "run.state_changed", {"state": "running", "error": None,
                "savedBatchId": None, "outcomeUnknown": False})

    async def _watch(self, control):
        while control.task is not None and not control.task.done():
            await asyncio.sleep(0.1)
            if control.cancel.is_set():
                return
            try:
                with self.projects.state_lock:
                    self.leases.require(control.project_id, epoch=control.owner_epoch)
                    if self.store.load(control.project_id).owner_epoch != control.owner_epoch:
                        raise AgentFailure("AGENT_OWNER_MISMATCH")
                    if self.connection().epoch != control.connection_epoch:
                        raise AgentFailure("AGENT_CONNECTION_CHANGED")
                    if control.project_id in self.projects.deleted_ids:
                        raise AgentFailure("AGENT_PROJECT_DELETED")
            except AgentFailure as error:
                self.revoke(control, error.code)
                return

    async def _drive(self, control):
        monitor = asyncio.create_task(self._watch(control))
        session = None
        result = RuntimeResult(error="AGENT_RUNTIME_UNSUPPORTED")
        loop = asyncio.get_running_loop()
        try:
            if self.runtime is None or self.tools is None:
                raise AgentFailure("AGENT_RUNTIME_UNSUPPORTED")
            _, run, journal = run_in(self.store.load(control.project_id), control.run_id)
            async with worker_slot(self.projects, control.cancel, control.queued_at + 30):
                session = await self.tools.open(control, run, journal)
                async def close_session():
                    await session.close()
                def close_tools(timeout):
                    future = asyncio.run_coroutine_threadsafe(close_session(), loop)
                    future.result(timeout=min(3, timeout))
                value = RuntimeInput(model=run.model, prompt=session.prompt, url=session.url, token=session.token,
                    tools=tuple(session.names), allow_web=run.allow_web, before_start=lambda: self.before_start(control),
                    revoke=lambda: self.revoke(control), close_tools=close_tools, queued_at=control.queued_at)
                result = await self.runtime.run(value, control.cancel, lambda kind, payload: self.event(control, kind, payload))
        except (AdmissionCancelled, asyncio.CancelledError):
            self.revoke(control, "AGENT_CANCELLED")
            result = RuntimeResult(state="cancelled", error=control.reason)
        except AdmissionTimeout:
            result = RuntimeResult(error="AGENT_BUSY")
        except AdmissionBlocked:
            result = RuntimeResult(error="AGENT_CLEANUP_FAILED")
        except AgentFailure as error:
            result = RuntimeResult(error=error.code)
        except Exception:
            result = RuntimeResult(error="AGENT_PROTOCOL")
        finally:
            self.revoke(control)
            control.seed = None
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
            if session is not None:
                try:
                    await asyncio.wait_for(session.close(), 3)
                except Exception:
                    INFERENCE.block()
                    result.state, result.error = "failed", "AGENT_CLEANUP_FAILED"
            if control.reason is not None and result.error != "AGENT_CLEANUP_FAILED":
                result.state = "cancelled" if control.reason == "AGENT_CANCELLED" else "interrupted"
                result.error = control.reason
            if result.error == "AGENT_CLEANUP_FAILED":
                INFERENCE.block()
                self.cleanup_error(result.error)
            control.result = result
            try:
                state = self.store.load(control.project_id)
                conversation, run, _ = run_in(state, control.run_id)
                if result.error == "AGENT_MODEL_INCOMPATIBLE":
                    self.capability_states[self.capability_key(run.connection_epoch, run.model, run.allow_edits, run.allow_web)] = ("incompatible", result.error)
                elif result.state == "completed" and result.tool_calls > 0 and getattr(self.runtime, "native", False):
                    self.capability_states[self.capability_key(run.connection_epoch, run.model, run.allow_edits, run.allow_web)] = ("verified", None)
                sources = [AgentReference(id=source.id, label=source.title[:256]) for source in conversation.sources
                    if source.id in result.text]
                findings = [AgentReference(id=finding.id, label=finding.message[:256]) for finding in conversation.findings
                    if finding.run_id == run.id]
                finished = self.store.finish(control.project_id, control.run_id, result.state, text=result.text,
                    error=result.error, sources=sources, findings=findings, truncated=result.truncated,
                    native_completed=result.state == "completed")
                self.event(control, "run.state_changed", {"state": finished.state,
                    "error": finished.error.model_dump(by_alias=True) if finished.error else None,
                    "savedBatchId": finished.saved_batch_id, "outcomeUnknown": finished.outcome_unknown}, terminal=True)
            except AgentFailure as error:
                if error.code not in {"AGENT_PROJECT_DELETED", "AGENT_NOT_FOUND"}:
                    try:
                        result.state, result.error = "failed", error.code
                        self.store.finish(control.project_id, control.run_id, "failed", error=error.code,
                            text=result.text.encode()[:1024].decode("utf-8", "ignore"), truncated=bool(result.text))
                    except AgentFailure:
                        self.startup_errors[control.project_id] = "AGENT_STORE_UNAVAILABLE"
            await self.projects.drain_catalog_actions(run_id=control.run_id)
