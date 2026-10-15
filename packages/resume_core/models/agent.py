"""Version 1 assistant wires and private journal; canonical project wires stay fixed."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import AfterValidator, ConfigDict, Field, RootModel, model_validator

from .. import agent_limits as limits
from .contracts import MetricValue, PartialDate, Revision, Sha256, Wire, _unique
from .rich_mutations import DependencyStamp, RichMutation, RichSelection

AgentId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
ReferenceId = Annotated[str, Field(min_length=1, max_length=256)]
ModelId = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")]
def valid_timestamp(value: str) -> str:
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


Timestamp = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$",
    json_schema_extra={"format": "date-time"}), AfterValidator(valid_timestamp)]
RunState = Literal["queued", "running", "waiting_for_editor", "cancelling", "completed", "failed", "cancelled", "interrupted"]
EditState = Literal["prepared", "offered", "applying", "saved", "stale", "rejected", "cancelled", "save_failed", "outcome_unknown"]
TERMINAL_RUNS = frozenset({"completed", "failed", "cancelled", "interrupted"})
TERMINAL_EDITS = frozenset({"saved", "stale", "rejected", "cancelled", "save_failed"})
ErrorCode = Literal[
    "AGENT_DISABLED", "AGENT_MODEL_REQUIRED", "AGENT_MODEL_UNAVAILABLE", "AGENT_MODEL_INCOMPATIBLE",
    "AGENT_SETTINGS_CONFLICT", "AGENT_SETTINGS_CORRUPT", "AGENT_SETTINGS_SAVE_FAILED",
    "AGENT_CONNECTION_UNAVAILABLE", "AGENT_CONNECTION_CHANGED", "AGENT_AUTH_REQUIRED", "AGENT_QUOTA",
    "AGENT_BUSY", "AGENT_CANCELLED", "AGENT_INTERRUPTED", "AGENT_DEADLINE", "AGENT_STARTUP_TIMEOUT",
    "AGENT_PROTOCOL", "AGENT_PROCESS_FAILED", "AGENT_CLEANUP_FAILED", "AGENT_RUNTIME_UNSUPPORTED",
    "AGENT_MODEL_REROUTED", "AGENT_UNEXPECTED_COMPACTION", "AGENT_TOOL_DENIED", "AGENT_TOOL_LIMIT",
    "AGENT_OUTPUT_LIMIT", "AGENT_CONTEXT_LIMIT", "AGENT_WEB_DISABLED", "AGENT_SOURCE_UNAVAILABLE",
    "AGENT_SOURCE_DENIED", "AGENT_SOURCE_LIMIT", "AGENT_SCOPE_INVALID", "AGENT_STALE_READ",
    "AGENT_EDIT_INVALID", "AGENT_EDIT_LIMIT", "AGENT_EVIDENCE_INVALID", "AGENT_NO_OWNER",
    "AGENT_LEASE_EXPIRED", "AGENT_OWNER_MISMATCH", "AGENT_TICKET_INVALID", "AGENT_RECEIPT_TIMEOUT",
    "AGENT_SAVE_FAILED", "AGENT_OUTCOME_UNKNOWN", "AGENT_IDEMPOTENCY_CONFLICT", "AGENT_NOT_FOUND",
    "AGENT_CONVERSATION_FULL", "AGENT_PROJECT_FULL", "AGENT_STORE_CORRUPT", "AGENT_STORE_UNAVAILABLE",
    "AGENT_STORE_SAVE_FAILED", "AGENT_PROJECT_DELETED", "AGENT_CLEANUP_INCOMPLETE", "AGENT_RESYNC_REQUIRED",
]


def wire_bytes(value: Wire | RootModel) -> bytes:
    return value.model_dump_json(by_alias=True).encode("utf-8")


def bounded(value: Wire | RootModel, maximum: int) -> None:
    if len(wire_bytes(value)) > maximum:
        raise ValueError("serialized assistant record exceeds its byte limit")


class AgentWire(Wire):
    @model_validator(mode="before")
    @classmethod
    def literal_version_is_not_boolean(cls, value):
        if isinstance(value, dict) and type(value.get("schemaVersion")) is bool:
            raise ValueError("assistant schema version must be an integer")
        return value

    @model_validator(mode="after")
    def valid_unicode(self):
        def visit(value):
            if isinstance(value, str):
                value.encode("utf-8")
            elif isinstance(value, dict):
                for key, part in value.items():
                    visit(key)
                    visit(part)
            elif isinstance(value, list):
                for part in value:
                    visit(part)
        visit(self.model_dump(mode="json", by_alias=True))
        return self


class AgentError(AgentWire):
    code: ErrorCode


class AgentEmptyRequest(AgentWire):
    pass


class AgentSettings(AgentWire):
    schema_version: Literal[1]
    revision: Revision
    enabled: bool
    selected_agent_model: ModelId | None


class AgentSettingsRequest(AgentWire):
    expected_revision: Revision
    enabled: bool
    selected_agent_model: ModelId | None


class AgentModelCapability(AgentWire):
    model: ModelId
    state: Literal["unverified", "verified", "incompatible"]
    binary_sha256: Sha256
    protocol_sha256: Sha256
    config_sha256: Sha256
    account_epoch: AgentId
    reason: AgentError | None


class AgentCapabilities(AgentWire):
    schema_version: Literal[1]
    ready: bool
    binary_version: str = Field(max_length=128)
    binary_sha256: Sha256 | None
    protocol_sha256: Sha256 | None
    config_sha256: Sha256 | None
    connection_epoch: AgentId | None
    modes: list[Literal["edit", "check_only"]]
    tools: list[str] = Field(max_length=32)
    web_available: bool
    models: list[AgentModelCapability] = Field(max_length=100)
    unavailable: AgentError | None


class WholeResumeScope(AgentWire):
    kind: Literal["resume"]


class SelectionScope(AgentWire):
    kind: Literal["selection"]
    selection: RichSelection


AgentScope = Annotated[Union[WholeResumeScope, SelectionScope], Field(discriminator="kind")]


class AgentOwner(AgentWire):
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    epoch: Revision


class AgentLeaseOpen(AgentWire):
    session_id: AgentId


class AgentLease(AgentWire):
    project_id: AgentId
    session_id: AgentId
    owner: AgentOwner
    expires_at: Timestamp


class AgentOwnerRequest(AgentWire):
    owner: AgentOwner


class AgentRunRequest(AgentOwnerRequest):
    client_request_id: AgentId
    conversation_id: AgentId
    message: str = Field(min_length=1, max_length=limits.USER_CHARS)
    allow_edits: bool
    allow_web: bool
    scope: AgentScope
    settings_revision: Revision
    project_revision: Revision
    document_revision: Revision
    facts_revision: Revision


class AgentQuery(AgentWire):
    kind: Literal["context", "document", "find", "facts", "source", "history"]
    text: str = Field(default="", max_length=1000)
    ids: list[ReferenceId] = Field(default_factory=list, max_length=100)
    parent_id: ReferenceId | None = None
    cursor: str | None = Field(default=None, max_length=512)


class AgentEntityDependency(AgentWire):
    kind: Literal["entity"]
    stamp: DependencyStamp


class AgentQueryDependency(AgentWire):
    kind: Literal["query"]
    query: AgentQuery
    fingerprint: Sha256


AgentSnapshotDependency = Annotated[Union[AgentEntityDependency, AgentQueryDependency], Field(discriminator="kind")]


class AgentReadSnapshot(AgentWire):
    id: AgentId
    run_id: AgentId
    content_sha256: Sha256
    dependencies: list[AgentSnapshotDependency] = Field(max_length=2000)
    truncated: bool
    next_cursor: str | None = Field(max_length=512)


class AgentUsage(AgentWire):
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class AgentRun(AgentWire):
    id: AgentId
    conversation_id: AgentId
    project_id: AgentId
    client_request_id: AgentId
    owner_epoch: Revision
    state: RunState
    allow_edits: bool
    allow_web: bool
    scope: AgentScope
    model: ModelId
    connection_epoch: AgentId
    settings_revision: Revision
    created_at: Timestamp
    deadline: Timestamp
    finished_at: Timestamp | None
    usage: AgentUsage | None
    error: AgentError | None
    saved_batch_id: AgentId | None
    outcome_unknown: bool

    @model_validator(mode="after")
    def coherent_terminal(self):
        if (self.state in TERMINAL_RUNS) != (self.finished_at is not None):
            raise ValueError("terminal run needs its finish time")
        if self.state == "completed" and (self.error is not None or self.outcome_unknown):
            raise ValueError("completed run cannot conceal a failure or uncertain write")
        if not self.allow_edits and (self.saved_batch_id is not None or self.outcome_unknown):
            raise ValueError("read-only run cannot have an edit outcome")
        return self


class AgentReference(AgentWire):
    id: AgentId
    label: str = Field(max_length=256)


class AgentMessage(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.MESSAGE_BYTES,
        "allOf": [{"if": {"properties": {"role": {"const": "user"}}}, "then": {
            "properties": {"text": {"minLength": 1, "maxLength": limits.USER_CHARS}}}},
            {"if": {"properties": {"role": {"const": "assistant"}}}, "then": {
                "properties": {"text": {"x-maxUtf8Bytes": limits.ASSISTANT_TEXT_BYTES}}}}]})
    id: AgentId
    role: Literal["user", "assistant"]
    text: str
    run_id: AgentId
    timestamp: Timestamp
    sources: list[AgentReference] = Field(max_length=100)
    findings: list[AgentReference] = Field(max_length=100)
    truncated: bool
    error: AgentError | None

    @model_validator(mode="after")
    def message_limit(self):
        if self.role == "user" and (not self.text or len(self.text) > limits.USER_CHARS):
            raise ValueError("user message exceeds character limit")
        if self.role == "assistant" and len(self.text.encode("utf-8")) > limits.ASSISTANT_TEXT_BYTES:
            raise ValueError("assistant text exceeds byte limit")
        for refs in (self.sources, self.findings):
            _unique([ref.id for ref in refs], "message reference")
        bounded(self, limits.MESSAGE_BYTES)
        return self


class AgentWebSource(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.SOURCE_BYTES})
    id: AgentId
    run_id: AgentId
    requested_url: str = Field(min_length=1, max_length=4096)
    final_url: str = Field(min_length=1, max_length=4096)
    title: str = Field(max_length=512)
    retrieved_at: Timestamp
    content_sha256: Sha256
    text: str
    truncated: bool
    original_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def source_limit(self):
        bounded(self, limits.SOURCE_BYTES)
        return self


class AgentAnchor(AgentWire):
    block_id: ReferenceId | None
    cell_id: ReferenceId | None
    record_id: ReferenceId | None
    field_key: ReferenceId | None
    start: int | None = Field(ge=0)
    end: int | None = Field(ge=0)
    text: str = Field(max_length=4000)
    dependencies: list[DependencyStamp] = Field(max_length=100)

    @model_validator(mode="after")
    def ordered_range(self):
        if (self.start is None) != (self.end is None) or self.start is not None and self.end < self.start:
            raise ValueError("anchor needs an ordered UTF-16 range")
        return self


class AgentFinding(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.FINDING_BYTES})
    id: AgentId
    run_id: AgentId
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1, max_length=4000)
    anchors: list[AgentAnchor] = Field(max_length=20)
    source_ids: list[AgentId] = Field(max_length=20)

    @model_validator(mode="after")
    def finding_limit(self):
        bounded(self, limits.FINDING_BYTES)
        return self


class AgentInline(AgentWire):
    text: str = Field(max_length=16000)
    marks: list[Literal["bold", "italic", "underline", "strike", "code"]] = Field(default_factory=list, max_length=5)


class AgentRange(AgentWire):
    snapshot_id: AgentId
    block_id: ReferenceId
    cell_id: ReferenceId | None
    field: Literal["content", "caption"]
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered_range(self):
        if self.end < self.start:
            raise ValueError("edit range ends before its start")
        return self


class AgentReplaceText(AgentWire):
    kind: Literal["replace_text"]
    target: AgentRange
    content: list[AgentInline] = Field(max_length=100)


class AgentBlockAnchor(AgentWire):
    snapshot_id: AgentId
    parent_id: ReferenceId
    after_id: ReferenceId | None


class AgentNewBlock(AgentWire):
    key: AgentId
    kind: Literal["paragraph", "bullet_list_item", "numbered_list_item"]
    content: list[AgentInline] = Field(max_length=100)


class AgentInsertBlocks(AgentWire):
    kind: Literal["insert_blocks"]
    destination: AgentBlockAnchor
    blocks: list[AgentNewBlock] = Field(min_length=1, max_length=100)


class AgentDeleteBlocks(AgentWire):
    kind: Literal["delete_blocks"]
    snapshot_id: AgentId
    block_ids: list[ReferenceId] = Field(min_length=1, max_length=100)


class AgentMoveBlocks(AgentDeleteBlocks):
    kind: Literal["move_blocks"]
    destination: AgentBlockAnchor


class AgentSourceEvidence(AgentWire):
    kind: Literal["source"]
    source_id: ReferenceId
    unit_id: ReferenceId


class AgentFactEvidence(AgentWire):
    kind: Literal["fact"]
    record_id: ReferenceId


class AgentUserCorrection(AgentWire):
    kind: Literal["user_correction"]
    quote: str = Field(min_length=1, max_length=limits.USER_CHARS)


AgentEvidence = Annotated[Union[AgentSourceEvidence, AgentFactEvidence, AgentUserCorrection], Field(discriminator="kind")]


class AgentFactValue(AgentWire):
    status: Literal["known", "uncertain"]
    value: str | PartialDate | bool | MetricValue | None
    text: str = Field(max_length=8000)

    @model_validator(mode="after")
    def authority(self):
        if (self.status == "uncertain") != (self.value is None):
            raise ValueError("uncertain fact cannot claim a typed value")
        return self


FactKey = Literal["name", "title", "location", "label", "value", "employer", "role", "display", "canonical_id", "institution", "qualification", "specialty", "completion", "language", "level", "issuer", "date"]


class AgentUpdateFact(AgentWire):
    kind: Literal["update_fact"]
    snapshot_id: AgentId
    record_id: ReferenceId
    field_key: FactKey
    value: AgentFactValue
    evidence: list[AgentEvidence] = Field(min_length=1, max_length=20)


class AgentCreateFact(AgentWire):
    kind: Literal["create_fact"]
    key: AgentId
    record_kind: Literal["candidate", "detail", "employment", "technology", "education", "language", "certification", "claim", "metric"]
    owner_record_id: ReferenceId | None
    values: dict[FactKey, AgentFactValue] = Field(min_length=1, max_length=20)
    correction: AgentUserCorrection


class AgentDeleteFact(AgentWire):
    kind: Literal["delete_fact"]
    snapshot_id: AgentId
    record_id: ReferenceId
    correction: AgentUserCorrection


AgentEditOperation = Annotated[Union[AgentReplaceText, AgentInsertBlocks, AgentDeleteBlocks,
    AgentMoveBlocks, AgentUpdateFact, AgentCreateFact, AgentDeleteFact], Field(discriminator="kind")]


class AgentPrepareRequest(AgentWire):
    key: AgentId
    snapshot_ids: list[AgentId] = Field(max_length=24)
    operations: list[AgentEditOperation] = Field(max_length=limits.EDIT_OPERATIONS)


class AgentApplyRequest(AgentWire):
    batch_id: AgentId


class AgentEditBatch(AgentWire):
    id: AgentId
    run_id: AgentId
    tool_key: AgentId
    owner_epoch: Revision
    state: EditState
    scope: AgentScope
    read_snapshot_ids: list[AgentId] = Field(max_length=24)
    dependencies: list[AgentSnapshotDependency] = Field(max_length=2000)
    mutation: RichMutation
    request_sha256: Sha256
    preview_sha256: Sha256
    affected: list[AgentAnchor] = Field(max_length=100)
    fact_record_ids: list[ReferenceId] = Field(max_length=100)

    @model_validator(mode="after")
    def journal_limit(self):
        if self.mutation.kind != "structure":
            raise ValueError("prepared edit uses the shared structure action")
        bounded(self, limits.JOURNAL_BYTES)
        return self


class AgentEditReceipt(AgentWire):
    batch_id: AgentId
    run_id: AgentId
    tool_key: AgentId
    client_mutation_id: AgentId
    request_sha256: Sha256
    disposition: EditState
    project_revision: Revision | None
    document_revision: Revision | None
    facts_revision: Revision | None
    durable: bool
    error: AgentError | None

    @model_validator(mode="after")
    def saved_proof(self):
        if self.durable != (self.disposition == "saved"):
            raise ValueError("only saved receipt can claim durability")
        if self.durable and (self.error is not None or any(rev is None for rev in (
                self.project_revision, self.document_revision, self.facts_revision))):
            raise ValueError("saved receipt needs resulting revisions")
        return self


class AgentPrepareResult(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.TOOL_BYTES})
    disposition: Literal["prepared", "no_change"]
    batch_id: AgentId | None
    affected: list[AgentAnchor] = Field(max_length=100)
    preview: str = Field(max_length=4000)

    @model_validator(mode="after")
    def no_change(self):
        if (self.disposition == "prepared") != (self.batch_id is not None):
            raise ValueError("no_change has no batch")
        bounded(self, limits.TOOL_BYTES)
        return self


class AgentCommitRequest(AgentOwnerRequest):
    ticket: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    request_sha256: Sha256


class AgentClaimResult(AgentWire):
    ticket: str = Field(min_length=32, max_length=128)
    expires_at: Timestamp
    batch: AgentEditBatch


class AgentResultRequest(AgentOwnerRequest):
    receipt: AgentEditReceipt


class EventBase(AgentWire):
    schema_version: Literal[1]
    id: AgentId
    sequence: int = Field(ge=1)
    project_id: AgentId
    conversation_id: AgentId
    run_id: AgentId
    timestamp: Timestamp


class MessageDeltaPayload(AgentWire):
    text: str = Field(max_length=8000)


class MessageDelta(EventBase):
    type: Literal["message.delta"]
    payload: MessageDeltaPayload


class ToolPayload(AgentWire):
    call_id: AgentId
    name: str = Field(min_length=1, max_length=128)
    error: AgentError | None


class ToolEvent(EventBase):
    type: Literal["tool.started", "tool.completed", "tool.failed"]
    payload: ToolPayload


class ResourcePayload(AgentWire):
    id: AgentId


class ResourceEvent(EventBase):
    type: Literal["source.ready", "finding.ready"]
    payload: ResourcePayload


class EditPayload(AgentWire):
    batch_id: AgentId
    disposition: EditState
    error: AgentError | None


class EditEvent(EventBase):
    type: Literal["edit.offered", "edit.result"]
    payload: EditPayload


class UsageEvent(EventBase):
    type: Literal["usage.reported"]
    payload: AgentUsage


class RunStatePayload(AgentWire):
    state: RunState
    error: AgentError | None
    saved_batch_id: AgentId | None
    outcome_unknown: bool


class RunStateEvent(EventBase):
    type: Literal["run.state_changed"]
    payload: RunStatePayload


class AgentEvent(RootModel[Annotated[Union[MessageDelta, ToolEvent, ResourceEvent, EditEvent,
        UsageEvent, RunStateEvent], Field(discriminator="type")]]):
    pass


class AgentConversation(AgentWire):
    schema_version: Literal[1]
    id: AgentId
    project_id: AgentId
    created_at: Timestamp
    updated_at: Timestamp
    messages: list[AgentMessage] = Field(max_length=limits.CONVERSATION_MESSAGES)
    runs: list[AgentRun]
    sources: list[AgentWebSource]
    findings: list[AgentFinding]

    @model_validator(mode="after")
    def references(self):
        for collection in (self.messages, self.runs, self.sources, self.findings):
            _unique([item.id for item in collection], "conversation item")
        runs = {run.id for run in self.runs}
        sources = {source.id for source in self.sources}
        findings = {finding.id for finding in self.findings}
        if any(run.conversation_id != self.id or run.project_id != self.project_id for run in self.runs):
            raise ValueError("foreign conversation run")
        if sum(run.state not in TERMINAL_RUNS for run in self.runs) > 1:
            raise ValueError("conversation has more than one active run")
        if any(item.run_id not in runs for item in [*self.messages, *self.sources, *self.findings]):
            raise ValueError("foreign conversation resource")
        if any(ref.id not in sources for msg in self.messages for ref in msg.sources):
            raise ValueError("message cites an unstored source")
        if any(ref.id not in findings for msg in self.messages for ref in msg.findings):
            raise ValueError("message refers to an unstored finding")
        if any(id not in sources for finding in self.findings for id in finding.source_ids):
            raise ValueError("finding cites an unstored source")
        return self


class AgentPageRequest(AgentWire):
    cursor: str | None = Field(default=None, max_length=512)
    limit: int = Field(default=20, ge=1, le=20)
    ids: list[AgentId] = Field(default_factory=list, max_length=20)


class AgentConversationSummary(AgentWire):
    id: AgentId
    created_at: Timestamp
    updated_at: Timestamp
    title: str = Field(max_length=120)
    active_run_id: AgentId | None


class AgentConversationPage(AgentWire):
    items: list[AgentConversationSummary] = Field(max_length=20)
    next_cursor: str | None = Field(max_length=512)


class AgentMessagePage(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.RESPONSE_BYTES})
    items: list[AgentMessage] = Field(max_length=20)
    next_cursor: str | None = Field(max_length=512)

    @model_validator(mode="after")
    def response_limit(self):
        bounded(self, limits.RESPONSE_BYTES)
        return self


class AgentResourcePage(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.RESPONSE_BYTES})
    sources: list[AgentWebSource] = Field(max_length=20)
    findings: list[AgentFinding] = Field(max_length=20)
    next_cursor: str | None = Field(max_length=512)

    @model_validator(mode="after")
    def response_limit(self):
        bounded(self, limits.RESPONSE_BYTES)
        return self


class AgentEventsRequest(AgentOwnerRequest):
    after_sequence: int = Field(ge=0)


class AgentRunRead(AgentWire):
    run: AgentRun
    receipts: list[AgentEditReceipt] = Field(max_length=100)


class AgentToolRead(AgentWire):
    query: AgentQuery


class AgentToolResult(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.TOOL_BYTES})
    snapshot: AgentReadSnapshot
    content: str

    @model_validator(mode="after")
    def response_limit(self):
        bounded(self, limits.TOOL_BYTES)
        return self


class AgentFetchRequest(AgentWire):
    url: str = Field(min_length=1, max_length=4096)


class AgentFindingTarget(AgentWire):
    snapshot_id: AgentId
    block_id: ReferenceId | None
    cell_id: ReferenceId | None
    record_id: ReferenceId | None
    field_key: ReferenceId | None
    start: int | None = Field(ge=0)
    end: int | None = Field(ge=0)

    @model_validator(mode="after")
    def ordered_range(self):
        if (self.start is None) != (self.end is None) or self.start is not None and self.end < self.start:
            raise ValueError("finding target needs an ordered UTF-16 range")
        return self


class AgentFindingInput(AgentWire):
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1, max_length=4000)
    targets: list[AgentFindingTarget] = Field(max_length=20)
    source_ids: list[AgentId] = Field(max_length=20)


class AgentPublishFindings(AgentWire):
    findings: list[AgentFindingInput] = Field(max_length=20)


class AgentJournalRequest(AgentWire):
    client_request_id: AgentId
    conversation_id: AgentId
    message: str = Field(min_length=1, max_length=limits.USER_CHARS)
    allow_edits: bool
    allow_web: bool
    scope: AgentScope
    settings_revision: Revision
    project_revision: Revision
    document_revision: Revision
    facts_revision: Revision


class AgentBatchJournal(AgentWire):
    key: AgentId
    payload_sha256: Sha256
    result: AgentPrepareResult
    batch: AgentEditBatch | None
    receipt: AgentEditReceipt | None


class AgentRunJournal(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.JOURNAL_BYTES + limits.RUN_BYTES})
    run_id: AgentId
    request: AgentJournalRequest
    request_sha256: Sha256
    reserved: bool
    snapshots: list[AgentReadSnapshot] = Field(max_length=24)
    batches: list[AgentBatchJournal] = Field(max_length=100)
    events: list[AgentEvent]

    @model_validator(mode="after")
    def bounded_journal(self):
        bounded(self, limits.JOURNAL_BYTES + limits.RUN_BYTES)
        return self


class AgentProjectState(AgentWire):
    model_config = ConfigDict(json_schema_extra={"x-maxSerializedBytes": limits.PROJECT_BYTES})
    schema_version: Literal[1]
    project_id: AgentId
    revision: Revision
    owner_epoch: int = Field(ge=0)
    conversations: list[AgentConversation]
    journals: list[AgentRunJournal]

    @model_validator(mode="after")
    def owned_records(self):
        _unique([item.id for item in self.conversations], "conversation")
        _unique([item.run_id for item in self.journals], "run journal")
        if any(conv.project_id != self.project_id for conv in self.conversations):
            raise ValueError("foreign project conversation")
        runs = {run.id: run for conv in self.conversations for run in conv.runs}
        _unique([run.id for conv in self.conversations for run in conv.runs], "run")
        if set(runs) != {journal.run_id for journal in self.journals}:
            raise ValueError("every run needs exactly one journal")
        _unique([journal.request.client_request_id for journal in self.journals], "client request")
        for journal in self.journals:
            run = runs[journal.run_id]
            if journal.request.conversation_id != run.conversation_id or journal.request.client_request_id != run.client_request_id:
                raise ValueError("journal run identity mismatch")
            if any(snapshot.run_id != run.id for snapshot in journal.snapshots):
                raise ValueError("foreign read snapshot")
            _unique([snapshot.id for snapshot in journal.snapshots], "read snapshot")
            _unique([item.key for item in journal.batches], "prepare key")
            if sum(item.receipt is not None and item.receipt.durable for item in journal.batches) > 1:
                raise ValueError("run has more than one saved batch")
            if sum(item.batch is not None and item.batch.state not in TERMINAL_EDITS for item in journal.batches) > 1:
                raise ValueError("run has more than one live batch")
            sequences = [event.root.sequence for event in journal.events]
            if sequences != sorted(set(sequences)):
                raise ValueError("events must be ordered without duplicates")
            if any((event.root.run_id, event.root.project_id, event.root.conversation_id) !=
                    (run.id, self.project_id, run.conversation_id) for event in journal.events):
                raise ValueError("foreign event")
            if any(item.batch is not None and item.batch.run_id != run.id or
                    item.receipt is not None and item.receipt.run_id != run.id for item in journal.batches):
                raise ValueError("foreign batch")
        bounded(self, limits.PROJECT_BYTES)
        return self


AGENT_CONTRACTS = {
    "agent_error": AgentError, "agent_empty_request": AgentEmptyRequest, "agent_capabilities": AgentCapabilities,
    "agent_settings": AgentSettings, "agent_settings_request": AgentSettingsRequest,
    "agent_conversation": AgentConversation, "agent_message": AgentMessage,
    "agent_run_request": AgentRunRequest, "agent_run": AgentRun,
    "agent_read_snapshot": AgentReadSnapshot, "agent_web_source": AgentWebSource,
    "agent_finding": AgentFinding, "agent_prepare_request": AgentPrepareRequest,
    "agent_prepare_result": AgentPrepareResult, "agent_apply_request": AgentApplyRequest,
    "agent_edit_batch": AgentEditBatch, "agent_edit_receipt": AgentEditReceipt,
    "agent_event": AgentEvent, "agent_page_request": AgentPageRequest,
    "agent_conversation_page": AgentConversationPage, "agent_message_page": AgentMessagePage,
    "agent_resource_page": AgentResourcePage, "agent_lease_open": AgentLeaseOpen,
    "agent_lease": AgentLease, "agent_owner_request": AgentOwnerRequest,
    "agent_commit_request": AgentCommitRequest, "agent_claim_result": AgentClaimResult,
    "agent_result_request": AgentResultRequest, "agent_events_request": AgentEventsRequest,
    "agent_run_read": AgentRunRead, "agent_tool_read": AgentToolRead,
    "agent_tool_result": AgentToolResult, "agent_fetch_request": AgentFetchRequest,
    "agent_publish_findings": AgentPublishFindings, "agent_project_state": AgentProjectState,
}
