"""Apply coordinator-admitted extension replacements as one scoped candidate."""

from .models.rich_facts import RecordTombstone
from .models.template_facts import WorkingFactsV2
from .template_mutations import content, extension_content


def _effective_value(cell):
    return (cell.raw_input, cell.typed_value, cell.evidence)


def has_human_authority(record):
    return any(cell.origin == 'human' or cell.user_corrected or cell.state in {'human_raw', 'pending_manual'}
        for cell in record.cells)


def _merge_supplied(previous, incoming):
    proposed = incoming.model_copy(deep=True)
    if not previous.active or (proposed.id, proposed.semantic_type, proposed.semantic_schema_hash,
            proposed.copy_of_record_id) != (previous.id, previous.semantic_type, previous.semantic_schema_hash,
            previous.copy_of_record_id):
        raise ValueError('replacement changes retained semantic identity')
    previous_cells = {cell.id: cell for cell in previous.cells}
    for index, cell in enumerate(proposed.cells):
        old = previous_cells.get(cell.id)
        if old is not None and _effective_value(old) == _effective_value(cell):
            proposed.cells[index] = old.model_copy(deep=True)
        elif old is not None:
            if old.origin == 'human':
                raise ValueError('model replacement cannot overwrite human authority')
            cell.revision = old.revision + 1
    supplied = {cell.id: cell for cell in proposed.cells}
    proposed.cells = [supplied.pop(cell.id, cell.model_copy(deep=True)) for cell in previous.cells] + list(supplied.values())
    proposed.observation_ids = list(dict.fromkeys([*previous.observation_ids, *proposed.observation_ids]))
    return proposed


def apply_accepted_records(facts, records, allocations, lineage, *, accepted_handles, expected_revisions, action_id):
    existing = {record.item_handle: record for record in facts.extensions}
    allocated = {allocation.item_handle: allocation for allocation in allocations}
    incoming = {record.item_handle: record for record in records}
    if len(incoming) != len(records) or len(allocated) != len(allocations):
        raise ValueError('duplicate replacement identity')
    children = set()
    parents = set()
    for link in lineage:
        if (link.kind == 'add' and (link.parents or not link.children)
            or link.kind == 'split' and (len(link.parents) != 1 or len(link.children) < 2)
            or link.kind == 'merge' and (len(link.parents) < 2 or len(link.children) != 1)):
            raise ValueError('invalid replacement lineage cardinality')
        if children & set(link.children) or parents & set(link.parents) or len(set(link.children)) != len(link.children) or len(set(link.parents)) != len(link.parents):
            raise ValueError('duplicate replacement lineage')
        children.update(link.children)
        parents.update(link.parents)
        if not set(link.children) <= incoming.keys() or any(handle not in existing for handle in link.parents):
            raise ValueError('replacement lineage is outside retained scope')
        if set(link.children) & set(link.parents):
            raise ValueError('replacement cannot recycle a parent handle')
    if set(incoming) - set(existing) - children:
        raise ValueError('new records need explicit replacement lineage')
    for handle, record in incoming.items():
        allocation = allocated.get(handle)
        if allocation is None or (record.id, record.semantic_type) != (allocation.record_id, allocation.semantic_type):
            raise ValueError('replacement does not use application allocations')
        if any(allocation.cell_ids.get(cell.field_key) != cell.id for cell in record.cells):
            raise ValueError('replacement cell identity mismatch')
        if not record.active or any(cell.state != 'admitted' for cell in record.cells) or (
                record.copy_of_record_id is not None and handle not in existing):
            raise ValueError('model replacement must contain admitted cells')
    result = facts.model_copy(deep=True)
    changed = False
    groups = [(link.parents, link.children) for link in lineage if link.kind != 'add']
    groups += [([], [handle]) for link in lineage if link.kind == 'add' for handle in link.children]
    groups += [([], [handle]) for handle in incoming if handle in existing and handle not in children]
    for group_parents, group_children in groups:
        if not set(group_children) <= set(accepted_handles):
            continue
        if any(has_human_authority(existing[handle]) for handle in group_parents):
            continue
        replay = all(handle in existing and extension_content(existing[handle]) == extension_content(
            _merge_supplied(existing[handle], incoming[handle]))
            for handle in group_children)
        if replay and all(not existing[handle].active for handle in group_parents):
            continue
        for handle in [*group_parents, *[h for h in group_children if h in existing]]:
            if expected_revisions.get(handle) != existing[handle].revision:
                raise ValueError('stale replacement capture')
        retiring = {existing[handle].id for handle in group_parents}
        if any(relation.active and relation.target_id in retiring and relation.subject_id not in retiring
               and relation.kind in {'owned_by', 'extension_of'} for relation in result.relations):
            raise ValueError('replacement leaves an owned dependent without an accepted owner')
        for handle in group_children:
            proposed = incoming[handle].model_copy(deep=True)
            previous = existing.get(handle)
            if previous is not None:
                proposed = _merge_supplied(previous, proposed)
                if extension_content(proposed) == extension_content(previous):
                    continue
                proposed.revision = max([previous.revision + 1, *[cell.revision for cell in proposed.cells]])
                result.extensions[next(i for i, record in enumerate(result.extensions) if record.id == proposed.id)] = proposed
            else:
                proposed.revision = max([proposed.revision, *[cell.revision for cell in proposed.cells]])
                result.extensions.append(proposed)
            changed = True
            for relation in proposed.relations:
                if any(current.id == relation.id and current != relation for current in result.relations):
                    raise ValueError('replacement relation identity collision')
                if not any(current.id == relation.id for current in result.relations):
                    result.relations.append(relation)
        for handle in group_parents:
            parent = next(record for record in result.extensions if record.item_handle == handle)
            if not parent.active:
                raise ValueError('replacement parent was already retired by other work')
            parent.active = False
            parent.revision += 1
            result.tombstones.append(RecordTombstone(recordId=parent.id, revision=parent.revision,
                actionId=action_id, orderIndex=result.extensions.index(parent) + len(result.records)))
            changed = True
        for index, relation in enumerate(result.relations):
            if relation.active and (relation.subject_id in retiring or relation.target_id in retiring):
                updated = relation.model_copy(deep=True)
                updated.active = False
                updated.revision += 1
                result.relations[index] = updated
        for record in result.extensions:
            mirrored = [relation for relation in result.relations if relation.subject_id == record.id]
            if record.relations != mirrored:
                record.revision += 1
            record.relations = mirrored
    result.revision += bool(changed)
    return WorkingFactsV2.model_validate(result.model_dump(by_alias=True))
