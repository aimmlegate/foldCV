"""Keep exact source display text while retaining reviewed interpretations separately."""

from .models.template_import import EvidenceOption
from .template_completion import stating, stating_words
from .template_import import digest
from .template_source_cleanup import clean_source_wording
from .templates.compiler import canonical


def display_text(raw):
    """The text a reader sees: a date or period shows its stated wording, any other object its canonical JSON.
    Built-in records already map dates this way; a template-only type (CT08) showed the JSON."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get('raw'), str) and raw['raw'].strip():
        return raw['raw']
    return canonical(raw).decode()


def own_evidence(raw, evidence, units, captured):
    """The cited spans that are this value's own. A derived citation lists every line that states the value and a
    list-level entry every line of its list; shown whole, each value would repeat the lines of the others."""
    if len(evidence) < 2:
        return evidence
    table = {}
    for index, span in enumerate(evidence):
        unit = units.get((span.source_id, span.source_revision, span.unit_id, span.unit_revision))
        if unit is None or span.start < unit.start or span.end > unit.end:
            return evidence
        text = captured[digest(unit)][span.start - unit.start:span.end - unit.start]
        table[str(index)] = EvidenceOption(ref=str(index), span=span, text=text)
    value = raw.strip()
    exact = [ref for ref, option in table.items() if option.text.strip() == value]
    return [table[ref].span for ref in exact[:1] or stating(value, table)[:1] or stating_words(value, table)] or evidence


def display_raw_input(review, field, raw):
    if (review.allow_text_rewrite or not isinstance(raw, str) or not raw.strip()
            or field.pointer not in review.semantic_context.get('sourceWordingPointers', [])):
        return display_text(raw)
    return clean_source_wording(source_wording(review, field, raw), field.pointer)


def source_wording(review, field, raw):
    """The exact source text a value cites, or the input its effective cells hold."""
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
        for span in own_evidence(raw, field.evidence, units, captured):
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
            # Cited lines end with their line break; it ends the line, it is not part of the wording.
            texts.extend(value.rstrip('\r\n') or value for value in (text[start - unit.start:end - unit.start] for start, end in merged))
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
