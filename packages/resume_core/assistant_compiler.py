"""Assistant change ops to authored operations (D109, plan 2.8 table).

Every op becomes one or more `AuthoredOperation` values, prepared one by one with `prepare_edit` against the
workspace the previous step produced. The editor and the assistant therefore share one preparation path, and the
caller commits the final workspace as one action (one undo step).
"""

from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError

from .models.rich_document import InlineStyles
from .models.template_authoring import TemplateEditPreparationV1
from .models.template_document import BoundLink, ManualScopeSpan
from .rich_dependencies import placements
from .rich_fields import inline_groups, working_field
from .rich_mutations import RichMutationFailure, inline_text, utf16_slice
from .rich_panel import FIELDS
from .template_panel_records import REMOVABLE, technology_targets
from .template_preparation import _fields, _leaves, _length, prepare_edit

KINDS = {'paragraph': {'type': 'paragraph'}, 'bullet': {'type': 'bullet_list'},
    'numbered': {'type': 'numbered_list', 'start': None}}


class CompileFailure(Exception):
    """A refused op; `detail` names the blocks, fields or matches involved, never wording of the resume."""

    def __init__(self, code, *detail):
        self.code, self.detail = code, [str(value)[:200] for value in detail][:20]
        super().__init__(code)


def _hash(value):
    data = value.model_dump(mode='json', by_alias=True)
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def find_block(workspace, block_id):
    return next((block for block in workspace.project.document.blocks() if block.id == block_id), None)


def find_record(workspace, record_id):
    facts = workspace.project.facts
    record = next((value for value in facts.records if value.id == record_id), None)
    if record is not None:
        return record, False
    extension = next((value for value in facts.extensions if value.id == record_id and value.active), None)
    return (extension, True) if extension is not None else (None, False)


def region_ids(workspace):
    return {region.id for region in workspace.project.document.regions}


def container(block, cell_id, field):
    content = dict(inline_groups(block)).get(cell_id or field)
    if content is None or field == 'caption' and cell_id is not None:
        raise CompileFailure('ASSISTANT_TARGET_MISSING', block.id, cell_id or field)
    return content


def container_text(content):
    return ''.join(inline_text(span) for span in content)


def _units(text):
    return len(text.encode('utf-16-le')) // 2


def targets(op):
    """Block and record ids an op depends on; their hashes in the read snapshot make the staleness proof."""
    kind = op.op
    if kind in {'set_block_text', 'replace_text', 'format_block'}:
        return [op.block_id]
    if kind == 'insert_blocks':
        return [op.after_block_id or op.parent_id]
    if kind == 'delete_blocks':
        return list(op.block_ids)
    if kind == 'move_block':
        return [op.block_id, op.after_block_id or op.parent_id]
    if kind in {'update_fact', 'delete_fact'}:
        return [op.record_id]
    if kind == 'create_fact':
        return [op.job_id] if op.job_id else []
    return []


def touched(workspace, ops):
    """sha256 of each referenced block or record in `workspace`; region ids have no hash (they are not content)."""
    result, regions = {}, region_ids(workspace)
    for op in ops:
        for identifier in targets(op):
            if identifier in regions or identifier in result:
                continue
            block = find_block(workspace, identifier)
            if block is not None:
                result[identifier] = _hash(block)
                continue
            record, _extension = find_record(workspace, identifier)
            if record is None:
                raise CompileFailure('ASSISTANT_TARGET_MISSING', identifier)
            result[identifier] = _hash(record)
    return result


def changed_targets(proposal_touched, workspace):
    """Targets whose current hash differs from the proposal's read; a missing target counts as changed."""
    changed = []
    for identifier, value in proposal_touched.items():
        block = find_block(workspace, identifier)
        current = block if block is not None else find_record(workspace, identifier)[0]
        if current is None or _hash(current) != value:
            changed.append(identifier)
    return changed


def target_text(workspace, identifier):
    block = find_block(workspace, identifier)
    if block is not None:
        return ' / '.join(container_text(content) for _key, content in inline_groups(block))
    record, extension = find_record(workspace, identifier)
    if record is None:
        return ''
    if extension:
        return '; '.join(f'{cell.field_key}: {cell.raw_input}' for cell in record.cells)
    fields = [(key, working_field(record, key)) for key in FIELDS.get(record.kind, ())]
    return '; '.join(f'{key}: {value.raw_text}' for key, value in fields if value is not None and value.raw_text)


class Chain:
    """The workspace after each prepared step, with the ids taken so far."""

    def __init__(self, workspace, *, action_id, occupied, response_for):
        self.current, self.action_id = workspace, action_id
        self.occupied, self.response_for = set(occupied), response_for
        self.created, self.count = {}, 0

    def block(self, block_id):
        block = find_block(self.current, block_id)
        if block is None:
            raise CompileFailure('ASSISTANT_TARGET_MISSING', block_id)
        return block

    def apply(self, operation):
        self.count += 1
        op_id = f'assistant-{self.count}'
        capture = {'sessionId': 'assistant', 'actionId': self.action_id, 'actionToken': 1, 'dependencies': []}
        if operation['kind'] == 'builtin_panel':
            operation['command'] = {**operation['command'], 'factsRevision': self.current.project.facts.revision,
                'documentRevision': self.current.document_revision, 'capture': capture}
        response = self.response_for(self.current)
        try:
            preparation = TemplateEditPreparationV1.model_validate({'schemaVersion': 1,
                'clientMutationId': f'{self.action_id}-{self.count}',
                'snapshot': response.snapshot.model_dump(mode='json', by_alias=True), 'capture': capture,
                'operations': [{**operation, 'opId': op_id}]})
            prepared = prepare_edit(response, preparation, occupied=self.occupied)
        except ValidationError as error:
            raise CompileFailure('ASSISTANT_OP_INVALID', *(issue['type'] for issue in error.errors()[:3])) from None
        except (ValueError, RichMutationFailure) as error:
            raise CompileFailure('ASSISTANT_OP_REFUSED', getattr(error, 'code', None) or str(error)) from None
        if prepared.mutation is None:
            return None
        before = {block.id for block in self.current.project.document.blocks()}
        self.current = prepared.preview.workspace
        for slots in prepared.created_ids.values():
            self.occupied.update(slots.values())
        self.created.update(prepared.created_ids)
        return [block.id for block in self.current.project.document.blocks() if block.id not in before]


def _protected(content):
    """UTF-16 ranges the text compiler must keep verbatim: field occurrences, bound links and manual scopes."""
    ranges, names, cursor = [], [], 0
    for span in content:
        length = _length(span)
        if isinstance(span, BoundLink):
            ranges.append((cursor, cursor + length))
            names.append('link')
        cursor += length
    for span, start, end in _fields(content):
        if not any(left <= start and end <= right for left, right in ranges):
            ranges.append((start, end))
            names.append(getattr(span, 'field_key', None) or getattr(span, 'cell_id', None) or 'field')
    for span, start, end in _leaves(content):
        if isinstance(span, ManualScopeSpan) and not any(left <= start and end <= right for left, right in ranges):
            ranges.append((start, end))
            names.append('manual')
    return sorted(zip(ranges, names))


def _styles_at(content, start, end):
    for span, left, right in _leaves(content):
        if left <= start < right or start == end and left <= start <= right:
            return span.styles.model_dump(mode='json', by_alias=True)
    return InlineStyles().model_dump(mode='json', by_alias=True)


def _replace(block, op, start, end, text, styles):
    selected = {'blockId': block.id, 'beforeRevision': block.revision, 'cellId': op.cell_id, 'field': op.field,
        'start': start, 'end': end}
    if start == end:
        selected['insertionTarget'] = {'kind': 'literal'}
    return {'kind': 'replace_text', 'range': selected, 'text': text, 'styles': styles}


def set_block_text(chain, op):
    block = chain.block(op.block_id)
    content = container(block, op.cell_id, op.field)
    old = container_text(content)
    protected = _protected(content)
    gaps, cursor, position, lost = [], 0, 0, []
    for (start, end), name in protected:
        kept = utf16_slice(old, start, end)
        found = op.text.find(kept, position)
        if found < 0:
            lost.append(name)
            continue
        gaps.append((cursor, start, op.text[position:found]))
        cursor, position = end, found + len(kept)
    if lost:
        raise CompileFailure('ASSISTANT_FIELDS_LOST', *lost)
    gaps.append((cursor, _units(old), op.text[position:]))
    # Right to left: a later replacement never moves an earlier range.
    for start, end, text in reversed(gaps):
        if utf16_slice(old, start, end) == text and op.marks is None:
            continue
        current = chain.block(op.block_id)
        content = container(current, op.cell_id, op.field)
        styles = op.marks.model_dump(mode='json', by_alias=True) if op.marks else _styles_at(content, start, end)
        chain.apply(_replace(current, op, start, end, text, styles))


def replace_text(chain, op):
    block = chain.block(op.block_id)
    content = container(block, op.cell_id, op.field)
    text = container_text(content)
    count = text.count(op.find)
    if count != 1:
        raise CompileFailure('ASSISTANT_MATCH_NOT_UNIQUE', count)
    found = text.index(op.find)
    start, end = _units(text[:found]), _units(text[:found + len(op.find)])
    leaf = next(((span, left, right) for span, left, right in _leaves(content) if left <= start and end <= right), None)
    if leaf is None:
        raise CompileFailure('ASSISTANT_MATCH_CROSSES_SPAN', op.block_id)
    chain.apply(_replace(block, op, start, end, op.replace, leaf[0].styles.model_dump(mode='json', by_alias=True)))


def _placement(chain, after_block_id, parent_id):
    if after_block_id is not None:
        positions = placements(chain.current.project.document)
        if after_block_id not in positions:
            raise CompileFailure('ASSISTANT_TARGET_MISSING', after_block_id)
        return {'parentId': positions[after_block_id][0], 'afterId': after_block_id}, after_block_id
    regions = {region.id: region for region in chain.current.project.document.regions}
    children = regions[parent_id].blocks if parent_id in regions else getattr(find_block(chain.current, parent_id), 'children', None)
    if not children:
        raise CompileFailure('ASSISTANT_TARGET_MISSING', parent_id)
    return {'parentId': parent_id, 'afterId': None}, children[0].id


def _kind_patch(kind, level):
    if kind == 'heading':
        return {'type': 'heading', 'level': level}
    return KINDS[kind]


def insert_blocks(chain, op):
    after, parent = op.after_block_id, op.parent_id
    for value in op.blocks:
        placement, context = _placement(chain, after, parent)
        anchor = chain.block(context)
        created = chain.apply({'kind': 'insert_paragraph', 'contextBlockId': anchor.id, 'contextRevision': anchor.revision,
            'placement': placement, 'text': value.text})
        if not created:
            raise CompileFailure('ASSISTANT_OP_REFUSED', 'insert_paragraph')
        inserted = chain.block(created[0])
        if value.kind != 'paragraph':
            chain.apply({'kind': 'format_blocks', 'targets': [{'blockId': inserted.id, 'beforeRevision': inserted.revision}],
                'patch': {'blockKind': _kind_patch(value.kind, value.level)}})
        after, parent = inserted.id, None


def delete_blocks(chain, op):
    chain.apply({'kind': 'remove_occurrences', 'blocks': [{'blockId': identifier,
        'beforeRevision': chain.block(identifier).revision} for identifier in op.block_ids]})


def move_block(chain, op):
    block = chain.block(op.block_id)
    placement, _context = _placement(chain, op.after_block_id, op.parent_id)
    chain.apply({'kind': 'move_block', 'blockId': block.id, 'beforeRevision': block.revision, 'placement': placement})


def format_block(chain, op):
    block = chain.block(op.block_id)
    patch = {}
    if op.kind is not None:
        patch['blockKind'] = _kind_patch(op.kind, op.level or 2)
    for key, value in (('alignment', op.alignment), ('textColor', op.text_color), ('backgroundColor', op.background_color)):
        if value is not None:
            patch[key] = value
    if not patch:
        raise CompileFailure('ASSISTANT_OP_INVALID', 'format_block')
    chain.apply({'kind': 'format_blocks', 'targets': [{'blockId': block.id, 'beforeRevision': block.revision}], 'patch': patch})


def _allowed(record):
    allowed = set(FIELDS.get(record.kind, ()))
    if record.kind == 'employment':
        allowed.update(f'period:{value.id}:{part}' for value in record.periods for part in ('start', 'end', 'present'))
    return allowed


def first_occurrence(workspace, matches):
    for block in workspace.project.document.blocks():
        for key, content in inline_groups(block):
            for span, start, end in _fields(content):
                if matches(span):
                    return block, key, start, end, span
    return None


def _occurrence_edit(chain, found, value):
    block, key, start, end, span = found
    selected = {'blockId': block.id, 'beforeRevision': block.revision, 'cellId': None if key in {'content', 'caption'} else key,
        'field': 'caption' if key == 'caption' else 'content', 'start': start, 'end': end}
    if start == end:
        selected['insertionTarget'] = {'kind': 'field', 'bindingId': span.binding_id}
    chain.apply({'kind': 'replace_text', 'range': selected, 'text': value,
        'styles': span.styles.model_dump(mode='json', by_alias=True)})


def _panel(chain, operation, record_id, kind, *, job_id=None, values=None, context=None):
    step = {'kind': 'builtin_panel', 'command': {'operation': operation, 'recordId': record_id, 'recordKind': kind,
        'jobId': job_id, 'periodId': None, 'values': values or {}}}
    chain.apply({**step, 'placementContext': context} if context else step)


def update_fact(chain, op):
    """A builtin field changes through the panel, even with no occurrence; a template cell through its first occurrence."""
    record, extension = find_record(chain.current, op.record_id)
    if record is None:
        raise CompileFailure('ASSISTANT_TARGET_MISSING', op.record_id)
    if not extension:
        if op.field not in _allowed(record):
            raise CompileFailure('ASSISTANT_FIELD_UNKNOWN', op.field, *sorted(_allowed(record)))
        _panel(chain, 'edit', record.id, record.kind, values={op.field: op.value})
        return
    cell = next((value for value in record.cells if value.field_key == op.field), None)
    if cell is None:
        raise CompileFailure('ASSISTANT_FIELD_UNKNOWN', op.field, *sorted(value.field_key for value in record.cells))
    found = first_occurrence(chain.current, lambda span: getattr(span, 'cell_id', None) == cell.id)
    if found is None:
        raise CompileFailure('ASSISTANT_FIELD_WITHOUT_OCCURRENCE', op.field)
    _occurrence_edit(chain, found, op.value)


def _technology_context(chain, op):
    """The panel's placement of a new technology. A scope with several lines needs `targetId`; the refusal lists them with
    the template's view titles, as the panel names them."""
    scope = [value for value in technology_targets(chain.current.project) if value.job_id == op.job_id]
    chosen = [value for value in scope if op.target_id in {None, value.block_id}]
    if len(chosen) != 1:
        raise CompileFailure('ASSISTANT_OP_REFUSED', 'TECHNOLOGY_GROUP_REQUIRED' if scope else 'TECHNOLOGY_LINE_MISSING',
            *(f'{value.block_id}: {value.label}' for value in scope))
    return {'contextBlockId': chosen[0].block_id, 'placement': chosen[0].placement.model_dump(mode='json', by_alias=True)}


def create_fact(chain, op):
    """The panel adds jobs, their periods and technologies; other kinds have no adapter there."""
    if op.target_id is not None and op.kind != 'technology':
        raise CompileFailure('ASSISTANT_OP_INVALID', 'targetId')
    if op.kind == 'period':
        record, extension = find_record(chain.current, op.job_id) if op.job_id else (None, False)
        if record is None or extension or record.kind != 'employment':
            raise CompileFailure('ASSISTANT_TARGET_MISSING', op.job_id or 'jobId')
        _panel(chain, 'add_period', record.id, 'employment', values=dict(op.values))
    elif op.kind == 'technology':
        if op.values.keys() != {'display'}:
            raise CompileFailure('ASSISTANT_FIELD_UNKNOWN', 'values', 'display')
        _panel(chain, 'add', None, 'technology', job_id=op.job_id, values=dict(op.values), context=_technology_context(chain, op))
    elif op.kind == 'employment':
        _panel(chain, 'add', None, 'employment', values=dict(op.values))
    else:
        raise CompileFailure('ASSISTANT_OP_REFUSED', 'create ' + op.kind)


def delete_fact(chain, op):
    """What the panel removes goes as there, with its separator and an emptied line; the rest is deleted as an entity."""
    record, extension = find_record(chain.current, op.record_id)
    if record is None:
        raise CompileFailure('ASSISTANT_TARGET_MISSING', op.record_id)
    if not extension and record.kind in {'employment', *REMOVABLE}:
        _panel(chain, 'remove', record.id, record.kind)
        return
    chain.apply({'kind': 'delete_entity', 'recordId': record.id, 'beforeRevision': record.revision})


COMPILERS = {'set_block_text': set_block_text, 'replace_text': replace_text, 'insert_blocks': insert_blocks,
    'delete_blocks': delete_blocks, 'move_block': move_block, 'format_block': format_block, 'update_fact': update_fact,
    'create_fact': create_fact, 'delete_fact': delete_fact}


def compile_ops(workspace, ops, *, action_id, occupied, response_for):
    """The workspace after every op, prepared in order on `workspace`, and the ids the steps created."""
    if workspace.project is None:
        raise CompileFailure('ASSISTANT_TARGET_MISSING', 'project')
    chain = Chain(workspace, action_id=action_id, occupied=occupied, response_for=response_for)
    for op in ops:
        COMPILERS[op.op](chain, op)
    return chain.current, chain.created


def preview(before, after, ops):
    """Before and after text of every target the ops name, plus the blocks they created."""
    entries, seen = [], set()
    old_blocks = {block.id for block in before.project.document.blocks()}
    for op in ops:
        for identifier in targets(op):
            if identifier in seen or identifier in region_ids(before):
                continue
            seen.add(identifier)
            entries.append({'target': identifier, 'label': op.op, 'before': target_text(before, identifier)[:16000],
                'after': target_text(after, identifier)[:16000]})
    for block in after.project.document.blocks():
        if block.id not in old_blocks:
            entries.append({'target': block.id, 'label': 'insert_blocks', 'before': '', 'after': target_text(after, block.id)[:16000]})
    # A new technology joins an existing line, so neither a target nor a new block shows it.
    known = {record.id for record in before.project.facts.records}
    for record in after.project.facts.records:
        if record.kind == 'technology' and record.id not in known:
            entries.append({'target': record.id, 'label': 'create_fact', 'before': '', 'after': target_text(after, record.id)[:16000]})
    if not entries:
        entries.append({'target': 'facts', 'label': ops[0].op if ops else 'facts', 'before': '', 'after': ''})
    return entries
