"""Deterministic human edit intents retain the existing writer authority."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, PrivateAttr, model_validator

from .contracts import Id, Revision, Sha256, Wire, _unique
from .rich_document import Alignment, Color, Hyperlink, InlineStyles, StyledText
from .rich_mutations import ActionCapture
from .template_mutations import TemplateMutationV1
from .template_render import TemplateSnapshotIdentity
from ..rich_panel import RichPanelRequest
from ..template_api import TemplateProjectResponseV1


class FieldInsertionTarget(Wire):
    kind: Literal['field']
    binding_id: Id


class LiteralInsertionTarget(Wire):
    kind: Literal['literal']


class ManualScopeInsertionTarget(Wire):
    kind: Literal['manual_scope']
    fragment_id: Id


class AuthoredRange(Wire):
    block_id: Id
    before_revision: Revision
    cell_id: Id | None
    field: Literal['content', 'caption']
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    insertion_target: Annotated[FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget,
        Field(discriminator='kind')] | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def ordered(self):
        if (self.end < self.start or self.cell_id is not None and self.field != 'content'
                or self.start != self.end and self.insertion_target is not None):
            raise ValueError('invalid authored range')
        return self


class BlockTarget(Wire):
    block_id: Id
    before_revision: Revision


class AuthoredPlacement(Wire):
    parent_id: Id
    after_id: Id | None


class AuthoredOperationBase(Wire):
    op_id: Id


class ReplaceText(AuthoredOperationBase):
    kind: Literal['replace_text']
    range: AuthoredRange
    text: str
    styles: InlineStyles


class SetMarks(AuthoredOperationBase):
    kind: Literal['set_marks']
    range: AuthoredRange
    styles: InlineStyles


class SplitBlock(AuthoredOperationBase):
    kind: Literal['split_block']
    block_id: Id
    before_revision: Revision
    offset: int = Field(ge=0)


class MergeBlocks(AuthoredOperationBase):
    kind: Literal['merge_blocks']
    leading_id: Id
    leading_revision: Revision
    trailing_id: Id
    trailing_revision: Revision

    @model_validator(mode='after')
    def distinct(self):
        if self.leading_id == self.trailing_id:
            raise ValueError('merge needs distinct blocks')
        return self


class InsertParagraph(AuthoredOperationBase):
    kind: Literal['insert_paragraph']
    context_block_id: Id
    context_revision: Revision
    placement: AuthoredPlacement
    text: str


BlockTargets = Annotated[list[BlockTarget], Field(min_length=1, max_length=1000)]


class CopyBlocks(AuthoredOperationBase):
    kind: Literal['copy_blocks']
    sources: BlockTargets
    placement: AuthoredPlacement

    @model_validator(mode='after')
    def distinct(self):
        _unique([target.block_id for target in self.sources], 'copy target')
        return self


class CopyFragment(AuthoredOperationBase):
    kind: Literal['copy_fragment']
    source: AuthoredRange
    placement: AuthoredPlacement


class SameProjectClipboard(Wire):
    kind: Literal['same_project']
    clipboard_capture_id: Id


LiteralInline = Annotated[StyledText | Hyperlink, Field(discriminator='type')]


class LiteralPaste(Wire):
    kind: Literal['literal']
    content: list[LiteralInline]


class PasteInline(AuthoredOperationBase):
    kind: Literal['paste_inline']
    destination: AuthoredRange
    source: Annotated[SameProjectClipboard | LiteralPaste, Field(discriminator='kind')]


class PasteBlocks(AuthoredOperationBase):
    kind: Literal['paste_blocks']
    source: SameProjectClipboard
    placement: AuthoredPlacement


class MoveBlock(AuthoredOperationBase):
    kind: Literal['move_block']
    block_id: Id
    before_revision: Revision
    placement: AuthoredPlacement


class ResolveTemplateSync(AuthoredOperationBase):
    kind: Literal['resolve_template_sync']
    sync_id: Id
    before_record_hash: Sha256
    before_lifecycle_id: Id


class RemoveOccurrences(AuthoredOperationBase):
    kind: Literal['remove_occurrences']
    blocks: BlockTargets

    @model_validator(mode='after')
    def distinct(self):
        _unique([target.block_id for target in self.blocks], 'remove target')
        return self


class DeleteEntity(AuthoredOperationBase):
    kind: Literal['delete_entity']
    record_id: Id
    before_revision: Revision


class PanelPlacementContext(Wire):
    context_block_id: Id
    placement: AuthoredPlacement


class BuiltinPanel(AuthoredOperationBase):
    kind: Literal['builtin_panel']
    command: RichPanelRequest
    placement_context: PanelPlacementContext | None = Field(default=None, exclude_if=lambda value: value is None)


class ParagraphKind(Wire):
    type: Literal['paragraph']


class HeadingKind(Wire):
    type: Literal['heading']
    level: Literal[1, 2, 3]


class BulletKind(Wire):
    type: Literal['bullet_list']


class NumberedKind(Wire):
    type: Literal['numbered_list']
    start: Annotated[int, Field(ge=1)] | None


class BlockFormatPatch(Wire):
    model_config = ConfigDict(json_schema_extra={'anyOf': [
        {'required': [name]} for name in ['blockKind', 'alignment', 'textColor', 'backgroundColor']]})
    block_kind: Annotated[ParagraphKind | HeadingKind | BulletKind | NumberedKind,
        Field(discriminator='type')] = Field(default=None, exclude_if=lambda value: value is None)
    alignment: Alignment = Field(default=None, exclude_if=lambda value: value is None)
    text_color: Color = Field(default=None, exclude_if=lambda value: value is None)
    background_color: Color = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError('format patch needs nonnull supplied fields')
        return self


class FormatBlocks(AuthoredOperationBase):
    kind: Literal['format_blocks']
    targets: BlockTargets
    patch: BlockFormatPatch

    @model_validator(mode='after')
    def distinct(self):
        _unique([target.block_id for target in self.targets], 'format target')
        return self


AuthoredOperation = Annotated[ReplaceText | SetMarks | SplitBlock | MergeBlocks | InsertParagraph |
    CopyBlocks | CopyFragment | PasteInline | PasteBlocks | MoveBlock | RemoveOccurrences | DeleteEntity |
    BuiltinPanel | FormatBlocks | ResolveTemplateSync, Field(discriminator='kind')]


class TemplateEditPreparationV1(Wire):
    schema_version: Literal[1]
    client_mutation_id: Id
    snapshot: TemplateSnapshotIdentity
    capture: ActionCapture
    operations: list[AuthoredOperation] = Field(min_length=1, max_length=1)

    @model_validator(mode='after')
    def bounded(self):
        if len(self.model_dump_json(by_alias=True).encode()) > 1024 * 1024:
            raise ValueError('preparation exceeds 1 MiB')
        for operation in self.operations:
            target = operation.range if isinstance(operation, (ReplaceText, SetMarks)) else (
                operation.destination if isinstance(operation, PasteInline) else None)
            if target is not None:
                if isinstance(operation, SetMarks) and target.insertion_target is not None:
                    raise ValueError('marks have no insertion target')
                if isinstance(operation, (ReplaceText, PasteInline)) and target.start == target.end and target.insertion_target is None:
                    raise ValueError('collapsed replacement needs an explicit insertion target')
            if isinstance(operation, CopyFragment) and operation.source.insertion_target is not None:
                raise ValueError('clipboard source has no insertion target')
            if isinstance(operation, BuiltinPanel) and (operation.command.capture != self.capture
                    or operation.command.document_revision != self.snapshot.document_revision):
                raise ValueError('panel command capture differs from preparation')
        return self


class TemplatePreparedEditV1(Wire):
    schema_version: Literal[1]
    client_mutation_id: Id
    base_snapshot: TemplateSnapshotIdentity
    capture: ActionCapture
    request_hash: Sha256
    created_ids: dict[str, dict[str, Id]]
    mutation: TemplateMutationV1 | None
    preview: TemplateProjectResponseV1
    # Set only by the preparer; the address map needs typed versus restyled text.
    _address_middle: Literal['inserted', 'restyled'] | None = PrivateAttr(default=None)

    @property
    def address_middle(self):
        return self._address_middle

    @model_validator(mode='after')
    def identity(self):
        if self.preview.workspace.project_id != self.base_snapshot.project_id:
            raise ValueError('prepared preview belongs to another project')
        if self.mutation is not None and (self.mutation.client_mutation_id != self.client_mutation_id
                or self.mutation.capture != self.capture or self.mutation.history.kind != 'edit'
                or self.mutation.project_id != self.base_snapshot.project_id):
            raise ValueError('prepared mutation identity differs')
        if self.mutation is None and self.preview.snapshot != self.base_snapshot:
            raise ValueError('no-op preview must retain its base snapshot')
        _unique([identifier for slots in self.created_ids.values() for identifier in slots.values()], 'allocated ID')
        return self


class ClipboardRangeSelection(Wire):
    kind: Literal['range']
    range: AuthoredRange

    @model_validator(mode='after')
    def source_only(self):
        if self.range.insertion_target is not None:
            raise ValueError('clipboard source has no insertion target')
        return self


class ClipboardBlocksSelection(Wire):
    kind: Literal['blocks']
    blocks: BlockTargets

    @model_validator(mode='after')
    def distinct(self):
        _unique([target.block_id for target in self.blocks], 'clipboard target')
        return self


ClipboardSelection = Annotated[ClipboardRangeSelection | ClipboardBlocksSelection, Field(discriminator='kind')]


class TemplateClipboardCaptureV1(Wire):
    schema_version: Literal[1]
    clipboard_capture_id: Id
    project_id: Id
    source_snapshot: TemplateSnapshotIdentity
    selection: ClipboardSelection

    @model_validator(mode='after')
    def identity(self):
        if self.project_id != self.source_snapshot.project_id:
            raise ValueError('clipboard snapshot belongs to another project')
        return self


TEMPLATE_AUTHORING_CONTRACTS = {
    'template_edit_preparation_v1': TemplateEditPreparationV1,
    'template_prepared_edit_v1': TemplatePreparedEditV1,
    'template_clipboard_capture_v1': TemplateClipboardCaptureV1,
}
