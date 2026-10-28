"""Facts panel changes outside employment and Focus rows (D113): a field edit of any builtin record, a technology's
entry in its tags line, and removal of a technology, education or language record. The panel offers nothing else."""

from dataclasses import dataclass

from .models.rich_document import FactFieldSpan
from .models.rich_facts import TechnologyRecord
from .models.template_document import BoundLink, FieldOccurrence, PresentedText, TemplateParagraphBlock, TemplateSectionBlock
from .rich_dependencies import placements
from .rich_fields import field_key, inline_groups, set_text, working_field
from .template_builtin_admission import unknown
from .template_facts import delete_subject
from .template_panel_creation import _report_cells
from .template_panel_focus import experience_text, show_experience
from .template_preparation_panel import (_focus_section, _join_technology_line, _patch_displays, _split_technology_line)
from .templates.materialize_nodes import literal, locale_text, reference
from .templates.projection import pointer_tokens
from .technologies import normalize_name

# The fields the panel's dialog shows; employment has its own path.
EDIT_FIELDS = {
    'candidate': {'name', 'title', 'location'},
    'technology': {'display', 'experience'},
    'education': {'institution', 'qualification', 'specialty', 'completion'},
    'language': {'language', 'level'},
    'claim': {'value'},
}
REMOVABLE = {'technology', 'education', 'language'}


@dataclass(frozen=True)
class TechnologyTarget:
    """A place the panel adds a technology to: a tags line of one scope, or a job section whose view has a technology
    line it does not show yet."""
    block_id: str
    job_id: str | None
    label: str


def _separator(node):
    # As the materializer writes it: tags without a declared separator keep the comma.
    return (node.separator or ', ') if node.type == 'tags' else node.separator


def _lines(project):
    """(block, container, content) of each inline group outside Focus rows that lists technology names."""
    focus = {key for key, view in project.template_package.recipe.views.items()
        if any(node.type == 'focus_entry' for node in view.nodes)}
    found = []
    def visit(blocks, inside_focus=False):
        for block in blocks:
            inside = inside_focus or _focus_section(block) or block.presentation is not None and block.presentation.view_key in focus
            if not inside:
                for container, content in inline_groups(block):
                    if _split_technology_line(content)[1]:
                        found.append((block, container, content))
            visit(block.children, inside)
    for region in project.document.regions:
        visit(region.blocks)
    return found


def _title(document, view_key):
    heading = next((block for block in document.blocks() if block.type == 'heading' and block.presentation is not None
        and block.presentation.view_key == view_key and block.presentation.node_index is None), None)
    return ''.join(getattr(part, 'text', '') for part in heading.content) if heading is not None else ''


def _line_node(package, view_id):
    """(index, node) of the items view's tags node that lists each item's own technologies, or None."""
    view = next((value for value in package.definition.blocks if value.id == view_id), None)
    if view is None or view.view.mode != 'items':
        return None
    types = {value.id for value in package.definition.fact_types if value.builtin_kind == 'technology'}
    pointers = {tuple(pointer_tokens(binding.pointer)) for binding in view.bindings
        if binding.semantic_type in types and binding.field == 'display'}
    found = [(index, node) for index, node in enumerate(view.view.nodes) if node.type in {'tags', 'join_items'} and node.field
        and ('*', *pointer_tokens(node.field), '*', 'display') in pointers]
    return found[0] if len(found) == 1 else None


def technology_targets(project):
    """Every tags line whose entries share one scope, then each job section that shows no line of its own but whose view
    has one. The facts panel offers adding a technology only to these."""
    records = {record.id: record for record in project.facts.records if record.kind == 'technology'}
    jobs = {record.id for record in project.facts.records if record.kind == 'employment'}
    targets, shown, nodes = [], set(), {}
    for block, container, content in _lines(project):
        owners = {getattr(records.get(identifier), 'job_id', '?') for identifier, _lead, _spans in _split_technology_line(content)[1]}
        if container != 'content' or len(owners) != 1 or '?' in owners:
            continue
        job = owners.pop()
        shown.add(job)
        targets.append(TechnologyTarget(block.id, job, _title(project.document, block.presentation.view_key)
            if job is None and block.presentation is not None else ''))
    for block in project.document.blocks():
        job = getattr(block.props, 'record_id', None) if isinstance(block, TemplateSectionBlock) else None
        if job not in jobs or job in shown or block.presentation is None:
            continue
        view = block.presentation.view_key
        if view not in nodes:
            nodes[view] = _line_node(project.template_package, view)
        if nodes[view] is not None:
            shown.add(job)
            targets.append(TechnologyTarget(block.id, job, ''))
    return targets


def _duplicate(project, job_id, name, record_id=None):
    key = normalize_name(name)
    return any(record.kind == 'technology' and record.job_id == job_id and record.id != record_id
        and normalize_name(record.display.raw_text) == key for record in project.facts.records)


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
    """(candidate project, steps) removing one technology, education or language record, or every technology of one
    scope; None when the scope has none. Each tags line loses the entry with its separator; a line, section or view
    title left empty goes too, as an import would not show it."""
    records = {record.id: record for record in project.facts.records}
    if command.operation == 'clear_technologies':
        if command.job_id is not None and getattr(records.get(command.job_id), 'kind', None) != 'employment':
            raise ValueError('PANEL_OWNER_INVALID')
        targets = [record for record in project.facts.records if record.kind == 'technology' and record.job_id == command.job_id]
        if not targets:
            return None
    else:
        target = records.get(command.record_id)
        if target is None or target.kind not in REMOVABLE or command.values or command.period_id is not None:
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        targets = [target]
    facts = project.facts
    for record in targets:
        facts = delete_subject(facts, record.id, action_id)
    def alive(value):
        return {record.id for record in [*value.records, *value.extensions] if getattr(record, 'active', True)}
    removed = alive(project.facts) - alive(facts)
    candidate = project.model_copy(deep=True)
    emptied = set()
    for block, container, content in _lines(candidate):
        prefix, entries, trailing = _split_technology_line(content)
        kept = [entry for entry in entries if entry[0] not in removed]
        if len(kept) != len(entries):
            content[:] = _join_technology_line(prefix, kept, trailing)
            if not kept and container == 'content' and not block.children and all(isinstance(node, PresentedText) for node in content):
                emptied.add(block.id)
    views = set()
    def prune(items):
        for block in list(items):
            if getattr(block.props, 'record_id', None) in removed or block.id in emptied:
                views.add(block.presentation.view_key if block.presentation is not None else None)
                items.remove(block)
                continue
            prune(block.children)
            # A removed record shown inside other text would leave a broken sentence; that text is the user's to edit.
            if any(_bound(span, removed) for _container, content in inline_groups(block) for span in content):
                raise ValueError('PANEL_LINE_SHARED')
            block.provenance = [value for value in block.provenance if getattr(value, 'record_id', None) not in removed]
            if isinstance(block, TemplateSectionBlock) and not block.children and not block.content \
                    and block.presentation is not None and block.presentation.view_key in views:
                items.remove(block)
    for region in candidate.document.regions:
        prune(region.blocks)
    for view in views - {None}:
        blocks = [block for block in candidate.document.blocks() if block.presentation is not None and block.presentation.view_key == view]
        if all(block.type == 'heading' and block.presentation.node_index is None for block in blocks):
            titles = {block.id for block in blocks}
            for items in _sibling_lists(candidate.document):
                items[:] = [block for block in items if block.id not in titles]
    steps = [{'kind': 'remove_record', 'recordId': record.id, 'beforeRevision': record.revision} for record in targets]
    return candidate, steps


def _sibling_lists(document):
    def visit(items):
        yield items
        for block in items:
            yield from visit(block.children)
    for region in document.regions:
        yield from visit(region.blocks)


def add_technology(project, operation, allocator):
    """(candidate project, steps) adding one technology to the end of a target line; a job without a line gets one from
    its view's tags node. Several targets in one scope need the placement context's choice."""
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
        if target is None or placements(project.document)[target.block_id][:2] != (context.placement.parent_id,
                context.placement.after_id):
            raise ValueError('TECHNOLOGY_LINE_MISSING')
    record_id = allocator.allocate('technology', ['panel-technology', command.job_id or '', normalize_name(name)])
    record = TechnologyRecord(id=record_id, kind='technology', revision=1, origin='user', userCorrected=True, evidence=[],
        jobId=command.job_id, subprojectId=None, display=unknown(), canonicalId=unknown())
    set_text(record, 'display', name)
    _report_cells(project, record, allocator)
    candidate = project.model_copy(deep=True)
    block = next(value for value in candidate.document.blocks() if value.id == target.block_id)
    package = candidate.template_package
    def occurrence(ref):
        value = working_field(record, 'display')
        root = allocator.allocate('occurrence', ['panel-technology-occurrence', record.id])
        return FieldOccurrence(type='fact_field', bindingId=allocator.allocate('fragment', ['panel-technology-fragment', root]),
            bindingRootId=root, recordId=record.id, fieldKey='display', cellId=field_key(record.id, 'display'),
            occurrenceId=root, complete=True, presentation=ref, text=value.raw_text, styles={}, syncedFactRevision=value.revision)
    if isinstance(block, TemplateSectionBlock):
        index, node = _line_node(package, block.presentation.view_key)
        ref = reference(package, block.presentation.view_key, node.style, block.presentation.template_instance_id,
            block.presentation.item_handle, node_index=index)
        locale = package.definition.template.default_locale
        prefix, label = locale_text(node.prefix, locale), locale_text(node.label, locale)
        def paragraph(slot, content):
            return TemplateParagraphBlock(type='paragraph', id=allocator.allocate('block', [slot, block.id]), revision=1,
                props={'alignment': ref.overrides.alignment or 'left'}, children=[], provenance=[], presentation=ref,
                content=content)
        lines = [paragraph('panel-technology-line', [*([literal(prefix, ref)] if prefix else []), occurrence(ref)])]
        if label:
            lines.insert(0, paragraph('panel-technology-label', [literal(label, ref)]))
        # After the item's blocks of earlier nodes, where the import puts the line.
        at = sum(1 for child in block.children if child.presentation is not None and child.presentation.node_index is not None
            and child.presentation.node_index < index)
        block.children[at:at] = lines
    else:
        content = block.content
        prefix, entries, trailing = _split_technology_line(content)
        sample = entries[-1][2][-1]
        ref = (sample.presentation or block.presentation).model_copy(deep=True)
        node = package.recipe.views[ref.view_key].nodes[ref.node_index] if ref.node_index is not None else None
        # A line of one entry has no separator to copy; the node's own one is the import's.
        separator = literal((_separator(node) if node is not None else '') or ', ', ref)
        entries.append((record.id, [], [occurrence(ref)]))
        content[:] = _join_technology_line(prefix, entries, trailing, separator)
    return candidate, [{'kind': 'put_record', 'beforeRevision': None, 'record': record.model_dump(by_alias=True)}]
