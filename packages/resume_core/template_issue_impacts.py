"""Only content/entity/ownership changes can retire a retained import issue."""

from .models.rich_document import Hyperlink
from .models.rich_mutations import PutBlock, RemoveBlock
from .models.template_document import BoundLink
from .rich_fields import bound_link_fields, builtin_cell_values, field_key, inline_groups, occurrences


def _semantic(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json', by_alias=True)
    if isinstance(value, dict):
        return {key: _semantic(part) for key, part in value.items() if key not in {'revision', 'syncedFactRevision'}}
    if isinstance(value, list):
        return [_semantic(part) for part in value]
    return value


def _cells(project):
    result = {identifier: (record.id, _semantic(value))
        for identifier, (record, _key, value) in builtin_cell_values(project.facts.records).items()}
    result.update({cell.id: (record.id, _semantic(cell)) for record in project.facts.extensions
        if record.active for cell in record.cells})
    return result


def _atoms(block):
    result = []
    def append(key, text):
        if result and result[-1][0] == key:
            result[-1] = (key, result[-1][1] + text)
        else:
            result.append((key, text))
    def inline(span, container, link=None):
        if isinstance(span, (Hyperlink, BoundLink)):
            reference = [span.href]
            for child in span.content:
                inline(child, container, reference)
        else:
            append([container, link], span.text)
    for container, content in inline_groups(block):
        for span in content:
            inline(span, container)
    if isinstance(block.content, str):
        append(['code'], block.content)
    return result


def _stream(order, atoms, identifiers):
    result = []
    for identifier in sorted(identifiers & order.keys(), key=order.__getitem__):
        for key, text in atoms[identifier]:
            if result and result[-1][0] == key:
                result[-1] = (key, result[-1][1] + text)
            else:
                result.append((key, text))
    return result


def _preserved_blocks(before, after, request, old_blocks, new_blocks, touched):
    old_atoms = {identifier: _atoms(block) for identifier, block in old_blocks.items()}
    new_atoms = {identifier: _atoms(block) for identifier, block in new_blocks.items()}
    old_order = {identifier: index for index, identifier in enumerate(old_blocks)}
    new_order = {identifier: index for index, identifier in enumerate(new_blocks)}
    preserved = {identifier for identifier in old_blocks.keys() & new_blocks.keys()
        if old_atoms[identifier] == new_atoms[identifier]}
    def prove(identifiers):
        if _stream(old_order, old_atoms, identifiers) == _stream(new_order, new_atoms, identifiers):
            preserved.update(identifiers)
    puts = {step.block.id: step for step in request.steps if isinstance(step, PutBlock)}
    added = set(puts) - old_blocks.keys()
    for identifier in puts.keys() & old_blocks.keys():
        selected = {identifier}
        remaining = set(added)
        while True:
            following = {value for value in remaining if puts[value].after_id in selected}
            if not following:
                break
            selected.update(following)
            remaining -= following
            prove(selected)
    removed = {step.block_id for step in request.steps if isinstance(step, RemoveBlock)}
    for identifier in removed:
        for survivor in puts.keys() & old_blocks.keys():
            prove({identifier, survivor})
    groups = {}
    for project in (before, after):
        for key, group in occurrences(project.document).items():
            groups.setdefault(key, set()).update(set(group.block_ids) & touched)
    for identifiers in groups.values():
        if identifiers:
            prove(identifiers)
    for step in request.steps:
        if step.kind == 'set_authored_anchors':
            prove(set(step.before_block_ids) | set(step.after_block_ids))
    return preserved


def issue_impacts(before, after, request):
    old_records = {record.id: record for record in [*before.facts.records, *before.facts.extensions]
        if getattr(record, 'active', True)}
    new_records = {record.id: record for record in [*after.facts.records, *after.facts.extensions]
        if getattr(record, 'active', True)}
    old_cells, new_cells = _cells(before), _cells(after)
    affected = set(old_records.keys() ^ new_records.keys())
    affected.update(identifier for identifier in old_cells.keys() | new_cells.keys()
        if old_cells.get(identifier) != new_cells.get(identifier))
    for identifier in list(affected):
        for cells in (old_cells, new_cells):
            if identifier in cells:
                affected.add(cells[identifier][0])
    old_blocks = {block.id: block for block in before.document.blocks()}
    new_blocks = {block.id: block for block in after.document.blocks()}
    touched = set()
    def descend(block):
        touched.add(block.id)
        for child in block.children:
            descend(child)
    for step in request.steps:
        if isinstance(step, (PutBlock, RemoveBlock)):
            identifier = step.block.id if isinstance(step, PutBlock) else step.block_id
            for blocks in (old_blocks, new_blocks):
                if identifier in blocks:
                    descend(blocks[identifier])
        elif step.kind == 'replace_inline_range':
            touched.add(step.block_id)
    preserved = _preserved_blocks(before, after, request, old_blocks, new_blocks, touched)
    changed_blocks = {identifier for identifier, block in old_blocks.items()
        if identifier not in preserved and (identifier not in new_blocks or _atoms(block) != _atoms(new_blocks[identifier]))}
    old_groups, new_groups = occurrences(before.document), occurrences(after.document)
    for key, group in old_groups.items():
        current = new_groups.get(key)
        # Removing a display occurrence does not remove its current semantic cell.
        changed = current is not None and group.text != current.text
        changed |= current is None and bool(set(group.block_ids) & new_blocks.keys() & changed_blocks)
        if changed:
            affected.add(group.record_id)
            affected.update(getattr(span, 'cell_id', None) or field_key(span.record_id, span.field_key) for span in group.spans)
    def links(project):
        result = {}
        for value in bound_link_fields(project.document):
            ref = value.reference
            key = (value.role, ref.record_id, ref.field_key, ref.cell_id, ref.occurrence_id)
            result.setdefault(key, []).append(value.text)
        return {key: set(value) if key[0] == 'url' else ''.join(value) for key, value in result.items()}
    old_links, new_links = links(before), links(after)
    for key in old_links.keys() & new_links.keys():
        if old_links[key] != new_links[key]:
            affected.update([key[1], key[3]])
    old_relations = {relation.id: _semantic(relation) for relation in before.facts.relations}
    new_relations = {relation.id: _semantic(relation) for relation in after.facts.relations}
    affected.update(identifier for identifier in old_relations.keys() | new_relations.keys()
        if old_relations.get(identifier) != new_relations.get(identifier))
    for identifier in old_relations.keys() | new_relations.keys():
        if old_relations.get(identifier) != new_relations.get(identifier):
            for relations in (old_relations, new_relations):
                if identifier in relations:
                    affected.add(relations[identifier]['subjectId'])
    for identifier in list(affected):
        record = old_records.get(identifier) or new_records.get(identifier)
        if record is not None and hasattr(record, 'item_handle'):
            affected.add(record.item_handle)
    known = (old_records.keys() | new_records.keys() | old_cells.keys() | new_cells.keys()
        | old_relations.keys() | new_relations.keys() | old_blocks.keys() | new_blocks.keys())
    known.update(record.item_handle for record in [*old_records.values(), *new_records.values()]
        if hasattr(record, 'item_handle'))
    return affected | changed_blocks, known
