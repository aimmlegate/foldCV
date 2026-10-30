"""Field lines of item sections: a field or period the document does not show yet joins the line its template node gives
it, and a period line keeps the template's wording as its dates change. Authored text in a line stays."""

from .models.rich_document import FactFieldSpan
from .models.template_document import PresentedText, TemplateParagraphBlock, TemplateSectionBlock
from .rich_fields import field_key, occurrences, working_field
from .template_panel_values import field_occurrence, period_endpoint, period_field_id
from .templates.materialize_nodes import literal, locale_text, period_format, reference
from .templates.projection import pointer_tokens


def sibling_lists(document):
    """Each list of sibling blocks: a region's blocks and every block's children."""
    def visit(items):
        yield items
        for block in items:
            yield from visit(block.children)
    for region in document.regions:
        yield from visit(region.blocks)


def line_text(block):
    return ''.join(part.text for part in block.content) if all(isinstance(part, PresentedText) for part in block.content) else None


def node_labels(project, lines):
    """The label line the import writes before each of these lines, when its node has one."""
    package = project.template_package
    views, locale, found = {value.id: value for value in package.definition.blocks}, package.definition.template.default_locale, set()
    for items in sibling_lists(project.document):
        for previous, block in zip(items, items[1:]):
            ref, before = block.presentation, previous.presentation
            if block.id not in lines or ref is None or before is None or ref.node_index is None or ref.view_key not in views:
                continue
            label = locale_text(views[ref.view_key].view.nodes[ref.node_index].label, locale)
            if label and (before.view_key, before.template_instance_id, before.node_index) == (
                    ref.view_key, ref.template_instance_id, ref.node_index) and line_text(previous) == label:
                found.add(previous.id)
    return found


def block_node(package, block):
    """The template node a block's line comes from, or None."""
    ref = block.presentation
    view = next((value for value in package.definition.blocks if ref is not None and value.id == ref.view_key), None)
    return view.view.nodes[ref.node_index] if view is not None and ref.node_index is not None else None


def template_literal(text, *words):
    """Whether a line's literal is the template's own: one of its words or only punctuation."""
    return text in words or not any(character.isalnum() for character in text)


def _sections(project, record_id):
    return [block for block in project.document.blocks() if isinstance(block, TemplateSectionBlock)
        and block.props.record_id == record_id and block.presentation is not None]


def _shown_field(package, view, kind, key):
    """(node index, node, the field keys of the node's parts) of the text or join node that shows a builtin field."""
    types = {value.id: value for value in package.definition.fact_types}
    depth, keys, bound = 1 if view.view.mode == 'items' else 0, {}, set()
    for binding in view.bindings:
        declaration, path = types[binding.semantic_type], tuple(pointer_tokens(binding.pointer))
        mapped = declaration.builtin_fields.get(binding.field)
        keys[path[depth:]] = mapped.field if mapped is not None else binding.field
        if mapped is not None and declaration.builtin_kind == kind and mapped.field == key and mapped.period is None:
            bound.add(path[depth:])
    for index, node in enumerate(view.view.nodes):
        paths = [tuple(pointer_tokens(path)) for path in ([node.field] if node.type == 'text' else
            node.fields if node.type == 'join_fields' else [])]
        if bound & set(paths):
            return index, node, [keys.get(path) for path in paths]
    return None


def field_place(project, record, key):
    """(section, view, node index, node, field keys of the node's parts) where the document can show a record's field;
    None when no section of the record has a node for it."""
    views = {value.id: value for value in project.template_package.definition.blocks}
    for section in _sections(project, record.id):
        view = views.get(section.presentation.view_key)
        found = _shown_field(project.template_package, view, record.kind, key) if view is not None else None
        if found is not None:
            return section, view, *found
    return None


def _insert_line(package, section, index, node, ref, content, allocator, seed):
    """The node's new line after the blocks of earlier nodes and its own label, which it brings unless one is shown."""
    label = locale_text(node.label, package.definition.template.default_locale)
    def paragraph(slot, inline):
        return TemplateParagraphBlock(type='paragraph', id=allocator.allocate('block', [slot, section.id, index, seed]),
            revision=1, props={'alignment': ref.overrides.alignment or 'left'}, children=[], provenance=[], presentation=ref,
            content=inline)
    def earlier(child):
        return child.presentation is not None and child.presentation.node_index is not None and child.presentation.node_index <= index
    at = next((len(section.children) - position for position, child in enumerate(reversed(section.children)) if earlier(child)), 0)
    labelled = bool(label) and any(earlier(child) and child.presentation.node_index == index and line_text(child) == label
        for child in section.children)
    section.children[at:at] = [*([paragraph('panel-line-label', [literal(label, ref)])] if label and not labelled else []),
        paragraph('panel-line', content)]


def _join_field(content, occurrence, separator, later):
    """The occurrence in a line, before the first part the node writes after it, else after the last part."""
    fields = [at for at, span in enumerate(content) if isinstance(span, FactFieldSpan)]
    following = next((at for at in fields if content[at].field_key in later), None)
    if following is not None:
        content[following:following] = [occurrence, separator]
    elif fields:
        content[fields[-1] + 1:fields[-1] + 1] = [separator, occurrence]
    else:
        content.append(occurrence)


def show_fields(project, record, keys, allocator):
    """Each of these fields with a value and no occurrence joins the line of its node, which the section gets when it has
    none. A field without a node has no place; the panel's plan leaves it out."""
    package = project.template_package
    shown = {group.key for group in occurrences(project.document).values() if group.record_id == record.id}
    for key in sorted(keys - shown):
        if key.startswith('period:') or field_key(record.id, key) in project.facts.builtin_manual_scopes \
                or not working_field(record, key).raw_text:
            continue
        found = field_place(project, record, key)
        if found is None:
            continue
        section, view, index, node, parts = found
        label = locale_text(node.label, package.definition.template.default_locale)
        line = next((child for child in section.children if child.presentation is not None
            and child.presentation.node_index == index and not (label and line_text(child) == label)), None)
        if line is not None:
            ref = line.presentation
            _join_field(line.content, field_occurrence(allocator, 'field', record, key, ref, line.id, key), literal(node.separator, ref),
                parts[parts.index(key) + 1:])
            continue
        ref = reference(package, view.id, node.style, section.presentation.template_instance_id,
            section.presentation.item_handle, node_index=index)
        prefix = locale_text(node.prefix, package.definition.template.default_locale)
        _insert_line(package, section, index, node, ref, [*([literal(prefix, ref)] if prefix else []),
            field_occurrence(allocator, 'field', record, key, ref, section.id, key)], allocator, key)


def period_words(package):
    """(separator, ongoing label) of the template's period lines; without a declared format there is no label."""
    declared = period_format(package)
    if declared is None:
        return '–', None
    return declared['separator'], locale_text(declared['ongoingLabel'], package.definition.template.default_locale) or None


def period_fields(period, label):
    """The field keys a period's line shows, and whether the ongoing label closes it."""
    base = 'period:' + period.id + ':'
    keys = [base + 'start'] if period.start.raw_text else []
    if period_endpoint(period) == 'end':
        return [*keys, *([base + 'end'] if period.end.raw_text else [])], False
    # A declared format words a current period itself; an unresolved human endpoint stays as typed.
    return (keys, True) if label and period.present.value is True else ([*keys, base + 'present'], False)


def period_text(period, package):
    """A period as the document writes it."""
    separator, label = period_words(package)
    keys, ongoing = period_fields(period, label)
    return separator.join([*(getattr(period, key.rpartition(':')[2]).raw_text for key in keys), *([label] if ongoing else [])])


def _of_period(span, record_id, period_id):
    return isinstance(span, FactFieldSpan) and span.record_id == record_id and period_field_id(span.field_key) == period_id


def _period_content(package, node, ref, content, seed, record, period, identifier, words, allocator):
    """A template period line with the period's current fields; [] when nothing is left to show. None for a line that holds
    other text, which stays."""
    separator, label = words
    prefix = locale_text(node.prefix, package.definition.template.default_locale)
    spans, literals = {}, []
    for span in content:
        if _of_period(span, record.id, identifier):
            spans.setdefault(span.field_key, []).append(span)
        elif isinstance(span, PresentedText) and template_literal(span.text, prefix, label or ''):
            literals.append(span)
        else:
            return None
    if period is None:
        return []
    keys, ongoing = period_fields(period, label)
    # Spans the panel just emptied are gone; a field without a span gets one.
    parts = [[span for span in spans.get(key, []) if span.text]
        or [field_occurrence(allocator, 'period', record, key, ref, seed, key)] for key in keys]
    if ongoing:
        parts.append([next((span for span in literals if span.text == label), None) or literal(label, ref)])
    if not parts:
        return []
    lead = next((span for span in literals if prefix and span.text == prefix), None) or (literal(prefix, ref) if prefix else None)
    between = next((span for span in literals if span.text and span.text not in {prefix, label}), None) or literal(separator, ref)
    return [*([lead] if lead else []), *parts[0], *(part for rest in parts[1:] for part in [between, *rest])]


def _add_period_line(project, record, period, words, allocator):
    """A period that shows something and has no line gets one in the record's section; a job without its own section, as
    in a compressed list, shows no periods."""
    package = project.template_package
    keys, ongoing = period_fields(period, words[1])
    views = {value.id: value for value in package.definition.blocks}
    for section in _sections(project, record.id) if keys or ongoing else []:
        view = views.get(section.presentation.view_key)
        nodes = [(index, node) for index, node in enumerate(view.view.nodes if view is not None else []) if node.type == 'period']
        if len(nodes) != 1:
            continue
        index, node = nodes[0]
        ref = reference(package, view.id, node.style, section.presentation.template_instance_id,
            section.presentation.item_handle, node_index=index)
        content = _period_content(package, node, ref, [], section.id, record, period, period.id, words, allocator)
        _insert_line(package, section, index, node, ref, content, allocator, period.id)
        return


def _label_line(project, record_id, old, label):
    """The line of a current period without a start: only the label, so no span names its period."""
    if old is None or not label or period_fields(old, label) != ([], True):
        return None
    for section in _sections(project, record_id):
        for child in section.children:
            if line_text(child) == label and block_node(project.template_package, child) is not None:
                return child
    return None


def sync_period_lines(before, candidate, original, updated, selected, removed, allocator):
    """Template period lines follow the changed periods: the ongoing label and the bound end replace each other, a missing
    field joins, an emptied line goes. A line with other text stays, and an endpoint it cannot show is refused."""
    package = candidate.template_package
    words = period_words(package)
    blocks = {block.id: block for block in candidate.document.blocks()}
    gone = set()
    for identifier in sorted({period_field_id(key) for key in selected} - {None} | removed):
        period = next((value for value in updated.periods if value.id == identifier), None)
        old = next((value for value in original.periods if value.id == identifier), None)
        shown = [blocks[block.id] for block in before.document.blocks() if block.id in blocks
            and isinstance(block.content, list) and any(_of_period(span, updated.id, identifier) for span in block.content)]
        lines = [(block, node) for block in shown if (node := block_node(package, block)) is not None and node.type == 'period']
        found = _label_line(candidate, updated.id, old, words[1]) if not shown else None
        if found is not None:
            lines = [(found, block_node(package, found))]
        for block, node in lines:
            content = _period_content(package, node, block.presentation, block.content, block.id, updated, period, identifier,
                words, allocator)
            if content is None:
                _require_endpoint(block, updated, period, identifier, selected)
            elif content:
                block.content = content
            else:
                gone.add(block.id)
        if not shown and found is None and period is not None:
            _add_period_line(candidate, updated, period, words, allocator)
    if gone:
        gone |= node_labels(candidate, gone)
        for items in sibling_lists(candidate.document):
            items[:] = [block for block in items if block.id not in gone]


def _require_endpoint(block, record, period, identifier, selected):
    if period is None:
        return
    base = 'period:' + identifier + ':'
    key = base + ('end' if period_endpoint(period) == 'end' else 'present')
    if {base + 'end', base + 'present'} & selected and working_field(record, key).raw_text and not any(
            _of_period(span, record.id, identifier) and span.field_key == key for span in block.content):
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
