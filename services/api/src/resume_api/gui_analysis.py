"""Persisted pending fields, completion scheduling and guarded background results."""

import asyncio
import threading
import uuid
from packages.resume_core.gui_derived import digest
from packages.resume_core.gui_reconciliation import (analysis_index, reconciliation_input,
    result_dependencies, apply_reconciliation)
from packages.resume_core.models.contracts import Usage
from packages.resume_core.models.recovery import GuiOperation, AnalysisBatch
from packages.resume_core.rules import RulesFailure
from .gui_admission import AdmissionCancelled, QueuedProvider
from .gui_errors import ProjectFailure
from .gui_reconciliation_content import GuiReconciliationContentService
from .lifecycle import OperationFiles, SpikeError
from .providers.content import ContentFailure


class GuiAnalysisMixin:
    def analysis_enabled(self):
        try:
            if self.preferences is None: return True
            return self.preferences.load().automatic_analysis
        except Exception:
            return False

    def pending_analysis(self, id):
        workspace = self.workspaces[id]
        return next((op for op in reversed(self.owner(workspace).operations) if op.kind == 'reconcile_edits'
            and op.status == 'queued' and op.analysis_batch and op.analysis_batch.phase == 'pending'), None)

    def running_analysis(self, id):
        return [(oid, task) for (pid, oid), task in self.tasks.items() if pid == id and not task.done()
            and any(op.id == oid and op.kind == 'reconcile_edits' and op.status in {'queued', 'running'} for op in self.owner(self.workspaces[id]).operations)]

    def accumulate_analysis(self, id, fields=(), completed=(), *, enable=False):
        workspace = self.workspaces[id]
        if workspace.project is None: return None
        pending = self.pending_analysis(id)
        indexed = analysis_index(workspace)
        inherited, ready = set(fields), set(completed)
        for oid, _task in self.running_analysis(id):
            op = next(op for op in workspace.project.operations if op.id == oid)
            inherited.update(op.target_field_ids)
            ready.update(op.target_field_ids)
            self.cancels[(id, oid)].set()
        if pending:
            inherited.update(pending.target_field_ids)
            ready.update(pending.analysis_batch.completed_field_ids)
        inherited &= indexed.keys();ready &= inherited
        if not inherited: return None
        if pending is None:
            pending = GuiOperation(id='analysis-'+uuid.uuid4().hex, kind='reconcile_edits', status='queued',
                baseRevision=workspace.project_revision, usage=None, events=[], projectId=id,
                capturedDocumentRevision=None, dependencies=None, rulesUsed=None, targetFieldIds=[],
                resultFingerprint=None, errorCode=None, analysisBatch=AnalysisBatch(phase='pending', completedFieldIds=[], enabled=False))
            workspace.project.operations.append(pending)
        pending.target_field_ids = [key for key in indexed if key in inherited]
        pending.analysis_batch.completed_field_ids = [key for key in indexed if key in ready]
        if enable: pending.analysis_batch.enabled = True;pending.error_code = None
        return pending

    def invalidate_analysis(self, id, fields):
        self.read(id)
        with self.state_lock:
            if self.workspaces[id].project is None: return
            if not set(fields) <= analysis_index(self.workspaces[id]).keys(): raise ProjectFailure('ANALYSIS_SCOPE_INVALID', 422)
            pending = self.accumulate_analysis(id, fields)
            if pending:
                pending.analysis_batch.completed_field_ids = [key for key in pending.analysis_batch.completed_field_ids if key not in fields]
            self.persist(id)

    def analysis_mutation(self, id, request, result, before):
        if result.status != 'applied': return
        workspace = self.workspaces[id]
        indexed = analysis_index(workspace)
        if request.kind in {'restore-previous-block', 'apply-related-update'}:
            # Both actions already carry assessed facts and never require a second call.
            if before.document_revision != workspace.document_revision:
                pending = self.accumulate_analysis(id)
                if request.kind == 'restore-previous-block':
                    fields = {key for key, (_field, slot) in indexed.items() if slot == request.payload.slot_id}
                else:
                    suggestion = next(item for item in before.related_update_suggestions if item.id == request.payload.suggestion_id)
                    fields = {item.field_id for item in suggestion.replacements}
                for op in workspace.project.operations:
                    if op.kind == 'reconcile_edits' and op.analysis_batch and op.analysis_batch.phase == 'dispatched' and op.status in {'queued','running'}:
                        op.analysis_batch.completed_field_ids = [key for key in op.analysis_batch.completed_field_ids if key not in fields]
                if pending:
                    pending.analysis_batch.enabled = False
                    pending.target_field_ids = [key for key in pending.target_field_ids if key not in fields]
                    pending.analysis_batch.completed_field_ids = [key for key in pending.analysis_batch.completed_field_ids if key not in fields]
                    if not pending.target_field_ids: pending.status, pending.error_code = 'cancelled', 'RESTORED'
                self.stop_analysis_timer(id)
            return
        if request.kind == 'edit-field':
            field = request.payload.field_id
            if before.document_revision != workspace.document_revision: self.invalidate_analysis(id, [field])
            if request.payload.completion == 'none': return
            if request.payload.completion == 'slot':
                slot = indexed[field][1]
                fields = [key for key, (_value, owner) in indexed.items() if owner == slot]
            else: fields = [field]
            pending = self.pending_analysis(id)
            fields = [key for key in fields if pending and key in pending.target_field_ids]
        elif before.document_revision != workspace.document_revision:
            fields = [key for key, (_field, slot) in indexed.items() if slot in result.changed_slot_ids]
            if not fields: fields = ['profile/text'] if 'profile/text' in indexed else [next(iter(indexed))]
        else: return
        if fields:
            self.accumulate_analysis(id, fields, fields, enable=True)
            self.schedule_analysis(id)

    def stop_analysis_timer(self, id):
        old = self.analysis_timers.pop(id, None)
        if old and old is not asyncio.current_task(): old.cancel()

    def schedule_analysis(self, id):
        self.stop_analysis_timer(id)
        try: loop = asyncio.get_running_loop()
        except RuntimeError: return
        self.analysis_timers[id] = loop.create_task(self._analysis_after_completion(id))

    async def _analysis_after_completion(self, id):
        try:
            await asyncio.sleep(self.analysis_delay)
            await self.dispatch_analysis(id)
        except asyncio.CancelledError:
            pass
        except (ProjectFailure, RulesFailure) as error:
            with self.state_lock:
                pending = self.pending_analysis(id)
                if pending: pending.analysis_batch.enabled = False;pending.error_code = error.code;self.persist(id)
        finally:
            if self.analysis_timers.get(id) is asyncio.current_task(): self.analysis_timers.pop(id, None)

    async def dispatch_analysis(self, id):
        if self.analysis_cleanup_failed: raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503)
        for oid, _task in self.running_analysis(id): await self.cancel(id, oid)
        with self.state_lock:
            workspace = self.workspaces.get(id)
            if not workspace or workspace.project is None: return
            pending = self.pending_analysis(id)
            if not pending or not pending.analysis_batch.enabled or not pending.analysis_batch.completed_field_ids or not self.analysis_enabled(): return
            if any(op.kind == 'rewrite_prose' and op.status in {'queued', 'running'} for op in workspace.project.operations): return
            if self.persist(id) == 'failed':
                pending.error_code = 'PROJECT_SAVE_FAILED';pending.analysis_batch.enabled = False;return
            selected = self.provider_factory()
            if selected is None: raise ProjectFailure('CONNECTION_REQUIRED')
            rules = self.rules.load()
            fields = pending.analysis_batch.completed_field_ids[:]
            remaining = [key for key in pending.target_field_ids if key not in fields]
            pending.target_field_ids = fields
            pending.analysis_batch.phase = 'dispatched'
            pending.base_revision = workspace.project_revision
            pending.captured_document_revision = workspace.document_revision
            pending.rules_used = rules
            pending.dependencies = result_dependencies(workspace, rules)
            captured = self.read_memory(id)
            if remaining: self.accumulate_analysis(id, remaining)
            if self.persist(id) == 'failed':
                pending.status, pending.error_code = 'failed', 'PROJECT_SAVE_FAILED'
                retry = self.accumulate_analysis(id, fields, fields)
                retry.error_code = 'PROJECT_SAVE_FAILED';return
            key = (id, pending.id)
            self.cancels[key] = threading.Event()
            self.tasks[key] = asyncio.create_task(self._run_analysis(captured, pending, selected))

    async def _run_analysis(self, captured, operation, selected):
        id, oid = captured.project_id, operation.id
        key = (id, oid);cancel = self.cancels[key]
        files = OperationFiles(self.temp_root);self.files[key] = files
        cleanup_failed = False
        def admitted():
            with self.state_lock:
                operation.status = 'running'
                operation.usage = Usage(logicalAttempts=1, internalInferenceRequests=None, reportedInputTokens=None, reportedOutputTokens=None)
                self._event(operation, 'operation.started')
                if id in self.save_errors: raise ProjectFailure('PROJECT_SAVE_FAILED', 503)
        try:
            prompt = reconciliation_input(captured, operation.target_field_ids, operation.rules_used)
            provider, model = selected
            service = GuiReconciliationContentService(QueuedProvider(provider, admitted), model)
            def run():
                with files.open(): return service.run(prompt, captured, operation.target_field_ids, files, cancel)
            async with self.worker_slot(cancel): proposal, response = await asyncio.to_thread(run)
            operation.usage = Usage(logicalAttempts=response.logical_attempts, internalInferenceRequests=response.internal_inference_count,
                reportedInputTokens=response.usage.input_tokens, reportedOutputTokens=response.usage.output_tokens)
            with self.state_lock:
                if cancel.is_set(): raise AdmissionCancelled()
                if id not in self.workspaces: raise ProjectFailure('PROJECT_DELETED')
                if self.rules.load().sha256 != operation.rules_used.sha256: raise ProjectFailure('RULES_CHANGED')
                apply_reconciliation(self.workspaces[id], operation.target_field_ids, proposal, operation.dependencies, operation.rules_used, self.clock().isoformat())
                operation.result_fingerprint = digest(proposal.model_dump(mode='json', by_alias=True))
                operation.editorial_recommendations = proposal.recommendations[:]
                operation.status = 'completed'
                self._event(operation, 'usage.updated', save=False);self._event(operation, 'operation.completed', save=False)
        except (ContentFailure, AdmissionCancelled, ProjectFailure, ValueError, SpikeError) as error:
            if isinstance(error, SpikeError):
                self.cleanup_error(error);cleanup_failed = True;self.analysis_cleanup_failed = True
            operation.status = 'cancelled' if cancel.is_set() or isinstance(error, AdmissionCancelled) else 'failed'
            code = str(error) if isinstance(error, ValueError) and str(error) in {'ANALYSIS_STALE','ANALYSIS_SCOPE_INVALID','INPUT_TOO_LARGE','NO_SAFE_CONTENT','INVALID_CONTENT_INPUT'} else 'INVALID_RESULT'
            operation.error_code = 'CANCELLED' if operation.status == 'cancelled' else getattr(error, 'code', code)
            attempts = max(operation.usage.logical_attempts if operation.usage else 0, error.logical_attempts if isinstance(error, ContentFailure) else 0)
            usage = error.usage if isinstance(error, ContentFailure) else None
            operation.usage = Usage(logicalAttempts=attempts, internalInferenceRequests=None,
                reportedInputTokens=usage.input_tokens if usage else None, reportedOutputTokens=usage.output_tokens if usage else None)
            self._event(operation, 'cancelled' if operation.status == 'cancelled' else 'operation.failed', save=False)
        except Exception:
            operation.status, operation.error_code = 'failed', 'INVALID_RESULT'
            self._event(operation, 'operation.failed', save=False)
        finally:
            self.files.pop(key, None)
            with self.state_lock:
                if id in self.workspaces:
                    if operation.status != 'completed':
                        pending = self.pending_analysis(id)
                        enabled = pending.analysis_batch.enabled if pending else False
                        invalidated = set(pending.target_field_ids) - set(pending.analysis_batch.completed_field_ids) if pending else set()
                        retained = operation.analysis_batch.completed_field_ids
                        retry = self.accumulate_analysis(id, retained, [field for field in retained if field not in invalidated])
                        if retry:
                            retry.analysis_batch.enabled = enabled and not cleanup_failed
                            if not retry.analysis_batch.enabled:
                                retry.error_code = 'PROCESS_CLEANUP_FAILED' if self.analysis_cleanup_failed else operation.error_code
                    self.persist(id)

    async def analysis_action(self, id, request):
        if request.action == 'invalidate':
            self.invalidate_analysis(id, request.field_ids)
            for oid, _task in self.running_analysis(id):
                asyncio.create_task(self.stop_obsolete_analysis(id, oid))
        else:
            self.read(id)
            with self.state_lock:
                pending = self.pending_analysis(id)
                if pending:
                    pending.analysis_batch.enabled = True;pending.error_code = None
                    self.persist(id);self.schedule_analysis(id)

    async def stop_obsolete_analysis(self, id, oid):
        try:
            await self.cancel(id, oid)
        except ProjectFailure as error:
            with self.state_lock:
                pending = self.pending_analysis(id)
                if pending:
                    pending.analysis_batch.enabled = False;pending.error_code = error.code
                    self.persist(id)

    async def set_analysis_preference(self, enabled):
        self.ensure_loaded()
        if not enabled:
            for id in list(self.workspaces):
                self.stop_analysis_timer(id)
                for oid, _task in self.running_analysis(id):
                    self.accumulate_analysis(id)
                    await self.cancel(id, oid)
                self.persist(id)
        else:
            for id in list(self.workspaces):
                pending = self.pending_analysis(id)
                if pending:
                    pending.analysis_batch.enabled = True;pending.error_code = None
                    self.persist(id);self.schedule_analysis(id)

    def restore_analysis_pending(self, id):
        workspace = self.workspaces[id]
        if workspace.project is None: return
        fields, ready = set(), set()
        for op in workspace.project.operations:
            if op.kind == 'reconcile_edits' and op.status == 'interrupted' and op.analysis_batch:
                fields.update(op.target_field_ids);ready.update(op.analysis_batch.completed_field_ids)
        if fields:
            pending = self.accumulate_analysis(id, fields, ready)
            pending.analysis_batch.enabled = False;pending.error_code = 'INTERRUPTED'

    async def prepare_analysis_rewrite(self, id):
        if self.analysis_cleanup_failed: raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503)
        self.stop_analysis_timer(id)
        with self.state_lock:
            pending = self.accumulate_analysis(id)
            if pending: pending.analysis_batch.enabled = False
        for oid, _task in self.running_analysis(id):
            await self.cancel(id, oid)
            operation = next(op for op in self.workspaces[id].project.operations if op.id == oid)
            if operation.error_code == 'PROCESS_CLEANUP_FAILED': raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503)
