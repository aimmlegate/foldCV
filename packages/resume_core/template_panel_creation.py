"""Create only a new employment item from unambiguous captured bindings and nodes."""

from .models.rich_document import FactFieldSpan, SectionBlock
from .models.rich_facts import EmploymentRecord, WorkingPeriod
from .models.template_document import BoundLink, FieldOccurrence, ManualScopeSpan, PresentedText, TemplateParagraphBlock, TemplateSectionBlock
from .rich_fields import builtin_cell_values, inline_groups, set_text, working_field, field_key
from .rich_mutations import locate, parent_items, subtree
from .template_builtin_admission import unknown
from .template_identity import _bound_root
from .template_panel_values import period_endpoint
from .templates.compiler import canonical
from .templates.materialize_nodes import fallback_style, locale_text, reference
from .templates.projection import pointer_tokens


def view_options(project):
    semantic = {value.id: value for value in project.template_package.definition.fact_types
        if value.builtin_kind == 'employment' and value.builtin_fields}
    result = []
    for view in project.template_package.definition.blocks:
        if view.view.mode != 'items':
            continue
        types = {value.semantic_type for value in view.bindings
            if value.semantic_type in semantic
                and _bound_root(value.pointer, value.semantic_type, value.field, view.bindings) == ['*']}
        result.extend((view, semantic[kind]) for kind in sorted(types))
    return result


def section_records(project, block):
    records = {value.id for value in project.facts.records if value.kind == 'employment'}
    found = {block.props.record_id} & records if isinstance(block, SectionBlock) else set()
    cells = builtin_cell_values(project.facts.records)
    scope_records = {}
    for cell, scope in project.facts.builtin_manual_scopes.items():
        if cell in cells and cells[cell][0].id in records:
            scope_records.setdefault(scope, set()).add(cells[cell][0].id)
    def visit(value):
        for _container, group in inline_groups(value):
            found.update(part.record_id for part in group if isinstance(part, FactFieldSpan) and part.record_id in records)
            for part in group:
                if isinstance(part, BoundLink):
                    found.update(value.record_id for value in (part.label_binding, part.url_binding)
                        if value is not None and value.record_id in records)
                elif isinstance(part, ManualScopeSpan):
                    found.update(scope_records.get(part.scope_id, set()))
        found.update(part.record_id for part in value.provenance
            if part.kind == 'working_owner' and part.record_id in records)
        for child in value.children:
            if not isinstance(child, SectionBlock):
                visit(child)
    visit(block)
    return found


def _mapping(view, semantic):
    result = {}
    for binding in view.bindings:
        if (binding.semantic_type == semantic.id
                and _bound_root(binding.pointer, binding.semantic_type, binding.field, view.bindings) == ['*']):
            target = semantic.builtin_fields.get(binding.field)
            if target is not None:
                path = tuple(pointer_tokens(binding.pointer))
                if not path or path[0] != '*':
                    raise ValueError('employment view has incompatible item binding')
                if path[1:] in result and result[path[1:]] != target:
                    raise ValueError('employment view has ambiguous canonical binding')
                result[path[1:]] = target
    return result


def node_fields(view, semantic, node, period_id):
    mapping = _mapping(view, semantic)
    if node.type == 'period':
        base = tuple(pointer_tokens(node.field))
        fields = [mapping.get((*base, key)) for key in ('start', 'end', 'ongoing')]
        if any(value is None for value in fields):
            return []
        if ([value.field for value in fields] != ['start', 'end', 'present']
                or len({value.period for value in fields}) != 1 or fields[0].period is None):
            raise ValueError('period node has incompatible captured endpoint mapping')
        return ['period:' + period_id + ':' + value.field for value in fields]
    paths = [node.field] if node.type == 'text' else node.fields if node.type == 'join_fields' else []
    fields = [mapping.get(tuple(pointer_tokens(path))) for path in paths]
    if not paths:
        referenced = [value for value in [node.field, *node.fields, node.name_field, node.url_field, node.experience_field]
            if value is not None]
        if any(tuple(pointer_tokens(path)) == target[:len(pointer_tokens(path))]
                for path in referenced for target in mapping):
            raise ValueError('employment creation node is unsupported')
        return []
    if any(value is not None and (value.period is not None or value.field not in {'employer', 'role'}) for value in fields):
        raise ValueError('employment scalar node has unsupported canonical fields')
    return [value.field for value in fields if value is not None]


def _context(project, operation):
    value = operation.placement_context
    if value is None:
        return None
    found = locate(project.document, value.context_block_id)
    if found is None:
        raise ValueError('panel placement context missing')
    return found[0][found[1]]


def _unique(values, message):
    if len(values) != 1:
        raise ValueError(message)
    return values[0]


def _insert(document, blocks, parent_id, after_id):
    items, _parent = parent_items(document, parent_id)
    positions = {block.id: index for index, block in enumerate(items)}
    if after_id is not None and after_id not in positions:
        raise ValueError('panel placement sibling missing')
    index = positions[after_id] + 1 if after_id else 0
    items[index:index] = blocks


def _period(allocator, record_id):
    return WorkingPeriod(id=allocator.allocate('period', ['panel-period', record_id]), revision=1,
        start=unknown(), end=unknown(), present={**unknown(), 'value': False, 'status': 'known'}, evidence=[])


def _report_cells(before, record, allocator):
    current = builtin_cell_values(before.facts.records)
    for identifier, (owner, key, _value) in builtin_cell_values([record]).items():
        if identifier not in current:
            if working_field(record, key) is None or identifier != field_key(owner.id, key):
                raise ValueError('new canonical cell is not a record field')
            allocator.derived('builtin-cell', ['builtin-cell', owner.id, key], identifier)


def _values(command, period_id, *, employment):
    allowed = {'employer', 'role'} if employment else set()
    result = {}
    for key, value in command.values.items():
        translated = 'period:' + period_id + ':' + key if key in {'start', 'end', 'present'} else key
        if translated not in allowed | {'period:' + period_id + ':' + name for name in ('start', 'end', 'present')}:
            raise ValueError('new employment/period value is unknown')
        if translated in result and result[translated] != value:
            raise ValueError('new period aliases conflict')
        result[translated] = value
    return result


def _blocks(package, view, semantic, record, period, indexes, instance, allocator, context=None):
    blocks = []
    locale = package.definition.template.default_locale
    for index in indexes:
        node = view.view.nodes[index]
        keys = node_fields(view, semantic, node, period.id)
        if not keys:
            continue
        if node.type == 'period':
            keys = [keys[0], keys[2] if period_endpoint(period) == 'present' else keys[1]]
        ref = reference(package, view.id, node.style, instance, node_index=index)
        if context is not None:
            ref.overrides = context.presentation.overrides.model_copy(deep=True)
        content = []
        prefix = locale_text(node.prefix, locale)
        if prefix:
            content.append(PresentedText(type='text', text=prefix, styles={}, presentation=ref))
        for position, key in enumerate(keys):
            if position:
                content.append(PresentedText(type='text', text='–' if node.type == 'period' else node.separator,
                    styles={}, presentation=ref))
            root = allocator.allocate('occurrence', ['panel-occurrence', record.id, period.id, index, position, key])
            content.append(FieldOccurrence(type='fact_field',
                bindingId=allocator.allocate('fragment', ['panel-fragment', root]), bindingRootId=root,
                recordId=record.id, fieldKey=key, cellId=field_key(record.id, key), occurrenceId=root,
                complete=True, presentation=ref, text=working_field(record, key).raw_text,
                styles={}, syncedFactRevision=working_field(record, key).revision))
        label = locale_text(node.label, locale)
        if label:
            blocks.append(TemplateParagraphBlock(type='paragraph',
                id=allocator.allocate('block', ['panel-node-label', record.id, period.id, index]), revision=1,
                props={}, children=[], provenance=[], presentation=ref,
                content=[PresentedText(type='text', text=label, styles={}, presentation=ref)]))
        blocks.append(TemplateParagraphBlock(type='paragraph',
            id=allocator.allocate('block', ['panel-node', record.id, period.id, index]), revision=1,
            props={'alignment': ref.overrides.alignment or 'left'}, children=[], provenance=[], presentation=ref, content=content))
    return blocks


def create_employment(workspace, operation, allocator):
    before = workspace.project
    command = operation.command
    context = _context(before, operation)
    options = [value for value in view_options(before) if context is None or value[0].id == context.presentation.view_key]
    view, semantic = _unique(options, 'employment creation needs one captured view')
    if command.record_kind != 'employment' or command.record_id is not None or command.period_id is not None:
        raise ValueError('new employment has incompatible identity')
    if len({value.period for value in semantic.builtin_fields.values() if value.period is not None}) > 1:
        raise ValueError('new employment has ambiguous configured period slots')
    record_id = allocator.allocate('employment', ['panel-employment'])
    period = _period(allocator, record_id)
    record = EmploymentRecord(id=record_id, kind='employment', revision=1, origin='user', userCorrected=True,
        evidence=[], employer=unknown(), role=unknown(), periods=[period])
    for key, value in _values(command, period.id, employment=True).items():
        set_text(record, key, value)
    _report_cells(before, record, allocator)
    candidate = before.model_copy(deep=True)
    regions = {region.id: region for region in candidate.document.regions}
    if operation.placement_context is None:
        region = _unique([value for value in regions.values() if value.role == view.placement.region],
            'employment region missing')
        parent, after = region.id, region.blocks[-1].id if region.blocks else None
    else:
        parent, after = operation.placement_context.placement.parent_id, operation.placement_context.placement.after_id
        cursor, seen = parent, set()
        while cursor not in regions:
            if cursor in seen:
                raise ValueError('cyclic employment placement')
            seen.add(cursor)
            found = locate(candidate.document, cursor)
            if (found is None or getattr(found[0][found[1]].props, 'record_id', None) is not None
                    or section_records(before, found[0][found[1]])
                    or found[0][found[1]].presentation.view_key != view.id):
                raise ValueError('new employment cannot become another item child')
            cursor = found[2].id
        if regions[cursor].role != view.placement.region:
            raise ValueError('new employment placement crosses captured region')
    instance = allocator.allocate('template-instance', ['panel-employment-instance', record_id])
    children = _blocks(before.template_package, view, semantic, record, period,
        range(len(view.view.nodes)), instance, allocator)
    if not children:
        raise ValueError('employment view has no supported canonical item fields')
    section = TemplateSectionBlock(type='section', id=allocator.allocate('block', ['panel-employment-section', record_id]),
        revision=1, props={'recordId': record_id}, content=[], children=children, provenance=[],
        presentation=reference(before.template_package, view.id, fallback_style(view), instance))
    _insert(candidate.document, [section], parent, after)
    return candidate, [{'kind': 'put_record', 'beforeRevision': None, 'record': record.model_dump(by_alias=True)}]


def create_period(workspace, operation, allocator):
    before = workspace.project
    command = operation.command
    original = next((value for value in before.facts.records if value.id == command.record_id and value.kind == 'employment'), None)
    if original is None or command.period_id is not None:
        raise ValueError('new period target missing')
    context = _context(before, operation)
    options = {}
    for view, semantic in view_options(before):
        options.setdefault(view.id, []).append((view, semantic))
    sections = [block for block in before.document.blocks() if isinstance(block, SectionBlock)
        and block.props.record_id in {None, original.id} and section_records(before, block) == {original.id}
        and all(value.record_id == original.id for value in block.provenance if value.kind == 'working_owner')
        and block.presentation.view_key in options]
    if operation.placement_context is not None:
        sections = [block for block in sections if block.id == operation.placement_context.placement.parent_id
            and context.id in {value.id for value in subtree(block)}]
    section = _unique(sections, 'period creation needs one authored employment section')
    view, semantic = _unique(options[section.presentation.view_key], 'period creation view has ambiguous canonical types')
    if context is not None and context.presentation.view_key != view.id:
        raise ValueError('period context belongs to another captured view')
    updated = original.model_copy(deep=True)
    period = _period(allocator, original.id)
    updated.periods.append(period)
    for key, value in _values(command, period.id, employment=False).items():
        set_text(updated, key, value)
    _report_cells(before, updated, allocator)
    indexes = [index for index, node in enumerate(view.view.nodes)
        if node.type == 'period' and node_fields(view, semantic, node, period.id)]
    if context is not None and context.presentation.node_index in indexes:
        indexes = [context.presentation.node_index]
    index = _unique(indexes, 'period creation needs one compatible captured node')
    if context is None:
        references = []
        for block in subtree(section):
            value = block.presentation
            if value.view_key == view.id and value.node_index == index:
                references.append((block, value))
        by_style = {canonical(value.model_dump(exclude={'template_instance_id', 'item_handle'})): (block, value)
            for block, value in references}
        if len(by_style) > 1:
            raise ValueError('period paragraph overrides need explicit context')
        if references:
            block, ref = next(iter(by_style.values()))
            context = block.model_copy(update={'presentation': ref}, deep=True)
    candidate = before.model_copy(deep=True)
    instance = allocator.allocate('template-instance', ['panel-period-instance', original.id, period.id])
    blocks = _blocks(before.template_package, view, semantic, updated, period, [index], instance, allocator, context)
    after = (operation.placement_context.placement.after_id if operation.placement_context is not None
        else section.children[-1].id if section.children else None)
    _insert(candidate.document, blocks, section.id, after)
    return candidate, [{'kind': 'put_record', 'beforeRevision': original.revision, 'record': updated.model_dump(by_alias=True)}]
