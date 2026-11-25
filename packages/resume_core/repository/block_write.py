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
from pydantic import Field

from ..importing.lite.scheme import WRITTEN_ITEM, WRITTEN_LINES, written_check
from ..models.contracts import Id, Wire
from .block_reword import RewordValue, Target, reword_source

# Text blocks of the import's write call that the editor writes again, and list blocks (F6b, D181).
BLOCKS = tuple(block for block, spec in P.WRITE.items() if spec['shape'] == 'text')
LIST_BLOCKS = tuple(block for block, spec in P.WRITE.items() if spec['shape'] == 'items')
# A list written again has 1 to 5 items, or as many as it had when that is more, but not more than 8 (the owner, D4).
LIST_USUAL, LIST_MOST = 5, 8
# The reasons of written_check as the preview names them.
REASONS = {'no text': 'empty', 'no lines': 'lines', 'too long': 'long', 'a number the CV lacks': 'number',
           'a word of two alphabets': 'mixed', 'a name the CV lacks': 'name', 'another language': 'language',
           'duplicate': 'duplicate'}


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
    """The ids of the top-level blocks the editor can write again: text blocks and list blocks."""
    project = workspace.project
    if project is None or not hidden:
        return []
    return [block.id for region in project.document.regions for block in region.blocks
            if write_source(workspace, block.id, hidden) is not None or list_source(workspace, block.id, hidden) is not None]


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


# ---------------------------------------------------------------------------------------------------- a list (F6b)

class WrittenItem(Wire):
    """One item of a list the model wrote, and what code makes of it."""
    id: Id
    text: str
    lines: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)
    state: str        # added | refused
    reason: str | None = None
    words: list[str] = Field(default_factory=list)


class AddedItem(Wire):
    """A new item the user's Apply takes: the text (edited or as the preview gave it) and the refs it rests on."""
    text: str = Field(min_length=1, max_length=4000)
    lines: list[str] = Field(default_factory=list, max_length=10)
    edited: bool = True


@dataclass
class ListItem:
    bullet_id: str
    record_id: str
    cell_id: str
    field: str
    text: str
    corrected: bool          # the user's own value: «оставить» is on at the start (the owner, D2b)


@dataclass
class ListSource:
    title: str
    block_id: str
    items: list              # ListItem, page order
    kept: list               # texts of the bullets the user typed (no record): they stay
    lines: list              # the CV lines sent (EvidenceOption), hidden ones left out


def list_source(workspace, block_id, hidden, language='ru'):
    """What writing a list block again reads; None when the block cannot be: not a list block of the import's write
    call, no item on the page, or no hidden lines known."""
    from ..editing.template_list_items import item_bullets, list_section
    from .source_diff import written_by_model
    project = workspace.project
    if project is None or not hidden:
        return None
    source = reword_source(workspace, block_id)
    block: Any = source.block if source is not None else None
    section = list_section(project, block_id) if source is not None and block.id in LIST_BLOCKS else None
    if section is None:
        return None
    pairs = item_bullets(project, section)
    items = [ListItem(bullet.id, record.id, record.cells[0].id, record.cells[0].field_key, fold(bullet.content[0].text),
                      not written_by_model(project, record, record.cells[0].id)) for bullet, record in pairs]
    shown = {bullet.id for bullet, _record in pairs}
    kept = [text for child in section.children if child.id not in shown
            for text in [fold(''.join(getattr(span, 'text', '') for span in child.content)) if isinstance(child.content, list) else '']
            if text]
    lines = [line for line in CV(project.sources).lines if fold(line.text) not in hidden and fold(line.text)]
    if not lines:
        return None
    title = (block.view.title or {}).get(language) or block.id
    return ListSource(title, block_id, items, kept, lines)


def list_most(source):
    return min(LIST_MOST, max(LIST_USUAL, len(source.items)))


def list_request(source, instruction):
    return P.rewrite_list_request(source.title, source.lines, instruction, [item.text for item in source.items], source.kept,
                                  list_most(source))


def list_schema(_source):
    return P.rewrite_list_schema()


def list_values(source, reply):
    """(the present items, each with whether «оставить» starts on; the new items with what code makes of each)."""
    present = [RewordValue.model_validate({'id': 'P' + str(number), 'recordId': item.record_id, 'field': item.field,
        'kind': 'items', 'before': item.text, 'after': None, 'state': 'present', 'reason': None, 'words': [],
        'source': [], 'keep': item.corrected}) for number, item in enumerate(source.items, 1)]
    sent = {line.ref: index for index, line in enumerate(source.lines)}
    texts = [line.text for line in source.lines]
    seen = {fold(text).casefold() for text in source.kept}
    added = []
    replied = (reply if isinstance(reply, dict) else {}).get('items') or []
    for number, item in enumerate([value for value in replied if isinstance(value, dict)][:list_most(source)], 1):
        text = fold(item.get('text') or '')
        refs = sorted({ref for ref in (item.get('lines') or [])[:WRITTEN_LINES] if isinstance(ref, str) and ref in sent},
                      key=lambda ref: sent[ref])
        problem, words, _told = written_check(text, refs, texts, WRITTEN_ITEM, language=True)
        if problem is None and text.casefold() in seen:
            problem, words = 'duplicate', []
        seen.add(text.casefold())
        added.append(WrittenItem(id='N' + str(number), text=text, lines=refs, source=[texts[sent[ref]] for ref in refs],
            state='refused' if problem else 'added', reason=REASONS[problem] if problem else None, words=list(words)))
    return present, added


def list_workspace(workspace, block_id, removed, added, hidden, *, action_id, occupied, response_for):
    """The workspace after the user's Apply of a list written again: the new items (in the reply's order, at the place
    of the first removed item, else after the last item), then each removed item taken off the page with its record
    (remove_list_item). One chain, so the caller commits it as one action."""
    from .assistant_compiler import Chain, find_block
    source = list_source(workspace, block_id, hidden)
    if source is None:
        raise ValueError('not a list that can be written again')
    present = {item.record_id: item for item in source.items}
    if not set(removed) <= present.keys() or len(set(removed)) != len(removed) or not (removed or added):
        raise ValueError('a removal outside the list, or nothing to apply')
    if len(present) - len(removed) + len(added) < 1:
        raise ValueError('the list would be left with no item')
    sent = {line.ref: line for line in source.lines}
    if any(ref not in sent for item in added for ref in item.lines):
        raise ValueError('an item rests on a line that was not sent')
    chain = Chain(workspace, action_id=action_id, occupied=occupied, response_for=response_for)
    block = find_block(workspace, block_id)
    if block is None:
        raise ValueError('the list block is gone')
    children = [child.id for child in block.children]
    gone = [present[record].bullet_id for record in removed]
    first = min((children.index(bullet) for bullet in gone), default=None)
    after = (children[first - 1] if first else None) if first is not None else present[source.items[-1].record_id].bullet_id
    for item in added:
        section = chain.block(block_id)
        created = chain.apply({'kind': 'add_list_item', 'blockId': block_id, 'beforeRevision': section.revision,
            'afterId': after, 'text': item.text,
            'evidence': [sent[ref].span.model_dump(mode='json', by_alias=True) for ref in item.lines],
            **({} if item.edited else {'written': 'model'})})
        if not created:
            raise ValueError('add_list_item made no bullet')
        after = created[0]
    for record_id in removed:
        remove_list_item(chain, present[record_id].bullet_id, record_id)
    return chain.current, chain.created


def remove_list_item(chain, bullet_id, record_id):
    """A list item off the page with its record: its bullet goes (no empty bullet stays), then the record (D5: only
    Undo brings it back)."""
    from .assistant_compiler import find_record
    bullet = chain.block(bullet_id)
    chain.apply({'kind': 'remove_occurrences', 'blocks': [{'blockId': bullet.id, 'beforeRevision': bullet.revision}]})
    record, _extension = find_record(chain.current, record_id)
    if record is not None:
        chain.apply({'kind': 'delete_entity', 'recordId': record.id, 'beforeRevision': record.revision})
