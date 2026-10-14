"""Rich GUI response contracts; domain types remain the Python authority."""

from typing import Literal

from .models.contracts import Id, Revision, Wire
from .models.rich_workspace import WorkspaceV6


class RichGenerationState(Wire):
    id: Id
    status: Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
    stage: Literal["normalize_semantics", "draft_prose", "assemble", "render"]
    error_code: Id | None


class RichProjectResponse(Wire):
    workspace: WorkspaceV6
    durability: Literal["pending", "durable", "failed"]
    saved_project_revision: Revision | None
    saved_document_revision: Revision | None
    save_error: Id | None
    generation: RichGenerationState | None
