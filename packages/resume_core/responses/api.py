"""Rich GUI response contracts; domain types remain the Python authority."""

from typing import Literal
from pydantic import Field

from ..models.contracts import Id, Revision, Wire
from ..models.rich_workspace import WorkspaceV6
from .presentation import RichPresentation
from ..rich_identity import ResumeIdentity
from ..models.template_response import RichGenerationState




class RichProjectResponse(Wire):
    workspace: WorkspaceV6
    durability: Literal["pending", "durable", "failed"]
    saved_project_revision: Revision | None
    saved_document_revision: Revision | None
    save_error: Id | None
    generation: RichGenerationState | None
    presentation: RichPresentation | None = None
    identity: ResumeIdentity | None = None


class ImageSessionRequest(Wire):
    session_id: Id
    revision: Revision
    live: list[Id] = Field(max_length=20)
    history: list[Id]
    closed: bool = False
    previous_session_id: Id | None = None


class ImageUploadCapture(Wire):
    session_id: Id
    revision: Revision
    action_id: Id
    reservation_id: Id
    replacement_id: Id | None = None
