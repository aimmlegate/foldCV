"""Private background wires v1 and deferred apply v2; portable contracts stay fixed."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field, RootModel, model_validator

from ..background_limits import LIMITS
from .agent import (AgentBatchJournal, AgentCommitResult, AgentFinding, AgentId, AgentJournalRequest,
    AgentMessage, AgentReadSnapshot, AgentRun, AgentScope, AgentSnapshotDependency, AgentUsage, AgentWebSource, AgentWire,
    ModelId, Timestamp, bounded)
from .contracts import Revision, Sha256
from .rich_document import RichDocumentV1
from .rich_facts import WorkingFacts
from .rich_mutations import RichMutation
from .rich_workspace import WorkspaceV6

Execution = Literal["queued", "starting", "running", "cancelling", "completed", "failed", "cancelled", "interrupted"]
Publication = Literal["none", "ready", "waiting_for_sync", "needs_review", "committing", "saved", "no_change",
    "save_failed", "outcome_unknown", "discarded", "cancelled"]
JobKind = Literal["agent", "processing", "rewrite", "reconciliation"]
SchedulingClass = Literal["background", "interactive", "reconciliation"]
Tool = Literal["get_resume_context", "find_resume_content", "get_working_facts", "get_original_source",
    "get_conversation_context", "check_resume", "read_public_page", "publish_findings", "prepare_edit_batch", "apply_edit_batch"]
ScopeKey = Annotated[str, Field(min_length=1, max_length=512)]
Counter = Annotated[int, Field(ge=0, le=9007199254740991)]


class BackgroundWire(AgentWire):
    @model_validator(mode="before")
    @classmethod
    def literal_booleans(cls, value):
        if isinstance(value, dict):
            for key in ("durable", "proposalStored", "snapshotWrite"):
                if key in value and type(value[key]) is not bool:
                    raise ValueError("background boolean must be explicit")
        return value


class GenerationStamp(BackgroundWire):
    kind: Literal["entity", "structure", "query", "source", "rules"]
    key: ScopeKey
    generation: Counter
    fingerprint: Sha256


class ScopeGuardV1(BackgroundWire):
    schema_version: Literal[1]
    reads: list[GenerationStamp] = Field(max_length=100)
    writes: list[GenerationStamp] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_scopes(self):
        for group in (self.reads, self.writes):
            if len({(item.kind, item.key) for item in group}) != len(group):
                raise ValueError("duplicate scoped generation")
        return self


class JobIdentity(BackgroundWire):
    project_id: AgentId
    lineage: AgentId
    request_epoch: Revision
    request_id: AgentId


class InputReference(BackgroundWire):
    kind: Literal["agent_journal", "rich_sync", "processing"]
    id: AgentId
    sha256: Sha256


class JobAgentRequestV1(BackgroundWire):
    schema_version: Literal[1]
    lineage: AgentId
    request_epoch: Revision
    request: AgentJournalRequest


class JobArtifactV1(BackgroundWire):
    schema_version: Literal[1]
    id: AgentId
    identity: JobIdentity
    request: AgentJournalRequest
    request_sha256: Sha256
    connection_epoch: AgentId
    rules_sha256: Sha256
    job_id: AgentId | None
    created_at: Timestamp
    snapshots: list[AgentReadSnapshot] = Field(max_length=24)
    batches: list[AgentBatchJournal] = Field(max_length=100)
    sources: list[AgentWebSource] = Field(max_length=20)
    findings: list[AgentFinding] = Field(max_length=100)
    reply: AgentMessage | None
    usage: AgentUsage | None
    observed_guards: ScopeGuardV1 | None = None
    prepared_guards: ScopeGuardV1 | None = None

    @model_validator(mode="after")
    def owns_artifacts_only(self):
        if self.identity.request_id != self.request.client_request_id:
            raise ValueError("artifact input identity mismatch")
        resources = [*self.snapshots, *self.sources, *self.findings, *([self.reply] if self.reply else [])]
        if any(item.run_id != self.job_id for item in resources):
            raise ValueError("foreign job artifact")
        if self.job_id is None and (resources or self.batches or self.usage is not None
                or self.observed_guards is not None or self.prepared_guards is not None):
            raise ValueError("unbound input cannot have execution artifacts")
        if self.reply is not None and self.reply.role != "assistant":
            raise ValueError("the original user message belongs to the immutable request")
        if any(item.receipt is not None or item.publication is not None or item.history_actions
                or item.batch is not None and (item.batch.run_id != self.job_id or item.batch.state != "prepared") for item in self.batches):
            raise ValueError("Job alone owns publication and lifecycle")
        return self


class JobLegacyRunV2(BackgroundWire):
    schema_version: Literal[2]
    job_id: AgentId
    publication: Publication
    run: AgentRun

    @model_validator(mode="after")
    def same_job(self):
        if self.job_id != self.run.id:
            raise ValueError("legacy view must identify its Job")
        return self


class ModelCapture(BackgroundWire):
    stage: Literal["agent", "assessment", "extraction", "rewrite", "reconciliation"]
    model: ModelId
    config_sha256: Sha256


class JobSubmissionV1(BackgroundWire):
    schema_version: Literal[1]
    identity: JobIdentity
    payload_sha256: Sha256
    kind: JobKind
    scheduling_class: SchedulingClass
    input: InputReference
    models: list[ModelCapture] = Field(min_length=1, max_length=2)
    account_generation: Revision
    tools: list[Tool] = Field(max_length=10)
    allow_edits: bool
    allow_web: bool
    scope: AgentScope
    guards: ScopeGuardV1
    submitted_at: Timestamp

    @model_validator(mode="after")
    def server_capture(self):
        expected_class = {"agent": "background", "processing": "background", "rewrite": "interactive",
            "reconciliation": "reconciliation"}[self.kind]
        expected_stages = {"agent": ["agent"], "processing": ["assessment", "extraction"],
            "rewrite": ["rewrite"], "reconciliation": ["reconciliation"]}[self.kind]
        expected_input = {"agent": "agent_journal", "processing": "processing",
            "rewrite": "rich_sync", "reconciliation": "rich_sync"}[self.kind]
        if (self.scheduling_class != expected_class or [m.stage for m in self.models] != expected_stages
                or self.input.kind != expected_input or len(self.tools) != len(set(self.tools))):
            raise ValueError("invalid server-assigned job capture")
        if not self.allow_edits and (self.guards.writes or {"prepare_edit_batch", "apply_edit_batch"} & set(self.tools)):
            raise ValueError("check-only job cannot capture edit authority")
        if not self.allow_web and "read_public_page" in self.tools:
            raise ValueError("web-disabled job cannot capture page fetching")
        if self.kind != "agent" and (self.tools or not self.allow_edits or self.allow_web):
            raise ValueError("fixed jobs have no agent tools and use conditional publication")
        return self


class CanonicalReceiptV1(BackgroundWire):
    schema_version: Literal[1]
    project_id: AgentId
    lineage: AgentId
    job_id: AgentId
    proposal_id: AgentId
    client_mutation_id: AgentId
    request_sha256: Sha256
    proposal_sha256: Sha256
    workspace_sha256: Sha256
    generations_sha256: Sha256
    project_revision: Revision
    document_revision: Revision
    facts_revision: Revision
    durable: Literal[True]
    persisted_at: Timestamp


class AgentPayloadReference(BackgroundWire):
    kind: Literal["agent_journal"]
    conversation_id: AgentId
    run_id: AgentId
    batch_id: AgentId


class FixedPayloadReference(BackgroundWire):
    kind: Literal["rich_sync"]
    sync_id: AgentId


class ProcessingPayloadReference(BackgroundWire):
    kind: Literal["processing"]
    candidate_id: AgentId


PayloadReference = Annotated[Union[AgentPayloadReference, FixedPayloadReference, ProcessingPayloadReference],
    Field(discriminator="kind")]


class ProposalBindingV1(BackgroundWire):
    schema_version: Literal[1]
    id: AgentId
    job_id: AgentId
    project_id: AgentId
    lineage: AgentId
    account_generation: Revision
    execution_generation: Revision
    turn_id: AgentId
    payload: PayloadReference
    payload_sha256: Sha256
    payload_bytes: int = Field(ge=1, le=LIMITS.proposal_bytes)
    guards: ScopeGuardV1
    scope: AgentScope
    accepted_at: Timestamp
    execution_deadline: Timestamp
    authority: Literal["active", "revoked"]
    revocation: Literal["stop", "discard", "superseded", "deleted", "account_changed"] | None

    @model_validator(mode="after")
    def accepted_authority(self):
        from datetime import datetime
        if datetime.fromisoformat(self.accepted_at.replace("Z", "+00:00")) >= datetime.fromisoformat(
                self.execution_deadline.replace("Z", "+00:00")):
            raise ValueError("proposal must be durable before execution deadline")
        if (self.authority == "revoked") != (self.revocation is not None):
            raise ValueError("revoked authority needs its explicit cause")
        return self


class WriterSessionV1(BackgroundWire):
    schema_version: Literal[1]
    project_id: AgentId
    lineage: AgentId
    epoch: Revision
    session_id: AgentId
    incarnation: AgentId
    resume_credential_sha256: Sha256
    lease_expires_at: Timestamp
    status: Literal["attached", "recovering", "clean_detached", "fenced"]
    acknowledged_revision: Revision
    acknowledged_cursor: Counter
    touch_generation: Counter
    barrier_generation: Counter
    draft_id: AgentId | None

    @model_validator(mode="after")
    def clean_is_explicit(self):
        if self.status == "clean_detached" and self.draft_id is not None:
            raise ValueError("unreconciled draft is not clean detach")
        return self


class PublicationBarrierV1(BackgroundWire):
    schema_version: Literal[1]
    project_id: AgentId
    lineage: AgentId
    writer_epoch: Revision
    incarnation: AgentId
    generation: Revision
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    acknowledged_revision: Revision
    action_cursor: Counter
    touch_generation: Counter
    expires_at: Timestamp
    state: Literal["acked", "revoked", "commit_claimed", "resolved"]


class DraftCheckpointV1(BackgroundWire):
    schema_version: Literal[1]
    id: AgentId
    project_id: AgentId
    lineage: AgentId
    writer_epoch: Revision
    incarnation: AgentId
    sequence: Revision
    action_cursor: Counter
    base_revision: Revision
    base_sha256: Sha256
    payload_sha256: Sha256
    payload_bytes: int = Field(ge=1, le=LIMITS.draft_project_bytes)
    payload_ref: AgentId
    touches: list[GenerationStamp] = Field(max_length=100)
    checkpointed_at: Timestamp


class DraftPayloadV1(BackgroundWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": LIMITS.draft_project_bytes})
    schema_version: Literal[1]
    document: RichDocumentV1
    facts: WorkingFacts
    outbox: list[RichMutation] = Field(max_length=100)
    asset_pins: list[AgentId] = Field(max_length=100)

    @model_validator(mode="after")
    def payload_bound(self):
        bounded(self, LIMITS.draft_project_bytes)
        return self


class DeferredApplyV2(BackgroundWire):
    schema_version: Literal[2]
    disposition: Literal["waiting_for_sync", "needs_review"]
    job_id: AgentId
    proposal_id: AgentId
    proposal_stored: Literal[True]
    durable: Literal[False]
    reason: Literal["WRITER_DIRTY", "WRITER_UNKNOWN", "BARRIER_EXPIRED", "DEPENDENCY_CHANGED",
        "ACCOUNT_CHANGED", "DURABILITY_UNKNOWN"]


class SavedApplyV2(BackgroundWire):
    schema_version: Literal[2]
    disposition: Literal["saved"]
    job_id: AgentId
    proposal_id: AgentId
    proposal_stored: Literal[True]
    durable: Literal[True]
    result: AgentCommitResult

    @model_validator(mode="after")
    def exact_receipt(self):
        if not self.result.receipt.durable:
            raise ValueError("saved tool result needs an exact canonical receipt")
        return self


class ApplyResultV2(RootModel[Annotated[Union[DeferredApplyV2, SavedApplyV2], Field(discriminator="disposition")]]):
    pass


class JobFailure(BackgroundWire):
    code: Literal["AUTH_REQUIRED", "RATE_LIMITED", "BUSY", "MODEL_DENIED", "CANCELLED", "DEADLINE",
        "STARTUP_TIMEOUT", "PROCESS_FAILED", "CLEANUP_FAILED", "INTERRUPTED", "PROTOCOL",
        "JOB_QUEUE_FULL", "JOB_STORAGE_FULL", "JOB_IDEMPOTENCY_CONFLICT", "REQUEST_EXPIRED",
        "JOB_NOT_FOUND", "JOB_STORE_CORRUPT", "JOB_STORE_UNAVAILABLE", "JOB_DISABLED", "JOB_SCOPE_INVALID", "ACCOUNT_CHANGED",
        "DEPENDENCY_CHANGED", "WRITER_UNKNOWN", "SAVE_FAILED", "OUTCOME_UNKNOWN", "PROJECT_DELETED"]


class JobAttemptV1(BackgroundWire):
    schema_version: Literal[1]
    id: AgentId
    stage: Literal["agent", "assessment", "extraction", "rewrite", "reconciliation"]
    execution_generation: Revision
    state: Literal["reserved", "starting", "running", "completed", "failed", "cancelled", "interrupted", "cleanup_failed"]
    dispatched_at: Timestamp
    startup_deadline: Timestamp
    active_deadline: Timestamp
    native_started: bool
    child_started_at: Timestamp | None
    cleanup_verified: bool
    error: JobFailure | None

    @model_validator(mode="after")
    def process_proof(self):
        if self.native_started != (self.child_started_at is not None):
            raise ValueError("native start needs its actual child marker")
        if self.cleanup_verified and self.state in {"reserved", "starting", "running", "cleanup_failed"}:
            raise ValueError("cleanup proof cannot coexist with live or unverified ownership")
        return self


class JobSnapshotV1(BackgroundWire):
    schema_version: Literal[1]
    id: AgentId
    submission: JobSubmissionV1
    execution: Execution
    publication: Publication
    execution_generation: Revision
    attempts: list[JobAttemptV1] = Field(max_length=2)
    event_cursor: Counter
    proposal_id: AgentId | None
    receipt: CanonicalReceiptV1 | None
    error: JobFailure | None
    created_at: Timestamp
    updated_at: Timestamp
    publication_error: JobFailure | None = None

    @model_validator(mode="after")
    def exact_saved(self):
        if self.publication in {"saved", "no_change", "none"} and self.publication_error is not None:
            raise ValueError("publication error cannot claim a successful or absent publication")
        if len({a.id for a in self.attempts}) != len(self.attempts) or len(self.attempts) > len(self.submission.models):
            raise ValueError("an attempt cannot start twice or hide a retry")
        for index, attempt in enumerate(self.attempts):
            if attempt.stage != self.submission.models[index].stage or attempt.execution_generation != self.execution_generation:
                raise ValueError("attempt must match its captured stage and execution generation")
        if (self.publication == "saved") != (self.receipt is not None):
            raise ValueError("only saved has a canonical receipt")
        if self.receipt is not None and (self.receipt.job_id != self.id or
                self.receipt.project_id != self.submission.identity.project_id or
                self.receipt.lineage != self.submission.identity.lineage or self.receipt.proposal_id != self.proposal_id):
            raise ValueError("receipt must belong to this job and proposal")
        if self.publication not in {"none", "no_change", "cancelled"} and self.proposal_id is None:
            raise ValueError("publication state needs a bound proposal")
        if not self.submission.allow_edits and self.publication != "none":
            raise ValueError("check-only job has no publication")
        return self


class JobEventV1(BackgroundWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": LIMITS.replay_bytes})
    schema_version: Literal[1]
    project_id: AgentId
    lineage: AgentId
    job_id: AgentId
    generation: Revision
    cursor: Revision
    type: Literal["job.snapshot", "cursor.gap"]
    snapshot: JobSnapshotV1

    @model_validator(mode="after")
    def exact_event(self):
        if (self.snapshot.id != self.job_id or self.snapshot.submission.identity.project_id != self.project_id
                or self.snapshot.submission.identity.lineage != self.lineage or self.snapshot.event_cursor != self.cursor
                or self.snapshot.execution_generation != self.generation):
            raise ValueError("event identity must match its snapshot")
        bounded(self, LIMITS.replay_bytes)
        return self


class JobReplayRequestV1(BackgroundWire):
    schema_version: Literal[1]
    generation: Revision
    after: Counter


class JobReplayV1(BackgroundWire):
    schema_version: Literal[1]
    events: list[JobEventV1] = Field(max_length=LIMITS.replay_events)

    @model_validator(mode="after")
    def ordered_one_job(self):
        cursors = [event.cursor for event in self.events]
        if cursors != sorted(set(cursors)):
            raise ValueError("replay must be ordered without duplicates")
        if self.events:
            first = self.events[0]
            if any((event.project_id, event.lineage, event.job_id, event.generation) !=
                    (first.project_id, first.lineage, first.job_id, first.generation) for event in self.events):
                raise ValueError("replay cannot mix jobs")
            if len(self.events) > 1 and any(event.type == "cursor.gap" for event in self.events):
                raise ValueError("a gap is one current snapshot")
        return self


class JobProjectV1(BackgroundWire):
    schema_version: Literal[1]
    project_id: AgentId
    lineage: AgentId
    request_epoch: Revision
    jobs: list[JobSnapshotV1] = Field(max_length=LIMITS.metadata_project_records)

    @model_validator(mode="after")
    def same_project(self):
        if len({job.id for job in self.jobs}) != len(self.jobs) or any(
                job.submission.identity.project_id != self.project_id or job.submission.identity.lineage != self.lineage for job in self.jobs):
            raise ValueError("project view cannot mix or duplicate jobs")
        return self


class CanonicalIntentV1(BackgroundWire):
    schema_version: Literal[1]
    id: AgentId
    project_id: AgentId
    lineage: AgentId
    client_mutation_id: AgentId
    request_sha256: Sha256
    before_workspace_sha256: Sha256
    after_workspace_sha256: Sha256
    after_generations_sha256: Sha256
    candidate_ref: AgentId
    previous_ref: AgentId
    writer_epoch: Revision | None
    incarnation: AgentId | None
    barrier_generation: Revision | None
    phase: Literal["intent_stored", "commit_claimed", "workspace_replaced", "workspace_durable",
        "generation_history_durable", "receipt_stored", "fenced", "reconciled"]
    asset_pins: list[AgentId] = Field(max_length=100)
    candidate_sha256: Sha256 | None = None
    before_generations_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def complete_writer_binding(self):
        parts = (self.writer_epoch, self.incarnation, self.barrier_generation)
        if any(p is None for p in parts) and not all(p is None for p in parts):
            raise ValueError("intent needs the whole writer binding or a proved clean detach")
        return self


class PublicationIntentV1(CanonicalIntentV1):
    job_id: AgentId
    proposal_id: AgentId


class ManualIntentV1(CanonicalIntentV1):
    pass


class UndoOwnershipV1(BackgroundWire):
    schema_version: Literal[1]
    job_id: AgentId
    proposal_id: AgentId
    owner: Literal["session", "backend", "transferring", "expired"]
    writer_epoch: Revision | None
    incarnation: AgentId | None
    transfer_id: AgentId
    inverse_ref: AgentId
    inverse_sha256: Sha256
    inverse_bytes: int = Field(ge=1, le=LIMITS.inverse_bytes)
    expires_at: Timestamp
    guards: ScopeGuardV1

    @model_validator(mode="after")
    def single_owner(self):
        if (self.writer_epoch is None) != (self.incarnation is None):
            raise ValueError("inverse writer binding must be complete")
        if self.owner == "session" and self.writer_epoch is None:
            raise ValueError("session inverse needs its acknowledged writer")
        if self.owner in {"backend", "expired"} and self.writer_epoch is not None:
            raise ValueError("headless inverse cannot also have a session owner")
        return self


class RequestReplayV1(BackgroundWire):
    identity: JobIdentity
    payload_sha256: Sha256
    job_id: AgentId
    expires_at: Timestamp
    archived_result: JobSnapshotV1 | None


class HistoryDefinitionV1(BackgroundWire):
    key: ScopeKey
    selector: AgentSnapshotDependency


class BackgroundHistoryV1(BackgroundWire):
    schema_version: Literal[1]
    namespace: AgentId
    phase: Literal["initializing", "ready", "fenced"]
    workspace_sha256: Sha256
    definitions: list[HistoryDefinitionV1] = Field(max_length=LIMITS.metadata_project_records)

    @model_validator(mode="after")
    def unique_definitions(self):
        if len({definition.key for definition in self.definitions}) != len(self.definitions):
            raise ValueError("duplicate history definition")
        return self


class HistoryCheckpointV1(BackgroundWire):
    history: BackgroundHistoryV1
    generations: list[GenerationStamp] = Field(max_length=LIMITS.metadata_project_records)


class CanonicalCandidateV1(BackgroundWire):
    schema_version: Literal[1]
    id: AgentId
    project_id: AgentId
    lineage: AgentId
    job_id: AgentId | None
    proposal_id: AgentId | None
    proposal_sha256: Sha256 | None
    payload: PayloadReference | None
    manual_mutation: RichMutation | None
    client_mutation_id: AgentId
    action_id: AgentId
    session_id: AgentId
    request_sha256: Sha256
    before_workspace_sha256: Sha256
    after_workspace_sha256: Sha256
    before_history: HistoryCheckpointV1
    after_history: HistoryCheckpointV1
    workspace: WorkspaceV6
    inverse: RichMutation | None
    inverse_guards: ScopeGuardV1
    persisted_at: Timestamp
    snapshot_write: bool = False

    @model_validator(mode="after")
    def exact_candidate(self):
        job_fields = (self.job_id, self.proposal_id, self.proposal_sha256, self.payload)
        if any(part is None for part in job_fields) and not all(part is None for part in job_fields):
            raise ValueError("candidate needs complete proposal identity")
        if (self.job_id is None) != (self.manual_mutation is not None or self.snapshot_write):
            raise ValueError("a job candidate references its original payload exactly once")
        if self.snapshot_write and self.manual_mutation is not None:
            raise ValueError("a snapshot write cannot also execute a mutation")
        if self.workspace.project_id != self.project_id:
            raise ValueError("candidate workspace belongs to another project")
        return self


class BackgroundSidecarV1(BackgroundWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": LIMITS.sidecar_project_bytes,
        "x-maxMetadataRecords": LIMITS.metadata_project_records})
    schema_version: Literal[1]
    project_id: AgentId
    lineage: AgentId
    account_generation: Revision
    active_request_epoch: Revision
    expired_through_epoch: Counter
    request_epoch_expires_at: Timestamp
    tombstoned: bool
    jobs: list[JobSnapshotV1] = Field(max_length=LIMITS.metadata_project_records)
    requests: list[RequestReplayV1] = Field(max_length=LIMITS.metadata_project_records)
    proposals: list[ProposalBindingV1] = Field(max_length=LIMITS.metadata_project_records)
    writer: WriterSessionV1 | None
    barrier: PublicationBarrierV1 | None
    drafts: list[DraftCheckpointV1] = Field(max_length=LIMITS.metadata_project_records)
    generations: list[GenerationStamp] = Field(max_length=LIMITS.metadata_project_records)
    intents: list[PublicationIntentV1] = Field(max_length=LIMITS.metadata_project_records)
    inverses: list[UndoOwnershipV1] = Field(max_length=LIMITS.inverse_project_records)
    history: BackgroundHistoryV1 | None = None
    manual_intents: list[ManualIntentV1] = Field(default_factory=list, max_length=LIMITS.metadata_project_records)

    @model_validator(mode="after")
    def bounded_authority(self):
        groups = (self.jobs, self.requests, self.proposals, self.drafts, self.generations, self.intents, self.inverses,
            self.manual_intents)
        if self.active_request_epoch <= self.expired_through_epoch:
            raise ValueError("active request epoch must be above the durable expired floor")
        if (sum(map(len, groups)) + int(self.writer is not None) + int(self.barrier is not None)
                + (1 + len(self.history.definitions) if self.history is not None else 0) > LIMITS.metadata_project_records):
            raise ValueError("background metadata capacity exhausted")
        for item in [*self.jobs, *self.requests, *self.proposals, *self.drafts, *self.intents, *self.manual_intents,
                *([self.writer] if self.writer else []), *([self.barrier] if self.barrier else [])]:
            identity = item.submission.identity if isinstance(item, JobSnapshotV1) else item.identity if isinstance(item, RequestReplayV1) else item
            if identity.project_id != self.project_id or identity.lineage != self.lineage:
                raise ValueError("sidecar cannot contain foreign project authority")
        request_keys = [(r.identity.request_epoch, r.identity.request_id) for r in self.requests]
        if len(set(request_keys)) != len(request_keys) or len({j.id for j in self.jobs}) != len(self.jobs):
            raise ValueError("duplicate job or request authority")
        for job in self.jobs:
            request = next((r for r in self.requests if r.job_id == job.id), None)
            if request is None or request.archived_result is not None or request.identity != job.submission.identity or request.payload_sha256 != job.submission.payload_sha256:
                raise ValueError("live job needs its single exact request binding")
        for request in self.requests:
            archived = request.archived_result
            if archived is not None and (archived.id != request.job_id or archived.submission.identity != request.identity
                    or archived.submission.payload_sha256 != request.payload_sha256 or archived.execution not in {"completed", "failed", "cancelled", "interrupted"}
                    or archived.publication not in {"none", "saved", "no_change", "discarded", "cancelled"}):
                raise ValueError("only a terminal resolved reply may replace a pruned job")
        bounded(self, LIMITS.sidecar_project_bytes)
        return self


class DispatchStateV1(BackgroundWire):
    schema_version: Literal[1]
    account_generation: Revision
    paused: Literal["RATE_LIMITED", "AUTH_REQUIRED"] | None


BACKGROUND_CONTRACTS = {"background_submission_v1": JobSubmissionV1, "background_snapshot_v1": JobSnapshotV1,
    "background_proposal_v1": ProposalBindingV1, "background_scope_guard_v1": ScopeGuardV1,
    "background_writer_v1": WriterSessionV1, "background_barrier_v1": PublicationBarrierV1,
    "background_draft_v1": DraftCheckpointV1, "background_receipt_v1": CanonicalReceiptV1,
    "background_apply_v2": ApplyResultV2, "background_event_v1": JobEventV1,
    "background_intent_v1": PublicationIntentV1, "background_undo_v1": UndoOwnershipV1,
    "background_sidecar_v1": BackgroundSidecarV1, "background_attempt_v1": JobAttemptV1,
    "background_draft_payload_v1": DraftPayloadV1, "background_dispatch_v1": DispatchStateV1,
    "background_agent_request_v1": JobAgentRequestV1, "background_artifact_v1": JobArtifactV1,
    "background_legacy_run_v2": JobLegacyRunV2, "background_project_v1": JobProjectV1,
    "background_replay_request_v1": JobReplayRequestV1, "background_replay_v1": JobReplayV1}
