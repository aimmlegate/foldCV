"""Scoped template facts and issue changes join the canonical rich transaction."""

from dataclasses import dataclass

from .models.rich_facts import WorkingFacts
from .models.rich_mutations import MoveBlock, PutBlock, PutRecord, RemoveBlock, RemoveRecord, ReplaceInlineRange
from .models.template_facts import WorkingFactsV2
from .models.template_mutations import (PutExtension, RemoveExtension, PutRelation, RemoveRelation,
    PutManualScope, SetBuiltinManualScope, SetIssueState, SetAuthoredAnchors, RestoreAuthoredBlockPatch,
    SetManualScopeDisplays, TemplateMutationV1, PutTemplateSync, RemoveTemplateSync)
from .rich_fact_mutations import apply_record_mutations
from .template_facts import delete_subject


FACT_STEPS = (PutRecord, RemoveRecord, PutExtension, RemoveExtension, PutRelation, RemoveRelation, PutManualScope, SetBuiltinManualScope)
DOMAIN_STEPS = (*FACT_STEPS, SetIssueState, SetAuthoredAnchors, SetManualScopeDisplays, PutTemplateSync, RemoveTemplateSync)


def content(value):
    return value.model_dump(mode='json', by_alias=True, exclude={'revision'})


def extension_content(record):
    return {**content(record), 'cells': [content(cell) for cell in record.cells],
        'relations': [content(relation) for relation in record.relations]}


@dataclass(frozen=True)
class HistoryAuthorization:
    project_id: str
    document_revision: int
    session_id: str
    action_token: int
    origin_action_id: str
    request_sha256: str


def check_history(workspace, request, authorization):
    from .rich_mutations import mutation_sha256
    if request.history.kind == 'edit':
        if any(isinstance(step, RestoreAuthoredBlockPatch) or getattr(step, 'history_placement', None) is not None
                for step in request.steps):
            raise ValueError('authored block restoration requires retained history')
        return False
    expected = HistoryAuthorization(workspace.project_id, workspace.document_revision,
        request.capture.session_id, request.capture.action_token, request.history.origin_action_id,
        mutation_sha256(request))
    if authorization != expected:
        raise ValueError('history replay lacks current retained inverse authorization')
    return True


def check_tree_targets(steps):
    seen = {}
    for step in steps:
        if isinstance(step, DOMAIN_STEPS):
            continue
        identifier = step.block.id if isinstance(step, PutBlock) else step.block_id
        family = 'position' if isinstance(step, MoveBlock) else 'remove' if isinstance(step, RemoveBlock) else 'content'
        key = (family, step.cell_id, step.field) if isinstance(step, ReplaceInlineRange) else (family,)
        previous = seen.setdefault(identifier, set())
        if key in previous or previous and family == 'remove' or any(p[0] == 'remove' for p in previous):
            raise ValueError('duplicate authored mutation target')
        if family == 'content' and any(p[0] == 'content' and (len(p) == 1 or len(key) == 1) for p in previous):
            raise ValueError('overlapping authored mutation target')
        previous.add(key)


def _record_id(step):
    return step.record.id if isinstance(step, (PutRecord, PutExtension)) else step.record_id


def _cell_identity(cell):
    return (cell.id, cell.field_key, cell.evidence, cell.observation_ids, cell.admission_receipt_ids)


def _put_extension(facts, incoming, replay):
    records = {record.id: record for record in facts.extensions}
    old = records.get(incoming.id)
    if old is not None:
        immutable = ('id', 'item_handle', 'semantic_type', 'semantic_schema_hash', 'observation_ids', 'copy_of_record_id')
        if any(getattr(old, key) != getattr(incoming, key) for key in immutable):
            raise ValueError('extension edit replaces immutable identity or observations')
        supplied = {cell.field_key: cell for cell in incoming.cells}
        if any((cell.field_key not in supplied and not replay) or (
                cell.field_key in supplied and cell.id != supplied[cell.field_key].id) for cell in old.cells):
            raise ValueError('extension edit replaces cell identities')
        if old.active != incoming.active and not replay:
            raise ValueError('extension lifecycle requires deletion or retained history')
    elif incoming.copy_of_record_id is not None:
        parent = records.get(incoming.copy_of_record_id)
        if parent is None or not parent.active or incoming.semantic_type != parent.semantic_type:
            raise ValueError('entity copy has no compatible retained parent')
        if parent.observation_ids != incoming.observation_ids:
            raise ValueError('entity copy replaces retained observations')
        if len(parent.cells) != len(incoming.cells):
            raise ValueError('entity copy changes field identities')
        for source, copied in zip(parent.cells, incoming.cells, strict=True):
            if {k: v for k, v in content(source).items() if k not in {'id', 'manualScopeId', 'origin', 'userCorrected'}} != {
                    k: v for k, v in content(copied).items() if k not in {'id', 'manualScopeId', 'origin', 'userCorrected'}}:
                raise ValueError('entity copy changes retained cell values')
            if copied.origin != 'human' or not copied.user_corrected:
                raise ValueError('entity copy requires human authority')
    updated = incoming.model_copy(deep=True)
    updated.revision = max(getattr(old, 'revision', 0), incoming.revision) + 1
    for index, cell in enumerate(updated.cells):
        previous = next((value for value in old.cells if value.field_key == cell.field_key), None) if old is not None else None
        if previous is not None and _cell_identity(previous) != _cell_identity(cell):
            raise ValueError('extension edit replaces immutable cell evidence')
        if previous is not None and content(previous) == content(cell):
            updated.cells[index] = previous.model_copy(deep=True)
        else:
            copied = old is None and incoming.copy_of_record_id is not None
            if not replay and not copied and cell.state not in {'human_raw', 'pending_manual'}:
                raise ValueError('human edit cannot assert an admitted template value')
            cell.revision = max(getattr(previous, 'revision', 0), cell.revision) + 1
            updated.revision = max(updated.revision, cell.revision)
    if old is None:
        facts.extensions.append(updated)
    else:
        facts.extensions[facts.extensions.index(old)] = updated
    facts.tombstones = [item for item in facts.tombstones if item.record_id != updated.id]
    return updated


def _set_builtin_owner(facts, relation):
    if relation.kind != 'owned_by':
        return
    record = next((r for r in facts.records if r.id == relation.subject_id), None)
    if record is None or not hasattr(record, 'job_id'):
        return
    if not relation.active:
        return
    target = next((r for r in facts.records if r.id == relation.target_id), None)
    if target is not None and target.kind == 'employment':
        record.job_id = target.id
        if hasattr(record, 'subproject_id'):
            record.subproject_id = None
    elif target is not None and target.kind == 'subproject' and hasattr(record, 'subproject_id'):
        record.job_id, record.subproject_id = target.job_id, target.id
    else:
        raise ValueError('incompatible built-in owner')
    record.revision += 1


def apply_fact_steps(original, request, replay=False):
    steps = [step for step in request.steps if isinstance(step, FACT_STEPS)]
    if not steps:
        return original.model_copy(deep=True)
    records = {r.id: r for r in [*original.records, *original.extensions]}
    tombstones = {r.record_id: r for r in original.tombstones}
    relations = {r.id: r for r in original.relations}
    scopes = {scope.id: scope for scope in original.manual_scopes}
    touched = set()
    for step in steps:
        if isinstance(step, SetBuiltinManualScope):
            target = ('builtin-scope', step.cell_id)
            if original.builtin_manual_scopes.get(step.cell_id) != step.before_scope_id:
                raise ValueError('stale builtin manual scope reference')
        elif isinstance(step, PutManualScope):
            target = ('scope', step.scope.id)
            if step.scope.id in scopes and scopes[step.scope.id] != step.scope:
                raise ValueError('manual edit scope is immutable')
            if not replay and step.scope.action_id != request.action_id:
                raise ValueError('manual edit scope belongs to another action')
        else:
            relation_step = isinstance(step, (PutRelation, RemoveRelation))
            identifier = (step.relation.id if isinstance(step, PutRelation) else step.relation_id) if relation_step else _record_id(step)
            target = ('relation' if relation_step else 'record', identifier)
            current = relations.get(identifier) if relation_step else records.get(identifier) or tombstones.get(identifier)
            if step.before_revision != getattr(current, 'revision', None):
                raise ValueError('stale fact/relation mutation')
            if isinstance(step, RemoveRecord) and not any(r.id == identifier for r in original.records):
                raise ValueError('built-in deletion requires a built-in record')
            if isinstance(step, RemoveExtension) and not any(r.id == identifier and r.active for r in original.extensions):
                raise ValueError('extension deletion requires an active extension')
        if target in touched:
            raise ValueError('duplicate fact/relation mutation target')
        touched.add(target)
    result = original.model_copy(deep=True)
    for step in steps:
        if isinstance(step, (RemoveRecord, RemoveExtension)):
            result = delete_subject(result, step.record_id, request.action_id)
    builtin_steps = [step for step in steps if isinstance(step, PutRecord)]
    if builtin_steps:
        base = WorkingFacts(revision=result.revision, records=result.records, tombstones=result.tombstones,
            extraction=result.extraction, mode=result.mode)
        changed = apply_record_mutations(base, builtin_steps, request.action_id).facts
        result.records, result.tombstones = changed.records, changed.tombstones
        from .rich_fields import builtin_cell_values
        remaining = builtin_cell_values(result.records)
        result.builtin_manual_scopes = {cell: scope for cell, scope in result.builtin_manual_scopes.items()
            if cell in remaining}
    incoming_extensions = []
    for step in steps:
        if isinstance(step, PutExtension):
            incoming_extensions.append(_put_extension(result, step.record, replay))
        elif isinstance(step, PutManualScope) and step.scope.id not in scopes:
            result.manual_scopes.append(step.scope.model_copy(deep=True))
        elif isinstance(step, SetBuiltinManualScope):
            if step.after_scope_id is None:
                result.builtin_manual_scopes.pop(step.cell_id, None)
            else:
                result.builtin_manual_scopes[step.cell_id] = step.after_scope_id
    from .rich_fields import builtin_cell_values
    old_builtin = builtin_cell_values(original.records)
    new_builtin = builtin_cell_values(result.records)
    if not replay:
        for step in steps:
            if isinstance(step, PutManualScope) and any(identifier in old_builtin or identifier in new_builtin
                    for identifier in step.scope.cell_ids):
                if any((identifier in old_builtin or identifier in new_builtin)
                        and result.builtin_manual_scopes.get(identifier) != step.scope.id
                        for identifier in step.scope.cell_ids):
                    raise ValueError('new builtin manual scope needs every current cell reference')
    for step in steps:
        if not isinstance(step, SetBuiltinManualScope):
            continue
        if step.cell_id not in old_builtin and step.cell_id not in new_builtin:
            raise ValueError('builtin scope mutation targets a missing canonical field')
        current = new_builtin.get(step.cell_id)
        if (not replay and step.before_scope_id is not None and step.after_scope_id is None
                and current is not None and current[2].status == 'pending'):
            raise ValueError('pending builtin cell still needs its exact manual scope')
    for step in steps:
        if isinstance(step, (PutRelation, RemoveRelation)):
            previous = relations.get(step.relation.id if isinstance(step, PutRelation) else step.relation_id)
            if isinstance(step, RemoveRelation):
                updated = previous.model_copy(deep=True)
                updated.active = False
            else:
                updated = step.relation.model_copy(deep=True)
                if previous and (previous.subject_id != updated.subject_id or previous.kind != updated.kind):
                    raise ValueError('relation edit replaces identity')
            updated.revision = max(getattr(previous, 'revision', 0), updated.revision) + 1
            position = next((i for i, r in enumerate(result.relations) if r.id == updated.id), None)
            if position is None:
                result.relations.append(updated)
            else:
                result.relations[position] = updated
            _set_builtin_owner(result, updated)
    for record in result.extensions:
        mirrored = [relation for relation in result.relations if relation.subject_id == record.id]
        if record in incoming_extensions and {r.id: content(r) for r in record.relations} != {r.id: content(r) for r in mirrored}:
            raise ValueError('extension put conflicts with explicit relation changes')
        if record.relations != mirrored:
            record.revision += 1
        record.relations = mirrored
    result.revision = original.revision + 1
    return WorkingFactsV2.model_validate(result.model_dump(by_alias=True))


def apply_issue_steps(project, request, replay=False, *, before=None):
    original = {issue.id: issue for issue in project.import_issues}
    touched = set()
    impacts = None
    for step in request.steps:
        if not isinstance(step, SetIssueState):
            continue
        issue = original.get(step.issue_id)
        if issue is None or step.issue_id in touched:
            raise ValueError('missing or duplicate issue target')
        touched.add(step.issue_id)
        if (issue.lifecycle_id, issue.state, issue.imported_fingerprint) != (
                step.before_lifecycle_id, step.before_state, step.imported_fingerprint):
            raise ValueError('stale issue lifecycle')
        if not replay and (step.after_state == 'active' or step.before_state != 'active'):
            raise ValueError('ordinary edit cannot reactivate an imported issue')
        if not replay and step.action_id != request.action_id:
            raise ValueError('issue retirement belongs to another action')
        if not replay:
            if before is None:
                raise ValueError('issue retirement needs its original scope')
            from .template_issue_impacts import issue_impacts
            if impacts is None:
                impacts = issue_impacts(before, project, request)
            affected, known = impacts
            captured = next((value for value in before.import_issues if value.id == issue.id), issue)
            targets = set(captured.target_ids) if captured.target_ids else set(captured.block_ids)
            if not targets & known:
                targets.update(captured.block_ids)
            if not affected & targets:
                raise ValueError('issue retirement lacks a changed content or ownership scope')
        issue.lifecycle_id, issue.state = step.after_lifecycle_id, step.after_state
        issue.retired_by_action = step.action_id if step.after_state == 'retired' else None
