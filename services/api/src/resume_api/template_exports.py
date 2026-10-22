"""Template exports reuse canonical checkpoints and the existing worker owner."""

import asyncio
import threading

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure, identity
from packages.resume_core.rendering.captured_docx import renderer_identity
from packages.resume_core.template_import import TemplateImportFailure
from .gui_projects import ProjectFailure
from .gui_admission import AdmissionCancelled
from .importer.template_checkpoints import TemplateCheckpoints
from .importer.template_export import TemplateExporter
from .lifecycle import OperationFiles, SpikeError


class TemplateExports:
    def configure_template_exports(self, jobs, *, cleanup_verified):
        self.template_jobs = jobs
        self.template_export_stopping = False
        self.template_export_keys = set()
        self.template_export_cleanup_verified = cleanup_verified
        self.template_checkpoints = TemplateCheckpoints(jobs.publisher, originals=self.originals, artifacts=self.artifacts,
            images=self.images, wall=lambda: self.clock().isoformat(), export_only=True)

    def canonical_jobs(self, identifier):
        jobs = getattr(self, 'background_jobs', None)
        if jobs is not None and jobs.enabled:
            return jobs
        workspace = self.workspaces.get(identifier)
        return getattr(self, 'template_jobs', None) if workspace is not None and workspace.schema_version == 7 else None

    def _adopt_template_export(self, identifier):
        with self.state_lock:
            self._adopt_template_export_locked(identifier)

    def _adopt_template_export_locked(self, identifier):
        owner = self.template_checkpoints
        if identifier in self.deleted_ids:
            return
        if identifier in owner.pending_checkpoints or identifier in owner.checkpoint_fences or identifier in owner.publisher.jobs.fences:
            self.save_errors[identifier] = 'OUTCOME_UNKNOWN'
            return
        try:
            current = owner.read(identifier)
            self.adopt_committed(identifier, current, digest_bytes(current), preserve=True)
        except Exception as error:
            self.save_errors[identifier] = getattr(error, 'code', 'PROJECT_SAVE_FAILED')

    async def export_template(self, identifier, expected, *, retry_attempt_id=None):
        if self.template_export_stopping:
            raise ProjectFailure('CANCELLED', 409)
        captured = self.read(identifier)
        if captured.schema_version != 7:
            raise ProjectFailure('IMPORT_PROTOCOL_MISMATCH', 409)
        self.require_agent_writable(identifier)
        owner = getattr(self, 'template_checkpoints', None)
        if owner is None:
            raise ProjectFailure('IMPORT_PROTOCOL_MISMATCH', 409)
        self.template_jobs.store.open(identifier)
        key = (identifier, identity('template_export'))
        cancel, files = threading.Event(), OperationFiles(self.temp_root)
        self.tasks[key], self.cancels[key], self.files[key] = asyncio.current_task(), cancel, files
        self.template_export_keys.add(key)
        async def render(request):
            try:
                async with self.worker_slot(cancel):
                    if cancel.is_set():
                        raise ProjectFailure('CANCELLED', 409)
                    with files.open():
                        blob = await self.renderer.render_template(request, files)
                    if cancel.is_set():
                        raise ProjectFailure('CANCELLED', 409)
                    return blob
            except Exception as error:
                if isinstance(error, AdmissionCancelled) or cancel.is_set() and getattr(error, 'code', None) not in {
                        'PROCESS_CLEANUP_FAILED', 'CLEANUP_FAILED'}:
                    raise ProjectFailure('CANCELLED', 409) from None
                raise
        try:
            result = await TemplateExporter(owner, renderer_identity(), render_async=render).export(identifier, expected,
                retry_attempt_id=retry_attempt_id)
            if result.attempt.state != 'completed' or result.artifact is None:
                raise ProjectFailure(result.attempt.error_code or 'RICH_RENDER_FAILED', 422)
            return result
        except (BackgroundFailure, TemplateImportFailure) as error:
            raise ProjectFailure(error.code, 409) from None
        except SpikeError as error:
            self.cleanup_error(error)
            raise ProjectFailure(error.code, 503) from None
        finally:
            self.tasks.pop(key, None)
            self.cancels.pop(key, None)
            self.template_export_keys.discard(key)
            if not files.cleanup_failed:
                self.files.pop(key, None)
            else:
                self.cleanup_error(SpikeError('PROCESS_CLEANUP_FAILED'))
            self._adopt_template_export(identifier)

    async def recover_template_exports(self):
        self.ensure_loaded()
        owner = self.template_checkpoints
        for identifier, workspace in list(self.workspaces.items()):
            if workspace.schema_version != 7 or workspace.project is None or not any(
                    value.state in {'pending', 'running'} for value in workspace.project.exports):
                continue
            if not self.template_export_cleanup_verified():
                owner.fence_checkpoint(identifier, 'startup-exports')
                self.save_errors[identifier] = 'OUTCOME_UNKNOWN'
                continue
            try:
                self.template_jobs.store.open(identifier)
                current = await owner.reconcile_checkpoint(identifier)
                targets = {value.id for value in current.project.exports if value.state in {'pending', 'running'}}
                def interrupted(value):
                    for attempt in value.project.exports:
                        if attempt.id in targets and attempt.state in {'pending', 'running'}:
                            attempt.state, attempt.error_code, attempt.artifact_hash = 'failed', 'OPERATION_INTERRUPTED', None
                    attempts = {attempt.id: attempt for attempt in value.project.exports}
                    for operation in value.project.template_operations:
                        operation.export_attempts = [attempts[attempt.id].model_copy(deep=True) for attempt in operation.export_attempts]
                    return value
                await owner.checkpoint_async(identifier, interrupted, operation_id='startup-exports')
                self._adopt_template_export(identifier)
            except (BackgroundFailure, TemplateImportFailure) as error:
                owner.fence_checkpoint(identifier, 'startup-exports')
                self.save_errors[identifier] = error.code

    async def drain_template_exports(self):
        owner = getattr(self, 'template_checkpoints', None)
        if owner is None:
            return
        deadline = asyncio.get_running_loop().time() + owner.cleanup_seconds
        while owner.publisher.template_export_tasks or owner.pending_checkpoints:
            tasks = list(owner.publisher.template_export_tasks.values()) + list(owner.pending_checkpoints.values())
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError
                results = await asyncio.wait_for(asyncio.shield(asyncio.gather(*tasks, return_exceptions=True)), remaining)
                if any(isinstance(value, BaseException) for value in results):
                    raise ProjectFailure('OUTCOME_UNKNOWN', 503)
                await asyncio.sleep(0)
                if any(task.done() for task in owner.pending_checkpoints.values()):
                    raise ProjectFailure('OUTCOME_UNKNOWN', 503)
            except asyncio.TimeoutError:
                for project, attempt, _purpose in owner.publisher.template_export_tasks:
                    owner.fence_checkpoint(project, attempt)
                for project in owner.pending_checkpoints:
                    owner.fence_checkpoint(project, owner.checkpoint_owners.get(project))
                self.cleanup_error(SpikeError('PROCESS_CLEANUP_FAILED'))
                raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503) from None
        if any(files.cleanup_failed for files in self.files.values()):
            raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503)
