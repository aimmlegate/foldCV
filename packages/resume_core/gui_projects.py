"""Python-owned creation API contracts for the recovery document flow."""

from typing import Literal
from pydantic import Field, field_validator

from .models.contracts import Id, Revision, Wire, Sha256
from .models.recovery import WorkspaceV5, RegistryEntry


class GuiCreateProjectRequest(Wire):
    text: str = Field(max_length=60000)


class GuiStartGenerationRequest(Wire):
    text: str | None = Field(default=None, max_length=60000)


class GuiProjectResponse(Wire):
    workspace: WorkspaceV5
    durability: Literal["in_memory", "durable", "pending", "failed"]
    generation_id: Id | None
    selection_fingerprint: Sha256 | None = None
    saved_project_revision: Revision | None = None
    saved_document_revision: Revision | None = None
    save_error: Id | None = None


class GuiRenameProjectRequest(Wire):
    title: str = Field(min_length=1, max_length=200)
    base_revision: Revision


class ProjectReadError(Wire):
    project_id: Id
    error_code: Id


class GuiProjectListResponse(Wire):
    entries: list[RegistryEntry]
    errors: list[ProjectReadError]


class GuiDeleteProjectRequest(Wire):
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True: raise ValueError("confirmation_required")
        return value


class GuiDeleteProjectResult(Wire):
    project_id: Id
    status: Literal["deleted", "cleanup_incomplete"]
    error_code: Id | None


class GuiArchiveRequest(Wire):
    project_revision: Revision
    document_revision: Revision


GUI_PROJECT_CONTRACTS = {"gui_create_project_request": GuiCreateProjectRequest,
    "gui_start_generation_request": GuiStartGenerationRequest, "gui_project_response": GuiProjectResponse,
    "gui_rename_project_request": GuiRenameProjectRequest,
    "gui_project_list_response": GuiProjectListResponse, "gui_delete_project_request": GuiDeleteProjectRequest,
    "gui_delete_project_result": GuiDeleteProjectResult, "gui_archive_request": GuiArchiveRequest}
