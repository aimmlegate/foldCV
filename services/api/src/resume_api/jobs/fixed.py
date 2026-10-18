"""Capture fixed operations before queue admission and publish their exact result."""

import asyncio
import hashlib
from datetime import datetime

from packages.resume_core.agent_store import digest as value_digest
from packages.resume_core.background_fixed import fixed_mutation, fixed_payload
from packages.resume_core.background_fixed_inputs import FixedInputs
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_scopes import mutation_selectors
from packages.resume_core.background_store import BackgroundFailure, TERMINAL_EXECUTION, claimed, expiration, job_in
from packages.resume_core.gui_normalization import GuiNormalizeRequest
from packages.resume_core.import_diagnostics import source_warnings
from packages.resume_core.models.agent import AgentEntityDependency
from packages.resume_core.models.background import (FixedInputV1, JobFixedReplyV1, JobIdentity, JobSubmissionV1,
    ProcessingCandidateV1, ProposalBindingV1, ScopeGuardV1, JobFailure, FixedInvalidationV1)
from packages.resume_core.models.rich_workspace import RichWarning
from packages.resume_core.project_store import encoded
from packages.resume_core.rich_import import assemble_import
from packages.resume_core.gui_annotations import unresolved_source_units
from ..gui_normalization_content import GuiNormalizationContentService
from ..gui_projects import ProjectFailure
from ..resume_assessment_content import ResumeAssessmentContentService
from .fixed_projection import FixedProjection
from packages.resume_core.models.importing import IMPORT_TOOLS

PROTOCOL = "fixed-jobs-v1:existing-services:one-attempt:assessment-extraction-original"


def digest(value):
    def wire(item):
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json", by_alias=True)
        if isinstance(item, dict):
            return {key: wire(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [wire(value) for value in item]
        return item
    return value_digest(wire(value))


def processing_source(workspace, rules):
    return digest({"empty": workspace.project is None, "formatting": workspace.formatting_as_of,
        "sources": [s.model_dump(mode="json", by_alias=True) for s in workspace.pre_draft.sources
            if s.id == workspace.pre_draft.selected_source_id] if workspace.pre_draft else [], "rules": rules})


def action_capture(command):
    if command.kind == "processing":
        return None
    if command.kind == "rewrite":
        return command.request.selection.capture
    return command.request.capture if command.kind in {"completion", "panel"} else command.capture


def action_key(capture):
    return capture.session_id, capture.action_id, capture.action_token


class FixedJobs:
    def __init__(self, service):
        self.service, self.inputs = service, FixedInputs(service.store)
        self.renders, self.render_errors = {}, {}

    def render(self, job):
        if job.submission.kind != "processing" or job.receipt is None or job.id in self.renders:
            return
        completed = [key for key, task in self.renders.items() if task.done()]
        for key in completed[:-8]:
            del self.renders[key]
            self.render_errors.pop(key, None)
        async def run():
            from packages.resume_core.rendering.template import RenderFailure
            project = job.submission.identity.project_id
            try:
                await self.service.projects.export(project)
            except (RenderFailure, ProjectFailure, BackgroundFailure) as error:
                self.render_errors[job.id] = error.code
                if error.code == "RICH_EXPORT_UNSUPPORTED":
                    with self.service.projects.state_lock:
                        workspace = self.service.projects.read(project)
                        if not any(w.code == error.code for w in workspace.warnings):
                            workspace.warnings.append(RichWarning(id="warning_" + digest([job.id, error.code])[:24],
                                code=error.code, blockIds=[], recordIds=[], evidence=[]))
                            self.service.projects.workspaces[project] = workspace
                            self.service.projects.persist(project)
        self.renders[job.id] = asyncio.create_task(run())

    async def shutdown(self):
        if self.renders:
            await asyncio.gather(*self.renders.values(), return_exceptions=True)

    def input(self, job):
        with self.service.store.guard(job.submission.identity.project_id) as directory:
            return self.inputs.read(directory, job)

    def reply(self, job):
        value = self.input(job)
        return JobFixedReplyV1(schemaVersion=1, projectId=value.identity.project_id, job=job,
            syncId=value.sync_id, actionId=value.action_id)

    def generation(self, project):
        from packages.resume_core.rich_api import RichGenerationState
        state = self.service.store.load(project) if (self.service.store.projects / project).exists() else None
        jobs = [j for j in state.jobs if j.submission.kind == "processing"] if state else []
        if not jobs:
            return None
        job = jobs[-1]
        stage = "normalize_semantics" if "save_import" in job.submission.tools else (
            "assess_resume" if not job.attempts or job.attempts[-1].stage == "assessment" else "normalize_semantics")
        error = job.error or job.publication_error
        status = ("completed" if job.receipt is not None else "failed" if job.publication == "needs_review"
            else job.execution if job.execution in {"queued", "failed", "cancelled", "interrupted"} else "running")
        return RichGenerationState(id=job.id, status=status, stage="render" if job.receipt else stage,
            errorCode=error.code if error else None, startedAt=job.created_at)

    async def submit(self, project, request):
        service, projects = self.service, self.service.projects
        if not service.enabled or not service.accepting or service.supervisor.closed or service.supervisor.dispatcher is None:
            raise BackgroundFailure("JOB_DISABLED")
        identity = JobIdentity(projectId=project, lineage=request.lineage, requestEpoch=request.request_epoch,
            requestId=request.client_request_id)
        logical = digest({"identity": identity, "request": request})
        superseded, supersede_ids = [], []
        with projects.state_lock:
            state = service.store.open(project)
            known = next((r for r in state.requests if r.identity == identity), None)
            if known is not None:
                if known.payload_sha256 != logical:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                return self.reply(job_in(state, known.job_id)), False
            if request.lineage != state.lineage:
                raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
            if (request.request_epoch != state.active_request_epoch or request.request_epoch <= state.expired_through_epoch
                    or datetime.fromisoformat(service.store.clock().replace("Z", "+00:00")) >=
                        datetime.fromisoformat(state.request_epoch_expires_at.replace("Z", "+00:00"))):
                raise BackgroundFailure("REQUEST_EXPIRED")
            processing = request.command.kind == "processing"
            selected = projects.import_provider_factory() if processing else projects.provider_factory()
            connection = service.connection()
            if selected is None or not connection.ready:
                raise BackgroundFailure("RATE_LIMITED" if connection.reason == "AGENT_QUOTA" else "AUTH_REQUIRED")
            if selected[1] not in connection.models:
                raise BackgroundFailure("MODEL_DENIED")
            workspace, _checksum = projects.storage.read_committed(project, synchronize=True)
            command = request.command
            origin = action_capture(command)
            if origin is not None and any(action_key(item) == action_key(origin) for item in state.fixed_invalidations):
                raise ProjectFailure("STALE_SELECTION", 409)
            rules = projects.rules.load() if processing else workspace.rules_used
            if processing and rules is None:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            original = None
            if processing:
                if workspace.project is not None:
                    raise ProjectFailure("DOCUMENT_ALREADY_CREATED", 409)
                if not workspace.pre_draft or not any(s.id == workspace.pre_draft.selected_source_id
                        and any(u.text.strip() for u in s.units) for s in workspace.pre_draft.sources):
                    raise ProjectFailure("NO_USABLE_TEXT", 422)
                if any(j.submission.kind == "processing" and j.execution not in TERMINAL_EXECUTION for j in state.jobs):
                    raise ProjectFailure("PROJECT_GENERATION_ACTIVE", 409)
            elif workspace.project is None:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            if command.kind in {"retry", "resolve"}:
                original = next((s.model_copy(deep=True) for s in workspace.sync_records if s.id == command.sync_id), None)
                if original is None:
                    raise ProjectFailure("SYNC_NOT_FOUND", 404)
                original.proposed_steps, original.ready = [], False
            identifier = "fixed_" + digest(identity)[:32]
            captured = workspace.model_copy(deep=True)
            captured.sync_records = []
            projection = None if processing else FixedProjection(project, captured, identifier, original=original)
            record = None if projection is None else await projection.capture(command)
            service.writers.initialize(project)
            with service.store.guard(project) as directory:
                state = service.store._read(project, directory)
                current, checksum = projects.storage._read_committed_unlocked(project)
                service.history._ready(state, directory, checksum)
                selectors = [AgentEntityDependency(kind="entity", stamp=s) for s in record.dependencies] if record else []
                guards = service.history.register(state, current, selectors)
                value = FixedInputV1(schemaVersion=1, id=identifier, identity=identity, request=request,
                    workspace=captured, rules=rules, connectionEpoch=connection.epoch, model=selected[1],
                    sourceSha256=processing_source(captured, rules) if processing else digest(captured.project),
                    syncId=identifier if record else None, actionId=record.action_id if record else None,
                    originalSync=original)
                checksum = self.inputs.prepare(directory, state, value)
                service.store._write(directory, state, service.store._all())
            kind = "processing" if processing else "rewrite" if record.kind == "rewrite" else "reconciliation"
            models = ["extraction"] if processing else ["rewrite" if kind == "rewrite" else "reconciliation"]
            from ..importer.session import SKILL_SHA256
            submission = JobSubmissionV1(schemaVersion=1, identity=identity, payloadSha256=logical,
                kind=kind, schedulingClass="background" if processing else "interactive" if kind == "rewrite" else "reconciliation",
                input={"kind": "processing" if processing else "rich_sync", "id": identifier, "sha256": checksum},
                models=[{"stage": stage, "model": selected[1], "configSha256": digest([SKILL_SHA256 if processing else PROTOCOL, stage, rules])} for stage in models],
                accountGeneration=state.account_generation, tools=list(IMPORT_TOOLS) if processing else [], allowEdits=True, allowWeb=False,
                scope={"kind": "selection", "selection": record.selection} if record and record.selection else {"kind": "resume"},
                guards=guards, submittedAt=service.store.clock())
            # Retire only queued automatic work; explicit requests and active attempts keep their visible outcome.
            if command.kind in {"completion", "panel"}:
                for previous in state.jobs:
                    if previous.execution != "queued" or previous.submission.kind != "reconciliation":
                        continue
                    old = self.input(previous)
                    if old.request.command.kind not in {"completion", "panel"}:
                        continue
                    old_projection = FixedProjection(project, old.workspace, old.sync_id)
                    old_record = await old_projection.capture(old.request.command)
                    if set(old_record.block_ids) & set(record.block_ids) or set(old_record.fact_ids) & set(record.fact_ids):
                        supersede_ids.append(previous.id)
            try:
                job, created = service.store.submit(submission, supersede_ids=supersede_ids)
            except BackgroundFailure as error:
                if error.code in {"JOB_QUEUE_FULL", "JOB_STORAGE_FULL"}:
                    with service.store.guard(project) as directory:
                        current = service.store._read(project, directory)
                        if not any(r.identity == identity for r in current.requests):
                            path = self.inputs.path(directory, "fixed-inputs", identifier)
                            path.unlink(missing_ok=True)
                            service.store._sync_namespace(path)
                raise
            superseded.extend(service.store.read(project, previous) for previous in supersede_ids)
            if command.kind in {"retry", "resolve"}:
                for previous in state.jobs:
                    if previous.submission.input.kind == "rich_sync" and previous.submission.input.id == command.sync_id:
                        superseded.append(service.store.discard(project, previous.id, superseded=True))
        try:
            for previous in superseded:
                await service.supervisor._emit(previous)
            if created:
                await service.supervisor.observer("accepted_durable", job.id)
            await service.supervisor._emit(job)
        finally:
            service.supervisor.changed.set()
        return self.reply(job), created

    def preflight(self, job):
        service = self.service
        try:
            if job.capture_invalidated:
                return "DEPENDENCY_CHANGED"
            captured = self.input(job)
            if any(model.model not in service.connection().models for model in job.submission.models):
                return "MODEL_DENIED"
            if service.connection().epoch != captured.connection_epoch:
                return "ACCOUNT_CHANGED"
            current, _checksum = service.projects.storage.read_committed(captured.identity.project_id)
            if job.submission.kind == "processing":
                from ..importer.session import SKILL_SHA256
                if "save_import" in job.submission.tools and any(
                        model.config_sha256 != digest([SKILL_SHA256, model.stage, captured.rules])
                        for model in job.submission.models):
                    return "DEPENDENCY_CHANGED"
                if processing_source(current, service.projects.rules.load()) != captured.source_sha256:
                    return "DEPENDENCY_CHANGED"
            else:
                if digest(current.rules_used) != digest(captured.rules):
                    return "DEPENDENCY_CHANGED"
                with service.store.guard(captured.identity.project_id) as directory:
                    state = service.store._read(captured.identity.project_id, directory)
                    service.history.validate(state, directory, current, job.submission.guards)
            return None
        except (BackgroundFailure, ProjectFailure) as error:
            return error.code

    async def invalidate_action(self, project, capture):
        service = self.service
        service.writers.initialize(project)
        with service.store.guard(project) as directory:
            state = service.store._read(project, directory)
            if not any(action_key(item) == action_key(capture) for item in state.fixed_invalidations):
                state.fixed_invalidations.append(FixedInvalidationV1(requestEpoch=state.active_request_epoch,
                    sessionId=capture.session_id, actionId=capture.action_id, actionToken=capture.action_token))
                service.store._write(directory, state, service.store._all())
        for job in service.store.load(project).jobs:
            if job.submission.kind == "agent" or job.receipt is not None:
                continue
            captured = self.input(job)
            command = captured.request.command
            origin = action_capture(command)
            if origin is None or action_key(origin) != action_key(capture):
                continue
            def invalidate(_state, current):
                if current.receipt is not None or claimed(_state, current.id):
                    return
                current.capture_invalidated = True
                if current.execution == "queued":
                    current.execution, current.error = "failed", JobFailure(code="DEPENDENCY_CHANGED")
                if current.proposal_id is not None and current.publication not in {"cancelled", "discarded", "no_change"}:
                    current.publication, current.publication_error = "needs_review", JobFailure(code="DEPENDENCY_CHANGED")
            updated = service.store.update(project, job.id, invalidate)
            await service.supervisor._emit(updated)
        service.supervisor.changed.set()
        return service.projects.response(project)

    def validate_processing(self, state, directory, job, candidate, workspace):
        captured = self.inputs.read(directory, job)
        if (candidate.input_id != captured.id or candidate.workspace is None or (candidate.normalized is None and candidate.import_draft is None)
                or workspace.project is not None
                or processing_source(workspace, self.service.projects.rules.load()) != captured.source_sha256):
            raise BackgroundFailure("DEPENDENCY_CHANGED")

    async def accept_sync(self, control, captured, record):
        service, project = self.service, control.project_id
        if record is None or (record.id, record.action_id) != (captured.sync_id, captured.action_id):
            raise BackgroundFailure("PROTOCOL")
        if record.status == "failed":
            from .fixed_runtime import ERRORS
            raise BackgroundFailure(ERRORS.get(record.error_code, record.error_code or "PROTOCOL"))
        guards = control.job.submission.guards.model_copy(deep=True)
        needs_review = False
        with service.projects.state_lock, service.store.guard(project) as directory:
            state = service.store._read(project, directory)
            current, _checksum = service.projects.storage._read_committed_unlocked(project)
            try:
                service.history.validate(state, directory, current, guards)
                mutation = fixed_mutation(project, record)
                if mutation is not None:
                    guards.writes = service.history.register(state, current,
                        mutation_selectors(captured.workspace, mutation), write=True).writes
                    service.store._write(directory, state, service.store._all())
            except BackgroundFailure as error:
                if error.code != "DEPENDENCY_CHANGED":
                    raise
                needs_review = True
        def store_payload():
            with service.projects.state_lock:
                current, checksum = service.projects.storage.read_committed(project)
                if any(s.id == record.id for s in current.sync_records):
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                after = current.model_copy(deep=True)
                if captured.original_sync is not None:
                    for original in after.sync_records:
                        if original.id == captured.original_sync.id and original.ready:
                            original.status, original.ready, original.proposed_steps = "stale", False, []
                            original.error_code = "SYNC_SUPERSEDED"
                after.sync_records.append(record)
                saved, _replay = service.publisher.snapshot(project, checksum, after, "metadata_fixed_" + record.id,
                    originals=service.projects.originals, artifacts=service.projects.artifacts, images=service.projects.images)
                service.publication.adopt(project, saved, digest_bytes(saved))
                from packages.resume_core.background_retention import JobRetention
                JobRetention(service.store).compact_manual(project, service.history)
        await asyncio.to_thread(store_payload)
        raw = fixed_payload(record)
        await self.accept(control, {"kind": "rich_sync", "syncId": record.id}, raw, guards, needs_review)

    def payload(self, project, reference):
        service = self.service
        with service.store.guard(project) as directory:
            state = service.store._read(project, directory)
            if reference.kind == "processing":
                return self.inputs.payload(state, directory, reference)
            if reference.kind != "rich_sync":
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            workspace, _checksum = service.projects.storage._read_committed_unlocked(project)
            record = next((s for s in workspace.sync_records if s.id == reference.sync_id), None)
            if record is None:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            return fixed_payload(record)

    async def accept(self, control, reference, raw, guards, needs_review=False):
        service = self.service
        proposal = ProposalBindingV1(schemaVersion=1, id="proposal_" + control.job.submission.input.id,
            jobId=control.job.id, projectId=control.project_id, lineage=control.job.submission.identity.lineage,
            accountGeneration=control.job.submission.account_generation, executionGeneration=control.job.execution_generation,
            turnId="turn_" + control.job.submission.input.id, payload=reference,
            payloadSha256=hashlib.sha256(raw).hexdigest(), payloadBytes=len(raw), guards=guards,
            scope=control.job.submission.scope, acceptedAt=service.store.clock(),
            executionDeadline=expiration(service.store.clock(), max(0.001, control.active_deadline-service.supervisor.clock.now())),
            authority="active", revocation=None)
        await service.proposals_for(control.project_id).accept(control, proposal, needs_review=needs_review)
        service.wake_publication(control.project_id)

    async def processing_stage(self, runtime, control):
        service, captured = self.service, runtime.captured
        sources = [s for s in captured.workspace.pre_draft.sources if s.id == captured.workspace.pre_draft.selected_source_id]
        request = GuiNormalizeRequest(sources=sources, formattingAsOf=captured.workspace.formatting_as_of,
            revision=captured.workspace.project_revision)
        await runtime.authorize()
        content_type = ResumeAssessmentContentService if runtime.model.stage == "assessment" else GuiNormalizationContentService
        content = content_type(runtime.provider, runtime.model.model)
        result = await runtime.content(lambda files: content.run(request, captured.rules, files, control.cancel)[0])
        if control.cancel.is_set():
            raise BackgroundFailure("CANCELLED")
        reason = self.preflight(control.job)
        if reason:
            raise BackgroundFailure(reason)
        identifier = "processing_" + captured.id[6:]
        with service.store.guard(control.project_id) as directory:
            state = service.store._read(control.project_id, directory)
            if runtime.model.stage == "assessment":
                candidate = ProcessingCandidateV1(schemaVersion=1, id=identifier, inputId=captured.id,
                    assessment=result, normalized=None, workspace=None)
            else:
                candidate = self.inputs.processing(directory, identifier)
                workspace = captured.workspace.model_copy(deep=True)
                workspace.project, workspace.pre_draft = assemble_import(workspace, result), None
                workspace.project_revision, workspace.document_revision = workspace.project.revision, workspace.project.document.revision
                workspace.rules_used, workspace.source_observed_at = captured.rules, result.source_observed_at
                if not workspace.title_manually_set:
                    workspace.title = result.candidate.name.text or workspace.title
                codes = {"unlikely": "source_not_resume", "uncertain": "source_resume_uncertain"}
                warnings = [codes[candidate.assessment.verdict]] if candidate.assessment.verdict in codes else []
                workspace.warnings = [w for w in workspace.warnings if w.code not in {
                    *[code for source in result.sources for code in source.warnings], "source_details_unresolved"}]
                workspace.warnings.extend(source_warnings(result.sources))
                if result._native_recovery_count or unresolved_source_units(result):
                    warnings.append("source_details_unresolved")
                for code in dict.fromkeys(warnings):
                    if not any(w.code == code for w in workspace.warnings):
                        workspace.warnings.append(RichWarning(id="warning_" + digest([identifier, code])[:24],
                            code=code, blockIds=[], recordIds=[], evidence=[]))
                candidate.normalized, candidate.workspace = result, workspace
            self.inputs.save_processing(directory, state, candidate)
        if runtime.model.stage == "extraction":
            await self.accept(control, {"kind": "processing", "candidateId": identifier},
                encoded(candidate.model_dump(mode="json", by_alias=True)), control.job.submission.guards)
