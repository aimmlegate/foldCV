"""The present document against the original, both ways (a trial of the look).

Every fact field the document shows is compared with the source lines its value rests on. The words of the shown text
that those lines do not state are the field's additions. The words of those lines that the document shows nowhere are
the lines' removals. It holds for any field and any way the text came to differ (a form the import gave a value, a
rewording, the user's own typing). A value with no source lines has no original to compare with and is left out; a
date, which code writes in the document's own form, is no addition. A line no shown value rests on is not seen here:
the import's own notices carry the lines it left out. Nothing here writes the project."""

import re

from ..editing.template_preparation_text import _fields
from ..fields import field_key, inline_groups
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


def additions(workspace):
    """{cell id: the words its shown text has and its source lines lack}, for the fields that have such words."""
    found, whole = {}, None
    for cell, key, text, lines, record in shown_fields(workspace):
        # A date is written by code in the document's form (03.2021), whatever the line's own form.
        if key.startswith('period:') or not lines or not any(char.isalpha() for char in text):
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


def removals(workspace):
    """The source lines of shown values with the words the document shows nowhere, as rows {text, words}; words is
    None when the document shows no word of the line. A word counts as the import counts it (three letters or a
    number; a period's month names and a label before a value are form)."""
    fields = list(shown_fields(workspace))
    shown = set().union(*(words(text) for _id, _key, text, _lines, _record in fields)) if fields else set()
    rows, seen = [], set()
    for _id, _key, _text, lines, _record in fields:
        for line in lines:
            line = ' '.join(line.split())
            if line in seen:
                continue
            seen.add(line)
            need = line_words(line)
            missing = need - shown
            if missing:
                rows.append({'text': line, 'words': sorted(missing) if need & shown else None})
    return rows
