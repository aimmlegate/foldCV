"""Hold job ownership until its worker or shared turn and private tools close."""

import asyncio
import copy
import time

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.agent import AgentEvent
from packages.resume_core.rich_assembly import identity

from ..agent.runtime import RuntimeInput
from .tools import DEVELOPER_INSTRUCTIONS_V2

ERRORS = {"AGENT_QUOTA": "RATE_LIMITED", "AGENT_AUTH_REQUIRED": "AUTH_REQUIRED",
    "AGENT_MODEL_INCOMPATIBLE": "MODEL_DENIED", "AGENT_CANCELLED": "CANCELLED",
    "AGENT_DEADLINE": "DEADLINE", "AGENT_STARTUP_TIMEOUT": "STARTUP_TIMEOUT",
    "AGENT_CLEANUP_FAILED": "CLEANUP_FAILED", "AGENT_BUSY": "BUSY"}


class JobRuntime:
    instructions = DEVELOPER_INSTRUCTIONS_V2
    revoke_owner = True

    def __init__(self, service, job, model):
        self.service, self.job, self.model = service, job, model
        self.driver = self.session = self.result = self.control = None
        self.closed = False
        self.runtime_entered = False

    def open_session(self, control):
        return self.service.tools.session(control)

    async def finish_result(self, control):
        self.service.artifacts.finish(control.project_id, control.run_id, self.result)
        agent = getattr(self.service.projects, "agent", None)
        if getattr(agent, "assistant_protocol_enabled", False):
            agent.proposals.finish(control.project_id, control.run_id, cancelled=self.result.state == "cancelled")

    async def run(self, control):
        if self.closed or self.driver is not None:
            raise BackgroundFailure("PROTOCOL")
        self.control = control
        self.driver = asyncio.create_task(self._execute(control))
        return await asyncio.shield(self.driver)

    async def _execute(self, control):
        loop = asyncio.get_running_loop()
        try:
            self.session = self.open_session(control)
            await self.session.start()
            conversation = None
            if control.job.submission.kind == "agent":
                _job, artifact = self.service.artifacts.record(control.project_id, control.run_id)
                conversation = artifact.request.conversation_id
            if control.cancel.is_set():
                raise BackgroundFailure("CANCELLED")
            runtime = copy.copy(self.service.runtime)
            if runtime is None:
                raise AgentFailure("AGENT_RUNTIME_UNSUPPORTED")
            multiplexed = getattr(runtime, "multiplexed", False)
            if getattr(runtime, "native", False) and not multiplexed:
                await self.service.authorize_native(control)
            runtime.admission = control.permit
            def call(coroutine):
                return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=15)
            def revoke():
                if self.revoke_owner:
                    control.revoked = True
                self.session.revoke()
            def close_tools(seconds):
                asyncio.run_coroutine_threadsafe(self.session.close(), loop).result(timeout=max(0.001, seconds))
            async def ready_shared():
                await control.execution_ready()
                if getattr(runtime, "native", False):
                    await self.service.authorize_native(control)
            async def close_shared(_seconds):
                await self.session.close()
                return (not self.session.token and self.session.listener.fileno() == -1
                    and (self.session.task is None or self.session.task.done()))
            async def started_shared():
                if getattr(runtime, "native", False):
                    await control.child_started()
                else:
                    await self.service.supervisor.observer("scripted_model_ready", control.run_id)
            def emit(kind, payload):
                error = payload.get("error")
                if kind == "run.state" and isinstance(error, dict) and error.get("code") in {"AGENT_QUOTA", "AGENT_AUTH_REQUIRED"}:
                    loop.call_soon_threadsafe(self.service.supervisor.pause, ERRORS[error["code"]])
                if conversation is None or kind not in {"activity.updated", "tool.started", "tool.completed", "tool.failed"}:
                    return
                def progress(_state, job):
                    if job.execution_generation != control.job.execution_generation or job.execution not in {"starting", "running", "cancelling"}:
                        return
                    event = AgentEvent.model_validate({"schemaVersion": 1, "id": identity("activity"), "sequence": job.event_cursor + 1,
                        "projectId": control.project_id, "runId": job.id, "conversationId": conversation,
                        "timestamp": self.service.store.clock(), "type": kind, "payload": payload})
                    if kind == "activity.updated":
                        job.activity = [item for item in job.activity if item.root.type != kind or item.root.payload.item_id != event.root.payload.item_id]
                    job.activity = [*job.activity, event][-40:]
                self.service.store.update(control.project_id, control.run_id, progress)
            instructions = self.instructions
            if getattr(getattr(self.service.projects, "agent", None), "assistant_protocol_enabled", False):
                from ..agent.capabilities import proposal_instructions
                instructions = proposal_instructions()
            value = RuntimeInput(model=self.model.model, prompt=self.session.prompt, url=self.session.url,
                token=self.session.token, tools=tuple(control.job.submission.tools), allow_web=control.job.submission.allow_web,
                queued_at=time.monotonic(), before_start=ready_shared if multiplexed else
                    (lambda: call(control.execution_ready())) if getattr(runtime, "native", False) else control.execution_ready,
                child_started=started_shared if multiplexed else lambda: call(control.child_started()),
                revoke=revoke, close_tools=close_shared if multiplexed else close_tools,
                developer_instructions=instructions, elapsed_clock=self.service.supervisor.clock.now,
                active_seconds=control.active_seconds,
                job_id=control.run_id, cancelled=control.cancelled)
            self.runtime_entered = True
            self.result = await runtime.run(value, control.cancel, emit)
            error = ERRORS.get(self.result.error, "PROTOCOL" if self.result.error else None)
            # An observed account failure still pauses dispatch when a deadline wins the race.
            if error in {"RATE_LIMITED", "AUTH_REQUIRED"}:
                self.service.supervisor.pause(error)
            await self.finish_result(control)
            return ExecutionOutcome(self.result.state, error, self.service.supervisor.clock.now())
        except AgentFailure as error:
            return ExecutionOutcome("failed", ERRORS.get(error.code, "PROTOCOL"))
        finally:
            if self.session is not None:
                await self.session.close()
            self.closed = True

    async def close(self):
        if self.control is not None:
            self.control.cancel.set()
        if self.session is not None:
            self.session.revoke()
        if self.driver is not None:
            try:
                await asyncio.shield(self.driver)
            except Exception:
                if self.runtime_entered and (self.result is None or not self.result.cleanup_verified):
                    raise
        else:
            self.closed = True

    def verified_dead(self):
        return (self.closed and (self.driver is None or self.driver.done())
            and (not self.runtime_entered or self.result is not None and self.result.cleanup_verified))
