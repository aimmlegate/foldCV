"""One canonical transaction with exact durable recovery and scoped guards."""

from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager

from .agent_edits import semantic, validate_references
from .agent_store import digest
from .background_authority import PublicationAuthority
from .background_history import digest_bytes
from .background_inverse import inverse_mutation
from .background_limits import LIMITS
from .background_scopes import mutation_selectors, query_touches
from .background_store import BackgroundFailure, expiration, identity, job_in, records
from .models.agent import AgentEditBatch, AgentQuery, AgentQueryDependency
from .models.background import (CanonicalCandidateV1, CanonicalReceiptV1, HistoryCheckpointV1, JobFailure,
    ManualIntentV1, PublicationIntentV1, ScopeGuardV1, UndoOwnershipV1)
from .project_store import encoded, owned_file, strict_json
from .rich_mutations import apply_rich_mutation, mutation_sha256
from .storage import atomic_write, locked_root, private_directory
from .models.template_publication import TemplateCanonicalCandidateV2, decode_canonical_candidate
from .models.template_authority import TemplatePublicationAuthorizationV1

RESOLVED = frozenset({"receipt_stored", "reconciled"})


def checkpoint(state):
    return HistoryCheckpointV1(history=state.history.model_copy(deep=True),
        generations=[stamp.model_copy(deep=True) for stamp in state.generations])


def checkpoint_sha(value):
    return digest(value.model_dump(mode="json", by_alias=True))


def snapshot_request(identifier, before, after):
    return digest({"commandId": identifier, "beforeWorkspaceSha256": before, "afterWorkspaceSha256": after})


def proposal_in(state, job):
    result = next((proposal for proposal in state.proposals if proposal.id == job.proposal_id), None)
    if result is None or result.job_id != job.id:
        raise BackgroundFailure("JOB_SCOPE_INVALID")
    return result


class CanonicalCoordinator:
    def __init__(self, jobs, history, canonical, payload_loader, *, authority=None,
                 observer=lambda _name, _project: None, validate=validate_references):
        self.jobs, self.history, self.canonical, self.payload_loader = jobs, history, canonical, payload_loader
        self.authority, self.observer, self.validate = authority or PublicationAuthority(), observer, validate
        self.mutexes = {}
        self.template_checkpoint_locks = {}
        self.template_checkpoint_tasks = {}
        self.template_checkpoint_async_locks = {}
        self.template_checkpoint_fences = {}
        self.template_checkpoint_owners = {}
        self.template_export_tasks = {}
        self.canonical.background_observer = lambda phase, project: self.observer(phase, project)

    def _mutex(self, project):
        return self.mutexes.setdefault(project, threading.Lock())

    @contextmanager
    def _writer(self, project):
        self.jobs.load(project)
        with self._mutex(project), locked_root(self.jobs.projects / project, ".canonical.lock"):
            yield

    def _persist(self, directory, state):
        self.jobs._write(directory, state, self.jobs._all())

    def _fence(self, state, directory, intent):
        if intent.phase == "receipt_stored":
            return
        intent.phase = "fenced"
        if isinstance(intent, PublicationIntentV1):
            job = job_in(state, intent.job_id)
            if job.receipt is None:
                self._publication(job, "outcome_unknown", "OUTCOME_UNKNOWN")
        self.jobs.fences.setdefault(state.project_id, "OUTCOME_UNKNOWN")
        self._persist(directory, state)

    def _publication(self, job, publication, code=None):
        job.publication, job.publication_error = publication, JobFailure(code=code) if code else None
        job.event_cursor += 1
        job.updated_at = self.jobs.clock()

    def authorize_template(self, project, operation):
        from .template_import import authorization
        captured = authorization(operation)
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            self._writable(state)
            workspace, _checksum = self.canonical._read_committed_unlocked(project)
            retained = next((item for item in (workspace.project or workspace.pre_draft).template_operations if item.id == operation.id), None)
            if retained is None or retained != operation or operation.project_id != project:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            value = TemplatePublicationAuthorizationV1(schemaVersion=1, operationId=operation.id,
                authorizationId=captured.id, state='active', authorityHash=captured.authority_hash,
                dependencyHash=captured.dependency_hash, accountGeneration=state.account_generation)
            old = next((item for item in state.template_authorizations
                if item.operation_id == operation.id and item.authorization_id == captured.id), None)
            if old is not None:
                if old != value:
                    raise BackgroundFailure('CANCELLED' if old.state == 'cancelled' else 'DEPENDENCY_CHANGED')
                return old
            state.template_authorizations.append(value)
            self._persist(directory, state)
            return value

    def cancel_template(self, project, operation_id):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            intents = [intent for intent in state.manual_intents if intent.template_finalization is not None
                and intent.template_finalization.operation_id == operation_id]
            if any(intent.phase == 'fenced' for intent in intents):
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            claimed = any(intent.phase not in {'intent_stored', 'reconciled'} for intent in intents)
            if claimed:
                return False
            if not any(value.operation_id == operation_id for value in state.template_authorizations):
                workspace, _checksum = self.canonical._read_committed_unlocked(project)
                operation = next((item for item in (workspace.project or workspace.pre_draft).template_operations if item.id == operation_id), None)
                if operation is None or not operation.authorizations:
                    raise BackgroundFailure('JOB_NOT_FOUND')
                captured = operation.authorizations[-1]
                state.template_authorizations.append(TemplatePublicationAuthorizationV1(schemaVersion=1,
                    operationId=operation_id, authorizationId=captured.id, state='cancelled', authorityHash=captured.authority_hash,
                    dependencyHash=captured.dependency_hash, accountGeneration=state.account_generation))
            for value in state.template_authorizations:
                if value.operation_id == operation_id:
                    value.state = 'cancelled'
            self._persist(directory, state)
            return True

    @staticmethod
    def _intents(state):
        return [*state.intents, *state.manual_intents]

    def _writable(self, state, *, own=None):
        if state.project_id in self.template_checkpoint_fences:
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        if state.tombstoned:
            raise BackgroundFailure("PROJECT_DELETED")
        if any(intent.id != own and intent.phase not in RESOLVED for intent in self._intents(state)):
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        if state.project_id in self.jobs.fences:
            raise BackgroundFailure(self.jobs.fences[state.project_id])

    def _gate(self, state, job, proposal):
        if proposal.payload.kind == "agent_journal" and getattr(self, "assistant_review_required", lambda: False)():
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        account = self.jobs._read_dispatch(self.jobs.background / "dispatch.json").account_generation
        if state.tombstoned or state.account_generation != account or proposal.account_generation != account:
            raise BackgroundFailure("ACCOUNT_CHANGED")
        if (proposal.authority != "active" or job.publication in {"cancelled", "discarded"}
                or proposal.execution_generation != job.execution_generation):
            raise BackgroundFailure("CANCELLED")
        if job.capture_invalidated:
            raise BackgroundFailure("DEPENDENCY_CHANGED")

    def _payload(self, state, directory, proposal):
        from .agent_store import AgentFailure
        from .storage import StorageFailure
        try:
            return self._read_payload(state, directory, proposal)
        except BackgroundFailure as error:
            if error.code == "OUTCOME_UNKNOWN":
                self.jobs.fences.setdefault(state.project_id, "OUTCOME_UNKNOWN")
            raise
        except (AgentFailure, StorageFailure, OSError, ValueError):
            self.jobs.fences.setdefault(state.project_id, "OUTCOME_UNKNOWN")
            raise BackgroundFailure("OUTCOME_UNKNOWN") from None

    def _read_payload(self, state, directory, proposal):
        record = None
        if proposal.payload.kind == "rich_sync":
            from .background_fixed import fixed_payload
            workspace, _checksum = self.canonical._read_committed_unlocked(state.project_id)
            record = next((item for item in workspace.sync_records if item.id == proposal.payload.sync_id), None)
            if record is None:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            raw = fixed_payload(record)
        else:
            raw = self.payload_loader(state, directory, proposal.payload)
        if (not isinstance(raw, bytes) or len(raw) != proposal.payload_bytes
                or hashlib.sha256(raw).hexdigest() != proposal.payload_sha256):
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        if record is not None:
            from .background_fixed import fixed_mutation
            return fixed_mutation(state.project_id, record)
        if proposal.payload.kind == "processing":
            from .models.background import ProcessingCandidateV1
            value = ProcessingCandidateV1.model_validate(strict_json(raw))
            if (value.id != proposal.payload.candidate_id or value.workspace is None or (value.normalized is None and value.import_draft is None)
                    or value.workspace.project_id != state.project_id or value.workspace.project is None):
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            return value
        if proposal.payload.kind != "agent_journal":
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        batch = AgentEditBatch.model_validate(strict_json(raw))
        if (batch.run_id != proposal.job_id or batch.scope != proposal.scope
                or batch.id != proposal.payload.batch_id or mutation_sha256(batch.mutation) != batch.request_sha256):
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        return batch.mutation

    @staticmethod
    def _actual(original, state, job):
        value = original.model_copy(deep=True)
        value.client_mutation_id = "background_" + digest([state.lineage, job.id, job.proposal_id])[:40]
        value.action_id = value.client_mutation_id
        value.capture.session_id = "backend_" + state.lineage
        value.capture.action_id, value.capture.action_token = value.action_id, 0
        return type(original).model_validate(value.model_dump(by_alias=True))

    def _apply(self, workspace, mutation, *, validate, history_authorization=None):
        candidate, duplicate = apply_rich_mutation(workspace, mutation, history_authorization=history_authorization)
        if duplicate:
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        if validate:
            baseline = semantic(candidate)
            self.validate(candidate)
            if semantic(candidate) != baseline:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
        candidate.updated_at = self.jobs.clock()
        return candidate

    def _candidate(self, state, directory, before, after, mutation, job, proposal, *, snapshot_id=None, writer_binding=None, history_binding=None,
                   template_finalization=None):
        if template_finalization is not None and after.schema_version != 7:
            raise BackgroundFailure('JOB_SCOPE_INVALID')
        from .background_assets import guard_removal
        guard_removal(state, before, after)
        if mutation is not None and after.schema_version == 7:
            from .template_inverse import inverse_template_mutation
            inverse = inverse_template_mutation(before, after, mutation_id='inverse_' + mutation.client_mutation_id,
                session_id=mutation.capture.session_id, origin_action_id=mutation.action_id, action_token=0)
        else:
            inverse = inverse_mutation(before, after, mutation_id="inverse_" + mutation.client_mutation_id,
                session_id=mutation.capture.session_id) if mutation is not None else None
        if inverse is not None:
            self.history.register(state, before, mutation_selectors(before, inverse), write=True)
            from .models.agent import AgentEntityDependency
            from .rich_dependencies import dependency
            extra = []
            for selector in mutation_selectors(after, inverse):
                kind, identifier = selector.stamp.kind, selector.stamp.id
                try:
                    stamp = dependency(before, kind, identifier)
                except ValueError:
                    stamp = {"kind": kind, "id": identifier, "revision": 1, "fingerprint": None}
                extra.append(AgentEntityDependency(kind="entity", stamp=stamp))
            self.history.register(state, before, extra, write=True)
        linked = []
        if inverse is not None:
            identifiers = [step.record.id if step.kind == "put_record" else step.record_id for step in inverse.steps
                if step.kind in {"put_record", "remove_record"}]
            if identifiers:
                selector = AgentQueryDependency(kind="query", query=AgentQuery(kind="facts", ids=identifiers, parentId="linked"),
                    fingerprint="0" * 64)
                selector.fingerprint = self.history.fingerprint(before, selector, missing=True)
                self.history.register(state, before, [selector], write=True)
                linked.append(selector)
        previous = checkpoint(state)
        self._persist(directory, state)
        following = state.model_copy(deep=True)
        touches = query_touches(state, before, after, mutation) if mutation else set()
        self.history.advance(following, before, after, touches=touches)
        inverse_guards = (self.history.register(following, after, mutation_selectors(after, inverse), write=True)
            if inverse else ScopeGuardV1(schemaVersion=1, reads=[], writes=[]))
        for selector in linked:
            selector = selector.model_copy(update={"fingerprint": self.history.fingerprint(after, selector, missing=True)})
            inverse_guards.reads = self.history.register(following, after, [selector], write=True).writes
        candidate_type = TemplateCanonicalCandidateV2 if after.schema_version == 7 else CanonicalCandidateV1
        extra = {'templateFinalization': template_finalization} if after.schema_version == 7 else {}
        return candidate_type(schemaVersion=2 if after.schema_version == 7 else 1, id=identity("candidate"), projectId=state.project_id,
            lineage=state.lineage, jobId=job.id if job else None, proposalId=proposal.id if proposal else None,
            proposalSha256=proposal.payload_sha256 if proposal else None, payload=proposal.payload if proposal else None,
            manualMutation=None if job else mutation, clientMutationId=mutation.client_mutation_id if mutation else snapshot_id,
            actionId=mutation.action_id if mutation else snapshot_id, sessionId=mutation.capture.session_id if mutation else "backend",
            requestSha256=mutation_sha256(mutation) if mutation else snapshot_request(snapshot_id, digest_bytes(before), digest_bytes(after)),
            beforeWorkspaceSha256=digest_bytes(before), afterWorkspaceSha256=digest_bytes(after),
            beforeHistory=previous, afterHistory=checkpoint(following), workspace=after, inverse=inverse,
            inverseGuards=inverse_guards, persistedAt=self.jobs.clock(), snapshotWrite=mutation is None,
            writerBinding=writer_binding,
            historyBinding=history_binding, **extra,
            syncPayloads=[{"syncId": record.id, "stepsSha256": digest([step.model_dump(mode="json", by_alias=True) for step in record.proposed_steps])}
                for record in after.sync_records if record.proposed_steps and any(item.payload.kind == "rich_sync"
                    and item.payload.sync_id == record.id for item in state.proposals)])

    def _store_intent(self, state, directory, candidate, claim):
        value = candidate.model_dump(mode="json", by_alias=True)
        for record in value["workspace"]["syncRecords"]:
            if any(item.sync_id == record["id"] for item in candidate.sync_payloads):
                record["proposedSteps"] = []
        raw = encoded(value)
        folder = private_directory(directory / "canonical-candidates")
        path = folder / (candidate.id + ".json")
        fields = dict(schemaVersion=1, id="intent_" + candidate.id, projectId=state.project_id, lineage=state.lineage,
            clientMutationId=candidate.client_mutation_id, requestSha256=candidate.request_sha256,
            beforeWorkspaceSha256=candidate.before_workspace_sha256, afterWorkspaceSha256=candidate.after_workspace_sha256,
            beforeGenerationsSha256=checkpoint_sha(candidate.before_history),
            afterGenerationsSha256=checkpoint_sha(candidate.after_history), candidateRef=candidate.id,
            previousRef=candidate.id, writerEpoch=claim.epoch if claim else None,
            incarnation=claim.incarnation if claim else None, barrierGeneration=claim.generation if claim else None,
            phase="intent_stored", assetPins=[asset.id for asset in candidate.workspace.project.assets] if candidate.workspace.project else [],
            candidateSha256=hashlib.sha256(raw).hexdigest())
        if candidate.job_id:
            intent = PublicationIntentV1(**fields, jobId=candidate.job_id, proposalId=candidate.proposal_id)
        else:
            intent = ManualIntentV1(**fields, actionId=candidate.action_id,
                templateFinalization=getattr(candidate, 'template_finalization', None),
                historyJobId=candidate.history_binding.job_id if candidate.history_binding else None,
                stepsSha256=digest([step.model_dump(mode="json", by_alias=True) for step in candidate.manual_mutation.steps])
                    if candidate.manual_mutation else None)
        future = state.model_copy(deep=True)
        future.history, future.generations = candidate.after_history.history, candidate.after_history.generations
        if future.writer is not None and (candidate.writer_binding is not None or future.writer.status == "clean_detached"):
            future.writer.acknowledged_revision = candidate.workspace.project_revision
            future.writer.acknowledged_sha256 = candidate.after_workspace_sha256
            if candidate.writer_binding is not None:
                from .background_drafts import finish_draft_resolution
                finish_draft_resolution(future, candidate.writer_binding)
        completed_at = "9999-12-30T23:59:59.999999+00:00"
        completed = intent.model_copy(update={"phase": "receipt_stored", "resolved_at": completed_at}, deep=True)
        (future.intents if candidate.job_id else future.manual_intents).append(completed)
        if candidate.history_binding is not None:
            from .background_history_commands import apply_history_receipt
            apply_history_receipt(future, candidate, self.canonical, completed_at)
        states = self.jobs._all()
        from .background_fixed import stored_fixed_bytes
        fixed_bytes = stored_fixed_bytes(state, candidate.workspace)
        self.jobs._capacity(future, states, replacing=(path, len(raw)), canonical_fixed_bytes=fixed_bytes)
        if candidate.job_id:
            from .background_history_owner import close_redo
            close_redo(future, completed_at)
            future_job = job_in(future, candidate.job_id)
            future_job.receipt, future_job.publication = self._receipt_value(candidate, completed_at), "saved"
            if candidate.inverse is not None:
                future.inverses.append(self._inverse_value(candidate, completed_at))
                from .background_assets import pin_snapshot
                pin_snapshot(future, self.canonical, candidate.workspace, "inverse", candidate.proposal_id)
        if records(future) > LIMITS.metadata_project_records or len(future.inverses) > LIMITS.inverse_project_records:
            raise BackgroundFailure("JOB_STORAGE_FULL")
        self.jobs._capacity(future, states, replacing=(path, len(raw)), canonical_fixed_bytes=fixed_bytes)
        self.jobs._capacity(state, states, replacing=(path, len(raw)), canonical_fixed_bytes=fixed_bytes)
        atomic_write(path, raw)
        self.jobs._sync_namespace(path)
        self.observer("before_intent_stored", state.project_id)
        if candidate.job_id:
            state.intents.append(intent)
        else:
            state.manual_intents.append(intent)
        self._persist(directory, state)
        self.observer("intent_stored", state.project_id)
        return intent

    def _load_candidate(self, state, directory, intent):
        path = directory / "canonical-candidates" / (intent.candidate_ref + ".json")
        owned_file(path, LIMITS.sidecar_project_bytes)
        raw = path.read_bytes()
        value = decode_canonical_candidate(strict_json(raw))
        if value.sync_payloads:
            workspace, _checksum = self.canonical._read_committed_unlocked(state.project_id)
            for ref in value.sync_payloads:
                source = next((record for record in workspace.sync_records if record.id == ref.sync_id), None)
                target = next((record for record in value.workspace.sync_records if record.id == ref.sync_id), None)
                if (source is None or target is None or target.proposed_steps
                        or digest([step.model_dump(mode="json", by_alias=True) for step in source.proposed_steps]) != ref.steps_sha256):
                    raise BackgroundFailure("OUTCOME_UNKNOWN")
                target.proposed_steps = [step.model_copy(deep=True) for step in source.proposed_steps]
        if (hashlib.sha256(raw).hexdigest() != intent.candidate_sha256 or value.id != intent.candidate_ref
                or (value.project_id, value.lineage, value.client_mutation_id, value.request_sha256,
                    value.before_workspace_sha256, value.after_workspace_sha256) !=
                (state.project_id, state.lineage, intent.client_mutation_id, intent.request_sha256,
                    intent.before_workspace_sha256, intent.after_workspace_sha256)
                or digest_bytes(value.workspace) != value.after_workspace_sha256
                or checkpoint_sha(value.before_history) != intent.before_generations_sha256
                or checkpoint_sha(value.after_history) != intent.after_generations_sha256
                or value.before_history.history.workspace_sha256 != value.before_workspace_sha256
                or value.after_history.history.workspace_sha256 != value.after_workspace_sha256):
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        if isinstance(intent, PublicationIntentV1):
            job = job_in(state, intent.job_id)
            proposal = proposal_in(state, job)
            original = self._payload(state, directory, proposal)
            expected_request = (snapshot_request(value.client_mutation_id, value.before_workspace_sha256, value.after_workspace_sha256)
                if proposal.payload.kind == "processing" else mutation_sha256(self._actual(original, state, job)))
            if ((value.job_id, value.proposal_id, value.proposal_sha256, value.payload) !=
                    (job.id, proposal.id, proposal.payload_sha256, proposal.payload)
                    or expected_request != value.request_sha256):
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            if proposal.payload.kind == "processing" and (not value.snapshot_write
                    or value.workspace.project != original.workspace.project
                    or value.workspace.rules_used != original.workspace.rules_used
                    or value.workspace.source_observed_at != original.workspace.source_observed_at):
                raise BackgroundFailure("OUTCOME_UNKNOWN")
        else:
            expected = (snapshot_request(value.client_mutation_id, value.before_workspace_sha256, value.after_workspace_sha256)
                if value.snapshot_write else mutation_sha256(value.manual_mutation))
            if value.job_id is not None or expected != value.request_sha256:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            if getattr(value, 'template_finalization', None) != intent.template_finalization:
                raise BackgroundFailure('OUTCOME_UNKNOWN')
        for history in (value.before_history, value.after_history):
            proof = state.model_copy(deep=True)
            proof.history, proof.generations = history.history, history.generations
            self.history._ready(proof, directory, history.history.workspace_sha256)
        return value

    def publish(self, project, job_id, proposal_sha256, *, originals=None, artifacts=None, images=None, expected_claim=None, approved=False):
        from .project_catalog import AccessChanged
        job = self.jobs.read(project, job_id)
        catalog = getattr(self.canonical, "catalog", None)
        if job.submission.kind == "agent" and job.receipt is None and catalog is not None:
            try:
                with catalog.authority(project, job.submission.access_revision):
                    return self._publish(project, job_id, proposal_sha256, originals=originals,
                        artifacts=artifacts, images=images, expected_claim=expected_claim, approved=approved)
            except AccessChanged:
                raise BackgroundFailure("DEPENDENCY_CHANGED") from None
        return self._publish(project, job_id, proposal_sha256, originals=originals,
            artifacts=artifacts, images=images, expected_claim=expected_claim, approved=approved)

    def _publish(self, project, job_id, proposal_sha256, *, originals=None, artifacts=None, images=None, expected_claim=None, approved=False):
        with self._writer(project):
            known_job = self.jobs.read(project, job_id)
            if known_job.receipt is not None or known_job.publication == "no_change":
                state = self.jobs.load(project)
                if proposal_in(state, known_job).payload_sha256 != proposal_sha256:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                return known_job
            from .background_retention import JobRetention
            JobRetention(self.jobs).compact_manual(project, self.history)
            self.history.open(project)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                job, current = job_in(state, job_id), self.canonical._read_committed_unlocked(project)[0]
                proposal = proposal_in(state, job)
                if proposal.payload_sha256 != proposal_sha256:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                if job.receipt is not None:
                    return job
                known = next((intent for intent in state.intents if intent.job_id == job_id and intent.phase != "reconciled"), None)
                if known is not None:
                    if known.phase not in RESOLVED:
                        raise BackgroundFailure("OUTCOME_UNKNOWN")
                    return job
                self._writable(state)
                if job.capture_invalidated:
                    self._publication(job, "needs_review", "DEPENDENCY_CHANGED")
                    self._persist(directory, state)
                    return job
                self._gate(state, job, proposal)
                if job.submission.approval_required and not approved:
                    return job
                if job.publication == "needs_review":
                    return job
                try:
                    self.history.validate(state, directory, current, proposal.guards)
                except BackgroundFailure as error:
                    if error.code != "DEPENDENCY_CHANGED":
                        raise
                    self._publication(job, "needs_review", "DEPENDENCY_CHANGED")
                    self._persist(directory, state)
                    return job
                original = self._payload(state, directory, proposal)
                if original is None:
                    self._publication(job, "no_change")
                    from .background_assets import release_resolved_jobs
                    release_resolved_jobs(state)
                    self._persist(directory, state)
                    return job
                try:
                    claim = self.authority.require(state, current, now=self.jobs.clock())
                    if expected_claim is not None and claim != expected_claim:
                        raise BackgroundFailure("WRITER_UNKNOWN")
                except BackgroundFailure as error:
                    if error.code != "WRITER_UNKNOWN":
                        raise
                    self._publication(job, "waiting_for_sync", "WRITER_UNKNOWN")
                    self._persist(directory, state)
                    return job
                actual, snapshot_id = None, None
                if proposal.payload.kind == "processing":
                    validator = getattr(self, "processing_validator", None)
                    if validator is None:
                        raise BackgroundFailure("JOB_SCOPE_INVALID")
                    try:
                        validator(state, directory, job, original, current)
                    except BackgroundFailure as error:
                        if error.code != "DEPENDENCY_CHANGED":
                            raise
                        self._publication(job, "needs_review", error.code)
                        self._persist(directory, state)
                        return job
                    after = current.model_copy(deep=True)
                    after.project, after.pre_draft = original.workspace.project.model_copy(deep=True), None
                    after.project_revision, after.document_revision = original.workspace.project_revision, original.workspace.document_revision
                    after.rules_used, after.source_observed_at = original.workspace.rules_used, original.workspace.source_observed_at
                    if not after.title_manually_set:
                        after.title = original.workspace.title
                    after.warnings += [w.model_copy(deep=True) for w in original.workspace.warnings
                        if w.code not in {old.code for old in after.warnings}]
                    snapshot_id = "background_" + digest([state.lineage, job.id, job.proposal_id])[:40]
                else:
                    actual = self._actual(original, state, job)
                    after = self._apply(current, actual, validate=True)
                if proposal.payload.kind == "rich_sync":
                    record = next(item for item in after.sync_records if item.id == proposal.payload.sync_id)
                    record.ready = False
                    if record.status != "conflict":
                        record.status = "applied"
            self.observer("before_canonical_prepared", project)
            prepared = self.canonical.prepare_save(after, originals or {}, artifacts or {}, images)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                latest, checksum = self.canonical._read_committed_unlocked(project)
                self._writable(state)
                job, proposal = job_in(state, job_id), proposal_in(state, job_in(state, job_id))
                self._gate(state, job, proposal)
                if checksum != digest_bytes(current):
                    raise BackgroundFailure("BUSY")
                self.history.validate(state, directory, latest, proposal.guards)
                if self.authority.require(state, latest, now=self.jobs.clock()) != claim:
                    raise BackgroundFailure("WRITER_UNKNOWN")
                candidate = self._candidate(state, directory, current, after, actual, job, proposal, snapshot_id=snapshot_id)
                intent = self._store_intent(state, directory, candidate, claim)
            return self._commit(project, intent.id, candidate, prepared)

    def manual(self, project, request, *, originals=None, artifacts=None, images=None, authorize=None, history_binding=None,
               history_authority=None, prepared=None):
        return self._manual(project, request, originals=originals, artifacts=artifacts, images=images, authorize=authorize,
            history_binding=history_binding, history_authority=history_authority, prepared=prepared)

    def apply_reviewed(self, project, request, grant, *, originals=None, artifacts=None, images=None):
        from .assistant_publication import AssistantMutationGrant
        if not isinstance(grant, AssistantMutationGrant):
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        grant.require(project, request)
        return self._manual(project, request, originals=originals, artifacts=artifacts, images=images,
            authorize=grant.authorize, history_binding=grant.history_binding, reviewed=grant)

    def _manual(self, project, request, *, originals=None, artifacts=None, images=None, authorize=None, history_binding=None,
                history_authority=None, prepared=None, reviewed=None):
        with self._writer(project):
            from .background_retention import JobRetention
            JobRetention(self.jobs).compact_manual(project, self.history)
            self.history.open(project)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                before, _checksum = self.canonical._read_committed_unlocked(project)
                known = next((intent for intent in state.manual_intents if intent.client_mutation_id == request.client_mutation_id), None)
                if known is not None:
                    if known.request_sha256 != mutation_sha256(request):
                        raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                    if known.phase == "receipt_stored":
                        return before, True
                    raise BackgroundFailure("OUTCOME_UNKNOWN" if known.phase != "reconciled" else
                        known.reconciled_reason.code if known.reconciled_reason else "SAVE_FAILED")
                if reviewed is not None:
                    reviewed.require(project, request)
                elif request.client_mutation_id.startswith(("background_", "agent_", "inverse_")) or request.client_mutation_id.startswith("history_") and history_binding is None:
                    raise BackgroundFailure("JOB_SCOPE_INVALID")
                self._writable(state)
                self.history._ready(state, directory, digest_bytes(before))
                proof = next((item for item in before.mutation_replay if item.client_mutation_id == request.client_mutation_id), None)
                if proof is not None:
                    if proof.request_sha256 != mutation_sha256(request):
                        raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                    self.canonical._read_committed_unlocked(project, synchronize=True)
                    return before, True
                binding = authorize(state, before, directory) if authorize else None
                if (any(record.action_id == request.action_id and record.error_code in {"CANCELLED", "SYNC_SUPERSEDED"}
                        for record in before.sync_records) and not any(record.action_id == request.action_id and record.ready
                            and record.proposed_steps == request.steps for record in before.sync_records)):
                    raise BackgroundFailure("JOB_SCOPE_INVALID")
                authorization = history_authority(state, before, directory) if history_authority else None
                after = self._apply(before, request, validate=False, history_authorization=authorization)
            prepared_save = self.canonical.prepare_save(after, originals or {}, artifacts or {}, images)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                _latest, checksum = self.canonical._read_committed_unlocked(project)
                self._writable(state)
                if checksum != digest_bytes(before):
                    raise BackgroundFailure("BUSY")
                self.history._ready(state, directory, checksum)
                candidate = self._candidate(state, directory, before, after, request, None, None,
                    writer_binding=binding, history_binding=history_binding)
                if prepared is not None:
                    prepared(before, after, candidate, state)
                if reviewed is not None:
                    reviewed.prepared(after)
                intent = self._store_intent(state, directory, candidate, None)
            self._commit(project, intent.id, candidate, prepared_save, reviewed=reviewed)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                known = next(item for item in state.manual_intents if item.id == intent.id)
                if known.phase != "receipt_stored":
                    raise BackgroundFailure(known.reconciled_reason.code if known.phase == "reconciled"
                        and known.reconciled_reason else "OUTCOME_UNKNOWN")
            return after, False

    def _stage(self, state, directory, intent, phase):
        intent.phase = phase
        if phase in RESOLVED and intent.resolved_at is None:
            intent.resolved_at = self.jobs.clock()
        self._persist(directory, state)
        self.observer(phase, state.project_id)

    def confirm_snapshot(self, project, snapshot):
        with self._writer(project), self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            self._writable(state)
            current, checksum = self.canonical._read_committed_unlocked(project, synchronize=True)
            self.history._ready(state, directory, checksum)
            if digest_bytes(snapshot) != checksum:
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            self.canonical.expected[project] = checksum
            return current, checksum

    def legacy_sync_saved(self, project, record):
        with self._writer(project), self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            self._writable(state)
            current, checksum = self.canonical._read_committed_unlocked(project)
            self.history._ready(state, directory, checksum)
            for intent in state.manual_intents:
                if intent.phase != "receipt_stored":
                    continue
                if intent.action_id is not None and intent.steps_sha256 is not None:
                    if intent.action_id == record.action_id and intent.steps_sha256 == digest([
                            step.model_dump(mode="json", by_alias=True) for step in record.proposed_steps]):
                        return any(item.client_mutation_id == intent.client_mutation_id and item.request_sha256 == intent.request_sha256
                            for item in current.mutation_replay)
                    continue
                candidate = self._load_candidate(state, directory, intent)
                mutation = candidate.manual_mutation
                if mutation is not None and mutation.action_id == record.action_id and mutation.steps == record.proposed_steps:
                    return any(item.client_mutation_id == mutation.client_mutation_id
                        and item.request_sha256 == intent.request_sha256 for item in current.mutation_replay)
            return False

    def snapshot(self, project, before_sha256, after, command_id, *, originals=None, artifacts=None, images=None, base=None,
                 template_finalization=None):
        return self._snapshot(project, before_sha256, after, command_id, originals=originals, artifacts=artifacts,
            images=images, base=base, template_finalization=template_finalization)

    def reviewed_snapshot(self, project, before_sha256, after, grant, *, originals=None, artifacts=None, images=None):
        from .assistant_publication import AssistantSnapshotGrant
        if not isinstance(grant, AssistantSnapshotGrant):
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        grant.require(project, after)
        return self._snapshot(project, before_sha256, after, grant.command_id, originals=originals,
            artifacts=artifacts, images=images, reviewed=grant)

    def _snapshot(self, project, before_sha256, after, command_id, *, originals=None, artifacts=None, images=None, base=None,
                  template_finalization=None, reviewed=None):
        """A whole-snapshot writer must prove its exact base; it cannot overwrite a newer save."""
        with self._writer(project):
            from .background_retention import JobRetention
            JobRetention(self.jobs).compact_manual(project, self.history)
            self.history.open(project)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                before, checksum = self.canonical._read_committed_unlocked(project)
                if base is not None:
                    from .rich_snapshot_merge import merge_snapshot
                    if digest_bytes(base) != before_sha256:
                        raise BackgroundFailure("JOB_SCOPE_INVALID")
                    after = merge_snapshot(base, after, before)
                    before_sha256 = checksum
                request_sha = snapshot_request(command_id, before_sha256, digest_bytes(after))
                known = next((item for item in state.manual_intents if item.client_mutation_id == command_id), None)
                if known is not None:
                    if known.request_sha256 != request_sha:
                        raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                    if known.phase == "receipt_stored":
                        return before, True
                    raise BackgroundFailure("OUTCOME_UNKNOWN" if known.phase != "reconciled" else "SAVE_FAILED")
                self._writable(state)
                if checksum != before_sha256:
                    raise BackgroundFailure("DEPENDENCY_CHANGED")
                self.history._ready(state, directory, checksum)
                binding = reviewed.authorize(state, before, directory) if reviewed else None
                from .background_fixed import guard_fixed_records
                guard_fixed_records(state, before, after)
                if digest_bytes(after) == checksum:
                    current, _checksum = self.canonical._read_committed_unlocked(project, synchronize=True)
                    self.canonical.expected[project] = checksum
                    return current, False
            self.observer("before_snapshot_prepared", project)
            prepared = self.canonical.prepare_save(after, originals or {}, artifacts or {}, images)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                _latest, checksum = self.canonical._read_committed_unlocked(project)
                self._writable(state)
                if checksum != before_sha256:
                    raise BackgroundFailure("DEPENDENCY_CHANGED")
                self.history._ready(state, directory, checksum)
                candidate = self._candidate(state, directory, before, after, None, None, None, snapshot_id=command_id,
                    template_finalization=template_finalization, writer_binding=binding)
                intent = self._store_intent(state, directory, candidate, None)
            self._commit(project, intent.id, candidate, prepared, reviewed=reviewed)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                final_intent = next(item for item in state.manual_intents if item.id == intent.id)
                if template_finalization is not None and final_intent.phase == 'reconciled' and final_intent.reconciled_reason:
                    raise BackgroundFailure(final_intent.reconciled_reason.code)
                if final_intent.phase != "receipt_stored":
                    raise BackgroundFailure("OUTCOME_UNKNOWN")
            return after, False

    def _commit(self, project, intent_id, candidate, prepared, *, reviewed=None):
        result = None
        self.observer("before_commit_claim", project)
        try:
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                intent = next(intent for intent in self._intents(state) if intent.id == intent_id)
                before, checksum = self.canonical._read_committed_unlocked(project)
                self._writable(state, own=intent.id)
                if checksum != candidate.before_workspace_sha256 or checkpoint_sha(checkpoint(state)) != checkpoint_sha(candidate.before_history):
                    raise BackgroundFailure("DEPENDENCY_CHANGED")
                self._load_candidate(state, directory, intent)
                self.canonical.expected[project] = checksum
                def claim_commit():
                    if reviewed is not None:
                        from .assistant_publication import AssistantSnapshotGrant
                        reviewed.require(project, candidate if isinstance(reviewed, AssistantSnapshotGrant) else candidate.manual_mutation)
                    from .background_assets import guard_removal
                    guard_removal(state, before, candidate.workspace)
                    binding = getattr(candidate, 'template_finalization', None)
                    if binding is not None:
                        from .template_finalization import validate_finalization
                        validate_finalization(binding, before, candidate.workspace, self.jobs.clock())
                        current = [item for item in state.template_authorizations if item.operation_id == binding.operation_id]
                        if not current or current[-1].authorization_id != binding.authorization_id or current[-1].state != 'active':
                            raise BackgroundFailure('CANCELLED')
                        captured = next(operation.capture for operation in (before.project or before.pre_draft).template_operations
                            if operation.id == binding.operation_id)
                        if (current[-1].authority_hash, current[-1].dependency_hash) != (captured.authority_hash, captured.dependency_hash):
                            raise BackgroundFailure('DEPENDENCY_CHANGED')
                        if current[-1].account_generation != self.jobs._read_dispatch(self.jobs.background / 'dispatch.json').account_generation:
                            raise BackgroundFailure('ACCOUNT_CHANGED')
                        gate = getattr(self, 'template_authority', None)
                        if gate is None:
                            raise BackgroundFailure('WRITER_UNKNOWN')
                        gate(binding, before, candidate.workspace)
                    if candidate.writer_binding is not None:
                        validator = getattr(self, "writer_validator", None)
                        if validator is None:
                            raise BackgroundFailure("WRITER_UNKNOWN")
                        validator(state, candidate.writer_binding)
                    if candidate.history_binding is not None:
                        validator = getattr(self, "history_validator", None)
                        if validator is None:
                            raise BackgroundFailure("WRITER_UNKNOWN")
                        validator(state, directory, before, candidate.history_binding)
                    if candidate.job_id:
                        job, proposal = job_in(state, candidate.job_id), proposal_in(state, job_in(state, candidate.job_id))
                        self._gate(state, job, proposal)
                        self.history.validate(state, directory, before, proposal.guards)
                        if proposal.payload.kind == "processing":
                            self.processing_validator(state, directory, job, self._payload(state, directory, proposal), before)
                        claim = self.authority.require(state, before, now=self.jobs.clock())
                        if (claim.epoch, claim.incarnation, claim.generation) != (intent.writer_epoch, intent.incarnation, intent.barrier_generation):
                            raise BackgroundFailure("WRITER_UNKNOWN")
                        self._publication(job, "committing")
                        if state.barrier is not None and claim.epoch is not None:
                            state.barrier.state = "commit_claimed"
                    if reviewed is not None:
                        reviewed.claim()
                    self._stage(state, directory, intent, "commit_claimed")
                    self.observer("before_workspace_replaced", project)
                def replaced():
                    self._stage(state, directory, intent, "workspace_replaced")
                    self.observer("before_workspace_durable", project)
                def durable(checksum):
                    if checksum != candidate.after_workspace_sha256:
                        raise BackgroundFailure("OUTCOME_UNKNOWN")
                    self._stage(state, directory, intent, "workspace_durable")
                    self.observer("before_generation_history_durable", project)
                    state.history, state.generations = candidate.after_history.history, candidate.after_history.generations
                    self._stage(state, directory, intent, "generation_history_durable")
                    self._receipt(state, directory, intent, candidate)
                self.canonical._commit_prepared_unlocked(prepared, before_workspace=claim_commit,
                    workspace_replaced=replaced, after_workspace=durable)
                self.observer("registry_updated", project)
                if candidate.job_id:
                    result = job_in(state, candidate.job_id).model_copy(deep=True)
        except Exception as error:
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                intent = next(intent for intent in self._intents(state) if intent.id == intent_id)
                if (intent.phase == "intent_stored" and isinstance(error, BackgroundFailure)
                        and error.code in {"CANCELLED", "ACCOUNT_CHANGED", "WRITER_UNKNOWN", "DEPENDENCY_CHANGED", "REQUEST_EXPIRED", "CLEANUP_FAILED"}):
                    if candidate.job_id:
                        job = job_in(state, candidate.job_id)
                        if job.publication not in {"cancelled", "discarded"}:
                            if error.code in {"CANCELLED", "ACCOUNT_CHANGED"}:
                                self._publication(job, "cancelled", error.code)
                                proposal = proposal_in(state, job)
                                proposal.authority, proposal.revocation = "revoked", "account_changed" if error.code == "ACCOUNT_CHANGED" else "stop"
                            else:
                                self._publication(job, "needs_review" if error.code == "DEPENDENCY_CHANGED" else "waiting_for_sync",
                                    error.code)
                    intent.phase = "reconciled"
                    intent.reconciled_reason = JobFailure(code=error.code)
                    intent.resolved_at = self.jobs.clock()
                    self._persist(directory, state)
                    return job.model_copy(deep=True) if candidate.job_id else None
                if intent.phase != "receipt_stored":
                    self._fence(state, directory, intent)
                elif candidate.job_id:
                    result = job_in(state, candidate.job_id).model_copy(deep=True)
            if intent.phase != "receipt_stored":
                raise BackgroundFailure("OUTCOME_UNKNOWN") from None
        self.observer("before_response_event_delivery", project)
        self.observer("response_event_delivery", project)
        self.observer("event_emitted", project)
        return result

    def _receipt(self, state, directory, intent, candidate):
        self.observer("before_receipt_stored", state.project_id)
        binding = candidate.writer_binding
        if binding is not None:
            writer = state.writer
            if writer is None or (writer.epoch, writer.incarnation) != (binding.epoch, binding.incarnation):
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            writer.acknowledged_revision = candidate.workspace.project_revision
            writer.acknowledged_sha256 = candidate.after_workspace_sha256
            from .background_drafts import finish_draft_resolution
            finish_draft_resolution(state, binding)
        if candidate.history_binding is not None:
            from .background_history_commands import apply_history_receipt
            apply_history_receipt(state, candidate, self.canonical, self.jobs.clock())
        if candidate.job_id:
            from .background_history_owner import close_redo
            from .background_assets import pin_snapshot, release_resolved_jobs
            completed_at = self.jobs.clock()
            close_redo(state, completed_at)
            job = job_in(state, candidate.job_id)
            job.receipt = self._receipt_value(candidate, completed_at)
            self._publication(job, "saved")
            if candidate.inverse is not None and not any(item.proposal_id == candidate.proposal_id for item in state.inverses):
                state.inverses.append(self._inverse_value(candidate, completed_at))
                pin_snapshot(state, self.canonical, candidate.workspace, "inverse", candidate.proposal_id)
            release_resolved_jobs(state)
        if state.barrier is not None and state.barrier.state == "commit_claimed":
            state.barrier.state = "resolved"
        if state.writer is not None and state.writer.status == "clean_detached":
            state.writer.acknowledged_revision = candidate.workspace.project_revision
            state.writer.acknowledged_sha256 = candidate.after_workspace_sha256
        self._stage(state, directory, intent, "receipt_stored")

    @staticmethod
    def _receipt_value(candidate, completed_at=None):
        workspace = candidate.workspace
        return CanonicalReceiptV1(schemaVersion=1, projectId=candidate.project_id, lineage=candidate.lineage,
            jobId=candidate.job_id, proposalId=candidate.proposal_id, clientMutationId=candidate.client_mutation_id,
            requestSha256=candidate.request_sha256, proposalSha256=candidate.proposal_sha256,
            workspaceSha256=candidate.after_workspace_sha256, generationsSha256=checkpoint_sha(candidate.after_history),
            projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
            factsRevision=workspace.project.facts.revision, durable=True, persistedAt=completed_at or candidate.persisted_at)

    @staticmethod
    def _inverse_value(candidate, completed_at=None):
        raw = encoded(candidate.inverse.model_dump(mode="json", by_alias=True))
        return UndoOwnershipV1(schemaVersion=1, jobId=candidate.job_id, proposalId=candidate.proposal_id,
            owner="backend", writerEpoch=None, incarnation=None, transferId="transfer_" + candidate.id,
            inverseRef=candidate.id, inverseSha256=hashlib.sha256(raw).hexdigest(), inverseBytes=len(raw),
            expiresAt=expiration(completed_at or candidate.persisted_at, LIMITS.inverse_seconds), guards=candidate.inverse_guards)

    def recover(self, project, *, clear_fence=True):
        with self._writer(project), self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            for intent in self._intents(state):
                if intent.phase in RESOLVED:
                    continue
                try:
                    candidate = self._load_candidate(state, directory, intent)
                    self.observer("before_proof_recovery", project)
                    current, checksum = self.canonical._read_committed_unlocked(project, synchronize=True)
                    actual_history = checkpoint_sha(checkpoint(state))
                    if checksum == candidate.before_workspace_sha256 and actual_history == checkpoint_sha(candidate.before_history):
                        if candidate.job_id:
                            job = job_in(state, candidate.job_id)
                            if job.publication not in {"cancelled", "discarded"}:
                                self._publication(job, "save_failed", "SAVE_FAILED")
                        intent.phase = "reconciled"
                        intent.resolved_at = self.jobs.clock()
                        if state.barrier is not None and state.barrier.state == "commit_claimed":
                            state.barrier.state = "revoked"
                        self._persist(directory, state)
                        self.observer("recovery_aborted", project)
                    elif checksum == candidate.after_workspace_sha256 and actual_history in {
                            checkpoint_sha(candidate.before_history), checkpoint_sha(candidate.after_history)}:
                        proof = next((item for item in current.mutation_replay if item.client_mutation_id == candidate.client_mutation_id), None)
                        if not candidate.snapshot_write and (proof is None or proof.request_sha256 != candidate.request_sha256
                                or proof.resulting_revision != candidate.workspace.project_revision):
                            raise BackgroundFailure("OUTCOME_UNKNOWN")
                        state.history, state.generations = candidate.after_history.history, candidate.after_history.generations
                        self._stage(state, directory, intent, "generation_history_durable")
                        self.observer("after_generation_recovery", project)
                        self._receipt(state, directory, intent, candidate)
                        self.observer("after_receipt_recovery", project)
                    else:
                        raise BackgroundFailure("OUTCOME_UNKNOWN")
                except Exception:
                    self._fence(state, directory, intent)
                    raise BackgroundFailure("OUTCOME_UNKNOWN") from None
            if state.history is not None or state.generations or (directory / "history-activation.json").exists():
                _current, checksum = self.canonical._read_committed_unlocked(project)
                self.history._ready(state, directory, checksum)
            if clear_fence and self.jobs.fences.get(project) == "OUTCOME_UNKNOWN":
                self.jobs.fences.pop(project, None)
            return state
