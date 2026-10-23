"""Server-captured agent submission and event-driven capacity-one dispatch."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from packages.resume_core.agent_artifacts import JobArtifacts
from packages.resume_core.agent_edits import Scope
from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.agent_store import AgentFailure, digest
from packages.resume_core.background_proposals import JobProposals
from packages.resume_core.background_history import ScopeHistory
from packages.resume_core.background_publication import CanonicalCoordinator
from packages.resume_core.background_writers import WriterSessions
from packages.resume_core.background_scopes import mutation_selectors
from packages.resume_core.background_store import BackgroundFailure, JobStore, RESOLVED_PUBLICATION, TERMINAL_EXECUTION, job_in
from packages.resume_core.background_supervisor import JobSupervisor
from packages.resume_core.models.background import JobIdentity, JobProjectV1, JobSubmissionV1, ScopeGuardV1, JobSummaryV1, JobIndexV1
from packages.resume_core.models.agent import wire_bytes

from ..agent.service import CONFIG_SHA256
from ..agent.context import query_fingerprint
from ..agent.tools import TOOL_NAMES
from ..agent.web import PublicFetcher
from ..inference_admission import AdmissionBlocked, AdmissionCancelled, INFERENCE
from .runtime import JobRuntime
from .tools import JobTools, PROTOCOL_V2_SHA256
from .publication import JobPublication


async def deny_native(_control):
    raise BackgroundFailure("JOB_DISABLED")


class JobService:
    def __init__(self, projects, runtime, connection, *, enabled=False, factory=None, clock=None,
                 admission=INFERENCE, authorize_native=deny_native, observer=None, fetcher=None,
                 parallel=False, server_factory=None, shared_native=False, template_factory=None, template_cleanup_verified=None):
        if parallel and (not enabled or factory is None and server_factory is None):
            raise ValueError("Parallel jobs require an enabled isolated transport")
        self.projects, self.runtime, self.connection = projects, runtime, connection
        self.enabled, self.admission, self.authorize_native = enabled, admission, authorize_native
        self.accepting = enabled
        self.runtime_available = runtime is not None or factory is not None or parallel
        self.content_provider = lambda: self.projects.provider_factory()
        from packages.resume_core.background_limits import LIMITS
        self.content_pool = ThreadPoolExecutor(max_workers=LIMITS.executions if parallel else LIMITS.serial_executions,
            thread_name_prefix="foldcv-inference")
        self.store = JobStore(projects.storage.root)
        self.artifacts = JobArtifacts(self.store)
        self.history = ScopeHistory(self.store, query_fingerprint)
        self.publisher = CanonicalCoordinator(self.store, self.history, projects.storage, self.load_payload)
        configure_exports = getattr(projects, 'configure_template_exports', None)
        if configure_exports is not None:
            configure_exports(self, cleanup_verified=template_cleanup_verified or (lambda: False))
        self.publication = JobPublication(self)
        self.writers = WriterSessions(self.publisher, blocked=lambda project: project in self.projects.agent_recovery_fences | self.projects.catalog_recovery_fences)
        self.artifacts.prepare_capture = self.capture_preparation
        self.settings = AgentSettingsStore(projects.storage.root)
        self.proposals = {}
        self.publication_tasks, self.publication_wakes = {}, set()
        from .fixed import FixedJobs
        from .fixed_runtime import FixedRuntime
        self.fixed = FixedJobs(self)
        self.publisher.processing_validator = self.fixed.validate_processing
        from .templates import TemplateJobs, TemplateJobRuntime
        self.templates = TemplateJobs(self, template_factory(self)) if template_factory is not None else None
        agent_factory = factory or (lambda job, model: JobRuntime(self, job, model))
        def runtime_factory(job, model):
            from packages.resume_core.template_import import processing_protocol
            if job.submission.protocol == 'template_import_v1':
                if self.templates is None:
                    raise BackgroundFailure('JOB_DISABLED')
                return TemplateJobRuntime(self, job)
            if job.submission.kind == "agent":
                return agent_factory(job, model)
            if processing_protocol(job.submission) == 'agent_import_v1':
                from ..importer.job import ImportJobRuntime
                return ImportJobRuntime(self, job, model)
            return FixedRuntime(self, job, model)
        async def observed(name, identifier):
            if observer is not None:
                await observer(name, identifier)
            if name == "slot_released":
                if self.templates is not None:
                    for project, state in self.store.snapshots().items():
                        job = next((value for value in state.jobs if value.id == identifier), None)
                        if job is not None and job.submission.protocol == 'template_import_v1':
                            await self.templates.complete(project, identifier)
                await self.projects.drain_catalog_actions(run_id=identifier)
        self.supervisor = JobSupervisor(self.store,
            runtime_factory,
            clock=clock, preflight=self.preflight, admit=self.admit, eligible=self.eligible, parallel=parallel,
            observer=observed)
        self.parallel_owner = None
        if parallel:
            from .parallel import ParallelOwner
            self.parallel_owner = ParallelOwner(self, server_factory, native=shared_native)
            self.supervisor.idle = self.parallel_owner.idle
            self.supervisor.maintenance_ready = self.parallel_owner.login_allowed
        self.tools = JobTools(self, fetcher=fetcher or PublicFetcher(projects.temp_root))

    async def start(self):
        # An activated store keeps its writer authority when model delivery is off.
        self.enabled = self.enabled or self.store.projects.exists()
        if self.enabled:
            self.projects.background_jobs = self
            for project, state in self.store.snapshots().items():
                if any(intent.phase not in {"receipt_stored", "reconciled"} for intent in [*state.intents, *state.manual_intents]):
                    try:
                        self.publisher.recover(project)
                    except BackgroundFailure:
                        self.store.fences.setdefault(project, "OUTCOME_UNKNOWN")
            from packages.resume_core.background_retention import JobRetention
            self.writers.recover_all()
            JobRetention(self.store).sweep_all()
        if hasattr(self.projects, 'recover_template_exports'):
            await self.projects.recover_template_exports()
        if self.enabled:
            self.supervisor.dispatch_enabled = self.accepting
            await self.supervisor.start()
            if self.templates is not None:
                await self.templates.recover()

    def capture_preparation(self, directory, state, record, batch):
        workspace, checksum = self.projects.storage._read_committed_unlocked(state.project_id)
        self.history._ready(state, directory, checksum)
        try:
            reads = self.history.register(state, workspace, batch.dependencies)
            writes = self.history.register(state, workspace, mutation_selectors(workspace, batch.mutation), write=True)
        except BackgroundFailure as error:
            if error.code == "DEPENDENCY_CHANGED":
                raise AgentFailure("AGENT_STALE_READ") from None
            raise
        original = record.observed_guards
        values = {(stamp.kind, stamp.key): stamp for stamp in original.reads} if original else {}
        for stamp in reads.reads:
            values.setdefault((stamp.kind, stamp.key), stamp)
        if len(values) > 4096:
            raise BackgroundFailure("JOB_STORAGE_FULL")
        record.prepared_guards = ScopeGuardV1(schemaVersion=1, reads=list(values.values()), writes=writes.writes)
        self.store._write(directory, state, self.store._all())

    def project(self, project):
        if not self.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        if self.templates is not None and project in self.templates.pending_jobs:
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        state = self.store.open(project)
        return JobProjectV1(schemaVersion=1, projectId=project, lineage=state.lineage,
            requestEpoch=state.active_request_epoch, jobs=state.jobs)

    def index(self):
        if not self.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        if self.templates is not None and self.templates.pending_jobs:
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        titles = {entry["projectId"]: entry["title"] for entry in self.projects.listing()["entries"]}
        rows = []
        for project, state in self.store.snapshots().items():
            title = (titles.get(project) or "Резюме")[:512]
            for job in state.jobs:
                rows.append(JobSummaryV1(schemaVersion=1, projectId=project, lineage=state.lineage,
                    jobId=job.id, projectTitle=title, kind=job.submission.kind,
                    stage=job.attempts[-1].stage if job.attempts else None, execution=job.execution,
                    publication=job.publication, executionGeneration=job.execution_generation,
                    eventCursor=job.event_cursor, allowEdits=job.submission.allow_edits,
                    approvalRequired=job.submission.approval_required,
                    saved=job.receipt is not None or job.template_outcome is not None and job.template_outcome.state == 'saved',
                    error=job.error, publicationError=job.publication_error,
                    updatedAt=job.updated_at))
        return JobIndexV1(schemaVersion=1, jobs=rows)

    async def discard(self, project, identifier):
        self.project(project)
        job = self.store.read(project, identifier)
        if job.submission.protocol == 'template_import_v1':
            if self.templates is None:
                raise BackgroundFailure('JOB_DISABLED')
            return await self.templates.cancel(project, identifier)
        if job.publication == "outcome_unknown":
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        await self.supervisor.cancel(project, identifier)
        job = self.store.discard(project, identifier)
        await self.supervisor._emit(job)
        self.supervisor.changed.set()
        return job

    async def cancel(self, project, identifier):
        job = self.store.read(project, identifier)
        if job.submission.protocol == 'template_import_v1':
            if self.templates is None:
                raise BackgroundFailure('JOB_DISABLED')
            return await self.templates.cancel(project, identifier)
        return await self.supervisor.cancel(project, identifier)

    def proposals_for(self, project):
        if project not in self.proposals:
            self.proposals = {key: value for key, value in self.proposals.items()
                if any(not task.done() for _, task in value.tasks.values())}
            self.proposals[project] = JobProposals(self.supervisor,
                lambda reference: self.artifacts.payload_for(project, reference) if reference.kind == "agent_journal"
                    else self.fixed.payload(project, reference))
        return self.proposals[project]

    def load_payload(self, state, directory, reference):
        if reference.kind == "processing":
            return self.fixed.inputs.payload(state, directory, reference)
        return self.artifacts.payload_unlocked(state, directory, reference)

    def preflight(self, job):
        if job.submission.protocol == 'template_import_v1':
            return self.templates.preflight(job) if self.templates is not None else 'JOB_DISABLED'
        connection = self.connection()
        if not connection.ready:
            return "RATE_LIMITED" if connection.reason == "AGENT_QUOTA" else "AUTH_REQUIRED"
        try:
            self.writers.initialize(job.submission.identity.project_id)
        except BackgroundFailure as error:
            return error.code
        if job.submission.kind != "agent":
            return self.fixed.preflight(job)
        if not self.settings.load().enabled:
            return "JOB_DISABLED"
        _job, artifact = self.artifacts.record(job.submission.identity.project_id, job.id)
        if connection.epoch != artifact.connection_epoch:
            return "ACCOUNT_CHANGED"
        if digest(self.projects.storage.read_committed(job.submission.identity.project_id)[0].rules_used) != artifact.rules_sha256:
            return "DEPENDENCY_CHANGED"
        if any(model.model not in connection.models for model in job.submission.models):
            return "MODEL_DENIED"
        return None

    def eligible(self, job):
        return job.submission.identity.project_id not in self.store.fences and job.submission.identity.project_id not in self.projects.catalog_recovery_fences

    async def admit(self, control):
        try:
            return await (self.parallel_owner.reserve(control) if self.parallel_owner is not None
                else self.admission.reserve(control.cancelled))
        except AdmissionCancelled:
            raise BackgroundFailure("CANCELLED") from None
        except AdmissionBlocked:
            raise BackgroundFailure("CLEANUP_FAILED") from None

    async def submit(self, project, payload):
        if not self.enabled or not self.accepting or self.supervisor.closed or self.supervisor.dispatcher is None:
            raise BackgroundFailure("JOB_DISABLED")
        logical = payload.request
        if getattr(getattr(self.projects, "agent", None), "assistant_protocol_enabled", False):
            from ..agent.capabilities import known_intent
            if known_intent(logical.message) is not None:
                raise AgentFailure("AGENT_TOOL_DENIED")
        identity = JobIdentity(projectId=project, lineage=payload.lineage, requestEpoch=payload.request_epoch,
            requestId=logical.client_request_id)
        logical_hash = digest({"identity": identity.model_dump(by_alias=True), "request": logical.model_dump(by_alias=True)})
        with self.projects.state_lock:
            state = self.store.load(project)
            existing = next((item for item in state.requests if item.identity == identity), None)
            if existing is not None:
                if existing.payload_sha256 != logical_hash:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                job = job_in(state, existing.job_id)
                self.artifacts.bind(job)
                return job, False
            self.projects.ensure_loaded()
            settings, connection = self.settings.load(), self.connection()
            if not settings.enabled or not self.runtime_available:
                raise BackgroundFailure("JOB_DISABLED")
            if logical.settings_revision != settings.revision:
                raise AgentFailure("AGENT_SETTINGS_CONFLICT")
            if not connection.ready:
                raise BackgroundFailure("RATE_LIMITED" if connection.reason == "AGENT_QUOTA" else "AUTH_REQUIRED")
            if settings.selected_agent_model is None or settings.selected_agent_model not in connection.models:
                raise BackgroundFailure("MODEL_DENIED")
            workspace, _checksum = self.projects.storage.read_committed(project, synchronize=True)
            if (workspace.project is None or (workspace.project_revision, workspace.document_revision,
                    workspace.project.facts.revision) != (logical.project_revision, logical.document_revision, logical.facts_revision)):
                raise AgentFailure("AGENT_STALE_READ")
            if self.projects.durability(project) != "durable":
                raise AgentFailure("AGENT_SAVE_FAILED")
            Scope(workspace, logical.scope)
            access = self.projects.catalog.get(project)
            if logical.allow_edits and access.read_only:
                raise AgentFailure("AGENT_TOOL_DENIED")
            record = self.artifacts.prepare_input(identity, logical, connection.epoch, digest(workspace.rules_used))
            cap_mode = getattr(getattr(self.projects, "agent", None), "assistant_protocol_enabled", False)
            names = [name for name in TOOL_NAMES if (not cap_mode or name != "apply_edit_batch")
                and (logical.allow_edits or name not in {"prepare_edit_batch", "apply_edit_batch", "project_action"} or cap_mode and name == "prepare_edit_batch")
                and (logical.allow_web or name != "read_public_page")]
            protocol = self.projects.agent.protocol_sha256 if cap_mode else PROTOCOL_V2_SHA256
            config = digest({"base": CONFIG_SHA256, "protocol": protocol,
                "tools": names, "allowEdits": logical.allow_edits, "allowWeb": logical.allow_web})
            captured = JobSubmissionV1(schemaVersion=1, identity=identity, payloadSha256=logical_hash,
                kind="agent", schedulingClass="background", input={"kind": "agent_journal", "id": record.id,
                    "sha256": record.request_sha256}, models=[{"stage": "agent", "model": settings.selected_agent_model,
                    "configSha256": config}], accountGeneration=state.account_generation, tools=names,
                allowEdits=logical.allow_edits, accessRevision=access.access_revision, allowWeb=logical.allow_web, scope=logical.scope,
                guards={"schemaVersion": 1, "reads": [], "writes": []}, submittedAt=self.store.clock())
            job, created = self.store.submit(captured)
            self.artifacts.bind(job)
        try:
            if created:
                await self.supervisor.observer("accepted_durable", job.id)
            await self.supervisor._emit(job)
        finally:
            self.supervisor.changed.set()
        return job, created

    async def stream(self, project, job_id, request):
        changed = asyncio.Event()
        self.supervisor.listeners.add(changed)
        after, generation, sent = request.after, request.generation, 0
        try:
            while not self.supervisor.closed:
                changed.clear()
                events = self.supervisor.events.replay(project, job_id, after=after, generation=generation)
                for event in events:
                    raw = wire_bytes(event) + b"\n"
                    if sent + len(raw) > 256 * 1024:
                        return
                    sent += len(raw)
                    after, generation = event.cursor, event.generation
                    yield raw
                job = self.store.read(project, job_id)
                if job.execution in TERMINAL_EXECUTION and job.publication in RESOLVED_PUBLICATION and after >= job.event_cursor and generation == job.execution_generation:
                    return
                if after < job.event_cursor or generation != job.execution_generation:
                    continue
                await changed.wait()
        finally:
            self.supervisor.listeners.discard(changed)

    async def shutdown(self):
        await self.supervisor.shutdown()
        for proposal in self.proposals.values():
            await proposal.shutdown()
        if self.publication_tasks:
            await asyncio.gather(*tuple(self.publication_tasks.values()), return_exceptions=True)
        await self.fixed.shutdown()
        self.content_pool.shutdown(wait=True, cancel_futures=True)
        for changed in tuple(self.supervisor.listeners):
            changed.set()

    async def disable(self):
        self.accepting = False
        self.supervisor.dispatch_enabled = False
        await self.shutdown()
        for project in self.store.snapshots():
            try:
                await asyncio.to_thread(self.publisher.recover, project)
            except BackgroundFailure as error:
                self.store.fences.setdefault(project, error.code)
            self.store.recover(project)

    def wake_publication(self, project):
        if not self.enabled or not self.accepting or self.supervisor.closed:
            return
        self.publication_wakes.add(project)
        if project in self.publication_tasks and not self.publication_tasks[project].done():
            return
        async def reconcile():
            try:
                while project in self.publication_wakes:
                    self.publication_wakes.discard(project)
                    updated = await asyncio.to_thread(self.publish_waiting, project)
                    for job in updated:
                        await self.supervisor._emit(job)
                        self.fixed.render(job)
            except Exception as error:
                self.store.fences.setdefault(project, getattr(error, "code", "OUTCOME_UNKNOWN"))
            finally:
                self.publication_tasks.pop(project, None)
        task = asyncio.create_task(reconcile())
        self.publication_tasks[project] = task

    def publish_waiting(self, project):
        updated = []
        try:
            state = self.store.load(project)
            for job in state.jobs:
                if job.submission.kind == "agent" and not self.settings.load().enabled:
                    continue
                if job.submission.approval_required or job.publication not in {"ready", "waiting_for_sync", "save_failed"} or job.proposal_id is None:
                    continue
                proposal = next(item for item in state.proposals if item.id == job.proposal_id)
                result = self.publication.publish(project, job.id, proposal.payload_sha256)
                if result.event_cursor != job.event_cursor:
                    updated.append(result)
        except BackgroundFailure as error:
            if error.code not in {"PROJECT_DELETED", "JOB_NOT_FOUND"}:
                self.store.fences.setdefault(project, error.code)
        return updated

    async def stop_agents(self):
        controls = [control for control in self.supervisor.controls.values() if control.job.submission.kind == "agent"]
        for control in controls:
            control.stop("CANCELLED", revoke_publication=True)
        for project, state in self.store.snapshots().items():
            for job in state.jobs:
                if job.submission.kind == "agent" and (job.execution not in TERMINAL_EXECUTION or job.publication not in RESOLVED_PUBLICATION):
                    await self.supervisor.cancel(project, job.id)
        tasks = [control.task for control in controls if control.task is not None and control.task is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_project(self, project):
        controls = [control for control in self.supervisor.controls.values()
            if control.project_id == project and control.task is not None and control.task is not asyncio.current_task() and not control.task.done()]
        for control in controls:
            control.stop("PROJECT_DELETED", revoke_publication=True)
        if (self.store.projects / project).exists():
            self.store.mark_deleted(project)
        if controls:
            await asyncio.gather(*(control.task for control in controls), return_exceptions=True)
        if self.templates is not None and (self.store.projects / project).exists():
            await self.templates.cleanup_deleted(project)
        if project in self.proposals:
            await self.proposals[project].shutdown()
        if (self.store.projects / project).exists():
            with self.store.guard(project, deleted=True) as directory:
                state = self.store._read(project, directory)
                if any(job.execution not in TERMINAL_EXECUTION or any(not attempt.cleanup_verified for attempt in job.attempts)
                        for job in state.jobs):
                    raise BackgroundFailure("CLEANUP_FAILED")
        self.supervisor.changed.set()
