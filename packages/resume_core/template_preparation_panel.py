"""Facts panel changes keep authored wording outside selected canonical fields."""

from .models.rich_document import FactFieldSpan
from .models.template_authoring import BuiltinPanel, DeleteEntity
from .models.template_document import BoundLink, PresentedText
from .rich_fields import field_key, inline_groups, occurrences, set_text, working_field
from .template_anchors import anchor_steps
from .template_facts import delete_subject
from .template_panel_values import period_endpoint, period_field_id
from .template_preparation_blocks import changed_block_steps
from .template_preparation_common import allocator_for, finish_preparation, prepared_response, validate_preparation


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
    def prune(items):
        for block in list(items):
            if getattr(block.props, 'record_id', None) in removed:
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
    for region in candidate.document.regions:
        prune(region.blocks)
    steps = [{'kind': 'remove_extension' if hasattr(record, 'cells') else 'remove_record',
        'recordId': record.id, 'beforeRevision': record.revision}]
    return candidate, steps


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


def _technology_lists(document):
    found = []
    def visit(blocks, focus=False):
        for block in blocks:
            inside = focus or _focus_section(block)
            if not inside:
                for _container, content in inline_groups(block):
                    if any(isinstance(span, FactFieldSpan) and span.field_key == 'display' for span in content):
                        found.append(content)
            visit(block.children, inside)
    for region in document.regions:
        visit(region.blocks)
    return found


def _display_entry(span):
    return isinstance(span, FactFieldSpan) and span.field_key == 'display' and getattr(span, 'complete', True)


def _split_technology_line(content):
    """A tags line is a fixed prefix, then one entry per technology, then a trailing tail.
    The nodes between entries are the separator that travels with the following entry."""
    prefix, entries, bucket, spans, record = [], [], [], [], None
    def flush():
        nonlocal bucket, spans, record
        if record is not None:
            entries.append((record, bucket, spans))
            bucket, spans, record = [], [], None
    for span in content:
        if _display_entry(span) and (record is None or record == span.record_id):
            if record is None:
                record = span.record_id
            spans.append(span)
            continue
        if _display_entry(span):
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
    for content in _technology_lists(candidate.document):
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


def prepare_panel_edit(response, request, *, occupied=None):
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
        from .template_panel_focus import FOCUS_OPERATIONS, prepare_focus
        from .template_panel_records import add_technology, edit_record, remove_records
        records = {value.id: value.kind for value in workspace.project.facts.records}
        kind = records.get(command.record_id) if command.record_id is not None else command.record_kind
        if command.operation in FOCUS_OPERATIONS:
            if operation.placement_context is not None:
                raise ValueError('FOCUS_SCOPE_INVALID')
            prepared = prepare_focus(workspace, command, allocator)
            if prepared is None:
                return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
            candidate, steps = prepared
        elif command.operation == 'add' and command.record_kind == 'technology':
            candidate, steps = add_technology(workspace.project, operation, allocator)
        elif command.operation in {'edit', 'remove', 'clear_technologies'} and kind not in {None, 'employment'}:
            if operation.placement_context is not None:
                raise ValueError('PANEL_ACTION_UNSUPPORTED')
            prepared = (edit_record(workspace.project, command, allocator) if command.operation == 'edit'
                else remove_records(workspace.project, command, request.capture.action_id))
            if prepared is None:
                return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
            candidate, steps = prepared
        elif command.operation == 'move_technology':
            if operation.placement_context is not None:
                raise ValueError('TECHNOLOGY_MOVE_INVALID')
            candidate = _reorder_technology_displays(workspace.project, command)
            if candidate is None:
                return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
            steps = []
        elif command.job_id is not None or command.record_kind not in {None, 'employment'}:
            # Adding a candidate, an education or language item or a claim has no adapter; the panel does not offer it.
            raise ValueError('PANEL_ACTION_UNSUPPORTED')
        elif command.operation in {'add', 'add_period'}:
            from .template_panel_creation import create_employment, create_period
            create = create_employment if command.operation == 'add' else create_period
            candidate, steps = create(workspace, operation, allocator)
            tree, replacements = changed_block_steps(workspace.project.document, candidate.document)
            steps += tree + [value.model_dump(by_alias=True) for value in anchor_steps(workspace.project, replacements)]
            return finish_preparation(response, request, allocator, steps, candidate, kind='panel')
        else:
            original = next((record for record in workspace.project.facts.records if record.id == command.record_id), None)
            if original is None or original.kind != 'employment':
                raise ValueError('employment panel target missing')
            if command.operation == 'remove':
                if command.values or command.period_id is not None or operation.placement_context is not None:
                    raise ValueError('employment deletion has unexpected fields')
                candidate, steps = _delete_entity(workspace, original.id, original.revision, request.capture.action_id)
            elif command.operation in {'edit', 'remove_period'}:
                if operation.placement_context is not None:
                    raise ValueError('existing panel edit has no placement')
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
                    return prepared_response(response, request, allocator, None, response.model_copy(deep=True))
                for key in selected:
                    set_text(updated, key, command.values[key])
                candidate = workspace.project.model_copy(deep=True)
                _patch_displays(workspace.project, candidate, original, updated, selected, removed_periods, allocator)
                steps = [{'kind': 'put_record', 'beforeRevision': original.revision, 'record': updated.model_dump(by_alias=True)}]
                for cell, scope_id in workspace.project.facts.builtin_manual_scopes.items():
                    if cell in {field_key(original.id, key) for key in selected} or any(
                            cell == field_key(original.id, 'period:' + identifier + ':' + key)
                            for identifier in removed_periods for key in ('start', 'end', 'present')):
                        steps.append({'kind': 'set_builtin_manual_scope', 'cellId': cell, 'beforeScopeId': scope_id, 'afterScopeId': None})
            else:
                raise ValueError('employment panel creation requires its captured creation adapter')
    else:
        raise ValueError('panel preparation needs a panel or entity operation')
    tree, replacements = changed_block_steps(workspace.project.document, candidate.document)
    steps += tree + [value.model_dump(by_alias=True) for value in anchor_steps(workspace.project, replacements)]
    return finish_preparation(response, request, allocator, steps, candidate, kind='panel')
