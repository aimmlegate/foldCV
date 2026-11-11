"""The technologies an entry owns, read against the entry's lines (point 14 of T4, D164).

The model sometimes writes a project technology the source does not name as written: it expands an abbreviation the
source states (TCA (Composable Architecture) where the CV says TCA) or changes the dash of a version range. A name
the entry's lines state as written, case and spacing aside, or by an alias the catalog gives it, passes. One they
write with other spaces or punctuation takes their spelling when the reply is completed (template_completion). Any
other fails the template's own rule by code before the review (template_review, D115); the repair gets it as any
finding (D107), and it stays a warning when the repair leaves it (D156).
"""

import re

from ..sources import source_slice
from ..technologies import BY_ID, resolve_technology, split_version
from ..templates.source_spans import payload_value

# The catalog leaves these unresolved, as common words of free text; a technologies item names the one technology.
AMBIGUOUS = {'go': 'golang', 'node': 'nodejs', 'drf': 'djangorest'}
# Signs a name may hold or leave out between its letters (Win Forms, Node.js, CI/CD, 4–5); a comma, a semicolon or a
# line break ends a name.
JOINING = re.compile(r'[^\S\r\n]|[-.\\/_+#&\'’()\[\]‐-―−]')
# Cyrillic letters that look like Latin ones are the same text (D163): 1С and 1C are one name.
LOOKALIKE = str.maketrans('авсенкмортху', 'abcehkmoptxy')
FINDING = 'Строки этой записи не называют технологию «{name}».'


def owned_types(fact_types):
    """The fact types of the technologies an entry owns: a job's or project's stack, not a skills list."""
    return frozenset(value.id for value in fact_types if value.builtin_kind == 'technology'
        and any(relation.kind == 'owned_by' for relation in value.relations))


def _folded(text):
    return ' '.join(text.split()).casefold()


def named(name, texts):
    """Whether lines name a technology: as written, case and spacing aside, a version may follow it (Python3, C++17);
    or by an alias the catalog gives it, with the version the name states."""
    value, lines = _folded(name), '\n'.join(_folded(text) for text in texts)
    if re.search(r'(?<![^\W_])' + re.escape(value) + r'(?![^\W\d_])', lines):
        return True
    base, version = split_version(name)
    identifier = resolve_technology(name).canonical_id or AMBIGUOUS.get(base)
    if identifier is None:
        return False
    aliases = [*BY_ID[identifier].aliases, *[word for word, target in AMBIGUOUS.items() if target == identifier]]
    return (any(re.search(r'(?<![\w.+#])' + re.escape(alias) + r'(?![\w+#])', lines) for alias in aliases)
        and (version is None or re.search(r'(?<![\w.])v?' + re.escape(version) + r'(?!\w)', lines) is not None))


def _word(text, index):
    return 0 <= index < len(text) and (text[index].isalnum() or text[index] == '_')


def _joined(text):
    return all(char.isalnum() or JOINING.fullmatch(char) for char in text)


def _paired(text, start, end):
    """The bounds widened over the brackets just outside them that pair the ones inside; None when one stays
    unpaired."""
    for opening, closing in ('()', '[]'):
        while text.count(opening, start, end) > text.count(closing, start, end) and text[end:end + 1] == closing:
            end += 1
        while (text.count(closing, start, end) > text.count(opening, start, end) and start
                and text[start - 1] == opening):
            start -= 1
        if text.count(opening, start, end) != text.count(closing, start, end):
            return None
    return start, end


def _letter(char):
    return char.casefold().translate(LOOKALIKE)


def source_spelling(name, texts):
    """How a line writes a name with other spaces or punctuation (WinForms for Win Forms, 4–5 for 4-5): the whole words
    with the name's letters and digits, joined by signs a name may hold and led and closed by the name's own signs
    (.NET, C++); None when no line writes it so."""
    name = name.strip()
    letters = [index for index, char in enumerate(name) if char.isalnum()]
    if not letters or not _joined(name[letters[0]:letters[-1] + 1]):
        return None
    lead, trail = name[:letters[0]], name[letters[-1] + 1:]
    key = ''.join(_letter(name[index]) for index in letters)
    if len(key) < 2:
        return None
    for text in texts:
        # The line's letters and digits; starts and ends map their offsets back to the line.
        flat, starts, ends = [], {}, {}
        for index, char in enumerate(text):
            if char.isalnum():
                starts[len(flat)] = index
                flat.extend(_letter(char))
                ends[len(flat)] = index + 1
        flat = ''.join(flat)
        at = flat.find(key)
        while at >= 0:
            first, last = starts.get(at), ends.get(at + len(key))
            if first is not None and last is not None and _joined(text[first:last]):
                start, end = first - len(lead), last + len(trail)
                bounds = _paired(text, start, end) if (start >= 0 and text[start:first] == lead
                    and text[last:end] == trail) else None
                if bounds and not _word(text, bounds[0] - 1) and not _word(text, bounds[1]):
                    return text[bounds[0]:bounds[1]]
            at = flat.find(key, at + 1)
    return None


def respelling(name, scopes):
    """The spelling a technology takes from the first scope (a list of line texts) that names it or writes it
    otherwise; None when that scope names it as it is, or no scope writes it."""
    for texts in scopes:
        if named(name, texts):
            return None
        spelled = source_spelling(name, texts)
        if spelled is not None:
            return spelled
    return None


def _stretch(sources, spans, others=()):
    """The source text from the first to the last of the spans, through every unit between them, without the text of
    the other spans."""
    texts = []
    for source in sources:
        units = {(unit.id, unit.revision): unit for unit in source.units}
        def inside(span, source=source, units=units):
            return ((span.source_id, span.source_revision) == (source.id, source.revision)
                and (span.unit_id, span.unit_revision) in units)
        own = [(units[(span.unit_id, span.unit_revision)], span) for span in spans if inside(span)]
        if not own:
            continue
        low = min((unit.order, span.start) for unit, span in own)
        high = max((unit.order, span.end) for unit, span in own)
        for unit in sorted(source.units, key=lambda value: value.order):
            if not low[0] <= unit.order <= high[0]:
                continue
            position, end = low[1] if unit.order == low[0] else 0, high[1] if unit.order == high[0] else len(unit.text)
            for start, stop in sorted((span.start, span.end) for span in others if inside(span)
                    and (span.unit_id, span.unit_revision) == (unit.id, unit.revision)):
                if start < end and stop > position:
                    texts.append(unit.text[position:start])
                    position = max(position, stop)
            texts.append(unit.text[position:end])
    return [text for text in texts if text.strip()]


def foreign_technologies(proposal, allocations, sources, types, entry=None, others=()):
    """The resolved fields of the technologies entries own that no line of their entry names in any form: as written,
    by a catalog alias, or with other spaces or punctuation. A value read from the editor's cells stays with the model.

    The lines of an entry are the lines its record's values other than technologies cite and the text between the first
    and the last of them: a project cites its employer and job title above its entry (D155), and what its job states
    between them is the project's too. When the block runs entry by entry (D117), add the entry's own lines and leave
    out the lines of the block's other entries (others); else add the lines its record's technologies cite, as a stack
    line is cited by the names it holds."""
    by_handle = {allocation.item_handle: allocation for allocation in allocations}
    owners = {relation.subject_id: relation.target_id for relation in proposal.resolved_relations
        if relation.kind in {'owned_by', 'extension_of'}}
    def stack(field):
        return by_handle[field.item_handle].semantic_type in types
    records = {}
    for field in proposal.resolved_fields:
        if field.item_handle in by_handle:
            identifier = by_handle[field.item_handle].record_id
            records.setdefault(owners.get(identifier, identifier), []).append(field)
    found, lines = [], {}
    for record, family in records.items():
        for field in family:
            value = payload_value(proposal.reply.payload, field.pointer)
            if (not stack(field) or not isinstance(value, str) or not value.strip() or field.effective_cell_ids
                    or by_handle[field.item_handle].record_id not in owners):
                continue
            if record not in lines:
                cited = [span for other in family if not stack(other) for span in other.evidence]
                own = entry if entry is not None else [span for other in family if stack(other)
                    for span in other.evidence]
                lines[record] = [*_stretch(sources, cited, others),
                    *[source_slice(sources, span) for span in [*cited, *own]]]
            if not named(value, lines[record]) and source_spelling(value, lines[record]) is None:
                found.append(field)
    return found
