"""Explicit writer v2 content envelopes retain the existing opening authority."""

import hashlib
from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from . import background
from .background import (BackgroundWire, DraftPayloadV1, WriterAdvanceV1, WriterBarrierAckV1,
    WriterCheckpointV1, WriterDraftReadV1, WriterDraftResolveV1, WriterViewV1)
from .contracts import Id, Revision
from .template_authoring import ClipboardSelection, TemplateEditPreparationV1
from .template_delta import TemplatePreparedEditDeltaV1
from .template_render import TemplateSnapshotIdentity
from .contracts import Sha256
from .canonical_patch import CanonicalPatchStep
from .rich_workspace import RichMutationReplay
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


class WriterPreparedDeltaV2(BackgroundWire):
    schema_version: Literal[2]
    preparation_input_sha256: Sha256
    request_hash: Sha256
    delta: TemplatePreparedEditDeltaV1

    @model_validator(mode='after')
    def exact_preparation(self):
        if self.request_hash != self.delta.request_hash:
            raise ValueError('transport binding differs from prepared request')
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


class DraftPayloadV2(DraftPayloadV1):
    schema_version: Literal[2]
    document: RichDocumentV2
    facts: WorkingFactsV2
    outbox: list[TemplateMutationV1] = Field(max_length=100)
    touches: list[WriterTouchV2] = Field(default_factory=list, max_length=100)
    import_issues: list[ImportIssue]
    import_coverage: list[SpanCoverage]


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

    @model_validator(mode='after')
    def exact_workspace(self):
        workspace = self.response.workspace
        if (hashlib.sha256(self.workspace_wire.encode()).hexdigest() != self.workspace_sha256
                or WorkspaceV7.model_validate_json(self.workspace_wire) != workspace
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
    'background_writer_capture_clipboard_v2': WriterCaptureClipboardV2,
    'background_writer_release_clipboard_v2': WriterReleaseClipboardV2,
    'background_writer_clipboard_release_result_v2': WriterClipboardReleaseResultV2,
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
