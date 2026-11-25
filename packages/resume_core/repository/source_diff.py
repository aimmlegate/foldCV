"""The present document against the original, both ways (a trial of the look).

Every fact field the document shows is compared with the source lines its value rests on. The words of the shown text
that those lines do not state are the field's additions, marked only while a model wrote the value (D179): text the
user typed or accepted is not marked. The words of those lines that the document shows nowhere are the lines'
removals, and so are the lines of a fact the template shows and the page does not (a removed card or bullet). A value
with no source lines has no original to compare with and is left out; a date, which code writes in the document's own
form, is no addition. Lines no fact rests on are not seen here: the import's own notices carry the lines it left out.
Nothing here writes the project."""

import json
import re

from ..editing.template_preparation_text import _fields
from ..fields import field_key, inline_groups, working_field
from ..importing.lite.words import line_words, words
from .assistant_compiler import find_record

TOKEN = re.compile(r'[^\W_]+')


def fold(word):
    return word.casefold().replace('ё', 'е')


def stated_words(lines):
    """The words lines state, and each two neighbours as one word (a word set apart otherwise is the same word)."""
    stated = set()
    for line in lines:
        tokens = [fold(word) for word in TOKEN.findall(line)]
        stated.update(tokens)
        stated.update(left + right for left, right in zip(tokens, tokens[1:]))
    return stated


def beyond(text, lines, stated=None):
    """The words of text that no line states, each once, in order, as text writes them. Case, punctuation and the
    way a word is set apart are form: «Node.js» states «nodejs», «WinForms» states «Win Forms». stated: the words of
    the lines when the caller has them."""
    stated = stated_words(lines) if stated is None else stated
    tokens = TOKEN.findall(text)
    keys = [fold(word) for word in tokens]
    found, seen = [], set()
    for index, (word, key) in enumerate(zip(tokens, keys)):
        joined = (index and keys[index - 1] + key in stated) or (index + 1 < len(keys) and key + keys[index + 1] in stated)
        if key not in stated and not joined and key not in seen:
            seen.add(key)
            found.append(word)
    return found


def source_lines(project, record, extension, key, units=None):
    """The text of every source span a value rests on."""
    if units is None:
        units = {unit.id: unit.text for source in project.sources for unit in source.units}
    if extension:
        cell = next((value for value in record.cells if value.field_key == key), None)
        spans = cell.evidence if cell is not None else []
    else:
        spans = record.evidence
    lines = []
    for span in spans:
        text = getattr(span, 'text', None)
        if text is None:
            whole = units.get(span.unit_id)
            if whole is None or span.end > len(whole):
                continue
            # A span counts code points, as sources.source_slice reads it.
            text = whole[span.start:span.end]
        lines.append(str(text))
    return lines


def shown_fields(workspace):
    """Each fact field the document shows, once: (its cell id as the editor has it, field key, its shown text, its
    source lines, its record)."""
    project = workspace.project
    if project is None:
        return
    units = {unit.id: unit.text for source in project.sources for unit in source.units}
    seen = set()
    for block in project.document.blocks():
        for _key, content in inline_groups(block):
            for span, _start, _end in _fields(content):
                record_id, key = getattr(span, 'record_id', None), getattr(span, 'field_key', None)
                text = getattr(span, 'text', '')
                if record_id is None or key is None or (record_id, key, text) in seen:
                    continue
                seen.add((record_id, key, text))
                record, extension = find_record(workspace, record_id)
                # The editor names a field by its span's cell id (an extension's cell has an id of its own).
                yield (getattr(span, 'cell_id', None) or field_key(record_id, key), key, text,
                       source_lines(project, record, extension, key, units) if record is not None else [], record)


def written_by_model(project, record, cell):
    """Whether a model gave the cell its present value and no person wrote it since (D179): the import's value until
    the user types in it or accepts it, and a value an Apply took unchanged from a preview. A fact the user made is
    the user's."""
    if cell in project.facts.model_written:
        return True
    if record is None:
        return False
    if hasattr(record, 'cells'):
        value = next((value for value in record.cells if value.id == cell), None)
        return value is not None and value.origin != 'human'
    key = json.loads(cell)[2] if cell.startswith('["fact"') else None
    value = working_field(record, key) if key is not None else None
    return record.origin == 'source' and value is not None and not value.user_corrected


def additions(workspace):
    """{cell id: the words its shown text has and its source lines lack}, for the fields that have such words and that
    a model wrote (`written_by_model`): text the user typed or accepted is not marked."""
    found, whole = {}, None
    for cell, key, text, lines, record in shown_fields(workspace):
        # A date is written by code in the document's form (03.2021), whatever the line's own form.
        if key.startswith('period:') or not lines or not any(char.isalpha() for char in text) \
                or not written_by_model(workspace.project, record, cell):
            continue
        if getattr(record, 'kind', None) == 'technology' and key == 'display':
            # A technology is one fact for the whole CV and keeps only a few of the lines that name it: its name is
            # compared with the whole original.
            if whole is None:
                whole = stated_words(unit.text for source in workspace.project.sources for unit in source.units)
            words_beyond = beyond(text, (), whole)
        else:
            words_beyond = beyond(text, lines)
        for word in words_beyond:
            if word not in found.setdefault(cell, []):
                found[cell].append(word)
    return {cell: found[cell] for cell in found if found[cell]}


def record_lines(project, record, units):
    """The text of every source span a record rests on: a builtin record's own, an extension's cells'."""
    if hasattr(record, 'cells'):
        return [line for cell in record.cells for line in source_lines(project, record, True, cell.field_key, units)]
    return source_lines(project, record, False, None, units)


def removals(workspace):
    """The source lines of the facts the document showed with the words it shows nowhere, as rows {text, words,
    reason}; words is None when the document shows no word of the line, or when the line is a fact's off the page
and no shown value rests on it. A word counts as the import counts it (three
    letters or a number; a period's month names and a label before a value are form). reason: `removed` for a line of
    a record off the page (D179) or of a card that lost a field line, `changed` for a line of a shown value."""
    from ..editing.off_page import named_records, off_fields, off_page
    project = workspace.project
    fields = list(shown_fields(workspace))
    shown = set().union(*(words(text) for _id, _key, text, _lines, _record in fields)) if fields else set()
    rows, seen = [], set()
    units = {unit.id: unit.text for source in project.sources for unit in source.units} if project is not None else {}
    gone = set()
    if project is not None:
        records = {record.id: record for record in [*project.facts.records, *project.facts.extensions]}
        order = {identifier: index for index, identifier in enumerate(records)}
        lost_lines = [line for identifier in sorted(off_page(project), key=lambda identifier: order[identifier])
            for line in record_lines(project, records[identifier], units)]
        # D181: an item that a list written again removed keeps its record, inactive, with its evidence; its lines are
        # red as removed until Undo makes the record active again.
        from .block_write import LIST_BLOCKS
        lost_lines += [line for record in project.facts.extensions
            if not record.active and record.semantic_type.split(':')[-1] in LIST_BLOCKS
            for line in record_lines(project, record, units)]
        cut = set(off_fields(project, named_records(project.document)))
        gone = {' '.join(line.split()) for line in lost_lines}
        gone |= {' '.join(line.split()) for identifier in cut for line in record_lines(project, records[identifier], units)}
    else:
        lost_lines = []

    def add(line, whole=False):
        line = ' '.join(line.split())
        if line in seen:
            return
        seen.add(line)
        need = line_words(line)
        missing = need if whole else need - shown
        if missing:
            rows.append({'text': line, 'words': sorted(missing) if need & shown and not whole else None,
                'reason': 'removed' if line in gone else 'changed'})
    for _id, _key, _text, lines, _record in fields:
        for line in lines:
            add(line)
    # A line of a fact off the page that no shown value rests on is red whole (G5): words the page shows on other
    # lines (a city, a year) do not keep a part of it.
    for line in lost_lines:
        add(line, whole=True)
    return rows
