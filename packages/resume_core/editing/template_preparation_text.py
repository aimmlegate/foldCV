"""The text edit of one authored block: typed text, marks and the field occurrences it keeps."""

from __future__ import annotations

from ..fields import field_key, inline_groups
from ..models.rich_document import FactFieldSpan, Hyperlink, SectionBlock
from ..models.template_authoring import ReplaceText, SetMarks
from ..models.template_document import BoundLink, FieldRef, ManualScopeSpan, PresentedText
from .mutations import cut_inline, inline_text, locate, utf16_slice
from .template_preparation_blocks import changed_block_steps
from .template_preparation_cells import human_cell_steps
from .template_preparation_common import allocator_for, finish_preparation, prepared_response, validate_preparation
from .template_ranges import FlankRecorder


def _length(span):
    return len(inline_text(span).encode('utf-16-le')) // 2


def _leaves(content, origin=0):
    cursor = origin
    for span in content:
        length = _length(span)
        if isinstance(span, (Hyperlink, BoundLink)):
            yield from _leaves(span.content, cursor)
        else:
            yield span, cursor, cursor + length
        cursor += length


def _identity(span):
    return (getattr(span, 'cell_id', None) or field_key(span.record_id, span.field_key),
        getattr(span, 'occurrence_id', None) or span.binding_root_id or span.binding_id)


def _fields(content, origin=0):
    cursor = origin
    for span in content:
        length = _length(span)
        if isinstance(span, BoundLink) and span.label_binding is not None:
            yield span.label_binding, cursor, cursor + length
        elif isinstance(span, (Hyperlink, BoundLink)):
            yield from _fields(span.content, cursor)
        elif isinstance(span, FactFieldSpan) and getattr(span, 'complete', True):
            yield span, cursor, cursor + length
        cursor += length


def _raw_occurrence(document, bound):
    result = []
    for block in document.blocks():
        for _container, content in inline_groups(block):
            text = ''.join(inline_text(span) for span in content)
            for span, start, end in _fields(content):
                if _identity(span) == _identity(bound):
                    result.append(utf16_slice(text, start, end))
    return ''.join(result)


def _plain(span):
    return PresentedText(type='text', text=span.text, styles=span.styles.model_copy(deep=True),
        presentation=getattr(span, 'presentation', None), citations=[value.model_copy(deep=True) for value in getattr(span, 'citations', [])])


def _detach_copies(document, bound):
    """The field's other occurrences become plain text, as a shared edit leaves them: the fact took the typed text, so a
    bound copy would show a stale value. Returns the ids of the blocks that held one."""
    cell, root = _identity(bound)
    def other(reference):
        return _identity(reference)[0] == cell and _identity(reference)[1] != root
    touched = set()
    for block in document.blocks():
        for _container, content in inline_groups(block):
            for index, span in enumerate(content):
                if isinstance(span, FactFieldSpan) and other(span):
                    content[index] = _plain(span)
                elif isinstance(span, BoundLink) and span.label_binding is not None and other(span.label_binding):
                    label = [_plain(part) if isinstance(part, FactFieldSpan) else part for part in span.content]
                    if span.url_binding is None:
                        content[index:index + 1] = label
                    else:
                        span.content, span.label_binding = label, None
                else:
                    continue
                touched.add(block.id)
    return touched


def _range_content(block, selected):
    if block.revision != selected.before_revision or isinstance(block, SectionBlock):
        raise ValueError('stale authored block')
    key = selected.cell_id or selected.field
    groups = dict(inline_groups(block))
    content = groups.get(key)
    if content is None or selected.field == 'caption' and selected.cell_id is not None:
        raise ValueError('authored inline container missing')
    text = ''.join(inline_text(span) for span in content)
    if selected.end > len(text.encode('utf-16-le')) // 2:
        raise ValueError('authored range exceeds content')
    utf16_slice(text, selected.start, selected.end)
    return content, text


def _insertion(content, selected):
    target, point = selected.insertion_target, selected.start
    if target.kind == 'manual_scope':
        found = [span for span, start, end in _leaves(content) if isinstance(span, ManualScopeSpan)
            and span.fragment_id == target.fragment_id and start <= point <= end]
        if len(found) != 1:
            raise ValueError('insertion scope fragment does not contain the captured point')
        return found[0]
    if target.kind == 'field':
        found = [span for span, start, end in _leaves(content) if isinstance(span, FactFieldSpan)
            and span.binding_id == target.binding_id and start <= point <= end and getattr(span, 'complete', True)]
        if len(found) != 1:
            raise ValueError('insertion binding does not contain the captured point')
        return found[0]
    cursor, length = 0, sum(_length(span) for span in content)
    allowed = point in {0, length}
    for span in content:
        size = _length(span)
        if isinstance(span, PresentedText) and cursor <= point <= cursor + size:
            allowed = True
        cursor += size
    if not allowed:
        raise ValueError('literal insertion has no addressed literal boundary')
    return None


def _rewrite(content, selected, operation, allocator, bound, flanks, *, path=(), citations=(), replacement=None,
        gone=frozenset()):
    cursor = 0
    for index, span in enumerate(content):
        length = _length(span)
        nested_target = (selected.start != selected.end or isinstance(bound, FactFieldSpan)
            and any(child.binding_id == bound.binding_id for child, _start, _end in _leaves(span.content)
                if isinstance(child, FactFieldSpan))) if isinstance(span, (Hyperlink, BoundLink)) else False
        if nested_target and gone and selected.start <= cursor and cursor + length <= selected.end:
            # A link that a deletion wholly covers goes with its text, as the replay cuts it.
            nested_target = False
        if nested_target and cursor <= selected.start <= selected.end <= cursor + length:
            result = [part.model_copy(deep=True) for part in content]
            nested = selected.model_copy(update={'start': selected.start - cursor, 'end': selected.end - cursor})
            result[index].content, replacement = _rewrite(span.content, nested, operation, allocator, bound, flanks,
                path=(*path, index), citations=citations, replacement=replacement)
            middle = span.model_copy(deep=True)
            middle.content = replacement
            return result, [middle]
        cursor += length
    length = sum(_length(span) for span in content)
    prefix = cut_inline(content, 0, selected.start, id_factory=flanks.factory('prefix'))
    suffix = cut_inline(content, selected.end, length, id_factory=flanks.factory('suffix'), empty_end=True)
    if replacement is not None:
        inserted = replacement.insert(bound, path, content, selected)
    elif isinstance(operation, SetMarks):
        inserted = cut_inline(content, selected.start, selected.end, id_factory=allocator,
            allocation_path=(*path, 'marks'))
        for span, _start, _end in _leaves(inserted):
            span.styles = operation.styles.model_copy(deep=True)
    elif isinstance(bound, ManualScopeSpan):
        inserted_span = bound.model_copy(deep=True)
        inserted_span.text, inserted_span.styles = operation.text, operation.styles.model_copy(deep=True)
        inserted_span.fragment_id = allocator.allocate('manual-fragment', ['replace-scope-text', bound.scope_id,
            bound.occurrence_id, selected.start, selected.end, list(path)])
        inserted = [inserted_span]
    elif isinstance(bound, FactFieldSpan) and not operation.text and any(isinstance(span, FactFieldSpan)
            and _identity(span) == _identity(bound) for span, _start, _end in _leaves(prefix + suffix)):
        # A deletion adds no empty fragment while the field keeps another one here; only an emptied field keeps one, as
        # the place to type into. Each deleted letter used to leave one behind.
        inserted = []
    elif isinstance(bound, FactFieldSpan):
        inserted_span = bound.model_copy(deep=True)
        inserted_span.text, inserted_span.styles = operation.text, operation.styles.model_copy(deep=True)
        inserted_span.binding_id = allocator.allocate('fragment', ['replace-text', bound.binding_id,
            selected.start, selected.end, list(path)])
        for span, start, end in _leaves(content):
            if start < selected.end and end > selected.start:
                for citation in getattr(span, 'citations', []):
                    if citation not in inserted_span.citations:
                        inserted_span.citations.append(citation.model_copy(deep=True))
        inserted = [inserted_span]
    else:
        evidence, reference = [value.model_copy(deep=True) for value in citations], None
        for span, start, end in _leaves(content):
            if end <= selected.start or start >= selected.end:
                continue
            reference = reference or getattr(span, 'presentation', None)
            for citation in getattr(span, 'citations', []):
                if citation not in evidence:
                    evidence.append(citation.model_copy(deep=True))
        inserted = [PresentedText(type='text', text=operation.text, styles=operation.styles,
            presentation=reference, citations=evidence)] if operation.text else []
    return prefix + inserted + suffix, inserted


def _guard_links(content, selected, operation, gone=frozenset()):
    if not isinstance(operation, ReplaceText):
        return
    cursor = 0
    for span in content:
        length = _length(span)
        if isinstance(span, BoundLink) and selected.start <= cursor and cursor + length <= selected.end and any(
                _identity(field) in gone for field, _start, _end in _fields([span])):
            # The deletion takes the whole link off the page; its label and URL facts keep their values (F3-0).
            cursor += length
            continue
        if isinstance(span, BoundLink):
            overlap = selected.start < cursor + length and selected.end > cursor
            if selected.start == selected.end and cursor < selected.start < cursor + length:
                overlap = True
            if (selected.start == selected.end and selected.insertion_target.kind == 'field'
                    and any(child.binding_id == selected.insertion_target.binding_id for child, _start, _end
                        in _leaves(span.content) if isinstance(child, FactFieldSpan))):
                overlap = True
            if overlap and span.label_binding is None:
                raise ValueError('URL-only editing requires the dedicated URL path')
            if (overlap and span.url_binding is not None and selected.start <= cursor
                    and selected.end >= cursor + length
                    and (selected.start < cursor or selected.end > cursor + length)):
                raise ValueError('cross-link replacement cannot discard an untouched URL binding')
        cursor += length


def whole_occurrences(document, block_id, selected, field_ranges):
    """The field occurrences whose whole text lies inside the selected range of this one container (D178; it replaces
    the empty place of D132). An occurrence with text elsewhere is cut, not whole."""
    key = selected.cell_id or selected.field
    candidates = {_identity(span) for span, start, end in field_ranges if end > start}
    places = {}
    if candidates:
        for block in document.blocks():
            for container, content in inline_groups(block):
                for span, start, end in _fields(content):
                    if _identity(span) in candidates:
                        places.setdefault(_identity(span), []).append((block.id, container, start, end))
    return {identity for identity in candidates if all(owner == block_id and container == key
        and selected.start <= start and end <= selected.end for owner, container, start, end in places[identity])}


def _without_gone(content, gone):
    """An empty fragment that an older save left beside a removed field goes too: typed text there is the user's own."""
    result = []
    for span in content:
        if isinstance(span, FactFieldSpan) and not span.text and _identity(span) in gone:
            continue
        if isinstance(span, (Hyperlink, BoundLink)):
            kept = span.model_copy(deep=True)
            kept.content = _without_gone(kept.content, gone)
            if kept.content or not span.content:
                result.append(kept)
            continue
        result.append(span)
    return result


def _technology_names(workspace, fields):
    records = {record.id for record in workspace.project.facts.records if record.kind == 'technology'}
    return [span for span in fields if span.record_id in records and span.field_key == 'display']


def model_written_steps(response, request, steps):
    """D179: the marks that a model wrote each cell these steps change, for the Apply of an unchanged rewrite preview.
    A cell is one value: when the selection covers a part of it, the whole value counts as the model's until the user
    types in it or accepts it."""
    from .template_mutations import _cell_values
    from .template_preparation_common import next_facts
    facts = response.workspace.project.facts
    before, after = _cell_values(facts), _cell_values(next_facts(response, request, steps))
    return [{'kind': 'set_model_written', 'cellId': cell, 'beforeActionId': facts.model_written.get(cell),
        'afterActionId': request.capture.action_id} for cell in sorted(after) if before.get(cell) != after[cell]]


def prepare_text_edit(response, request, *, operation=None, replacement=None, occupied=None):
    workspace = response.workspace
    validate_preparation(response, request)
    operation = operation or request.operations[0]
    if not isinstance(operation, (ReplaceText, SetMarks)):
        raise ValueError('text preparation needs a text operation')
    selected = operation.range
    found = locate(workspace.project.document, selected.block_id)
    if found is None:
        raise ValueError('authored block missing')
    original = found[0][found[1]]
    content, text = _range_content(original, selected)
    if replacement is None and isinstance(operation, ReplaceText) and utf16_slice(text, selected.start, selected.end) == operation.text:
        operation = SetMarks(kind='set_marks', opId=operation.op_id, range=selected, styles=operation.styles)
    field_ranges = [(span, start, end) for span, start, end in _fields(content)
        if start < selected.end and end > selected.start or start == end and selected.start <= start < selected.end]
    gone = set()
    if isinstance(operation, ReplaceText) and replacement is None and not operation.text and selected.start != selected.end:
        # A deletion of a field's whole text takes the field off the page and keeps its fact; a technology line stays
        # locked, so its name keeps the refusal below.
        gone = whole_occurrences(workspace.project.document, original.id, selected, field_ranges) - {
            _identity(span) for span in _technology_names(workspace, [span for span, _start, _end in field_ranges])}
    _guard_links(content, selected, operation, frozenset(gone))
    allocator = allocator_for(response, request, operation, occupied)
    if replacement is not None:
        replacement.allocator = allocator
    def prepared(mutation, preview):
        return prepared_response(response, request, allocator, mutation, preview)
    if isinstance(operation, SetMarks) and selected.start == selected.end:
        return prepared(None, response.model_copy(deep=True))
    leaves = [(span, start, end) for span, start, end in _leaves(content)
        if start < selected.end and end > selected.start or start == end and selected.start <= start < selected.end]
    gone_length = sum(min(end, selected.end) - max(start, selected.start) for span, start, end in field_ranges
        if _identity(span) in gone)
    field_ranges = [(span, start, end) for span, start, end in field_ranges if _identity(span) not in gone]
    fields = [span for span, _start, _end in field_ranges]
    scope_ranges = [(span, start, end) for span, start, end in leaves if isinstance(span, ManualScopeSpan)]
    bound, direct = None, False
    if isinstance(operation, ReplaceText) and selected.start == selected.end:
        bound = _insertion(content, selected)
        fields = [bound] if isinstance(bound, FactFieldSpan) else []
        direct = isinstance(bound, FactFieldSpan)
        if isinstance(bound, ManualScopeSpan):
            scope_ranges = [(bound, selected.start, selected.end)]
    elif fields:
        covered = gone_length + sum(min(end, selected.end) - max(start, selected.start) for _span, start, end in field_ranges)
        direct = not scope_ranges and len({_identity(span) for span in fields}) == 1 and covered == selected.end - selected.start
        bound = fields[0] if direct else None
    if replacement is not None:
        replacement.guard(content, selected, fields, scope_ranges, bound)
        replacement.same_text = not replacement.semantic and utf16_slice(text, selected.start, selected.end) == operation.text
        if selected.start == selected.end and (not replacement.content or replacement.same_text):
            return prepared(None, response.model_copy(deep=True))
    if (replacement is None and all(span.styles == operation.styles for span, _start, _end in leaves)
            and (isinstance(operation, SetMarks) or utf16_slice(text, selected.start, selected.end) == operation.text)):
        return prepared(None, response.model_copy(deep=True))
    structural_paste = replacement is not None and replacement.same_text
    if (isinstance(operation, ReplaceText) and not structural_paste and fields and not direct and not operation.text.strip()
            and _technology_names(workspace, fields)):
        raise ValueError('TECHNOLOGY_NAME_EMPTY')
    if isinstance(operation, ReplaceText) and not structural_paste and (scope_ranges or fields and not direct):
        from .template_preparation_scopes import scope_edit_steps
        steps, candidate = scope_edit_steps(workspace, operation, allocator, content, fields, scope_ranges, bound,
            request.capture.action_id, replacement=replacement)
    else:
        candidate = workspace.project.model_copy(deep=True)
        candidate_found = locate(candidate.document, selected.block_id)
        block = candidate_found[0][candidate_found[1]]
        target_content = dict(inline_groups(block))[selected.cell_id or selected.field]
        seed = bound
        if isinstance(bound, FieldRef):
            seed = next((span for span, _start, _end in leaves if isinstance(span, FactFieldSpan)
                and _identity(span) == _identity(bound)), None)
        flanks = FlankRecorder(allocator)
        changed, inserted = _rewrite(content, selected, operation, allocator, seed, flanks, replacement=replacement,
            gone=frozenset(gone))
        kept = _without_gone(changed, gone) if gone else changed
        target_content[:] = kept
        steps = [{'kind': 'replace_inline_range', 'blockId': original.id, 'cellId': selected.cell_id, 'field': selected.field,
            'start': selected.start, 'end': selected.end, 'beforeRevision': original.revision,
            'content': [part.model_dump(by_alias=True) for part in inserted], 'flankBindings': flanks.entries}]
        if isinstance(operation, ReplaceText) and fields and not structural_paste:
            raw = _raw_occurrence(candidate.document, bound)
            if not raw.strip() and _technology_names(workspace, fields):
                raise ValueError('TECHNOLOGY_NAME_EMPTY')
            steps += human_cell_steps(workspace, sorted({_identity(span)[0] for span in fields}), raw,
                request.capture.action_id, [original.id], allocator)
            copies = _detach_copies(candidate.document, bound)
            if copies:
                # Two changes to one block go as one; a range step cannot name the copy beside the edit.
                tree, _removed = changed_block_steps(workspace.project.document, candidate.document)
                steps = tree + steps[1:] if original.id in copies else [*steps,
                    *(step for step in tree if step['block']['id'] != original.id)]
        if kept != changed and steps[0]['kind'] == 'replace_inline_range':
            # The range replay keeps an empty fragment at the range end; only a block write drops it.
            tree, _removed = changed_block_steps(workspace.project.document, candidate.document)
            steps = [step for step in tree if step['block']['id'] == original.id] + steps[1:]
    if isinstance(operation, ReplaceText) and operation.written == 'model':
        steps += model_written_steps(response, request, steps)
    result = finish_preparation(response, request, allocator, steps, candidate,
        kind='typing' if isinstance(operation, ReplaceText) and replacement is None else 'structure')
    # Clipboard content is never optimistic, so a paste offers no address correspondence.
    result._address_middle = None if replacement is not None else 'restyled' if isinstance(operation, SetMarks) else 'inserted'
    return result
