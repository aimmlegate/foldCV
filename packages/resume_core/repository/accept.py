"""«Принять» in the tip of a green mark (F8 G8, D179): the user accepts what a model wrote, with its text unchanged.

A word mark names one value: it becomes the user's, so it loses its green marks and its «Проверьте значение». A block
mark names the block the import wrote whole: its notice is retired and each value the block shows is accepted. One
history action; Undo brings the marks back."""

from ..editing.mutations import apply_rich_mutation, subtree
from ..editing.template_preparation_text import _fields
from ..fact_records import set_human_cell
from ..fields import builtin_cell_values, inline_groups
from ..models.template_mutations import TemplateMutationV1
from .assistant_compiler import find_block

WRITTEN = 'IMPORT_TEXT_GENERATED'


def _block_cells(block):
    return {getattr(span, 'cell_id', None) for part in subtree(block) for _key, content in inline_groups(part)
        for span, _start, _end in _fields(content)} - {None}


def _issues(workspace, block_id):
    """The active notices of a written block that mark this line: they name it or a block around it."""
    project = workspace.project
    found = []
    for issue in project.import_issues:
        if issue.state != 'active' or issue.code != WRITTEN:
            continue
        named = [find_block(workspace, identifier) for identifier in issue.block_ids]
        if any(block is not None and block_id in {part.id for part in subtree(block)} for block in named):
            found.append(issue)
    return found


def accept_steps(workspace, *, cell_id=None, block_id=None, action_id):
    """(the fact steps of the user's «Принять», the written block's notices it retires); both empty when nothing is
    left to accept. ValueError for a target that does not exist."""
    project = workspace.project
    if (cell_id is None) == (block_id is None):
        raise ValueError('accept names one cell or one block')
    issues, cells = [], set()
    if cell_id is not None:
        cells.add(cell_id)
    else:
        if find_block(workspace, block_id) is None:
            raise ValueError('accept block missing')
        issues = _issues(workspace, block_id)
        for issue in issues:
            for identifier in issue.block_ids:
                block = find_block(workspace, identifier)
                if block is not None:
                    cells |= _block_cells(block)
    builtin = builtin_cell_values(project.facts.records)
    extension = {cell.id: record for record in project.facts.extensions if record.active for cell in record.cells}
    if cell_id is not None and cell_id not in builtin and cell_id not in extension:
        raise ValueError('accept cell missing')
    changed, steps = {}, []
    for identifier in sorted(cells):
        if identifier in builtin:
            record, _key, _value = builtin[identifier]
            updated = changed.setdefault(record.id, record.model_copy(deep=True))
            value = builtin_cell_values([updated])[identifier][2]
            if not value.user_corrected:
                value.user_corrected = updated.user_corrected = True
        elif identifier in extension:
            record = extension[identifier]
            updated = changed.setdefault(record.id, record.model_copy(deep=True))
            cell = next(value for value in updated.cells if value.id == identifier)
            if cell.origin != 'human' and cell.state == 'admitted':
                # The text stays; an edit of the user is a human raw cell, as typing leaves it.
                set_human_cell(updated, cell.field_key, cell.raw_input)
        if identifier in project.facts.model_written:
            steps.append({'kind': 'set_model_written', 'cellId': identifier,
                'beforeActionId': project.facts.model_written[identifier], 'afterActionId': None})
    originals = {record.id: record for record in [*project.facts.records, *project.facts.extensions]}
    for identifier, updated in changed.items():
        original = originals[identifier]
        if updated == original:
            continue
        steps.append({'kind': 'put_extension' if hasattr(updated, 'cells') else 'put_record',
            'beforeRevision': original.revision, 'record': updated.model_dump(by_alias=True)})
    return steps, issues


def accept(workspace, *, cell_id=None, block_id=None, action_id, client_mutation_id):
    """The workspace after the user's «Принять», or None when nothing changes. The notice of a written block is
    retired by this action itself: an ordinary edit retires one only by changing the block's text."""
    steps, issues = accept_steps(workspace, cell_id=cell_id, block_id=block_id, action_id=action_id)
    if not steps and not issues:
        return None
    result = workspace.model_copy(deep=True)
    if steps:
        capture = {'sessionId': 'accept', 'actionId': action_id, 'actionToken': 1, 'dependencies': []}
        mutation = TemplateMutationV1.model_validate({'schemaVersion': 1, 'projectId': workspace.project_id,
            'clientMutationId': client_mutation_id, 'actionId': action_id, 'kind': 'panel', 'capture': capture,
            'steps': steps, 'history': {'kind': 'edit', 'originActionId': None}})
        result, _replayed = apply_rich_mutation(workspace, mutation)
    retired = {issue.id for issue in issues}
    for issue in getattr(result.project, 'import_issues', []):
        if issue.id in retired:
            issue.lifecycle_id = 'issue-lifecycle-' + action_id + '-' + issue.id
            issue.state, issue.retired_by_action = 'retired', action_id
    return result
