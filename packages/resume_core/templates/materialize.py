"""Materialize admitted current cells and exact source fallback into one rich tree."""

from ..models.template_document import RichDocumentV2
from ..models.template_workspace import SpanCoverage
from ..template_capture import item_identities
from ..editing.template_effective import builtin_effective_cells, effective_cells
from .source_spans import _bound_root
from ..sources import capture_span, line_spans, source_slice
from ..hashing import digest
from ..template_source_cleanup import without_contacts
from .captured_fields import capture_fields, ownership_parents, visible_path
from .focus import focus_durations
from .materialize_nodes import (DisplayField, fallback_style, heading_style, literal, locale_text, reference, render_nodes,
    render_plain_fields, row_section, stable_id)
from .operations import display_pointer, operation_value
from ..fields import field_key
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


def _stored_views(package, operations, current):
    """Stored operation results hide records in some views and list records of other blocks in others."""
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
    return hidden, compact, assigned


def _positions(sources):
    """A span's place in the document: its source, its unit's order, its start."""
    units = {(source.id, source.revision, unit.id, unit.revision): (index, unit.order)
        for index, source in enumerate(sources) for unit in source.units}
    return lambda span: (*units[unit_key(span)], span.start)


def _nearest(cards, position, span):
    """The card whose cited lines come last before the span; the first card when the span precedes them all.
    `cards`: card -> positions of its cited lines, in the cards' order."""
    at = position(span)
    before = [(max(value for value in places if value <= at), -index, card)
        for index, (card, places) in enumerate(cards.items()) if any(value <= at for value in places)]
    if before:
        return max(before)[2]
    after = [(min(places), index, card) for index, (card, places) in enumerate(cards.items()) if places]
    return min(after)[2] if after else next(iter(cards))


def _place_kept(sources, kept, unshown, homes, task_cards, occupied, placements, missing_by_view):
    """The lines a task that kept its values still shows (D156), each in the entry it belongs to: the lines of a value it
    does not show in that value's card, and lines no shown value covers (an omission) only once, in the card that cites
    the lines before them. A task without a card in its view places them in the block. Returns {(view, card): spans}."""
    position, result = _positions(sources), {}
    def owners(task_id, cards, span):
        found = {homes[(proposal, root)] for task, proposal, root, evidence in unshown if task == task_id
            and homes.get((proposal, root)) in cards and any(overlaps(span, raw) for raw in evidence)}
        return found or ({_nearest(cards, position, span)} if cards else set())
    for view, task_id, cited, left in kept:
        cards = task_cards.get((view, task_id), {})
        for span in cited:
            found = owners(task_id, cards, span)
            for card in found:
                result.setdefault((view, card), []).append(span)
            if not found:
                placements[view] = union_spans(sources, [*placements.get(view, []), span])
        for line in scope_lines(sources, left):
            if any(overlaps(line, other) for other in occupied):
                continue
            found = owners(task_id, cards, line)
            if found:
                card = _nearest({card: cards[card] for card in found}, position, line)
                result.setdefault((view, card), []).append(line)
            else:
                missing_by_view.setdefault(view, []).append(line)
            occupied.append(line)
    return {key: union_spans(sources, spans) for key, spans in result.items()}


def _place_gaps_and_uncited(sources, ordered, visible_by_view, placements, missing_by_view, uncited_by_view, shown=()):
    """Lines of an uncited scope that no accepted value or cited fallback shows go once to the last such block on the
    page; a coverage gap's lines go to the block's own view, once (`placements` is updated in place). `shown`: lines
    the cards show already."""
    occupied = [*[span for cells in visible_by_view.values() for cell in cells.values() for span in cell.evidence],
        *[span for spans in placements.values() for span in spans], *shown]
    # A coverage gap's lines go to the block's own view, once, unless an accepted value or another fallback shows them
    # (a live import: courses repeated the education lines, open source the portfolio items).
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


def _retained_coverage(sources, coverage, add_coverage):
    """Source text outside every configured field view is recorded as retained source only."""
    covered = union_spans(sources, [value.span for value in coverage])
    for source in sources:
        for unit in source.units:
            cursor = 0
            spans = [span for span in covered if unit_key(span) == (source.id, source.revision, unit.id, unit.revision)]
            for span in [*spans, capture_span(source, unit, len(unit.text), len(unit.text))]:
                if cursor < span.start:
                    add_coverage(capture_span(source, unit, cursor, span.start), None, [], 'source_only', 'retained outside configured field views')
                cursor = span.end


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
    hidden, compact, assigned = _stored_views(package, operations, current)
    fallbacks, uncited_by_view, missing_by_view, human_scopes = [], {}, {}, []
    # D156: whose each shown value is (its task and record), the root record of each reply item, the values a reply
    # does not show, and the fallbacks of tasks that kept values.
    value_owners, homes, unshown, kept = {}, {}, [], []
    for operation in operations:
        tasks = {task.id: task for task in operation.tasks}
        attempts = {attempt.id: attempt for attempt in operation.attempts}
        allocated = {value.item_handle: value for value in item_identities(operation)}
        # Blocks run in parallel finish in any order; a stable sort reads them in declaration order.
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
                    homes[(proposal.id, root)] = identity.record_id
                cell = current.get(identifier)
                if identifier not in proposal.admitted_cell_ids or cell is None:
                    unshown.append((task.id, proposal.id, root, field.evidence))
                    continue
                relative = tuple(tokens[len(root):])
                if cell.origin == 'human' and visible_path(declaration, relative):
                    human_scopes.extend(field.evidence)
                fields[(declaration.id, identifier)] = DisplayField(relative, identity.record_id, identity.item_handle, cell)
                value_owners[(declaration.id, identifier)] = (task.id, identity.record_id)
                unassigned.pop((declaration.id, identifier), None)
                # Without a declared period format an ongoing period has no readable label, so it shows source wording.
                # It replaces only the cells of its own record that cite the same lines (D156).
                if cell.state == 'uncertain' or (period_format is None and cell.origin != 'human' and cell.typed_value is True
                        and relative[-1:] == ('ongoing',)):
                    fallbacks.append((declaration.id, ('record', identity.record_id), cell.evidence))
        for result in sorted(operation.task_results, key=lambda value: order[value.task_id]):
            if result.disposition == 'source_fallback':
                task = tasks[result.task_id]
                view = task.block_id
                if view in operation_ids:
                    # An operation has no view; the blocks it reads show their own source lines.
                    continue
                if view not in declarations:
                    raise ValueError('source fallback has no configured block view')
                uncited = isinstance(result.value, dict) and result.value.get('scope') == 'uncited'
                # Lines a review names as missing from the block are placed only where no view shows them yet.
                missing = set(result.value.get('leftoverOnly', ())) if isinstance(result.value, dict) else set()
                cited = [span for span in result.source_spans if digest(span) not in missing]
                left = [span for span in result.source_spans if digest(span) in missing]
                if task.state == 'accepted' and not uncited:
                    # A task that kept values withdraws none of them; its findings' lines go to its own cards (D156),
                    # those of a value whose owner the review doubts to its block.
                    unowned = set(result.value.get('unowned', ())) if isinstance(result.value, dict) else set()
                    kept.append((view, task.id, [span for span in cited if digest(span) not in unowned], left))
                    # An owner with no cells: these lines replace no value.
                    fallbacks.append((view, ('kept', task.id), [span for span in cited if digest(span) in unowned]))
                    continue
                if uncited:
                    uncited_by_view.setdefault(view, []).extend(cited)
                else:
                    fallbacks.append((view, ('task', task.id), cited))
                missing_by_view.setdefault(view, []).extend(left)
    visible_by_view = {}
    for (view, identifier), field in [*fields.items(), *unassigned.items()]:
        if visible_path(declarations[view], field.relative):
            visible_by_view.setdefault(view, {})[identifier] = field.cell
    owned_by = {key: {('task', task_id), ('record', record_id)} for key, (task_id, record_id) in value_owners.items()}
    cells_by_view = {view: [(cell, owned_by.get((view, identifier), set())) for identifier, cell in cells.items()]
        for view, cells in visible_by_view.items()}
    _fallback, suppressed, placements = fallback_plan(sources, fallbacks, cells_by_view, protected_spans=human_scopes)
    ordered = sorted(declarations.values(), key=lambda value: (['header', 'sidebar', 'main'].index(value.placement.region), value.placement.order, value.id))
    parents = ownership_parents(facts)
    def primary_owner(identifier, view, seen=()):
        if (view, identifier) in roots:
            return {identifier}
        if identifier in seen:
            raise ValueError('cyclic materialized ownership')
        return set().union(*(primary_owner(parent, view, (*seen, identifier)) for parent in parents.get(identifier, set())))
    # The cards each kept task shows, with the places of the lines they cite.
    position, task_cards, keeping = _positions(sources), {}, {(view, task_id) for view, task_id, _cited, _left in kept}
    for (view, identifier), field in fields.items():
        if ((view, value_owners.get((view, identifier), (None,))[0]) not in keeping
                or identifier not in visible_by_view.get(view, {}) or (view, identifier) in suppressed):
            continue
        card = primary_owner(field.record_id, view)
        if len(card) == 1 and not card & hidden.get(view, set()):
            task_cards.setdefault((view, value_owners[(view, identifier)][0]), {}).setdefault(next(iter(card)), []).extend(
                position(span) for span in field.cell.evidence)
    occupied = [*[span for cells in visible_by_view.values() for cell in cells.values() for span in cell.evidence],
        *[span for spans in placements.values() for span in spans]]
    card_lines = _place_kept(sources, kept, unshown, homes, task_cards, occupied, placements, missing_by_view)
    _place_gaps_and_uncited(sources, ordered, visible_by_view, placements, missing_by_view, uncited_by_view,
        [span for spans in card_lines.values() for span in spans])
    regions = {role: {'id': stable_id(operation_id, role), 'role': role, 'revision': revision, 'blocks': []}
        for role in ['header', 'sidebar', 'main']}
    coverage, displayed, owned, shown_scopes, shown_fallback = [], {}, set(), set(), []
    scopes = {scope.id: scope for scope in facts.manual_scopes}
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
    rewriting = any(value.capture.allow_text_rewrite for value in operations)
    def source_paragraph(span, identifier, ref):
        """One exact source line (or adjacent lines) as a paragraph with its citation; None for blank text."""
        shown = without_line_break(sources, span)
        wording = source_slice(sources, shown) if shown is not None else ''
        if not rewriting:
            wording = without_contacts(wording)
        if not wording.strip():
            return None
        text = literal(wording, ref)
        text.citations = [shown]
        add_coverage(shown, None, [identifier], 'fallback', 'exact source scope')
        return {'type': 'paragraph', 'id': identifier, 'revision': 1, 'props': {}, 'content': [text],
            'children': [], 'provenance': [], 'presentation': ref}
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
            # The source lines of this entry's remarks follow its values, inside its card (D156).
            ref = reference(package, declaration.id, fallback_style(declaration), instance, primary.item_handle)
            children.extend(paragraph for span in card_lines.get((declaration.id, primary.record_id), [])
                if (paragraph := source_paragraph(span, stable_id(instance, 'fallback', digest(span)), ref)) is not None)
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
            ref = reference(package, declaration.id, fallback_style(declaration),
                stable_id(operation_id, declaration.id, 'fallback'))
            paragraph = source_paragraph(span, stable_id(operation_id, 'fallback', digest(span)), ref)
            if paragraph is not None:
                paragraphs.append(paragraph)
        # A block that shows only source lines keeps its own title (a live import: projects text without "ПРОЕКТЫ").
        if sections or paragraphs:
            title = locale_text(declaration.view.title, package.definition.template.default_locale)
            if declaration.view.heading != 'none' and title:
                ref = reference(package, declaration.id, heading_style(package, declaration),
                    stable_id(operation_id, declaration.id, 'heading'))
                output.append({'type': 'heading', 'id': stable_id(operation_id, declaration.id, 'heading'), 'revision': 1,
                    'props': {'level': 1}, 'content': [literal(title, ref)], 'children': [], 'provenance': [], 'presentation': ref})
        if declaration.view.row is not None and (sections or paragraphs):
            # The whole block is one table row under its label (D143); rows of neighbouring blocks share the table.
            row = row_section(package, declaration, stable_id(operation_id, declaration.id, 'row'),
                stable_id(operation_id, declaration.id, 'row'))
            row['children'] = [*sections, *paragraphs]
            sections, paragraphs = [row], []
        output.extend(sections)
        output.extend(paragraphs)
    if set(placements) - set(declarations):
        raise ValueError('source fallback has no materialized placement')
    for identifier, blocks in displayed.items():
        record, handle = cell_owners[identifier]
        for span in current[identifier].evidence:
            add_coverage(span, handle, blocks, 'multiple_views' if len(blocks) > 1 else 'accepted', 'configured field presentation')
    _retained_coverage(sources, coverage, add_coverage)
    document = RichDocumentV2(schemaVersion=2, revision=revision, regions=list(regions.values()))
    return document, coverage
