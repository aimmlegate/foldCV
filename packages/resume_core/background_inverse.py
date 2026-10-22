"""Build a scoped typed inverse without restoring an old whole workspace."""

from .agent_edits import semantic
from .background_limits import LIMITS
from .background_store import BackgroundFailure
from .models.rich_mutations import RichMutation
from .project_store import encoded
from .rich_dependencies import placements
from .rich_mutations import locate, parent_items, subtree


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
            raise BackgroundFailure("PROTOCOL")
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
                        raise BackgroundFailure("PROTOCOL")
                    steps.append({"kind": "move_block", "blockId": old.id, "beforeRevision": resulting[old.id].revision,
                        "parentId": parent_id, "afterId": previous})
                    place(current, parent_id, previous)
                if changed:
                    value = old.model_copy(deep=True)
                    value.children = []
                    position = placements(shadow)[old.id]
                    anchor = previous if moved else position[1]
                    if before.schema_version == 7:
                        from .canonical_patch import build_patch
                        from .template_block_patches import block_payload
                        steps.append({'kind': 'restore_authored_block_patch', 'blockId': old.id,
                            'beforeRevision': resulting[old.id].revision, 'beforeSemanticHash': block_hash(current),
                            'afterSemanticHash': block_hash(old), 'patch': build_patch(block_payload(current), block_payload(old))})
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
            raise BackgroundFailure("PROTOCOL")
        steps.append({"kind": "remove_block", "blockId": identifier, "beforeRevision": resulting[identifier].revision})
        found[0].pop(found[1])
    if not steps:
        return None
    from .models.template_mutations import TemplateTreeMutation
    mutation_type = TemplateTreeMutation if before.schema_version == 7 else RichMutation
    result = mutation_type(schemaVersion=1, projectId=before.project_id, clientMutationId=mutation_id,
        actionId=mutation_id, kind="undo", capture={"sessionId": session_id, "actionId": mutation_id,
            "actionToken": 0, "dependencies": []}, steps=steps)
    if len(encoded(result.model_dump(mode="json", by_alias=True))) > LIMITS.inverse_bytes:
        raise BackgroundFailure("JOB_STORAGE_FULL")
    return result
