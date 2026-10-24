"""Captured template imports retain every proposal, reservation and outcome."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from ..project_limits import FINALIZATION_BASE_SECONDS, FINALIZATION_CEILING_SECONDS, IMPORT_MINUTES
from .contracts import Id, PartialDate, Revision, Sha256, Wire, _unique
from .template_facts import CapturedItemIdentity, ExtensionCell, HandleAllocation, Lineage, Relation, SourceSpan
from ..templates.models import Check, JsonObject


class Discovery(Wire):
    key: Id
    semantic_type: Id
    pointer: str


class DiscoverySelector(Wire):
    kind: Literal["discovery_key"]
    key: Id


class HandleSelector(Wire):
    kind: Literal["handle"]
    item_handle: Id


ItemSelector = Annotated[DiscoverySelector | HandleSelector,Field(discriminator="kind")]


class RelationDiscoverySelector(Wire):
    kind: Literal["discovery_key"]
    key: Id


class ExistingRelationSelector(Wire):
    kind: Literal["relation_id"]
    relation_id: Id


RelationSelector = Annotated[RelationDiscoverySelector | ExistingRelationSelector, Field(discriminator='kind')]


class ProposalRelation(Wire):
    relation: RelationSelector
    kind: Literal["owned_by", "extension_of", "related_to"]
    subject: ItemSelector
    target: ItemSelector
    evidence: list[SourceSpan]


class ProposalField(Wire):
    item: ItemSelector
    field_key: Id
    pointer: str
    evidence: list[SourceSpan]
    effective_cell_ids: list[Id]


class FieldSidecar(Wire):
    item_handle: Id
    field_key: Id
    pointer: str
    evidence: list[SourceSpan]
    effective_cell_ids: list[Id]


class ProposalLineage(Wire):
    kind: Literal["add", "split", "merge"]
    parents: list[Id]
    children: list[Id]

    @model_validator(mode="after")
    def cardinality(self):
        _unique(self.parents,"lineage parent"); _unique(self.children,"lineage child")
        if (self.kind == "add" and (self.parents or not self.children)
            or self.kind == "split" and (len(self.parents)!=1 or len(self.children)<2)
            or self.kind == "merge" and (len(self.parents)<2 or len(self.children)!=1)):
            raise ValueError("invalid discovery lineage cardinality")
        return self


class ProposalReply(Wire):
    schema_version: Literal[1]
    payload: JsonValue
    discoveries: list[Discovery]
    fields: list[ProposalField]
    lineage: list[ProposalLineage]
    relations: list[ProposalRelation] = Field(default_factory=list, exclude_if=lambda value: not value)


# A provider reply selects request-local choices; the coordinator restores the captured identities (plan 3.3).
EvidenceRef = Annotated[str, Field(min_length=1, json_schema_extra={'x-reference': 'EvidenceRef'})]
CheckRef = Annotated[str, Field(min_length=1, json_schema_extra={'x-reference': 'CheckRef'})]
ItemRef = Annotated[str, Field(min_length=1, json_schema_extra={'x-reference': 'ItemRef'})]
CellRef = Annotated[str, Field(min_length=1, json_schema_extra={'x-reference': 'CellRef'})]
RelationRef = Annotated[str, Field(min_length=1, json_schema_extra={'x-reference': 'RelationRef'})]


class EvidenceOption(Wire):
    ref: Id
    span: SourceSpan
    text: str


class ItemReference(Wire):
    ref: Id
    item_handle: Id
    semantic_type: Id
    key: Id | None


class CellReference(Wire):
    ref: Id
    cell_id: Id
    field_key: Id
    text: str


class RelationReference(Wire):
    ref: Id
    relation_id: Id
    kind: Literal["owned_by", "extension_of", "related_to"]
    subject: str
    target: str


class ReferenceTable(Wire):
    items: list[ItemReference]
    cells: list[CellReference]
    relations: list[RelationReference]

    @model_validator(mode="after")
    def distinct(self):
        _unique([value.ref for value in [*self.items, *self.cells, *self.relations]], "offered reference")
        _unique([value.item_handle for value in self.items], "offered item")
        _unique([value.cell_id for value in self.cells], "offered cell")
        _unique([value.relation_id for value in self.relations], "offered relation")
        return self


class HandleChoice(Wire):
    kind: Literal["handle"]
    ref: ItemRef


ItemChoice = Annotated[DiscoverySelector | HandleChoice, Field(discriminator="kind")]


class NewRelationKey(Wire):
    kind: Literal["new"]
    key: Id


class RelationChoice(Wire):
    kind: Literal["relation"]
    ref: RelationRef


RelationChoiceSelector = Annotated[NewRelationKey | RelationChoice, Field(discriminator="kind")]


class ReferencedField(Wire):
    item: ItemChoice
    field_key: Id
    pointer: str
    evidence: list[EvidenceRef]
    effective_cells: list[CellRef]


class ReferencedRelation(Wire):
    relation: RelationChoiceSelector
    kind: Literal["owned_by", "extension_of", "related_to"]
    subject: ItemChoice
    target: ItemChoice
    evidence: list[EvidenceRef]


class ReferencedLineage(Wire):
    kind: Literal["add", "split", "merge"]
    parents: list[ItemRef]
    children: list[Id]


class ReferencedProposalReply(Wire):
    schema_version: Literal[3]
    payload: JsonValue
    discoveries: list[Discovery]
    fields: list[ReferencedField]
    lineage: list[ReferencedLineage]
    relations: list[ReferencedRelation]


class CheckTarget(Wire):
    rule_id: Id
    target_id: Id


class ModelCapture(Wire):
    adapter: Id
    model: Id
    effort: Id
    capability_profile: Id
    capability_version: Id
    configuration_hash: Sha256


class ReviewInput(Wire):
    schema_version: Literal[1, 2]
    protocol: Literal["template_import_v1"]
    proposal_hash: Sha256
    targets: list[CheckTarget]
    handle_map: list[HandleAllocation | CapturedItemIdentity]
    rules: list[Check]
    source_spans: list[SourceSpan]
    source_texts: dict[str,str]
    effective_cells: list[ExtensionCell]
    relations: list[Relation]
    package_hash: Sha256
    allow_text_rewrite: bool
    semantic_context: JsonObject
    policy: ModelCapture
    occurrence_context: JsonValue
    occurrence_independent: bool
    # Version 2 offers evidence by reference; version 1 keeps its digest-keyed spans and texts.
    evidence: list[EvidenceOption] = Field(default_factory=list, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def evidence_form(self):
        if self.schema_version == 1 and self.evidence or self.schema_version == 2 and (self.source_spans or self.source_texts):
            raise ValueError("review evidence form differs from its schema version")
        _unique([value.ref for value in self.evidence], "review evidence reference")
        _unique([value.span.model_dump_json() for value in self.evidence], "review evidence span")
        return self


class ReviewDisposition(Wire):
    rule_id: Id
    target_id: Id
    disposition: Literal["satisfied", "violation", "uncertain"]
    reason: str
    evidence: list[SourceSpan]
    actionable: bool


class ReviewReply(Wire):
    results: list[ReviewDisposition]


class ReferencedDisposition(Wire):
    check: CheckRef
    disposition: Literal["satisfied", "violation", "uncertain"]
    reason: str
    evidence: list[EvidenceRef]
    actionable: bool


class ReferencedReviewReply(Wire):
    results: list[ReferencedDisposition]


class ReviewReceipt(Wire):
    id: Id
    review_input_hash: Sha256
    expected_checks: list[CheckTarget]
    reply: ReviewReply
    attempt_id: Id
    completed_at: str


class ImportIssue(Wire):
    id: Id
    rule_id: Id | None
    task_id: Id
    target_ids: list[Id]
    block_ids: list[Id]
    category: Literal["content_violation", "uncertain_interpretation", "check_not_completed"]
    code: Id
    message: str
    imported_fingerprint: Sha256
    review_input_hash: Sha256 | None
    lifecycle_id: Id
    state: Literal["active", "retired"]
    retired_by_action: Id | None

    @model_validator(mode="after")
    def lifecycle(self):
        if (self.state == "retired") != (self.retired_by_action is not None):
            raise ValueError("retired issue requires its authoring action")
        return self


class RuntimePolicy(Wire):
    call_cap: int = Field(gt=0)
    concurrency: Literal[1]
    # Captured from Settings at the start; operations captured at 300 s and 30 s stay valid.
    processing_seconds: int = Field(ge=IMPORT_MINUTES[1] * 60, le=IMPORT_MINUTES[2] * 60)
    cleanup_seconds: Literal[5]
    finalization_seconds: int = Field(ge=FINALIZATION_BASE_SECONDS, le=FINALIZATION_CEILING_SECONDS)
    primary_repairs: Literal[1]
    fallback_repairs: Literal[1]


class ImportCapture(Wire):
    package_hash: Sha256
    source_hashes: dict[str,Sha256]
    fact_revisions: dict[str,Revision]
    authority_hash: Sha256
    dependency_hash: Sha256
    allow_text_rewrite: bool
    primary: ModelCapture
    fallback: ModelCapture | None
    formatting_as_of: PartialDate
    policy: RuntimePolicy


class StartTemplateImportV1(Wire):
    kind: Literal["start_new_import"]
    protocol: Literal["template_import_v1"]
    client_request_id: Id
    capture: ImportCapture


class ResumeTemplateImportV1(Wire):
    kind: Literal["resume_import"]
    protocol: Literal["template_import_v1"]
    operation_id: Id
    authorization_id: Id
    authority_hash: Sha256


class ImportAuthorization(Wire):
    id: Id
    kind: Literal["start", "resume"]
    state: Literal["active", "cancelled"]
    authorized_at: str
    authority_hash: Sha256
    dependency_hash: Sha256


class TaskInputRecord(Wire):
    id: Id
    task_id: Id
    input_hash: Sha256
    value: JsonObject
    captured_at: str


class TaskResultRecord(Wire):
    id: Id
    task_id: Id
    input_hash: Sha256
    value: JsonValue
    source_spans: list[SourceSpan]
    item_handles: list[Id]
    issue_ids: list[Id]
    disposition: Literal['admitted', 'derived', 'source_fallback', 'empty']


class ImportTask(Wire):
    id: Id
    operation_id: Id
    block_id: Id
    kind: Literal["extract", "rewrite", "derive", "source_copy"]
    dependencies: list[Id]
    input_hash: Sha256
    allowed_handles: list[Id]
    expected_checks: list[CheckTarget]
    state: Literal["pending", "running", "proposed", "checking", "repairing", "accepted", "empty",
                   "source_fallback", "cancelled", "technical_failure"]
    attempt_ids: list[Id]
    proposal_hash: Sha256 | None
    receipt_ids: list[Id]
    issue_ids: list[Id]


class LaunchOwner(Wire):
    reservation_id: Id
    incarnation_id: Id
    generation: int = Field(gt=0)
    lease_id: Id
    process_start_witness: str | None
    transport_session_id: Id | None
    transport_turn_id: Id | None
    pid: int | None = Field(gt=0)


class ObservedUsage(Wire):
    input_tokens: int | None = Field(ge=0)
    cached_input_tokens: int | None = Field(ge=0)
    output_tokens: int | None = Field(ge=0)
    complete: bool


class CleanupOutcome(Wire):
    state: Literal["pending", "verified", "unknown"]
    evidence_hash: Sha256 | None
    witness: str | None

    @model_validator(mode="after")
    def proof(self):
        if self.state == "verified" and (self.evidence_hash is None or self.witness is None):
            raise ValueError("verified cleanup requires retained ownership evidence")
        return self


class ImportAttempt(Wire):
    id: Id
    operation_id: Id
    task_id: Id
    slot: Literal["initial", "review", "primary_repair", "fallback_repair", "replacement_review"]
    input_hash: Sha256
    model: ModelCapture
    state: Literal["reserved", "dispatch_started", "returned", "outcome_unknown", "reconciled", "released"]
    owner: LaunchOwner
    reserved_at: str
    dispatched_at: str | None
    return_hash: Sha256 | None
    usage: ObservedUsage
    cleanup: CleanupOutcome
    proposal_record_id: Id | None
    review_input_record_id: Id | None
    review_receipt_id: Id | None
    raw_return: str | None
    raw_return_hash: Sha256 | None
    outcome: Literal["completed", "invalid_payload", "refused", "incomplete", "timed_out", "cancelled",
                     "transport_failure", "cleanup_failure"] | None = Field(default=None, exclude_if=lambda value: value is None)
    error_code: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    request_value: JsonObject | None = Field(default=None, exclude_if=lambda value: value is None)
    authorization_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    returned_at: str | None = Field(default=None, exclude_if=lambda value: value is None)


class AttemptCleanupRecord(Wire):
    attempt_id: Id
    owner_hash: Sha256
    evidence_hash: Sha256
    witness: str
    never_dispatched: bool
    verified_at: str


class RelationAllocation(Wire):
    operation_id: Id
    task_id: Id
    discovery_attempt_id: Id
    key: Id
    relation_id: Id
    kind: Literal["owned_by", "extension_of", "related_to"]
    subject_id: Id
    target_id: Id


class ProposalRecord(Wire):
    id: Id
    attempt_id: Id
    input_hash: Sha256
    raw_return: str
    raw_return_hash: Sha256
    reply: ProposalReply | None
    resolved_fields: list[FieldSidecar]
    lineage: list[Lineage]
    state: Literal["invalid", "provisional", "accepted", "rejected"]
    errors: list[str]
    proposal_hash: Sha256
    resolved_relations: list[Relation] = Field(default_factory=list, exclude_if=lambda value: not value)
    applied_receipt_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    admitted_cell_ids: list[Id] = Field(default_factory=list, exclude_if=lambda value: not value)
    admitted_relation_ids: list[Id] = Field(default_factory=list, exclude_if=lambda value: not value)
    admitted_record_revisions: dict[str, Revision] = Field(default_factory=dict, exclude_if=lambda value: not value)
    admitted_relation_revisions: dict[str, Revision] = Field(default_factory=dict, exclude_if=lambda value: not value)


class ReviewInputRecord(Wire):
    id: Id
    attempt_id: Id
    input_hash: Sha256
    value: ReviewInput


class FinalizationCandidate(Wire):
    id: Id
    operation_id: Id
    authorization_id: Id
    source_hash: Sha256
    dependency_hash: Sha256
    authority_hash: Sha256
    package_hash: Sha256
    document_hash: Sha256
    facts_hash: Sha256
    issues_hash: Sha256
    coverage_hash: Sha256
    candidate_hash: Sha256
    started_at: str
    expires_at: str


class PublicationOutcome(Wire):
    state: Literal["pending", "saved", "failed_before_replacement", "outcome_unknown", "cancelled"]
    intent_id: Id | None
    workspace_hash: Sha256 | None
    error_code: Id | None


class ExportAttempt(Wire):
    id: Id
    state: Literal["pending", "running", "completed", "failed"]
    document_hash: Sha256
    facts_hash: Sha256
    presentation_hash: Sha256
    package_hash: Sha256
    assets_hash: Sha256
    renderer_hash: Sha256
    artifact_hash: Sha256 | None
    error_code: Id | None
    publication_intent_id: Id | None


class ImportOperation(Wire):
    schema_version: Literal[1]
    id: Id
    project_id: Id
    capture: ImportCapture
    state: Literal["captured", "processing", "cleanup_pending", "finalizing", "published", "cancelled", "failed", "fenced"]
    admitted_at: str | None
    expires_at: str | None
    last_observed_at: str | None
    tasks: list[ImportTask]
    allocations: list[HandleAllocation]
    attempts: list[ImportAttempt]
    proposals: list[ProposalRecord]
    review_inputs: list[ReviewInputRecord]
    receipts: list[ReviewReceipt]
    finalization: FinalizationCandidate | None
    publication: PublicationOutcome
    export_attempts: list[ExportAttempt]
    client_request_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    authorizations: list[ImportAuthorization] = Field(default_factory=list, exclude_if=lambda value: not value)
    task_inputs: list[TaskInputRecord] = Field(default_factory=list, exclude_if=lambda value: not value)
    cleanup_records: list[AttemptCleanupRecord] = Field(default_factory=list, exclude_if=lambda value: not value)
    relation_allocations: list[RelationAllocation] = Field(default_factory=list, exclude_if=lambda value: not value)
    inference_closed: bool = Field(default=False, exclude_if=lambda value: not value)
    finalization_history: list[FinalizationCandidate] = Field(default_factory=list, exclude_if=lambda value: not value)
    task_results: list[TaskResultRecord] = Field(default_factory=list, exclude_if=lambda value: not value)
    issues: list[ImportIssue] = Field(default_factory=list, exclude_if=lambda value: not value)
    captured_relation_revisions: dict[str, Revision] = Field(default_factory=dict, exclude_if=lambda value: not value)
    captured_items: list[CapturedItemIdentity] = Field(default_factory=list, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def identity(self):
        from ..template_capture import item_identities
        item_identities(self)
        if any(self.capture.fact_revisions.get(value.record_id) != value.record_revision for value in self.captured_items):
            raise ValueError('captured item revision differs from immutable fact capture')
        for name in ("tasks","attempts","proposals","review_inputs","receipts","export_attempts"):
            _unique([value.id for value in getattr(self,name)],"import "+name)
        tasks={t.id for t in self.tasks};attempts={a.id for a in self.attempts}
        for task in self.tasks:
            if task.operation_id != self.id or not set(task.dependencies)<=tasks or not set(task.attempt_ids)<=attempts:
                raise ValueError("task/operation identity mismatch")
        for attempt in self.attempts:
            if attempt.operation_id != self.id or attempt.task_id not in tasks:
                raise ValueError("attempt/operation identity mismatch")
        for proposal in self.proposals:
            if proposal.attempt_id not in attempts: raise ValueError("proposal has no retained attempt")
        _unique([value.id for value in self.authorizations], 'import authorization')
        _unique([value.task_id for value in self.task_inputs], 'captured task input')
        for value in self.task_inputs:
            if value.task_id not in tasks:
                raise ValueError('captured input has no task')
        for value in self.cleanup_records:
            if value.attempt_id not in attempts:
                raise ValueError('cleanup proof has no attempt')
        _unique([value.id for value in self.task_results], 'task result')
        _unique([value.task_id for value in self.task_results], 'task result owner')
        _unique([value.id for value in self.issues], 'operation issue')
        for value in self.task_results:
            if value.task_id not in tasks or value.input_hash != next(task.input_hash for task in self.tasks if task.id == value.task_id):
                raise ValueError('task result has no matching captured input')
        _unique([value.id for value in self.task_inputs], 'task input')
        _unique([value.attempt_id for value in self.cleanup_records], 'attempt cleanup')
        _unique([value.attempt_id for value in self.review_inputs], 'attempt review input')
        _unique([(value.task_id, value.discovery_attempt_id, value.key) for value in self.relation_allocations], 'relation allocation')
        _unique([value.relation_id for value in self.relation_allocations], 'allocated relation')
        if self.authorizations:
            from ..templates.compiler import canonical, sha256
            by_attempt = {value.id: value for value in self.attempts}
            by_receipt = {value.id: value for value in self.receipts}
            by_input = {value.attempt_id: value for value in self.review_inputs}
            authorities = {value.id: value for value in self.authorizations}
            if any(value.authority_hash != self.capture.authority_hash or value.dependency_hash != self.capture.dependency_hash
                    for value in self.authorizations):
                raise ValueError('authorization changes immutable capture')
            if sum(value.state != 'released' for value in self.attempts) > self.capture.policy.call_cap:
                raise ValueError('operation exceeds its captured call cap')
            for task in self.tasks:
                _unique(task.attempt_ids, 'task attempt')
                _unique(task.receipt_ids, 'task receipt')
                _unique([(target.rule_id, target.target_id) for target in task.expected_checks], 'task check target')
                if (set(task.attempt_ids) != {value.id for value in self.attempts if value.task_id == task.id}
                        or not set(task.receipt_ids) <= by_receipt.keys()):
                    raise ValueError('task attempt or receipt ownership mismatch')
            for value in self.task_inputs:
                if value.input_hash != sha256(canonical(value.value)) or value.input_hash != next(
                        task.input_hash for task in self.tasks if task.id == value.task_id):
                    raise ValueError('captured task input hash mismatch')
            for value in self.attempts:
                if value.authorization_id not in authorities or (value.request_value is not None
                        and value.input_hash != sha256(canonical(value.request_value))):
                    raise ValueError('attempt input or authorization mismatch')
                checksum = sha256(value.raw_return.encode()) if value.raw_return is not None else None
                if checksum != value.raw_return_hash or value.return_hash != value.raw_return_hash:
                    raise ValueError('attempt raw return hash mismatch')
            for value in self.review_inputs:
                attempt = by_attempt.get(value.attempt_id)
                if (attempt is None or value.input_hash != sha256(canonical(value.value))
                        or attempt.input_hash != value.input_hash or attempt.review_input_record_id != value.id):
                    raise ValueError('review input has no matching attempt')
            for receipt in self.receipts:
                record = by_input.get(receipt.attempt_id)
                attempt = by_attempt.get(receipt.attempt_id)
                if (record is None or receipt.review_input_hash != record.input_hash or receipt.expected_checks != record.value.targets
                        or attempt.review_receipt_id != receipt.id):
                    raise ValueError('review receipt has no matching input and attempt')
            for value in self.proposals:
                attempt = by_attempt[value.attempt_id]
                if (value.raw_return_hash != sha256(value.raw_return.encode()) or value.raw_return_hash != attempt.raw_return_hash
                        or value.input_hash != attempt.input_hash or attempt.proposal_record_id != value.id):
                    raise ValueError('proposal has no matching durable return')
            for value in [*self.finalization_history, *([self.finalization] if self.finalization else [])]:
                if value.operation_id != self.id or value.authorization_id not in authorities:
                    raise ValueError('finalization belongs to another operation or authorization')
        return self
