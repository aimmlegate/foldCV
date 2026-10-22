"""Bound canonical I/O without pretending a timed-out filesystem write stopped."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_authority import TemplateFinalizationBinding
from packages.resume_core.models.template_import import PublicationOutcome
from packages.resume_core.template_import import instant


@dataclass(frozen=True)
class PersistenceWindow:
    expires_at: str
    elapsed_expiry: float

    @classmethod
    def capture(cls, expires_at, now, elapsed, *, started_at=None):
        remaining = max(0, (instant(expires_at) - instant(now)).total_seconds())
        if started_at is not None and instant(now) < instant(started_at):
            remaining = 0
        return cls(expires_at, elapsed + remaining)

    def remaining(self, now, elapsed):
        return max(0, min(self.elapsed_expiry - elapsed,
            (instant(self.expires_at) - instant(now)).total_seconds()))


class TemplatePersistence:
    def __init__(self, publisher, *, wall, elapsed=time.monotonic):
        self.publisher, self.wall, self.elapsed = publisher, wall, elapsed
        self.pending, self.windows, self.saved = {}, {}, {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='foldcv-template-persistence')

    async def wait(self, tasks, *, timeout):
        return await asyncio.wait(tasks, timeout=timeout)

    async def bounded(self, project, action, window):
        if project in self.pending:
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        remaining = window.remaining(self.wall(), self.elapsed())
        if remaining <= 0:
            raise BackgroundFailure('REQUEST_EXPIRED')
        worker = self.executor.submit(action)
        task = asyncio.wrap_future(worker)
        task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
        self.pending[project] = worker
        try:
            done, _waiting = await self.wait({task}, timeout=remaining)
            if not done:
                self.publisher.jobs.fences.setdefault(project, 'OUTCOME_UNKNOWN')
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            return task.result()
        except BaseException:
            if not worker.done():
                self.publisher.jobs.fences.setdefault(project, 'OUTCOME_UNKNOWN')
            raise
        finally:
            # Keep the task, including its exception, until explicit reconciliation.
            if worker.done():
                self.pending.pop(project, None)

    async def wait_pending(self, project):
        worker = self.pending.get(project)
        if worker is not None:
            return await asyncio.shield(asyncio.wrap_future(worker))

    async def reconcile(self, project):
        task = self.pending.get(project)
        if task is not None:
            if not task.done():
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            try:
                task.result()
            except Exception:
                pass
            self.pending.pop(project, None)
        return await asyncio.to_thread(self.publisher.recover, project)

    def outcome(self, project, binding):
        task = self.pending.get(project)
        if task is not None and not task.done():
            return PublicationOutcome(state='outcome_unknown', intentId=None, workspaceHash=None, errorCode='OUTCOME_UNKNOWN')
        return self._durable_outcome(project, binding)

    def _durable_outcome(self, project, binding):
        state = self.publisher.jobs.load(project)
        intents = [intent for intent in state.manual_intents if intent.template_finalization == binding]
        if len(intents) > 1:
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        if not intents:
            return PublicationOutcome(state='failed_before_replacement', intentId=None, workspaceHash=None, errorCode='SAVE_FAILED')
        intent = intents[0]
        if intent.phase == 'receipt_stored':
            return PublicationOutcome(state='saved', intentId=intent.id,
                workspaceHash=intent.after_workspace_sha256, errorCode=None)
        if intent.phase == 'reconciled':
            code = intent.reconciled_reason.code if intent.reconciled_reason else 'SAVE_FAILED'
            return PublicationOutcome(state='cancelled' if code == 'CANCELLED' else 'failed_before_replacement',
                intentId=intent.id, workspaceHash=None, errorCode=code)
        return PublicationOutcome(state='outcome_unknown', intentId=intent.id, workspaceHash=None, errorCode='OUTCOME_UNKNOWN')

    def renew_candidate(self, project, operation, authored, now, *, id_factory):
        from packages.resume_core.template_finalization import capture_finalization
        from packages.resume_core.template_import import authorization
        previous, current = operation.finalization, authorization(operation)
        if (previous is None or current.kind != 'resume' or previous.authorization_id == current.id
                or project in self.pending):
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        with self.publisher._writer(project), self.publisher.jobs.guard(project) as directory:
            state = self.publisher.jobs._read(project, directory)
            self.publisher._writable(state)
            workspace, _checksum = self.publisher.canonical._read_committed_unlocked(project)
            retained = next(value for value in (workspace.project or workspace.pre_draft).template_operations if value.id == operation.id)
            if retained != operation or workspace.project is not None:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            intents = [intent for intent in state.manual_intents if intent.template_finalization is not None
                and intent.template_finalization.operation_id == operation.id
                and intent.template_finalization.finalization_id == previous.id]
            if any(intent.phase != 'reconciled' for intent in intents):
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            # No intent under the writer lock also proves replacement never began.
            updated = operation.model_copy(deep=True)
            updated.finalization = None
            candidate = capture_finalization(updated, authored, now, id_factory=id_factory)
            if candidate.candidate_hash != previous.candidate_hash:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            return candidate

    async def publish(self, before, after, operation, *, originals, artifacts=None, images=None):
        candidate = operation.finalization
        if candidate is None:
            raise BackgroundFailure('JOB_SCOPE_INVALID')
        project = before.project_id
        binding = TemplateFinalizationBinding(operationId=operation.id, authorizationId=candidate.authorization_id,
            finalizationId=candidate.id)
        if (project, candidate.id) in self.saved:
            return self.saved[(project, candidate.id)].model_copy(deep=True)
        window = self.windows.setdefault((project, candidate.id), PersistenceWindow.capture(candidate.expires_at,
            self.wall(), self.elapsed(), started_at=candidate.started_at))
        def transaction():
            try:
                self.publisher.snapshot(project, digest_bytes(before), after,
                    'template_publication_' + candidate.id, originals=originals, artifacts=artifacts,
                    images=images, template_finalization=binding)
            except Exception as error:
                self.publisher.recover(project)
                result = self._durable_outcome(project, binding)
                if result.state == 'failed_before_replacement' and result.intent_id is None:
                    result.error_code = getattr(error, 'code', 'SAVE_FAILED')
                return result
            return self._durable_outcome(project, binding)
        try:
            outcome = await self.bounded(project, transaction, window)
        except BackgroundFailure as error:
            if error.code == 'REQUEST_EXPIRED' and project not in self.pending:
                return PublicationOutcome(state='outcome_unknown', intentId=None, workspaceHash=None,
                    errorCode='REQUEST_EXPIRED')
            return PublicationOutcome(state='outcome_unknown', intentId=None, workspaceHash=None, errorCode='OUTCOME_UNKNOWN')
        if outcome.state == 'outcome_unknown':
            return outcome
        if outcome.state == 'saved':
            self.saved[(project, candidate.id)] = outcome.model_copy(deep=True)
        def checkpoint():
            current, checksum = self.publisher.canonical.read_committed(project)
            retained = next(item for item in (current.project or current.pre_draft).template_operations if item.id == operation.id)
            if retained.publication == outcome:
                return retained.publication
            updated = current.model_copy(deep=True)
            record = next(item for item in (updated.project or updated.pre_draft).template_operations if item.id == operation.id)
            record.publication, record.state = outcome, {'saved': 'published', 'cancelled': 'cancelled',
                'failed_before_replacement': 'failed'}[outcome.state]
            if outcome.state == 'cancelled':
                record.authorizations[-1].state = 'cancelled'
            updated.project_revision += 1
            if updated.project is not None:
                updated.project.revision = updated.project_revision
            updated.updated_at = self.wall()
            self.publisher.snapshot(project, checksum, updated, 'metadata_template_outcome_' + candidate.id,
                originals=originals, artifacts=artifacts, images=images)
        try:
            await self.bounded(project, checkpoint, window)
        except Exception:
            # The caller can report saved and reconcile this metadata checkpoint later.
            return outcome
        return outcome
