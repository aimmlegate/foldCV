"""Facts panel changes outside employment and Focus rows (D113): field edits of builtin records, technologies in their
lines, and removal of technology, education and language records. The panel offers nothing else."""

from .models.rich_document import FactFieldSpan
from .models.rich_facts import TechnologyRecord
from .models.template_document import BoundLink, PresentedText, TemplateParagraphBlock, TemplateSectionBlock
from .rich_dependencies import placements
from .rich_fields import field_key, inline_groups, occurrences, set_text, working_field
from .rich_panel import FIELDS
from .template_api import EditorPlacement, EditorTechnologyTarget
from .template_builtin_admission import unknown
from .template_facts import delete_subject_in_place
from .template_panel_creation import _report_cells, period_jobs
from .template_panel_focus import experience_text, focus_only, focus_rows, focus_view, show_experience
from .template_panel_lines import field_place, line_text, node_labels, period_text, show_fields
from .template_preparation_panel import (_join_technology_line, _patch_displays, _split_technology_line, drop_empty_titles,
    field_occurrence, line_is_list, restore_view, sibling_lists, technology_lines, view_position, view_title)
from .templates.materialize_nodes import literal, locale_text, reference
from .templates.operations import OperationContext, active, display_pointer, select_role_branch
from .templates.projection import pointer_tokens
from .technologies import normalize_name

# The fields the panel's dialog shows; employment has its own path.
EDIT_FIELDS = {kind: set(FIELDS[kind]) for kind in ('candidate', 'technology', 'education', 'language', 'claim')}
REMOVABLE = {'technology', 'education', 'language'}
# Fields the dialog shows that only reach the document through a template node.
DOCUMENT_FIELDS = {'candidate': EDIT_FIELDS['candidate'], 'education': EDIT_FIELDS['education'],
    'language': EDIT_FIELDS['language'], 'employment': {'employer', 'role'}}
# A group's target names its view, so it stays the same when the group's line goes and comes back.
VIEW_TARGET = 'view:'


def _separator(node):
    # As the materializer writes it: tags without a declared separator keep the comma.
    return (node.separator or ', ') if node.type == 'tags' else node.separator


def _names_technology(definition):
    """Whether a binding binds the technology name, through the builtin mapping of its fact type."""
    types = {value.id: value for value in definition.fact_types}
    def check(binding):
        declaration = types[binding.semantic_type]
        mapped = declaration.builtin_fields.get(binding.field)
        return declaration.builtin_kind == 'technology' and mapped is not None and mapped.field == 'display'
    return check


def _list_nodes(view, pointer):
    """(index, node) of each tags or join node of a view that lists the bound names at the pointer."""
    return [(index, node) for index, node in enumerate(view.view.nodes) if node.type in {'tags', 'join_items'} and node.field
        and (*pointer_tokens(node.field), '*', *(pointer_tokens(node.item_field) if node.item_field else ())) == pointer]


def _line_node(package, view_id):
    """(index, node) of the items view's tags node that lists each item's own technologies, or None."""
    view = next((value for value in package.definition.blocks if value.id == view_id), None)
    if view is None or view.view.mode != 'items':
        return None
    names = _names_technology(package.definition)
    found = [value for binding in view.bindings if names(binding) and pointer_tokens(binding.pointer)[:1] == ['*']
        for value in _list_nodes(view, tuple(pointer_tokens(binding.pointer)[1:]))]
    return found[0] if len(found) == 1 else None


def _group_nodes(package):
    """View id to (view, node index, node) for each view that lists general technology names in one line, such as a
    skill group."""
    found = {}
    for view in package.definition.blocks:
        if view.view.mode == 'items' or any(node.type == 'focus_entry' for node in view.view.nodes):
            continue
        pointer = display_pointer(package.definition, view)
        nodes = _list_nodes(view, tuple(pointer)) if pointer is not None else []
        if len(nodes) == 1:
            found[view.id] = (view, *nodes[0])
    return found


def _shown(project, view):
    """Whether the import shows the view for this project. Its role branch is chosen again from the facts, as the import
    chose it: an edited workspace keeps no operation results."""
    if view.when is None:
        return True
    declaration = next((value for value in project.template_package.definition.operations if value.id == view.when.operation
        and value.kind == 'select_role_branch'), None)
    return declaration is not None and active(view, {view.when.operation: select_role_branch(declaration,
        OperationContext(capture=None, facts=project.facts)).value})


def _placement(where, block_id):
    parent, previous, _owner = where[block_id]
    return EditorPlacement(parentId=parent, afterId=previous)


def _group_line(project, view_id, index):
    """The first line a group view shows, or None."""
    return next((block for block, container, _content, owner in technology_lines(project) if owner is None
        and container == 'content' and block.presentation is not None and block.presentation.view_key == view_id
        and block.presentation.node_index == index), None)


def technology_targets(project):
    """Where the facts panel adds a technology, with the placement Python checks: a job's line, else its section; each
    group the import shows for this project, by template order, at its line or where the line goes."""
    package, document = project.template_package, project.document
    jobs = {record.id for record in project.facts.records if record.kind == 'employment'}
    where, order = placements(document), {value.id: index for index, value in enumerate(package.definition.blocks)}
    groups, nodes = _group_nodes(package), {}
    general, owned, lined = [], [], set()
    for block, container, _content, owner in technology_lines(project):
        ref = block.presentation
        if container != 'content' or ref is None:
            continue
        # The scope is the view and item section that show the line, not the current owners of its entries.
        if owner is None and ref.view_key in groups and ref.node_index == groups[ref.view_key][1]:
            if ref.view_key in lined:
                continue
            lined.add(ref.view_key)
            title = next((''.join(getattr(part, 'text', '') for part in value.content) for value in document.blocks()
                if view_title(value, ref.view_key)), '')
            general.append((order[ref.view_key], EditorTechnologyTarget(blockId=VIEW_TARGET + ref.view_key, jobId=None,
                label=title, placement=_placement(where, block.id))))
        elif owner in jobs:
            if ref.view_key not in nodes:
                nodes[ref.view_key] = _line_node(package, ref.view_key)
            if nodes[ref.view_key] is not None and ref.node_index == nodes[ref.view_key][0]:
                owned.append(EditorTechnologyTarget(blockId=block.id, jobId=owner, label='',
                    placement=_placement(where, block.id)))
    shown = {value.job_id for value in owned}
    for block in document.blocks():
        job = block.props.record_id if isinstance(block, TemplateSectionBlock) else None
        if job not in jobs or job in shown or block.presentation is None:
            continue
        view = block.presentation.view_key
        if view not in nodes:
            nodes[view] = _line_node(package, view)
        if nodes[view] is not None:
            shown.add(job)
            owned.append(EditorTechnologyTarget(blockId=block.id, jobId=job, label='', placement=_placement(where, block.id)))
    locale = package.definition.template.default_locale
    for view, _index, _node in groups.values():
        if view.id in lined or not _shown(project, view):
            continue
        title = next(((items, value) for items in sibling_lists(document) for value in items if view_title(value, view.id)), None)
        if title is not None:
            placement = EditorPlacement(parentId=where[title[1].id][0], afterId=title[1].id)
        elif (position := _view_position(project, view)) is not None:
            placement = position
        else:
            continue
        general.append((order[view.id], EditorTechnologyTarget(blockId=VIEW_TARGET + view.id, jobId=None,
            label=locale_text(view.view.title, locale), placement=placement)))
    return [target for _order, target in sorted(general, key=lambda value: value[0])] + owned


def panel_plan(project):
    """What the facts panel shows and offers beyond its targets (D113): each job's periods as the document writes them and
    whether it can take another, the fields with no place in the document, and the technologies that share a line, the
    only order a move can change."""
    package, jobs, unshown = project.template_package, {}, {}
    addable = period_jobs(project)
    shown = {(group.record_id, group.key) for group in occurrences(project.document).values()}
    for record in project.facts.records:
        missing = sorted(key for key in DOCUMENT_FIELDS.get(record.kind, ()) if (record.id, key) not in shown
            and field_place(project, record, key) is None)
        if missing:
            unshown[record.id] = missing
        if record.kind == 'employment':
            jobs[record.id] = {'periods': [period_text(period, package) for period in record.periods],
                **({'addPeriod': True} if record.id in addable else {})}
    lines = [identifiers for _block, _container, content, _owner in technology_lines(project)
        if len(identifiers := [entry[0] for entry in _split_technology_line(content)[1]]) > 1
        and len(identifiers) == len(set(identifiers))]
    return {key: value for key, value in (('jobs', jobs), ('unshownFields', unshown), ('technologyLines', lines)) if value}


def _view_position(project, view):
    position = view_position(project.document, project.template_package, view)
    if position is None:
        return None
    region, at = position
    return EditorPlacement(parentId=region.id, afterId=region.blocks[at - 1].id if at else None)


def _duplicate(project, job_id, name, record_id=None):
    """Whether the list that shows the record already has the name: the Focus rows for a record only Focus shows, else
    the scope's technologies outside them."""
    only = focus_only(project) or frozenset()
    if record_id in only:
        view = focus_view(project.template_package)[0]
        technologies = {record.id for record in project.facts.records if record.kind == 'technology'}
        listed = {section.props.record_id for _items, section in focus_rows(project.document, view.id, technologies)}
    else:
        listed = {record.id for record in project.facts.records if record.kind == 'technology' and record.job_id == job_id}
        listed -= only
    key = normalize_name(name)
    return any(record.id in listed and record.id != record_id and normalize_name(record.display.raw_text) == key
        for record in project.facts.records)


def edit_record(project, command, allocator):
    """(candidate project, steps) of a field edit of a non-employment record; None when every value is unchanged."""
    original = next((value for value in project.facts.records if value.id == command.record_id), None)
    if (original is None or original.kind not in EDIT_FIELDS or command.job_id is not None or command.period_id is not None
            or not command.values or not command.values.keys() <= EDIT_FIELDS[original.kind]):
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    values = dict(command.values)
    if original.kind == 'technology':
        if 'experience' in values:
            values['experience'] = experience_text(project.template_package, values['experience'])
        if 'display' in values:
            values['display'] = ' '.join(values['display'].split())
            if not values['display']:
                raise ValueError('TECHNOLOGY_NAME_REQUIRED')
            if _duplicate(project, original.job_id, values['display'], original.id):
                raise ValueError('TECHNOLOGY_DUPLICATE')
    selected = {key for key, text in values.items() if working_field(original, key).raw_text != text}
    if not selected:
        return None
    updated = original.model_copy(deep=True)
    for key in selected:
        set_text(updated, key, values[key])
    candidate = project.model_copy(deep=True)
    _patch_displays(project, candidate, original, updated, selected, set(), allocator)
    if 'experience' in selected:
        show_experience(candidate, updated, allocator)
    show_fields(candidate, updated, selected - {'experience'}, allocator)
    steps = [{'kind': 'put_record', 'beforeRevision': original.revision, 'record': updated.model_dump(by_alias=True)}]
    for key in sorted(selected):
        cell = field_key(original.id, key)
        scope = project.facts.builtin_manual_scopes.get(cell)
        if scope is not None:
            steps.append({'kind': 'set_builtin_manual_scope', 'cellId': cell, 'beforeScopeId': scope, 'afterScopeId': None})
    return candidate, steps


def _bound(span, removed):
    if isinstance(span, BoundLink):
        return any(value is not None and value.record_id in removed for value in (span.label_binding, span.url_binding)) \
            or any(_bound(child, removed) for child in span.content)
    return isinstance(span, FactFieldSpan) and span.record_id in removed


def remove_records(project, command, action_id):
    """(candidate project, steps) removing one technology, education or language record, or a scope's listed technologies;
    a line loses each entry with its separator, an emptied line, label, item section or view title goes too."""
    records = {record.id: record for record in project.facts.records}
    if command.operation == 'clear_technologies':
        if command.job_id is not None and getattr(records.get(command.job_id), 'kind', None) != 'employment':
            raise ValueError('PANEL_OWNER_INVALID')
        # The list leaves out the records only Focus rows show; Focus keeps them.
        only = focus_only(project) or frozenset()
        targets = [record for record in project.facts.records if record.kind == 'technology'
            and record.job_id == command.job_id and record.id not in only]
        if not targets:
            return None
    else:
        target = records.get(command.record_id)
        if target is None or target.kind not in REMOVABLE or command.values or command.period_id is not None:
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        targets = [target]
    # One copy for every removal: the facts only tell which records the cascade takes.
    facts, removed = project.facts.model_copy(deep=True), set()
    order = {record.id: index for index, record in enumerate([*facts.records, *facts.extensions])}
    for record in targets:
        removed |= delete_subject_in_place(facts, record.id, action_id, order=order)
    candidate = project.model_copy(deep=True)
    emptied = set()
    for block, container, content, _owner in technology_lines(candidate):
        prefix, entries, trailing = _split_technology_line(content)
        kept = [entry for entry in entries if entry[0] not in removed]
        if len(kept) != len(entries):
            # A name inside other text would leave a broken sentence; that text is the user's to edit.
            if container == 'content' and not line_is_list(candidate.template_package, block):
                raise ValueError('PANEL_LINE_SHARED')
            content[:] = _join_technology_line(prefix, kept, trailing)
            if not kept and container == 'content' and not block.children and all(isinstance(node, PresentedText) for node in content):
                emptied.add(block.id)
    emptied |= node_labels(candidate, emptied)
    views = set()
    def prune(items):
        for block in list(items):
            if getattr(block.props, 'record_id', None) in removed or block.id in emptied:
                views.add(block.presentation.view_key if block.presentation is not None else None)
                items.remove(block)
                continue
            prune(block.children)
            if any(_bound(span, removed) for _container, content in inline_groups(block) for span in content):
                raise ValueError('PANEL_LINE_SHARED')
            block.provenance = [value for value in block.provenance if getattr(value, 'record_id', None) not in removed]
            if isinstance(block, TemplateSectionBlock) and not block.children and not block.content \
                    and block.presentation is not None and block.presentation.view_key in views:
                items.remove(block)
    for region in candidate.document.regions:
        prune(region.blocks)
    drop_empty_titles(candidate.document, views)
    steps = [{'kind': 'remove_record', 'recordId': record.id, 'beforeRevision': record.revision} for record in targets]
    return candidate, steps


def add_technology(project, operation, allocator):
    """(candidate project, steps) adding one technology to the end of a target's line, which a job or group without one
    gets from its view; with several targets in one scope the placement context names one."""
    command = operation.command
    if command.record_id is not None or command.period_id is not None or command.values.keys() != {'display'}:
        raise ValueError('PANEL_ACTION_UNSUPPORTED')
    name = ' '.join(command.values['display'].split())
    if not name:
        raise ValueError('TECHNOLOGY_NAME_REQUIRED')
    jobs = {record.id for record in project.facts.records if record.kind == 'employment'}
    if command.job_id is not None and command.job_id not in jobs:
        raise ValueError('PANEL_OWNER_INVALID')
    if _duplicate(project, command.job_id, name):
        raise ValueError('TECHNOLOGY_DUPLICATE')
    scope = [value for value in technology_targets(project) if value.job_id == command.job_id]
    context = operation.placement_context
    if context is None:
        if len(scope) != 1:
            raise ValueError('TECHNOLOGY_GROUP_REQUIRED' if scope else 'TECHNOLOGY_LINE_MISSING')
        target = scope[0]
    else:
        target = next((value for value in scope if value.block_id == context.context_block_id), None)
        if target is None or (target.placement.parent_id, target.placement.after_id) != (context.placement.parent_id,
                context.placement.after_id):
            raise ValueError('TECHNOLOGY_LINE_MISSING')
    record_id = allocator.allocate('technology', ['panel-technology', command.job_id or '', normalize_name(name)])
    record = TechnologyRecord(id=record_id, kind='technology', revision=1, origin='user', userCorrected=True, evidence=[],
        jobId=command.job_id, subprojectId=None, display=unknown(), canonicalId=unknown())
    set_text(record, 'display', name)
    _report_cells(project, record, allocator)
    candidate = project.model_copy(deep=True)
    package = candidate.template_package
    locale = package.definition.template.default_locale
    def paragraph(slot, owner, ref, content):
        return TemplateParagraphBlock(type='paragraph', id=allocator.allocate('block', [slot, owner]), revision=1,
            props={'alignment': ref.overrides.alignment or 'left'}, children=[], provenance=[], presentation=ref,
            content=content)
    def line(owner, node, ref, labelled):
        """The new line of one node with its prefix, after the node's label unless one is shown already."""
        prefix, label = locale_text(node.prefix, locale), locale_text(node.label, locale)
        blocks = [paragraph('panel-technology-line', owner, ref, [*([literal(prefix, ref)] if prefix else []),
            field_occurrence(allocator, 'technology', record, 'display', ref)])]
        return [paragraph('panel-technology-label', owner, ref, [literal(label, ref)]), *blocks] if label and not labelled else blocks
    group = _group_nodes(package).get(target.block_id.removeprefix(VIEW_TARGET)) if target.block_id.startswith(VIEW_TARGET) else None
    block = _group_line(candidate, group[0].id, group[1]) if group is not None else next(value for value
        in candidate.document.blocks() if value.id == target.block_id)
    if group is not None and block is None:
        # The group's line went with its last technology: it comes back after the title, or with it.
        view, index, node = group
        ref = reference(package, view.id, node.style, allocator.allocate('template-instance',
            ['panel-technology-instance', view.id]), node_index=index)
        blocks = line(view.id, node, ref, False)
        title = next(((items, value) for items in sibling_lists(candidate.document) for value in items
            if view_title(value, view.id)), None)
        if title is not None:
            items, heading = title
            items[items.index(heading) + 1:items.index(heading) + 1] = blocks
        elif not restore_view(candidate.document, package, view, blocks, allocator, 'technology'):
            raise ValueError('TECHNOLOGY_LINE_MISSING')
        return candidate, [{'kind': 'put_record', 'beforeRevision': None, 'record': record.model_dump(by_alias=True)}]
    if isinstance(block, TemplateSectionBlock):
        index, node = _line_node(package, block.presentation.view_key)
        ref = reference(package, block.presentation.view_key, node.style, block.presentation.template_instance_id,
            block.presentation.item_handle, node_index=index)
        label = locale_text(node.label, locale)
        # A label an earlier removal left behind is used again, not doubled.
        labelled = bool(label) and any(child.presentation is not None and child.presentation.node_index == index
            and line_text(child) == label for child in block.children)
        # After the item's blocks of earlier nodes and the node's own label, where the import puts the line.
        at = sum(1 for child in block.children if child.presentation is not None and child.presentation.node_index is not None
            and child.presentation.node_index <= index)
        block.children[at:at] = line(block.id, node, ref, labelled)
    else:
        content = block.content
        prefix, entries, trailing = _split_technology_line(content)
        sample = entries[-1][2][-1]
        ref = (sample.presentation or block.presentation).model_copy(deep=True)
        node = package.recipe.views[ref.view_key].nodes[ref.node_index] if ref.node_index is not None else None
        # A line of one entry has no separator to copy; the node's own one is the import's.
        separator = literal((_separator(node) if node is not None else '') or ', ', ref)
        entries.append((record.id, [], [field_occurrence(allocator, 'technology', record, 'display', ref)]))
        content[:] = _join_technology_line(prefix, entries, trailing, separator)
    return candidate, [{'kind': 'put_record', 'beforeRevision': None, 'record': record.model_dump(by_alias=True)}]
