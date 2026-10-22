"""Retained clipboard fragments contain source keys and exact authority witnesses."""

from typing import Annotated,Literal

from pydantic import Field

from .contracts import Id,Sha256,Wire
from .template_authoring import TemplateClipboardCaptureV1
from .template_document import TemplateBlock,TemplateInline
from .template_facts import SourceSpan


class ClipboardBuiltinOwner(Wire):
    job_id: Id | None
    subproject_id: Id | None


class ClipboardRelationWitness(Wire):
    relation_id: Id
    relation_hash: Sha256


class ClipboardAncestorWitness(Wire):
    record_id: Id
    record_identity_hash: Sha256
    builtin_owner: ClipboardBuiltinOwner | None


class ClipboardOwnershipWitness(Wire):
    builtin_owner: ClipboardBuiltinOwner | None
    relations: list[ClipboardRelationWitness]
    ancestors: list[ClipboardAncestorWitness]


class ClipboardFieldWitness(Wire):
    kind: Literal['field']
    record_id: Id
    record_identity_hash: Sha256
    cell_id: Id
    field_key: Id
    effective_cell_hash: Sha256
    ownership: ClipboardOwnershipWitness


class ClipboardActiveCell(Wire):
    record_id: Id
    record_identity_hash: Sha256
    cell_id: Id
    field_key: Id
    effective_cell_hash: Sha256


class ClipboardRecordOwnership(Wire):
    record_id: Id
    ownership: ClipboardOwnershipWitness


class ClipboardScopeWitness(Wire):
    kind: Literal['scope']
    scope_id: Id
    scope_hash: Sha256
    active_cells: list[ClipboardActiveCell]
    ownerships: list[ClipboardRecordOwnership]


class ClipboardSourceWitness(Wire):
    kind: Literal['source_span']
    span: SourceSpan
    span_hash: Sha256


ClipboardWitness = Annotated[ClipboardFieldWitness | ClipboardScopeWitness | ClipboardSourceWitness,
    Field(discriminator='kind')]


class ClassifiedClipboardInline(Wire):
    kind: Literal['inline']
    content: list[TemplateInline]


class ClassifiedClipboardBlocks(Wire):
    kind: Literal['blocks']
    blocks: list[TemplateBlock]


class RetainedTemplateClipboardV1(Wire):
    capture: TemplateClipboardCaptureV1
    request_hash: Sha256
    package_fingerprint: Sha256
    payload: Annotated[ClassifiedClipboardInline | ClassifiedClipboardBlocks,Field(discriminator='kind')]
    witnesses: list[ClipboardWitness]
