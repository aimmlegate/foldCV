"""Direct imports share admission while publishing after verified worker release."""

import asyncio
import threading

from packages.resume_core.template_import import TemplateImportFailure
from packages.resume_core.project_store import ProjectStoreFailure
from ..inference_admission import AdmissionBlocked, AdmissionCancelled
from .template_transport import JOB_PERMIT


class TemplateDirect:
    def __init__(self, pipeline, admission):
        self.pipeline, self.admission = pipeline, admission
        self.permits, self.stops, self.locks = {}, {}, {}

    async def run(self, project, command):
        async with self.locks.setdefault(project, asyncio.Lock()):
            return await self._run(project, command)

    async def _run(self, project, command):
        if command.kind == 'resume_import':
            operation = await self.pipeline.recover(project, command.operation_id)
            if all(attempt.cleanup.state == 'verified' for attempt in operation.attempts):
                retained = self.permits.get(project)
                if retained is not None and retained[1] == operation.id:
                    self.permits.pop(project)[0].release()
        stop, cancelled = threading.Event(), asyncio.Event()
        self.stops[project] = stop, cancelled
        permit_token = None
        async def admitted():
            nonlocal permit_token
            workspace = self.pipeline.read(project)
            operations = (workspace.project or workspace.pre_draft).template_operations
            operation = next(value for value in operations if value.id == command.operation_id) if command.kind == 'resume_import' else next(
                value for value in operations if value.client_request_id == command.client_request_id)
            try:
                permit = await self.admission.reserve(cancelled)
            except (AdmissionBlocked, AdmissionCancelled):
                raise TemplateImportFailure('IMPORT_CLEANUP_UNKNOWN' if self.admission.blocked else 'CANCELLED') from None
            self.permits[project] = permit, operation.id
            permit_token = JOB_PERMIT.set(permit)
        result = None
        try:
            result = await self.pipeline.run(project, command, admitted=admitted, finalize=False, cancel_event=stop)
        finally:
            if permit_token is not None:
                JOB_PERMIT.reset(permit_token)
            retained = self.permits.get(project)
            if retained is not None:
                try:
                    workspace = self.pipeline.read(project)
                    operation = next(value for value in (workspace.project or workspace.pre_draft).template_operations if value.id == retained[1])
                    verified = all(attempt.cleanup.state == 'verified' for attempt in operation.attempts)
                except ProjectStoreFailure as error:
                    if error.code != 'PROJECT_DELETED':
                        raise
                    verified = await asyncio.to_thread(self.pipeline.cleanup_deleted, project, retained[1])
                if verified:
                    self.permits.pop(project)[0].release()
            self.stops.pop(project, None)
        if result.state in {'published', 'cancelled', 'failed', 'fenced'} or stop.is_set():
            return result
        return await self.pipeline.finalize(project, result.id)

    async def cancel(self, project, operation_id):
        signals = self.stops.get(project)
        if signals is not None:
            signals[0].set()
            signals[1].set()
        return await self.pipeline.cancel(project, operation_id)

    async def cleanup_deleted(self, project):
        retained = self.permits.get(project)
        verified = await asyncio.to_thread(self.pipeline.cleanup_deleted, project, retained[1] if retained else None)
        if verified and retained is not None and self.permits.get(project) is retained:
            self.permits.pop(project)[0].release()
        return verified
