"""Human raw cells and shared ambiguous input become one guarded fact patch."""

from .rich_fields import builtin_cell_values, working_field
from .template_preparation_ids import allocate_id


def human_cell_steps(workspace, cell_ids, text, action_id, block_ids, allocator, *, ambiguous=False):
    identifiers = sorted(cell_ids)
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError('human input needs distinct current cells')
    facts = workspace.project.facts
    builtin = builtin_cell_values(facts.records)
    extension = {cell.id: (record, cell.field_key, cell) for record in facts.extensions
        if record.active for cell in record.cells}
    cells = {**builtin, **extension}
    if any(identifier not in cells for identifier in identifiers):
        raise ValueError('human input targets a missing current cell')
    ambiguous = ambiguous or len(identifiers) > 1
    scope_id = allocate_id(allocator, 'manual', ['manual-scope', identifiers]) if ambiguous else None
    changed, previous, references = {}, {}, []
    for identifier in identifiers:
        record, key, _value = cells[identifier]
        previous[record.id] = record
        updated = changed.setdefault(record.id, record.model_copy(deep=True))
        value = working_field(updated, key)
        if identifier in extension:
            value.raw_input, value.typed_value = '' if ambiguous else text, None
            value.state, value.origin, value.user_corrected = 'pending_manual' if ambiguous else 'human_raw', 'human', True
            value.manual_scope_id = scope_id
        else:
            value.value, value.raw_text = None, '' if ambiguous else text
            value.status, value.pending_raw_text = ('pending', text) if ambiguous else ('unresolved', None)
            value.user_corrected = updated.user_corrected = True
            old_scope = facts.builtin_manual_scopes.get(identifier)
            if old_scope != scope_id:
                references.append({'kind': 'set_builtin_manual_scope', 'cellId': identifier,
                    'beforeScopeId': old_scope, 'afterScopeId': scope_id})
    steps = []
    if ambiguous:
        steps.append({'kind': 'put_manual_scope', 'scope': {'id': scope_id, 'actionId': action_id,
            'rawInput': text, 'cellIds': identifiers, 'blockIds': list(dict.fromkeys(block_ids))}})
    for identifier in sorted(changed):
        record = changed[identifier]
        steps.append({'kind': 'put_extension' if hasattr(record, 'cells') else 'put_record',
            'beforeRevision': previous[identifier].revision, 'record': record.model_dump(by_alias=True)})
    return steps + references
