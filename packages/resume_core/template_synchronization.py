"""Synchronization rows share the guarded document transaction and its replay."""

from .models.template_mutations import PutTemplateSync, RemoveTemplateSync, TemplateSyncRecord
from .rich_dependencies import dependencies_current, dependency, fingerprint
from .rich_fields import bound_link_fields, occurrences, records_by_id
from .template_dependencies import selector
from .templates.compiler import canonical, sha256


def row_hash(record):
    return fingerprint(record) if record is not None else None


def occurrence_blocks(project, record_id):
    result = {value.root: set(value.block_ids) for value in occurrences(project.document).values()
        if value.record_id == record_id}
    for value in bound_link_fields(project.document):
        if value.reference.record_id == record_id:
            result.setdefault(value.reference.occurrence_id, set()).add(value.block_id)
    return result


def effective_owner(project, record_id, relation_id):
    records = records_by_id(project.facts)
    if record_id not in records:
        raise ValueError('ownership conflict subject missing')
    if relation_id is not None:
        relation = next((value for value in project.facts.relations if value.id == relation_id), None)
        if relation is None or not relation.active or relation.kind != 'owned_by' or relation.subject_id != record_id:
            raise ValueError('ownership conflict relation mismatch')
        return relation.target_id
    value = records[record_id]
    return getattr(value, 'subproject_id', None) or getattr(value, 'job_id', None)


def resolution_source(workspace, sync_id, before_hash, before_lifecycle_id):
    record = next((value for value in workspace.sync_records if value.id == sync_id), None)
    if (not isinstance(record, TemplateSyncRecord) or record.status != 'conflict'
            or row_hash(record) != before_hash or record.lifecycle_id != before_lifecycle_id
            or record.ownership_conflict is None):
        raise ValueError('resolution requires its exact supported ownership conflict')
    if record.capture is not None and not dependencies_current(workspace, record.dependencies):
        raise ValueError('resolution has stale dependencies')
    conflict = record.ownership_conflict
    groups = occurrence_blocks(workspace.project, conflict.record_id)
    records = records_by_id(workspace.project.facts)
    if (not set(record.fact_ids + [conflict.before_owner_id, conflict.proposed_owner_id]) <= records.keys()
            or effective_owner(workspace.project, conflict.record_id, conflict.relation_id) != conflict.proposed_owner_id
            or set(groups) != set(conflict.moved_occurrence_ids + conflict.remaining_occurrence_ids)
            or set(record.block_ids) != set().union(*groups.values())):
        raise ValueError('resolution ownership targets changed')
    for identifier in record.field_keys:
        dependency(workspace, 'field', identifier)
    return record


def guard_resolutions(before, request, steps):
    sources, results = set(), set()
    original = {value.id: value for value in before.sync_records}
    for step in steps:
        if not isinstance(step, PutTemplateSync) or step.before_hash is not None or step.record.resolution_of is None:
            continue
        value = step.record
        lineage = value.resolution_of
        source = resolution_source(before, lineage.sync_id, lineage.before_record_hash, lineage.before_lifecycle_id)
        prior = next((item for item in steps if isinstance(item, PutTemplateSync) and item.record.id == source.id), None)
        if (source.id in sources or value.id in original or prior is None or prior.before_hash != lineage.before_record_hash
                or prior.record.status != 'stale' or prior.record.error_code != 'SYNC_SUPERSEDED'
                or prior.record.ready or prior.record.proposed_steps
                or any(getattr(value, key) != getattr(source, key) for key in
                    ('ownership_conflict', 'block_ids', 'field_keys', 'fact_ids', 'kind'))
                or value.status != 'conflict' or value.error_code != 'NARRATIVE_REQUIRES_SCOPED_EDIT'
                or value.ready or value.proposed_steps):
            raise ValueError('invalid ownership resolution transaction')
        seen, cursor = {value.id}, source
        while cursor is not None:
            if cursor.id in seen:
                raise ValueError('cyclic template sync resolution lineage')
            seen.add(cursor.id)
            parent = getattr(cursor, 'resolution_of', None)
            cursor = original.get(parent.sync_id) if parent is not None else None
        sources.add(source.id)
        results.add(value.id)
    if results and (len(request.steps) != 2 * len(results) or any(not isinstance(step, PutTemplateSync)
            or step.record.id not in sources | results for step in request.steps)):
        raise ValueError('ownership resolution cannot carry unrelated writes')
    return sources, results


def guard_new_conflict(before, after, record, request):
    conflict = record.ownership_conflict
    if conflict is None:
        return
    from .rich_mutations import locate, subtree
    from .template_authoring import move_occurrence_steps
    moved_blocks = set()
    supported = set()
    for step in request.steps:
        if step.kind == 'move_block':
            found = locate(before.project.document, step.block_id)
            if found is not None:
                moved_blocks.update(value.id for value in subtree(found[0][found[1]]))
            derived, _conflicts = move_occurrence_steps(before, step.block_id, step.parent_id, step.after_id,
                id_factory=lambda prefix: 'sync-check-' + prefix)
            supported.update((value['relation']['subjectId'], value['relation']['targetId'])
                for value in derived if value['kind'] == 'put_relation')
    groups = occurrence_blocks(before.project, conflict.record_id)
    moved = {root for root, blocks in groups.items() if blocks <= moved_blocks}
    remaining = groups.keys() - moved
    old_relation = next((value for value in before.project.facts.relations if value.id == conflict.relation_id), None)
    old_owner = effective_owner(before.project, conflict.record_id,
        conflict.relation_id if old_relation is not None else None)
    if (old_owner != conflict.before_owner_id
            or effective_owner(after.project, conflict.record_id, conflict.relation_id) != conflict.proposed_owner_id
            or set(conflict.moved_occurrence_ids) != moved
            or set(conflict.remaining_occurrence_ids) != remaining
            or occurrence_blocks(after.project, conflict.record_id) != groups
            or record.status != 'conflict' or record.ready or record.proposed_steps
            or (conflict.record_id, conflict.proposed_owner_id) not in supported
            or set(record.block_ids) != set().union(*groups.values())
            or conflict.record_id not in record.fact_ids):
        raise ValueError('ownership conflict does not match the atomic move')


def final_dependencies(workspace, record, touched):
    targets = {(value.kind, value.id) for value in record.dependencies}
    targets.update(('block', identifier) for identifier in record.block_ids)
    targets.update(('record', identifier) for identifier in record.fact_ids)
    targets.update(('field', identifier) for identifier in record.field_keys)
    conflict = record.ownership_conflict
    if conflict is not None:
        targets.update(('record', identifier) for identifier in
            [conflict.record_id, conflict.before_owner_id, conflict.proposed_owner_id])
        if conflict.relation_id is not None:
            targets.add(('field', selector('relation', conflict.relation_id)))
        for blocks in occurrence_blocks(workspace.project, conflict.record_id).values():
            targets.update(('block', identifier) for identifier in blocks)
            targets.update(('ownership', identifier) for identifier in blocks)
    targets.discard(('field', selector('sync', record.id)))
    if any(('field', selector('sync', identifier)) in targets for identifier in touched):
        raise ValueError('template sync cannot depend on another row written in the same transaction')
    return [dependency(workspace, kind, identifier) for kind, identifier in sorted(targets)]


def apply_sync_steps(before, after, request, *, replay=False):
    steps = [value for value in request.steps if isinstance(value, (PutTemplateSync, RemoveTemplateSync))]
    original = {value.id: value for value in before.sync_records}
    resolved, resolutions = guard_resolutions(before, request, steps) if not replay else (set(), set())
    predecessors = {value.id: before.sync_records[index - 1].id if index else None
        for index, value in enumerate(before.sync_records)}
    seen = set()
    for step in steps:
        identifier = step.record.id if isinstance(step, PutTemplateSync) else step.sync_id
        existing = original.get(identifier)
        if identifier in seen or step.before_hash != row_hash(existing):
            raise ValueError('stale or duplicate template sync target')
        seen.add(identifier)
        if isinstance(step, RemoveTemplateSync):
            if not isinstance(existing, TemplateSyncRecord):
                raise ValueError('template sync removal target missing')
            continue
        if step.history_placement is not None and (not replay or existing is None
                or predecessors[identifier] != step.history_placement.before_after_sync_id):
            raise ValueError('template sync historical predecessor mismatch')
        if not replay:
            if step.record.lifecycle_id is not None or step.record.dependencies:
                raise ValueError('ordinary template sync cannot supply computed authority')
            if step.record.capture is None or step.record.capture != request.capture:
                raise ValueError('template sync requires exact current action capture')
            if existing is None:
                if step.record.action_id != request.action_id:
                    raise ValueError('new template sync belongs to another action')
                if identifier not in resolutions:
                    guard_new_conflict(before, after, step.record, request)
            elif step.record.action_id != existing.action_id:
                raise ValueError('template sync replaces originating action')
            elif (not isinstance(existing, TemplateSyncRecord) or identifier not in resolved
                    and (existing.capture is None or not dependencies_current(before, existing.dependencies))):
                raise ValueError('template sync replacement has stale authority')
            elif any(getattr(step.record, key) != getattr(existing, key) for key in
                    ('ownership_conflict', 'block_ids', 'field_keys', 'fact_ids', 'kind', 'resolution_of')):
                raise ValueError('template sync replacement changes its guarded scope')
    for step in steps:
        identifier = step.record.id if isinstance(step, PutTemplateSync) else step.sync_id
        existing = original.get(identifier)
        position = next((index for index, value in enumerate(after.sync_records) if value.id == identifier), None)
        if isinstance(step, RemoveTemplateSync):
            after.sync_records.pop(position)
            continue
        value = step.record.model_copy(deep=True)
        value.capture = request.capture.model_copy(deep=True)
        prior = getattr(existing, 'lifecycle_id', None)
        value.lifecycle_id = 'sync-life-' + sha256(canonical([request.client_mutation_id, identifier, prior]))
        if position is not None and step.history_placement is None:
            after.sync_records[position] = value
        else:
            if position is not None:
                after.sync_records.pop(position)
            predecessor = (step.history_placement.after_sync_id if step.history_placement is not None
                else step.placement.after_sync_id)
            if not replay and predecessor != (after.sync_records[-1].id if after.sync_records else None):
                raise ValueError('ordinary template sync creation must append')
            if predecessor is None:
                position = 0
            else:
                index = next((index for index, row in enumerate(after.sync_records) if row.id == predecessor), None)
                if index is None:
                    raise ValueError('template sync predecessor missing')
                position = index + 1
            after.sync_records.insert(position, value)
    for index, value in enumerate(after.sync_records):
        if value.id in seen:
            value.dependencies = final_dependencies(after, value, seen)
            after.sync_records[index] = TemplateSyncRecord.model_validate(value.model_dump(by_alias=True))


def inverse_sync_steps(before, after):
    original = {value.id: value for value in before.sync_records}
    current = {value.id: value for value in after.sync_records}
    steps = [{'kind': 'remove_template_sync', 'syncId': identifier, 'beforeHash': row_hash(record)}
        for identifier, record in current.items() if identifier not in original]
    predecessors = {value.id: after.sync_records[index - 1].id if index else None
        for index, value in enumerate(after.sync_records)}
    shadow = [value.id for value in after.sync_records if value.id in original]
    unchanged = {identifier for identifier, record in original.items()
        if row_hash(record) == row_hash(current.get(identifier))}
    if [identifier for identifier in shadow if identifier in unchanged] != [
            value.id for value in before.sync_records if value.id in unchanged]:
        raise ValueError('template history cannot reorder unchanged synchronization rows')
    previous = None
    for record in before.sync_records:
        existing = current.get(record.id)
        index = shadow.index(record.id) if record.id in shadow else None
        moved = index is not None and (shadow[index - 1] if index else None) != previous
        if record.id not in unchanged:
            if not isinstance(record, TemplateSyncRecord):
                raise ValueError('template history cannot replace a legacy synchronization row')
            value = {'kind': 'put_template_sync', 'beforeHash': row_hash(existing),
                'record': record.model_dump(mode='json', by_alias=True)}
            if existing is None:
                value['placement'] = {'afterSyncId': previous}
            elif moved:
                value['historyPlacement'] = {'beforeAfterSyncId': predecessors[record.id], 'afterSyncId': previous}
            steps.append(value)
            if index is not None:
                shadow.pop(index)
            if previous is not None and previous not in shadow:
                raise ValueError('inverse template sync predecessor missing')
            shadow.insert(shadow.index(previous) + 1 if previous is not None else 0, record.id)
        previous = record.id
    if shadow != [value.id for value in before.sync_records]:
        raise ValueError('template inverse synchronization order mismatch')
    return steps


def live_sync_record(workspace, sync_id, before_hash, before_lifecycle_id):
    record = next((value for value in workspace.sync_records if value.id == sync_id), None)
    if (not isinstance(record, TemplateSyncRecord) or record.capture is None
            or row_hash(record) != before_hash or record.lifecycle_id != before_lifecycle_id
            or not dependencies_current(workspace, record.dependencies)):
        raise ValueError('stale template sync authority')
    return record


def restore_sync_rows(current, restored, delta):
    from .project_repository import RepositoryFailure
    from pydantic import TypeAdapter
    from .models.rich_workspace import RichSyncRecord
    adapter = TypeAdapter(TemplateSyncRecord | RichSyncRecord)
    repositioned = {identifier for (kind, identifier), value in delta.items()
        if kind == 'sync_placement' and value[0] is not None}
    rows = [adapter.validate_python(restored[('sync', row.id)]) for row in current.sync_records
        if ('sync', row.id) in restored and row.id not in repositioned]
    pending = {identifier: value for (kind, identifier), value in restored.items()
        if kind == 'sync' and not any(row.id == identifier for row in rows)}
    while pending:
        progress = False
        for identifier, value in list(pending.items()):
            placement = delta.get(('sync_placement', identifier))
            if placement is None or placement[0] is None:
                raise RepositoryFailure('DEPENDENCY_CHANGED')
            predecessor = placement[0]['afterSyncId']
            if predecessor in pending:
                continue
            index = next((index for index, row in enumerate(rows) if row.id == predecessor), None)
            if predecessor is not None and index is None:
                raise RepositoryFailure('DEPENDENCY_CHANGED')
            rows.insert(index + 1 if index is not None else 0, adapter.validate_python(value))
            pending.pop(identifier)
            progress = True
        if not progress:
            raise RepositoryFailure('DEPENDENCY_CHANGED')
    previous, actual = None, {}
    for row in rows:
        actual[('sync_placement', row.id)] = {'afterSyncId': previous}
        previous = row.id
    if any(restored.get(key) != actual.get(key) for key in delta if key[0] == 'sync_placement'):
        raise RepositoryFailure('DEPENDENCY_CHANGED')
    return rows
