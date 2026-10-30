"""V7 selected-text rewrite: one counted generation per preview; the document changes only through Apply."""

import asyncio
from collections import OrderedDict
import threading

from packages.resume_core.preferences import PreferencesFailure
from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt
from .inference_admission import AdmissionCancelled
from .lifecycle import OperationFiles, SpikeError
from .projects.errors import ProjectFailure
from .providers.admitted import QueuedProvider, generate_admitted
from .providers.content import ContentFailure, ContentInput, GenerationPolicy

CANCEL_SECONDS = 65
EARLY_CANCELS_KEPT = 64


class TemplateRewrite:
    def __init__(self, provider_factory, *, preferences, temp_root, worker_slot, cleanup_error, reasoning=lambda _model: None,
                 unavailable=lambda: 'CONNECTION_REQUIRED'):
        self.provider_factory, self.preferences, self.temp_root = provider_factory, preferences, temp_root
        self.reasoning, self.unavailable = reasoning, unavailable
        self.worker_slot, self.cleanup_error = worker_slot, cleanup_error
        self.tasks, self.cancels, self.files = {}, {}, {}
        # Cancel runs in a worker thread, and a cancel must not fall between a request's check and its registration.
        self.early, self.registry = OrderedDict(), threading.Lock()

    async def text(self, identifier, request_id, instruction, source, admitted=lambda: None):
        key, cancel, files = (identifier, request_id), threading.Event(), OperationFiles(self.temp_root)
        with self.registry:
            if self.early.pop(key, False):
                raise ProjectFailure('CANCELLED', 409)
            if key in self.cancels:
                raise ProjectFailure('REQUEST_IN_PROGRESS', 409)
            self.tasks[key], self.cancels[key], self.files[key] = asyncio.current_task(), cancel, files
        try:
            selected = self.provider_factory()
            if selected is None:
                raise ProjectFailure(self.unavailable(), 409)
            try:
                effort = self.preferences.load().rewrite_reasoning_effort if self.preferences else None
            except PreferencesFailure as error:
                raise ProjectFailure(error.code, 409) from None
            # A level saved for another model runs at this model's default instead of failing the rewrite.
            metadata = self.reasoning(selected[1])
            if effort is not None and metadata is not None and effort not in metadata.supported:
                effort = None
            request = ContentInput(plain_prompt(instruction, source), PlainTextReply, GenerationPolicy(model=selected[1],
                timeout_seconds=180, allow_repair=False, reasoning_effort=effort))
            def run():
                with files.open():
                    return generate_admitted(QueuedProvider(selected[0], admitted), request, files, cancel)
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
        except asyncio.CancelledError:
            # The service is stopping: the worker thread outlives this handler, and the finally below hides it from shutdown.
            cancel.set()
            try:
                files.stop_worker()
            except SpikeError as error:
                self.cleanup_error(error)
            raise
        finally:
            with self.registry:
                self.tasks.pop(key, None)
                self.cancels.pop(key, None)
                self.files.pop(key, None)

    def cancel(self, identifier, request_id):
        """Stop a request, or remember one not registered yet: it may still be saving or waiting for the project lock."""
        key = (identifier, request_id)
        with self.registry:
            cancel = self.cancels.get(key)
            if cancel is not None:
                cancel.set()
                return True
            self.early[key] = True
            while len(self.early) > EARLY_CANCELS_KEPT:
                self.early.popitem(last=False)
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
