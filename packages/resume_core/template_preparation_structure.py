"""Prepare authored structure through the shared writer transaction."""

from pydantic import TypeAdapter

from .models.template_authoring import (CopyBlocks, CopyFragment, FormatBlocks, InsertParagraph,
    MergeBlocks, MoveBlock, PasteBlocks, RemoveOccurrences, SplitBlock)
from .models.template_document import TemplateBlock
from .rich_mutations import locate, parent_items, subtree
from .template_anchors import anchor_steps
from .template_authoring import (allocate_classified_blocks, copy_blocks, copy_fragment, inserted_paragraph, merge_blocks,
    move_occurrence_steps, split_block)
from .template_preparation_common import finish_preparation, prepared_response, validate_preparation
from .template_preparation_ids import EditIdAllocator, existing_ids
from .templates.compiler import canonical


def target(document, identifier, revision):
    found = locate(document, identifier)
    if found is None or found[0][found[1]].revision != revision:
        raise ValueError('stale authored block')
    return found


def placement(document, value):
    items, parent = parent_items(document, value.parent_id)
    if value.after_id is not None and value.after_id not in {block.id for block in items}:
        raise ValueError('authored placement sibling missing')
    return items, parent


def formatted(block, patch):
    if block.type not in {'paragraph', 'heading', 'bullet_list', 'numbered_list'}:
        raise ValueError('unsupported authored block formatting')
    data = block.model_dump(by_alias=True)
    if patch.block_kind is not None:
        data['type'] = patch.block_kind.type
        data['props'].pop('level', None)
        data['props'].pop('start', None)
        if patch.block_kind.type == 'heading':
            data['props']['level'] = patch.block_kind.level
        elif patch.block_kind.type == 'numbered_list':
            data['props']['start'] = patch.block_kind.start
    for key in ('alignment', 'text_color', 'background_color'):
        if key in patch.model_fields_set:
            alias = {'text_color': 'textColor', 'background_color': 'backgroundColor'}.get(key, key)
            data['props'][alias] = getattr(patch, key)
    result = TypeAdapter(TemplateBlock).validate_python(data)
    if 'alignment' in patch.model_fields_set:
        result.presentation.overrides.alignment = patch.alignment
    return result


def prepare_structure_edit(response, request, proof, *, clipboard=None):
    validate_preparation(response, request, proof)
    workspace = response.workspace
    before = workspace.project
    candidate = before.model_copy(deep=True)
    operation = request.operations[0]
    allocator = EditIdAllocator(proof, request.client_mutation_id, operation.op_id, existing_ids(workspace))
    steps, replacements = [], {}

    def put(block, parent_id, after_id):
        old = locate(before.document, block.id)
        items, _parent = parent_items(candidate.document, parent_id)
        found = locate(candidate.document, block.id)
        if found:
            if found[0] is not items:
                raise ValueError('content replacement cannot move its parent')
            found[0].pop(found[1])
        positions = {value.id: index for index, value in enumerate(items)}
        if after_id is not None and after_id not in positions:
            raise ValueError('authored placement sibling missing')
        items.insert(positions[after_id] + 1 if after_id else 0, block.model_copy(deep=True))
        steps.append({'kind': 'put_block', 'parentId': parent_id, 'afterId': after_id,
            'beforeRevision': old[0][old[1]].revision if old else None, 'block': block.model_dump(by_alias=True)})

    def replace(block):
        found = locate(candidate.document, block.id)
        previous = found[0][found[1] - 1].id if found[1] else None
        put(block, found[2].id, previous)

    def remove(identifier):
        found = locate(candidate.document, identifier)
        old = locate(before.document, identifier)
        for block in subtree(found[0][found[1]]):
            replacements[block.id] = []
        found[0].pop(found[1])
        steps.append({'kind': 'remove_block', 'blockId': identifier, 'beforeRevision': old[0][old[1]].revision})

    if isinstance(operation, SplitBlock):
        found = target(before.document, operation.block_id, operation.before_revision)
        left, right = split_block(found[0][found[1]], operation.offset, id_factory=allocator)
        replace(left)
        put(right, found[2].id, left.id)
        replacements[left.id] = [left.id, right.id]
    elif isinstance(operation, MergeBlocks):
        leading = target(before.document, operation.leading_id, operation.leading_revision)
        trailing = target(before.document, operation.trailing_id, operation.trailing_revision)
        if leading[0] is not trailing[0] or trailing[1] != leading[1] + 1:
            raise ValueError('merge requires adjacent authored siblings')
        joined = merge_blocks(leading[0][leading[1]], trailing[0][trailing[1]])
        # Remove the trailing container before adding its retained children to the survivor.
        remove(operation.trailing_id)
        for child in joined.children:
            replacements.pop(child.id, None)
            for descendant in subtree(child):
                replacements.pop(descendant.id, None)
        replace(joined)
        replacements[operation.trailing_id] = [operation.leading_id]
    elif isinstance(operation, (CopyBlocks, CopyFragment, InsertParagraph, PasteBlocks)):
        placement(candidate.document, operation.placement)
        if isinstance(operation, PasteBlocks):
            from .template_preparation_paste import retained_payload
            payload = retained_payload(response, operation, clipboard, 'blocks')
            copied = allocate_classified_blocks(payload.blocks, id_factory=allocator)
        elif isinstance(operation, CopyBlocks):
            sources = [target(before.document, value.block_id, value.before_revision) for value in operation.sources]
            order = {block.id: index for index, block in enumerate(before.document.blocks())}
            sources.sort(key=lambda found: order[found[0][found[1]].id])
            selected = {value.block_id for value in operation.sources}
            if any(selected & {child.id for child in subtree(found[0][found[1]]) if child.id != found[0][found[1]].id}
                    for found in sources):
                raise ValueError('copy selects both an ancestor and its descendant')
            copied = copy_blocks(before, [found[0][found[1]] for found in sources], id_factory=allocator)
        elif isinstance(operation, CopyFragment):
            from .template_preparation import _range_content
            selected = operation.source
            found = target(before.document, selected.block_id, selected.before_revision)
            block = found[0][found[1]]
            _range_content(block, selected)
            if selected.cell_id is not None or selected.field != 'content':
                raise ValueError('fragment block copy needs an authored text block')
            if selected.start == selected.end:
                return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
            copied = [copy_fragment(before, block, selected.start, selected.end, id_factory=allocator)]
        else:
            found = target(before.document, operation.context_block_id, operation.context_revision)
            copied = [inserted_paragraph(found[0][found[1]], operation.text, id_factory=allocator)]
        after = operation.placement.after_id
        for block in copied:
            put(block, operation.placement.parent_id, after)
            after = block.id
    elif isinstance(operation, MoveBlock):
        found = target(before.document, operation.block_id, operation.before_revision)
        items, _parent = placement(candidate.document, operation.placement)
        if operation.placement.parent_id in {block.id for block in subtree(found[0][found[1]])}:
            raise ValueError('cannot move a block into its own subtree')
        if operation.placement.after_id == operation.block_id:
            raise ValueError('cannot place a block after itself')
        steps, _conflicts = move_occurrence_steps(workspace, operation.block_id,
            operation.placement.parent_id, operation.placement.after_id, id_factory=allocator)
        if _conflicts:
            from .template_preparation_sync import move_conflict_steps
            steps += move_conflict_steps(workspace, request, allocator, steps, _conflicts)
        moving = locate(candidate.document, operation.block_id)
        block = moving[0].pop(moving[1])
        positions = {value.id: index for index, value in enumerate(items)}
        items.insert(positions[operation.placement.after_id] + 1 if operation.placement.after_id else 0, block)
    elif isinstance(operation, RemoveOccurrences):
        selected = [target(before.document, value.block_id, value.before_revision) for value in operation.blocks]
        descendants = {child.id for found in selected for child in subtree(found[0][found[1]])
            if child.id != found[0][found[1]].id}
        for value in operation.blocks:
            if value.block_id not in descendants:
                remove(value.block_id)
    elif isinstance(operation, FormatBlocks):
        identifiers = {value.block_id for value in operation.targets}
        for value in operation.targets:
            target(before.document, value.block_id, value.before_revision)
        # A parent replacement must not overwrite a separately formatted child.
        def visit(items):
            for block in list(items):
                visit(block.children)
                if block.id in identifiers:
                    changed = formatted(block, operation.patch)
                    if canonical(changed) != canonical(block):
                        replace(changed)
        visit(candidate.document.regions[0].blocks)
        visit(candidate.document.regions[1].blocks)
        visit(candidate.document.regions[2].blocks)
        # Existing parent/child targets use independent content writes.
        for step in steps:
            if step['kind'] == 'put_block':
                step['block']['children'] = []
                step['keepChildren'] = True
    else:
        raise ValueError('authored operation is not supported by structural preparation')
    if not steps or canonical(candidate) == canonical(before) and all(step['kind'] == 'move_block' for step in steps):
        return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
    steps += [step.model_dump(by_alias=True) for step in anchor_steps(before, replacements)]
    return finish_preparation(response, request, allocator, steps, candidate)
