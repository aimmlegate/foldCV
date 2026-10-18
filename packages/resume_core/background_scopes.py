"""Server-owned mutation scopes; query invalidation remains history metadata."""

from .agent_edits import semantic
from .models.agent import AgentEntityDependency
from .rich_dependencies import dependency, placements
from .rich_mutations import locate, subtree


def mutation_selectors(workspace, mutation):
    targets = set()
    for step in mutation.steps:
        if step.kind in {"put_record", "remove_record"}:
            targets.add(("record", step.record.id if step.kind == "put_record" else step.record_id))
            continue
        identifier = step.block.id if step.kind == "put_block" else step.block_id
        targets.add(("block", identifier))
        if step.kind in {"remove_block", "move_block"} or step.kind == "put_block" and not step.keep_children:
            targets.add(("ownership", identifier))
        if step.kind == "put_block" and not step.keep_children:
            for child in subtree(step.block):
                targets.update({("block", child.id), ("ownership", child.id)})
        if step.kind == "remove_block" or step.kind == "put_block" and not step.keep_children:
            found = locate(workspace.project.document, identifier)
            if found is not None:
                for child in subtree(found[0][found[1]]):
                    targets.update({("block", child.id), ("ownership", child.id)})
    result = []
    for kind, identifier in sorted(targets):
        try:
            stamp = dependency(workspace, kind, identifier)
        except ValueError:
            stamp = {"kind": kind, "id": identifier, "revision": 1, "fingerprint": None}
        result.append(AgentEntityDependency(kind="entity", stamp=stamp))
    return result


def query_touches(state, before, after, mutation):
    from .background_history import selector_key
    selectors = mutation_selectors(before, mutation)
    def value(workspace, selector):
        kind, identifier = selector.stamp.kind, selector.stamp.id
        if kind == "ownership":
            return placements(workspace.project.document).get(identifier)
        if kind == "block":
            found = locate(workspace.project.document, identifier)
            return semantic(found[0][found[1]]) if found else None
        return semantic(next((record for record in workspace.project.facts.records if record.id == identifier), None))
    unchanged = {(selector.stamp.kind, selector.stamp.id) for selector in selectors
        if value(before, selector) == value(after, selector)}
    blocks = {identifier for kind, identifier in unchanged if kind == "block"}
    records = {identifier for kind, identifier in unchanged if kind == "record"}
    structural = any(kind == "ownership" for kind, _identifier in unchanged)
    touched = set()
    for definition in state.history.definitions:
        if definition.selector.kind != "query":
            continue
        query = definition.selector.query
        if query.kind == "find" and (blocks or records) or query.kind == "context" and structural:
            touched.add(definition.key)
        elif query.kind == "document":
            targets = set(query.ids)
            for workspace in (before, after):
                for block in workspace.project.document.blocks():
                    if not query.ids or block.id in query.ids:
                        targets.update(child.id for child in subtree(block))
                    if block.type == "table" and any(cell.id in query.ids for row in block.content.rows for cell in row.cells):
                        targets.add(block.id)
            if blocks & targets:
                touched.add(definition.key)
        elif query.kind == "facts" and (records and (not query.ids or records & set(query.ids))):
            touched.add(definition.key)
    return touched | {selector_key(selector) for selector in selectors}
