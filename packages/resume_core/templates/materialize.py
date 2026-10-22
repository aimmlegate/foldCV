"""Materialize admitted current cells and exact source fallback into one rich tree."""

from ..models.template_document import RichDocumentV2
from ..models.template_workspace import SpanCoverage
from ..template_capture import item_identities
from ..template_effective import builtin_effective_cells, effective_cells
from ..template_identity import _bound_root, capture_span, source_slice
from ..template_import import digest
from .captured_fields import capture_fields, ownership_parents, visible_path
from .materialize_nodes import DisplayField, fallback_style, literal, locale_text, reference, render_nodes, render_plain_fields, stable_id
from .projection import pointer_tokens
from .span_coverage import fallback_plan, overlaps, union_spans, unit_key
from .store import verify_package


def materialize(package, facts, operations, sources, *, operation_id, revision=1):
    verify_package(package)
    declarations = {value.id: value for value in package.definition.blocks}
    current = {cell.id: cell for cell in effective_cells(facts, operations)}
    current.update({cell.id: cell for cell in builtin_effective_cells(facts, operations, include_raw=True)})
    active_records = {record.id for record in [*facts.records, *facts.extensions] if getattr(record, 'active', True)}
    record_order = {record.id: index for index, record in enumerate([*facts.records, *facts.extensions]) if record.id in active_records}
    fields, roots, unassigned = capture_fields(declarations, operations, current, record_order)
    fallbacks_by_view, human_scopes = {}, []
    for operation in operations:
        tasks = {task.id: task for task in operation.tasks}
        attempts = {attempt.id: attempt for attempt in operation.attempts}
        allocated = {value.item_handle: value for value in item_identities(operation)}
        for proposal in operation.proposals:
            task = tasks[attempts[proposal.attempt_id].task_id]
            declaration = declarations.get(task.block_id)
            if declaration is None or proposal.applied_receipt_id is None:
                continue
            for field in proposal.resolved_fields:
                identity = allocated[field.item_handle]
                identifier = identity.cell_ids[field.field_key]
                tokens = pointer_tokens(field.pointer)
                root = tuple(tokens[:1]) if declaration.view.mode == 'items' else ()
                item_root = _bound_root(field.pointer, identity.semantic_type, field.field_key, declaration.bindings)
                if tuple(item_root) == root and identity.record_id in active_records:
                    roots[(declaration.id, identity.record_id)] = (root, identity)
                cell = current.get(identifier)
                if identifier not in proposal.admitted_cell_ids or cell is None:
                    continue
                relative = tuple(tokens[len(root):])
                if cell.origin == 'human' and visible_path(declaration, relative):
                    human_scopes.extend(field.evidence)
                fields[(declaration.id, identifier)] = DisplayField(relative, identity.record_id, identity.item_handle, cell)
                unassigned.pop((declaration.id, identifier), None)
                if cell.state == 'uncertain' or cell.origin != 'human' and cell.typed_value is True and relative[-1:] == ('ongoing',):
                    fallbacks_by_view.setdefault(declaration.id, []).extend(cell.evidence)
        for result in operation.task_results:
            if result.disposition == 'source_fallback':
                view = tasks[result.task_id].block_id
                if view not in declarations:
                    raise ValueError('source fallback has no configured block view')
                fallbacks_by_view.setdefault(view, []).extend(result.source_spans)
    visible = {identifier: field.cell for (view, identifier), field in [*fields.items(), *unassigned.items()]
        if visible_path(declarations[view], field.relative)}
    fallback, suppressed, fallbacks_by_view = fallback_plan(sources, fallbacks_by_view, list(visible.values()), protected_spans=human_scopes)
    regions = {role: {'id': stable_id(operation_id, role), 'role': role, 'revision': revision, 'blocks': []}
        for role in ['header', 'sidebar', 'main']}
    coverage, displayed, owned, shown_scopes, shown_fallback = [], {}, set(), set(), set()
    scopes = {scope.id: scope for scope in facts.manual_scopes}
    parents = ownership_parents(facts)
    def primary_owner(identifier, view, seen=()):
        if (view, identifier) in roots:
            return {identifier}
        if identifier in seen:
            raise ValueError('cyclic materialized ownership')
        return set().union(*(primary_owner(parent, view, (*seen, identifier)) for parent in parents.get(identifier, set())))
    for (view, _identifier), field in unassigned.items():
        owners = primary_owner(field.record_id, view)
        if len(owners) != 1:
            raise ValueError('captured human field needs one reachable configured owner section')
    by_record = {record.id: record for record in [*facts.records, *facts.extensions] if getattr(record, 'active', True)}
    cell_owners = {cell.id: (record.id, record.item_handle) for record in facts.extensions if record.active for cell in record.cells}
    for operation in operations:
        for identity in item_identities(operation):
            cell_owners.update({cell: (identity.record_id, identity.item_handle) for cell in identity.cell_ids.values()
                if identity.record_id in by_record})
    def add_coverage(span, handle, blocks, disposition, reason):
        coverage.append(SpanCoverage(span=span, itemHandle=handle, blockIds=blocks, disposition=disposition, reason=reason))
    ordered = sorted(declarations.values(), key=lambda value: (['header', 'sidebar', 'main'].index(value.placement.region), value.placement.order, value.id))
    for declaration in ordered:
        sections = []
        selected_roots = [value for (view, _record), value in roots.items() if view == declaration.id]
        selected_roots.sort(key=lambda pair: (tuple(int(token) if token.isdecimal() else token for token in pair[0]), pair[1].item_handle))
        for root, primary in selected_roots:
            selected = []
            for (view, identifier), field in fields.items():
                if view != declaration.id or identifier in suppressed:
                    continue
                owners = primary_owner(field.record_id, view)
                if len(owners) > 1:
                    raise ValueError('materialized field has ambiguous application ownership')
                if primary.record_id in owners:
                    selected.append(field)
            instance = stable_id(operation_id, declaration.id, primary.item_handle)
            children, mounted = render_nodes(package, declaration, instance, selected, scopes, shown_scopes)
            plain_fields = []
            for (view, identifier), field in unassigned.items():
                if view != declaration.id or identifier in suppressed:
                    continue
                owners = primary_owner(field.record_id, view)
                if len(owners) > 1:
                    raise ValueError('materialized field has ambiguous application ownership')
                if primary.record_id in owners:
                    plain_fields.append(field)
            plain_fields.sort(key=lambda field: (record_order[field.record_id], field.cell.id))
            plain, plain_mounted = render_plain_fields(package, declaration, instance, plain_fields, scopes, shown_scopes)
            children.extend(plain)
            mounted.update(plain_mounted)
            if not children:
                continue
            section_id = stable_id(instance, 'item')
            owner_id = primary.record_id if primary.record_id not in owned else None
            if owner_id is not None:
                owned.add(owner_id)
            sections.append({'type': 'section', 'id': section_id, 'revision': 1,
                'props': {'recordId': owner_id}, 'content': [], 'children': children, 'provenance': [],
                'presentation': reference(package, declaration.id, fallback_style(declaration), instance, primary.item_handle)})
            for identifier, blocks in mounted.items():
                displayed.setdefault(identifier, []).extend(blocks)
        output = regions[declaration.placement.region]['blocks']
        if sections:
            title = locale_text(declaration.view.title, package.definition.template.default_locale)
            if declaration.view.heading != 'none' and title:
                ref = reference(package, declaration.id, package.recipe.style.section_band.heading_style,
                    stable_id(operation_id, declaration.id, 'heading'))
                output.append({'type': 'heading', 'id': stable_id(operation_id, declaration.id, 'heading'), 'revision': 1,
                    'props': {'level': 1}, 'content': [literal(title, ref)], 'children': [], 'provenance': [], 'presentation': ref})
            output.extend(sections)
        for span in fallback:
            key = digest(span)
            if key in shown_fallback or not any(overlaps(span, raw) for raw in fallbacks_by_view.get(declaration.id, [])):
                continue
            shown_fallback.add(key)
            identifier = stable_id(operation_id, 'fallback', key)
            ref = reference(package, declaration.id, fallback_style(declaration),
                stable_id(operation_id, declaration.id, 'fallback'))
            text = literal(source_slice(sources, span), ref)
            text.citations = [span]
            output.append({'type': 'paragraph', 'id': identifier, 'revision': 1, 'props': {}, 'content': [text],
                'children': [], 'provenance': [], 'presentation': ref})
            add_coverage(span, None, [identifier], 'fallback', 'exact source scope')
    if len(shown_fallback) != len(fallback):
        raise ValueError('source fallback has no materialized placement')
    for identifier, blocks in displayed.items():
        record, handle = cell_owners[identifier]
        for span in current[identifier].evidence:
            add_coverage(span, handle, blocks, 'multiple_views' if len(blocks) > 1 else 'accepted', 'configured field presentation')
    covered = union_spans(sources, [value.span for value in coverage])
    for source in sources:
        for unit in source.units:
            cursor = 0
            spans = [span for span in covered if unit_key(span) == (source.id, source.revision, unit.id, unit.revision)]
            for span in [*spans, capture_span(source, unit, len(unit.text), len(unit.text))]:
                if cursor < span.start:
                    add_coverage(capture_span(source, unit, cursor, span.start), None, [], 'source_only', 'retained outside configured field views')
                cursor = span.end
    document = RichDocumentV2(schemaVersion=2, revision=revision, regions=list(regions.values()))
    return document, coverage
