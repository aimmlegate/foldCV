"""Explicit writer v2 content envelopes retain the existing opening authority."""

import hashlib
from typing import Annotated, Literal, Union

from pydantic import Field, RootModel, ValidationError, model_validator

from . import background
from .background import (BackgroundWire, DraftPayloadV1, WriterAdvanceV1, WriterBarrierAckV1,
    WriterCheckpointV1, WriterDraftReadV1, WriterDraftResolveV1, WriterViewV1)
from .contracts import Id, Revision
from .template_address import PreparedAddressMapV1
from .template_authoring import AuthoredRange, ClipboardSelection, TemplateEditPreparationV1, TemplatePreparedEditV1
from .template_delta import TemplatePreparedEditDeltaV1
from .template_render import TemplateSnapshotIdentity
from .contracts import Sha256
from .canonical_patch import CanonicalPatchStep
from .rich_workspace import RichMutationReplay
from .rich_document import InlineStyles
from .template_document import RichDocumentV2
from .template_facts import WorkingFactsV2
from .template_import import ImportIssue
from .template_mutations import TemplateMutationV1
from .template_workspace import SpanCoverage, WorkspaceV7
from ..template_api import TemplateProjectResponseV1
from ..rich_api import RichGenerationState
from ..rich_identity import ResumeIdentity


class WriterTouchV2(BackgroundWire):
    cursor: int = Field(ge=1)
    mutation: TemplateMutationV1 | None


class WriterAdvanceV2(WriterAdvanceV1):
    schema_version: Literal[2]
    touches: list[WriterTouchV2] = Field(default_factory=list, max_length=100)


class WriterBarrierAckV2(WriterBarrierAckV1):
    schema_version: Literal[2]
    touches: list[WriterTouchV2] = Field(default_factory=list, max_length=100)


class PreparedEditReference(BackgroundWire):
    request_hash: Sha256


class WriterMutationV2(WriterAdvanceV2):
    mutation: TemplateMutationV1
    preparation: PreparedEditReference | None = Field(default=None, exclude_if=lambda value: value is None)
    response_mode: Literal['full', 'prepared_delta'] = Field(default='full', exclude_if=lambda value: value == 'full')

    @model_validator(mode='after')
    def compact_needs_preparation(self):
        if self.response_mode == 'prepared_delta' and self.preparation is None:
            raise ValueError('compact save acknowledgment needs its prepared request')
        return self


class WriterPrepareEditV2(BackgroundWire):
    schema_version: Literal[2]
    proof: background.WriterProofV1
    preparation: TemplateEditPreparationV1
    preparation_input_wire: str | None = Field(default=None, max_length=1024 * 1024,
        exclude_if=lambda value: value is None)


def _bound_address(value, client_mutation_id, base, result, unchanged):
    import json
    wire = json.dumps(value.address_map.model_dump(mode='json', by_alias=True), ensure_ascii=False,
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    address = value.address_map
    if (hashlib.sha256(wire).hexdigest() != value.address_map_sha256
            or address.client_mutation_id != client_mutation_id or address.request_hash != value.request_hash
            or address.base_snapshot != base or address.result_snapshot != result or unchanged and address.containers):
        raise ValueError('address map differs from its prepared request')


class WriterPreparedDeltaV2(BackgroundWire):
    schema_version: Literal[2]
    preparation_input_sha256: Sha256
    request_hash: Sha256
    delta: TemplatePreparedEditDeltaV1
    address_map: PreparedAddressMapV1
    address_map_sha256: Sha256

    @model_validator(mode='after')
    def exact_preparation(self):
        if self.request_hash != self.delta.request_hash:
            raise ValueError('transport binding differs from prepared request')
        _bound_address(self, self.delta.client_mutation_id, self.delta.base_snapshot, self.delta.result_snapshot,
            self.delta.mutation_wire is None)
        return self


class WriterPreparedEditV2(BackgroundWire):
    schema_version: Literal[2]
    preparation_input_sha256: Sha256
    request_hash: Sha256
    prepared: TemplatePreparedEditV1
    address_map: PreparedAddressMapV1
    address_map_sha256: Sha256

    @model_validator(mode='after')
    def exact_preparation(self):
        if self.request_hash != self.prepared.request_hash:
            raise ValueError('transport binding differs from prepared request')
        _bound_address(self, self.prepared.client_mutation_id, self.prepared.base_snapshot,
            self.prepared.preview.snapshot, self.prepared.mutation is None)
        return self


class WriterCaptureClipboardV2(BackgroundWire):
    schema_version: Literal[2]
    proof: background.WriterProofV1
    client_capture_id: Id
    snapshot: TemplateSnapshotIdentity
    selection: ClipboardSelection


class WriterReleaseClipboardV2(BackgroundWire):
    schema_version: Literal[2]
    proof: background.WriterProofV1
    clipboard_capture_id: Id


class WriterClipboardReleaseResultV2(BackgroundWire):
    schema_version: Literal[2]
    clipboard_capture_id: Id
    released: Literal[True]


class WriterRewritePreviewV2(BackgroundWire):
    """Selected-text rewrite in one text block or cell; generation never changes the document."""
    schema_version: Literal[2]
    proof: background.WriterProofV1
    request_id: Id
    snapshot: TemplateSnapshotIdentity
    range: AuthoredRange
    instruction: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def selected(self):
        if self.range.start >= self.range.end or self.range.insertion_target is not None:
            raise ValueError('rewrite needs a selected range')
        return self


class TemplateRewritePreviewV1(BackgroundWire):
    schema_version: Literal[1]
    request_id: Id
    snapshot: TemplateSnapshotIdentity
    range: AuthoredRange
    source: str
    text: str = Field(min_length=1, max_length=65536)


class WriterRewriteCancelV2(BackgroundWire):
    schema_version: Literal[2]
    proof: background.WriterProofV1
    request_id: Id


class WriterRewriteCancelResultV2(BackgroundWire):
    schema_version: Literal[2]
    request_id: Id
    cancelled: bool


DraftId = Annotated[str, Field(min_length=1, max_length=256)]


class LocalContainerV1(BackgroundWire):
    block_id: DraftId
    kind: Literal['content', 'caption', 'cell']
    cell_id: DraftId | None

    @model_validator(mode='after')
    def cell(self):
        if (self.kind == 'cell') != (self.cell_id is not None):
            raise ValueError('only a cell container names a cell')
        return self


class LocalReplaceTextV1(BackgroundWire):
    kind: Literal['replace_text']
    container: LocalContainerV1
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    styles: InlineStyles
    side: Literal['before', 'after', 'interior', 'anchor'] | None

    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start or (self.side is None) == (self.start == self.end):
            raise ValueError('a collapsed replacement needs exactly one side')
        return self


class LocalSetMarksV1(BackgroundWire):
    kind: Literal['set_marks']
    container: LocalContainerV1
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    styles: InlineStyles

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('marks need a range')
        return self


class LocalSplitBlockV1(BackgroundWire):
    kind: Literal['split_block']
    container: LocalContainerV1
    offset: int = Field(ge=0)
    created: DraftId


class LocalMergeBlocksV1(BackgroundWire):
    kind: Literal['merge_blocks']
    leading: LocalContainerV1
    trailing: LocalContainerV1


LocalOperationV1 = Annotated[Union[LocalReplaceTextV1, LocalSetMarksV1, LocalSplitBlockV1, LocalMergeBlocksV1],
    Field(discriminator='kind')]


class DraftTextV1(BackgroundWire):
    container: LocalContainerV1
    text: str


class DraftIntentV1(BackgroundWire):
    local_id: DraftId
    action_id: DraftId
    action_token: int = Field(ge=0)
    client_mutation_id: DraftId
    operation: LocalOperationV1
    prior: list[DraftTextV1] = Field(min_length=1, max_length=2)


class DraftHeadV1(BackgroundWire):
    client_mutation_id: DraftId
    # The exact frozen preparation without the writer proof; no credential enters a draft.
    preparation_wire: str
    stage: Literal['frozen', 'prepared', 'saving']

    @model_validator(mode='after')
    def preparation(self):
        try:
            value = TemplateEditPreparationV1.model_validate_json(self.preparation_wire)
        except ValidationError:
            raise ValueError('head preparation is not a template edit preparation') from None
        if value.client_mutation_id != self.client_mutation_id:
            raise ValueError('head preparation names another mutation')
        return self


class DraftLocalBlockV1(BackgroundWire):
    local: DraftId
    canonical: DraftId


class TemplateQueueDraftV1(BackgroundWire):
    """Pending V7 input for recovery; Python checks shape and bounds and never interprets local operations."""
    schema_version: Literal[1]
    intents: list[DraftIntentV1] = Field(max_length=100)
    head: DraftHeadV1 | None
    locals: list[DraftLocalBlockV1] = Field(max_length=1000)
    editor_texts: list[DraftTextV1] = Field(max_length=1000)

    @model_validator(mode='after')
    def coherent(self):
        def key(container):
            return (container.block_id, container.kind, container.cell_id)
        if (len({item.local_id for item in self.intents}) != len(self.intents)
                or len({item.client_mutation_id for item in self.intents}) != len(self.intents)
                or len({item.local for item in self.locals}) != len(self.locals)
                or len({key(item.container) for item in self.editor_texts}) != len(self.editor_texts)):
            raise ValueError('duplicate queue draft identity')
        if self.head is not None and (not self.intents or self.intents[0].client_mutation_id != self.head.client_mutation_id):
            raise ValueError('the frozen head must be the first intent')
        return self


class DraftPayloadV2(DraftPayloadV1):
    schema_version: Literal[2]
    document: RichDocumentV2
    facts: WorkingFactsV2
    outbox: list[TemplateMutationV1] = Field(max_length=100)
    touches: list[WriterTouchV2] = Field(default_factory=list, max_length=100)
    import_issues: list[ImportIssue]
    import_coverage: list[SpanCoverage]
    # Omitted when absent so existing V2 drafts keep their bytes.
    template_queue: TemplateQueueDraftV1 | None = Field(default=None, exclude_if=lambda value: value is None)


class WriterCheckpointV2(WriterCheckpointV1):
    schema_version: Literal[2]
    payload: DraftPayloadV2


class WriterDraftReadV2(WriterDraftReadV1):
    schema_version: Literal[2]
    payload: DraftPayloadV2


class WriterDraftResolveV2(WriterDraftResolveV1):
    schema_version: Literal[2]
    mutation: TemplateMutationV1


class LocalHistoryAckV2(BackgroundWire):
    action_id: Id
    generation: Revision


class PreparedCommitProofV2(BackgroundWire):
    client_mutation_id: Id
    preparation_request_hash: Sha256
    mutation_sha256: Sha256
    replay: RichMutationReplay
    commit_binding: background.WriterCommitBindingV1
    prepared_workspace_sha256: Sha256
    committed_snapshot: TemplateSnapshotIdentity
    committed_workspace_sha256: Sha256
    commit_patch: list[CanonicalPatchStep] = Field(max_length=1000)
    local_history_ack: LocalHistoryAckV2 | None
    committed_identity: ResumeIdentity | None
    committed_generation: RichGenerationState | None

    @model_validator(mode='after')
    def exact_commit(self):
        if (self.replay.client_mutation_id != self.client_mutation_id or self.replay.request_sha256 != self.mutation_sha256
                or self.replay.resulting_revision != self.committed_snapshot.project_revision):
            raise ValueError('prepared commit proof differs from durable mutation replay')
        return self


class WriterPreparedSaveAckV2(PreparedCommitProofV2):
    schema_version: Literal[2]
    kind: Literal['committed']
    writer: background.WriterSessionV1
    replayed: bool
    current_canonical_revision: Revision
    current_canonical_sha256: Sha256
    current_equals_committed: bool

    @model_validator(mode='after')
    def current_identity(self):
        if (self.writer.project_id != self.committed_snapshot.project_id
                or (self.writer.epoch, self.writer.incarnation) != (self.commit_binding.epoch, self.commit_binding.incarnation)
                or self.writer.acknowledged_cursor < self.commit_binding.action_cursor
                or self.writer.touch_generation < self.commit_binding.touch_generation
                or self.current_canonical_revision < self.replay.resulting_revision
                or self.current_equals_committed != ((self.current_canonical_revision, self.current_canonical_sha256)
                    == (self.committed_snapshot.project_revision, self.committed_workspace_sha256))):
            raise ValueError('compact save acknowledgment misidentifies current state')
        return self


class WriterPreparedSaveRecoveryV2(BackgroundWire):
    schema_version: Literal[2]
    kind: Literal['committed_recovery_required']
    reason: Literal['compact_commit_proof_expired']
    writer: background.WriterSessionV1
    client_mutation_id: Id
    preparation_request_hash: Sha256
    mutation_sha256: Sha256
    replay: RichMutationReplay
    current_canonical_revision: Revision
    current_canonical_sha256: Sha256

    @model_validator(mode='after')
    def exact_replay(self):
        if (self.replay.client_mutation_id != self.client_mutation_id or self.replay.request_sha256 != self.mutation_sha256
                or self.current_canonical_revision < self.replay.resulting_revision):
            raise ValueError('compact recovery needs exact durable replay')
        return self


class WriterPreparedSaveResultV2(RootModel[Annotated[
        WriterPreparedSaveAckV2 | WriterPreparedSaveRecoveryV2, Field(discriminator='kind')]]):
    pass


class WriterViewV2(WriterViewV1):
    schema_version: Literal[2]
    response: TemplateProjectResponseV1
    local_history_ack: LocalHistoryAckV2 | None = None
    # The browser reads the workspace text from the response itself; a second copy doubled every reply (D104).
    workspace_wire: str = Field(default='', exclude=True)

    @model_validator(mode='after')
    def exact_workspace(self):
        from ..templates.compiler import canonical
        workspace = self.response.workspace
        exact = canonical(workspace)
        if (hashlib.sha256(exact).hexdigest() != self.workspace_sha256
                or self.workspace_wire and self.workspace_wire.encode() != exact
                or self.writer.project_id != workspace.project_id
                or any(item.project_id != workspace.project_id or item.lineage != self.writer.lineage for item in self.drafts)
                or not self.canonical_ready and self.response.durability == 'durable'
                or self.canonical_ready and (self.response.durability != 'durable'
                    or self.response.saved_project_revision != workspace.project_revision
                    or self.response.saved_document_revision != workspace.document_revision)):
            raise ValueError('writer v2 view needs its exact canonical bytes')
        if self.mutation_wire is not None:
            mutation = TemplateMutationV1.model_validate_json(self.mutation_wire)
            if (mutation.model_dump_json(by_alias=True) != self.mutation_wire or mutation.project_id != workspace.project_id
                    or not self.canonical_ready or not any(item.client_mutation_id == mutation.client_mutation_id
                        and item.request_sha256 == hashlib.sha256(self.mutation_wire.encode()).hexdigest()
                        and item.resulting_revision <= workspace.project_revision for item in workspace.mutation_replay)):
                raise ValueError('template mutation acknowledgment needs exact replay proof')
            origin = mutation.history.origin_action_id or mutation.action_id
            if self.local_history_ack is not None and self.local_history_ack.action_id != origin:
                raise ValueError('local history acknowledgment belongs to another action')
        elif self.local_history_ack is not None:
            raise ValueError('local history acknowledgment needs its exact mutation')
        return self


class WriterLocalHistoryCommandV2(WriterAdvanceV2):
    origin_action_id: Id
    action_generation: Revision
    direction: Literal['undo', 'redo']
    client_mutation_id: Id


TEMPLATE_WRITER_CONTRACTS = {
    'background_writer_touch_v2': WriterTouchV2,
    'background_writer_advance_v2': WriterAdvanceV2,
    'background_writer_barrier_ack_v2': WriterBarrierAckV2,
    'background_writer_mutation_v2': WriterMutationV2,
    'background_writer_prepare_edit_v2': WriterPrepareEditV2,
    'background_writer_prepared_delta_v2': WriterPreparedDeltaV2,
    'background_writer_prepared_edit_v2': WriterPreparedEditV2,
    'template_address_map_v1': PreparedAddressMapV1,
    'background_writer_capture_clipboard_v2': WriterCaptureClipboardV2,
    'background_writer_release_clipboard_v2': WriterReleaseClipboardV2,
    'background_writer_clipboard_release_result_v2': WriterClipboardReleaseResultV2,
    'background_writer_rewrite_preview_v2': WriterRewritePreviewV2,
    'template_rewrite_preview_v1': TemplateRewritePreviewV1,
    'background_writer_rewrite_cancel_v2': WriterRewriteCancelV2,
    'background_writer_rewrite_cancel_result_v2': WriterRewriteCancelResultV2,
    'background_writer_draft_payload_v2': DraftPayloadV2,
    'background_writer_checkpoint_v2': WriterCheckpointV2,
    'background_writer_draft_read_v2': WriterDraftReadV2,
    'background_writer_draft_resolve_v2': WriterDraftResolveV2,
    'background_writer_view_v2': WriterViewV2,
    'background_writer_local_history_command_v2': WriterLocalHistoryCommandV2,
    'background_writer_prepared_save_result_v2': WriterPreparedSaveResultV2,
}

for _model in TEMPLATE_WRITER_CONTRACTS.values():
    _model.model_rebuild(_types_namespace=vars(background))
