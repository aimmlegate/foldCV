"""Template import as one task. Checkpoints commit through the repository; resume reads the sidecar."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.resume_core.models.template_import import ResumeTemplateImportV1
from packages.resume_core.project_repository import RepositoryFailure, decode_project
from packages.resume_core.template_import import TemplateImportFailure

from .errors import ProjectFailure
from .fold import sidecar_store

LOG = logging.getLogger(__name__)


class ImportCommand(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    client_request_id: str = Field(default='import', alias='clientRequestId', min_length=1, max_length=200)
    allow_text_rewrite: bool = Field(default=False, alias='allowTextRewrite')
    kind: Literal['start', 'resume', 'cancel']
    operation_id: str | None = Field(default=None, alias='operationId')
    task_id: str | None = Field(default=None, alias='taskId')


class ImportService:
    def __init__(self, projects, pipeline=None, *, commands=None):
        self.projects = projects
        self.pipeline = pipeline
        self.commands = commands
        self.runners = {}

    def _require_pipeline(self):
        if self.pipeline is None:
            raise ProjectFailure('JOB_DISABLED', 409)

    async def start(self, project_id, request, started):
        self._require_pipeline()
        self.projects.require_writable(project_id)
        task = self.projects.tasks.start(project_id, 'import', stage='starting',
            detail={'clientRequestId': request.client_request_id})
        self.runners[task.id] = asyncio.create_task(self.drive(task, request, started))
        return task.id

    async def drive(self, task, request, started):
        project_id = task.project_id
        session = None
        try:
            session = self.projects.repository.open(project_id)
            with session.lock:
                session.pins += 1
            command = request
            if self.commands is not None and request.kind == 'start':
                command = await asyncio.to_thread(self.commands, project_id, request.client_request_id,
                    request.allow_text_rewrite)

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
                self.projects.tasks.update(task.id, stage='processing', detail={'operationId': operation_id})
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
            result = await self.pipeline.run(project_id, command, admitted=admitted, cancel_event=task.cancel)
            state = 'cancelled' if task.cancel.is_set() or getattr(result, 'state', None) == 'cancelled' else None
            if state is None and getattr(result, 'state', None) in {'failed', 'fenced'}:
                state = 'failed'
            publication = getattr(result, 'publication', None)
            if state is None and publication is not None and publication.state != 'saved':
                state = 'failed'
            error = None if state != 'failed' else getattr(publication, 'error_code', None) or 'PROCESS_FAILED'
            self.projects.tasks.finish(task.id, state or 'succeeded', error=error,
                detail={'operationId': getattr(result, 'id', request.client_request_id)})
        except (ProjectFailure, RepositoryFailure, TemplateImportFailure) as error:
            self._fail(task.id, getattr(error, 'code', 'PROCESS_FAILED'))
        except Exception:
            LOG.exception('import task failed')
            self._fail(task.id, 'PROCESS_FAILED')
        finally:
            if session is not None:
                with session.lock:
                    session.pins -= 1
            self.runners.pop(task.id, None)
            if not started.is_set():
                started.set()

    def _fail(self, task_id, code):
        try:
            self.projects.tasks.finish(task_id, 'failed', error=code)
        except Exception:
            pass

    async def cancel(self, project_id, request):
        if not request.task_id:
            raise ProjectFailure('INVALID_REQUEST', 422)
        _status(self.projects, project_id, request.task_id)
        task = self.projects.tasks.cancel(request.task_id)
        runner = self.runners.get(request.task_id)
        if runner is not None:
            try:
                await asyncio.wait_for(asyncio.shield(runner), 2)
            except asyncio.TimeoutError:
                pass
        if task.state == 'running':
            self.projects.tasks.finish(task.id, 'cancelled')
        return _status(self.projects, project_id, task.id)

    def statuses(self, project_id):
        for task in self.projects.tasks.running(project_id, 'import'):
            if self.pipeline is None or not hasattr(self.pipeline, 'read'):
                continue
            workspace = self.pipeline.read(project_id)
            data = workspace.project or workspace.pre_draft
            operations = data.template_operations
            operation = operations[-1] if operations else None
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
                    'technologyCount': len(technologies)}}
            stage = 'publication' if operation is not None and operation.state == 'finalizing' else 'processing'
            self.projects.tasks.update(task.id, stage=stage, detail=details)
        return self.projects.tasks.list(project_id)

    def resume_saved(self, project_id, operation_id):
        """Read the sidecar and commit it at the revision it names. Nothing is written before that commit."""
        repository = self.projects.repository
        session = repository.open(project_id)
        stored = sidecar_store(session.directory).read(project_id, operation_id)
        if stored is None:
            return session.workspace
        base, operation, facts = stored
        raw = (session.directory / 'workspace.json').read_bytes()
        workspace = decode_project(session.directory, raw, history=True)
        if base != workspace.project_revision:
            raise RepositoryFailure('OUTCOME_UNKNOWN')
        copied = workspace.model_copy(deep=True)
        owner = copied.project or copied.pre_draft
        if owner is None or not any(item.id == operation.id for item in owner.template_operations):
            raise RepositoryFailure('OUTCOME_UNKNOWN')
        owner.template_operations = [operation if item.id == operation.id else item for item in owner.template_operations]
        owner.facts = facts
        return repository.replace(project_id, base_revision=base, workspace=copied, reason='import-resume',
            client_mutation_id='resume-' + operation.id,
            request_sha256=hashlib.sha256(operation.id.encode()).hexdigest())

    def publish_at(self, project_id, task_id, workspace, base_revision):
        """One publication commit. A moved revision fails the import task and reports the conflict."""
        try:
            return self.projects.repository.replace(project_id, base_revision=base_revision, workspace=workspace,
                reason='publication', client_mutation_id='publication-' + task_id,
                request_sha256=hashlib.sha256(task_id.encode()).hexdigest())
        except RepositoryFailure as error:
            if error.code == 'REVISION_CONFLICT':
                self._fail(task_id, 'REVISION_CONFLICT')
            raise


def _status(projects, project_id, task_id):
    found = next((item for item in projects.tasks.list(project_id) if item['id'] == task_id), None)
    if found is None:
        raise ProjectFailure('JOB_NOT_FOUND', 404)
    return found
