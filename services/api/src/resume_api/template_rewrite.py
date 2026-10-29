"""V7 selected-text rewrite: one counted generation per preview; the document changes only through Apply."""

import asyncio
import threading

from packages.resume_core.preferences import PreferencesFailure
from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt
from .inference_admission import AdmissionCancelled
from .lifecycle import OperationFiles, SpikeError
from .projects.errors import ProjectFailure
from .providers.admitted import QueuedProvider, generate_admitted
from .providers.content import ContentFailure, ContentInput, GenerationPolicy

CANCEL_SECONDS = 65


class TemplateRewrite:
    def __init__(self, provider_factory, *, preferences, temp_root, worker_slot, cleanup_error, reasoning=lambda _model: None):
        self.provider_factory, self.preferences, self.temp_root = provider_factory, preferences, temp_root
        self.reasoning = reasoning
        self.worker_slot, self.cleanup_error = worker_slot, cleanup_error
        self.tasks, self.cancels, self.files = {}, {}, {}

    async def text(self, identifier, request_id, instruction, source):
        selected = self.provider_factory()
        if selected is None:
            raise ProjectFailure('CONNECTION_REQUIRED', 409)
        try:
            effort = self.preferences.load().rewrite_reasoning_effort if self.preferences else None
        except PreferencesFailure as error:
            raise ProjectFailure(error.code, 409) from None
        # A level saved for another model runs at this model's default instead of failing the rewrite.
        metadata = self.reasoning(selected[1])
        if effort is not None and metadata is not None and effort not in metadata.supported:
            effort = None
        key = (identifier, request_id)
        if key in self.cancels:
            raise ProjectFailure('REQUEST_IN_PROGRESS', 409)
        cancel, files = threading.Event(), OperationFiles(self.temp_root)
        self.tasks[key], self.cancels[key], self.files[key] = asyncio.current_task(), cancel, files
        request = ContentInput(plain_prompt(instruction, source), PlainTextReply, GenerationPolicy(model=selected[1],
            timeout_seconds=180, allow_repair=False, reasoning_effort=effort))
        def run():
            with files.open():
                return generate_admitted(QueuedProvider(selected[0], lambda: None), request, files, cancel)
        try:
            async with self.worker_slot(cancel):
                response = await asyncio.to_thread(run)
            if cancel.is_set():
                raise ContentFailure('CANCELLED')
            return PlainTextReply.model_validate(response.value).text
        except AdmissionCancelled:
            raise ProjectFailure('CANCELLED', 409) from None
        except SpikeError as error:
            self.cleanup_error(error)
            raise ProjectFailure(error.code, 503) from None
        except ContentFailure as error:
            raise ProjectFailure(error.code, 409 if error.code == 'CANCELLED' else 502) from None
        finally:
            self.tasks.pop(key, None)
            self.cancels.pop(key, None)
            self.files.pop(key, None)

    def cancel(self, identifier, request_id):
        cancel = self.cancels.get((identifier, request_id))
        if cancel is None:
            return False
        cancel.set()
        return True

    def request_shutdown(self):
        for cancel in list(self.cancels.values()):
            cancel.set()

    async def shutdown(self):
        """Stop every running rewrite and wait for it; a worker that does not stop blocks new work."""
        self.request_shutdown()
        for key, task in list(self.tasks.items()):
            files = self.files.get(key)
            try:
                if files is not None:
                    files.stop_worker()
            except SpikeError as error:
                self.cleanup_error(error)
                raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503) from None
            if task is asyncio.current_task() or task.done():
                continue
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=CANCEL_SECONDS)
            except asyncio.TimeoutError:
                self.cleanup_error(SpikeError('PROCESS_CLEANUP_FAILED'))
                raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503) from None
            except Exception:
                pass
