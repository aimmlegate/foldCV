"""A bound link's URL edit changes its URL cell and target together; its label and other occurrences stay."""

from .models.template_document import BoundLink, FieldOccurrence
from .rich_fields import inline_groups
from .template_anchors import anchor_steps
from .template_preparation_blocks import changed_block_steps
from .template_preparation_cells import human_cell_steps
from .template_preparation_common import allocator_for, finish_preparation, prepared_response, validate_preparation


def prepare_link_target(response, request, *, occupied=None):
    validate_preparation(response, request)
    workspace, operation = response.workspace, request.operations[0]
    allocator = allocator_for(response, request, operation, occupied)
    candidate = workspace.project.model_copy(deep=True)
    block = next((value for value in candidate.document.blocks() if value.id == operation.block_id), None)
    if block is None or block.revision != operation.before_revision:
        raise ValueError('stale link block')
    links = [span for _container, content in inline_groups(block) for span in content if isinstance(span, BoundLink)
        and operation.occurrence_id in {value.occurrence_id for value in (span.label_binding, span.url_binding) if value is not None}]
    if len(links) != 1 or links[0].url_binding is None:
        raise ValueError('link target needs one bound URL')
    link, url = links[0], links[0].url_binding
    if link.href == operation.href:
        return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
    records = {record.id: record for record in workspace.project.facts.extensions if record.active}
    cell = next((value for value in getattr(records.get(url.record_id), 'cells', []) if value.id == url.cell_id), None)
    if cell is None or cell.manual_scope_id is not None:
        raise ValueError('link URL cell is missing or waits on a manual edit scope')
    link.href = operation.href
    if link.label_binding is None:
        # A URL-only link shows its exact URL, so its one occurrence changes with the target.
        if not link.content or any(not isinstance(child, FieldOccurrence) or (child.record_id, child.field_key, child.cell_id,
                child.occurrence_id) != (url.record_id, url.field_key, url.cell_id, url.occurrence_id) for child in link.content):
            raise ValueError('URL-only link shows other text')
        link.content[0].text, link.content[0].complete = operation.href, True
        del link.content[1:]
    steps = human_cell_steps(workspace, [url.cell_id], operation.href, request.capture.action_id, [block.id], allocator)
    tree, replacements = changed_block_steps(workspace.project.document, candidate.document)
    steps += tree + [value.model_dump(by_alias=True) for value in anchor_steps(workspace.project, replacements)]
    return finish_preparation(response, request, allocator, steps, candidate, kind='panel')
