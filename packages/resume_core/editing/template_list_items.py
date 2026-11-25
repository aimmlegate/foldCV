"""D181: an item added to a list block written again from the CV («Написать заново по резюме», F6b).

A list block shows each item of its kind as one bullet that binds one extension record with one cell. A new item is a
new record of that kind and a bullet made in the form of the list's present item bullets, with new ids: the list must
show at least one such item. The cell is stored as text the user applied (`human_raw`, as an Apply of a rewrite
stores a value); `written: "model"` adds the mark that a model wrote it (D179), so its words that its evidence lacks
show green until the user types in it or accepts it."""

from ..models.rich_document import FactFieldSpan
from ..models.template_authoring import AddListItem
from ..models.template_document import TemplateSectionBlock
from .template_preparation_blocks import changed_block_steps
from .template_preparation_common import allocator_for, finish_preparation, validate_preparation


def item_bullets(project, section):
    """The bullets of a list section that each show one whole cell of one extension record: [(bullet, record)]."""
    extensions = {record.id: record for record in project.facts.extensions if record.active}
    found = []
    for child in section.children:
        content = child.content if isinstance(child.content, list) else []
        spans = [span for span in content if isinstance(span, FactFieldSpan)]
        if child.type != 'bullet_list' or len(spans) != 1 or len(content) != 1 or child.children:
            continue
        record = extensions.get(spans[0].record_id)
        if record is not None and len(record.cells) == 1 and getattr(spans[0], 'cell_id', None) == record.cells[0].id:
            found.append((child, record))
    return found


def list_section(project, block_id):
    """The top-level list section with this id that shows at least one item bullet, or None."""
    section = next((block for region in project.document.regions for block in region.blocks if block.id == block_id), None)
    if not isinstance(section, TemplateSectionBlock) or section.presentation is None or not item_bullets(project, section):
        return None
    return section


def prepare_list_item(response, request, *, occupied=None):
    validate_preparation(response, request)
    workspace = response.workspace
    operation = request.operations[0]
    if not isinstance(operation, AddListItem):
        raise ValueError('list item preparation needs add_list_item')
    project = workspace.project
    section = list_section(project, operation.block_id)
    if section is None or section.revision != operation.before_revision:
        raise ValueError('stale or unknown list block')
    if operation.after_id is not None and operation.after_id not in {child.id for child in section.children}:
        raise ValueError('list item placement is outside the list')
    allocator = allocator_for(response, request, operation, occupied)
    form, peer = item_bullets(project, section)[0]
    slot = ['list-item', operation.op_id]
    record_id = allocator.allocate('record', [*slot, 'record'])
    cell_id = allocator.allocate('cell', [*slot, 'cell'])
    handle = allocator.allocate('item', [*slot, 'item'])
    occurrence = allocator.allocate('occurrence', [*slot, 'occurrence'])
    cell = peer.cells[0].model_copy(update={'id': cell_id, 'revision': 1, 'raw_input': operation.text, 'typed_value': None,
        'state': 'human_raw', 'origin': 'human', 'user_corrected': True, 'evidence': list(operation.evidence),
        'observation_ids': [], 'admission_receipt_ids': [], 'manual_scope_id': None})
    record = peer.model_copy(update={'id': record_id, 'item_handle': handle, 'revision': 1, 'cells': [cell],
        'relations': [], 'observation_ids': [], 'active': True})
    span = form.content[0].model_copy(update={'record_id': record_id, 'cell_id': cell_id, 'text': operation.text,
        'binding_id': allocator.allocate('fragment', [*slot, 'fragment']), 'binding_root_id': occurrence,
        'occurrence_id': occurrence, 'synced_fact_revision': 1, 'complete': True,
        'presentation': form.content[0].presentation.model_copy(update={'item_handle': handle})
        if form.content[0].presentation is not None else None})
    bullet = form.model_copy(update={'id': allocator.allocate('block', [*slot, 'block']), 'revision': 1,
        'content': [span], 'children': [], 'provenance': []})
    candidate = project.model_copy(deep=True)
    target = next(block for region in candidate.document.regions for block in region.blocks if block.id == section.id)
    ids = [child.id for child in target.children]
    target.children.insert(ids.index(operation.after_id) + 1 if operation.after_id is not None else 0, bullet)
    steps = [{'kind': 'put_extension', 'beforeRevision': None, 'record': record.model_dump(mode='json', by_alias=True)}]
    if operation.written == 'model':
        steps.append({'kind': 'set_model_written', 'cellId': cell_id, 'beforeActionId': None,
            'afterActionId': request.capture.action_id})
    tree, _replacements = changed_block_steps(project.document, candidate.document)
    return finish_preparation(response, request, allocator, steps + tree, candidate, kind='structure')
