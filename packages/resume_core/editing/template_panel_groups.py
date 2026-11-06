"""Skill groups in the facts panel (D136): a technology moves between groups or leaves one, and a group of the user's own
starts with its first technology. Such a group copies the view of the last group, so it shows as the template's groups do,
after them; it goes with its last technology, as an emptied group of the template does."""

from ..models.rich_document import FactFieldSpan
from ..models.template_document import TemplateHeadingBlock, TemplateSectionBlock
from .dependencies import placements
from ..fields import inline_groups
from .template_panel_lines import node_labels
from .template_panel_records import (VIEW_TARGET, _duplicate, _group_line, _group_nodes, _shown, group_heading,
                                     group_lines, line_blocks, line_entries, new_technology, put_entry, remove_records,
                                     restore_group_line, technology_targets)
from .panel_views import _join_technology_line, _split_technology_line, line_is_list, view_position
from .template_panel_lines import sibling_lists
from ..templates.materialize_nodes import heading_style, literal, reference
from ..technologies import normalize_name

# Longer than any group title a template writes; the panel's field takes no more.
TITLE_LIMIT = 80


def new_group_place(project):
    """(view, node index, node, block) a new group of the user's own copies and follows: the view of the last group line the
    document shows and the block that holds that line, else the last group the import shows for this project and no block.
    None when that view shows no title, so a new group could not be named."""
    groups, shown = _group_nodes(project.template_package), group_lines(project)
    if shown:
        _identifier, line, view = shown[-1]
        parent = placements(project.document)[line.id][0]
        place = (*groups[view], next((block for block in project.document.blocks() if block.id == parent), line))
    else:
        active = [value for value in groups.values() if _shown(project, value[0])]
        if not active:
            return None
        place = (*active[-1], None)
    return place if place[0].view.heading != 'none' else None


def _technology(project, record_id):
    record = next((value for value in project.facts.records if value.id == record_id), None)
    if record is None or record.kind != 'technology':
        raise ValueError('TECHNOLOGY_MOVE_INVALID')
    return record


def _line(project, group_id):
    """The line of the group a plan target names; None for a group of the template the document no longer shows."""
    if not any(value.job_id is None and value.block_id == group_id for value in technology_targets(project)):
        raise ValueError('TECHNOLOGY_GROUP_MISSING')
    if group_id.startswith(VIEW_TARGET):
        view, index, _node = _group_nodes(project.template_package)[group_id.removeprefix(VIEW_TARGET)]
        return _group_line(project, view.id, index)
    return next(block for block in project.document.blocks() if block.id == group_id)


def _take(project, line, record_id):
    """A group line loses a record's entry with its separator; emptied, it goes with its label, the section around it and
    its title."""
    if not line_is_list(project.template_package, line):
        raise ValueError('PANEL_LINE_SHARED')
    prefix, entries, trailing = _split_technology_line(line.content)
    kept = [entry for entry in entries if entry[0] != record_id]
    if kept:
        line.content[:] = _join_technology_line(prefix, kept, trailing)
        return
    where = placements(project.document)
    heading = group_heading(project.document, line, line.presentation.view_key, where)
    gone = {line.id} | node_labels(project, {line.id}) | ({heading.id} if heading is not None else set())
    section = next((block for block in project.document.blocks() if block.id == where[line.id][0]), None)
    if isinstance(section, TemplateSectionBlock) and not section.content and {child.id for child in section.children} <= gone:
        gone.add(section.id)
    for items in sibling_lists(project.document):
        items[:] = [block for block in items if block.id not in gone]


def _leave_groups(project, record_id):
    """The record leaves every group line that shows it; a job's own line and Focus keep it."""
    for _identifier, line, _view in group_lines(project):
        if record_id in line_entries(line):
            _take(project, line, record_id)


def move_to_group(project, command, allocator):
    """(candidate project, steps) moving a technology into a group, before one of its technologies or at its end; inside one
    group it only reorders. The group it leaves loses it, a job keeps its own technology, and a group of the template the
    document no longer shows comes back where the import puts it."""
    record = _technology(project, command.record_id)
    candidate = project.model_copy(deep=True)
    line, before = _line(candidate, command.group_id), command.before_record_id
    if before == record.id or before is not None and (line is None or before not in line_entries(line)):
        raise ValueError('TECHNOLOGY_TARGET_MISSING')
    if line is not None and record.id in line_entries(line):
        prefix, entries, trailing = _split_technology_line(line.content)
        identifiers = [entry[0] for entry in entries]
        index = identifiers.index(record.id)
        destination = len(identifiers) if before is None else identifiers.index(before)
        if destination > index:
            destination -= 1
        if destination == index:
            return None
        entries.insert(destination, entries.pop(index))
        line.content[:] = _join_technology_line(prefix, entries, trailing)
        return candidate, []
    _leave_groups(candidate, record.id)
    if line is None:
        view, index, node = _group_nodes(candidate.template_package)[command.group_id.removeprefix(VIEW_TARGET)]
        restore_group_line(candidate.document, candidate.template_package, (view, index, node), record, allocator)
    else:
        put_entry(candidate.template_package, line, record, allocator, before)
    return candidate, []


def _shown_elsewhere(project, record_id, line):
    return any(block.id != line.id and isinstance(span, FactFieldSpan) and span.record_id == record_id
        for block in project.document.blocks() for _container, content in inline_groups(block) for span in content)


def remove_from_group(project, command, action_id):
    """(candidate project, steps) taking a technology out of one group. A job keeps its own technology and Focus its row; a
    technology shown nowhere else goes from the facts too, as a removal from its list does."""
    if command.job_id is not None or command.period_id is not None or command.values:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    record = _technology(project, command.record_id)
    line = _line(project, command.group_id)
    if line is None or record.id not in line_entries(line):
        raise ValueError('TECHNOLOGY_TARGET_MISSING')
    if not _shown_elsewhere(project, record.id, line):
        return remove_records(project, command, action_id)
    candidate = project.model_copy(deep=True)
    _take(candidate, next(block for block in candidate.document.blocks() if block.id == line.id), record.id)
    return candidate, []


def add_technology_group(project, command, allocator):
    """(candidate project, steps) starting a group of the user's own after the last group, under its title, with a new
    technology or one moved from its group."""
    title = ' '.join(command.values['title'].split())
    if not title:
        raise ValueError('TECHNOLOGY_GROUP_TITLE_REQUIRED')
    if len(title) > TITLE_LIMIT:
        raise ValueError('TECHNOLOGY_GROUP_INVALID')
    if any(value.job_id is None and normalize_name(value.label) == normalize_name(title) for value in technology_targets(project)):
        raise ValueError('TECHNOLOGY_GROUP_DUPLICATE')
    candidate, steps = project.model_copy(deep=True), []
    if command.record_id is not None:
        record = _technology(candidate, command.record_id)
        _leave_groups(candidate, record.id)
    else:
        name = ' '.join(command.values['display'].split())
        if not name:
            raise ValueError('TECHNOLOGY_NAME_REQUIRED')
        if _duplicate(project, None, name):
            raise ValueError('TECHNOLOGY_DUPLICATE')
        record = new_technology(project, None, name, allocator)
        steps.append({'kind': 'put_record', 'beforeRevision': None, 'record': record.model_dump(by_alias=True)})
    # After the record left its group, which may have been the last one.
    place = new_group_place(candidate)
    if place is None:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    view, index, node, holder = place
    package, key = candidate.template_package, normalize_name(title)
    heading_ref = reference(package, view.id, heading_style(package, view),
        allocator.allocate('template-instance', ['panel-group-heading-instance', key]))
    heading = TemplateHeadingBlock(type='heading', id=allocator.allocate('block', ['panel-group-heading', key]), revision=1,
        props={'level': 1}, content=[literal(title, heading_ref)], children=[], provenance=[], presentation=heading_ref)
    ref = reference(package, view.id, node.style, allocator.allocate('template-instance', ['panel-group-instance', key]),
        node_index=index)
    blocks = [heading, *line_blocks(package, allocator, record, 'group:' + key, node, ref)]
    if holder is not None:
        items = next(items for items in sibling_lists(candidate.document) if any(block is holder for block in items))
        at = next(position for position, block in enumerate(items) if block is holder) + 1
    else:
        position = view_position(candidate.document, package, view)
        if position is None:
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        region, at = position
        items = region.blocks
    items[at:at] = blocks
    return candidate, steps
