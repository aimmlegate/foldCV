"""Server-captured agent submission and event-driven capacity-one dispatch."""

import asyncio

from packages.resume_core.agent_artifacts import JobArtifacts
from packages.resume_core.agent_edits import Scope
from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.agent_store import AgentFailure, digest
from packages.resume_core.background_proposals import JobProposals
from packages.resume_core.background_history import ScopeHistory
from packages.resume_core.background_publication import CanonicalCoordinator
from packages.resume_core.background_scopes import mutation_selectors
from packages.resume_core.background_store import BackgroundFailure, JobStore, TERMINAL_EXECUTION, job_in
from packages.resume_core.background_supervisor import JobSupervisor
from packages.resume_core.models.background import JobIdentity, JobProjectV1, JobSubmissionV1, ScopeGuardV1
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
                 admission=INFERENCE, authorize_native=deny_native, observer=None, fetcher=None):
        self.projects, self.runtime, self.connection = projects, runtime, connection
        self.enabled, self.admission, self.authorize_native = enabled, admission, authorize_native
        self.runtime_available = runtime is not None or factory is not None
        self.store = JobStore(projects.storage.root)
        self.artifacts = JobArtifacts(self.store)
        self.history = ScopeHistory(self.store, query_fingerprint)
        self.publisher = CanonicalCoordinator(self.store, self.history, projects.storage, self.artifacts.payload_unlocked)
        self.publication = JobPublication(self)
        self.artifacts.prepare_capture = self.capture_preparation
        self.settings = AgentSettingsStore(projects.storage.root)
        self.proposals = {}
        self.supervisor = JobSupervisor(self.store, factory or (lambda job, model: JobRuntime(self, job, model)),
            clock=clock, preflight=self.preflight, admit=self.admit, eligible=self.eligible,
            **({"observer": observer} if observer else {}))
        self.tools = JobTools(self, fetcher=fetcher or PublicFetcher(projects.temp_root))

    async def start(self):
        if self.enabled:
            self.projects.background_jobs = self
            for project, state in self.store.snapshots().items():
                if any(intent.phase not in {"receipt_stored", "reconciled"} for intent in [*state.intents, *state.manual_intents]):
                    try:
                        self.publisher.recover(project)
                    except BackgroundFailure:
                        self.store.fences.setdefault(project, "OUTCOME_UNKNOWN")
            await self.supervisor.start()

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
        if len(values) > 100:
            raise BackgroundFailure("JOB_STORAGE_FULL")
        record.prepared_guards = ScopeGuardV1(schemaVersion=1, reads=list(values.values()), writes=writes.writes)
        self.store._write(directory, state, self.store._all())

    def project(self, project):
        if not self.enabled:
            raise BackgroundFailure("JOB_DISABLED")
        state = self.store.open(project)
        return JobProjectV1(schemaVersion=1, projectId=project, lineage=state.lineage,
            requestEpoch=state.active_request_epoch, jobs=state.jobs)

    def proposals_for(self, project):
        if project not in self.proposals:
            self.proposals[project] = JobProposals(self.supervisor,
                lambda reference: self.artifacts.payload_for(project, reference))
        return self.proposals[project]

    def preflight(self, job):
        connection = self.connection()
        if not connection.ready:
            return "RATE_LIMITED" if connection.reason == "AGENT_QUOTA" else "AUTH_REQUIRED"
        _job, artifact = self.artifacts.record(job.submission.identity.project_id, job.id)
        if connection.epoch != artifact.connection_epoch:
            return "ACCOUNT_CHANGED"
        if digest(self.projects.storage.read_committed(job.submission.identity.project_id)[0].rules_used) != artifact.rules_sha256:
            return "DEPENDENCY_CHANGED"
        if any(model.model not in connection.models for model in job.submission.models):
            return "MODEL_DENIED"
        return None

    def eligible(self, job):
        return job.submission.identity.project_id not in self.store.fences

    async def admit(self, control):
        try:
            return await self.admission.reserve(control.cancelled)
        except AdmissionCancelled:
            raise BackgroundFailure("CANCELLED") from None
        except AdmissionBlocked:
            raise BackgroundFailure("CLEANUP_FAILED") from None

    async def submit(self, project, payload):
        if not self.enabled or self.supervisor.closed or self.supervisor.dispatcher is None:
            raise BackgroundFailure("JOB_DISABLED")
        logical = payload.request
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
            record = self.artifacts.prepare_input(identity, logical, connection.epoch, digest(workspace.rules_used))
            names = [name for name in TOOL_NAMES if (logical.allow_edits or name not in {"prepare_edit_batch", "apply_edit_batch"})
                and (logical.allow_web or name != "read_public_page")]
            config = digest({"base": CONFIG_SHA256, "protocol": PROTOCOL_V2_SHA256,
                "tools": names, "allowEdits": logical.allow_edits, "allowWeb": logical.allow_web})
            captured = JobSubmissionV1(schemaVersion=1, identity=identity, payloadSha256=logical_hash,
                kind="agent", schedulingClass="background", input={"kind": "agent_journal", "id": record.id,
                    "sha256": record.request_sha256}, models=[{"stage": "agent", "model": settings.selected_agent_model,
                    "configSha256": config}], accountGeneration=state.account_generation, tools=names,
                allowEdits=logical.allow_edits, allowWeb=logical.allow_web, scope=logical.scope,
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
                if job.execution in TERMINAL_EXECUTION:
                    return
                await changed.wait()
        finally:
            self.supervisor.listeners.discard(changed)

    async def shutdown(self):
        await self.supervisor.shutdown()
        for proposal in self.proposals.values():
            await proposal.shutdown()
        for changed in tuple(self.supervisor.listeners):
            changed.set()

    async def stop_project(self, project):
        controls = [control for control in self.supervisor.controls.values()
            if control.project_id == project and control.task is not None and not control.task.done()]
        for control in controls:
            control.stop("PROJECT_DELETED", revoke_publication=True)
        if (self.store.projects / project).exists():
            self.store.mark_deleted(project)
        if controls:
            await asyncio.gather(*(control.task for control in controls), return_exceptions=True)
        self.supervisor.changed.set()
