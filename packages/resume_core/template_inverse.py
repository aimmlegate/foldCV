"""Scoped template inverses extend existing rich history without a second cursor."""

from .background_inverse import inverse_mutation
from .background_limits import LIMITS
from .background_store import BackgroundFailure
from .models.template_mutations import TemplateMutationV1
from .project_store import encoded
from .template_mutations import content, extension_content
from .template_anchors import coverage_sequence, coverage_target, issue_target


def inverse_template_mutation(before, after, *, origin_action_id, mutation_id, session_id, action_token, kind='undo'):
    tree = inverse_mutation(before, after, mutation_id=mutation_id, session_id=session_id)
    steps = [step.model_dump(by_alias=True) for step in tree.steps] if tree else []
    original = {record.id: record for record in before.project.facts.extensions}
    current = {record.id: record for record in after.project.facts.extensions}
    removals = {step['recordId'] for step in steps if step['kind'] == 'remove_record'}
    removals.update(identifier for identifier, record in current.items()
        if record.active and (identifier not in original or not original[identifier].active))
    parent_edges = {}
    for relation in after.project.facts.relations:
        if relation.active and relation.kind in {'owned_by', 'extension_of'}:
            parent_edges.setdefault(relation.subject_id, set()).add(relation.target_id)
    for record in after.project.facts.records:
        owner = getattr(record, 'subproject_id', None) or getattr(record, 'job_id', None)
        if owner is not None:
            parent_edges.setdefault(record.id, set()).add(owner)
    def removed_ancestor(identifier, seen=None):
        seen = set() if seen is None else seen
        if identifier in seen:
            raise ValueError('cyclic inverse ownership')
        return any(parent in removals or removed_ancestor(parent, seen | {identifier})
            for parent in parent_edges.get(identifier, set()))
    roots = {identifier for identifier in removals if not removed_ancestor(identifier)}
    steps = [step for step in steps if step['kind'] != 'remove_record' or step['recordId'] in roots]
    for identifier, record in original.items():
        existing = current.get(identifier)
        if record.active and (existing is None or extension_content(record) != extension_content(existing)):
            steps.append({'kind': 'put_extension', 'beforeRevision': existing.revision if existing else None,
                'record': record.model_dump(by_alias=True)})
    for identifier in roots & current.keys():
        steps.append({'kind': 'remove_extension', 'recordId': identifier, 'beforeRevision': current[identifier].revision})
    old_relations = {relation.id: relation for relation in before.project.facts.relations}
    new_relations = {relation.id: relation for relation in after.project.facts.relations}
    for identifier, relation in old_relations.items():
        existing = new_relations.get(identifier)
        if existing is None or content(relation) != content(existing):
            steps.append({'kind': 'put_relation', 'beforeRevision': existing.revision if existing else None,
                'relation': relation.model_dump(by_alias=True)})
    for identifier, relation in new_relations.items():
        if identifier not in old_relations and relation.active:
            steps.append({'kind': 'remove_relation', 'relationId': identifier, 'beforeRevision': relation.revision})
    old_scopes = {scope.id: scope for scope in before.project.facts.manual_scopes}
    new_scopes = {scope.id: scope for scope in after.project.facts.manual_scopes}
    for identifier, scope in old_scopes.items():
        if identifier not in new_scopes:
            steps.append({'kind': 'put_manual_scope', 'scope': scope.model_dump(by_alias=True)})
    old_builtin = before.project.facts.builtin_manual_scopes
    new_builtin = after.project.facts.builtin_manual_scopes
    for identifier in sorted(old_builtin.keys() | new_builtin.keys()):
        if old_builtin.get(identifier) != new_builtin.get(identifier):
            steps.append({'kind': 'set_builtin_manual_scope', 'cellId': identifier,
                'beforeScopeId': new_builtin.get(identifier), 'afterScopeId': old_builtin.get(identifier)})
    if coverage_sequence(before.project) != coverage_sequence(after.project):
        raise ValueError('history cannot replace immutable coverage sequence')
    for index, old in enumerate(before.project.import_coverage):
        current = after.project.import_coverage[index]
        if old.block_ids != current.block_ids:
            steps.append({'kind': 'set_authored_anchors', 'target': coverage_target(after.project, index).model_dump(by_alias=True),
                'beforeBlockIds': current.block_ids, 'afterBlockIds': old.block_ids})
    current_issues = {issue.id: issue for issue in after.project.import_issues}
    for issue in before.project.import_issues:
        existing = current_issues.get(issue.id)
        if existing is None:
            raise ValueError('history cannot replace retained imported issues')
        mutable = {'block_ids', 'lifecycle_id', 'state', 'retired_by_action'}
        if existing.model_dump(exclude=mutable) != issue.model_dump(exclude=mutable):
            raise ValueError('history issue identity changed')
        if existing.block_ids != issue.block_ids:
            steps.append({'kind': 'set_authored_anchors', 'target': issue_target(existing).model_dump(by_alias=True),
                'beforeBlockIds': existing.block_ids, 'afterBlockIds': issue.block_ids})
        if (existing.lifecycle_id, existing.state, existing.retired_by_action) != (
                issue.lifecycle_id, issue.state, issue.retired_by_action):
            steps.append({'kind': 'set_issue_state', 'issueId': issue.id, 'beforeLifecycleId': existing.lifecycle_id,
                'beforeState': existing.state, 'afterLifecycleId': issue.lifecycle_id, 'afterState': issue.state,
                'actionId': issue.retired_by_action or origin_action_id, 'importedFingerprint': issue.imported_fingerprint})
    from .template_synchronization import inverse_sync_steps
    steps.extend(inverse_sync_steps(before, after))
    if not steps:
        return None
    result = TemplateMutationV1(schemaVersion=1, projectId=before.project_id, clientMutationId=mutation_id,
        actionId=mutation_id, kind=kind, capture={'sessionId': session_id, 'actionId': mutation_id,
            'actionToken': action_token, 'dependencies': []}, steps=steps,
        history={'kind': kind, 'originActionId': origin_action_id})
    if len(encoded(result.model_dump(mode='json', by_alias=True))) > LIMITS.inverse_bytes:
        raise BackgroundFailure('JOB_STORAGE_FULL')
    return result
