"""Scoped template inverses extend existing rich history without a second cursor."""

from .models.rich_mutations import RichMutation
from .models.template_mutations import TemplateMutationV1
from .project_limits import INVERSE_BYTES
from .project_repository import RepositoryFailure
from .project_store import encoded
from .rich_dependencies import placements
from .rich_mutations import locate, parent_items, subtree
from .template_mutations import content, extension_content
from .template_anchors import coverage_sequence, coverage_target, issue_target


def semantic(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {key: semantic(part) for key, part in value.items() if key not in {"revision", "syncedFactRevision"}}
    if isinstance(value, list):
        return [semantic(part) for part in value]
    return value


def block_value(block):
    return semantic(block.model_dump(mode="json", by_alias=True, exclude={"children", "revision"}))


def inverse_mutation(before, after, *, mutation_id, session_id):
    original = {block.id: block for block in before.project.document.blocks()}
    resulting = {block.id: block for block in after.project.document.blocks()}
    added = set(resulting) - original.keys()
    shadow = after.project.document.model_copy(deep=True)
    steps = []
    facts_before = {record.id: record for record in before.project.facts.records}
    facts_after = {record.id: record for record in after.project.facts.records}
    tombstones = {item.record_id: item for item in after.project.facts.tombstones}
    for identifier, record in facts_before.items():
        current = facts_after.get(identifier)
        if current is None or semantic(current) != semantic(record):
            revision = current.revision if current else tombstones[identifier].revision if identifier in tombstones else None
            steps.append({"kind": "put_record", "beforeRevision": revision,
                "record": record.model_dump(mode="json", by_alias=True)})
    for identifier, record in facts_after.items():
        if identifier not in facts_before:
            steps.append({"kind": "remove_record", "recordId": identifier, "beforeRevision": record.revision})

    def missing_tree(block):
        value = block.model_copy(deep=True)
        value.children = [missing_tree(child) for child in block.children if child.id not in resulting]
        return value

    def place(block, parent_id, previous):
        found = locate(shadow, block.id)
        if found is not None:
            found[0].pop(found[1])
        siblings, _parent = parent_items(shadow, parent_id)
        position = next((index + 1 for index, sibling in enumerate(siblings) if sibling.id == previous), 0)
        if previous is not None and not any(sibling.id == previous for sibling in siblings):
            raise RepositoryFailure('PROTOCOL')
        siblings.insert(position, block)

    def visit(blocks, parent_id):
        previous = None
        for old in blocks:
            found = locate(shadow, old.id)
            if found is None:
                restored = missing_tree(old)
                steps.append({"kind": "put_block", "parentId": parent_id, "afterId": previous,
                    "beforeRevision": None, "block": restored.model_dump(mode="json", by_alias=True), "keepChildren": False})
                place(restored, parent_id, previous)
                current, moved = restored, False
            else:
                current = found[0][found[1]]
                actual_previous = next((sibling.id for sibling in reversed(found[0][:found[1]]) if sibling.id not in added), None)
                moved = found[2].id != parent_id or actual_previous != previous
                if before.schema_version == 7:
                    from .template_block_patches import block_hash
                    changed = block_hash(old) != block_hash(current)
                else:
                    changed = block_value(old) != block_value(current)
                if moved:
                    if old.id not in resulting:
                        raise RepositoryFailure('PROTOCOL')
                    steps.append({"kind": "move_block", "blockId": old.id, "beforeRevision": resulting[old.id].revision,
                        "parentId": parent_id, "afterId": previous})
                    place(current, parent_id, previous)
                if changed:
                    value = old.model_copy(deep=True)
                    value.children = []
                    position = placements(shadow)[old.id]
                    anchor = previous if moved else position[1]
                    if before.schema_version == 7:
                        from .template_block_patches import block_patch
                        steps.append({'kind': 'restore_authored_block_patch', 'blockId': old.id,
                            'beforeRevision': resulting[old.id].revision, 'beforeSemanticHash': block_hash(current),
                            'afterSemanticHash': block_hash(old), 'patch': block_patch(current, old)})
                    else:
                        steps.append({"kind": "put_block", "parentId": parent_id, "afterId": anchor,
                            "beforeRevision": resulting[old.id].revision, "block": value.model_dump(mode="json", by_alias=True),
                            "keepChildren": True})
                    value.children = current.children
                    place(value, parent_id, anchor)
            visit(old.children, old.id)
            previous = old.id

    for region in before.project.document.regions:
        visit(region.blocks, region.id)
    roots = [block.id for block in after.project.document.blocks() if block.id in added]
    for identifier in reversed(roots):
        found = locate(shadow, identifier)
        if found is None:
            continue
        if any(block.id not in added for block in subtree(found[0][found[1]])):
            raise RepositoryFailure('PROTOCOL')
        steps.append({"kind": "remove_block", "blockId": identifier, "beforeRevision": resulting[identifier].revision})
        found[0].pop(found[1])
    if not steps:
        return None
    from .models.template_mutations import TemplateTreeMutation
    mutation_type = TemplateTreeMutation if before.schema_version == 7 else RichMutation
    result = mutation_type(schemaVersion=1, projectId=before.project_id, clientMutationId=mutation_id,
        actionId=mutation_id, kind="undo", capture={"sessionId": session_id, "actionId": mutation_id,
            "actionToken": 0, "dependencies": []}, steps=steps)
    if len(encoded(result.model_dump(mode="json", by_alias=True))) > INVERSE_BYTES:
        raise RepositoryFailure('JOB_STORAGE_FULL')
    return result


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
    sequence = coverage_sequence(after.project)
    if coverage_sequence(before.project) != sequence:
        raise ValueError('history cannot replace immutable coverage sequence')
    for index, old in enumerate(before.project.import_coverage):
        current = after.project.import_coverage[index]
        if old.block_ids != current.block_ids:
            steps.append({'kind': 'set_authored_anchors', 'target': coverage_target(after.project, index, sequence).model_dump(by_alias=True),
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
    if len(encoded(result.model_dump(mode='json', by_alias=True))) > INVERSE_BYTES:
        raise RepositoryFailure('JOB_STORAGE_FULL')
    return result
