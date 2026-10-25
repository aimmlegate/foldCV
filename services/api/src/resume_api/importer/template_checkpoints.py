"""Template metadata shares the existing canonical publisher and checkpoint locks."""

import asyncio
import threading

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.project_limits import save_allowance_seconds
from packages.resume_core.template_import import TemplateImportFailure, checked, identity

from .template_sidecar import OperationSidecar


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


def save_seconds():
    # A save rewrites and re-validates the whole project file, so a larger project size setting allows longer saves.
    return LIMITS.receipt_seconds + save_allowance_seconds()


class TemplateCheckpoints:
    def __init__(self, publisher, *, originals, artifacts=None, images=None, wall, id_factory=identity, export_only=False,
                 checkpoint_seconds=None, cleanup_seconds=LIMITS.cleanup_seconds):
        self.publisher, self.originals = publisher, originals
        self.artifacts = artifacts if artifacts is not None else {}
        self.images = images if images is not None else {}
        self.wall, self.id_factory, self.export_only = wall, id_factory, export_only
        self.checkpoint_locks = publisher.template_checkpoint_locks
        self.pending_checkpoints = publisher.template_checkpoint_tasks
        self.async_locks = publisher.template_checkpoint_async_locks
        self.checkpoint_fences = publisher.template_checkpoint_fences
        self.checkpoint_owners = publisher.template_checkpoint_owners
        self.fixed_checkpoint_seconds, self.cleanup_seconds = checkpoint_seconds, cleanup_seconds
        self.sidecar = OperationSidecar(publisher)
        # Durable reads shared by the pipelines of one publisher, keyed by the identity of the saved files.
        self.read_cache = publisher.__dict__.setdefault('template_read_cache', {})

    @property
    def checkpoint_seconds(self):
        return self.fixed_checkpoint_seconds if self.fixed_checkpoint_seconds is not None else save_seconds()

    def read_saved(self, project):
        """The project as saved, without the sidecar steps of a running import, and the checksum of its file."""
        workspace, checksum = self.publisher.canonical.read_committed(project)
        if workspace.schema_version != 7:
            raise TemplateImportFailure('IMPORT_PROTOCOL_MISMATCH')
        return workspace, checksum

    def read(self, project):
        """The durable state: the saved project with each running import's sidecar. While neither file changed the
        last result is returned; callers read it and never change it."""
        key = self.publisher.canonical.committed_key(project)
        cached = self.read_cache.get(project)
        if cached is not None and cached[0] == key and cached[1] == self.sidecar.keys(project, cached[2]):
            return cached[2]
        workspace = self.overlaid(project, self.read_saved(project)[0])[0]
        self.read_cache[project] = (key, self.sidecar.keys(project, workspace), workspace)
        return workspace

    def overlaid(self, project, workspace):
        """The freshly read workspace, changed in place so a running import with a current sidecar reads as the sidecar
        (its operation and the facts), and whether one did."""
        data = workspace.project or workspace.pre_draft
        if data is None:
            return workspace, False
        overlays = [self.sidecar.overlay(project, workspace.project_revision, operation) for operation in data.template_operations]
        facts = [value for _operation, value in overlays if value is not None]
        if len(facts) > 1:
            # One import runs per project; two current sidecars mean the saved state is not one import's.
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        changed = any(new is not old for (new, _facts), old in zip(overlays, data.template_operations))
        data.template_operations = [operation for operation, _facts in overlays]
        if facts:
            data.facts = facts[0]
        return workspace, changed

    def folded(self, saved, after):
        """Whether a save from the saved operations to after keeps the retention rules for every import (an attempt
        moves one allowed step per save)."""
        from packages.resume_core.project_store import ProjectStoreFailure
        from packages.resume_core.template_retention import retain_operation
        before = {value.id: value for value in saved}
        try:
            for operation in (after.project or after.pre_draft).template_operations:
                if operation.id in before:
                    retain_operation(before[operation.id], operation)
        except ProjectStoreFailure:
            return False
        return True

    def update_operation(self, project, operation_id, transition, *, copy_on_write=False):
        """Apply a processing step to the sidecar instead of saving the whole project.

        The transition returns the operation and may replace the facts of its holder; it changes nothing else. A
        copy_on_write transition builds its result with the template_import functions, which copy and check the
        operation, so it gets the stored operation itself."""
        self._require_checkpoint(project, False)
        with self.checkpoint_locks.setdefault(project, threading.RLock()):
            self._require_checkpoint(project, False)
            current = self.read(project)
            data = current.project or current.pre_draft
            prior = next((value for value in data.template_operations if value.id == operation_id), None)
            if prior is None:
                raise TemplateImportFailure('IMPORT_OPERATION_UNKNOWN')
            given = prior if copy_on_write else prior.model_copy(deep=True)
            # A shallow holder: the transition may replace its facts; the cached read stays as it was.
            holder = data.model_copy()
            updated = transition(given, holder, current)
            if updated is given:
                if copy_on_write:
                    raise TemplateImportFailure('IMPORT_OPERATION_UNKNOWN')
                updated = checked(updated)
            if updated == prior and holder.facts is data.facts:
                return current
            holder.template_operations = [updated if value is prior else value for value in data.template_operations]
            view = current.model_copy()
            if current.project is not None:
                view.project = holder
            else:
                view.pre_draft = holder
            from packages.resume_core.project_store import ProjectStoreFailure
            from packages.resume_core.rich_project_store import retain_template_state
            try:
                # The rules a project save applies to the import record and the facts.
                retain_template_state(current, view)
            except ProjectStoreFailure:
                raise BackgroundFailure('OUTCOME_UNKNOWN') from None
            self.sidecar.write(project, current.project_revision, updated, holder.facts)
            self.read_cache[project] = (
                self.publisher.canonical.committed_key(project), self.sidecar.keys(project, view), view)
            return view

    def _require_checkpoint(self, project, owned):
        if project in self.checkpoint_fences or project in self.pending_checkpoints and not owned:
            raise BackgroundFailure('OUTCOME_UNKNOWN')

    def checkpoint(self, project, transition, *, _owned=False):
        self._require_checkpoint(project, _owned)
        with self.checkpoint_locks.setdefault(project, threading.RLock()):
            self._require_checkpoint(project, _owned)
            for retry in range(4):
                before, checksum = self.read_saved(project)
                data = before.project or before.pre_draft
                saved_operations = list(data.template_operations) if data is not None else []
                revision = before.project_revision
                before, pending = self.overlaid(project, before)
                after = transition(before.model_copy(deep=True))
                if after == before:
                    return before
                if self.export_only:
                    export_scope(before, after)
                # Sidecar steps are folded into this save; when the fold and the step together would move an attempt
                # past an allowed step, the folded steps are saved alone first.
                fold_only = pending and not self.folded(saved_operations, after)
                if fold_only:
                    after = before.model_copy(deep=True)
                after.project_revision = revision + 1
                if after.project is not None:
                    after.project.revision = after.project_revision
                after.updated_at = self.wall()
                after = WorkspaceV7.model_validate(after.model_dump(by_alias=True))
                try:
                    saved, _duplicate = self.publisher.snapshot(project, checksum, after,
                        self.id_factory('metadata_template'), originals=self.originals, artifacts=self.artifacts, images=self.images)
                except BackgroundFailure as error:
                    # Exports keep three attempts; the fourth pass only serves a fold saved alone.
                    if not self.export_only or error.code != 'DEPENDENCY_CHANGED' or retry == 2:
                        raise
                    continue
                for operation in saved_operations:
                    self.sidecar.discard(project, operation.id)
                if fold_only:
                    continue
                return saved

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
