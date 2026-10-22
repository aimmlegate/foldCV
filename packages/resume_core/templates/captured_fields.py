"""Select captured human text without inventing a nested presentation slot."""

from ..template_identity import _bound_root
from .materialize_nodes import DisplayField
from .projection import pointer_tokens


def visible_binding(declaration, binding):
    outer = ['*'] if declaration.view.mode == 'items' else []
    path = tuple(pointer_tokens(binding.pointer)[len(outer):])
    return visible_path(declaration, path)


def visible_path(declaration, path):
    for node in declaration.view.nodes:
        if node.type in {'join_items', 'tags', 'bullets'}:
            selected = [tuple(pointer_tokens(node.field)) + ('*',) +
                (tuple(pointer_tokens(node.item_field)) if node.item_field is not None else ())]
        elif node.type == 'period':
            selected = [tuple(pointer_tokens(node.field)) + (name,) for name in ['start', 'end', 'ongoing']]
        else:
            selected = [tuple(pointer_tokens(value)) for value in [*node.fields, node.field,
                node.name_field, node.url_field, node.experience_field] if value is not None]
        if any(len(path) == len(pattern) and all(expected == '*' or expected == actual
                for expected, actual in zip(pattern, path, strict=True)) for pattern in selected):
            return True
    return False


def capture_fields(declarations, operations, current, record_order):
    fields, roots, unassigned = {}, {}, {}
    for operation in operations:
        tasks = {task.block_id: task for task in operation.tasks}
        for identity in operation.captured_items:
            if identity.record_id not in record_order:
                continue
            for declaration in declarations.values():
                task = tasks.get(declaration.id)
                if task is None or identity.item_handle not in task.allowed_handles:
                    continue
                outer = ['*'] if declaration.view.mode == 'items' else []
                for binding in declaration.bindings:
                    if (binding.semantic_type != identity.semantic_type or binding.field not in identity.cell_ids
                            or not visible_binding(declaration, binding)):
                        continue
                    identifier = identity.cell_ids[binding.field]
                    item_root = _bound_root(binding.pointer, identity.semantic_type, binding.field, declaration.bindings)
                    if item_root == outer:
                        root = (str(record_order[identity.record_id]),) if outer else ()
                        roots[(declaration.id, identity.record_id)] = (root, identity)
                    cell = current.get(identifier)
                    if cell is None:
                        continue
                    field = DisplayField(tuple(pointer_tokens(binding.pointer)[len(outer):]),
                        identity.record_id, identity.item_handle, cell)
                    if item_root == outer:
                        fields[(declaration.id, identifier)] = field
                    elif cell.origin == 'human':
                        unassigned[(declaration.id, identifier)] = field
    return fields, roots, unassigned


def ownership_parents(facts):
    parents = {}
    for relation in facts.relations:
        if relation.active and relation.kind in {'owned_by', 'extension_of'}:
            parents.setdefault(relation.subject_id, set()).add(relation.target_id)
    for record in facts.records:
        owner = getattr(record, 'subproject_id', None) or getattr(record, 'job_id', None)
        if owner is not None and record.id not in parents:
            parents[record.id] = {owner}
    return parents
