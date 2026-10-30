"""Versioned template responses bind authored state, presentation and durability."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .models.contracts import Id, Revision, Sha256, Wire
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
    # Binding or fragment id of each span shown as a chip, with its background.
    chips: dict[str, Annotated[str, Field(pattern=r'^#[a-fA-F0-9]{6}$')]] = Field(default_factory=dict,
        exclude_if=lambda value: not value)


class EditorPlacement(Wire):
    """A block's parent block or region and the sibling before it, as a panel placement context names them."""
    parent_id: Id
    after_id: Id | None


class EditorTechnologyTarget(Wire):
    """Where the facts panel adds a technology: a line of one scope, a job section that has none yet, or a group view
    the document no longer shows (block id view:<view id>)."""
    block_id: Id
    job_id: Id | None
    # The view title the panel names when one scope has several lines.
    label: str
    # The block's place, or where the view's line goes; the panel sends it back and Python refuses an older one.
    placement: EditorPlacement


class EditorFocusPanel(Wire):
    """The facts panel can add, remove and move Focus rows, set their years and choose their icons."""
    # Records only Focus rows show; the panel's technology lists leave them out.
    records: list[Id]
    # A row's icon can be chosen from the template's icons (D122).
    icons: bool = Field(default=False, exclude_if=lambda value: not value)
    # The template's view takes no further row.
    full: bool = Field(default=False, exclude_if=lambda value: not value)


class EditorJob(Wire):
    """One job in the facts panel."""
    # Each period as the document writes it.
    periods: list[str]
    # A new period has a place in the document; a job in a compressed list has none.
    add_period: bool = Field(default=False, exclude_if=lambda value: not value)


class EditorPlanV1(Wire):
    """Python's presentation decisions for the mounted editor; the editor only applies them."""
    styles: dict[str, EditorStyle]
    blocks: dict[str, EditorBlock]
    fonts: list[Id]
    icons: list[Id]
    # Each used icon's PNG by hash; a packed icon has no asset entry of its own.
    icon_files: dict[str, Sha256] = Field(default_factory=dict, exclude_if=lambda value: not value)
    # The only places a new technology can be shown; a scope without one offers no adding.
    technology_targets: list[EditorTechnologyTarget] = Field(default_factory=list, exclude_if=lambda value: not value)
    # Absent when the template's Focus is not one view the panel can change.
    focus_panel: EditorFocusPanel | None = Field(default=None, exclude_if=lambda value: value is None)
    jobs: dict[Id, EditorJob] = Field(default_factory=dict, exclude_if=lambda value: not value)
    # By record, the fields the document has no place for; the panel's dialog leaves them out.
    unshown_fields: dict[Id, list[str]] = Field(default_factory=dict, exclude_if=lambda value: not value)
    # The technologies of each line with several; a move stays inside its line.
    technology_lines: list[list[Id]] = Field(default_factory=list, exclude_if=lambda value: not value)
    # The record kinds this template's document has a place for; the panel offers adding only these.
    add_kinds: list[Literal['employment', 'education', 'language']] = Field(default_factory=list,
        exclude_if=lambda value: not value)


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
        if self.durability == 'durable' and (self.saved_project_revision, self.saved_document_revision) != (
                self.workspace.project_revision, self.workspace.document_revision):
            raise ValueError('durable template response needs the matching save acknowledgment')
        # Recomputing snapshot and presentation costs a full pass over the project; tests and FOLDCV_VERIFY do it on
        # every construction, the service builds them from the workspace it serves (D109).
        if verifying():
            verify_response(self)
        return self


def verifying():
    import os
    return os.environ.get('FOLDCV_VERIFY') == '1'


def verify_response(response):
    """A response's snapshot and presentation are the ones its workspace yields."""
    if response.snapshot != snapshot_identity(response.workspace):
        raise ValueError('template response snapshot differs from its workspace')
    if not presentation_matches(response.presentation.model_dump(mode='json', by_alias=True) if response.presentation is not None
            else None, response.workspace):
        raise ValueError('template response presentation differs from its captured workspace')
    return response
