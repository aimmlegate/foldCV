"""Keep exact source display text while retaining reviewed interpretations separately."""

from .template_import import digest
from .templates.compiler import canonical


def display_raw_input(review, field, raw):
    if (review.allow_text_rewrite or not isinstance(raw, str) or not raw.strip()
            or field.pointer not in review.semantic_context.get('sourceWordingPointers', [])):
        return raw if isinstance(raw, str) else canonical(raw).decode()
    if field.evidence:
        offered = ([(option.span, option.text) for option in review.evidence] if review.schema_version == 2
            else [(span, review.source_texts[digest(span)]) for span in review.source_spans])
        units, captured = {}, {}
        for span, text in offered:
            key = (span.source_id, span.source_revision, span.unit_id, span.unit_revision)
            captured[digest(span)] = text
            current = units.get(key)
            if current is None or span.start <= current.start and span.end >= current.end:
                units[key] = span
        grouped = {}
        for span in field.evidence:
            key = (span.source_id, span.source_revision, span.unit_id, span.unit_revision)
            grouped.setdefault(key, []).append((span.start, span.end))
        texts = []
        for key, unit in units.items():
            intervals = sorted(set(grouped.pop(key, [])))
            merged = []
            for start, end in intervals:
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            text = captured[digest(unit)]
            if any(start < unit.start or end > unit.end for start, end in merged):
                raise ValueError('source wording exceeds captured context')
            texts.extend(text[start - unit.start:end - unit.start] for start, end in merged)
        if grouped:
            raise ValueError('source wording lacks captured context')
        return '\n'.join(texts)
    cells = {cell.id: cell for cell in review.effective_cells}
    scopes = {value['id']: value for value in review.semantic_context.get('taskInput', {}).get('manualScopes', [])}
    texts, shown = [], set()
    for identifier in field.effective_cell_ids:
        cell = cells.get(identifier)
        if cell is None:
            raise ValueError('source wording references missing effective input')
        if cell.manual_scope_id:
            if cell.manual_scope_id not in shown:
                texts.append(scopes[cell.manual_scope_id]['rawInput'])
                shown.add(cell.manual_scope_id)
        else:
            texts.append(cell.raw_input)
    if not texts:
        raise ValueError('source wording needs captured source or effective text')
    return '\n'.join(texts)
