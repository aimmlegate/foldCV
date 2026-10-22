"""Versioned template responses bind authored state, presentation and durability."""

from typing import Literal

from pydantic import model_validator

from .models.contracts import Id, Revision, Wire
from .models.template_render import TemplateSnapshotIdentity
from .models.template_workspace import WorkspaceV7
from .rich_api import RichGenerationState
from .rich_identity import ResumeIdentity
from .templates.models import AuthoredPresentation, CompiledRecipe
from .templates.presentation import project_presentation, snapshot_identity


class TemplatePresentationV1(Wire):
    schema_version: Literal[1]
    snapshot: TemplateSnapshotIdentity
    recipe: CompiledRecipe
    blocks: dict[str, AuthoredPresentation]


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
        presented = project_presentation(self.workspace)
        if (self.presentation.model_dump(mode='json', by_alias=True) if self.presentation is not None else None) != presented:
            raise ValueError('template response presentation differs from its captured workspace')
        if self.durability == 'durable' and (self.saved_project_revision, self.saved_document_revision) != (
                self.workspace.project_revision, self.workspace.document_revision):
            raise ValueError('durable template response needs the matching save acknowledgment')
        return self
