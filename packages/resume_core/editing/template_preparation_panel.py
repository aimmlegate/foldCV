"""Facts panel changes keep authored wording outside selected canonical fields."""

from ..models.rich_document import FactFieldSpan
from ..models.template_authoring import BuiltinPanel, DeleteEntity
from ..models.template_document import BoundLink, TemplateSectionBlock
from ..fields import field_key, inline_groups, set_text, working_field
from ..template_anchors import anchor_steps
from ..fact_records import delete_subject
from .template_panel_lines import block_node, node_labels, show_fields, sync_period_lines
from .template_panel_values import written_dates
from .template_preparation_blocks import changed_block_steps
from .template_preparation_common import (allocator_for, finish_preparation, next_facts, prepared_response,
                                          validate_preparation)
from .panel_views import (_join_technology_line, _patch_displays, _split_technology_line, drop_empty_titles,
                          line_is_list, technology_lines)

# Panel refusals the user can act on; the edit route answers with these codes instead of a generic rejection.
PANEL_REFUSALS = frozenset({'PANEL_ACTION_UNSUPPORTED', 'PANEL_LINE_SHARED', 'PANEL_OWNER_INVALID', 'TECHNOLOGY_DUPLICATE',
    'TECHNOLOGY_NAME_REQUIRED', 'TECHNOLOGY_NAME_EMPTY', 'TECHNOLOGY_GROUP_REQUIRED', 'TECHNOLOGY_LINE_MISSING', 'TECHNOLOGY_MOVE_INVALID',
    'TECHNOLOGY_TARGET_MISSING', 'FOCUS_DUPLICATE', 'FOCUS_FULL', 'FOCUS_SCOPE_INVALID', 'FOCUS_VIEW_MISSING',
    'FOCUS_ICON_UNKNOWN'})












def _drop_joined_entries(project, removed):
    """Removed records leave list lines with their separators; returns the lines left empty, with their labels."""
    emptied = set()
    for block in project.document.blocks():
        node = block_node(project.template_package, block)
        if node is None or node.type not in {'join_items', 'tags'} or not isinstance(block.content, list):
            continue
        prefix, entries, trailing = _split_technology_line(block.content, _joined_entry)
        kept = [entry for entry in entries if entry[0] not in removed]
        if len(kept) != len(entries):
            block.content[:] = _join_technology_line(prefix, kept, trailing)
            if not kept and not block.children and line_is_list(project.template_package, block):
                emptied.add(block.id)
    return emptied | node_labels(project, emptied)


def _delete_entity(workspace, record_id, revision, action_id):
    project = workspace.project
    records = {record.id: record for record in [*project.facts.records, *project.facts.extensions]
        if getattr(record, 'active', True)}
    record = records.get(record_id)
    if record is None or record.revision != revision:
        raise ValueError('stale entity deletion')
    facts = delete_subject(project.facts, record_id, action_id)
    remaining = {value.id for value in [*facts.records, *facts.extensions] if getattr(value, 'active', True)}
    removed = records.keys() - remaining
    candidate = project.model_copy(deep=True)
    emptied = _drop_joined_entries(candidate, removed)
    views = set()
    def prune(items):
        for block in list(items):
            if getattr(block.props, 'record_id', None) in removed or block.id in emptied:
                views.add(block.presentation.view_key if block.presentation is not None else None)
                items.remove(block)
                continue
            prune(block.children)
            for _container, content in inline_groups(block):
                for span in content:
                    if isinstance(span, BoundLink) and any(value is not None and value.record_id in removed
                            for value in (span.label_binding, span.url_binding)):
                        raise ValueError('semantic link deletion needs its dedicated adapter')
                content[:] = [span for span in content if not isinstance(span, FactFieldSpan) or span.record_id not in removed]
            block.provenance = [value for value in block.provenance if getattr(value, 'record_id', None) not in removed]
            if isinstance(block, TemplateSectionBlock) and not block.children and not block.content \
                    and block.presentation is not None and block.presentation.view_key in views:
                items.remove(block)
    for region in candidate.document.regions:
        prune(region.blocks)
    # A job's technology in Focus takes its row; the Focus title goes with the last one.
    drop_empty_titles(candidate.document, views)
    steps = [{'kind': 'remove_extension' if hasattr(record, 'cells') else 'remove_record',
        'recordId': record.id, 'beforeRevision': record.revision}]
    return candidate, steps










def _joined_entry(span):
    return isinstance(span, FactFieldSpan) and getattr(span, 'complete', True)










def _reorder_technology_displays(project, command):
    records = {record.id: record for record in project.facts.records}
    record = records.get(command.record_id)
    before_id = command.before_record_id
    target = records.get(before_id) if before_id else None
    if record is None or record.kind != 'technology' or before_id and (
            target is None or target.kind != 'technology' or target.job_id != record.job_id):
        raise ValueError('TECHNOLOGY_MOVE_INVALID')
    if before_id == record.id:
        return None
    candidate = project.model_copy(deep=True)
    changed, matched, present = False, False, False
    for _block, _container, content, _owner in technology_lines(candidate):
        prefix, entries, trailing = _split_technology_line(content)
        identifiers = [item[0] for item in entries]
        if record.id not in identifiers:
            continue
        if len(identifiers) != len(set(identifiers)):
            raise ValueError('TECHNOLOGY_MOVE_INVALID')
        present = True
        if before_id is not None and before_id not in identifiers:
            continue
        matched = True
        index = identifiers.index(record.id)
        destination = len(identifiers) if before_id is None else identifiers.index(before_id)
        if destination > index:
            destination -= 1
        if index == destination:
            continue
        entries.insert(destination, entries.pop(index))
        content[:] = _join_technology_line(prefix, entries, trailing)
        changed = True
    if not present:
        raise ValueError('TECHNOLOGY_MOVE_INVALID')
    if before_id is not None and not matched:
        raise ValueError('TECHNOLOGY_TARGET_MISSING')
    return candidate if changed else None


def _employment_change(workspace, command, allocator, action_id):
    """(candidate project, steps) of a job's removal, field edit or period removal; None when nothing changes."""
    original = next((record for record in workspace.project.facts.records if record.id == command.record_id), None)
    if original is None or original.kind != 'employment':
        raise ValueError('employment panel target missing')
    if command.operation == 'remove':
        if command.values or command.period_id is not None:
            raise ValueError('employment deletion has unexpected fields')
        return _delete_entity(workspace, original.id, original.revision, action_id)
    if command.operation not in {'edit', 'remove_period'}:
        raise ValueError('employment panel creation requires its captured creation adapter')
    updated = original.model_copy(deep=True)
    removed_periods = set()
    if command.operation == 'remove_period':
        if command.values or command.period_id not in {period.id for period in updated.periods}:
            raise ValueError('employment period deletion target missing')
        removed_periods.add(command.period_id)
        updated.periods = [period for period in updated.periods if period.id not in removed_periods]
    elif command.period_id is not None:
        raise ValueError('employment edit uses explicit canonical period field keys')
    allowed = {'employer', 'role'} | {'period:' + period.id + ':' + key
        for period in updated.periods for key in ('start', 'end', 'present')}
    if not command.values.keys() <= allowed:
        raise ValueError('employment panel field is unknown')
    selected = {key for key, text in command.values.items() if working_field(original, key).raw_text != text}
    if not selected and not removed_periods:
        return None
    for key in selected:
        set_text(updated, key, command.values[key])
    written_dates(workspace.project.facts, original, updated, selected)
    candidate = workspace.project.model_copy(deep=True)
    _patch_displays(workspace.project, candidate, original, updated, selected, removed_periods, allocator)
    sync_period_lines(workspace.project, candidate, original, updated, selected, removed_periods, allocator)
    show_fields(candidate, updated, {key for key in selected if not key.startswith('period:')}, allocator)
    steps = [{'kind': 'put_record', 'beforeRevision': original.revision, 'record': updated.model_dump(by_alias=True)}]
    for cell, scope_id in workspace.project.facts.builtin_manual_scopes.items():
        if cell in {field_key(original.id, key) for key in selected} or any(
                cell == field_key(original.id, 'period:' + identifier + ':' + key)
                for identifier in removed_periods for key in ('start', 'end', 'present')):
            steps.append({'kind': 'set_builtin_manual_scope', 'cellId': cell, 'beforeScopeId': scope_id, 'afterScopeId': None})
    return candidate, steps


def prepare_panel_edit(response, request, *, occupied=None, remembered=None):
    validate_preparation(response, request)
    workspace = response.workspace
    operation = request.operations[0]
    allocator = allocator_for(response, request, operation, occupied)
    if isinstance(operation, DeleteEntity):
        candidate, steps = _delete_entity(workspace, operation.record_id, operation.before_revision, request.capture.action_id)
    elif isinstance(operation, BuiltinPanel):
        command = operation.command
        if ((command.facts_revision, command.document_revision) != (workspace.project.facts.revision, workspace.document_revision)
                or command.capture != request.capture):
            raise ValueError('stale or incompatible employment panel command')
        # Only an add names a place: the line of a technology, the position of a job or a period.
        if operation.placement_context is not None and command.operation not in {'add', 'add_period'}:
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        from .template_panel_creation import SCALAR_RECORDS, create_scalar
        from .template_panel_focus import FOCUS_OPERATIONS, prepare_focus
        from .template_panel_records import add_technology, edit_record, remove_records
        records = {value.id: value.kind for value in workspace.project.facts.records}
        kind = records.get(command.record_id) if command.record_id is not None else command.record_kind
        from .template_panel_groups import add_technology_group, move_to_group, remove_from_group
        if command.operation in FOCUS_OPERATIONS:
            prepared = prepare_focus(workspace, command, allocator, remembered)
        elif command.operation == 'add' and command.record_kind == 'technology':
            prepared = add_technology(workspace.project, operation, allocator)
        elif command.operation == 'move_technology' and command.group_id is not None:
            prepared = move_to_group(workspace.project, command, allocator)
        elif command.operation == 'remove' and command.group_id is not None:
            prepared = remove_from_group(workspace.project, command, request.capture.action_id)
        elif command.operation == 'add_technology_group':
            prepared = add_technology_group(workspace.project, command, allocator)
        elif command.operation in {'edit', 'remove', 'clear_technologies'} and kind not in {None, 'employment'}:
            prepared = (edit_record(workspace.project, command, allocator) if command.operation == 'edit'
                else remove_records(workspace.project, command, request.capture.action_id))
        elif command.operation == 'move_technology':
            moved = _reorder_technology_displays(workspace.project, command)
            prepared = (moved, []) if moved is not None else None
        elif command.operation == 'add' and command.record_kind in SCALAR_RECORDS and command.job_id is None:
            prepared = create_scalar(workspace, operation, allocator)
        elif command.job_id is not None or command.record_kind not in {None, 'employment'}:
            # Adding a candidate or a claim has no adapter; the panel does not offer it.
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        elif command.operation in {'add', 'add_period'}:
            from .template_panel_creation import create_employment, create_period
            create = create_employment if command.operation == 'add' else create_period
            prepared = create(workspace, operation, allocator)
        else:
            prepared = _employment_change(workspace, command, allocator, request.capture.action_id)
        if prepared is None:
            return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
        candidate, steps = prepared
    else:
        raise ValueError('panel preparation needs a panel or entity operation')
    if steps:
        from .template_panel_focus import refresh_durations
        refresh_durations(workspace, candidate, next_facts(response, request, steps), allocator)
    tree, replacements = changed_block_steps(workspace.project.document, candidate.document)
    steps += tree + [value.model_dump(by_alias=True) for value in anchor_steps(workspace.project, replacements)]
    return finish_preparation(response, request, allocator, steps, candidate, kind='panel')
