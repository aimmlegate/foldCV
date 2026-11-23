"""One user action over several text containers, as a chain of present operations (F3 of the tester feedback of
2026-11-23). Each step is prepared on the workspace that the step before it left, as the assistant's compiler does; the
edit route commits the last workspace as one action, so a refused step changes nothing."""

from __future__ import annotations

from ..fields import inline_groups
from ..models.rich_document import SectionBlock, TableBlock
from ..models.template_authoring import PasteLines, RemoveRange, TemplateEditPreparationV1
from ..models.template_document import PresentedText
from .mutations import inline_text, locate, subtree, utf16_slice
from .template_preparation_common import allocator_for, finish_preparation, validate_preparation
from .dependencies import placements
from .template_preparation_ids import existing_ids

TEXT_TYPES = {'paragraph', 'heading', 'bullet_list', 'numbered_list', 'check_list', 'toggle_list', 'quote'}
# The paste limits of F3d; a larger paste is refused with its own code, so the text can name them.
PASTE_LINES, PASTE_CHARS = 200, 64_000
LINE_ENDS = ('\r\n', '\r', '\n')


def _place(document, identifier):
    found = locate(document, identifier)
    if found is None:
        raise ValueError('authored block missing')
    return found


def _units(text):
    return len(text.encode('utf-16-le')) // 2


def _text(block):
    return ''.join(inline_text(span) for span in block.content) if isinstance(block.content, list) else ''


def pasted_lines(text):
    """Text with no line end is one line as it is; text with line ends (CR LF, LF, a lone CR) is split, and a line of only
    white space is dropped."""
    if not any(end in text for end in LINE_ENDS):
        return [text]
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    return [line for line in lines if line.strip()]


def checked_lines(lines):
    if len(lines) > PASTE_LINES or sum(_units(line) for line in lines) > PASTE_CHARS:
        raise ValueError('PASTE_TOO_LARGE')
    return lines


class ChainedEdit:
    def __init__(self, workspace, created_ids):
        self.workspace, self.created_ids = workspace, created_ids


class EditChain:
    """The workspace after each prepared step, with the ids taken so far; all steps share the request's capture, so the
    journal keeps them as one action."""

    def __init__(self, response, request, *, occupied, response_for):
        self.request, self.response, self.response_for = request, response, response_for
        self.current = response.workspace
        self.occupied = set(occupied if occupied is not None else existing_ids(response.workspace))
        self.created, self.count = {}, 0

    def block(self, identifier):
        found = locate(self.current.project.document, identifier)
        if found is None:
            raise ValueError('authored block missing')
        return found[0][found[1]]

    def _preparation(self, operation):
        self.count += 1
        base = self.request.operations[0].op_id
        response = self.response if self.count == 1 else self.response_for(self.current)
        preparation = TemplateEditPreparationV1.model_validate({'schemaVersion': 1,
            'clientMutationId': f'{self.request.client_mutation_id}:{self.count}',
            'snapshot': response.snapshot.model_dump(mode='json', by_alias=True),
            'capture': self.request.capture.model_dump(mode='json', by_alias=True),
            'operations': [{**operation, 'opId': f'{base}:{self.count}'}]})
        return response, preparation

    def _took(self, prepared):
        if prepared.mutation is None:
            return False
        self.current = prepared.preview.workspace
        for slots in prepared.created_ids.values():
            self.occupied.update(slots.values())
        self.created.update(prepared.created_ids)
        return True

    def step(self, operation):
        from .template_preparation import prepare_edit
        response, preparation = self._preparation(operation)
        return self._took(prepare_edit(response, preparation, occupied=self.occupied))

    def lines(self, context_id, lines, styles):
        """New blocks of the context block's type after it, each with one line of plain text and no fact."""
        response, preparation = self._preparation({'kind': 'insert_paragraph', 'contextBlockId': context_id,
            'contextRevision': self.block(context_id).revision,
            'placement': {'parentId': self.parent(context_id), 'afterId': context_id}, 'text': ''})
        return self._took(_inserted_lines(response, preparation, context_id, lines, styles, self.occupied))

    def parent(self, identifier):
        return _place(self.current.project.document, identifier)[2].id

    def text_range(self, identifier, start, end, text='', styles=None, target=None, *, cell=None):
        block = self.block(identifier)
        selected = {'blockId': identifier, 'beforeRevision': block.revision, 'cellId': cell, 'field': 'content',
            'start': start, 'end': end}
        if target is not None:
            selected['insertionTarget'] = target
        try:
            return self.step({'kind': 'replace_text', 'range': selected, 'text': text,
                'styles': styles.model_dump(mode='json', by_alias=True) if styles is not None else {}})
        except ValueError as error:
            # A bound link that a range edge cuts in part keeps its present guard, with a code the user can read.
            if 'URL' in str(error):
                raise ValueError('RANGE_LINK_EDGE') from None
            raise

    def result(self):
        return ChainedEdit(None if self.current is self.response.workspace else self.current, self.created)


def _inserted_lines(response, request, context_id, lines, styles, occupied):
    validate_preparation(response, request)
    candidate = response.workspace.project.model_copy(deep=True)
    allocator = allocator_for(response, request, request.operations[0], occupied)
    found = _place(candidate.document, context_id)
    items, parent, context = found[0], found[2], found[0][found[1]]
    steps, after = [], context_id
    for index, text in enumerate(lines):
        block = context.model_copy(deep=True)
        block.id = allocator.allocate('block', ['paste-line', context_id, index])
        block.revision, block.children, block.provenance = 1, [], []
        block.content = [PresentedText(type='text', text=text, styles=styles.model_copy(deep=True))] if text else []
        if block.type == 'numbered_list':
            block.props.start = None
        position = next(position for position, value in enumerate(items) if value.id == after) + 1
        items.insert(position, block)
        steps.append({'kind': 'put_block', 'parentId': parent.id, 'afterId': after, 'beforeRevision': None,
            'block': block.model_dump(by_alias=True)})
        after = block.id
    return finish_preparation(response, request, allocator, steps, candidate)


def _technology_line(workspace, block):
    from .template_preparation_text import _fields, _technology_names
    return any(_technology_names(workspace, [span for span, _start, _end in _fields(content)])
        for _key, content in inline_groups(block))


def paste_at(chain, identifier, start, end, lines, styles, target=None, *, enter=False):
    """Lines as typed with Enter between them: the first at the place, each next one a new block after it, the text
    that stood after the place after the last line (F3d). `enter` splits after the lines (F3c)."""
    lines = list(lines)
    if enter:
        lines = (lines or ['']) + ['']
    first = lines[0] if lines else ''
    if start < end or first:
        chain.text_range(identifier, start, end, first, styles, target if start == end and first else None)
    if len(lines) < 2:
        return
    block = chain.block(identifier)
    chain.step({'kind': 'split_block', 'blockId': identifier, 'beforeRevision': block.revision, 'offset': start + _units(first)})
    found = _place(chain.current.project.document, identifier)
    tail = found[0][found[1] + 1].id
    if len(lines) > 2:
        chain.lines(identifier, lines[1:-1], styles)
    if lines[-1]:
        chain.text_range(tail, 0, 0, lines[-1], styles, {'kind': 'literal'})


def _cells(block):
    return [cell for row in block.content.rows for cell in row.cells]


def _edge(document, edge, workspace):
    """The edge's block, its text length, whether it is a technology line and, in a table, the index of its cell."""
    found = locate(document, edge.block_id)
    if found is None:
        raise ValueError('authored block missing')
    block = found[0][found[1]]
    if block.revision != edge.before_revision:
        raise ValueError('stale authored block')
    if edge.cell_id is not None:
        if not isinstance(block, TableBlock) or edge.field != 'content':
            raise ValueError('range edge outside block text')
        cells = _cells(block)
        index = next((index for index, cell in enumerate(cells) if cell.id == edge.cell_id), None)
        if index is None:
            raise ValueError('authored inline container missing')
        text = ''.join(inline_text(span) for span in cells[index].content)
    else:
        if edge.field != 'content' or not isinstance(block.content, list) or isinstance(block, SectionBlock):
            raise ValueError('range edge outside block text')
        index, text = None, _text(block)
    if edge.offset > _units(text):
        raise ValueError('authored range exceeds content')
    utf16_slice(text, 0, edge.offset)
    return block, _units(text), _technology_line(workspace, block), index


def _cell_text(cell):
    return ''.join(inline_text(span) for span in cell.content)


def _cut_cells(chain, table, first, last, start=None, end=None):
    """F3e: the covered text of cells `first` to `last` of one table goes; a cell keeps the text outside the range."""
    cells = _cells(chain.block(table))
    for index in range(first, last + 1):
        cell = cells[index]
        length = _units(_cell_text(cell))
        lo = start if index == first and start is not None else 0
        hi = end if index == last and end is not None else length
        if lo < hi:
            chain.text_range(table, lo, hi, cell=cell.id)


def prepare_range(response, request, *, occupied=None, response_for):
    """F3a: remove the range between two edges in two containers, keep the facts, and merge the two edge blocks when
    they become adjacent siblings; an optional join puts text or lines at the place of the range."""
    validate_preparation(response, request)
    operation = request.operations[0]
    workspace = response.workspace
    document = workspace.project.document
    listed = document.blocks()
    order = {block.id: index for index, block in enumerate(listed)}
    blocks = {block.id: block for block in listed}
    parents = {identifier: place[0] for identifier, place in placements(document).items()}
    first, first_length, first_technology, first_cell = _edge(document, operation.start, workspace)
    last, last_length, last_technology, last_cell = _edge(document, operation.end, workspace)
    if (order[first.id], first_cell or 0) >= (order[last.id], last_cell or 0):
        raise ValueError('range edges out of order or in one container')
    start, end, join = operation.start.offset, operation.end.offset, operation.join
    lines = checked_lines(pasted_lines(join.text)) if join is not None and join.text else []
    joined = join is not None and (bool(lines) or join.enter)
    # A technology line changes only in Facts (D131): an edge may not cut its text, and nothing is typed into it.
    if first_technology and (0 < start < first_length or joined) or last_technology and 0 < end < last_length:
        raise ValueError('TECHNOLOGY_IN_FACTS')
    whole = {identifier for identifier, index in order.items() if order[first.id] < index < order[last.id]}
    if start == 0 and not joined and first_cell is None:
        whole.add(first.id)
    if end == last_length and last_cell is None:
        whole.add(last.id)
    if first_cell is not None or last_cell is not None:
        # F3e: a table with an edge in it stays with its rows; its covered cell text goes.
        return _table_range(response, request, occupied, response_for, document, order, blocks, whole,
            (first, start, first_cell, first_length), (last, end, last_cell), lines, join)
    gone = {identifier for identifier in whole if all(value.id in whole for value in subtree(blocks[identifier]))}

    def ancestors(identifier):
        while parents.get(identifier) in blocks:
            identifier = parents[identifier]
            yield identifier

    def stays(identifier):
        return identifier not in gone and not any(value in gone for value in ancestors(identifier))

    shown = [block.id for block in listed if block.type in TEXT_TYPES and not _technology_line(workspace, block)]
    if not any(stays(identifier) for identifier in shown):
        # The last shown text block of the document stays, empty, and takes the caret (F2 point 5).
        gone -= {first.id, *ancestors(first.id)}
    roots = [identifier for identifier in order if identifier in gone and not any(value in gone for value in ancestors(identifier))]
    chain = EditChain(response, request, occupied=occupied, response_for=response_for)
    first_stays, last_stays = stays(first.id), stays(last.id)
    if last_stays and end > 0:
        chain.text_range(last.id, 0, end)
    for identifier in order:
        # A covered block that keeps a line under it stays, with no text.
        if identifier in whole and identifier not in {first.id, last.id} and stays(identifier) and _text(blocks[identifier]):
            chain.text_range(identifier, 0, _units(_text(blocks[identifier])))
    if first_stays and (start < first_length or lines):
        target = join.insertion_target.model_dump(mode='json', by_alias=True) if (
            join is not None and join.insertion_target is not None and start == first_length and lines) else None
        chain.text_range(first.id, start, first_length, lines[0] if lines else '', join.styles if join else None, target)
    if roots:
        chain.step({'kind': 'remove_occurrences', 'blocks': [{'blockId': identifier,
            'beforeRevision': chain.block(identifier).revision} for identifier in roots]})
    if first_stays and last_stays:
        _merge(chain, first.id, last.id, first_technology or last_technology)
    if join is not None and joined and (len(lines) > 1 or join.enter):
        # The first line is in place; the next ones go after it as Enter would put them.
        at = start + (_units(lines[0]) if lines else 0)
        paste_at(chain, first.id, at, at, ['', *lines[1:]], join.styles, enter=join.enter)
    return chain.result()


def _table_range(response, request, occupied, response_for, document, order, blocks, whole, head, tail, lines, join):
    (first, start, first_cell, first_length), (last, end, last_cell) = head, tail
    if join is not None and join.enter:
        raise ValueError('RANGE_TABLE_EDGE')
    text = ' '.join(lines) if first_cell is not None else None
    if first_cell is None and lines and len(lines) > 1:
        raise ValueError('RANGE_TABLE_EDGE')
    parents = {identifier: place[0] for identifier, place in placements(document).items()}
    gone = {identifier for identifier in whole if all(value.id in whole for value in subtree(blocks[identifier]))}

    def under(identifier):
        while parents.get(identifier) in blocks:
            identifier = parents[identifier]
            if identifier in gone:
                return True
        return False
    chain = EditChain(response, request, occupied=occupied, response_for=response_for)
    styles = join.styles if join is not None else None
    if first.id == last.id:
        _cut_cells(chain, first.id, first_cell, last_cell, start, end)
    else:
        if last_cell is not None:
            _cut_cells(chain, last.id, 0, last_cell, None, end)
        elif end > 0 and last.id not in gone:
            chain.text_range(last.id, 0, end)
        for identifier in order:
            value = blocks[identifier]
            if identifier in whole and identifier not in gone and not under(identifier) and _text(value):
                chain.text_range(identifier, 0, _units(_text(value)))
        if first_cell is not None:
            _cut_cells(chain, first.id, first_cell, len(_cells(first)) - 1, start, None)
        elif start < first_length or lines:
            target = join.insertion_target.model_dump(mode='json', by_alias=True) if (
                join is not None and join.insertion_target is not None and start == first_length and lines) else None
            chain.text_range(first.id, start, first_length, lines[0] if lines else '', styles, target)
        roots = [identifier for identifier in order if identifier in gone and not under(identifier)]
        if roots:
            chain.step({'kind': 'remove_occurrences', 'blocks': [{'blockId': identifier,
                'beforeRevision': chain.block(identifier).revision} for identifier in roots]})
    if text and join is not None and first_cell is not None:
        target = join.insertion_target.model_dump(mode='json', by_alias=True) if join.insertion_target is not None else {'kind': 'literal'}
        chain.text_range(first.id, start, start, text, styles, target, cell=_cells(first)[first_cell].id)
    return chain.result()


def _merge(chain, leading, trailing, technology):
    """Rule 6 of F3a: two text blocks, no technology line, a leading block with no children, and the trailing block now
    its next sibling. Otherwise the two blocks stay apart."""
    found = _place(chain.current.project.document, leading)
    items, index = found[0], found[1]
    first, last = items[index], items[index + 1] if index + 1 < len(items) else None
    if (technology or last is None or last.id != trailing or first.children or first.type not in TEXT_TYPES
            or last.type not in TEXT_TYPES):
        return
    chain.step({'kind': 'merge_blocks', 'leadingId': first.id, 'leadingRevision': first.revision,
        'trailingId': last.id, 'trailingRevision': last.revision})


def prepare_lines(response, request, *, occupied=None, response_for):
    """F3d: plain text with line ends at a caret or over a selection in one container; F3c: Enter over a selection."""
    validate_preparation(response, request)
    operation = request.operations[0]
    selected = operation.destination
    found = locate(response.workspace.project.document, selected.block_id)
    if found is None:
        raise ValueError('authored block missing')
    block = found[0][found[1]]
    lines = checked_lines(pasted_lines(operation.text)) if operation.text else []
    chain = EditChain(response, request, occupied=occupied, response_for=response_for)
    target = selected.insertion_target.model_dump(mode='json', by_alias=True) if selected.insertion_target else None
    if selected.cell_id is not None or selected.field != 'content':
        # A table cell or a caption takes one line: the lines join with one space.
        text = ' '.join(lines)
        if selected.start < selected.end or text:
            chain.step({'kind': 'replace_text', 'range': selected.model_dump(mode='json', by_alias=True), 'text': text,
                'styles': operation.styles.model_dump(mode='json', by_alias=True)})
        return chain.result()
    if _technology_line(response.workspace, block):
        raise ValueError('TECHNOLOGY_IN_FACTS')
    paste_at(chain, block.id, selected.start, selected.end, lines, operation.styles, target, enter=operation.enter)
    return chain.result()


CHAINED = (RemoveRange, PasteLines)


def prepare_chained(response, request, *, occupied=None, response_for):
    operation = request.operations[0]
    if isinstance(operation, RemoveRange):
        return prepare_range(response, request, occupied=occupied, response_for=response_for)
    if isinstance(operation, PasteLines):
        return prepare_lines(response, request, occupied=occupied, response_for=response_for)
    raise ValueError('operation is not chained')
