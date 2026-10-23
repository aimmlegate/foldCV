"""Build the session-only address map inside the preparation that produced it."""

from dataclasses import dataclass

from .models.rich_document import Hyperlink, ImageBlock, InlineStyles, TableBlock
from pydantic import ValidationError

from .models.template_address import AddressContainerV1, PreparedAddressMapV1
from .models.template_authoring import AuthoredRange, InsertParagraph, MergeBlocks, ReplaceText, SplitBlock
from .models.template_document import BoundLink, FieldOccurrence, ManualScopeSpan
from .models.template_mutations import SetManualScopeDisplays, TemplateReplaceInlineRange
from .rich_fields import inline_groups
from .rich_mutations import RichMutationFailure, inline_text, utf16_slice
from .templates.compiler import canonical, sha256


class NoCorrespondence(Exception):
    pass


@dataclass(frozen=True)
class Leaf:
    path: tuple
    span: object
    link: object
    start: int
    end: int


def units(text):
    return len(text.encode('utf-16-le')) // 2


def content_text(content):
    return ''.join(inline_text(span) for span in content)


def content_wire(content):
    return [span.model_dump(mode='json', by_alias=True) for span in content]


def content_leaves(content):
    result, cursor = [], 0
    for index, span in enumerate(content):
        if isinstance(span, (Hyperlink, BoundLink)):
            for child_index, child in enumerate(span.content):
                size = units(child.text)
                result.append(Leaf((index, child_index), child, span, cursor, cursor + size))
                cursor += size
        else:
            size = units(span.text)
            result.append(Leaf((index,), span, None, cursor, cursor + size))
            cursor += size
    return result


def span_ref(leaf):
    span, link = leaf.span, leaf.link
    if isinstance(span, FieldOccurrence):
        return {'kind': 'field', 'bindingId': span.binding_id, 'occurrenceId': span.occurrence_id,
            'recordId': span.record_id, 'fieldKey': span.field_key, 'cellId': span.cell_id}
    if isinstance(span, ManualScopeSpan):
        return {'kind': 'manual_scope', 'scopeId': span.scope_id, 'occurrenceId': span.occurrence_id,
            'fragmentId': span.fragment_id}
    if isinstance(link, BoundLink):
        bound, name = (link.label_binding, 'label') if link.label_binding is not None else (link.url_binding, 'url')
        return {'kind': 'bound_text', 'path': list(leaf.path), 'binding': name, 'recordId': bound.record_id,
            'fieldKey': bound.field_key, 'cellId': bound.cell_id, 'occurrenceId': bound.occurrence_id}
    return {'kind': 'literal', 'path': list(leaf.path)}


def identity(leaf):
    if isinstance(leaf.span, FieldOccurrence):
        return 'field', leaf.span.binding_id
    if isinstance(leaf.span, ManualScopeSpan):
        return 'scope', leaf.span.fragment_id
    return None


def leaf_wire(leaf):
    # Paths are positions, not identity: a shifted identical leaf needs no segment.
    owner = leaf.link.model_dump(mode='json', by_alias=True, exclude={'content'}) if leaf.link is not None else None
    reference = {key: value for key, value in span_ref(leaf).items() if key != 'path'}
    return canonical({'span': leaf.span.model_dump(mode='json', by_alias=True), 'owner': owner, 'ref': reference})


def candidate(leaf):
    if isinstance(leaf.span, FieldOccurrence):
        return {'kind': 'field', 'bindingId': leaf.span.binding_id} if leaf.span.complete else None
    if isinstance(leaf.span, ManualScopeSpan):
        return {'kind': 'manual_scope', 'fragmentId': leaf.span.fragment_id}
    if isinstance(leaf.link, BoundLink):
        return None
    return {'kind': 'literal'}


class Output:
    def __init__(self, block, key, content):
        self.block, self.key, self.content = block, key, content
        self.text, self.leaves = content_text(content), content_leaves(content)
        self.length = units(self.text)
        self.probe = ReplaceText(kind='replace_text', opId='address-probe', range=self.range(0, None), text='',
            styles=InlineStyles())

    def range(self, point, target):
        kind = container_kind(self.block)
        value = {'blockId': self.block.id, 'beforeRevision': self.block.revision,
            'cellId': self.key if kind == 'cell' else None,
            'field': 'caption' if kind == 'caption' else 'content', 'start': point, 'end': point}
        if target is not None:
            value['insertionTarget'] = target
        return AuthoredRange.model_validate(value)

    def accepted(self, target, point):
        # Reuse the preparer's own collapsed-insertion address checks.
        from .template_preparation import _guard_links, _insertion
        if target is None:
            return None
        selected = self.range(point, target)
        try:
            _insertion(self.content, selected)
            _guard_links(self.content, selected, self.probe)
        except (ValueError, RichMutationFailure):
            return None
        return target

    def piece_target(self, leaf, start, end):
        target = candidate(leaf)
        points = {start, end} | ({(start + end) // 2} if end - start > 1 else set())
        return target if target is not None and all(self.accepted(target, point) for point in points) else None

    def boundary(self, offset):
        nonempty = [leaf for leaf in self.leaves if leaf.end > leaf.start]
        inside = next((leaf for leaf in nonempty if leaf.start < offset < leaf.end), None)
        if inside is not None:
            target = self.accepted(candidate(inside), offset)
            return {'offset': offset, 'before': target, 'after': target}
        left = next((leaf for leaf in reversed(nonempty) if leaf.end == offset), None)
        right = next((leaf for leaf in nonempty if leaf.start == offset), None)
        before = {'kind': 'literal'} if offset == 0 else candidate(left) if left is not None else None
        after = {'kind': 'literal'} if offset == self.length else candidate(right) if right is not None else None
        return {'offset': offset, 'before': self.accepted(before, offset), 'after': self.accepted(after, offset)}


def container_kind(block):
    # Table cell IDs may equal 'content' or 'caption'; the block type decides.
    return 'cell' if isinstance(block, TableBlock) else 'caption' if isinstance(block, ImageBlock) else 'content'


def container_ref(block, key):
    if container_kind(block) != 'cell':
        return {'kind': container_kind(block), 'blockId': block.id, 'revision': block.revision}
    cell = next(cell for row in block.content.rows for cell in row.cells if cell.id == key)
    return {'kind': 'cell', 'blockId': block.id, 'revision': block.revision, 'cellId': key,
        'cellRevision': cell.revision}


def same_structure(before, after, block_id, key, steps):
    old, new = content_leaves(before), content_leaves(after)
    assignments = {value.address.inline_index: value for step in steps if isinstance(step, SetManualScopeDisplays)
        for value in step.assignments if value.address.block_id == block_id
        and (value.address.cell_id or value.address.field) == key}
    def retained(a, b):
        if span_ref(a) == span_ref(b):
            return True
        assignment = assignments.get(a.path[0]) if len(a.path) == 1 else None
        target = span_ref(b)
        target.pop('path', None)
        return (assignment is not None and assignment.before_hash == sha256(canonical(a.span))
            and assignment.after.model_dump(by_alias=True) == target)
    return content_text(before) == content_text(after) and len(old) == len(new) and all(
        (a.path, a.start, a.end) == (b.path, b.start, b.end) and retained(a, b) for a, b in zip(old, new))


class Spec:
    def __init__(self, block, key, content, regions):
        self.ref = container_ref(block, key) if block is not None else None
        self.content = content
        self.leaves = content_leaves(content) if content is not None else []
        self.regions = regions


def exact(output, specs, created, slot):
    for spec in specs:
        source_text = content_text(spec.content) if spec.content is not None else None
        for role, source, result in spec.regions:
            if result[1] > output.length or source is not None and (source[1] > units(source_text)
                    or utf16_slice(source_text, *source) != utf16_slice(output.text, *result)):
                raise NoCorrespondence
    cursor = 0
    for start, end in sorted(result for spec in specs for _role, _source, result in spec.regions):
        if start != cursor:
            raise NoCorrespondence
        cursor = end
    if cursor != output.length:
        raise NoCorrespondence
    by_id = {identity(leaf): (index, leaf) for index, spec in enumerate(specs) for leaf in spec.leaves
        if identity(leaf) is not None}
    found = [[] for _spec in specs]

    def segment(index, role, source, start, end, leaf, base=None):
        allocated = created.get(identity(leaf)[1]) if identity(leaf) is not None else None
        found[index].append({'role': role, 'result': {'start': start, 'end': end, 'span': span_ref(leaf)},
            'source': None if source is None else {'start': source[0], 'end': source[1], 'span': span_ref(base)},
            'target': output.piece_target(leaf, start, end),
            'slot': None if allocated is None else {'opId': allocated[0], 'slot': allocated[1]}})

    for leaf in output.leaves:
        if leaf.end > leaf.start:
            owner = [(index, region) for index, spec in enumerate(specs) for region in spec.regions
                if region[2][0] <= leaf.start and leaf.end <= region[2][1]]
            if len(owner) != 1:
                raise NoCorrespondence
            index, (role, source, result) = owner[0]
            if source is None:
                segment(index, role, None, leaf.start, leaf.end, leaf)
                continue
            shift = source[0] - result[0]
            low, high = leaf.start + shift, leaf.end + shift
            bases = [base for base in specs[index].leaves if base.end > base.start and base.start < high and base.end > low]
            if (len(bases) == 1 and (bases[0].start, bases[0].end) == (low, high)
                    and leaf_wire(bases[0]) == leaf_wire(leaf)):
                continue
            for base in bases:
                start, end = max(low, base.start), min(high, base.end)
                segment(index, role, (start, end), start - shift, end - shift, leaf, base)
            continue
        key = identity(leaf)
        if key is None:
            raise NoCorrespondence
        if key not in by_id:
            owner = [(index, region) for index, spec in enumerate(specs) for region in spec.regions
                if region[1] is None and region[2][0] <= leaf.start <= region[2][1]]
            if len(owner) != 1:
                raise NoCorrespondence
            segment(owner[0][0], 'inserted', None, leaf.start, leaf.start, leaf)
            continue
        index, base = by_id[key]
        sourced = [region for region in specs[index].regions if region[1] is not None]
        region = next((value for value in sourced if value[1][0] <= base.start < value[1][1]), None)
        if region is None and sourced and sourced[-1][1][1] == base.start:
            region = sourced[-1]
        if region is None or leaf.start != region[2][0] + base.start - region[1][0]:
            raise NoCorrespondence
        if leaf_wire(base) != leaf_wire(leaf):
            segment(index, region[0], (base.start, base.start), leaf.start, leaf.start, leaf, base)
    after_hash = sha256(canonical(content_wire(output.content)))
    result = []
    for index, spec in enumerate(specs):
        segments = found[index]
        edges = sorted({edge for value in segments for edge in (value['result']['start'], value['result']['end'])})
        result.append({'input': spec.ref, 'output': container_ref(output.block, output.key), 'created': slot,
            'beforeContentHash': sha256(canonical(content_wire(spec.content))) if spec.content is not None else None,
            'afterContentHash': after_hash, 'beforeLength': units(content_text(spec.content)) if spec.content is not None else None,
            'afterLength': output.length, 'correspondence': 'exact',
            'regions': [{'role': role, 'source': None if source is None else {'start': source[0], 'end': source[1]},
                'result': {'start': result_range[0], 'end': result_range[1]}} for role, source, result_range in spec.regions],
            'segments': segments, 'boundaries': [output.boundary(offset) for offset in edges]})
    return result


def none(output, input_block, input_key, input_content, slot):
    return [{'input': container_ref(input_block, input_key) if input_block is not None else None,
        'output': container_ref(output.block, output.key), 'created': slot,
        'beforeContentHash': sha256(canonical(content_wire(input_content))) if input_content is not None else None,
        'afterContentHash': sha256(canonical(content_wire(output.content))),
        'beforeLength': units(content_text(input_content)) if input_content is not None else None,
        'afterLength': output.length, 'correspondence': 'none', 'regions': [], 'segments': [], 'boundaries': []}]


def output_entries(output, old, previous, base_blocks, steps, operation, created, middle):
    if operation.kind in {'builtin_panel', 'resolve_template_sync', 'delete_entity', 'copy_blocks',
            'copy_fragment', 'paste_inline', 'paste_blocks'}:
        raise NoCorrespondence
    allocated = created.get(output.block.id) if old is None else None
    slot = None if allocated is None else {'opId': allocated[0], 'slot': allocated[1]}
    specs = None
    if old is None:
        expected = {SplitBlock: ['split', getattr(operation, 'block_id', None), 'right-block'],
            InsertParagraph: ['insert-paragraph', getattr(operation, 'context_block_id', None)]}.get(type(operation))
        if allocated is not None and expected is not None and allocated[1] == canonical(expected).decode() and container_kind(output.block) == 'content':
            if isinstance(operation, SplitBlock):
                source = base_blocks[operation.block_id]
                length = units(content_text(source.content))
                specs = [Spec(source, 'content', source.content, [('retained_suffix', (operation.offset, length),
                    (0, length - operation.offset))])]
            else:
                inserted = output.length > 0 or any(leaf.start == leaf.end for leaf in output.leaves)
                specs = [Spec(None, None, None, [('inserted', None, (0, output.length))] if inserted else [])]
    elif isinstance(operation, SplitBlock) and old.id == operation.block_id and container_kind(output.block) == 'content':
        specs = [Spec(old, 'content', previous, [('retained_prefix', (0, operation.offset), (0, operation.offset))]
            if operation.offset else [])]
    elif isinstance(operation, MergeBlocks) and old.id == operation.leading_id and container_kind(output.block) == 'content':
        trailing = base_blocks[operation.trailing_id]
        leading_length, trailing_length = units(content_text(previous)), units(content_text(trailing.content))
        specs = [Spec(old, 'content', previous, [('retained_prefix', (0, leading_length), (0, leading_length))]),
            Spec(trailing, 'content', trailing.content, [('retained_suffix', (0, trailing_length),
                (leading_length, leading_length + trailing_length))])]
    elif previous is not None:
        replaced = [step for step in steps if isinstance(step, TemplateReplaceInlineRange)
            and step.block_id == old.id and (step.cell_id if container_kind(old) == 'cell' else step.field) == output.key
            and (step.cell_id is None) == (container_kind(old) != 'cell')]
        if len(replaced) == 1 and middle is not None:
            step, length = replaced[0], units(content_text(previous))
            added = units(content_text(step.content))
            regions = [('retained_prefix', (0, step.start), (0, step.start))] if step.start else []
            if middle == 'restyled':
                if added != step.end - step.start:
                    raise NoCorrespondence
                if step.end > step.start:
                    regions.append(('restyled', (step.start, step.end), (step.start, step.end)))
            elif added or any(leaf.start == leaf.end for leaf in content_leaves(step.content)):
                if utf16_slice(output.text, step.start, step.start + added) != content_text(step.content):
                    raise NoCorrespondence
                regions.append(('inserted', None, (step.start, step.start + added)))
            regions.append(('retained_suffix', (step.end, length), (step.start + added, step.start + added + length - step.end)))
            specs = [Spec(old, output.key, previous, regions)]
        elif not replaced and same_structure(previous, output.content, old.id, output.key, steps):
            specs = [Spec(old, output.key, previous, [('retained', (0, output.length), (0, output.length))])]
    if specs is None:
        raise NoCorrespondence
    return exact(output, specs, created, slot)


def address_containers(before, after, mutation, operation, created_ids, middle):
    created = {identifier: (op, slot) for op, slots in created_ids.items() for slot, identifier in slots.items()}
    base_blocks = {block.id: block for block in before.document.blocks()}
    result = []
    for block in after.document.blocks():
        old = base_blocks.get(block.id)
        old_groups = dict(inline_groups(old)) if old is not None else {}
        for key, content in inline_groups(block):
            previous = old_groups.get(key)
            if previous is not None and canonical(content_wire(previous)) == canonical(content_wire(content)):
                continue
            output = Output(block, key, content)
            try:
                found = output_entries(output, old, previous, base_blocks, mutation.steps, operation, created, middle)
                # Each output is checked alone, so an oversized or failed exact map never rejects the edit.
                for entry in found:
                    AddressContainerV1.model_validate(entry)
                result.extend(found)
            except (NoCorrespondence, RichMutationFailure, ValidationError):
                allocated = created.get(block.id) if old is None else None
                result.extend(none(output, old if previous is not None else None, key, previous,
                    None if allocated is None else {'opId': allocated[0], 'slot': allocated[1]}))
    return result


def build_address_map(response, request, prepared):
    containers = []
    if prepared.mutation is not None:
        containers = address_containers(response.workspace.project, prepared.preview.workspace.project,
            prepared.mutation, request.operations[0], prepared.created_ids, prepared.address_middle)
    return PreparedAddressMapV1(schemaVersion=1, clientMutationId=prepared.client_mutation_id,
        requestHash=prepared.request_hash, baseSnapshot=prepared.base_snapshot,
        resultSnapshot=prepared.preview.snapshot, containers=containers)


def address_map_sha256(value):
    return sha256(canonical(value))
