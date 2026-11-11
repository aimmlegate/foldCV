"""The map of a CV (T4 of D158).

One call reads the whole CV before any block and names the lines of each block, the entries of each block extracted
entry by entry with each entry's employer, job title and period, and the lines that hold no content of any block. The
coordinator checks the map before a block starts: every ref is an offered line and no range runs backwards, the
entries of a block share no line, every header value stands on its line (else on the line that states it, else it is
dropped), and every line of a block of entries is in an entry, is a header value's line or holds no content. Lines
left out of every entry get one repair. A map that stays doubted is not used: the import reads the whole CV as before.

The map's result names lines by the refs of its own captured request; every block's request offers its lines under
the same refs.
"""

import re

from ..models.template_import import MapRepairReply, MapReply
from ..sources import capture_span, line_spans
from ..templates.compiler import splits_entries
from ..templates.replies import MAP_PROTOCOL, MAP_REPAIR_PROTOCOL
from ..template_source_cleanup import without_contacts
from .template_entries import _bounds, line_options
from .template_identity import evidence_options, offered_evidence

HEADERS = ('employer', 'jobTitle', 'period')


def mapped_blocks(definition):
    """The blocks the map names lines for: model blocks that read the source, of every branch."""
    return [block for block in definition.blocks if block.mode == 'model' and any(ref.kind == 'source' for ref in block.selectors)]


def _title(definition, block):
    title = block.view.title
    return title.get(definition.template.default_locale) or next(iter(title.values()), None)


def whole_source(sources):
    """Every unit and each line of a multi-line unit, as a block that reads the whole CV is offered them."""
    return [span for source in sources for unit in source.units for span in [capture_span(source, unit), *line_spans(source, unit)]]


def map_input(operation, data):
    """The map task's request: the whole CV, the blocks by id, title and first extract rule, the blocks of entries with
    all their rules, and the template's general extract rules."""
    definition = data.template_package.definition
    blocks = mapped_blocks(definition)
    return {'protocol': 'template_import_v1', 'tools': [], 'replyProtocol': MAP_PROTOCOL,
        'packageHash': data.template_package.package_hash, 'allowTextRewrite': operation.capture.allow_text_rewrite,
        'modelInstructions': {'extract': list(definition.model.extract)},
        'evidence': [option.model_dump(mode='json', by_alias=True) for option in evidence_options(whole_source(data.sources), data.sources)],
        'blocks': [{'block': block.id, 'title': _title(definition, block), 'extract': list(block.extract[:1])} for block in blocks],
        'entryBlocks': [{'block': block.id, 'extract': list(block.extract)} for block in blocks if splits_entries(block)]}


def map_choices(request):
    """The block ids a map reply may name, and those of blocks of entries."""
    return [value['block'] for value in request['blocks']], [value['block'] for value in request['entryBlocks']]


class Lines:
    """The offered lines of a captured map request in CV order."""

    def __init__(self, offered, sources):
        self.offered, self.sources = offered, sources
        self.lines = line_options(offered, sources)
        self.index = {option.ref: position for position, option in enumerate(self.lines)}

    def bounds(self, ref):
        """The first and last line a ref stands for: its line, or the lines of a whole unit."""
        try:
            return _bounds(ref, self.offered, self.lines, self.sources)
        except ValueError:
            raise ValueError('map names no offered line: ' + str(ref)) from None

    def run(self, first, last):
        """The refs from the first line of `first` to the last line of `last`; a run backwards is refused."""
        start, end = self.bounds(first)[0], self.bounds(last)[1]
        if start > end:
            raise ValueError('map range runs backwards: ' + first + '–' + last)
        return [self.lines[position].ref for position in range(start, end + 1)]

    def ranges(self, values):
        refs = set()
        for value in values:
            refs.update(self.run(value.first, value.last))
        return self.ordered(refs)

    def ordered(self, refs):
        return sorted(set(refs), key=self.index.__getitem__)

    def text(self, ref):
        return self.lines[self.index[ref]].text


def _pattern(value):
    """A search for the value word for word: case, spacing, dashes and quote marks aside."""
    parts = []
    for character in ' '.join(value.split()):
        if character == ' ':
            parts.append(r'\s+')
        elif character in '-‐‑‒–—―':
            parts.append('[-‐‑‒–—―]')
        elif character in '"«»“”„\'':
            parts.append('["«»“”„\']')
        else:
            parts.append(re.escape(character))
    return re.compile(r'(?<!\w)' + ''.join(parts) + r'(?!\w)', re.IGNORECASE)


def stated(value, text):
    """The value as the text writes it, spaces joined; None when the text does not state it."""
    found = _pattern(value).search(text)
    return ' '.join(found.group(0).split()) if found else None


def checked_header(value, lines, near):
    """A header value checked on its line (T4, point 3): kept when its line states it, moved to the nearest line that
    states it otherwise, else dropped; a ref that is no offered line refuses the map. Returns ({value, line} or None,
    the dropped value or None); the value is the line's own wording."""
    if value is None:
        return None, None
    start, end = lines.bounds(value.line)
    candidates = [lines.lines[position].ref for position in range(start, end + 1)]
    for ref in candidates:
        own = stated(value.value, lines.text(ref))
        if own is not None:
            return {'value': own, 'line': ref}, None
    others = sorted((ref for ref in lines.index if ref not in candidates), key=lambda ref: abs(lines.index[ref] - near))
    for ref in others:
        own = stated(value.value, lines.text(ref))
        if own is not None:
            return {'value': own, 'line': ref}, None
    return None, ' '.join(value.value.split())


def _header(entry, lines, near):
    header, dropped = {}, []
    for key in HEADERS:
        header[key], lost = checked_header(getattr(entry, key if key != 'jobTitle' else 'job_title'), lines, near)
        if lost is not None:
            dropped.append(lost)
    return header, dropped


def header_lines(value):
    return {header['line'] for entry in value['entries'] for header in entry['header'].values() if header is not None}


def uncovered(value):
    """The lines of each block of entries that no entry holds, no header value stands on and the map does not name as
    holding no content (T4, point 4)."""
    held = {ref for entry in value['entries'] for ref in entry['lines']} | header_lines(value) | set(value['hidden'])
    result = {}
    for block in value['entryBlocks']:
        left = [ref for ref in value['blocks'].get(block, []) if ref not in held]
        if left:
            result[block] = left
    return result


def unused(value, lines):
    """Lines no block reads and the map does not name as holding no content; a line of contacts alone is none either."""
    read = {ref for refs in value['blocks'].values() for ref in refs} | {ref for entry in value['entries'] for ref in entry['lines']}
    read |= header_lines(value) | set(value['hidden'])
    return [ref for ref in lines.index if ref not in read and without_contacts(lines.text(ref)).strip()]


def parse_map(payload, offered, sources, request):
    """The checked map of a reply, or ValueError when it cannot be used: a ref that is no offered line, a range that runs
    backwards or entries of one block that share a line. Header values are checked on their lines; lines a block of
    entries leaves out are named in `uncovered`, for the repair."""
    reply = MapReply.model_validate(payload, strict=True)
    names, entry_names = map_choices(request)
    lines = Lines(offered, sources)
    blocks = {}
    for block in reply.blocks:
        if block.block not in names:
            raise ValueError('map names an unknown block')
        blocks[block.block] = lines.ordered([*blocks.get(block.block, []), *lines.ranges(block.ranges)])
    entries, taken = [], {}
    for entry in reply.entries:
        if entry.block not in entry_names:
            raise ValueError('map names entries of a block that has none')
        refs = lines.run(entry.first, entry.last)
        held = taken.setdefault(entry.block, set())
        if held & set(refs):
            raise ValueError('map entries share a line')
        held.update(refs)
        header, dropped = _header(entry, lines, lines.index[refs[0]])
        entries.append({'block': entry.block, 'title': ' '.join(entry.title.split()), 'lines': refs, 'header': header,
            **({'dropped': dropped} if dropped else {})})
        # A block of entries holds every line of its entries.
        blocks[entry.block] = lines.ordered([*blocks.get(entry.block, []), *refs])
    value = {'blocks': blocks, 'entries': entries, 'entryBlocks': entry_names, 'hidden': lines.ranges(reply.hidden),
        'repaired': False}
    value['uncovered'] = uncovered(value)
    value['unused'] = unused(value, lines)
    return value


def map_repair_input(stored, value, offered, sources):
    """The one repair of a map whose entries leave lines out: the lines of the blocks of entries and their header lines,
    the map's entries by number and the lines no entry holds."""
    lines = Lines(offered, sources)
    left = {ref for refs in value['uncovered'].values() for ref in refs}
    shown = set(left) | header_lines(value) | {ref for block in value['entryBlocks'] for ref in value['blocks'].get(block, [])}
    entries = [{'index': number, 'block': entry['block'], 'title': entry['title'], 'first': entry['lines'][0],
        'last': entry['lines'][-1], **{key: entry['header'][key] for key in HEADERS}} for number, entry in enumerate(value['entries'], 1)]
    return {**{key: part for key, part in stored.items() if key != 'blocks'}, 'slot': 'map_repair',
        'replyProtocol': MAP_REPAIR_PROTOCOL,
        'evidence': [option.model_dump(mode='json', by_alias=True) for option in offered.values() if option.ref in shown],
        'map': {'entries': entries}, 'uncovered': lines.ordered(left)}


def _placed(entries, entry, lines):
    """The index a new entry takes among the entries of its block: by its first line when they follow the CV's order
    or its reverse, else after them (as D117 places an entry its review adds)."""
    first = lambda value: lines.index[value['lines'][0]]
    own = [position for position, other in enumerate(entries) if other['block'] == entry['block']]
    places = [first(entries[position]) for position in own]
    ascending = all(left < right for left, right in zip(places, places[1:]))
    descending = all(left > right for left, right in zip(places, places[1:]))
    if not own or not (ascending or descending):
        return own[-1] + 1 if own else len(entries)
    for position in own:
        if (first(entries[position]) > first(entry)) == ascending:
            return position
    return own[-1] + 1


def apply_repair(value, payload, offered, sources):
    """The map with the repair's answer: each line it places joins its entry, a new entry is placed among its block's
    entries, a line of no entry holds no content. ValueError when the answer names no such entry or lines stay out."""
    reply = MapRepairReply.model_validate(payload, strict=True)
    lines = Lines(offered, sources)
    left = {ref: block for block, refs in value['uncovered'].items() for ref in refs}
    count = len(value['entries'])
    entries = [{**entry, 'lines': list(entry['lines'])} for entry in value['entries']]
    added = [{'title': ' '.join(entry.title.split()), 'lines': [], 'source': entry} for entry in reply.entries]
    hidden = list(value['hidden'])
    for answer in reply.lines:
        if answer.line not in offered:
            raise ValueError('map repair names an unoffered line')
        if answer.line not in left:
            continue
        if answer.entry is None:
            hidden.append(answer.line)
        elif answer.entry <= count:
            target = entries[answer.entry - 1]
            if target['block'] != left[answer.line]:
                raise ValueError('map repair moves a line into another block')
            target['lines'] = lines.ordered([*target['lines'], answer.line])
        elif answer.entry <= count + len(added):
            added[answer.entry - count - 1]['lines'].append(answer.line)
        else:
            raise ValueError('map repair names no entry')
    for entry in added:
        if not entry['lines']:
            continue
        blocks = {left[ref] for ref in entry['lines']}
        if len(blocks) != 1:
            raise ValueError('map repair joins lines of two blocks into one entry')
        refs = lines.ordered(entry['lines'])
        header, dropped = _header(entry['source'], lines, lines.index[refs[0]])
        new = {'block': next(iter(blocks)), 'title': entry['title'], 'lines': refs, 'header': header,
            **({'dropped': dropped} if dropped else {})}
        entries.insert(_placed(entries, new, lines), new)
    result = {**value, 'entries': entries, 'hidden': lines.ordered(hidden), 'repaired': True}
    result['uncovered'] = uncovered(result)
    if result['uncovered']:
        raise ValueError('map repair leaves lines of a block of entries out')
    result['unused'] = unused(result, lines)
    return result


def map_task(operation):
    return next((task for task in operation.tasks if task.kind == 'map'), None)


def source_map(operation):
    """The usable map of an import and its captured request's offered lines: (value, offered), or None when the import
    has no map task (started before T4), its map is not done yet or could not be used."""
    task = map_task(operation)
    result = next((value for value in operation.task_results if task is not None and value.task_id == task.id), None)
    if result is None or result.disposition != 'derived':
        return None
    stored = next(value.value for value in operation.task_inputs if value.task_id == task.id)
    return result.value, offered_evidence(stored)

