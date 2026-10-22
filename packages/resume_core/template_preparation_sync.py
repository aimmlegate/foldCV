"""Ownership conflicts reuse the canonical preparer and shared history."""

from .models.template_mutations import TemplateSyncWrite
from .template_preparation_common import finish_preparation, validate_preparation
from .template_preparation_ids import EditIdAllocator, existing_ids
from .template_synchronization import effective_owner, occurrence_blocks, resolution_source, row_hash


def move_conflict_steps(workspace, request, allocator, steps, conflicts):
    result = []
    previous = workspace.sync_records[-1].id if workspace.sync_records else None
    for step in steps:
        if step['kind'] != 'put_relation' or step['relation']['kind'] != 'owned_by':
            continue
        relation = step['relation']
        identifier = relation['subjectId']
        groups = occurrence_blocks(workspace.project, identifier)
        remaining = set(groups) & set(conflicts)
        if not remaining:
            continue
        old = next((value for value in workspace.project.facts.relations if value.id == relation['id']), None)
        before_owner = effective_owner(workspace.project, identifier, old.id if old else None)
        record = TemplateSyncWrite(schemaVersion=2,
            id=allocator.allocate('sync', ['move-conflict', identifier, relation['id']]),
            status='conflict', actionId=request.capture.action_id,
            blockIds=sorted(set().union(*groups.values())), fieldKeys=[], factIds=[identifier],
            dependencies=[], errorCode=None, kind='conflict', ready=False, proposedSteps=[],
            capture=request.capture.model_copy(deep=True),
            ownershipConflict={'recordId': identifier, 'relationId': relation['id'],
                'beforeOwnerId': before_owner, 'proposedOwnerId': relation['targetId'],
                'movedOccurrenceIds': sorted(groups.keys() - remaining), 'remainingOccurrenceIds': sorted(remaining)})
        result.append({'kind': 'put_template_sync', 'beforeHash': None,
            'placement': {'afterSyncId': previous}, 'record': record.model_dump(by_alias=True)})
        previous = record.id
    if not result:
        raise ValueError('ownership conflict has no supported subject')
    return result


def prepare_sync_resolution(response, request, proof):
    validate_preparation(response, request, proof)
    workspace = response.workspace
    operation = request.operations[0]
    source = resolution_source(workspace, operation.sync_id, operation.before_record_hash, operation.before_lifecycle_id)
    allocator = EditIdAllocator(proof, request.client_mutation_id, operation.op_id, existing_ids(workspace))
    payload = source.model_dump(by_alias=True, exclude={'lifecycle_id', 'dependencies'})
    payload.update(capture=request.capture.model_dump(by_alias=True), dependencies=[], ready=False, proposedSteps=[])
    superseded = TemplateSyncWrite.model_validate({**payload, 'status': 'stale', 'errorCode': 'SYNC_SUPERSEDED'})
    identifier = allocator.allocate('sync', ['resolution-result', source.id, source.lifecycle_id])
    result = TemplateSyncWrite.model_validate({**payload, 'id': identifier, 'actionId': request.capture.action_id,
        'status': 'conflict', 'errorCode': 'NARRATIVE_REQUIRES_SCOPED_EDIT',
        'resolutionOf': {'syncId': source.id, 'beforeRecordHash': row_hash(source), 'beforeLifecycleId': source.lifecycle_id}})
    steps = [{'kind': 'put_template_sync', 'beforeHash': row_hash(source), 'record': superseded.model_dump(by_alias=True)},
        {'kind': 'put_template_sync', 'beforeHash': None,
            'placement': {'afterSyncId': workspace.sync_records[-1].id}, 'record': result.model_dump(by_alias=True)}]
    return finish_preparation(response, request, allocator, steps, workspace.project.model_copy(deep=True))
