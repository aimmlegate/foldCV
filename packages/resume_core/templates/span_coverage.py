"""Merge exact fallback intervals and suppress only overlapping authored values."""

from ..sources import capture_span, source_slice


def unit_key(span):
    return (span.source_id, span.source_revision, span.unit_id, span.unit_revision)


def overlaps(left, right):
    return unit_key(left) == unit_key(right) and left.start < right.end and right.start < left.end


def union_spans(sources, spans):
    units = {(source.id, source.revision, unit.id, unit.revision): (source, unit)
        for source in sources for unit in source.units}
    grouped = {}
    for span in spans:
        source_slice(sources, span)
        if span.start < span.end:
            grouped.setdefault(unit_key(span), []).append((span.start, span.end))
    result = []
    for key, (source, unit) in units.items():
        merged = []
        for start, end in sorted(set(grouped.pop(key, []))):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        result.extend(capture_span(source, unit, start, end) for start, end in merged)
    if grouped:
        raise ValueError('fallback references an unknown source unit')
    return result


def without_line_break(sources, span):
    """The span without its closing line break, which a paragraph cannot show; None when nothing else remains."""
    source = next(source for source in sources if (source.id, source.revision) == (span.source_id, span.source_revision))
    unit = next(unit for unit in source.units if (unit.id, unit.revision) == (span.unit_id, span.unit_revision))
    end = span.start + len(unit.text[span.start:span.end].rstrip('\r\n'))
    return None if end == span.start else span if end == span.end else capture_span(source, unit, span.start, end)


def subtract_spans(sources, spans, exclusions):
    protected = union_spans(sources, exclusions)
    remaining = []
    units = {(source.id, source.revision, unit.id, unit.revision): (source, unit)
        for source in sources for unit in source.units}
    for span in union_spans(sources, spans):
        intervals = [(span.start, span.end)]
        for blocked in protected:
            if unit_key(span) != unit_key(blocked):
                continue
            intervals = [(left, right) for start, end in intervals
                for left, right in [(start, min(end, blocked.start)), (max(start, blocked.end), end)] if left < right]
        source, unit = units[unit_key(span)]
        remaining.extend(capture_span(source, unit, start, end) for start, end in intervals)
    return union_spans(sources, remaining)


def within_spans(sources, spans, scope):
    """The parts of spans that lie inside the scope spans."""
    return subtract_spans(sources, spans, subtract_spans(sources, spans, scope))


def fallback_plan(sources, fallbacks, cells_by_view, *, protected_spans=()):
    """Each fallback (view, owner, spans) shows its lines in its view and replaces there only its owner's cells that
    cite them, with their lines (K02's one source copy); `cells_by_view` lists (cell, owners) per view. A fallback never
    reaches another task's or record's values (D156): every card cites the shared employer and job-title lines.
    Suppressed cells are (view, cell id) pairs: a cell another view also shows stays there."""
    protected = [*protected_spans, *[span for cells in cells_by_view.values() for cell, _owners in cells
        if cell.origin == 'human' for span in cell.evidence]]
    placements, suppressed = {}, set()
    for view, owner, spans in fallbacks:
        own = [cell for cell, owners in cells_by_view.get(view, ()) if cell.origin != 'human' and owner in owners]
        placed, taken = subtract_spans(sources, spans, protected), set()
        while added := [cell for cell in own if cell.id not in taken
                and any(overlaps(span, raw) for span in cell.evidence for raw in placed)]:
            taken.update(cell.id for cell in added)
            placed = subtract_spans(sources, [*placed, *[span for cell in added for span in cell.evidence]], protected)
        suppressed.update((view, identifier) for identifier in taken)
        placements[view] = union_spans(sources, [*placements.get(view, []), *placed])
    return union_spans(sources, [span for spans in placements.values() for span in spans]), suppressed, placements
