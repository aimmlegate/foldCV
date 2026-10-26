"""Template jobs release inference ownership before application publication."""

import asyncio

from packages.resume_core.background_store import BackgroundFailure, TERMINAL_EXECUTION
from packages.resume_core.background_supervisor import ExecutionOutcome
from packages.resume_core.models.background import JobFailure, JobIdentity, JobSubmissionV1
from packages.resume_core.models.template_import import PublicationOutcome
from packages.resume_core.models.template_authority import TemplateFinalizationBinding
from packages.resume_core.rich_api import RichGenerationState
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.template_import import TemplateImportFailure, digest
from ..importer.template_pipeline import account_stop, operation_in


def job_code(code):
    if code in {'IMPORT_CAPTURE_STALE', 'IMPORT_AUTHORITY_REVOKED', 'IMPORT_ADMISSION_FACTS_STALE'}:
        return 'DEPENDENCY_CHANGED'
    if code == 'QUOTA_EXHAUSTED':
        return 'RATE_LIMITED'
    if code.startswith('IMPORT_CLEANUP_'):
        return 'CLEANUP_FAILED'
    try:
        return JobFailure(code=code).code
    except ValueError:
        return 'PROCESS_FAILED'


class TemplateJobs:
    def __init__(self, service, pipeline):
        if pipeline.publisher is not service.publisher:
            raise ValueError('template processing must share the canonical publisher')
        self.service, self.pipeline = service, pipeline
        self.pending_jobs, self.reconciliations = {}, {}

    def operation(self, job):
        workspace = self.pipeline.read(job.submission.identity.project_id)
        operation = operation_in(workspace, job.submission.input.id)
        if digest(operation.capture) != job.submission.input.sha256:
            raise BackgroundFailure('DEPENDENCY_CHANGED')
        return operation

    def preflight(self, job):
        try:
            operation = self.operation(job)
            self.pipeline.authority(operation, self.pipeline.read(job.submission.identity.project_id))
            if operation.state == 'cancelled' and job.submission.template_command.kind != 'resume_import':
                return 'CANCELLED'
            return None
        except (BackgroundFailure, TemplateImportFailure, ProjectStoreFailure) as error:
            return job_code(error.code)

    async def submit(self, project, command):
        service = self.service
        if not service.accepting or service.supervisor.closed or service.supervisor.dispatcher is None:
            raise BackgroundFailure('JOB_DISABLED')
        try:
            operation = await self.pipeline.start(project, command) if command.kind == 'start_new_import' else operation_in(
                self.pipeline.read(project), command.operation_id)
            self.pipeline.authority(operation, self.pipeline.read(project))
        except TemplateImportFailure as error:
            raise BackgroundFailure(job_code(error.code)) from None
        state = service.store.load(project)
        request_id = command.client_request_id if command.kind == 'start_new_import' else command.authorization_id
        identity = JobIdentity(projectId=project, lineage=state.lineage, requestEpoch=state.active_request_epoch, requestId=request_id)
        submission = JobSubmissionV1(schemaVersion=1, identity=identity, payloadSha256=digest(command),
            kind='processing', schedulingClass='background', input={'kind': 'template_import', 'id': operation.id,
                'sha256': digest(operation.capture)}, models=[{'stage': 'extraction', 'model': operation.capture.primary.model,
                'configSha256': operation.capture.primary.configuration_hash}], accountGeneration=state.account_generation,
            tools=[], allowEdits=True, allowWeb=False, scope={'kind': 'resume'},
            guards={'schemaVersion': 1, 'reads': [], 'writes': []}, submittedAt=service.store.clock(),
            protocol='template_import_v1', templateCommand=command)
        return await service.supervisor.submit(submission)

    async def complete(self, project, job_id, *, reconciled=False):
        service = self.service
        job = service.store.read(project, job_id)
        if job.submission.protocol != 'template_import_v1' or job.execution not in TERMINAL_EXECUTION:
            return job
        if job.template_outcome is not None and job.template_outcome.state == 'saved':
            return job
        try:
            operation = self.operation(job)
            if operation.state == 'cancelled' and not job.attempts and not operation.attempts:
                outcome = operation.publication
            elif not job.attempts or any(not attempt.cleanup_verified for attempt in job.attempts) or any(
                    attempt.cleanup.state != 'verified' for attempt in operation.attempts):
                outcome = PublicationOutcome(state='outcome_unknown', intentId=None, workspaceHash=None, errorCode='CLEANUP_FAILED')
            elif operation.state == 'cancelled':
                outcome = operation.publication
            elif operation.state == 'fenced':
                outcome = PublicationOutcome(state='outcome_unknown', intentId=None, workspaceHash=None, errorCode='OUTCOME_UNKNOWN')
            elif reconciled and operation.finalization is not None:
                candidate = operation.finalization
                outcome = self.pipeline.persistence.outcome(project, TemplateFinalizationBinding(operationId=operation.id,
                    authorizationId=candidate.authorization_id, finalizationId=candidate.id))
            elif account_stop(operation) is not None:
                # The account stopped the import (D104): saving would publish blocks no call could fill.
                outcome = PublicationOutcome(state='failed_before_replacement', intentId=None, workspaceHash=None,
                    errorCode=account_stop(operation))
            else:
                await self.pipeline.finish_fallbacks(project, operation.id)
                operation = await self.pipeline.finalize(project, operation.id)
                outcome = operation.publication
        except (BackgroundFailure, TemplateImportFailure, ProjectStoreFailure) as error:
            outcome = PublicationOutcome(state='outcome_unknown' if error.code == 'OUTCOME_UNKNOWN' else 'failed_before_replacement',
                intentId=None, workspaceHash=None, errorCode=error.code)
        if project in self.pipeline.persistence.pending:
            projected = job.model_copy(deep=True)
            projected.template_outcome = outcome
            projected.publication = 'saved' if outcome.state == 'saved' else 'outcome_unknown'
            projected.publication_error = None if outcome.state == 'saved' else JobFailure(code='OUTCOME_UNKNOWN')
            self.pending_jobs[project] = projected
            service.supervisor.fenced = service.supervisor.fenced or 'OUTCOME_UNKNOWN'
            self.defer_reconciliation(project, job.id)
            return projected
        def project_outcome(_state, current):
            current.template_outcome = outcome
            current.publication = {'saved': 'saved', 'cancelled': 'cancelled', 'outcome_unknown': 'outcome_unknown',
                'failed_before_replacement': 'save_failed', 'pending': 'ready'}[outcome.state]
            current.publication_error = JobFailure(code=job_code(outcome.error_code)) if outcome.error_code else None
        job = service.store.update(project, job.id, project_outcome)
        await service.supervisor._emit(job)
        return job

    def defer_reconciliation(self, project, job_id):
        if project in self.reconciliations:
            return
        async def reconcile():
            try:
                pending = self.pipeline.persistence.pending.get(project)
                if pending is not None:
                    try:
                        await self.pipeline.persistence.wait_pending(project)
                    except Exception:
                        pass
                await self.pipeline.persistence.reconcile(project)
                await self.complete(project, job_id, reconciled=True)
                self.pending_jobs.pop(project, None)
                if not self.pending_jobs and self.service.supervisor.fenced == 'OUTCOME_UNKNOWN':
                    self.service.supervisor.fenced = None
                    self.service.supervisor.changed.set()
            except Exception:
                self.service.store.fences.setdefault(project, 'OUTCOME_UNKNOWN')
            finally:
                self.reconciliations.pop(project, None)
        self.reconciliations[project] = asyncio.create_task(reconcile())

    async def recover(self):
        for project, state in self.service.store.snapshots().items():
            for job in state.jobs:
                if job.submission.protocol == 'template_import_v1' and job.execution in TERMINAL_EXECUTION:
                    await self.complete(project, job.id)

    async def cleanup_deleted(self, project):
        try:
            verified = await asyncio.to_thread(self.pipeline.cleanup_deleted, project)
        except (TemplateImportFailure, ProjectStoreFailure):
            verified = False
        if not verified:
            raise BackgroundFailure('CLEANUP_FAILED')
        with self.service.store.guard(project, deleted=True) as directory:
            state = self.service.store._read(project, directory)
            for job in state.jobs:
                if job.submission.protocol != 'template_import_v1':
                    continue
                job.execution, job.error = 'interrupted', JobFailure(code='PROJECT_DELETED')
                for attempt in job.attempts:
                    attempt.state, attempt.cleanup_verified = 'interrupted', True
            self.service.store._write(directory, state, self.service.store._all())

    def generation(self, job):
        outcome = job.template_outcome
        saved = outcome is not None and outcome.state == 'saved'
        error = job.publication_error or job.error
        return RichGenerationState(id=job.id, status='completed' if saved else 'cancelled'
            if job.publication in {'cancelled', 'discarded'} else 'failed'
            if job.publication in {'save_failed', 'outcome_unknown'} else job.execution
            if job.execution in {'queued', 'failed', 'cancelled', 'interrupted'} else 'running',
            stage='render' if saved else 'assemble' if job.execution in TERMINAL_EXECUTION else 'normalize_semantics',
            errorCode=error.code if error else None, startedAt=job.created_at)

    async def cancel(self, project, identifier):
        job = self.service.store.read(project, identifier)
        won = await self.pipeline.cancel(project, job.submission.input.id)
        if won:
            await self.service.supervisor.cancel(project, identifier)
        else:
            await self.complete(project, identifier)
        return self.service.store.read(project, identifier)


class TemplateJobRuntime:
    def __init__(self, service, job):
        self.service, self.job = service, job
        self.driver, self.control = None, None

    async def run(self, control):
        self.control = control
        async def process():
            from ..importer.template_transport import JOB_PERMIT
            token = JOB_PERMIT.set(control.permit)
            try:
                await self.service.templates.pipeline.run(control.project_id, self.job.submission.template_command,
                    admitted=control.execution_ready, finalize=False, cancel_event=control.cancel)
                return ExecutionOutcome('completed', None, self.service.supervisor.clock.now())
            except (TemplateImportFailure, BackgroundFailure, ProjectStoreFailure) as error:
                return ExecutionOutcome('cancelled' if error.code == 'CANCELLED' else 'failed', job_code(error.code))
            finally:
                JOB_PERMIT.reset(token)
        self.driver = asyncio.create_task(process())
        return await asyncio.shield(self.driver)

    async def close(self):
        if self.driver is not None and not self.driver.done():
            self.control.cancel.set()
        if self.driver is not None:
            await asyncio.shield(self.driver)
        try:
            self.service.templates.operation(self.job)
        except ProjectStoreFailure as error:
            if error.code != 'PROJECT_DELETED':
                raise
            if not await asyncio.to_thread(self.service.templates.pipeline.cleanup_deleted,
                    self.job.submission.identity.project_id, self.job.submission.input.id):
                raise BackgroundFailure('CLEANUP_FAILED')

    def verified_dead(self):
        if self.driver is None or not self.driver.done():
            return False
        try:
            operation = self.service.templates.operation(self.job)
            return all(attempt.cleanup.state == 'verified' for attempt in operation.attempts)
        except ProjectStoreFailure as error:
            if error.code != 'PROJECT_DELETED':
                raise
            with self.service.store.guard(self.job.submission.identity.project_id, deleted=True) as directory:
                state = self.service.store._read(self.job.submission.identity.project_id, directory)
                latest = [value for value in state.template_authorizations if value.operation_id == self.job.submission.input.id]
                return bool(latest and latest[-1].deleted_cleanup is not None
                    and latest[-1].deleted_cleanup.complete
                    and latest[-1].deleted_cleanup.capture_hash == self.job.submission.input.sha256)
