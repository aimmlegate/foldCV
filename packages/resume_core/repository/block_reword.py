"""A block's text reworded on the user's request (a trial).

The values a template lets a model reword (a block's `rewrite.fields`) are read from one item of the document, each
with the source lines it rests on. One model call gives one text per value, by the request the user wrote or took
from the unified rules (importing/lite/rules.py) and saw before sending: no instruction goes to the model unseen.
Code keeps a text only when it states no number and no name that its value and its source lines lack. Nothing here writes
the project: the result is a list of before and after, and the user's Apply sends the chosen ones as fact updates
(assistant_compiler), so a fact changes only by the user's action."""

from dataclasses import dataclass, field

from pydantic import Field

from ..fields import inline_groups
from ..importing.lite import prompts as P
from ..importing.lite.rules import block_text
from ..importing.lite.scheme import CYRILLIC, LATIN, LETTERS, NUMBER
from ..importing.lite.words import NAME as WORD, unknown_names
from ..technologies import resolve_technology
from ..importing.template_review import _matches
from ..models.assistant import UpdateFactOp
from ..models.contracts import Id, Wire
from ..editing.mutations import subtree
from ..editing.template_preparation_text import _fields
from ..templates.projection import pointer_tokens
from .assistant_compiler import find_record

SOURCE_LINES, SOURCE_CHARS, CONTEXT_VALUES = 6, 600, 24
# A reworded value is a line or a few sentences: it may grow, not into a page.
GROWTH, ROOM = 3, 300


class RewordValue(Wire):
    """One value of the block: what it says now, what the model proposes, and whether code keeps the proposal."""
    id: Id
    record_id: Id
    field: Id
    # What the value is in its block, as the template names it: tasks, results, project.description.
    kind: str
    before: str
    after: str | None
    state: str      # changed | same | refused
    # Why code refused the proposal (long, number, name, mixed) and the words it is about.
    reason: str | None
    words: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)


class RewordChange(Wire):
    record_id: Id
    field: Id
    value: str = Field(min_length=1, max_length=4000)


@dataclass
class Target:
    id: str
    record_id: str
    field: str
    kind: str
    text: str
    source: list[str] = field(default_factory=list)


@dataclass
class RewordSource:
    block: object                      # the template's block
    targets: list
    context: list


def _kind(pointer):
    tokens = [token for token in pointer_tokens(pointer) if token != '*']
    if len(tokens) > 1 and tokens[-1] == 'value':
        tokens = tokens[:-1]
    return '.'.join(tokens)


def _reworded(definition, block):
    """The values of the block a model may reword: {(record kind or semantic type, field key): [kind, ...]}."""
    types = {declaration.id: declaration for declaration in definition.fact_types}
    found = {}
    for binding in block.bindings:
        if not any(_matches(pattern, binding.pointer) for pattern in block.rewrite.fields):
            continue
        declaration = types.get(binding.semantic_type)
        if declaration is None:
            continue
        if declaration.builtin_kind is not None:
            target = (declaration.builtin_fields or {}).get(binding.field)
            if target is None or target.period is not None:
                continue
            key = (declaration.builtin_kind, target.field)
        else:
            key = (binding.semantic_type, binding.field)
        found.setdefault(key, []).append(_kind(binding.pointer))
    return found


def _unit_texts(project):
    return {unit.id: unit.text for source in project.sources for unit in source.units}


def _source_lines(record, extension, key, units):
    """The source lines a value rests on, as text."""
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
        text = ' '.join(str(text).split())[:SOURCE_CHARS]
        if text and text not in lines:
            lines.append(text)
    return lines[:SOURCE_LINES]


def _template_block(workspace, block):
    key = getattr(getattr(block, 'presentation', None), 'view_key', None)
    definition = workspace.project.template_package.definition
    found = next((value for value in definition.blocks if value.id == key), None)
    return found if found is not None and found.rewrite.fields else None


def reword_source(workspace, block_id):
    """What a rewording of one top-level document block reads; None when the template lets a model reword nothing
    in it."""
    project = workspace.project
    if project is None:
        return None
    top = next((block for region in project.document.regions for block in region.blocks if block.id == block_id), None)
    declared = _template_block(workspace, top) if top is not None else None
    if declared is None:
        return None
    reworded, units = _reworded(project.template_package.definition, declared), _unit_texts(project)
    targets, context, seen = [], [], set()
    for part in subtree(top):
        index = getattr(getattr(part, 'presentation', None), 'node_index', None)
        node = declared.view.nodes[index] if index is not None and index < len(declared.view.nodes) else None
        wanted = _kind(node.field) if node is not None and node.field else None
        for _key, content in inline_groups(part):
            for span, _start, _end in _fields(content):
                record_id, key = getattr(span, 'record_id', None), getattr(span, 'field_key', None)
                text = ' '.join(getattr(span, 'text', '').split())
                if record_id is None or not text or (record_id, key) in seen:
                    continue
                seen.add((record_id, key))
                record, extension = find_record(workspace, record_id)
                kinds = reworded.get((record.semantic_type if extension else record.kind, key)) if record is not None else None
                if not kinds:
                    if len(context) < CONTEXT_VALUES:
                        context.append(text)
                    continue
                kind = wanted if wanted in kinds else kinds[0]
                targets.append(Target('V' + str(len(targets) + 1), record_id, key, kind, text,
                    _source_lines(record, extension, key, units)))
    return RewordSource(declared, targets, context) if targets else None


def rewordable(workspace):
    """The top-level document blocks that hold a value the template lets a model reword: {block id: the template's
    rules of wording for its kind of block, as the text of a request the editor offers}."""
    project = workspace.project
    if project is None:
        return {}
    found = {}
    for region in project.document.regions:
        for block in region.blocks:
            declared = _template_block(workspace, block)
            if declared is not None and reword_source(workspace, block.id) is not None:
                found[block.id] = block_text(declared.id, project.template_package.definition)
    return found


# ---------------------------------------------------------------------------------------------------- the request

RULES = [
    P.COMMON[0],
    'Rewriting is allowed for these values: the runtime permission is true.',
    'request is the user\'s own word on how to reword the values: follow it within these rules. One value in, one '
    'value out: the reply has every id once. Never split a value into two, join two, or move content from one value '
    'to another, even where the request says to split.',
    'A value states only what its present text and its source lines state. Add no number, name, technology, employer, '
    'client or result they do not state, and drop none that its present text states.',
    'kind tells what a value is in its block (tasks, results, a description); follow what the request says for that '
    'kind.',
    'A value that already follows the request comes back word for word.',
    'Keep the language of the value. context holds the block\'s other values; they are not reworded.',
]
EXAMPLE = {
    'request': 'Задачи — одним пунктом одна зона ответственности, без вводных слов. Результаты — личный вклад и эффект.',
    'values': [{'id': 'V1', 'kind': 'tasks', 'text': 'Занималась тем, что делала API для мобильного приложения',
                'source': ['• Занималась тем, что делала API для мобильного приложения']},
               {'id': 'V2', 'kind': 'results', 'text': 'Время ответа API стало меньше в 2 раза',
                'source': ['• Время ответа API стало меньше в 2 раза']}],
    'reply': {'values': [{'id': 'V1', 'text': 'Разработка API для мобильного приложения'},
                         {'id': 'V2', 'text': 'Сократила время ответа API в 2 раза'}]},
}


def reword_schema(targets):
    ids = [target.id for target in targets]
    return P.closed({'values': P.array(P.closed({'id': {'type': 'string', 'enum': ids}, 'text': P.NAME}),
                                       minItems=len(ids), maxItems=len(ids))})


def reword_request(source, instruction, language='ru'):
    """instruction: the request as the user saw it in the panel. It is all the model is told about style."""
    block = source.block
    title = (block.view.title or {}).get(language) or block.id
    return P.request({
        'task': 'Reword the listed values of one block of a résumé by the user\'s request.',
        'rules': RULES, 'request': '\n'.join(' '.join(line.split()) for line in instruction.splitlines() if line.strip()),
        'example': EXAMPLE, 'block': title, 'context': source.context,
        'values': [{'id': target.id, 'kind': target.kind, 'text': target.text, 'source': target.source}
                   for target in source.targets]})


# ---------------------------------------------------------------------------------------------------- the checks

def refusal(target, text):
    """Why code does not keep a proposed text, as (reason, the words it is about); None when it keeps it."""
    known = ' '.join([target.text, *target.source])
    if len(text) > max(ROOM, GROWTH * len(target.text)):
        return 'long', []
    numbers = sorted(set(NUMBER.findall(text)) - set(NUMBER.findall(known)))
    if numbers:
        return 'number', numbers
    words = {word.casefold() for word in WORD.findall(known)} | {word.casefold() for word in LETTERS.findall(known)}
    # A name by its writing, and a technology the catalog knows however it is written (a lowercase «redis»).
    technologies = {word.casefold() for word in WORD.findall(text) if resolve_technology(word).canonical_id is not None}
    names = sorted({*unknown_names(text, words), *(name for name in technologies if name not in words)})
    if names:
        return 'name', names
    mixed = sorted({word for word in LETTERS.findall(text) if CYRILLIC.search(word.casefold())
                    and LATIN.search(word.casefold()) and word.casefold() not in words})
    if mixed:
        return 'mixed', mixed
    return None


def reword_values(source, reply):
    """Each value of the block with the model's proposal and what code makes of it."""
    proposed = {}
    for item in (reply or {}).get('values') or []:
        if isinstance(item, dict) and isinstance(item.get('text'), str):
            proposed.setdefault(item.get('id'), ' '.join(item['text'].split()))
    values = []
    for target in source.targets:
        text = proposed.get(target.id)
        if not text or text == target.text:
            state, refused, after = 'same', None, None
        else:
            refused = refusal(target, text)
            state, after = ('refused' if refused else 'changed'), text
        values.append(RewordValue(id=target.id, recordId=target.record_id, field=target.field, kind=target.kind,
            before=target.text, after=after, state=state, reason=refused[0] if refused else None,
            words=refused[1] if refused else [], source=target.source))
    return values


def reword_ops(workspace, block_id, changes):
    """The fact updates of the user's Apply. Only a value the template lets a model reword in this block is taken:
    a change of any other field is refused, whatever the request says."""
    source = reword_source(workspace, block_id)
    allowed = {(target.record_id, target.field) for target in source.targets} if source is not None else set()
    if not changes or any((change.record_id, change.field) not in allowed for change in changes):
        raise ValueError('a change outside the reworded fields of this block')
    return [UpdateFactOp(op='update_fact', recordId=change.record_id, field=change.field, value=change.value)
            for change in changes]
