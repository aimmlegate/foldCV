"""Versioned template responses bind authored state, presentation and durability."""

from typing import Literal

from pydantic import Field, model_validator

from .models.contracts import Id, Revision, Wire
from .models.template_render import TemplateSnapshotIdentity
from .models.template_workspace import WorkspaceV7
from .rich_api import RichGenerationState
from .rich_identity import ResumeIdentity
from .templates.models import AuthoredPresentation, CompiledRecipe
from .templates.presentation import presentation_matches, snapshot_identity


class EditorFaces(Wire):
    regular: Id | None
    bold: Id | None
    italic: Id | None
    bold_italic: Id | None


class EditorStyle(Wire):
    faces: EditorFaces
    size: float = Field(gt=0)
    line_height: float = Field(gt=0)
    color: str = Field(pattern=r'^#[a-fA-F0-9]{6}$')
    alignment: Literal['left', 'center', 'right', 'justify'] | None


class EditorFocus(Wire):
    blocks: list[Id] = Field(min_length=1)
    icon: Id | None


class EditorBlock(Wire):
    style: str
    band: Literal[True] | None = Field(default=None, exclude_if=lambda value: value is None)
    focus: EditorFocus | None = Field(default=None, exclude_if=lambda value: value is None)
    inline: dict[str, str] = Field(default_factory=dict, exclude_if=lambda value: not value)
    links: list[Id] = Field(default_factory=list, exclude_if=lambda value: not value)


class EditorPlanV1(Wire):
    """Python's presentation decisions for the mounted editor; the editor only applies them."""
    styles: dict[str, EditorStyle]
    blocks: dict[str, EditorBlock]
    fonts: list[Id]
    icons: list[Id]


class TemplatePresentationV1(Wire):
    schema_version: Literal[1]
    snapshot: TemplateSnapshotIdentity
    recipe: CompiledRecipe
    blocks: dict[str, AuthoredPresentation]
    editor: EditorPlanV1 | None = Field(default=None, exclude_if=lambda value: value is None)


class TemplateProjectResponseV1(Wire):
    schema_version: Literal[1]
    workspace: WorkspaceV7
    snapshot: TemplateSnapshotIdentity | None
    presentation: TemplatePresentationV1 | None
    durability: Literal['pending', 'durable', 'failed']
    saved_project_revision: Revision | None
    saved_document_revision: Revision | None
    save_error: Id | None
    generation: RichGenerationState | None
    identity: ResumeIdentity | None

    @model_validator(mode='after')
    def coherent_snapshot(self):
        expected = snapshot_identity(self.workspace)
        if self.snapshot != expected:
            raise ValueError('template response snapshot differs from its workspace')
        if not presentation_matches(self.presentation.model_dump(mode='json', by_alias=True) if self.presentation is not None
                else None, self.workspace):
            raise ValueError('template response presentation differs from its captured workspace')
        if self.durability == 'durable' and (self.saved_project_revision, self.saved_document_revision) != (
                self.workspace.project_revision, self.workspace.document_revision):
            raise ValueError('durable template response needs the matching save acknowledgment')
        return self
