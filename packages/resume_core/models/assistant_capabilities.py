"""Versioned task readiness, separate from runtime/model compatibility."""

from typing import Literal

from pydantic import Field, model_validator

from .agent import AgentId, AgentWire
from .contracts import Sha256

EditorFamily = Literal["ordinary", "template"]
TaskId = Literal["read_resume", "check_resume", "draft_text", "rewrite_resume", "correct_facts",
    "restructure", "format_document", "project_metadata", "sources", "images", "archive_project",
    "restore_project", "delete_project", "undo", "redo", "export_docx", "export_project",
    "read_public_page", "export_pdf", "shell", "apps", "send_application", "import_resume"]
TaskScope = Literal["resume", "selection", "project", "chat"]
TaskStage = Literal["generation", "preparation", "review", "apply"]


class AssistantProtocolV1(AgentWire):
    schema_version: Literal[1] = 1
    protocol_version: Literal[1] = 1

    @model_validator(mode="before")
    @classmethod
    def strict_protocol(cls, value):
        if isinstance(value, dict) and "protocolVersion" in value and type(value["protocolVersion"]) is not int:
            raise ValueError("protocol version must be an integer")
        return value


class AssistantAvailabilityV1(AgentWire):
    state: Literal["available", "permission_disabled", "missing_input", "temporarily_unavailable", "unsupported"]
    reason_code: str | None = Field(max_length=128)
    reason: str | None = Field(max_length=2000)
    remedy: str | None = Field(max_length=1000)


class AssistantTaskV1(AgentWire):
    id: TaskId
    label: str = Field(min_length=1, max_length=160)
    prompt: str | None = Field(max_length=1000)
    editors: list[EditorFamily] = Field(max_length=2)
    effect: Literal["read", "proposal", "project_action", "export"]
    scopes: list[TaskScope] = Field(min_length=1, max_length=4)
    required_inputs: list[str] = Field(max_length=8)
    required_permissions: list[Literal["read", "edit", "internet"]] = Field(max_length=3)
    reversibility: Literal["none", "shared_undo", "action_specific", "artifact"]
    limits: dict[str, int]
    generation: AssistantAvailabilityV1
    preparation: AssistantAvailabilityV1
    review: AssistantAvailabilityV1
    apply: AssistantAvailabilityV1


class AssistantTaskCatalogV1(AssistantProtocolV1):
    project_id: AgentId
    lineage: Sha256
    editor_family: EditorFamily
    catalog_revision: Sha256
    protocol_enabled: bool = Field(strict=True)
    tasks: list[AssistantTaskV1] = Field(min_length=1, max_length=32)


class AssistantTaskRequestV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    task_id: TaskId
    stage: TaskStage = "generation"
    scope: TaskScope = "resume"
    input_available: bool = Field(default=True, strict=True)


class AssistantMessageCheckV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    message: str = Field(min_length=1, max_length=8000)
    scope: TaskScope = "resume"
    allow_edits: bool = Field(strict=True)
    allow_web: bool = Field(strict=True)


class AssistantTaskCheckV1(AssistantProtocolV1):
    project_id: AgentId
    catalog_revision: Sha256
    task_id: TaskId | None
    availability: AssistantAvailabilityV1
    needs_planning: bool = Field(strict=True)


ASSISTANT_CAPABILITY_CONTRACTS = {
    "assistant_task_catalog_v1": AssistantTaskCatalogV1,
    "assistant_task_request_v1": AssistantTaskRequestV1,
    "assistant_message_check_v1": AssistantMessageCheckV1,
    "assistant_task_check_v1": AssistantTaskCheckV1,
}
