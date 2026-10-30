"""Focus rows from the facts panel (D113): membership and order change only the document; years are the technology's
stated experience, edited with the record, and its Focus line."""

from .models.rich_document import FactFieldSpan
from .models.template_document import BoundLink, TemplateParagraphBlock, TemplateSectionBlock
from .rich_dependencies import placements
from .rich_fields import inline_groups, working_field
from .template_panel_creation import _mapping
from .template_preparation_panel import drop_empty_titles, field_occurrence, restore_view, sibling_lists, view_title
from .templates.focus import catalog_for, focus_durations, remembered_icon, row_icon, row_name
from .templates.materialize_nodes import fallback_style, literal, locale_text, reference
from .templates.presentation_plan import focus_row
from .templates.projection import pointer_tokens
from .technology_experience import whole_years_text

FOCUS_OPERATIONS = {'add_to_focus', 'remove_from_focus', 'move_focus', 'set_focus_icon'}


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


def focus_rows(document, view_id, records):
    """(sibling list, section) of each Focus row in document order; a row is an item section of the view whose record
    is a technology."""
    rows = []
    for items in sibling_lists(document):
        for block in items:
            if (isinstance(block, TemplateSectionBlock) and block.presentation is not None
                    and block.presentation.view_key == view_id and block.props.record_id in records):
                rows.append((items, block))
    return rows


def focus_only(project):
    """Records only Focus rows show: Focus manages them and the panel's technology lists leave them out. None when the
    panel cannot change Focus rows."""
    try:
        view = focus_view(project.template_package)[0]
    except ValueError:
        return None
    technologies = {record.id for record in project.facts.records if record.kind == 'technology'}
    rows = focus_rows(project.document, view.id, technologies)
    skipped, shown = {section.id for _items, section in rows}, set()
    def visit(blocks):
        for block in blocks:
            if block.id in skipped:
                continue
            for _container, content in inline_groups(block):
                for span in content:
                    for part in span.content if isinstance(span, BoundLink) else [span]:
                        if isinstance(part, FactFieldSpan) and part.field_key == 'display':
                            shown.add(part.record_id)
            visit(block.children)
    for region in project.document.regions:
        visit(region.blocks)
    return frozenset(section.props.record_id for _items, section in rows) - shown


def focus_full(project):
    """Whether the Focus rows reached the most the template's view takes."""
    view = focus_view(project.template_package)[0]
    limit = view.content_schema.get('maxItems')
    technologies = {record.id for record in project.facts.records if record.kind == 'technology'}
    return limit is not None and len(focus_rows(project.document, view.id, technologies)) >= limit


def _detail_content(package, view, index, instance, record, experience_key, computed, allocator, slot):
    """The experience line: the stated value bound to its field, else the time the technology's jobs span; None hides it."""
    node = view.view.nodes[index]
    ref = reference(package, view.id, node.detail_style or node.style, instance, node_index=index)
    stated = working_field(record, experience_key) if experience_key else None
    if stated is not None and stated.raw_text.strip():
        return ref, [field_occurrence(allocator, 'focus', record, experience_key, ref, experience_key, slot)]
    return (ref, [literal(computed, ref)]) if computed else (ref, None)


def _is_name(block, record_id, name_key):
    return any(getattr(span, 'type', None) == 'fact_field' and span.record_id == record_id and span.field_key == name_key
        for span in block.content)


def _add(workspace, candidate, command, allocator, technologies, remembered):
    package = candidate.template_package
    view, index, name_key, experience_key = focus_view(package)
    record = technologies.get(command.record_id)
    if record is None:
        raise ValueError('FOCUS_SCOPE_INVALID')
    rows = focus_rows(candidate.document, view.id, technologies)
    if any(section.props.record_id == record.id for _items, section in rows):
        raise ValueError('FOCUS_DUPLICATE')
    if focus_full(candidate):
        raise ValueError('FOCUS_FULL')
    node = view.view.nodes[index]
    locale = package.definition.template.default_locale
    instance = allocator.allocate('template-instance', ['panel-focus-instance', record.id])
    name_ref = reference(package, view.id, node.style, instance, node_index=index)
    def paragraph(slot, ref, content):
        return TemplateParagraphBlock(type='paragraph', id=allocator.allocate('block', [slot, record.id]), revision=1,
            props={}, children=[], provenance=[], presentation=ref, content=content)
    # As the import writes a row: an optional label, the name with its prefix, then the experience line.
    label, prefix = locale_text(node.label, locale), locale_text(node.prefix, locale)
    children = [paragraph('panel-focus-label', name_ref, [literal(label, name_ref)])] if label else []
    children.append(paragraph('panel-focus-name', name_ref, [*([literal(prefix, name_ref)] if prefix else []),
        field_occurrence(allocator, 'focus', record, name_key, name_ref, name_key, 'name')]))
    as_of = workspace.formatting_as_of
    computed = focus_durations(candidate.facts, as_of, locale).get(record.id) if as_of is not None else None
    detail_ref, detail = _detail_content(package, view, index, instance, record, experience_key, computed, allocator, 'detail')
    if detail:
        children.append(paragraph('panel-focus-detail', detail_ref, detail))
    # The icon the user chose before for this name comes along (D122).
    icon = remembered_icon(catalog_for(package), remembered, record.display.raw_text) if remembered is not None else None
    section = TemplateSectionBlock(type='section', id=allocator.allocate('block', ['panel-focus-section', record.id]),
        revision=1, props={'recordId': record.id, **({'icon': icon} if icon else {})}, content=[], children=children,
        provenance=[], presentation=reference(package, view.id, fallback_style(view), instance))
    if rows:
        items, last = rows[-1]
        items.insert(items.index(last) + 1, section)
        return
    title = next(((items, block) for items in sibling_lists(candidate.document) for block in items if view_title(block, view.id)), None)
    if title is not None:
        items, block = title
        items.insert(items.index(block) + 1, section)
    # The last row's removal took the title along; it comes back with the first row.
    elif not restore_view(candidate.document, package, view, [section], allocator, 'focus'):
        raise ValueError('FOCUS_VIEW_MISSING')


def _remove(candidate, command, technologies):
    view = focus_view(candidate.template_package)[0]
    removed = [(items, section) for items, section in focus_rows(candidate.document, view.id, technologies)
        if section.props.record_id == command.record_id]
    if not removed:
        raise ValueError('FOCUS_SCOPE_INVALID')
    for items, section in removed:
        items.remove(section)
    # The title goes with the last row unless the view still shows other lines, such as source text.
    drop_empty_titles(candidate.document, {view.id})


def _move(candidate, command, technologies):
    """The moved row; None when the order stays as it is."""
    view = focus_view(candidate.template_package)[0]
    rows = focus_rows(candidate.document, view.id, technologies)
    moving = next(((items, section) for items, section in rows if section.props.record_id == command.record_id), None)
    target = next(((items, section) for items, section in rows if section.props.record_id == command.before_record_id), None)
    if moving is None or command.before_record_id is not None and target is None:
        raise ValueError('TECHNOLOGY_MOVE_INVALID')
    items, section = moving
    others = [value for _items, value in rows if value is not section]
    if command.before_record_id == command.record_id or not others:
        return None
    if (target[0] if target is not None else rows[-1][0]) is not items:
        raise ValueError('TECHNOLOGY_MOVE_INVALID')
    before = [value.id for value in items]
    items.remove(section)
    items.insert(items.index(target[1]) if target is not None else items.index(others[-1]) + 1, section)
    return section if [value.id for value in items] != before else None


def _set_icon(candidate, command, technologies):
    """The row's icon: one of the template's icons, or "" for the template's own choice. False when it stays."""
    view = focus_view(candidate.template_package)[0]
    sections = [section for _items, section in focus_rows(candidate.document, view.id, technologies)
        if section.props.record_id == command.record_id]
    if not sections:
        raise ValueError('FOCUS_SCOPE_INVALID')
    icon = command.values['icon'] or None
    if icon is not None and icon not in catalog_for(candidate.template_package).files:
        raise ValueError('FOCUS_ICON_UNKNOWN')
    if all(section.props.icon == icon for section in sections):
        return False
    for section in sections:
        section.props.icon = icon
    return True


def chosen_icons(project):
    """Section id to (chosen icon or None, technology name) of each Focus row; empty without one Focus view."""
    try:
        view = focus_view(project.template_package)[0]
    except ValueError:
        return {}
    technologies = {record.id: record for record in project.facts.records if record.kind == 'technology'}
    return {section.id: (section.props.icon, technologies[section.props.record_id].display.raw_text)
        for _items, section in focus_rows(project.document, view.id, technologies)}


def icon_choices(project, remembered=None):
    """The facts panel's icon search (D122): each icon of the project's template with its names, and per Focus row
    record the icon the template chooses itself and the one remembered for the row's name; and the PNG assets these
    name, for the asset route."""
    package = project.template_package
    catalog = catalog_for(package)
    names = {}
    for name, icon in catalog.aliases.items():
        names.setdefault(icon, []).append(name)
    icons = [{'id': icon, 'names': sorted(names.get(icon, [])), 'sha256': asset.sha256}
        for icon, asset in sorted(catalog.files.items())]
    assets, rows = list(catalog.files.values()), {}
    for block in project.document.blocks():
        row = focus_row(block, package.recipe)
        if not row or block.props.record_id is None:
            continue
        automatic = row_icon(package, project.facts, row, catalog)
        if automatic is not None:
            assets.append(automatic[1])
        rows[block.props.record_id] = {
            'automatic': {'id': automatic[0], 'sha256': automatic[1].sha256} if automatic is not None else None,
            'remembered': remembered_icon(catalog, remembered, row_name(package, project.facts, row))}
    return {'schemaVersion': 1, 'icons': icons, 'rows': rows}, assets


def icon_changes(before, after):
    """(name, icon or None) of each Focus row whose chosen icon a commit changed, as later rows should take it: a pick,
    its Undo or Redo, or a reset to the template's own choice. Rows added or removed change nothing."""
    if before is None or after is None:
        return []
    old = chosen_icons(before)
    return [(name, icon) for identifier, (icon, name) in chosen_icons(after).items()
        if identifier in old and old[identifier][0] != icon]


def experience_text(package, text):
    """The panel's years field: a bare number is whole years, written as the template's language writes them."""
    text = text.strip()
    return whole_years_text(int(text), package.definition.template.default_locale == 'ru') \
        if text.isascii() and text.isdigit() else text


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
        # The name and a label before it stay; the experience line follows the name.
        name = next((at for at, block in enumerate(section.children) if _is_name(block, updated.id, name_key)), None)
        lead = section.children[:name + 1] if name is not None else []
        details = section.children[len(lead):]
        instance = (lead[-1] if lead else section).presentation.template_instance_id
        ref, content = _detail_content(package, view, index, instance, updated, experience_key, None, allocator,
            ['detail', section.id])
        kept = details[0] if details else None
        section.children = lead
        if content:
            if kept is None:
                kept = TemplateParagraphBlock(type='paragraph',
                    id=allocator.allocate('block', ['panel-focus-detail', section.id]), revision=1, props={},
                    children=[], provenance=[], presentation=ref, content=content)
            else:
                kept.content, kept.presentation = content, ref
            section.children.append(kept)


def refresh_durations(workspace, candidate, facts, allocator):
    """A computed Focus line follows the jobs (D105). The line is known by its text: a row without stated experience whose
    line still reads what the jobs gave before takes what they give now. A line the user wrote stays, and a row they
    cleared stays empty."""
    try:
        view, index, name_key, experience_key = focus_view(candidate.template_package)
    except ValueError:
        return
    as_of, package = workspace.formatting_as_of, candidate.template_package
    if as_of is None:
        return
    locale = package.definition.template.default_locale
    old, new = focus_durations(workspace.project.facts, as_of, locale), focus_durations(facts, as_of, locale)
    records = {record.id: record for record in facts.records if record.kind == 'technology'}
    for _items, section in focus_rows(candidate.document, view.id, records):
        identifier = section.props.record_id
        name = next((at for at, block in enumerate(section.children) if _is_name(block, identifier, name_key)), None)
        stated = working_field(records[identifier], experience_key) if experience_key else None
        if old.get(identifier) == new.get(identifier) or name is None or stated is not None and stated.raw_text.strip():
            continue
        line = section.children[name + 1] if name + 1 < len(section.children) else None
        if line is None and identifier not in old and identifier in new:
            ref, content = _detail_content(package, view, index, section.children[name].presentation.template_instance_id,
                records[identifier], None, new[identifier], allocator, ['computed', section.id])
            section.children.append(TemplateParagraphBlock(type='paragraph', id=allocator.allocate('block',
                ['panel-focus-computed', section.id]), revision=1, props={}, children=[], provenance=[], presentation=ref, content=content))
        elif line is not None and [getattr(span, 'text', None) for span in line.content] == [old.get(identifier)]:
            if identifier in new:
                line.content[0].text = new[identifier]
            else:
                section.children.remove(line)


def prepare_focus(workspace, command, allocator, remembered=None):
    """(candidate project, steps) of one Focus row command, or None when it changes nothing. `remembered`: the icons
    the user chose before (`remembered_catalog`), which an added row takes."""
    project = workspace.project
    technologies = {record.id: record for record in project.facts.records if record.kind == 'technology'}
    candidate = project.model_copy(deep=True)
    steps = []
    if command.operation == 'add_to_focus':
        _add(workspace, candidate, command, allocator, technologies, remembered)
    elif command.operation == 'set_focus_icon':
        if not _set_icon(candidate, command, technologies):
            return None
    elif command.operation == 'remove_from_focus':
        _remove(candidate, command, technologies)
    elif command.operation == 'move_focus':
        section = _move(candidate, command, technologies)
        if section is None:
            return None
        # A changed order is no block change: the move is its own step.
        parent, previous, _owner = placements(candidate.document)[section.id]
        steps.append({'kind': 'move_block', 'blockId': section.id, 'beforeRevision': section.revision,
            'parentId': parent, 'afterId': previous})
    else:
        raise ValueError('FOCUS_SCOPE_INVALID')
    return candidate, steps
