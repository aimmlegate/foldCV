"""Versioned authoring steps keep template metadata across the rich engine."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Id, Revision, Sha256, Wire, _unique
from .template_facts import ExtensionRecord, ManualEditScope, Relation
from .canonical_patch import CanonicalPatchStep

from .rich_mutations import (MoveBlock, PutBlock, PutRecord, RemoveBlock, RemoveRecord,
                            ReplaceInlineRange, RichMutation, ActionCapture)
from .rich_workspace import RichSyncRecord
from .template_document import TemplateBlock, TemplateInline


class TemplatePutBlock(PutBlock):
    block: TemplateBlock


class FieldFlankSource(Wire):
    kind: Literal['field']
    binding_id: Id


class ManualScopeFlankSource(Wire):
    kind: Literal['manual_scope']
    fragment_id: Id


class FlankBinding(Wire):
    source: Annotated[FieldFlankSource | ManualScopeFlankSource, Field(discriminator='kind')]
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)
    role: Literal['prefix', 'suffix']
    fragment_id: Id

    @model_validator(mode='after')
    def ordered(self):
        if self.source_end <= self.source_start:
            raise ValueError('a partial flank needs a nonempty source range')
        return self


class TemplateReplaceInlineRange(ReplaceInlineRange):
    content: list[TemplateInline]
    flank_bindings: list[FlankBinding] | None = Field(default=None, max_length=1000,
        exclude_if=lambda value: value is None)


class AuthoredBlockHistoryDelta(Wire):
    block_id: Id
    before_semantic_hash: Sha256
    after_semantic_hash: Sha256
    forward_patch: list[CanonicalPatchStep] = Field(max_length=1000)
    inverse_patch: list[CanonicalPatchStep] = Field(max_length=1000)


class RestoreAuthoredBlockPatch(Wire):
    kind: Literal['restore_authored_block_patch']
    block_id: Id
    before_revision: Revision
    before_semantic_hash: Sha256
    after_semantic_hash: Sha256
    patch: list[CanonicalPatchStep] = Field(min_length=1, max_length=1000)


TemplateTreeStep = Annotated[TemplatePutBlock | RemoveBlock | MoveBlock | TemplateReplaceInlineRange |
    PutRecord | RemoveRecord | RestoreAuthoredBlockPatch, Field(discriminator='kind')]


class TemplateTreeMutation(RichMutation):
    steps: list[TemplateTreeStep] = Field(min_length=1, max_length=1000)


class PutExtension(Wire):
    kind: Literal['put_extension']
    before_revision: Revision | None
    record: ExtensionRecord


class RemoveExtension(Wire):
    kind: Literal['remove_extension']
    record_id: Id
    before_revision: Revision


class PutRelation(Wire):
    kind: Literal['put_relation']
    before_revision: Revision | None
    relation: Relation


class RemoveRelation(Wire):
    kind: Literal['remove_relation']
    relation_id: Id
    before_revision: Revision


class PutManualScope(Wire):
    kind: Literal['put_manual_scope']
    scope: ManualEditScope


class SetBuiltinManualScope(Wire):
    kind: Literal['set_builtin_manual_scope']
    cell_id: Id
    before_scope_id: Id | None
    after_scope_id: Id | None


class SetIssueState(Wire):
    kind: Literal['set_issue_state']
    issue_id: Id
    before_lifecycle_id: Id
    before_state: Literal['active', 'retired']
    after_lifecycle_id: Id
    after_state: Literal['active', 'retired']
    action_id: Id
    imported_fingerprint: Sha256


class IssueAnchorTarget(Wire):
    kind: Literal['issue']
    issue_id: Id
    imported_fingerprint: Sha256
    before_lifecycle_id: Id
    before_state: Literal['active', 'retired']


class CoverageAnchorTarget(Wire):
    kind: Literal['coverage']
    coverage_index: int = Field(ge=0)
    coverage_identity_hash: Sha256
    coverage_sequence_hash: Sha256


class SetAuthoredAnchors(Wire):
    kind: Literal['set_authored_anchors']
    target: Annotated[IssueAnchorTarget | CoverageAnchorTarget, Field(discriminator='kind')]
    before_block_ids: list[Id]
    after_block_ids: list[Id]

    @model_validator(mode='after')
    def unique_anchors(self):
        _unique(self.after_block_ids, 'authored anchor')
        return self


class ScopeDisplayFragment(Wire):
    block_id: Id
    cell_id: Id | None
    field: Literal['content', 'caption']
    fragment_id: Id
    fragment_hash: Sha256


class ScopeDisplaySource(Wire):
    scope_id: Id
    occurrence_id: Id
    scope_hash: Sha256
    active_cell_ids: list[Id] = Field(min_length=1, max_length=1000)
    fragments: list[ScopeDisplayFragment] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def distinct(self):
        _unique(self.active_cell_ids, 'scope display active cell')
        _unique([value.fragment_id for value in self.fragments], 'scope display source fragment')
        return self


class ScopeDisplayAddress(Wire):
    block_id: Id
    cell_id: Id | None
    field: Literal['content', 'caption']
    inline_index: int = Field(ge=0)


class ScopeDisplayBinding(Wire):
    kind: Literal['manual_scope']
    scope_id: Id
    occurrence_id: Id
    fragment_id: Id


class LiteralDisplayBinding(Wire):
    kind: Literal['literal']


class ScopeDisplayAssignment(Wire):
    address: ScopeDisplayAddress
    before_hash: Sha256
    after: Annotated[ScopeDisplayBinding | LiteralDisplayBinding, Field(discriminator='kind')]


class SetManualScopeDisplays(Wire):
    kind: Literal['set_manual_scope_displays']
    sources: list[ScopeDisplaySource] = Field(max_length=1000)
    assignments: list[ScopeDisplayAssignment] = Field(max_length=1000)

    @model_validator(mode='after')
    def distinct(self):
        _unique([(value.scope_id, value.occurrence_id) for value in self.sources], 'scope display source')
        _unique([(value.address.block_id, value.address.cell_id, value.address.field, value.address.inline_index)
            for value in self.assignments], 'scope display assignment')
        if not self.sources and not self.assignments:
            raise ValueError('empty scope display metadata step')
        return self


class HistoryCapture(Wire):
    kind: Literal['edit', 'undo', 'redo']
    origin_action_id: Id | None

    @model_validator(mode='after')
    def origin(self):
        if (self.kind == 'edit') != (self.origin_action_id is None):
            raise ValueError('history replay requires its original action')
        return self


TemplateNonSyncStep = Annotated[TemplatePutBlock | RemoveBlock | MoveBlock | TemplateReplaceInlineRange |
    PutRecord | RemoveRecord | PutExtension | RemoveExtension | PutRelation | RemoveRelation |
    PutManualScope | SetBuiltinManualScope | SetIssueState | SetAuthoredAnchors | RestoreAuthoredBlockPatch |
    SetManualScopeDisplays, Field(discriminator='kind')]


class TemplateOwnershipConflict(Wire):
    record_id: Id
    relation_id: Id | None
    before_owner_id: Id
    proposed_owner_id: Id
    moved_occurrence_ids: list[Id] = Field(min_length=1, max_length=1000)
    remaining_occurrence_ids: list[Id] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def distinct(self):
        _unique(self.moved_occurrence_ids + self.remaining_occurrence_ids, 'ownership conflict occurrence')
        if self.before_owner_id == self.proposed_owner_id:
            raise ValueError('ownership conflict requires an owner change')
        return self


class TemplateSyncResolution(Wire):
    sync_id: Id
    before_record_hash: Sha256
    before_lifecycle_id: Id


class TemplateSyncWrite(RichSyncRecord):
    schema_version: Literal[2]
    lifecycle_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    capture: ActionCapture | None
    proposed_steps: list[TemplateNonSyncStep] = Field(default_factory=list, max_length=1000)
    ownership_conflict: TemplateOwnershipConflict | None
    resolution_of: TemplateSyncResolution | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def sync_targets(self):
        for label, values in [('block', self.block_ids), ('field', self.field_keys), ('fact', self.fact_ids)]:
            _unique(values, 'template sync ' + label)
        _unique([(value.kind, value.id) for value in self.dependencies], 'template sync dependency')
        if self.ownership_conflict is not None and self.kind != 'conflict':
            raise ValueError('ownership conflict requires conflict kind')
        if self.resolution_of is not None and self.resolution_of.sync_id == self.id:
            raise ValueError('template sync resolution cannot reference itself')
        if self.capture is None and (self.ready or self.proposed_steps or self.dependencies or self.selection is not None):
            raise ValueError('inert template sync retains executable authority')
        return self


class TemplateSyncRecord(TemplateSyncWrite):
    lifecycle_id: Id


class TemplateSyncPlacement(Wire):
    after_sync_id: Id | None


class TemplateSyncHistoryPlacement(Wire):
    before_after_sync_id: Id | None
    after_sync_id: Id | None


class PutTemplateSync(Wire):
    kind: Literal['put_template_sync']
    before_hash: Sha256 | None
    record: TemplateSyncWrite
    placement: TemplateSyncPlacement | None = Field(default=None, exclude_if=lambda value: value is None)
    history_placement: TemplateSyncHistoryPlacement | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def creation_placement(self):
        if (self.before_hash is None) != (self.placement is not None):
            raise ValueError('only new template sync rows require placement')
        if self.placement is not None and self.placement.after_sync_id == self.record.id:
            raise ValueError('template sync cannot follow itself')
        if self.history_placement is not None and (self.before_hash is None or self.placement is not None
                or self.history_placement.after_sync_id == self.record.id
                or self.history_placement.before_after_sync_id == self.record.id):
            raise ValueError('invalid existing template sync history placement')
        return self


class RemoveTemplateSync(Wire):
    kind: Literal['remove_template_sync']
    sync_id: Id
    before_hash: Sha256


TemplateStep = Annotated[TemplateNonSyncStep | PutTemplateSync | RemoveTemplateSync, Field(discriminator='kind')]


class TemplateMutationV1(RichMutation):
    steps: list[TemplateStep] = Field(min_length=1, max_length=1000)
    history: HistoryCapture

    @model_validator(mode='after')
    def history_kind(self):
        expected = self.kind if self.kind in {'undo', 'redo'} else 'edit'
        if self.history.kind != expected or self.capture.action_id != self.action_id:
            raise ValueError('mutation/action history mismatch')
        return self
