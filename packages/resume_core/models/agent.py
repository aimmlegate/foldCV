"""Assistant wires the runtime, web fetcher, settings and the repository assistant share."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import AfterValidator, ConfigDict, Field, RootModel, model_validator

from .. import agent_limits as limits
from ..reasoning import ReasoningEffort
from .contracts import Revision, Sha256, Wire, _unique
from .rich_mutations import DependencyStamp


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


ErrorCode = Literal[
    "AGENT_DISABLED", "AGENT_MODEL_REQUIRED", "AGENT_MODEL_UNAVAILABLE", "AGENT_MODEL_INCOMPATIBLE",
    "AGENT_SETTINGS_CONFLICT", "AGENT_SETTINGS_CORRUPT", "AGENT_SETTINGS_SAVE_FAILED",
    "AGENT_CONNECTION_UNAVAILABLE", "AGENT_CONNECTION_CHANGED", "AGENT_AUTH_REQUIRED", "AGENT_QUOTA",
    "AGENT_BUSY", "AGENT_CANCELLED", "AGENT_INTERRUPTED", "AGENT_DEADLINE", "AGENT_STARTUP_TIMEOUT",
    "AGENT_PROTOCOL", "AGENT_PROCESS_FAILED", "AGENT_CLEANUP_FAILED", "AGENT_RUNTIME_UNSUPPORTED",
    "AGENT_MODEL_REROUTED", "AGENT_UNEXPECTED_COMPACTION", "AGENT_TOOL_DENIED", "AGENT_TOOL_LIMIT",
    "AGENT_OUTPUT_LIMIT", "AGENT_CONTEXT_LIMIT", "AGENT_ARGUMENT_INVALID", "AGENT_WEB_DISABLED", "AGENT_SOURCE_UNAVAILABLE",
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


class AgentSettings(AgentWire):
    schema_version: Literal[1]
    revision: Revision
    enabled: bool
    selected_agent_model: ModelId | None
    # Null runs the model's catalog default (decision 17); files written before MP01b load as null.
    reasoning_effort: ReasoningEffort | None = None


class AgentSettingsRequest(AgentWire):
    expected_revision: Revision
    enabled: bool
    selected_agent_model: ModelId | None
    reasoning_effort: ReasoningEffort | None = None


class AgentUsage(AgentWire):
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


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


class ActivityPayload(AgentWire):
    item_id: AgentId
    kind: Literal["summary"]
    text: str = Field(min_length=1, max_length=1200)


class ActivityEvent(EventBase):
    type: Literal["activity.updated"]
    payload: ActivityPayload


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
    type: Literal["source.ready", "finding.ready", "proposal.ready", "file.ready"]
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


class AgentEvent(RootModel[Annotated[Union[MessageDelta, ActivityEvent, ToolEvent, ResourceEvent, EditEvent,
        UsageEvent, RunStateEvent], Field(discriminator="type")]]):
    pass


class AgentFetchRequest(AgentWire):
    url: str = Field(min_length=1, max_length=4096)


AGENT_CONTRACTS = {
    "agent_error": AgentError,
    "agent_settings": AgentSettings,
    "agent_settings_request": AgentSettingsRequest,
    "agent_message": AgentMessage,
    "agent_web_source": AgentWebSource,
    "agent_finding": AgentFinding,
    "agent_event": AgentEvent,
    "agent_fetch_request": AgentFetchRequest,
}
