"""Entries of a block extracted on their own (D117).

A block declared `per_entry` is outlined first: one call names its entries, each by its title and by the refs of its
first and last source line. Consecutive entries are joined into as many groups as calls run at once, and every group
runs as its own entry task with the block's captured input and an `entry` part that names its lines and the outline
entries in them; its reply holds the items those lines state, so a group that joins two items of one outline entry
loses neither. The review of the outline runs beside them and may add an entry the outline missed. When they all
ended, the block closes with what they collected, its records in the entries' order.
"""

from .models.template_import import OutlineReply, OutlineReviewReply
from .template_import import digest, entries_of
from .templates.compiler import splits_entries

MAX_TITLE = 120
# D117 review: an entry the outline review names, whose lines another entry already holds, is named in the notice.
OVERLAP_WHOLE = 'Запись «{title}» из проверки уже входит в другую запись.'
OVERLAP_PART = 'Запись «{title}» из проверки частично входит в другую запись, остальные её строки извлечены отдельно.'


def _position(sources, span):
    units = [(index, unit.order) for index, source in enumerate(sources) if source.id == span.source_id
        for unit in source.units if unit.id == span.unit_id]
    if len(units) != 1:
        raise ValueError('outline span names no captured unit')
    return (*units[0], span.start)


def line_options(offered, sources):
    """The offered options that stand for single lines, in document order: each line of a multi-line unit, else the
    unit itself. A whole-unit option of a multi-line unit is not a line, nor is a blank one."""
    by_unit = {}
    for option in offered.values():
        if option.text.strip():
            by_unit.setdefault((option.span.source_id, option.span.unit_id), []).append(option)
    lines = []
    for options in by_unit.values():
        whole = [option for option in options if option.span.start == 0 and option.span.end == max(
            value.span.end for value in options)]
        parts = [option for option in options if option not in whole]
        lines += parts or whole[:1]
    return sorted(lines, key=lambda option: _position(sources, option.span))


def _bounds(ref, offered, lines, sources):
    """The first and last line index a ref stands for: its own line, or every line of a whole multi-line unit."""
    option = offered.get(ref)
    if option is None:
        raise ValueError('outline names an unoffered ref')
    indices = [index for index, line in enumerate(lines) if line.ref == ref]
    if not indices:
        indices = [index for index, line in enumerate(lines) if (line.span.source_id, line.span.unit_id)
            == (option.span.source_id, option.span.unit_id) and option.span.start <= line.span.start
            and line.span.end <= option.span.end]
    if not indices:
        raise ValueError('outline names no source line')
    return indices[0], indices[-1]


def _title(value, index):
    text = ' '.join(value.split())[:MAX_TITLE]
    return text or 'Запись ' + str(index)


def outline_scopes(entries, offered, sources, *, taken=(), overlapped=None):
    """(title, spans) for each outlined entry: its lines from its first to its last offered line in document order.
    Refuses a ref that is no offered line and entries that share a line. An entry keeps only its lines that `taken`
    (the lines of entries already running) does not hold; with none left it is no entry. Each entry that lost lines
    is added to `overlapped` as (title, whether lines are left)."""
    lines = line_options(offered, sources)
    held = {digest(span) for span in taken}
    scopes, used = [], set()
    for number, entry in enumerate(entries, 1):
        first, last = _bounds(entry.first, offered, lines, sources)[0], _bounds(entry.last, offered, lines, sources)[1]
        if first > last:
            first, last = last, first
        chosen = list(range(first, last + 1))
        if used & set(chosen):
            raise ValueError('outline entries share a line')
        used.update(chosen)
        title = _title(entry.title, number)
        free = [lines[index].span for index in chosen if digest(lines[index].span) not in held]
        if len(free) < len(chosen) and overlapped is not None:
            overlapped.append((title, bool(free)))
        if free:
            scopes.append((title, free))
    return scopes


def parse_outline(payload, offered, sources):
    return outline_scopes(OutlineReply.model_validate(payload, strict=True).entries, offered, sources)


def parse_outline_review(payload, offered, sources, *, taken):
    """The entries an outline review adds and its remarks on the outlined ones. A missed entry whose lines other
    entries already hold is named in a remark: its free lines run as their own entry, and with none left it adds
    nothing, so no line it names goes unseen."""
    reply = OutlineReviewReply.model_validate(payload, strict=True)
    overlapped = []
    missing = outline_scopes(reply.missing, offered, sources, taken=taken, overlapped=overlapped)
    remarks = [' '.join(remark.reason.split()) for remark in reply.remarks if remark.reason.strip()]
    remarks += [(OVERLAP_PART if free else OVERLAP_WHOLE).format(title=title) for title, free in overlapped]
    return missing, remarks


def _bounds_part(spans, refs):
    named = [refs[digest(span)] for span in spans if digest(span) in refs]
    return {'first': named[0], 'last': named[-1]} if named else {}


def entry_part(operation, task, offered):
    """The request part that tells a call which entry it extracts: the entry's lines by the request's refs, the outline
    entries in them and the other entries of the block by title and bounds."""
    refs = {digest(option.span): option.ref for option in offered.values()}
    others = [{'index': other.entry.index, 'title': other.entry.title, **_bounds_part(other.entry.spans, refs)}
        for other in entries_of(operation, task.parent_task_id) if other.id != task.id]
    return {'index': task.entry.index, 'title': task.entry.title,
        'lines': [refs[digest(span)] for span in task.entry.spans if digest(span) in refs],
        'parts': [{'title': part.title, **_bounds_part(part.spans, refs)} for part in task.entry.parts], 'others': others}


def outline_part(operation, parent_id, offered):
    """The outline as its review reads it: every outline entry with its title and bounds, not the groups they run in."""
    refs = {digest(option.span): option.ref for option in offered.values()}
    parts = [part for task in entries_of(operation, parent_id) for part in task.entry.parts]
    return {'entries': [{'index': index, 'title': part.title, **_bounds_part(part.spans, refs)}
        for index, part in enumerate(parts, 1)]}


def ordered_entries(operation, parent_id, sources):
    """The entry tasks of a block in the order the block shows them: the outline's order; an entry its review added
    goes by its source position when the outlined entries follow the source, else last."""
    entries = sorted(entries_of(operation, parent_id), key=lambda task: task.entry.index)
    outlined = [task for task in entries if task.entry.origin == 'outline']
    added = [task for task in entries if task.entry.origin != 'outline']
    def position(task):
        return min(_position(sources, span) for span in task.entry.spans) if task.entry.spans else None
    positions = [position(task) for task in outlined]
    ascending = all(left is not None and right is not None and left < right for left, right in zip(positions, positions[1:]))
    descending = all(left is not None and right is not None and left > right for left, right in zip(positions, positions[1:]))
    if not added or not outlined or not (ascending or descending):
        return [*outlined, *added]
    result = list(outlined)
    for task in added:
        place = position(task)
        index = next((number for number, other in enumerate(result) if place is not None and position(other) is not None
            and (position(other) > place if ascending else position(other) < place)), len(result))
        result.insert(index, task)
    return result


def entry_records(operation, tasks):
    """The record ids the given entry tasks allocated, in task order."""
    return [allocation.record_id for task in tasks for allocation in operation.allocations if allocation.task_id == task.id]


def reorder_records(facts, record_ids):
    """facts with the named records in the given order; each list keeps the slots its named records hold."""
    wanted = set(record_ids)
    for name in ('records', 'extensions'):
        items = getattr(facts, name)
        present = [identifier for identifier in record_ids if any(item.id == identifier for item in items)]
        slots = [index for index, item in enumerate(items) if item.id in wanted]
        by_id = {item.id: item for item in items}
        for slot, identifier in zip(slots, present, strict=True):
            items[slot] = by_id[identifier]
    return facts


def grouped(scopes, count):
    """Consecutive outline entries ((title, spans) each) joined into at most `count` groups of about the same number of
    lines. With `count` calls at once, one call per group ends sooner than rounds of one call per entry, and makes
    fewer calls and reviews: each call pays the same start, prompt and review cost."""
    count = max(1, min(count, len(scopes)))
    total = sum(len(spans) for _title, spans in scopes)
    groups, current, seen = [], [], 0
    for index, scope in enumerate(scopes):
        current.append(scope)
        seen += len(scope[1])
        left_groups, left_scopes = count - len(groups) - 1, len(scopes) - index - 1
        if left_groups > 0 and (seen * count >= total * (len(groups) + 1) or left_scopes == left_groups):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def closed_state(entries):
    """The state and result disposition of a block whose entries ended: accepted when any entry kept values (also one
    that shows a remark beside them), else a source fallback when one fell back, else empty."""
    states = {task.state for task in entries}
    if 'accepted' in states:
        return 'accepted', 'admitted'
    return ('source_fallback', 'source_fallback') if 'source_fallback' in states else ('empty', 'empty')
