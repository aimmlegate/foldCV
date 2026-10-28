"""Focus rows from the facts panel: add, remove and move a technology's row, and show its stated experience (D113).

Facts stay as they are: membership and order change only the document; the stated experience is the technology's own
field, edited with the record, and its Focus line."""

from .models.template_document import FieldOccurrence, TemplateHeadingBlock, TemplateParagraphBlock, TemplateSectionBlock
from .rich_dependencies import placements
from .rich_fields import field_key, working_field
from .template_panel_creation import _mapping
from .templates.focus import focus_durations
from .templates.materialize_nodes import fallback_style, literal, locale_text, reference
from .templates.projection import pointer_tokens
from .technology_experience import whole_years_text

FOCUS_OPERATIONS = {'add_to_focus', 'remove_from_focus', 'move_focus'}


def focus_view(package):
    """The one items view with a Focus node over the technology fact type: (view, node index, name key, experience key)."""
    types = {value.id: value for value in package.definition.fact_types if value.builtin_kind == 'technology'}
    found = []
    for view in package.definition.blocks:
        for index, node in enumerate(view.view.nodes if view.view.mode == 'items' else []):
            if node.type != 'focus_entry':
                continue
            for semantic in types.values():
                mapping = _mapping(view, semantic)
                name = mapping.get(tuple(pointer_tokens(node.name_field)))
                experience = mapping.get(tuple(pointer_tokens(node.experience_field))) if node.experience_field else None
                if name is not None and name.field == 'display':
                    found.append((view, index, 'display', experience.field if experience is not None else None))
    if len(found) != 1:
        raise ValueError('FOCUS_VIEW_MISSING')
    return found[0]


def _parent_lists(document):
    def visit(items):
        yield items
        for block in items:
            yield from visit(block.children)
    for region in document.regions:
        yield from visit(region.blocks)


def focus_rows(document, view_id, records):
    """(sibling list, section) of each Focus row in document order; a row is an item section of the view whose record
    is a technology."""
    rows = []
    for items in _parent_lists(document):
        for block in items:
            if (isinstance(block, TemplateSectionBlock) and block.presentation is not None
                    and block.presentation.view_key == view_id and block.props.record_id in records):
                rows.append((items, block))
    return rows


def _heading(document, view_id):
    for items in _parent_lists(document):
        for block in items:
            if block.type == 'heading' and block.presentation is not None and block.presentation.view_key == view_id \
                    and block.presentation.node_index is None:
                return items, block
    return None


def _occurrence(allocator, record, key, ref, slot):
    value = working_field(record, key)
    root = allocator.allocate('occurrence', ['panel-focus-occurrence', record.id, key, slot])
    return FieldOccurrence(type='fact_field', bindingId=allocator.allocate('fragment', ['panel-focus-fragment', root]),
        bindingRootId=root, recordId=record.id, fieldKey=key, cellId=field_key(record.id, key), occurrenceId=root,
        complete=True, presentation=ref, text=value.raw_text, styles={}, syncedFactRevision=value.revision)


def _detail_content(package, view, index, instance, record, experience_key, computed, allocator, slot):
    """The experience line: the stated value bound to its field, else the time the technology's jobs span; None hides it."""
    node = view.view.nodes[index]
    ref = reference(package, view.id, node.detail_style or node.style, instance, node_index=index)
    stated = working_field(record, experience_key) if experience_key else None
    if stated is not None and stated.raw_text.strip():
        return ref, [_occurrence(allocator, record, experience_key, ref, slot)]
    return (ref, [literal(computed, ref)]) if computed else (ref, None)


def _is_name(block, record_id, name_key):
    return any(getattr(span, 'type', None) == 'fact_field' and span.record_id == record_id and span.field_key == name_key
        for span in block.content)


def _add(workspace, candidate, command, allocator, technologies):
    package = candidate.template_package
    view, index, name_key, experience_key = focus_view(package)
    record = technologies.get(command.record_id)
    if record is None:
        raise ValueError('FOCUS_SCOPE_INVALID')
    rows = focus_rows(candidate.document, view.id, technologies)
    if any(section.props.record_id == record.id for _items, section in rows):
        raise ValueError('FOCUS_DUPLICATE')
    node = view.view.nodes[index]
    instance = allocator.allocate('template-instance', ['panel-focus-instance', record.id])
    name_ref = reference(package, view.id, node.style, instance, node_index=index)
    children = [TemplateParagraphBlock(type='paragraph', id=allocator.allocate('block', ['panel-focus-name', record.id]),
        revision=1, props={}, children=[], provenance=[], presentation=name_ref,
        content=[_occurrence(allocator, record, name_key, name_ref, 'name')])]
    as_of = workspace.formatting_as_of
    computed = focus_durations(candidate.facts, as_of, package.definition.template.default_locale).get(record.id) \
        if as_of is not None else None
    detail_ref, detail = _detail_content(package, view, index, instance, record, experience_key, computed, allocator, 'detail')
    if detail:
        children.append(TemplateParagraphBlock(type='paragraph', id=allocator.allocate('block', ['panel-focus-detail', record.id]),
            revision=1, props={}, children=[], provenance=[], presentation=detail_ref, content=detail))
    section = TemplateSectionBlock(type='section', id=allocator.allocate('block', ['panel-focus-section', record.id]),
        revision=1, props={'recordId': record.id}, content=[], children=children, provenance=[],
        presentation=reference(package, view.id, fallback_style(view), instance))
    if rows:
        items, last = rows[-1]
        items.insert(items.index(last) + 1, section)
        return
    heading = _heading(candidate.document, view.id)
    if heading is None:
        # The last row's removal took the heading along; it comes back with the first row.
        title = locale_text(view.view.title, package.definition.template.default_locale)
        regions = [region for region in candidate.document.regions if region.role == view.placement.region]
        if len(regions) != 1:
            raise ValueError('FOCUS_VIEW_MISSING')
        items = regions[0].blocks
        blocks = [section]
        if view.view.heading != 'none' and title:
            ref = reference(package, view.id, package.recipe.style.section_band.heading_style,
                allocator.allocate('template-instance', ['panel-focus-heading-instance', view.id]))
            blocks.insert(0, TemplateHeadingBlock(type='heading', id=allocator.allocate('block', ['panel-focus-heading', view.id]),
                revision=1, props={'level': 1}, content=[literal(title, ref)], children=[], provenance=[], presentation=ref))
        # Placed before the first block of a later view in the same region, as the import orders views.
        later = {value.id for value in package.definition.blocks if value.placement.region == view.placement.region
            and value.placement.order > view.placement.order}
        position = next((at for at, block in enumerate(items)
            if block.presentation is not None and block.presentation.view_key in later), len(items))
        items[position:position] = blocks
        return
    items, block = heading
    items.insert(items.index(block) + 1, section)


def _remove(candidate, command, technologies):
    view = focus_view(candidate.template_package)[0]
    rows = focus_rows(candidate.document, view.id, technologies)
    removed = [(items, section) for items, section in rows if section.props.record_id == command.record_id]
    if not removed:
        raise ValueError('FOCUS_SCOPE_INVALID')
    for items, section in removed:
        items.remove(section)
    if len(removed) == len(rows):
        heading = _heading(candidate.document, view.id)
        if heading is not None:
            heading[0].remove(heading[1])


def _move(candidate, command, technologies):
    view = focus_view(candidate.template_package)[0]
    rows = focus_rows(candidate.document, view.id, technologies)
    moving = next(((items, section) for items, section in rows if section.props.record_id == command.record_id), None)
    target = next(((items, section) for items, section in rows if section.props.record_id == command.before_record_id), None)
    if moving is None or command.before_record_id is not None and target is None:
        raise ValueError('TECHNOLOGY_MOVE_INVALID')
    if command.before_record_id == command.record_id:
        return False
    items, section = moving
    if (target[0] if target is not None else rows[-1][0]) is not items:
        raise ValueError('TECHNOLOGY_MOVE_INVALID')
    before = [value.id for value in items]
    others = [value for _items, value in rows if value is not section]
    items.remove(section)
    at = items.index(target[1]) if target is not None else items.index(others[-1]) + 1 if others else len(items)
    items.insert(at, section)
    return [value.id for value in items] != before


def experience_text(package, text):
    """The panel's years field: a bare number is whole years, written as the template's language writes them."""
    text = text.strip()
    return whole_years_text(int(text), package.definition.template.default_locale == 'ru') if text.isdigit() else text


def show_experience(candidate, updated, allocator):
    """Each Focus row of the record shows its stated experience; clearing it hides the line instead of returning to the
    jobs' span. A template without one Focus view has no row to change."""
    package = candidate.template_package
    try:
        view, index, name_key, experience_key = focus_view(package)
    except ValueError:
        return
    if experience_key is None:
        return
    technologies = {record.id for record in candidate.facts.records if record.kind == 'technology'}
    for _items, section in focus_rows(candidate.document, view.id, technologies):
        if section.props.record_id != updated.id:
            continue
        names = [block for block in section.children if _is_name(block, updated.id, name_key)]
        details = [block for block in section.children if block not in names]
        instance = (names[0] if names else section).presentation.template_instance_id
        ref, content = _detail_content(package, view, index, instance, updated, experience_key, None, allocator,
            ['detail', section.id])
        kept = details[0] if details else None
        section.children = names
        if content:
            if kept is None:
                kept = TemplateParagraphBlock(type='paragraph',
                    id=allocator.allocate('block', ['panel-focus-detail', section.id]), revision=1, props={},
                    children=[], provenance=[], presentation=ref, content=content)
            else:
                kept.content, kept.presentation = content, ref
            section.children.append(kept)


def prepare_focus(workspace, command, allocator):
    """(candidate project, steps) of one Focus row command, or None when it changes nothing."""
    project = workspace.project
    technologies = {record.id: record for record in project.facts.records if record.kind == 'technology'}
    candidate = project.model_copy(deep=True)
    steps = []
    if command.operation == 'add_to_focus':
        _add(workspace, candidate, command, allocator, technologies)
    elif command.operation == 'remove_from_focus':
        _remove(candidate, command, technologies)
    elif command.operation == 'move_focus':
        if not _move(candidate, command, technologies):
            return None
        # A changed order is no block change: the move is its own step.
        section = next(block for block in candidate.document.blocks() if block.type == 'section'
            and block.props.record_id == command.record_id)
        parent, previous, _owner = placements(candidate.document)[section.id]
        steps.append({'kind': 'move_block', 'blockId': section.id, 'beforeRevision': section.revision,
            'parentId': parent, 'afterId': previous})
    else:
        raise ValueError('FOCUS_SCOPE_INVALID')
    return candidate, steps
