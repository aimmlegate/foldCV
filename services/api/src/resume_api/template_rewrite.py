"""V7 selected-text rewrite: one counted generation per preview; the document changes only through Apply."""

import asyncio
import threading

from packages.resume_core.preferences import PreferencesFailure
from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt
from .gui_admission import AdmissionCancelled, QueuedProvider
from .gui_content import generate_admitted
from .gui_projects import ProjectFailure
from .lifecycle import OperationFiles
from .providers.content import ContentFailure, ContentInput, GenerationPolicy


class TemplateRewrite:
    @staticmethod
    def _rewrite_key(identifier, request_id):
        return identifier, 'template-rewrite:' + request_id

    async def template_rewrite_text(self, identifier, request_id, instruction, source):
        selected = self.provider_factory()
        if selected is None:
            raise ProjectFailure('CONNECTION_REQUIRED', 409)
        try:
            effort = self.preferences.load().rewrite_reasoning_effort if self.preferences else None
        except PreferencesFailure as error:
            raise ProjectFailure(error.code, 409) from None
        key = self._rewrite_key(identifier, request_id)
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
        except ContentFailure as error:
            raise ProjectFailure(error.code, 409 if error.code == 'CANCELLED' else 502) from None
        finally:
            self.tasks.pop(key, None)
            self.cancels.pop(key, None)
            self.files.pop(key, None)

    def template_rewrite_cancel(self, identifier, request_id):
        cancel = self.cancels.get(self._rewrite_key(identifier, request_id))
        if cancel is None:
            return False
        cancel.set()
        return True
