"""How the facts panel shows records in the document: titles, rows, technology lines and their places; shared by the panel edits and the presentation plan."""

from __future__ import annotations

from ..fields import field_key, inline_groups, occurrences, working_field
from ..models.rich_document import FactFieldSpan
from ..models.template_document import BoundLink, PresentedText, TemplateHeadingBlock, TemplateSectionBlock
from ..templates.materialize_nodes import fallback_style, heading_style, literal, locale_text, reference
from .template_panel_lines import block_node, is_row, sibling_lists, template_literal
from .template_panel_values import period_endpoint, period_field_id


def view_title(block, view=None):
    return (block.type == 'heading' and block.presentation is not None and block.presentation.node_index is None
        and view in {None, block.presentation.view_key})


def drop_empty_titles(document, views):
    """The title of each given view that shows nothing else goes, as an import would not show it. A view shown twice, as a
    skill group of the user's own copies one (D136), loses each title with nothing of its view right after it."""
    for view in set(views) - {None}:
        if all(view_title(block) for block in document.blocks()
                if block.presentation is not None and block.presentation.view_key == view):
            for items in sibling_lists(document):
                items[:] = [block for block in items if not view_title(block, view)]
        elif sum(1 for block in document.blocks() if view_title(block, view)) > 1:
            for items in sibling_lists(document):
                items[:] = [block for index, block in enumerate(items) if not view_title(block, view) or index + 1 < len(items)
                    and not view_title(items[index + 1]) and items[index + 1].presentation is not None
                    and items[index + 1].presentation.view_key == view]


def view_position(document, package, view):
    """(region, index) where a view's first block goes: before the first block of the view or of a view the import
    places after it in the same region; None without one such region."""
    regions = [region for region in document.regions if region.role == view.placement.region]
    if len(regions) != 1:
        return None
    later = {value.id for value in package.definition.blocks if value.placement.region == view.placement.region
        and (value.placement.order, value.id) >= (view.placement.order, view.id)}
    items = regions[0].blocks
    return regions[0], next((at for at, block in enumerate(items)
        if block.presentation is not None and block.presentation.view_key in later), len(items))


def view_row(package, view, blocks, allocator, kind):
    """The blocks of a view that is one table row (D143), inside the row section the import gives it; other views' blocks
    as they are."""
    if view.view.row is None or all(is_row(block) for block in blocks):
        return blocks
    return [TemplateSectionBlock(type='section', id=allocator.allocate('block', [f'panel-{kind}-row', view.id]), revision=1,
        props={'recordId': None, 'presentation': 'row'}, content=[], children=blocks, provenance=[],
        presentation=reference(package, view.id, fallback_style(view),
            allocator.allocate('template-instance', [f'panel-{kind}-row-instance', view.id])))]


def restore_view(document, package, view, blocks, allocator, kind):
    """Insert the blocks of a view the document no longer shows, after its title, where the import puts the view."""
    position = view_position(document, package, view)
    if position is None:
        return False
    region, at = position
    blocks = view_row(package, view, blocks, allocator, kind)
    title = locale_text(view.view.title, package.definition.template.default_locale)
    if view.view.heading != 'none' and title:
        ref = reference(package, view.id, heading_style(package, view),
            allocator.allocate('template-instance', [f'panel-{kind}-heading-instance', view.id]))
        blocks = [TemplateHeadingBlock(type='heading', id=allocator.allocate('block', [f'panel-{kind}-heading', view.id]),
            revision=1, props={'level': 1}, content=[literal(title, ref)], children=[], provenance=[], presentation=ref), *blocks]
    region.blocks[at:at] = blocks
    return True


def _patch_displays(before, candidate, original, updated, selected, removed_periods, allocator):
    switches = {}
    previous = {period.id: period for period in getattr(original, 'periods', [])}
    for period in getattr(updated, 'periods', []):
        old = previous[period.id]
        active = period_endpoint(period)
        inactive = 'end' if active == 'present' else 'present'
        if period_endpoint(old) != active:
            switches['period:' + period.id + ':' + inactive] = 'period:' + period.id + ':' + active
    affected = selected | set(switches) | set(switches.values())
    for block in before.document.blocks():
        for _container, content in inline_groups(block):
            for span in content:
                if isinstance(span, BoundLink) and any(value is not None and value.record_id == updated.id and (
                        value.field_key in affected or period_field_id(value.field_key) in removed_periods)
                        for value in (span.label_binding, span.url_binding)):
                    raise ValueError('semantic link panel editing needs its dedicated adapter')
    by_id = {block.id: block for block in candidate.document.blocks()}
    groups = occurrences(before.document)
    for group in groups.values():
        if group.record_id != updated.id:
            continue
        deleted = period_field_id(group.key) in removed_periods
        key = switches.get(group.key, group.key)
        if not deleted and key not in selected and group.key not in switches:
            continue
        for identifier in group.block_ids:
            for _container, content in inline_groups(by_id[identifier]):
                if any(isinstance(span, BoundLink) and any(value is not None and value.record_id == updated.id
                        and value.field_key == group.key for value in (span.label_binding, span.url_binding)) for span in content):
                    raise ValueError('semantic link panel editing needs its dedicated adapter')
        remaining = '' if deleted else working_field(updated, key).raw_text
        root = allocator.allocate('occurrence', ['panel-endpoint', updated.id, group.root, key]) if group.key in switches else None
        for index, original_span in enumerate(group.spans):
            for identifier in group.block_ids:
                for _container, content in inline_groups(by_id[identifier]):
                    for span in list(content):
                        if not isinstance(span, FactFieldSpan) or span.binding_id != original_span.binding_id:
                            continue
                        if deleted:
                            content.remove(span)
                            continue
                        text = remaining if index == len(group.spans) - 1 else remaining[:len(span.text)]
                        remaining = remaining[len(text):]
                        span.text = text
                        if root is not None:
                            span.field_key, span.cell_id = key, field_key(updated.id, key)
                            span.binding_root_id = span.occurrence_id = root
                            span.binding_id = allocator.allocate('fragment', ['panel-endpoint-fragment', original_span.binding_id, key])
    for block in candidate.document.blocks():
        kept = []
        for value in block.provenance:
            if getattr(value, 'record_id', None) == updated.id:
                if value.kind == 'field_binding':
                    if period_field_id(value.field_key) in removed_periods:
                        continue
                    value.field_key = switches.get(value.field_key, value.field_key)
                elif value.kind == 'citation':
                    value.field_keys = [switches.get(key, key) for key in value.field_keys
                        if period_field_id(key) not in removed_periods]
            kept.append(value)
        block.provenance = kept


def _focus_section(block):
    return getattr(getattr(block, 'props', None), 'presentation', None) == 'focus'


def technology_lines(project):
    """(block, container, content, owner) of each inline group outside Focus rows that lists technology names; owner is
    the record of the item section around the line, None outside one."""
    focus = {key for key, view in project.template_package.recipe.views.items()
        if any(node.type == 'focus_entry' for node in view.nodes)}
    found = []
    def visit(blocks, owner):
        for block in blocks:
            if _focus_section(block) or block.presentation is not None and block.presentation.view_key in focus:
                continue
            for container, content in inline_groups(block):
                if _split_technology_line(content)[1]:
                    found.append((block, container, content, owner))
            visit(block.children, getattr(block.props, 'record_id', None) or owner)
    for region in project.document.regions:
        visit(region.blocks, None)
    return found


def _display_entry(span):
    return isinstance(span, FactFieldSpan) and span.field_key == 'display' and getattr(span, 'complete', True)


def line_is_list(package, block):
    """Whether a line's literals are only what its node writes: its prefix and separators, not authored wording."""
    node = block_node(package, block)
    words = (locale_text(node.prefix, package.definition.template.default_locale), node.separator) if node is not None else ()
    return all(template_literal(span.text, *words) for span in block.content if isinstance(span, PresentedText))


def _split_technology_line(content, entry=_display_entry):
    """A tags line is a fixed prefix, then one entry per technology, then a trailing tail.
    The nodes between entries are the separator that travels with the following entry."""
    prefix, entries, bucket, spans, record = [], [], [], [], None
    def flush():
        nonlocal bucket, spans, record
        if record is not None:
            entries.append((record, bucket, spans))
            bucket, spans, record = [], [], None
    for span in content:
        if entry(span) and (record is None or record == span.record_id):
            if record is None:
                record = span.record_id
            spans.append(span)
            continue
        if entry(span):
            flush()
            record, spans = span.record_id, [span]
            continue
        if spans:
            flush()
        if record is None and not entries:
            prefix.append(span)
        else:
            bucket.append(span)
    flush()
    return prefix, entries, bucket


def _separator_nodes(nodes):
    return bool(nodes) and all(isinstance(node, PresentedText) for node in nodes)


def _join_technology_line(prefix, entries, trailing, separator=None):
    sample = next((node for _record, leading, _spans in entries for node in leading if isinstance(node, PresentedText)), None)
    if sample is None:
        sample = separator or PresentedText(type='text', text=', ', styles={})
    content = list(prefix)
    for index, (_record, leading, spans) in enumerate(entries):
        if index == 0 and _separator_nodes(leading):
            leading = []
        elif index and not leading:
            leading = [sample.model_copy(deep=True)]
        content.extend(leading)
        content.extend(spans)
    content.extend(trailing)
    return content
