"""Prepare exact human text transactions without a second editor or inference."""

from .models.rich_document import FactFieldSpan, Hyperlink, SectionBlock
from .models.template_authoring import ReplaceText, SetMarks
from .models.template_document import BoundLink, FieldRef, ManualScopeSpan, PresentedText
from .rich_fields import field_key, inline_groups
from .rich_mutations import cut_inline, inline_text, locate, utf16_slice
from .template_preparation_common import allocator_for, finish_preparation, preparation_hash, prepared_response, validate_preparation
from .template_preparation_blocks import changed_block_steps
from .template_preparation_cells import human_cell_steps
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


def _rewrite(content, selected, operation, allocator, bound, flanks, *, path=(), citations=(), replacement=None):
    cursor = 0
    for index, span in enumerate(content):
        length = _length(span)
        nested_target = (selected.start != selected.end or isinstance(bound, FactFieldSpan)
            and any(child.binding_id == bound.binding_id for child, _start, _end in _leaves(span.content)
                if isinstance(child, FactFieldSpan))) if isinstance(span, (Hyperlink, BoundLink)) else False
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


def _guard_links(content, selected, operation):
    if not isinstance(operation, ReplaceText):
        return
    cursor = 0
    for span in content:
        length = _length(span)
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


def _technology_names(workspace, fields):
    records = {record.id for record in workspace.project.facts.records if record.kind == 'technology'}
    return [span for span in fields if span.record_id in records and span.field_key == 'display']


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
    _guard_links(content, selected, operation)
    allocator = allocator_for(response, request, operation, occupied)
    if replacement is not None:
        replacement.allocator = allocator
    def prepared(mutation, preview):
        return prepared_response(response, request, allocator, mutation, preview)
    if isinstance(operation, SetMarks) and selected.start == selected.end:
        return prepared(None, response.model_copy(deep=True))
    leaves = [(span, start, end) for span, start, end in _leaves(content)
        if start < selected.end and end > selected.start or start == end and selected.start <= start < selected.end]
    field_ranges = [(span, start, end) for span, start, end in _fields(content)
        if start < selected.end and end > selected.start or start == end and selected.start <= start < selected.end]
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
        covered = sum(min(end, selected.end) - max(start, selected.start) for _span, start, end in field_ranges)
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
        changed, inserted = _rewrite(content, selected, operation, allocator, seed, flanks, replacement=replacement)
        target_content[:] = changed
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
    result = finish_preparation(response, request, allocator, steps, candidate,
        kind='typing' if isinstance(operation, ReplaceText) and replacement is None else 'structure')
    # Clipboard content is never optimistic, so a paste offers no address correspondence.
    result._address_middle = None if replacement is not None else 'restyled' if isinstance(operation, SetMarks) else 'inserted'
    return result


def prepare_edit(response, request, *, clipboard=None, occupied=None, remembered=None):
    """The prepared result of one authored operation on the exact durable response; `occupied` names the ids already
    taken (the repository session keeps them, otherwise they are collected from the workspace). `remembered`: the
    Focus icons the user chose before, which a row added from the facts panel takes (D122)."""
    if isinstance(request.operations[0], (ReplaceText, SetMarks)):
        return prepare_text_edit(response, request, occupied=occupied)
    from .models.template_authoring import PasteInline
    if isinstance(request.operations[0], PasteInline):
        from .template_preparation_paste import prepare_inline_paste
        return prepare_inline_paste(response, request, clipboard=clipboard, occupied=occupied)
    from .models.template_authoring import BuiltinPanel, DeleteEntity
    if isinstance(request.operations[0], (BuiltinPanel, DeleteEntity)):
        from .template_preparation_panel import prepare_panel_edit
        return prepare_panel_edit(response, request, occupied=occupied, remembered=remembered)
    from .models.template_authoring import ResolveTemplateSync
    if isinstance(request.operations[0], ResolveTemplateSync):
        from .template_preparation_sync import prepare_sync_resolution
        return prepare_sync_resolution(response, request, occupied=occupied)
    from .models.template_authoring import SetLinkTarget
    if isinstance(request.operations[0], SetLinkTarget):
        from .template_preparation_link import prepare_link_target
        return prepare_link_target(response, request, occupied=occupied)
    from .template_preparation_structure import prepare_structure_edit
    return prepare_structure_edit(response, request, clipboard=clipboard, occupied=occupied)
