"""Guard shared display membership, then change only explicit inline ownership."""

from .models.rich_document import TableBlock
from .models.template_document import ManualScopeSpan, PresentedText
from .models.template_mutations import ScopeDisplaySource, SetManualScopeDisplays
from .rich_fields import inline_groups
from .template_scope_occurrences import active_scope_cells
from .templates.compiler import canonical, sha256


def node_hash(span):
    return sha256(canonical(span))


def inline_addresses(document):
    for block in document.blocks():
        for container, content in inline_groups(block):
            cell = container if isinstance(block, TableBlock) else None
            field = 'content' if cell is not None else container
            for index, span in enumerate(content):
                yield (block.id, cell, field, index), block, content, span


def capture_source(project, scope_id, occurrence_id):
    scope = next((value for value in project.facts.manual_scopes if value.id == scope_id), None)
    cells = active_scope_cells(project.facts).get(scope_id)
    fragments = [{'blockId': address[0], 'cellId': address[1], 'field': address[2],
        'fragmentId': span.fragment_id, 'fragmentHash': node_hash(span)}
        for address, _block, _content, span in inline_addresses(project.document)
        if isinstance(span, ManualScopeSpan) and (span.scope_id, span.occurrence_id) == (scope_id, occurrence_id)]
    if scope is None or not cells or not fragments:
        raise ValueError('scope display source has no current authority or fragments')
    return ScopeDisplaySource(scopeId=scope_id, occurrenceId=occurrence_id, scopeHash=node_hash(scope),
        activeCellIds=sorted(cells), fragments=fragments)


def guard_scope_displays(project, request):
    seen, addresses = set(), set()
    for step in request.steps:
        if not isinstance(step, SetManualScopeDisplays):
            continue
        for source in step.sources:
            key = source.scope_id, source.occurrence_id
            if key in seen:
                raise ValueError('duplicate scope source across metadata steps')
            seen.add(key)
            actual = capture_source(project, *key)
            if (actual.scope_hash != source.scope_hash or set(actual.active_cell_ids) != set(source.active_cell_ids)
                    or sorted(actual.fragments, key=lambda value: value.fragment_id)
                        != sorted(source.fragments, key=lambda value: value.fragment_id)):
                raise ValueError('stale scope display membership, values or active cells')
        for assignment in step.assignments:
            address = assignment.address
            key = address.block_id, address.cell_id, address.field, address.inline_index
            if key in addresses:
                raise ValueError('duplicate scope assignment across metadata steps')
            addresses.add(key)


def apply_scope_displays(project, request, *, replay=False):
    locations = {address: (block, content, span) for address, block, content, span in inline_addresses(project.document)}
    changed_blocks = {}
    for step in request.steps:
        if not isinstance(step, SetManualScopeDisplays):
            continue
        sources = {(value.scope_id, value.occurrence_id) for value in step.sources}
        for assignment in step.assignments:
            address = assignment.address
            key = address.block_id, address.cell_id, address.field, address.inline_index
            location = locations.get(key)
            if location is None:
                raise ValueError('scope display assignment address is missing')
            block, content, span = location
            if node_hash(span) != assignment.before_hash:
                raise ValueError('scope display assignment values changed')
            if isinstance(span, ManualScopeSpan):
                if (span.scope_id, span.occurrence_id) not in sources:
                    raise ValueError('scope display assignment lacks its original source')
            elif not (replay and isinstance(span, PresentedText) and assignment.after.kind == 'manual_scope'):
                raise ValueError('literal-to-scope restoration requires retained history')
            values = dict(text=span.text, styles=span.styles.model_copy(deep=True),
                presentation=span.presentation, citations=[value.model_copy(deep=True) for value in span.citations])
            after = assignment.after
            if after.kind == 'literal':
                replacement = PresentedText(type='text', **values)
            else:
                replacement = ManualScopeSpan(type='manual_scope', scopeId=after.scope_id,
                    occurrenceId=after.occurrence_id, fragmentId=after.fragment_id, **values)
            content[address.inline_index] = replacement
            if replacement != span:
                changed_blocks[block.id] = block
                if address.cell_id is not None:
                    cell = next(value for row in block.content.rows for value in row.cells if value.id == address.cell_id)
                    cell.revision = max(cell.revision, project.document.revision) + 1
    for block in changed_blocks.values():
        block.revision = max(block.revision, project.document.revision) + 1


def guard_retained_scope_ownership(before, after, request, *, replay=False):
    if replay:
        return
    original_fragments = {span.fragment_id: (span.scope_id, span.occurrence_id)
        for _address, _block, _content, span in inline_addresses(before.document)
        if isinstance(span, ManualScopeSpan)}
    assigned = {(value.address.block_id, value.address.cell_id, value.address.field, value.address.inline_index): (step, value)
        for step in request.steps if isinstance(step, SetManualScopeDisplays) for value in step.assignments}
    for address, _block, _content, span in inline_addresses(after.document):
        if isinstance(span, ManualScopeSpan) and span.fragment_id in original_fragments:
            original = original_fragments[span.fragment_id]
            if (span.scope_id, span.occurrence_id) == original:
                continue
            step, assignment = assigned.get(address, (None, None))
            if (step is None or assignment.after.kind != 'manual_scope'
                    or (assignment.after.scope_id, assignment.after.occurrence_id, assignment.after.fragment_id)
                        != (span.scope_id, span.occurrence_id, span.fragment_id)
                    or not any((source.scope_id, source.occurrence_id) == original
                        and span.fragment_id in {fragment.fragment_id for fragment in source.fragments}
                        for source in step.sources)):
                raise ValueError('surviving original fragment changed ownership without its assignment')
