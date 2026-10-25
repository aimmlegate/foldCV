"""Merge exact fallback intervals and suppress only overlapping authored values."""

from ..template_identity import capture_span, source_slice


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


def fallback_plan(sources, spans_by_view, cells_by_view, *, protected_spans=()):
    """A view's fallback replaces only the overlapping cells that view shows; accepted blocks elsewhere stay (K02).
    Suppressed cells are (view, cell id) pairs: a cell another view also shows stays there."""
    protected = [*protected_spans, *[span for cells in cells_by_view.values() for cell in cells
        if cell.origin == 'human' for span in cell.evidence]]
    placements = {view: subtract_spans(sources, spans, protected) for view, spans in spans_by_view.items()}
    expanded, suppressed = {view: set() for view in placements}, set()
    while True:
        changed = False
        for view, spans in placements.items():
            added = [cell for cell in cells_by_view.get(view, ()) if cell.origin != 'human' and cell.id not in expanded[view]
                and any(overlaps(span, raw) for span in cell.evidence for raw in spans)]
            if added:
                changed = True
                expanded[view].update(cell.id for cell in added)
                suppressed.update((view, cell.id) for cell in added)
                placements[view] = subtract_spans(sources, [*spans, *[span for cell in added for span in cell.evidence]], protected)
        if not changed:
            return union_spans(sources, [span for spans in placements.values() for span in spans]), suppressed, placements
