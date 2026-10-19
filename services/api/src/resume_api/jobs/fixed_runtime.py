"""Fixed content uses the supervisor's permit and existing one-attempt services."""

import asyncio
import copy
import logging

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import ExecutionOutcome
from ..gui_content import generate_admitted
from ..lifecycle import OperationFiles, SpikeError
from ..providers.content import ContentFailure, ContentInput, GenerationPolicy
from ..rich_synchronization import sync_prompt
from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt
from .fixed_projection import FixedProjection

ERRORS = {"QUOTA_EXHAUSTED": "RATE_LIMITED", "RATE_LIMITED": "RATE_LIMITED",
    "AUTH_REQUIRED": "AUTH_REQUIRED", "PROCESS_CLEANUP_FAILED": "CLEANUP_FAILED",
    "PROCESS_TIMEOUT": "DEADLINE", "OPERATION_TIMEOUT": "DEADLINE", "DEADLINE_EXCEEDED": "DEADLINE"}


class OwnedContent:
    def __init__(self, provider, permit):
        self.provider, self.permit = provider, permit

    def generate(self, request, files, cancel):
        owned = getattr(self.provider, "generate_owned", None)
        if owned is not None:
            return owned(request, files, cancel, self.permit)
        with self.permit.hold(cancel):
            return self.provider.generate(request, files, cancel)


class FixedRuntime:
    def __init__(self, service, job, model):
        self.service, self.job, self.model = service, job, model
        self.files = OperationFiles(service.projects.temp_root)
        self.driver, self.control, self.closed = None, None, False

    async def run(self, control):
        if self.driver is not None or self.closed:
            raise BackgroundFailure("PROTOCOL")
        self.control = control
        self.driver = asyncio.create_task(self.execute(control))
        return await asyncio.shield(self.driver)

    async def content(self, function):
        def run():
            with self.files.open():
                return function(self.files)
        return await asyncio.get_running_loop().run_in_executor(self.service.content_pool, run)

    async def execute(self, control):
        try:
            captured = self.service.fixed.input(self.job)
            selected = self.service.content_provider()
            if selected is None:
                raise BackgroundFailure("AUTH_REQUIRED")
            provider = copy.copy(selected[0])
            loop = asyncio.get_running_loop()
            if getattr(provider, "multiplexed", False):
                provider.loop, provider.job_id, provider.cancelled = loop, control.run_id, control.cancelled
                provider.before_turn = lambda native=provider.native: self.service.authorize_native(control) if native else None
                provider.model_started = control.child_started if provider.native else lambda: self.service.supervisor.observer(
                    "scripted_fixed_model_ready", control.run_id)
            elif hasattr(provider, "model_started"):
                provider.model_started = lambda: asyncio.run_coroutine_threadsafe(control.child_started(), loop).result(timeout=15)
            provider = OwnedContent(provider, control.permit)
            await control.execution_ready()
            self.provider, self.captured = provider, captured
            self.native = getattr(provider.provider, "native", False)
            self.authorized = False
            if self.job.submission.kind == "processing":
                await self.service.fixed.processing_stage(self, control)
            else:
                projection = FixedProjection(control.project_id, captured.workspace, captured.sync_id,
                    invoke=self.sync_content, original=captured.original_sync)
                record = await projection.run(captured.request.command)
                if control.cancel.is_set():
                    raise BackgroundFailure("CANCELLED")
                await self.service.fixed.accept_sync(control, captured, record)
            return ExecutionOutcome("completed", None, self.service.supervisor.clock.now())
        except (ContentFailure, SpikeError, BackgroundFailure) as error:
            code = ERRORS.get(error.code, error.code)
            if code in {"RATE_LIMITED", "AUTH_REQUIRED"}:
                self.service.supervisor.pause(code)
            return ExecutionOutcome("cancelled" if code == "CANCELLED" else "failed", code)
        except Exception:
            logging.getLogger(__name__).exception("Fixed operation failed")
            return ExecutionOutcome("failed", "PROCESS_FAILED")
        finally:
            self.closed = True

    async def authorize(self):
        if not self.authorized:
            await self.service.supervisor.observer("fixed_model_ready", self.control.job.id)
        if self.control.cancel.is_set():
            raise BackgroundFailure("CANCELLED")
        if not self.authorized and self.native and not getattr(self.provider.provider, "multiplexed", False):
            await self.service.authorize_native(self.control)
        self.authorized = True

    async def sync_content(self, sync, payload, result_type):
        await self.authorize()
        plain = result_type is PlainTextReply
        prompt = plain_prompt(payload["instruction"], payload["text"]) if plain else sync_prompt(
            sync.kind if sync.kind in {"rewrite", "panel"} else "reconcile", payload, self.captured.rules)
        request = ContentInput(prompt, result_type, GenerationPolicy(model=self.model.model, timeout_seconds=180,
            allow_repair=False, reasoning_effort=self.captured.reasoning_effort if plain else None))
        response = await self.content(lambda files: generate_admitted(self.provider, request, files, self.control.cancel))
        return result_type.model_validate(response.value)

    async def close(self):
        if self.control is not None and self.driver is not None and not self.driver.done():
            self.control.cancel.set()
        if self.driver is not None:
            try:
                await asyncio.shield(self.driver)
            except Exception:
                if not self.verified_dead():
                    raise
        else:
            self.closed = True

    def verified_dead(self):
        provider = getattr(getattr(self, "provider", None), "provider", None)
        return (self.closed and (self.driver is None or self.driver.done())
            and self.files.process is None and self.files.path is None and not self.files.cleanup_failed
            and (not getattr(provider, "multiplexed", False) or provider.cleanup_verified))
