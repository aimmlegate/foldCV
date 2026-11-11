"""The technologies an entry owns, read against the entry's lines (point 14 of T4, D164; D165 and its follow-up).

The model sometimes writes a project technology the source does not name as written: it expands an abbreviation the
source states (TCA (Composable Architecture) where the CV says TCA), changes the dash of a version range, fixes a typo
of the CV or names a tool the entry never states. A name the entry's lines state as written, case and spacing aside, or
by an alias the catalog gives it, passes, and so do the other forms `verdict` names. One they write with other spaces
or punctuation, as a contraction, or without the qualifier or version the reply added takes their wording when the
reply is completed (template_completion). Any other leaves the reply as a value no source line states does (I4) and is
named in the block's notice; no model repair runs for it.
"""

from dataclasses import dataclass, field
import re

from ..technologies import BY_ID, resolve_technology, split_version
from ..templates.projection import pointer_tokens
from ..templates.source_spans import _bound_root, payload_value
from .template_identity import _binding_instances

# The catalog leaves these unresolved, as common words of free text; a technologies item names the one technology.
AMBIGUOUS = {'go': 'golang', 'node': 'nodejs', 'drf': 'djangorest'}
# Signs a name may hold or leave out between its letters (Win Forms, Node.js, CI/CD, 4–5); a comma, a semicolon or a
# line break ends a name.
JOINING = re.compile(r'[^\S\r\n]|[-.\\/_+#&\'’()\[\]‐-―−]')
# Cyrillic letters that look like Latin ones are the same text (D163): 1С and 1C are one name.
LOOKALIKE = str.maketrans('авсенкмортху', 'abcehkmoptxy')
# The version a name ends with: digits with dots, a range with any dash, a leading v, .x or a plus (Go 1.6–1.7, 8+).
VERSION = re.compile(r'\s+(?:v\s?)?\d+(?:\.\d+)*(?:\.x)?(?:\s*[-‐-―−]\s*(?:v\s?)?\d+(?:\.\d+)*(?:\.x)?)?\+?$', re.I)
# What a line may write as a contraction: letters and digits joined by the signs of VB.NET or C#, without a space or a
# slash (A/B names two things).
CONTRACTED = re.compile(r'[^\W_]+(?:[.#+&][^\W_]+)*')
# A shorter name with one letter changed is too often another name (Kafka, Kafra).
TYPO_LETTERS = 6


def owned_types(fact_types):
    """The fact types of the technologies an entry owns: a job's or project's stack, not a skills list."""
    return frozenset(value.id for value in fact_types if value.builtin_kind == 'technology'
        and any(relation.kind == 'owned_by' for relation in value.relations))


def _folded(text):
    return ' '.join(text.split()).casefold()


def _aliases(name):
    """The catalog's names of the technology a name resolves to, its version aside; empty for an unknown name."""
    identifier = resolve_technology(name).canonical_id or AMBIGUOUS.get(split_version(name)[0])
    if identifier is None:
        return []
    return [*BY_ID[identifier].aliases, *[word for word, target in AMBIGUOUS.items() if target == identifier]]


def named(name, texts):
    """Whether lines name a technology: as written, case and spacing aside, a version may follow it (Python3, C++17);
    or by an alias the catalog gives it, with the version the name states."""
    value, lines = _folded(name), '\n'.join(_folded(text) for text in texts)
    if re.search(r'(?<![^\W_])' + re.escape(value) + r'(?![^\W\d_])', lines):
        return True
    version = split_version(name)[1]
    return (any(re.search(r'(?<![\w.+#])' + re.escape(alias) + r'(?![\w+#])', lines) for alias in _aliases(name))
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


def _flat(text):
    """A line's letters and digits as one key; starts and ends map their offsets back to the line."""
    flat, starts, ends = [], {}, {}
    for index, char in enumerate(text):
        if char.isalnum():
            starts[len(flat)] = index
            flat.extend(_letter(char))
            ends[len(flat)] = index + 1
    return ''.join(flat), starts, ends


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
        flat, starts, ends = _flat(text)
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


def _words(text):
    """The words and version numbers of a text, a v before a number left out: v12 and 12 are one."""
    text = re.sub(r'(?<![^\W\d_])v(?=\d)', '', text, flags=re.I)
    return {word.casefold() for word in re.findall(r'\d+(?:\.\d+)*|[^\W\d_]+', text)}


def _written(name, text):
    """The text a line names a name with, case and spacing aside; None when it does not."""
    pattern = r'\s+'.join(re.escape(part) for part in name.split())
    match = re.search(r'(?<![^\W_])' + pattern + r'(?![^\W\d_])', text, re.I) if pattern else None
    return match.group() if match else None


def _aliased(name, text):
    """The text a line names a name's technology with, by an alias the catalog gives it."""
    for alias in _aliases(name):
        match = re.search(r'(?<![\w.+#])' + r'\s+'.join(re.escape(part) for part in alias.split()) + r'(?![\w+#])',
            text, re.I)
        if match:
            return match.group()
    return None


def _near(one, other):
    """Keys of one length with one letter changed or two neighbouring letters swapped; digits never change."""
    differ = [index for index, (left, right) in enumerate(zip(one, other)) if left != right]
    if len(differ) == 1:
        return one[differ[0]].isalpha() and other[differ[0]].isalpha()
    return (len(differ) == 2 and differ[1] == differ[0] + 1 and one[differ[0]] == other[differ[1]]
        and one[differ[1]] == other[differ[0]] and one[differ[0]].isalpha() and one[differ[1]].isalpha())


def _misspelled(name, text):
    """The text a line writes a name with one letter changed or two neighbouring letters swapped, for a name of at least
    TYPO_LETTERS letters with the same first letter: the model wrote the accepted spelling of the CV's typo."""
    key = ''.join(_letter(char) for char in name if char.isalnum())
    if sum(char.isalpha() for char in key) < TYPO_LETTERS or not key[0].isalpha():
        return None
    flat, starts, ends = _flat(text)
    for at in range(len(flat) - len(key) + 1):
        window = flat[at:at + len(key)]
        if window[0] != key[0] or not _near(window, key):
            continue
        first, last = starts.get(at), ends.get(at + len(key))
        if (first is not None and last is not None and _joined(text[first:last]) and not _word(text, first - 1)
                and not _word(text, last)):
            return text[first:last]
    return None


def _parts(token):
    """A written name split at case changes and signs: WinForms is Win and Forms, VB.NET is V, B, N, E and T."""
    parts = []
    for char in token:
        if not char.isalnum():
            parts.append('')
            continue
        last = parts[-1][-1:] if parts else ''
        if not last or char.isupper() or char.isdigit() != last.isdigit():
            parts.append(char)
        else:
            parts[-1] += char
    return [_letter(part) for part in parts if part]


def _starts(parts, words):
    """Whether groups of the parts in order start the words in order, every part and every word used."""
    if not parts or not words:
        return not parts and not words
    return any(words[0].startswith(''.join(parts[:size])) and _starts(parts[size:], words[1:])
        for size in range(1, len(parts) + 1))


def _contraction(name, text):
    """The name a line writes as a contraction of a name of two or more words (VB.NET for Visual Basic .NET, WinForms
    for Windows Forms)."""
    words = [_letter(word) for word in re.findall(r'[^\W_]+', name)]
    if len(words) < 2:
        return None
    for match in CONTRACTED.finditer(text):
        parts = _parts(match.group())
        if 2 <= len(parts) <= 16 and _starts(parts, words):
            return match.group()
    return None


def _synonym(name, text):
    """The text a line names a name with when the name starts with a catalog name and the line writes another alias of
    it before the same other words (MS SQL Compact for SQL Server Compact)."""
    words = name.split()
    for size in range(len(words) - 1, 0, -1):
        head, tail = ' '.join(words[:size]), ' '.join(words[size:])
        aliases = _aliases(head)
        if aliases:
            return next((found for alias in aliases if (found := _written(alias + ' ' + tail, text)
                or source_spelling(alias + ' ' + tail, [text]))), None)
    return None


def _qualified(name):
    """(base, rest) of a name with a version or a bracketed qualifier after its base: (TCA, (Composable Architecture)),
    (Next.js, 12 (Pages Router)); None without either."""
    cut = min([index for index in (name.find('('), name.find('[')) if index > 0] or [len(name)])
    base, rest = name[:cut].rstrip(), name[cut:]
    version = VERSION.search(base)
    if version:
        base, rest = base[:version.start()], base[version.start():] + rest
    base = base.strip()
    if not _words(rest) or not any(char.isalpha() for char in base):
        return None
    return base, rest


def _base(name, text):
    """(the text the line names a base with, whether the reply's base stays): the line's own wording replaces it, an
    alias, a catalog synonym or a typo of the CV keeps the reply's."""
    for find, keeps in ((_written, False), (lambda value, line: source_spelling(value, [line]), False),
            (_contraction, False), (_aliased, True), (_synonym, True), (_misspelled, True)):
        found = find(name, text)
        if found:
            return found, keeps
    return None


def _rows(runs):
    """The lines of runs of lines in a row, and those lines with each two in a row read as one, joined by a space."""
    lines, pairs = [], []
    for run in runs:
        previous = None
        for line in run.split('\n'):
            if not line.strip():
                previous = None
                continue
            lines.append(line)
            if previous is not None:
                pairs.append(previous + ' ' + line)
            previous = line
    return lines, [*lines, *pairs]


def verdict(name, runs):
    """How the lines of an entry (runs of lines in a row) read a technology. None when they name it: as written or by
    alias (also across a line break), by a catalog synonym, with a typo of the CV the name fixes, or as its base with
    every word of its version and qualifier in the same line (Ruby 2.7–3.1 for RUBY (MRI) 2.7-3.1). (value, fragment)
    when it takes their wording, cited by the fragment: their other spaces or punctuation, their contraction, or its
    base as a line writes it without the qualifier or version the reply added. False when they name it in no form."""
    name = ' '.join(name.split())
    lines, rows = _rows(runs)
    if named(name, rows):
        return None
    spelled = source_spelling(name, lines)
    if spelled is not None:
        return spelled, spelled
    if any(_misspelled(name, row) or _synonym(name, row) for row in rows):
        return None
    split = _qualified(name)
    if split and any(_base(split[0], row) and _words(split[1]) <= _words(row) for row in rows):
        return None
    for line in lines:
        token = _contraction(name, line)
        if token:
            return token, token
    for line in lines if split else ():
        found = _base(split[0], line)
        if found:
            return (split[0] if found[1] else found[0]), found[0]
    return False


def entry_runs(sources, cited, own, others=()):
    """The text of an entry's lines as runs of lines in a row: the cited spans and the source text between the first and
    the last of them without the spans of others, and the own spans. A run goes on across units, so a name the source
    layout wrapped reads as one line."""
    runs = []
    for source in sources:
        units = sorted(source.units, key=lambda value: value.order)
        index = {(unit.id, unit.revision): position for position, unit in enumerate(units)}
        def place(span, source=source, index=index):
            return index.get((span.unit_id, span.unit_revision)) if (span.source_id, span.source_revision) == (
                source.id, source.revision) else None
        ranges = {}
        held = [(place(span), span) for span in cited if place(span) is not None]
        if held:
            low = min((position, span.start) for position, span in held)
            high = max((position, span.end) for position, span in held)
            for position in range(low[0], high[0] + 1):
                start = low[1] if position == low[0] else 0
                end = high[1] if position == high[0] else len(units[position].text)
                for cut, stop in sorted((span.start, span.end) for span in others if place(span) == position):
                    if cut < end and stop > start:
                        ranges.setdefault(position, []).append((start, cut))
                        start = max(start, stop)
                ranges.setdefault(position, []).append((start, end))
        for span in [*cited, *own]:
            if place(span) is not None:
                ranges.setdefault(place(span), []).append((span.start, span.end))
        run, last = None, None
        for position in sorted(ranges):
            text, merged = units[position].text, []
            for start, end in sorted(ranges[position]):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                elif start < end:
                    merged.append([start, end])
            for start, end in merged:
                if not text[start:end].strip():
                    continue
                if run is not None and last[0] == position and not text[last[1]:start].strip():
                    run += text[last[1]:end]
                elif (run is not None and last[0] == position - 1 and not units[last[0]].text[last[1]:].strip()
                        and not text[:start].strip()):
                    run += '\n' + text[start:end]
                else:
                    if run is not None:
                        runs.append(run)
                    run = text[start:end]
                last = (position, end)
        if run is not None:
            runs.append(run)
    return runs


@dataclass
class EntryLines:
    """What a reply's technologies are read against: their semantic types, the captured sources, the entry task's own
    lines (None for a block run whole) and the lines of the block's other entries. dropped collects, as {pointer,
    fieldKey, text}, the technologies no line of their entry names in any form."""
    types: frozenset
    sources: list
    entry: list | None = None
    others: list = field(default_factory=list)
    dropped: list = field(default_factory=list)


def _record(pointer, semantic, key, bindings):
    """The root of the record a bound value belongs to: the item its binding's relation names (a job's technology,
    project and claims), else its own item."""
    actual = pointer_tokens(pointer)
    for binding in bindings:
        pattern = pointer_tokens(binding.pointer)
        if (binding.semantic_type == semantic and binding.field == key and binding.relation is not None
                and len(pattern) == len(actual) and all(expected in {'*', value} for expected, value in zip(pattern, actual))):
            return tuple(actual[index] if token == '*' and index < len(actual) else token
                for index, token in enumerate(pointer_tokens(binding.relation.subject_pointer)))
    return tuple(_bound_root(pointer, semantic, key, bindings))


def verdicts(reply, bindings, table, lines):
    """{pointer: (field key, verdict, anchors)} of the technologies of a completed reply that the lines of their entry
    do not name as they are; anchors are the refs the value cites, else those its record cites. A value read from the
    editor's cells stays as it is. Every bound value counts, a value the reply left uncited too.

    The lines of an entry (P14, D165) are the lines its record's values other than technologies cite and the text between
    the first and the last of them: a project cites its employer and job title above its entry (D155), and what its job
    states between them is the project's too. When the block runs entry by entry (D117), add the entry's own lines and
    leave out the lines of the block's other entries; else add the lines its record's technologies cite, as a stack line
    is cited by the names it holds."""
    payload = reply.get('payload')
    given = {}
    for entry in reply.get('fields') or []:
        if isinstance(entry, dict) and isinstance(entry.get('pointer'), str):
            given.setdefault(entry['pointer'], []).append(entry)
    def refs(values):
        return [ref for pointer, _semantic, _key in values for entry in given.get(pointer, [])
            for ref in entry.get('evidence') or [] if ref in table]
    records = {}
    for value in sorted(_binding_instances(payload, bindings)):
        records.setdefault(_record(*value, bindings), []).append(value)
    found = {}
    for family in records.values():
        stacks = [value for value in family if value[1] in lines.types]
        runs = cited = None
        for pointer, _semantic, key in stacks:
            text = payload_value(payload, pointer)
            if (not isinstance(text, str) or not text.strip()
                    or any(entry.get('effectiveCells') for entry in given.get(pointer, []))):
                continue
            if runs is None:
                cited = refs([value for value in family if value[1] not in lines.types])
                own = lines.entry if lines.entry is not None else [table[ref].span for ref in refs(stacks)]
                runs = entry_runs(lines.sources, [table[ref].span for ref in cited], own, lines.others)
            reading = verdict(text, runs)
            if reading is not None:
                found[pointer] = (key, reading, refs([(pointer, None, None)]) or cited)
    return found


def _bound_type(pointer, key, bindings):
    tokens = pointer_tokens(pointer)
    return next((binding.semantic_type for binding in bindings if binding.field == key
        and len(pattern := pointer_tokens(binding.pointer)) == len(tokens)
        and all(expected in {'*', actual} for expected, actual in zip(pattern, tokens))), None)


def carried(earlier, dropped, reply, bindings, types):
    """The technologies an earlier reply of the task lost (earlier, its dropped values) that this reply neither lost
    too (dropped) nor states: a repair keeps them, so the block's notice still names them."""
    payload = reply.get('payload')
    named_texts = {_folded(value.text) for value in dropped}
    named_texts |= {_folded(value) for pointer, semantic, _key in _binding_instances(payload, bindings)
        if semantic in types and isinstance(value := payload_value(payload, pointer), str)}
    kept = []
    for value in earlier:
        if _bound_type(value.pointer, value.field_key, bindings) in types and _folded(value.text) not in named_texts:
            kept.append(value)
            named_texts.add(_folded(value.text))
    return kept
