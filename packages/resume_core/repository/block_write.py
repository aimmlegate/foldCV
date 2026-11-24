"""«Написать заново по резюме» (F6a): a text block that has text is written again from the CV's lines.

The lines are the CV as the lite import read it, less the lines that import hid (contacts, headings, repeated page
lines): a project whose last import kept no hidden line cannot tell them, so it gets no such action (P1). The model
gets the request the user saw, the block's present text and the lines; code keeps its text by the import's checks
(written_check), against the lines that were sent. Nothing here writes the project: the preview is a value of the
block reword, and the user's Apply goes through its route."""

from collections import OrderedDict
from dataclasses import dataclass
import threading
from typing import Any

from ..importing.lite import prompts as P
from ..importing.lite.lines import CV
from ..importing.lite.scheme import WRITTEN_LINES, written_check
from .block_reword import RewordValue, Target, reword_source

# Text blocks of the import's write call that the editor writes again (a list block is F6b).
BLOCKS = tuple(block for block, spec in P.WRITE.items() if spec['shape'] == 'text')
# The reasons of written_check as the preview names them.
REASONS = {'no text': 'empty', 'no lines': 'lines', 'too long': 'long', 'a number the CV lacks': 'number',
           'a word of two alphabets': 'mixed', 'a name the CV lacks': 'name', 'another language': 'language'}


def fold(text):
    return ' '.join(str(text).split())


# Import records are content-addressed history files that never change: their hidden lines are read once per set.
_HIDDEN, _LOCK, _HELD = OrderedDict(), threading.Lock(), 16


def hidden_lines(operations):
    """The texts of the lines the last published import hid, white space folded; None when it kept none (an import
    before 1.1.0, or one that hid no line)."""
    published = [operation for operation in operations if operation.state == 'published']
    if not published:
        return None
    found = frozenset(fold(line) for rows in published[-1].other_lines if rows.reason == 'hidden' for line in rows.lines)
    return found or None


def project_hidden(directory, workspace):
    """hidden_lines of the project's import records, read from its history files once (D104)."""
    from .project_repository import import_records
    project = workspace.project
    if project is None:
        return None
    if project.template_operations:
        return hidden_lines(project.template_operations)
    key = tuple(ref.sha256 for ref in project.current_history())
    if not key:
        return None
    with _LOCK:
        if key in _HIDDEN:
            _HIDDEN.move_to_end(key)
            return _HIDDEN[key]
    value = hidden_lines(import_records(directory, workspace))
    with _LOCK:
        _HIDDEN[key] = value
        while len(_HIDDEN) > _HELD:
            _HIDDEN.popitem(last=False)
    return value


@dataclass
class WriteSource:
    title: str
    target: Target          # the block's one text value
    lines: list             # the CV lines sent (EvidenceOption), hidden ones left out


def write_source(workspace, block_id, hidden, language='ru'):
    """What writing one top-level block again reads; None when the block cannot be: not a text block of the import's
    write call, no text on the page, or no hidden lines known."""
    project = workspace.project
    if project is None or not hidden:
        return None
    source = reword_source(workspace, block_id)
    block: Any = source.block if source is not None else None
    if source is None or block.id not in BLOCKS or len(source.targets) != 1:
        return None
    lines = [line for line in CV(project.sources).lines if fold(line.text) not in hidden and fold(line.text)]
    if not lines:
        return None
    title = (block.view.title or {}).get(language) or block.id
    return WriteSource(title, source.targets[0], lines)


def writable(workspace, hidden):
    """The ids of the top-level blocks the editor can write again."""
    project = workspace.project
    if project is None or not hidden:
        return []
    return [block.id for region in project.document.regions for block in region.blocks
            if write_source(workspace, block.id, hidden) is not None]


def write_request(source, instruction, refused=None):
    return P.rewrite_request(source.title, source.lines, instruction, source.target.text, refused)


def write_value(source, reply):
    """The block's value with the model's text and what code makes of it, and the sentence for the model when code
    refused a text that one more call may fix (None otherwise)."""
    reply = reply if isinstance(reply, dict) else {}
    target, sent = source.target, {line.ref: index for index, line in enumerate(source.lines)}
    text = fold(reply.get('text') or '')
    refs = sorted({ref for ref in (reply.get('lines') or [])[:WRITTEN_LINES] if isinstance(ref, str) and ref in sent},
                  key=lambda ref: sent[ref])
    problem, words, told = written_check(text, refs, [line.text for line in source.lines], language=True)
    if problem is None and text == target.text:
        state, reason, after, told = 'same', None, None, None
    elif problem is not None:
        state, reason, after = 'refused', REASONS[problem], text or None
    else:
        state, reason, after = 'changed', None, text
    value = RewordValue.model_validate({'id': target.id, 'recordId': target.record_id, 'field': target.field,
        'kind': target.kind, 'before': target.text, 'after': after, 'state': state, 'reason': reason, 'words': list(words),
        'source': target.source})
    return value, told
