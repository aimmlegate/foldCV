"""Own the existing pinned runtime until its worker and private tools are closed."""

import asyncio
import copy
import time

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import ExecutionOutcome

from ..agent.runtime import RuntimeInput
from .tools import DEVELOPER_INSTRUCTIONS_V2

ERRORS = {"AGENT_QUOTA": "RATE_LIMITED", "AGENT_AUTH_REQUIRED": "AUTH_REQUIRED",
    "AGENT_MODEL_INCOMPATIBLE": "MODEL_DENIED", "AGENT_CANCELLED": "CANCELLED",
    "AGENT_DEADLINE": "DEADLINE", "AGENT_STARTUP_TIMEOUT": "STARTUP_TIMEOUT",
    "AGENT_CLEANUP_FAILED": "CLEANUP_FAILED", "AGENT_BUSY": "BUSY"}


class JobRuntime:
    def __init__(self, service, job, model):
        self.service, self.job, self.model = service, job, model
        self.driver = self.session = self.result = self.control = None
        self.closed = False
        self.runtime_entered = False

    async def run(self, control):
        if self.closed or self.driver is not None:
            raise BackgroundFailure("PROTOCOL")
        self.control = control
        self.driver = asyncio.create_task(self._execute(control))
        return await asyncio.shield(self.driver)

    async def _execute(self, control):
        loop = asyncio.get_running_loop()
        try:
            self.session = self.service.tools.session(control)
            await self.session.start()
            if control.cancel.is_set():
                raise BackgroundFailure("CANCELLED")
            runtime = copy.copy(self.service.runtime)
            if getattr(runtime, "native", False):
                await self.service.authorize_native(control)
            runtime.admission = control.permit
            def call(coroutine):
                return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=15)
            def revoke():
                control.revoked = True
                self.session.revoke()
            def close_tools(seconds):
                asyncio.run_coroutine_threadsafe(self.session.close(), loop).result(timeout=max(0.001, seconds))
            def emit(kind, payload):
                if kind == "run.state" and payload.get("error", {}).get("code") in {"AGENT_QUOTA", "AGENT_AUTH_REQUIRED"}:
                    loop.call_soon_threadsafe(self.service.supervisor.pause, ERRORS[payload["error"]["code"]])
            value = RuntimeInput(model=self.model.model, prompt=self.session.prompt, url=self.session.url,
                token=self.session.token, tools=tuple(control.job.submission.tools), allow_web=control.job.submission.allow_web,
                queued_at=time.monotonic(), before_start=(lambda: call(control.execution_ready()))
                    if getattr(runtime, "native", False) else control.execution_ready,
                child_started=lambda: call(control.child_started()), revoke=revoke, close_tools=close_tools,
                developer_instructions=DEVELOPER_INSTRUCTIONS_V2, elapsed_clock=self.service.supervisor.clock.now)
            self.runtime_entered = True
            self.result = await runtime.run(value, control.cancel, emit)
            error = ERRORS.get(self.result.error, "PROTOCOL" if self.result.error else None)
            # An observed account failure still pauses dispatch when a deadline wins the race.
            if error in {"RATE_LIMITED", "AUTH_REQUIRED"}:
                self.service.supervisor.pause(error)
            self.service.artifacts.finish(control.project_id, control.run_id, self.result)
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
