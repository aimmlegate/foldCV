"""Generic authored copies, fragments and styles do not change fact identity."""

import uuid
from types import SimpleNamespace

from .models.rich_document import FactFieldSpan, Hyperlink, SectionBlock, TableBlock, ImageBlock
from .models.template_document import BoundLink, ManualScopeSpan, PresentedHyperlink, PresentedText, TemplateParagraphBlock
from .models.template_facts import ManualEditScope, Relation
from .rich_fields import bound_link_fields, inline_groups, occurrences
from .rich_mutations import cut_inline, inline_text, locate, subtree
from .template_identity import capture_span
from .template_preparation_ids import allocate_id


def identity(prefix):
    return prefix + '-' + uuid.uuid4().hex


def _scope_fields(project, scopes):
    from .rich_fields import builtin_cell_values
    from .template_scope_occurrences import active_scope_cells
    active = active_scope_cells(project.facts)
    cells = {cell for scope in scopes for cell in active.get(scope, set())}
    return ([(record, key) for identifier, (record, key, _value) in builtin_cell_values(project.facts.records).items()
        if identifier in cells] + [(record, cell.field_key) for record in project.facts.extensions if record.active
            for cell in record.cells if cell.id in cells])


def citation_spans(project, span):
    if isinstance(span, ManualScopeSpan):
        result = [value.model_copy(deep=True) for value in span.citations]
        for record, key in _scope_fields(project, [span.scope_id]):
            for citation in citation_spans(project, SimpleNamespace(record_id=record.id, field_key=key)):
                if citation not in result:
                    result.append(citation)
        return result
    result = [value.model_copy(deep=True) for value in getattr(span, 'citations', [])]
    extension = next((r for r in project.facts.extensions if r.id == span.record_id), None)
    if extension is not None:
        cell = next((c for c in extension.cells if c.field_key == span.field_key), None)
        for value in cell.evidence if cell else []:
            if value not in result:
                result.append(value.model_copy(deep=True))
        return result
    record = next((r for r in project.facts.records if r.id == span.record_id), None)
    for witness in getattr(record, 'evidence', []):
        source = next((s for s in project.sources if s.id == witness.source_id and s.revision == witness.source_revision), None)
        unit = next((u for u in source.units if u.id == witness.unit_id and u.revision == witness.unit_revision), None) if source else None
        if unit is None:
            raise ValueError('copy cites missing retained source')
        offset = unit.text.find(witness.text)
        if offset >= 0 and unit.text.find(witness.text, offset + 1) < 0:
            value = capture_span(source, unit, offset, offset + len(witness.text))
        else:
            value = capture_span(source, unit)
        if value not in result:
            result.append(value)
    return result


def split_block(block, offset, *, id_factory=identity):
    if not isinstance(block.content, list) or isinstance(block, SectionBlock):
        raise ValueError('split requires an authored text block')
    length = sum(len(inline_text(part).encode('utf-16-le')) // 2 for part in block.content)
    if not 0 <= offset <= length:
        raise ValueError('split offset exceeds content')
    left, right = block.model_copy(deep=True), block.model_copy(deep=True)
    left.content = cut_inline(block.content, 0, offset, id_factory=id_factory, allocation_path=('split', block.id, 'left'))
    right.content = cut_inline(block.content, offset, length, id_factory=id_factory,
        allocation_path=('split', block.id, 'right'), empty_end=True)
    right.id, right.revision, right.children = allocate_id(id_factory, 'block', ['split', block.id, 'right-block']), 1, []
    for provenance in right.provenance:
        provenance.id = allocate_id(id_factory, 'citation', ['split-citation', block.id, provenance.id])
    return left, right


def _copy_classifier(project, selected_groups):
    from .template_scope_occurrences import scope_occurrences
    originals = occurrences(project.document)
    original_scopes = scope_occurrences(project.document)
    selected_scopes = {}
    for group in selected_groups:
        for span in group:
            if isinstance(span, ManualScopeSpan):
                selected_scopes.setdefault((span.scope_id, span.occurrence_id), []).append(span)
    complete_scopes = {key for key, selected in selected_scopes.items()
        if (original := original_scopes.get(key)) is not None
        and {value.fragment_id for value in selected} == {value.fragment_id for value in original.spans}
        and ''.join(value.text for value in selected) == original.text}
    def complete_scope(span):
        return (span.scope_id, span.occurrence_id) in complete_scopes
    selected = {}
    def link_lengths(groups):
        result = {}
        for group in groups:
            for span in group:
                if isinstance(span, BoundLink):
                    length = len(inline_text(span).encode('utf-16-le')) // 2
                    for reference in (span.label_binding, span.url_binding):
                        if reference is not None:
                            key = (reference.record_id, reference.field_key, reference.occurrence_id)
                            result[key] = result.get(key, 0) + length
        return result
    original_links = link_lengths([group for block in project.document.blocks() for _, group in inline_groups(block)])
    selected_links = link_lengths(selected_groups)
    for group in selected_groups:
        for span in group:
            for part in span.content if isinstance(span, BoundLink) else [span]:
                if isinstance(part, FactFieldSpan):
                    root = part.binding_root_id or part.binding_id
                    key = (part.record_id, part.field_key, root)
                    selected[key] = selected.get(key, 0) + len(part.text.encode('utf-16-le')) // 2
    def complete(part):
        root = part.binding_root_id or part.binding_id
        key = (part.record_id, part.field_key, root)
        original = originals.get(key)
        return getattr(part, 'complete', True) and original is not None and selected.get(key) == len(original.text.encode('utf-16-le')) // 2
    def literal(part):
        return PresentedText(type='text', text=part.text, styles=part.styles,
            presentation=part.presentation, citations=citation_spans(project, part))
    def complete_link(part):
        keys = [(reference.record_id, reference.field_key, reference.occurrence_id)
            for reference in (part.label_binding, part.url_binding) if reference is not None]
        return all(key in original_links and selected_links.get(key) == original_links[key] for key in keys) and all(
            complete(child) for child in part.content if isinstance(child, FactFieldSpan))
    def convert(part):
        if isinstance(part, ManualScopeSpan):
            if not complete_scope(part):
                return literal(part)
            return part
        if isinstance(part, FactFieldSpan):
            if complete(part):
                return part
            return literal(part)
        if isinstance(part, BoundLink):
            if not complete_link(part):
                children = [literal(child) if isinstance(child, FactFieldSpan) else child for child in part.content]
                if children:
                    for reference in (part.label_binding, part.url_binding):
                        if reference is not None:
                            for citation in citation_spans(project, reference):
                                if citation not in children[0].citations:
                                    children[0].citations.append(citation)
                return PresentedHyperlink(type='link', href=part.href, content=children, presentation=part.presentation) if part.href else children
            part.content = [convert(child) for child in part.content]
            return part
        return part
    return convert, complete, complete_link, complete_scope


def classify_inline(project, content):
    copied = [part.model_copy(deep=True) for part in content]
    convert, _, _, _ = _copy_classifier(project, [copied])
    converted = [convert(part) for part in copied]
    return [part for value in converted for part in (value if isinstance(value, list) else [value])]


def _copy_allocator(id_factory):
    roots, scope_roots = {}, {}
    def new_root(record_id, field_key, root):
        key = record_id, field_key, root
        if key not in roots:
            roots[key] = allocate_id(id_factory, 'occurrence', ['copy-occurrence', *key])
        return roots[key]
    def convert(part):
        if isinstance(part, ManualScopeSpan):
            key = part.scope_id, part.occurrence_id
            if key not in scope_roots:
                scope_roots[key] = allocate_id(id_factory, 'scope-occurrence', ['copy-scope-occurrence', *key])
            part.fragment_id = allocate_id(id_factory, 'manual-fragment', ['copy-scope-fragment', part.fragment_id])
            part.occurrence_id = scope_roots[key]
        elif isinstance(part, FactFieldSpan):
            root = part.binding_root_id or part.binding_id
            part.binding_id = allocate_id(id_factory, 'fragment', ['copy-fragment', part.binding_id])
            part.binding_root_id = part.occurrence_id = new_root(part.record_id, part.field_key, root)
        elif isinstance(part, BoundLink):
            part.content = [convert(child) for child in part.content]
            for reference in (part.label_binding, part.url_binding):
                if reference is not None:
                    reference.occurrence_id = new_root(reference.record_id, reference.field_key, reference.occurrence_id)
        return part
    return convert


def allocate_classified_inline(content, *, id_factory=identity):
    convert = _copy_allocator(id_factory)
    return [convert(part.model_copy(deep=True)) for part in content]


def copy_inline(project, content, *, id_factory=identity):
    return allocate_classified_inline(classify_inline(project, content), id_factory=id_factory)


def _copied_tree(items):
    for block in items:
        yield block
        yield from _copied_tree(block.children)


def classify_blocks(project, blocks):
    copied = [block.model_copy(deep=True) for block in blocks]
    convert, complete, complete_link, complete_scope = _copy_classifier(project,
        [group for block in _copied_tree(copied) for _, group in inline_groups(block)])
    for block in _copied_tree(copied):
        incomplete = {(part.record_id, part.field_key) for _, group in inline_groups(block) for span in group
            for part in (span.content if isinstance(span, BoundLink) else [span])
            if isinstance(part, FactFieldSpan) and not complete(part)}
        incomplete.update((reference.record_id, reference.field_key)
            for _, group in inline_groups(block) for span in group if isinstance(span, BoundLink) and not complete_link(span)
            for reference in (span.label_binding, span.url_binding) if reference is not None)
        incomplete.update((record.id, key) for record, key in _scope_fields(project,
            {span.scope_id for _, group in inline_groups(block) for span in group
                if isinstance(span, ManualScopeSpan) and not complete_scope(span)}))
        block.provenance = [p for p in block.provenance if p.kind != 'working_owner' and not (
            p.kind == 'field_binding' and (p.record_id, p.field_key) in incomplete)]
        if isinstance(block, SectionBlock):
            block.props.record_id = None
        for _, group in inline_groups(block):
            converted = [convert(part) for part in group]
            group[:] = [part for value in converted for part in (value if isinstance(value, list) else [value])]
    return copied


def allocate_classified_blocks(blocks, *, id_factory=identity):
    copied = [block.model_copy(deep=True) for block in blocks]
    convert = _copy_allocator(id_factory)
    for block in _copied_tree(copied):
        source_id = block.id
        block.id, block.revision = allocate_id(id_factory, 'block', ['copy-block', source_id]), 1
        for provenance in block.provenance:
            provenance.id = allocate_id(id_factory, 'citation', ['copy-citation', source_id, provenance.id])
        if isinstance(block, TableBlock):
            for row in block.content.rows:
                row.id = allocate_id(id_factory, 'row', ['copy-row', source_id, row.id])
                for cell in row.cells:
                    cell.id, cell.revision = allocate_id(id_factory, 'table-cell', ['copy-cell', source_id, cell.id]), 1
        for _, group in inline_groups(block):
            group[:] = [convert(part) for part in group]
    return copied


def copy_blocks(project, blocks, *, id_factory=identity):
    return allocate_classified_blocks(classify_blocks(project, blocks), id_factory=id_factory)


class SourceFragmentKeys:
    def allocate(self, prefix, slot):
        if prefix not in {'binding', 'manual-fragment'} or slot[0] != 'fragment':
            raise ValueError('unsupported captured fragment')
        return slot[1]


def classify_fragment(project, block, start, end):
    if not isinstance(block.content, list) or isinstance(block, SectionBlock):
        raise ValueError('fragment capture requires a text block')
    length = sum(len(inline_text(part).encode('utf-16-le')) // 2 for part in block.content)
    if not 0 <= start <= end <= length:
        raise ValueError('capture range exceeds content')
    selected = block.model_copy(deep=True)
    selected.content = cut_inline(block.content, start, end, id_factory=SourceFragmentKeys(), empty_end=True)
    selected.children = []
    return classify_blocks(project, [selected])[0]


def copy_fragment(project, block, start, end, *, id_factory=identity):
    if not isinstance(block.content, list) or isinstance(block, SectionBlock):
        raise ValueError('fragment copy requires a text block')
    length = sum(len(inline_text(part).encode('utf-16-le')) // 2 for part in block.content)
    if not 0 <= start <= end <= length:
        raise ValueError('copy range exceeds content')
    selected = block.model_copy(deep=True)
    selected.content = cut_inline(block.content, start, end, id_factory=id_factory,
        allocation_path=('copy-fragment', block.id, start, end), empty_end=True)
    selected.children = []
    return copy_blocks(project, [selected], id_factory=id_factory)[0]


def merge_blocks(leading, trailing):
    if not isinstance(leading.content, list) or not isinstance(trailing.content, list) or isinstance(leading, SectionBlock) or isinstance(trailing, SectionBlock):
        raise ValueError('merge requires authored text blocks')
    result = leading.model_copy(deep=True)
    other = trailing.model_copy(deep=True)
    def inherit(part):
        if part.presentation is None:
            part.presentation = other.presentation.model_copy(deep=True) if other.presentation else None
            if part.presentation is not None:
                part.presentation.overrides.alignment = None
        styles = getattr(part, 'styles', None)
        if styles is not None:
            for key in ('text_color', 'background_color'):
                value = getattr(other.props, key, 'default')
                if getattr(styles, key) == 'default' and value != 'default':
                    setattr(styles, key, value)
        if isinstance(part, (Hyperlink, BoundLink)):
            for child in part.content:
                inherit(child)
    for part in other.content:
        inherit(part)
    result.content += other.content
    result.children += other.children
    result.provenance += [p for p in other.provenance if p.id not in {q.id for q in result.provenance}]
    return result


def inserted_paragraph(context, text='', *, id_factory=identity):
    props = {key: value for key, value in context.props.model_dump(by_alias=True).items()
        if key in {'alignment', 'textColor', 'backgroundColor'}}
    return TemplateParagraphBlock(type='paragraph', id=allocate_id(id_factory, 'block', ['insert-paragraph', context.id]), revision=1, props=props,
        content=[PresentedText(type='text', text=text, styles={})] if text else [],
        children=[], provenance=[], presentation=context.presentation.model_copy(deep=True) if context.presentation else None)


def duplicate_entity(facts, record_id, action_id, *, id_factory=identity):
    original = next((record for record in facts.extensions if record.id == record_id and record.active), None)
    if original is None:
        raise ValueError('entity copy target missing')
    record = original.model_copy(deep=True)
    record.retired_cell_ids = {}
    record.copy_of_record_id, record.id, record.item_handle, record.revision = original.id, allocate_id(
        id_factory, 'record', ['copy-entity', original.id]), allocate_id(id_factory, 'item', ['copy-item', original.id]), 1
    cells = {}
    for cell in record.cells:
        previous = cell.id
        cell.id, cell.revision = allocate_id(id_factory, 'cell', ['copy-cell', original.id, previous]), 1
        cell.origin, cell.user_corrected = 'human', True
        cells[previous] = cell.id
    scopes = []
    for scope in facts.manual_scopes:
        if any(cell.manual_scope_id == scope.id for cell in record.cells):
            copied = ManualEditScope(id=allocate_id(id_factory, 'manual', ['copy-scope', original.id, scope.id]), actionId=action_id, rawInput=scope.raw_input,
                cellIds=[cells[key] for key in scope.cell_ids if key in cells], blockIds=[])
            scopes.append(copied)
            for cell in record.cells:
                if cell.manual_scope_id == scope.id:
                    cell.manual_scope_id = copied.id
    for relation in record.relations:
        relation.id, relation.subject_id, relation.revision = allocate_id(id_factory, 'relation',
            ['copy-relation', original.id, relation.id]), record.id, 1
    return record, scopes


def move_occurrence_steps(workspace, block_id, parent_id, after_id=None, *, id_factory=identity):
    project = workspace.project
    found = locate(project.document, block_id)
    if found is None:
        raise ValueError('move target missing')
    block = found[0][found[1]]
    steps = [{'kind': 'move_block', 'blockId': block_id, 'beforeRevision': block.revision,
        'parentId': parent_id, 'afterId': after_id}]
    records = {record.id: record for record in [*project.facts.records, *project.facts.extensions]
        if getattr(record, 'active', True)}
    declarations = project.template_package.definition.fact_types
    types = {identifier: {record.semantic_type} if hasattr(record, 'semantic_type') else {
        definition.id for definition in declarations if definition.builtin_kind == record.kind}
        for identifier, record in records.items()}
    owner_types = {target for definition in declarations for relation in definition.relations
        if relation.kind in {'owned_by', 'extension_of'} for target in relation.target_types}
    primary = getattr(block.props, 'record_id', None)
    if primary is not None and types.get(primary, set()) & owner_types:
        return steps, []
    moved_ids = {child.id for child in subtree(block)}
    groups = {}
    for group in occurrences(project.document).values():
        groups.setdefault((group.record_id, group.root), set()).update(group.block_ids)
    for field in bound_link_fields(project.document):
        key = (field.reference.record_id, field.reference.occurrence_id)
        groups.setdefault(key, set()).add(field.block_id)
    candidates = {record_id for (record_id, _), ids in groups.items() if ids <= moved_ids}
    if primary is not None:
        candidates.add(primary)
    ancestors = []
    cursor = parent_id
    seen = set()
    while cursor not in seen:
        seen.add(cursor)
        parent = locate(project.document, cursor)
        if parent is None:
            if cursor not in {region.id for region in project.document.regions}:
                raise ValueError('move destination missing')
            break
        container = parent[0][parent[1]]
        owner = getattr(container.props, 'record_id', None)
        if owner is not None:
            ancestors.append(owner)
        ancestors.extend(value.record_id for value in container.provenance if value.kind == 'working_owner')
        cursor = parent[2].id
    conflicts = []
    for identifier in sorted(candidates):
        if identifier not in records:
            continue
        targets = {target for definition in declarations if definition.id in types[identifier]
            for relation in definition.relations if relation.kind == 'owned_by' for target in relation.target_types}
        destination = next((owner for owner in ancestors if types.get(owner, set()) & targets), None)
        if destination is None:
            continue
        relations = [relation for relation in project.facts.relations
            if relation.active and relation.kind == 'owned_by' and relation.subject_id == identifier]
        if len(relations) > 1:
            raise ValueError('move has ambiguous effective ownership')
        old = relations[0] if relations else None
        if old is None and not (getattr(records[identifier], 'subproject_id', None) or getattr(records[identifier], 'job_id', None)):
            continue
        if old is not None and old.target_id == destination:
            continue
        updated = old.model_copy(deep=True) if old else Relation(id=allocate_id(id_factory, 'relation',
            ['move-owner', identifier, destination]), kind='owned_by',
            subjectId=identifier, targetId=destination, revision=1, active=True)
        updated.target_id = destination
        steps.append({'kind': 'put_relation', 'beforeRevision': old.revision if old else None,
            'relation': updated.model_dump(by_alias=True)})
        conflicts.extend(root for (record_id, root), ids in groups.items()
            if record_id == identifier and not ids <= moved_ids)
    return steps, sorted(set(conflicts))
