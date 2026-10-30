"""Materialize admitted current cells and exact source fallback into one rich tree."""

from ..models.template_document import RichDocumentV2
from ..models.template_workspace import SpanCoverage
from ..template_capture import item_identities
from ..template_effective import builtin_effective_cells, effective_cells
from ..template_identity import _bound_root, capture_span, line_spans, source_slice
from ..template_import import digest
from .captured_fields import capture_fields, ownership_parents, visible_path
from .focus import focus_durations
from .materialize_nodes import DisplayField, fallback_style, literal, locale_text, reference, render_nodes, render_plain_fields, stable_id
from .operations import display_pointer, operation_value
from ..rich_fields import field_key
from .projection import pointer_tokens
from .span_coverage import fallback_plan, overlaps, subtract_spans, union_spans, unit_key, without_line_break
from .store import verify_package


def scope_lines(sources, spans):
    """Each whole multi-line unit by its lines; any other span as it is."""
    units = {(source.id, source.revision, unit.id, unit.revision): (source, unit) for source in sources for unit in source.units}
    for span in spans:
        source, unit = units[unit_key(span)]
        whole = span.start == 0 and span.end == len(unit.text)
        yield from (line_spans(source, unit) or [span]) if whole else [span]


def shows_employer(cell):
    return cell is not None and bool(cell.raw_input or cell.manual_scope_id is not None)


def materialize(package, facts, operations, sources, *, operation_id, revision=1, as_of=None):
    verify_package(package)
    declarations = {value.id: value for value in package.definition.blocks}
    operation_ids = {value.id for value in package.definition.operations}
    current = {cell.id: cell for cell in effective_cells(facts, operations)}
    current.update({cell.id: cell for cell in builtin_effective_cells(facts, operations, include_raw=True)})
    active_records = {record.id for record in [*facts.records, *facts.extensions] if getattr(record, 'active', True)}
    record_order = {record.id: index for index, record in enumerate([*facts.records, *facts.extensions]) if record.id in active_records}
    fields, roots, unassigned = capture_fields(declarations, operations, current, record_order)
    # One declared period format applies to every period view.
    period_format = next(({'separator': value.parameters.separator, 'ongoingLabel': dict(value.parameters.ongoing_label)}
        for value in package.definition.operations if value.kind == 'format_period'), None)
    # Focus durations need the formatting date that ends an ongoing job; without it nothing is computed.
    durations = focus_durations(facts, as_of, package.definition.template.default_locale) if as_of is not None else {}
    # Stored operation results hide records in some views and list records of other blocks in others.
    hidden, compact, assigned = {}, {}, {}
    for value in package.definition.operations:
        stored = operation_value(operations, value.id)
        if stored is None:
            continue
        if value.kind == 'partition_employment':
            # The compact view names a job by its employer; a job with nothing to show there stays detailed.
            named = [record for record in stored['compact'] if shows_employer(current.get(field_key(record, 'employer')))]
            hidden.setdefault(stored['detailedBlock'], set()).update(named)
            compact[stored['compactBlock']] = named
        elif value.kind == 'assign_skills':
            for group, records in stored['hidden'].items():
                hidden.setdefault(group, set()).update(records)
            if stored['added']:
                assigned.setdefault(stored['uncertainGroup'], []).extend(stored['added'])
    fallbacks_by_view, uncited_by_view, missing_by_view, human_scopes = {}, {}, {}, []
    for operation in operations:
        tasks = {task.id: task for task in operation.tasks}
        attempts = {attempt.id: attempt for attempt in operation.attempts}
        allocated = {value.item_handle: value for value in item_identities(operation)}
        # Blocks run in parallel finish in any order (CT10); a stable sort reads them in declaration order.
        order = {task.id: index for index, task in enumerate(operation.tasks)}
        for proposal in sorted(operation.proposals, key=lambda value: order[attempts[value.attempt_id].task_id]):
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
                    # An entry extracted on its own (D117) is item 0 of its own reply; the block shows its entries in
                    # the facts' order, which the block's close set, like captured items.
                    shown = (str(record_order[identity.record_id]),) if task.entry is not None and root else root
                    roots[(declaration.id, identity.record_id)] = (shown, identity)
                cell = current.get(identifier)
                if identifier not in proposal.admitted_cell_ids or cell is None:
                    continue
                relative = tuple(tokens[len(root):])
                if cell.origin == 'human' and visible_path(declaration, relative):
                    human_scopes.extend(field.evidence)
                fields[(declaration.id, identifier)] = DisplayField(relative, identity.record_id, identity.item_handle, cell)
                unassigned.pop((declaration.id, identifier), None)
                # Without a declared period format an ongoing period has no readable label, so it shows source wording.
                if cell.state == 'uncertain' or (period_format is None and cell.origin != 'human' and cell.typed_value is True
                        and relative[-1:] == ('ongoing',)):
                    fallbacks_by_view.setdefault(declaration.id, []).extend(cell.evidence)
        for result in sorted(operation.task_results, key=lambda value: order[value.task_id]):
            if result.disposition == 'source_fallback':
                view = tasks[result.task_id].block_id
                if view in operation_ids:
                    # An operation has no view; the blocks it reads show their own source lines.
                    continue
                if view not in declarations:
                    raise ValueError('source fallback has no configured block view')
                uncited = isinstance(result.value, dict) and result.value.get('scope') == 'uncited'
                # Lines a review names as missing from the block are placed only where no view shows them yet.
                missing = set(result.value.get('leftoverOnly', ())) if isinstance(result.value, dict) else set()
                (uncited_by_view if uncited else fallbacks_by_view).setdefault(view, []).extend(
                    span for span in result.source_spans if digest(span) not in missing)
                missing_by_view.setdefault(view, []).extend(span for span in result.source_spans if digest(span) in missing)
    visible_by_view = {}
    for (view, identifier), field in [*fields.items(), *unassigned.items()]:
        if visible_path(declarations[view], field.relative):
            visible_by_view.setdefault(view, {})[identifier] = field.cell
    _fallback, suppressed, placements = fallback_plan(sources, fallbacks_by_view,
        {view: list(cells.values()) for view, cells in visible_by_view.items()}, protected_spans=human_scopes)
    ordered = sorted(declarations.values(), key=lambda value: (['header', 'sidebar', 'main'].index(value.placement.region), value.placement.order, value.id))
    # Lines of an uncited scope that no accepted value or cited fallback shows go once to the last such block on the page.
    occupied = [*[span for cells in visible_by_view.values() for cell in cells.values() for span in cell.evidence],
        *[span for spans in placements.values() for span in spans]]
    # A coverage gap's lines go to the block's own view, once, unless an accepted value or another fallback shows them
    # (LIVE-09: courses repeated the education lines, open source the portfolio items).
    for view in [declaration.id for declaration in ordered if missing_by_view.get(declaration.id)]:
        lines = [line for line in scope_lines(sources, missing_by_view[view]) if not any(overlaps(line, other) for other in occupied)]
        if lines:
            placements[view] = union_spans(sources, [*placements.get(view, []), *lines])
            occupied.extend(lines)
    leftover = [line for spans in uncited_by_view.values() for line in scope_lines(sources, spans)
        if not any(overlaps(line, other) for other in occupied)]
    if leftover:
        last = [declaration.id for declaration in ordered if declaration.id in uncited_by_view][-1]
        placements[last] = union_spans(sources, [*placements.get(last, []), *leftover])
    regions = {role: {'id': stable_id(operation_id, role), 'role': role, 'revision': revision, 'blocks': []}
        for role in ['header', 'sidebar', 'main']}
    coverage, displayed, owned, shown_scopes, shown_fallback = [], {}, set(), set(), []
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
    handle_of = {identity.record_id: identity.item_handle for value in operations for identity in item_identities(value)}
    cell_owners = {cell.id: (record.id, record.item_handle) for record in facts.extensions if record.active for cell in record.cells}
    for operation in operations:
        for identity in item_identities(operation):
            cell_owners.update({cell: (identity.record_id, identity.item_handle) for cell in identity.cell_ids.values()
                if identity.record_id in by_record})
    def add_coverage(span, handle, blocks, disposition, reason):
        coverage.append(SpanCoverage(span=span, itemHandle=handle, blockIds=blocks, disposition=disposition, reason=reason))
    def listed(declaration, sections, instance, selected, handle=None):
        """One section of records another block owns, rendered through this view's own nodes."""
        children, mounted = render_nodes(package, declaration, instance, selected, scopes, shown_scopes, period_format, durations)
        if children:
            sections.append({'type': 'section', 'id': stable_id(instance, 'item'), 'revision': 1, 'props': {'recordId': None},
                'content': [], 'children': children, 'provenance': [],
                'presentation': reference(package, declaration.id, fallback_style(declaration), instance, handle)})
            for identifier, blocks in mounted.items():
                displayed.setdefault(identifier, []).extend(blocks)
    for declaration in ordered:
        sections = []
        selected_roots = [value for (view, record), value in roots.items() if view == declaration.id
            and record not in hidden.get(view, ())]
        selected_roots.sort(key=lambda pair: (tuple(int(token) if token.isdecimal() else token for token in pair[0]), pair[1].item_handle))
        for root, primary in selected_roots:
            selected = []
            for (view, identifier), field in fields.items():
                if view != declaration.id or (view, identifier) in suppressed:
                    continue
                owners = primary_owner(field.record_id, view)
                if len(owners) > 1:
                    raise ValueError('materialized field has ambiguous application ownership')
                if primary.record_id in owners:
                    selected.append(field)
            instance = stable_id(operation_id, declaration.id, primary.item_handle)
            children, mounted = render_nodes(package, declaration, instance, selected, scopes, shown_scopes, period_format, durations)
            plain_fields = []
            for (view, identifier), field in unassigned.items():
                if view != declaration.id or (view, identifier) in suppressed:
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
        if declaration.id in compact:
            # The compact view names each old employment record by its current employer cell.
            listed(declaration, sections, stable_id(operation_id, declaration.id, 'compact'), [DisplayField(('items', str(index)), record,
                handle_of.get(record), current[field_key(record, 'employer')]) for index, record in enumerate(record
                    for record in compact[declaration.id] if record in active_records)])
        # An object view's list of independent records: the records below its root that no record of this view owns.
        listing = [field for (view, identifier), field in fields.items() if declaration.view.mode == 'object'
            and view == declaration.id and (view, identifier) not in suppressed and field.record_id not in hidden.get(view, ())
            and visible_path(declaration, field.relative) and not primary_owner(field.record_id, view)]
        records = [record for record in assigned.get(declaration.id, ())
            if record in active_records and field_key(record, 'display') in current]
        if records:
            # Technologies no group admitted appear once in the fallback group, through its own display binding.
            tokens = display_pointer(package.definition, declaration)
            names = [(record, handle_of.get(record), current[field_key(record, 'display')]) for record in records]
            if declaration.view.mode == 'items':
                for record, handle, cell in names:
                    listed(declaration, sections, stable_id(operation_id, declaration.id, 'assigned', handle),
                        [DisplayField(tuple(tokens[1:]), record, handle, cell)], handle)
            else:
                # They continue the group's own list after its last item.
                at = tokens.index('*')
                start = 1 + max((int(field.relative[at]) for field in listing if len(field.relative) > at
                    and field.relative[:at] == tuple(tokens[:at]) and field.relative[at].isdecimal()), default=-1)
                listing += [DisplayField((*tokens[:at], str(start + index), *tokens[at + 1:]), record, handle, cell)
                    for index, (record, handle, cell) in enumerate(names)]
        if listing:
            listed(declaration, sections, stable_id(operation_id, declaration.id, 'list'), listing)
        output = regions[declaration.placement.region]['blocks']
        # Each view shows its own placements; a line two failed blocks both cited shows once, in the first of them.
        paragraphs = []
        for span in subtract_spans(sources, placements.get(declaration.id, []), shown_fallback):
            shown_fallback.append(span)
            key = digest(span)
            shown = without_line_break(sources, span)
            if shown is None or not source_slice(sources, shown).strip():
                continue
            identifier = stable_id(operation_id, 'fallback', key)
            ref = reference(package, declaration.id, fallback_style(declaration),
                stable_id(operation_id, declaration.id, 'fallback'))
            text = literal(source_slice(sources, shown), ref)
            text.citations = [shown]
            paragraphs.append({'type': 'paragraph', 'id': identifier, 'revision': 1, 'props': {}, 'content': [text],
                'children': [], 'provenance': [], 'presentation': ref})
            add_coverage(shown, None, [identifier], 'fallback', 'exact source scope')
        # A block that shows only source lines keeps its own title (LIVE-09: projects text without "ПРОЕКТЫ").
        if sections or paragraphs:
            title = locale_text(declaration.view.title, package.definition.template.default_locale)
            if declaration.view.heading != 'none' and title:
                ref = reference(package, declaration.id, package.recipe.style.section_band.heading_style,
                    stable_id(operation_id, declaration.id, 'heading'))
                output.append({'type': 'heading', 'id': stable_id(operation_id, declaration.id, 'heading'), 'revision': 1,
                    'props': {'level': 1}, 'content': [literal(title, ref)], 'children': [], 'provenance': [], 'presentation': ref})
        output.extend(sections)
        output.extend(paragraphs)
    if set(placements) - set(declarations):
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
