"""Employment panel changes keep authored wording outside selected canonical fields."""

from .models.rich_document import FactFieldSpan
from .models.template_authoring import BuiltinPanel, DeleteEntity
from .models.template_document import BoundLink
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
    previous = {period.id: period for period in original.periods}
    for period in updated.periods:
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
                or command.capture != request.capture or command.job_id is not None or command.record_kind not in {None, 'employment'}):
            raise ValueError('stale or incompatible employment panel command')
        if command.operation in {'add', 'add_period'}:
            from .template_panel_creation import create_employment, create_period
            create = create_employment if command.operation == 'add' else create_period
            candidate, steps = create(workspace, operation, allocator)
            tree, replacements = changed_block_steps(workspace.project.document, candidate.document)
            steps += tree + [value.model_dump(by_alias=True) for value in anchor_steps(workspace.project, replacements)]
            return finish_preparation(response, request, allocator, steps, candidate, kind='panel')
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
