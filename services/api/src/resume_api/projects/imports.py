"""Template import as one task. Checkpoints commit through the repository; resume reads the sidecar."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.resume_core.models.template_import import ResumeTemplateImportV1
from packages.resume_core.project_repository import RepositoryFailure, decode_project
from packages.resume_core.reasoning import ReasoningEffort
from packages.resume_core.template_import import TemplateImportFailure

from ..importer.template_transport import JOB_PERMIT
from ..inference_admission import INFERENCE, AdmissionBlocked, AdmissionCancelled
from .errors import ProjectFailure
from .exports import pinned
from .fold import sidecar_store
from .import_progress import import_progress

LOG = logging.getLogger(__name__)
# A cancelled model call ends within seconds (its process group is stopped); the wait at shutdown and sign-out.
STOP_SECONDS = 15


class ImportCommand(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    client_request_id: str = Field(default='import', alias='clientRequestId', min_length=1, max_length=200)
    allow_text_rewrite: bool = Field(default=False, alias='allowTextRewrite')
    kind: Literal['start', 'resume', 'cancel']
    operation_id: str | None = Field(default=None, alias='operationId')
    task_id: str | None = Field(default=None, alias='taskId')
    # The import model's effort for this start; None keeps its catalog default. The capture checks it in the catalog.
    effort: ReasoningEffort | None = None


class _Stop:
    """The task's cancel flag as the admission queue waits on it."""

    def __init__(self, event):
        self.event = event

    def is_set(self):
        return self.event.is_set()

    async def wait(self):
        while not self.event.is_set():
            await asyncio.sleep(0.05)


def outcome(task, result):
    """The task's final state. The publication commit is the point of no return: a saved import succeeded even when a
    cancel came after it; before it, a cancel leaves the import unpublished."""
    state, publication = getattr(result, 'state', None), getattr(result, 'publication', None)
    if publication is not None and publication.state == 'saved':
        return 'succeeded', None
    if task.cancel.is_set() or state == 'cancelled':
        return 'cancelled', None
    if state in {'failed', 'fenced'} or publication is not None:
        return 'failed', getattr(publication, 'error_code', None) or 'PROCESS_FAILED'
    return 'succeeded', None


class ImportService:
    def __init__(self, projects, pipeline=None, *, commands=None, admission=INFERENCE,
                 wall=lambda: datetime.now(timezone.utc)):
        self.projects = projects
        self.pipeline = pipeline
        self.commands = commands
        self.admission = admission
        self.wall = wall
        self.runners = {}
        # When an import last took or returned the inference permit: a queued import is quiet only while this stays.
        self.queue_moved = None
        # project -> (permit, operation id): a permit whose import may still own a model process stays held until
        # every attempt of that operation has verified cleanup.
        self.retained = {}

    def _require_pipeline(self):
        if self.pipeline is None:
            raise ProjectFailure('JOB_DISABLED', 409)

    async def start(self, project_id, request, started):
        self._require_pipeline()
        await asyncio.to_thread(self.projects.require_writable, project_id)
        task = self.projects.tasks.start(project_id, 'import', stage='starting',
            detail={'clientRequestId': request.client_request_id})
        self.runners[task.id] = asyncio.create_task(self.drive(task, request, started))
        return task.id

    async def drive(self, task, request, started):
        """Only the runner finishes its task, as its last step: a finished import holds no pin, lock or permit."""
        project_id, held = task.project_id, {}
        state, error, detail = 'failed', 'PROCESS_FAILED', None
        try:
            async with pinned(self.projects.repository, project_id):
                try:
                    result = await self.run(task, request, started, held)
                finally:
                    if 'token' in held:
                        JOB_PERMIT.reset(held['token'])
                    if 'permit' in held:
                        await asyncio.to_thread(self._settle, project_id, held['operation'], held['permit'])
                        self.queue_moved = self.wall()
            state, error = outcome(task, result)
            detail = {'operationId': getattr(result, 'id', request.client_request_id)}
        except (ProjectFailure, RepositoryFailure, TemplateImportFailure) as failure:
            code = getattr(failure, 'code', 'PROCESS_FAILED')
            state, error = ('cancelled', None) if code == 'CANCELLED' else ('failed', code)
        except Exception:
            LOG.exception('import task failed')
        finally:
            self.runners.pop(task.id, None)
            self.projects.tasks.finish(task.id, state, error=error, detail=detail)
            started.set()

    async def run(self, task, request, started, held):
        project_id = task.project_id
        command = request
        if self.commands is not None and request.kind == 'start':
            command = await asyncio.to_thread(self.commands, project_id, request.client_request_id,
                request.allow_text_rewrite, request.effort)

        async def admitted():
            operation_id = request.operation_id or request.client_request_id
            reader = getattr(self.pipeline, 'read', None)
            if reader is not None:
                try:
                    workspace = await asyncio.to_thread(reader, project_id)
                    owner = workspace.project or workspace.pre_draft
                    match = next((item for item in owner.template_operations
                        if item.client_request_id == request.client_request_id), None)
                    if match is not None:
                        operation_id = match.id
                except Exception:
                    pass
            # One permit for the whole run, as the job runtime held it: parallel blocks run under it and an
            # assistant turn waits instead of turning a block into a source fallback.
            held['permit'], held['operation'] = await self._permit(task, operation_id, started), operation_id
            held['token'] = JOB_PERMIT.set(held['permit'])
            self.queue_moved = self.wall()
            self.projects.tasks.update(task.id, stage='processing', detail={'operationId': operation_id,
                'admittedAt': self.queue_moved.isoformat()})
            started.set()

        if request.kind == 'resume':
            if not request.operation_id:
                raise ProjectFailure('INVALID_REQUEST', 422)
            await asyncio.to_thread(self.resume_saved, project_id, request.operation_id)
            workspace = await asyncio.to_thread(self.pipeline.read, project_id)
            operation = next((item for item in (workspace.project or workspace.pre_draft).template_operations
                if item.id == request.operation_id), None)
            if operation is None:
                raise ProjectFailure('IMPORT_OPERATION_UNKNOWN', 404)
            command = ResumeTemplateImportV1(kind='resume_import', protocol='template_import_v1',
                operationId=operation.id, authorizationId='resume-' + request.client_request_id,
                authorityHash=operation.capture.authority_hash)
        return await self.pipeline.run(project_id, command, admitted=admitted, cancel_event=task.cancel)

    async def _permit(self, task, operation_id, started):
        project_id = task.project_id
        retained = self.retained.pop(project_id, None)
        if retained is not None:
            permit, owner = retained
            if owner == operation_id or not await asyncio.to_thread(self._verified, project_id, owner):
                # The same import continues, or an earlier one may still own a process: nothing else may start.
                return permit
            permit.release()
        if self.admission.busy():
            # Another import or an assistant turn has the permit: the start reply returns now and this task waits in
            # the queue, instead of the reply timing out while the task keeps waiting.
            self.projects.tasks.update(task.id, stage='queued', detail={'operationId': operation_id,
                'queuedAt': self.wall().isoformat()})
            started.set()
        try:
            return await self.admission.reserve(_Stop(task.cancel))
        except (AdmissionBlocked, AdmissionCancelled):
            raise TemplateImportFailure('IMPORT_CLEANUP_UNKNOWN' if self.admission.blocked else 'CANCELLED') from None

    def _verified(self, project_id, operation_id):
        reader = getattr(self.pipeline, 'read', None)
        if reader is None:
            return True
        try:
            workspace = reader(project_id)
        except Exception:
            # Unknown cleanup keeps the permit: no other inference may start beside a process that may live.
            return False
        owner = workspace.project or workspace.pre_draft
        operation = next((item for item in owner.template_operations if item.id == operation_id), None)
        return operation is not None and all(attempt.cleanup.state == 'verified' for attempt in operation.attempts)

    def _settle(self, project_id, operation_id, permit):
        if self._verified(project_id, operation_id):
            permit.release()
        else:
            self.retained[project_id] = (permit, operation_id)

    def release(self, project_id):
        """Free the permit a stopped import of this project kept. The project is being deleted, so no later run of it
        can prove that cleanup, and every other import and assistant turn would wait for it forever."""
        retained = self.retained.pop(project_id, None)
        if retained is not None:
            retained[0].release()

    async def cancel(self, project_id, request):
        """Ask the import to stop; its runner finishes the task. The reply is the status after a short wait."""
        if not request.task_id:
            raise ProjectFailure('INVALID_REQUEST', 422)
        if _status(self.projects, project_id, request.task_id)['kind'] != 'import':
            raise ProjectFailure('JOB_NOT_FOUND', 404)
        self.projects.tasks.cancel(request.task_id)
        runner = self.runners.get(request.task_id)
        if runner is not None:
            await asyncio.wait({runner}, timeout=2)
        return _status(self.projects, project_id, request.task_id)

    def stop_all(self):
        """Ask every running import to stop (shutdown, sign-in change); each runner finishes its own task."""
        for identifier in list(self.runners):
            self.projects.tasks.cancel(identifier)

    async def shutdown(self, timeout=STOP_SECONDS):
        """Stop every import and wait for its runner; one still running after `timeout` may own a model process."""
        self.stop_all()
        runners = [runner for runner in self.runners.values() if not runner.done()]
        if runners:
            _done, pending = await asyncio.wait(runners, timeout=timeout)
            if pending:
                raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503)

    def statuses(self, project_id):
        for task in self.projects.tasks.running(project_id, 'import'):
            if self.pipeline is None or not hasattr(self.pipeline, 'read'):
                continue
            workspace = self.pipeline.read(project_id)
            data = workspace.project or workspace.pre_draft
            operations = data.template_operations
            named = task.detail.get('operationId')
            operation = next((item for item in operations if item.id == named), operations[-1] if operations else None)
            facts = data.facts
            def text(record, field):
                value = getattr(record, field, None)
                return getattr(value, 'raw_text', '')
            records = list(facts.records)
            candidate = next((record for record in records if record.kind == 'candidate'), None)
            jobs = [{'id': record.id, 'employer': text(record, 'employer'), 'role': text(record, 'role')}
                for record in records if record.kind == 'employment']
            technologies = [text(record, 'display') for record in records if record.kind == 'technology']
            details = {'operationId': operation.id if operation is not None else None,
                'processingSeconds': operation.capture.policy.processing_seconds if operation is not None else None,
                'discoveries': {'name': text(candidate, 'name'), 'title': text(candidate, 'title'),
                    'facts': len(records) + sum(record.active for record in facts.extensions),
                    'jobs': jobs[:3], 'jobCount': len(jobs), 'technologies': technologies[:8],
                    'technologyCount': len(technologies)},
                'progress': import_progress(operation, data.template_package, stage=task.stage, now=self.wall(),
                    started_at=task.started_at, queued_at=task.detail.get('queuedAt'),
                    admitted_at=task.detail.get('admittedAt'), queue_moved_at=self.queue_moved)}
            # Only an admitted task moves between processing and publication; the runner owns the earlier stages.
            stage = None
            if task.stage in {'processing', 'publication'}:
                stage = 'publication' if operation is not None and operation.state == 'finalizing' else 'processing'
            self.projects.tasks.update(task.id, stage=stage, detail=details)
        return self.projects.tasks.list(project_id)

    def resume_saved(self, project_id, operation_id):
        """Read the sidecar and commit it at the revision it names. Nothing is written before that commit."""
        repository = self.projects.repository
        session = repository.open(project_id)
        with session.lock:
            stored = sidecar_store(session.directory).read(project_id, operation_id)
            if stored is None:
                return None
            base, operation, facts = stored
            raw = (session.directory / 'workspace.json').read_bytes()
            workspace = decode_project(session.directory, raw, history=True)
            if base != workspace.project_revision:
                raise RepositoryFailure('OUTCOME_UNKNOWN')
            copied = workspace.model_copy(deep=True)
            owner = copied.project or copied.pre_draft
            if owner is None or not any(item.id == operation.id for item in owner.template_operations):
                raise RepositoryFailure('OUTCOME_UNKNOWN')
            owner.template_operations = [operation if item.id == operation.id else item
                for item in owner.template_operations]
            owner.facts = facts
            return repository.replace(project_id, base_revision=base, workspace=copied, reason='import-resume',
                client_mutation_id='resume-' + operation.id,
                request_sha256=hashlib.sha256(operation.id.encode()).hexdigest())


def _status(projects, project_id, task_id):
    found = next((item for item in projects.tasks.list(project_id) if item['id'] == task_id), None)
    if found is None:
        raise ProjectFailure('JOB_NOT_FOUND', 404)
    return found
