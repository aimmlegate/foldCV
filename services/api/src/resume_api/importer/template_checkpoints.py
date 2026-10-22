"""Template metadata shares the existing canonical publisher and checkpoint locks."""

import asyncio
import threading

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.template_import import TemplateImportFailure, identity


def export_scope(before, after):
    if before.project is None or after.project is None:
        raise TemplateImportFailure('IMPORT_PROJECT_NOT_AUTHORED')
    left, right = [value.model_dump(mode='json', by_alias=True) for value in (before, after)]
    for value in (left, right):
        value.pop('projectRevision')
        value.pop('updatedAt')
        project = value['project']
        project.pop('revision')
        for field in ('exports', 'exportInputs', 'renders'):
            project.pop(field, None)
        for operation in project['templateOperations']:
            operation.pop('exportAttempts', None)
    if left != right:
        raise BackgroundFailure('JOB_SCOPE_INVALID')
    previous, current = before.project, after.project
    if (current.export_inputs[:len(previous.export_inputs)] != previous.export_inputs or
            current.renders[:len(previous.renders)] != previous.renders or
            [value.id for value in current.exports[:len(previous.exports)]] != [value.id for value in previous.exports]):
        raise BackgroundFailure('JOB_SCOPE_INVALID')
    states = {'pending': {'pending', 'running', 'failed'}, 'running': {'running', 'completed', 'failed'},
        'completed': {'completed'}, 'failed': {'failed'}}
    for old, new in zip(previous.exports, current.exports):
        changed = new.model_copy(update={'state': old.state, 'artifact_hash': old.artifact_hash, 'error_code': old.error_code})
        if (changed != old or new.state not in states[old.state] or
                old.state in {'completed', 'failed'} and new != old):
            raise BackgroundFailure('JOB_SCOPE_INVALID')
    inputs = {value.attempt_id: value for value in current.export_inputs}
    for new in current.exports[len(previous.exports):]:
        if new.state != 'pending' or new.id not in inputs:
            raise BackgroundFailure('JOB_SCOPE_INVALID')
    attempts = {value.id: value for value in current.exports}
    for attempt in current.exports:
        if (attempt.state == 'completed' and (attempt.artifact_hash is None or attempt.error_code is not None)
                or attempt.state == 'failed' and (attempt.error_code is None or attempt.artifact_hash is not None)
                or attempt.state in {'pending', 'running'} and (attempt.artifact_hash is not None or attempt.error_code is not None)):
            raise BackgroundFailure('JOB_SCOPE_INVALID')
    for rendered in current.renders[len(previous.renders):]:
        attempt, captured = attempts.get(rendered.id), inputs.get(rendered.id)
        if attempt is None or captured is None or attempt.state != 'completed' or (
                rendered.docx_sha256, rendered.document_revision, rendered.facts_revision,
                rendered.template_sha256, rendered.renderer_sha256, rendered.renderer_version) != (
                attempt.artifact_hash, captured.snapshot.document_revision, captured.request.facts.revision,
                captured.request.package_hash, captured.request.renderer.sha256, captured.request.renderer.version):
            raise BackgroundFailure('JOB_SCOPE_INVALID')
    for operation in current.template_operations:
        if operation.export_attempts != [value for value in current.exports
                if value.publication_intent_id is not None and value.publication_intent_id == operation.publication.intent_id]:
            raise BackgroundFailure('JOB_SCOPE_INVALID')
    if any(value.publication_intent_id is not None and not any(
            operation.publication.intent_id == value.publication_intent_id for operation in current.template_operations)
            for value in current.exports):
        raise BackgroundFailure('JOB_SCOPE_INVALID')


class TemplateCheckpoints:
    def __init__(self, publisher, *, originals, artifacts=None, images=None, wall, id_factory=identity, export_only=False,
                 checkpoint_seconds=LIMITS.receipt_seconds, cleanup_seconds=LIMITS.cleanup_seconds):
        self.publisher, self.originals = publisher, originals
        self.artifacts = artifacts if artifacts is not None else {}
        self.images = images if images is not None else {}
        self.wall, self.id_factory, self.export_only = wall, id_factory, export_only
        self.checkpoint_locks = publisher.template_checkpoint_locks
        self.pending_checkpoints = publisher.template_checkpoint_tasks
        self.async_locks = publisher.template_checkpoint_async_locks
        self.checkpoint_fences = publisher.template_checkpoint_fences
        self.checkpoint_owners = publisher.template_checkpoint_owners
        self.checkpoint_seconds, self.cleanup_seconds = checkpoint_seconds, cleanup_seconds

    def read(self, project):
        workspace, _checksum = self.publisher.canonical.read_committed(project)
        if workspace.schema_version != 7:
            raise TemplateImportFailure('IMPORT_PROTOCOL_MISMATCH')
        return workspace

    def _require_checkpoint(self, project, owned):
        if project in self.checkpoint_fences or project in self.pending_checkpoints and not owned:
            raise BackgroundFailure('OUTCOME_UNKNOWN')

    def checkpoint(self, project, transition, *, _owned=False):
        self._require_checkpoint(project, _owned)
        with self.checkpoint_locks.setdefault(project, threading.RLock()):
            self._require_checkpoint(project, _owned)
            for retry in range(3):
                before = self.read(project)
                after = transition(before.model_copy(deep=True))
                if after == before:
                    return before
                if self.export_only:
                    export_scope(before, after)
                after.project_revision = before.project_revision + 1
                if after.project is not None:
                    after.project.revision = after.project_revision
                after.updated_at = self.wall()
                after = WorkspaceV7.model_validate(after.model_dump(by_alias=True))
                try:
                    saved, _duplicate = self.publisher.snapshot(project, digest_bytes(before), after,
                        self.id_factory('metadata_template'), originals=self.originals, artifacts=self.artifacts, images=self.images)
                    return saved
                except BackgroundFailure as error:
                    if not self.export_only or error.code != 'DEPENDENCY_CHANGED' or retry == 2:
                        raise

    def fence_checkpoint(self, project, operation_id=None):
        self.checkpoint_fences.setdefault(project, operation_id)

    async def _await_checkpoint(self, project, task, seconds):
        uncertain = False
        try:
            return await asyncio.wait_for(asyncio.shield(task), seconds)
        except asyncio.TimeoutError:
            uncertain = True
            self.fence_checkpoint(project, self.checkpoint_owners.get(project))
            raise BackgroundFailure('OUTCOME_UNKNOWN') from None
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(asyncio.shield(task), self.cleanup_seconds)
            except BaseException:
                uncertain = True
                self.fence_checkpoint(project, self.checkpoint_owners.get(project))
            raise
        except Exception as error:
            if not isinstance(error, (BackgroundFailure, TemplateImportFailure)) or getattr(error, 'code', None) in {
                    'OUTCOME_UNKNOWN', 'PROJECT_SAVE_FAILED', 'SAVE_FAILED'}:
                uncertain = True
                self.fence_checkpoint(project, self.checkpoint_owners.get(project))
                raise BackgroundFailure('OUTCOME_UNKNOWN') from None
            raise
        finally:
            if task.done() and not uncertain:
                self.pending_checkpoints.pop(project, None)
                self.checkpoint_owners.pop(project, None)

    def _retain(self, project, coroutine, operation_id):
        task = asyncio.create_task(coroutine)
        task.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
        self.pending_checkpoints[project] = task
        self.checkpoint_owners[project] = operation_id
        return task

    async def checkpoint_async(self, project, transition, *, operation_id=None):
        async with self.async_locks.setdefault(project, asyncio.Lock()):
            if project in self.pending_checkpoints or project in self.checkpoint_fences:
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            task = self._retain(project, asyncio.to_thread(self.checkpoint, project, transition, _owned=True), operation_id)
            return await self._await_checkpoint(project, task, self.checkpoint_seconds)

    async def reconcile_checkpoint(self, project, *, operation_id=None):
        async with self.async_locks.setdefault(project, asyncio.Lock()):
            if operation_id is not None and (project in self.checkpoint_owners and self.checkpoint_owners[project] != operation_id
                    or project in self.checkpoint_fences and self.checkpoint_fences[project] != operation_id):
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            task = self.pending_checkpoints.get(project)
            if task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(task), self.cleanup_seconds)
                except asyncio.TimeoutError:
                    self.fence_checkpoint(project, self.checkpoint_owners.get(project))
                    raise BackgroundFailure('OUTCOME_UNKNOWN') from None
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
            def recover():
                self.publisher.recover(project, clear_fence=False)
                return self.read(project)
            task = self._retain(project, asyncio.to_thread(recover), operation_id)
            try:
                current = await self._await_checkpoint(project, task, self.checkpoint_seconds)
            except BaseException:
                self.fence_checkpoint(project, operation_id)
                # A known failure must retain recovery ownership as well.
                self.pending_checkpoints[project] = task
                self.checkpoint_owners[project] = operation_id
                raise
            self.checkpoint_fences.pop(project, None)
            return current
