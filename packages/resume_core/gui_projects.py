"""Python-owned creation API contracts for the recovery document flow."""

from typing import Literal
from pydantic import Field

from .models.contracts import Id, Wire, Sha256
from .models.recovery import WorkspaceV5


class GuiCreateProjectRequest(Wire):
    text: str = Field(max_length=60000)


class GuiStartGenerationRequest(Wire):
    text: str | None = Field(default=None, max_length=60000)


class GuiProjectResponse(Wire):
    workspace: WorkspaceV5
    durability: Literal["in_memory"]
    generation_id: Id | None
    selection_fingerprint: Sha256 | None = None


GUI_PROJECT_CONTRACTS = {"gui_create_project_request": GuiCreateProjectRequest,
    "gui_start_generation_request": GuiStartGenerationRequest, "gui_project_response": GuiProjectResponse}
