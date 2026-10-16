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

    @staticmethod
    def _intents(state):
        return [*state.intents, *state.manual_intents]

    def _writable(self, state, *, own=None):
        if state.tombstoned:
            raise BackgroundFailure("PROJECT_DELETED")
        if any(intent.id != own and intent.phase not in RESOLVED for intent in self._intents(state)):
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        if state.project_id in self.jobs.fences:
            raise BackgroundFailure(self.jobs.fences[state.project_id])

    def _gate(self, state, job, proposal):
        account = self.jobs._read_dispatch(self.jobs.background / "dispatch.json").account_generation
        if state.tombstoned or state.account_generation != account or proposal.account_generation != account:
            raise BackgroundFailure("ACCOUNT_CHANGED")
        if (proposal.authority != "active" or job.publication in {"cancelled", "discarded"}
                or proposal.execution_generation != job.execution_generation):
            raise BackgroundFailure("CANCELLED")

    def _payload(self, state, directory, proposal):
        raw = self.payload_loader(state, directory, proposal.payload)
        if (not isinstance(raw, bytes) or len(raw) != proposal.payload_bytes
                or hashlib.sha256(raw).hexdigest() != proposal.payload_sha256):
            raise BackgroundFailure("OUTCOME_UNKNOWN")
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

    def _apply(self, workspace, mutation, *, validate):
        candidate, duplicate = apply_rich_mutation(workspace, mutation)
        if duplicate:
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        if validate:
            baseline = semantic(candidate)
            self.validate(candidate)
            if semantic(candidate) != baseline:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
        candidate.updated_at = self.jobs.clock()
        return candidate

    def _candidate(self, state, directory, before, after, mutation, job, proposal, *, snapshot_id=None):
        inverse = inverse_mutation(before, after, mutation_id="inverse_" + mutation.client_mutation_id,
            session_id=mutation.capture.session_id) if job else None
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
        return CanonicalCandidateV1(schemaVersion=1, id=identity("candidate"), projectId=state.project_id,
            lineage=state.lineage, jobId=job.id if job else None, proposalId=proposal.id if proposal else None,
            proposalSha256=proposal.payload_sha256 if proposal else None, payload=proposal.payload if proposal else None,
            manualMutation=None if job else mutation, clientMutationId=mutation.client_mutation_id if mutation else snapshot_id,
            actionId=mutation.action_id if mutation else snapshot_id, sessionId=mutation.capture.session_id if mutation else "backend",
            requestSha256=mutation_sha256(mutation) if mutation else snapshot_request(snapshot_id, digest_bytes(before), digest_bytes(after)),
            beforeWorkspaceSha256=digest_bytes(before), afterWorkspaceSha256=digest_bytes(after),
            beforeHistory=previous, afterHistory=checkpoint(following), workspace=after, inverse=inverse,
            inverseGuards=inverse_guards, persistedAt=self.jobs.clock(), snapshotWrite=mutation is None)

    def _store_intent(self, state, directory, candidate, claim):
        raw = encoded(candidate.model_dump(mode="json", by_alias=True))
        folder = private_directory(directory / "canonical-candidates")
        path = folder / (candidate.id + ".json")
        fields = dict(schemaVersion=1, id="intent_" + candidate.id, projectId=state.project_id, lineage=state.lineage,
            clientMutationId=candidate.client_mutation_id, requestSha256=candidate.request_sha256,
            beforeWorkspaceSha256=candidate.before_workspace_sha256, afterWorkspaceSha256=candidate.after_workspace_sha256,
            beforeGenerationsSha256=checkpoint_sha(candidate.before_history),
            afterGenerationsSha256=checkpoint_sha(candidate.after_history), candidateRef=candidate.id,
            previousRef=candidate.id, writerEpoch=claim.epoch if claim else None,
            incarnation=claim.incarnation if claim else None, barrierGeneration=claim.generation if claim else None,
            phase="intent_stored", assetPins=[asset.id for asset in candidate.workspace.project.assets],
            candidateSha256=hashlib.sha256(raw).hexdigest())
        if candidate.job_id:
            intent = PublicationIntentV1(**fields, jobId=candidate.job_id, proposalId=candidate.proposal_id)
        else:
            intent = ManualIntentV1(**fields)
        future = state.model_copy(deep=True)
        future.history, future.generations = candidate.after_history.history, candidate.after_history.generations
        (future.intents if candidate.job_id else future.manual_intents).append(intent.model_copy(deep=True))
        states = self.jobs._all()
        self.jobs._capacity(future, states, replacing=(path, len(raw)))
        if candidate.job_id:
            future_job = job_in(future, candidate.job_id)
            future_job.receipt, future_job.publication = self._receipt_value(candidate), "saved"
            if candidate.inverse is not None:
                future.inverses.append(self._inverse_value(candidate))
        if records(future) > LIMITS.metadata_project_records or len(future.inverses) > LIMITS.inverse_project_records:
            raise BackgroundFailure("JOB_STORAGE_FULL")
        self.jobs._capacity(future, states, replacing=(path, len(raw)))
        self.jobs._capacity(state, states, replacing=(path, len(raw)))
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
        value = CanonicalCandidateV1.model_validate(strict_json(raw))
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
            actual = self._actual(self._payload(state, directory, proposal), state, job)
            if ((value.job_id, value.proposal_id, value.proposal_sha256, value.payload) !=
                    (job.id, proposal.id, proposal.payload_sha256, proposal.payload)
                    or mutation_sha256(actual) != value.request_sha256):
                raise BackgroundFailure("OUTCOME_UNKNOWN")
        else:
            expected = (snapshot_request(value.client_mutation_id, value.before_workspace_sha256, value.after_workspace_sha256)
                if value.snapshot_write else mutation_sha256(value.manual_mutation))
            if value.job_id is not None or expected != value.request_sha256:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
        for history in (value.before_history, value.after_history):
            proof = state.model_copy(deep=True)
            proof.history, proof.generations = history.history, history.generations
            self.history._ready(proof, directory, history.history.workspace_sha256)
        return value

    def publish(self, project, job_id, proposal_sha256, *, originals=None, artifacts=None, images=None):
        with self._writer(project):
            known_job = self.jobs.read(project, job_id)
            if known_job.receipt is not None:
                if known_job.receipt.proposal_sha256 != proposal_sha256:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                return known_job
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
                self._gate(state, job, proposal)
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
                try:
                    claim = self.authority.require(state, current)
                except BackgroundFailure as error:
                    if error.code != "WRITER_UNKNOWN":
                        raise
                    self._publication(job, "waiting_for_sync", "WRITER_UNKNOWN")
                    self._persist(directory, state)
                    return job
                actual = self._actual(self._payload(state, directory, proposal), state, job)
                after = self._apply(current, actual, validate=True)
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
                if self.authority.require(state, latest) != claim:
                    raise BackgroundFailure("WRITER_UNKNOWN")
                candidate = self._candidate(state, directory, current, after, actual, job, proposal)
                intent = self._store_intent(state, directory, candidate, claim)
            return self._commit(project, intent.id, candidate, prepared)

    def manual(self, project, request, *, originals=None, artifacts=None, images=None):
        with self._writer(project):
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
                    raise BackgroundFailure("OUTCOME_UNKNOWN" if known.phase != "reconciled" else "SAVE_FAILED")
                if request.client_mutation_id.startswith(("background_", "agent_", "inverse_")):
                    raise BackgroundFailure("JOB_SCOPE_INVALID")
                self._writable(state)
                self.history._ready(state, directory, digest_bytes(before))
                after = self._apply(before, request, validate=False)
            prepared = self.canonical.prepare_save(after, originals or {}, artifacts or {}, images)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                _latest, checksum = self.canonical._read_committed_unlocked(project)
                self._writable(state)
                if checksum != digest_bytes(before):
                    raise BackgroundFailure("BUSY")
                self.history._ready(state, directory, checksum)
                candidate = self._candidate(state, directory, before, after, request, None, None)
                intent = self._store_intent(state, directory, candidate, None)
            self._commit(project, intent.id, candidate, prepared)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                known = next(item for item in state.manual_intents if item.id == intent.id)
                if known.phase != "receipt_stored":
                    raise BackgroundFailure("OUTCOME_UNKNOWN")
            return after, False

    def _stage(self, state, directory, intent, phase):
        intent.phase = phase
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

    def snapshot(self, project, before_sha256, after, command_id, *, originals=None, artifacts=None, images=None):
        """A whole-snapshot writer must prove its exact base; it cannot overwrite a newer save."""
        with self._writer(project):
            self.history.open(project)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                before, checksum = self.canonical._read_committed_unlocked(project)
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
            prepared = self.canonical.prepare_save(after, originals or {}, artifacts or {}, images)
            with self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                _latest, checksum = self.canonical._read_committed_unlocked(project)
                self._writable(state)
                if checksum != before_sha256:
                    raise BackgroundFailure("DEPENDENCY_CHANGED")
                self.history._ready(state, directory, checksum)
                candidate = self._candidate(state, directory, before, after, None, None, None, snapshot_id=command_id)
                intent = self._store_intent(state, directory, candidate, None)
            self._commit(project, intent.id, candidate, prepared)
            return after, False

    def _commit(self, project, intent_id, candidate, prepared):
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
                    if candidate.job_id:
                        job, proposal = job_in(state, candidate.job_id), proposal_in(state, job_in(state, candidate.job_id))
                        self._gate(state, job, proposal)
                        self.history.validate(state, directory, before, proposal.guards)
                        claim = self.authority.require(state, before)
                        if (claim.epoch, claim.incarnation, claim.generation) != (intent.writer_epoch, intent.incarnation, intent.barrier_generation):
                            raise BackgroundFailure("WRITER_UNKNOWN")
                        self._publication(job, "committing")
                        if state.barrier is not None and claim.epoch is not None:
                            state.barrier.state = "commit_claimed"
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
                        and error.code in {"CANCELLED", "ACCOUNT_CHANGED", "WRITER_UNKNOWN", "DEPENDENCY_CHANGED"}):
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
        if candidate.job_id:
            job = job_in(state, candidate.job_id)
            job.receipt = self._receipt_value(candidate)
            self._publication(job, "saved")
            if candidate.inverse is not None and not any(item.proposal_id == candidate.proposal_id for item in state.inverses):
                state.inverses.append(self._inverse_value(candidate))
        if state.barrier is not None and state.barrier.state == "commit_claimed":
            state.barrier.state = "resolved"
        if state.writer is not None and state.writer.status == "clean_detached":
            state.writer.acknowledged_revision = candidate.workspace.project_revision
        self._stage(state, directory, intent, "receipt_stored")

    @staticmethod
    def _receipt_value(candidate):
        workspace = candidate.workspace
        return CanonicalReceiptV1(schemaVersion=1, projectId=candidate.project_id, lineage=candidate.lineage,
            jobId=candidate.job_id, proposalId=candidate.proposal_id, clientMutationId=candidate.client_mutation_id,
            requestSha256=candidate.request_sha256, proposalSha256=candidate.proposal_sha256,
            workspaceSha256=candidate.after_workspace_sha256, generationsSha256=checkpoint_sha(candidate.after_history),
            projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
            factsRevision=workspace.project.facts.revision, durable=True, persistedAt=candidate.persisted_at)

    @staticmethod
    def _inverse_value(candidate):
        raw = encoded(candidate.inverse.model_dump(mode="json", by_alias=True))
        return UndoOwnershipV1(schemaVersion=1, jobId=candidate.job_id, proposalId=candidate.proposal_id,
            owner="backend", writerEpoch=None, incarnation=None, transferId="transfer_" + candidate.id,
            inverseRef=candidate.id, inverseSha256=hashlib.sha256(raw).hexdigest(), inverseBytes=len(raw),
            expiresAt=expiration(candidate.persisted_at, LIMITS.inverse_seconds), guards=candidate.inverse_guards)

    def recover(self, project):
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
            if self.jobs.fences.get(project) == "OUTCOME_UNKNOWN":
                self.jobs.fences.pop(project, None)
            return state
