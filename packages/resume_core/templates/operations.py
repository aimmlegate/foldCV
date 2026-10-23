"""Registered deterministic template operations: typed functions over admitted facts, never a model or inferred identity."""

import calendar
from dataclasses import dataclass, field
from datetime import date

from ..technologies import technology_identity


@dataclass(frozen=True)
class OperationIssue:
    code: str
    message: str
    target_ids: tuple = ()


@dataclass(frozen=True)
class OperationResult:
    value: object
    item_handles: tuple
    source_spans: tuple = ()
    issues: tuple = ()


@dataclass(frozen=True)
class OperationContext:
    """What an operation reads: the capture, admitted facts, this import's identities and its finished results."""
    capture: object
    facts: object
    handles: dict = field(default_factory=dict)
    producers: dict = field(default_factory=dict)
    cells: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    blocks: dict = field(default_factory=dict)


def latest_day(value):
    """The latest day a partial date can mean; None when it is unknown."""
    if value is None:
        return None
    if value.month is None:
        return date(value.year, 12, 31)
    if value.day is None:
        return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])
    return date(value.year, value.month, value.day)


def earliest_day(value):
    return date(value.year, value.month or 1, value.day or 1)


def years_before(day, years):
    # A leap day without a match in the earlier year moves to 28 February.
    return day.replace(year=day.year - years, day=min(day.day, calendar.monthrange(day.year - years, day.month)[1]))


def partition_employment(declaration, context):
    """Compact an employment record only when every period ended, wholly, before the captured cutoff."""
    capture = context.capture
    cutoff = years_before(earliest_day(capture.formatting_as_of), declaration.parameters.years)
    compact, detailed = [], []
    for record in context.facts.records:
        if record.kind != 'employment' or not getattr(record, 'active', True):
            continue
        old = capture.allow_text_rewrite and bool(record.periods) and all(period.present.value is not True
            and latest_day(period.end.value) is not None and latest_day(period.end.value) < cutoff for period in record.periods)
        (compact if old else detailed).append(record.id)
    value = {'cutoff': cutoff.isoformat(), 'detailed': detailed, 'compact': compact,
        'detailedBlock': declaration.parameters.detailed, 'compactBlock': declaration.parameters.compact}
    return OperationResult(value, tuple(context.handles[record] for record in [*detailed, *compact] if record in context.handles))


def format_period(declaration, _context):
    """Period display formatting; the materializer applies it to period nodes."""
    return OperationResult({'separator': declaration.parameters.separator,
        'ongoingLabel': dict(declaration.parameters.ongoing_label)}, ())


ROLE_FAMILY_UNCERTAIN = 'Тип роли кандидата не определён однозначно, поэтому выбран вариант шаблона по умолчанию.'
SKILL_GROUP_UNCERTAIN = 'Для части технологий из проектов группа не определена, поэтому они показаны в группе по умолчанию.'


def select_role_branch(declaration, context):
    """The matched branch for one admitted declared role family; otherwise the fallback branch."""
    parameters, source = declaration.parameters, declaration.parameters.classification
    found = [] if source is None else [(record, cell) for record in context.facts.extensions
        if record.active and record.semantic_type == source.semantic_type for cell in record.cells
        if cell.field_key == source.field and cell.state == 'admitted' and cell.typed_value is not None]
    families = {cell.typed_value for _record, cell in found}
    family = next(iter(families)) if len(families) == 1 else None
    branch = parameters.matched if family in parameters.role_families else parameters.otherwise
    # A missing or conflicting classification is an interpretation issue, never a guess from wording.
    issues = () if family is not None else (
        OperationIssue('IMPORT_ROLE_FAMILY_UNCERTAIN', ROLE_FAMILY_UNCERTAIN, tuple(cell.id for _record, cell in found)),)
    return OperationResult({'branch': branch, 'family': family},
        tuple(dict.fromkeys(context.handles.get(record.id, record.item_handle) for record, _cell in found)),
        tuple(span for _record, cell in found for span in cell.evidence), issues)


def active(block, results):
    return block.when is None or (results.get(block.when.operation) or {}).get('branch') == block.when.equals


def assign_skills(declaration, context):
    """Each canonical technology once among the active groups; input technologies no group admitted join the fallback group."""
    parameters = declaration.parameters
    groups = [group for group in parameters.groups if active(context.blocks[group], context.results)]
    technologies = [(record, technology_identity(record)) for record in context.facts.records
        if record.kind == 'technology' and getattr(record, 'active', True)]
    kept, hidden, seen = {group: [] for group in groups}, {group: [] for group in groups}, set()
    for group in groups:
        for record, identity in technologies:
            if context.producers.get(record.id) == group and identity:
                (hidden if identity in seen else kept)[group].append(record.id)
                seen.add(identity)
    added = []
    sources = {ref.id for ref in declaration.inputs if ref.kind == 'block'} - set(parameters.groups)
    for record, identity in technologies if groups else ():
        if context.producers.get(record.id) in sources and identity and identity not in seen:
            added.append(record.id)
            seen.add(identity)
    issues = (OperationIssue('IMPORT_SKILL_GROUP_UNCERTAIN', SKILL_GROUP_UNCERTAIN,
        tuple(cell for record in added for cell in context.cells.get(record, ()))),) if added else ()
    value = {'active': groups, 'kept': kept, 'hidden': hidden, 'added': added, 'uncertainGroup': parameters.uncertain_group}
    shown = [*(record for group in groups for record in kept[group]), *added]
    return OperationResult(value, tuple(context.handles[record] for record in shown if record in context.handles), (), issues)


REGISTRY = {('partition_employment', 1): partition_employment, ('format_period', 1): format_period,
    ('select_role_branch', 1): select_role_branch, ('assign_skills', 1): assign_skills}


def display_pointer(definition, block):
    """The bound technology display inside a block view, with exactly one item wildcard; None when absent."""
    from .projection import pointer_tokens
    types = {value.id: value for value in definition.fact_types}
    for binding in block.bindings:
        declaration = types[binding.semantic_type]
        mapped = declaration.builtin_fields.get(binding.field)
        tokens = pointer_tokens(binding.pointer)
        if declaration.builtin_kind == 'technology' and mapped is not None and mapped.field == 'display' and tokens.count('*') == 1:
            return tokens
    return None


def runnable(declaration, definition):
    """Whether an operation's declared inputs let it run as specified; checked when it runs, so retained packages still open."""
    if (declaration.kind, declaration.version) not in REGISTRY:
        return False
    if declaration.kind != 'assign_skills':
        return True
    blocks = {value.id: value for value in definition.blocks}
    conditions = {(blocks[group].when.operation, blocks[group].when.equals) if blocks[group].when else None
        for group in declaration.parameters.groups}
    inputs = {ref.id for ref in declaration.inputs if ref.kind == 'block'}
    # Groups run before the assignment, switch on together, and leave one active assignment per branch.
    if not set(declaration.parameters.groups) <= inputs or len(conditions) != 1:
        return False
    condition = next(iter(conditions))
    for other in definition.operations:
        if other.kind == 'assign_skills' and other.id != declaration.id:
            when = blocks[other.parameters.groups[0]].when
            if condition is None or when is None or when.operation != condition[0] or when.equals == condition[1]:
                return False
    return display_pointer(definition, blocks[declaration.parameters.uncertain_group]) is not None


def operation_value(operations, operation_id):
    """The stored result of one operation task in the latest operation that ran it."""
    for operation in reversed(operations):
        tasks = {task.id: task for task in operation.tasks}
        for result in operation.task_results:
            if tasks[result.task_id].block_id == operation_id and result.disposition in {'derived', 'empty'}:
                return result.value
    return None


def operation_context(operation, data):
    from ..template_capture import item_identities
    tasks = {task.id: task for task in operation.tasks}
    identities = item_identities(operation)
    finished = {tasks[result.task_id].block_id: result.value for result in operation.task_results
        if result.disposition in {'derived', 'empty'}}
    return OperationContext(capture=operation.capture, facts=data.facts,
        handles={value.record_id: value.item_handle for value in identities},
        producers={value.record_id: tasks[value.task_id].block_id for value in operation.allocations if value.task_id in tasks},
        cells={value.record_id: tuple(value.cell_ids.values()) for value in identities},
        results=finished, blocks={value.id: value for value in data.template_package.definition.blocks})


def derive_task(operation, task, data):
    """The deterministic result of an operation task or a derived view task, from admitted facts only."""
    from ..template_import import TemplateImportFailure
    context = operation_context(operation, data)
    definition = data.template_package.definition
    declaration = next((value for value in definition.operations if value.id == task.block_id), None)
    if declaration is not None:
        if not runnable(declaration, definition):
            raise TemplateImportFailure('IMPORT_OPERATION_UNSUPPORTED')
        return REGISTRY[(declaration.kind, declaration.version)](declaration, context)
    block = context.blocks[task.block_id]
    source = next((value for value in definition.operations if value.id == block.operation), None)
    stored = context.results.get(block.operation) if source is not None else None
    if source is None or source.kind != 'partition_employment' or stored is None or stored['compactBlock'] != block.id:
        raise TemplateImportFailure('IMPORT_OPERATION_UNSUPPORTED')
    # The compact view lists the partition's old records; their facts stay complete and retained.
    return OperationResult({'records': list(stored['compact'])},
        tuple(context.handles[record] for record in stored['compact'] if record in context.handles))
