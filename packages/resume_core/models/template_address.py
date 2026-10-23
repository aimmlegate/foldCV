"""Session-only correspondence from one prepared request to its exact result."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Id, Revision, Sha256, Wire, _unique
from .template_authoring import FieldInsertionTarget, LiteralInsertionTarget, ManualScopeInsertionTarget
from .template_render import TemplateSnapshotIdentity

Offset = Annotated[int, Field(ge=0)]
InsertionTarget = Annotated[FieldInsertionTarget | LiteralInsertionTarget | ManualScopeInsertionTarget,
    Field(discriminator='kind')]


class TextContainerRef(Wire):
    kind: Literal['content', 'caption']
    block_id: Id
    revision: Revision


class CellContainerRef(Wire):
    kind: Literal['cell']
    block_id: Id
    revision: Revision
    cell_id: Id
    cell_revision: Revision


ContainerRefV1 = Annotated[TextContainerRef | CellContainerRef, Field(discriminator='kind')]


def container_key(ref):
    return ref.kind, ref.block_id, getattr(ref, 'cell_id', None)


class AllocationSlotV1(Wire):
    op_id: Id
    slot: Id


class LiteralSpanRef(Wire):
    kind: Literal['literal']
    path: list[Offset] = Field(min_length=1, max_length=2)


class FieldSpanRef(Wire):
    kind: Literal['field']
    binding_id: Id
    occurrence_id: Id
    record_id: Id
    field_key: Id
    cell_id: Id | None


class ScopeSpanRef(Wire):
    kind: Literal['manual_scope']
    scope_id: Id
    occurrence_id: Id
    fragment_id: Id


class BoundTextSpanRef(Wire):
    kind: Literal['bound_text']
    path: list[Offset] = Field(min_length=2, max_length=2)
    binding: Literal['label', 'url']
    record_id: Id
    field_key: Id
    cell_id: Id
    occurrence_id: Id


SpanRefV1 = Annotated[LiteralSpanRef | FieldSpanRef | ScopeSpanRef | BoundTextSpanRef, Field(discriminator='kind')]


class AddressInterval(Wire):
    start: Offset
    end: Offset

    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start:
            raise ValueError('address interval is reversed')
        return self


class SpanPieceV1(AddressInterval):
    span: SpanRefV1


AddressRole = Literal['retained_prefix', 'retained_suffix', 'retained', 'restyled', 'inserted']


def _sourced(role, source, result):
    if (role == 'inserted') != (source is None):
        raise ValueError('only inserted address content has no source')
    if source is not None and source.end - source.start != result.end - result.start:
        raise ValueError('retained address content changes length')


class AddressRegionV1(Wire):
    role: AddressRole
    source: AddressInterval | None
    result: AddressInterval

    @model_validator(mode='after')
    def sourced(self):
        _sourced(self.role, self.source, self.result)
        return self


class AddressSegmentV1(Wire):
    role: AddressRole
    source: SpanPieceV1 | None
    result: SpanPieceV1
    target: InsertionTarget | None
    slot: AllocationSlotV1 | None

    @model_validator(mode='after')
    def sourced(self):
        _sourced(self.role, self.source, self.result)
        return self


class AddressBoundaryV1(Wire):
    offset: Offset
    before: InsertionTarget | None
    after: InsertionTarget | None


class AddressContainerV1(Wire):
    input: ContainerRefV1 | None
    output: ContainerRefV1
    created: AllocationSlotV1 | None
    before_content_hash: Sha256 | None
    after_content_hash: Sha256
    before_length: Offset | None
    after_length: Offset
    correspondence: Literal['exact', 'none']
    regions: list[AddressRegionV1] = Field(max_length=3)
    segments: list[AddressSegmentV1] = Field(max_length=1000)
    boundaries: list[AddressBoundaryV1] = Field(max_length=2000)

    @model_validator(mode='after')
    def coherent(self):
        if not (self.input is None) == (self.before_content_hash is None) == (self.before_length is None):
            raise ValueError('address input needs its exact preimage')
        if self.input is not None and self.input.kind != self.output.kind:
            raise ValueError('address container changes its inline field kind')
        if self.correspondence == 'none':
            if self.regions or self.segments or self.boundaries:
                raise ValueError('an uncorresponded output carries no addresses')
            return self
        previous = None
        for region in self.regions:
            if region.result.end > self.after_length or region.source is not None and (
                    self.input is None or region.source.end > self.before_length):
                raise ValueError('address region exceeds its container')
            if previous is not None and (region.result.start != previous.result.end or region.source is not None
                    and previous.source is not None and region.source.start < previous.source.end):
                raise ValueError('address regions are not ordered and contiguous')
            previous = region
        edges = set()
        position = None
        for segment in self.segments:
            if position is not None and segment.result.start < position:
                raise ValueError('address segments are not in result order')
            position = segment.result.start
            region = next((value for value in self.regions if value.role == segment.role
                and value.result.start <= segment.result.start and segment.result.end <= value.result.end), None)
            if region is None:
                raise ValueError('address segment is outside its region')
            if segment.source is not None:
                shift = region.source.start - region.result.start
                if (segment.source.start != segment.result.start + shift
                        or segment.source.end != segment.result.end + shift):
                    raise ValueError('address segment source is not its mapped interval')
            edges.update((segment.result.start, segment.result.end))
        offsets = [value.offset for value in self.boundaries]
        if offsets != sorted(edges) or len(offsets) != len(set(offsets)):
            raise ValueError('address boundaries must be exactly the segment edges')
        return self


class PreparedAddressMapV1(Wire):
    schema_version: Literal[1]
    client_mutation_id: Id
    request_hash: Sha256
    base_snapshot: TemplateSnapshotIdentity
    result_snapshot: TemplateSnapshotIdentity
    containers: list[AddressContainerV1] = Field(max_length=10000)

    @model_validator(mode='after')
    def coherent(self):
        if (self.base_snapshot.project_id != self.result_snapshot.project_id
                or self.base_snapshot.package_hash != self.result_snapshot.package_hash):
            raise ValueError('address map changes project or captured package')
        if self.base_snapshot == self.result_snapshot and self.containers:
            raise ValueError('an unchanged result has no address containers')
        _unique([(container_key(value.input) if value.input is not None else None, container_key(value.output))
            for value in self.containers], 'address container')
        created = {}
        for value in self.containers:
            if value.created is not None and created.setdefault((value.created.op_id, value.created.slot),
                    container_key(value.output)[1]) != container_key(value.output)[1]:
                raise ValueError('one allocation slot names two created blocks')
        outputs, inputs = {}, {}
        for value in self.containers:
            outputs.setdefault(container_key(value.output), []).append(value)
            if value.input is not None:
                inputs.setdefault(container_key(value.input), []).append(value)
        for group in inputs.values():
            if any((value.input, value.before_content_hash, value.before_length)
                    != (group[0].input, group[0].before_content_hash, group[0].before_length) for value in group):
                raise ValueError('address entries disagree about one input')
        for group in outputs.values():
            first = group[0]
            if any((value.output, value.created, value.after_content_hash, value.after_length, value.correspondence)
                    != (first.output, first.created, first.after_content_hash, first.after_length, first.correspondence)
                    for value in group):
                raise ValueError('address entries disagree about one output')
            if first.correspondence == 'exact':
                regions = sorted((region.result.start, region.result.end) for value in group for region in value.regions)
                cursor = 0
                for start, end in regions:
                    if start != cursor:
                        raise ValueError('address regions do not partition their output')
                    cursor = end
                if cursor != first.after_length:
                    raise ValueError('address regions do not cover their output')
        return self
