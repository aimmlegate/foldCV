"""Model-facing text of a captured template request.

The stored request keeps every span, identity and hash; the reply names only references (S, H, E, R refs and
check refs C), so the model sees each offered entry by its ref and text and none of the bookkeeping the
coordinator restores from those references. Parts shared by the tasks of one import come first so a provider
can reuse the cached prefix: the protocol name and the offered evidence (the whole source, the same for every
proposal and review of an import) open the text (D116), then the parts shared by one kind of request, then the
block-specific ones. The text depends only on the request content, never on key insertion order, so a request
reloaded from storage reads the same.

A request of a compact protocol (replies.COMPACT_PROTOCOLS) shows each entry as [ref, text] and a whole unit offered
beside its lines as [ref, [first, last]], its other blocks by id and title, and its declaration without what only the
document needs. A request of an earlier protocol reads exactly as it was sent, so a resumed import keeps its form.
"""

import json

from ..templates.replies import COMPACT_PROTOCOLS

LEADING = ('protocol', 'evidence', 'replyProtocol', 'modelInstructions', 'allowTextRewrite', 'formattingAsOf',
    'references', 'effectiveCells', 'effectiveRecords', 'manualScopes', 'relations', 'dependencies')
# Identities, hashes and spans a reply cannot use: it selects items, cells, relations and checks by reference.
HIDDEN = {'allowedHandles', 'capturedHandles', 'capturedRelations', 'tools', 'packageHash', 'handleMap', 'targets',
    'policy', 'proposalHash', 'sourceSpans', 'sourceTexts', 'settled'}


# What a model can read in a cell: its identity, wording, value and standing; spans and receipts stay stored.
CELL_KEYS = ('id', 'fieldKey', 'rawInput', 'typedValue', 'state', 'origin')
# A compact declaration leaves out how and where the document shows the block; a review's also its bindings, since
# its checks name the pointer of every value.
EXTRACTION_OMITS = frozenset({'view', 'placement'})
REVIEW_OMITS = EXTRACTION_OMITS | {'bindings'}


def lean_cell(cell):
    return {key: cell[key] for key in CELL_KEYS if key in cell}


def read_cells(request):
    """The cells a review's proposal reads. A review input keeps every effective cell for its identity (receipt
    reuse), but the reviewer needs only these (a live import: 250k characters of cells refused as INPUT_TOO_LARGE)."""
    proposal = (request.get('semanticContext') or {}).get('proposal') or {}
    return {cell for field in proposal.get('fields', []) for cell in field.get('effectiveCellIds', [])}


def compact(request):
    """Whether a request is written in the compact form: by the reply protocol it was captured with (a review's is in
    its semantic context)."""
    context = request.get('semanticContext')
    protocol = context.get('replyProtocol') if isinstance(context, dict) else request.get('replyProtocol')
    return isinstance(protocol, dict) and protocol.get('version') in COMPACT_PROTOCOLS


def lean_evidence(options):
    return [{'ref': option['ref'], 'text': option['text']} for option in options]


def _unit(span):
    return span.get('sourceId'), span.get('sourceRevision'), span.get('unitId'), span.get('unitRevision')


def unit_lines(option, offered, ends):
    """The refs of a whole unit's lines, cut as line_spans cuts them, when every one is offered on its own; else []."""
    span = option['span']
    if span.get('start') != 0 or span.get('end') != ends[_unit(span)]:
        return []
    refs, start = [], 0
    for line in option['text'].splitlines(keepends=True):
        if line.strip():
            refs.append(offered.get((_unit(span), start, start + len(line), line)))
        start += len(line)
    return refs if len(refs) > 1 and None not in refs else []


def paired_evidence(options):
    """Each offered entry as [ref, text], in the table's order. A whole unit offered beside each of its lines is
    [ref, [first, last]]: its text was the text of those lines again (a fifth of an import's input)."""
    offered = {(_unit(option['span']), option['span'].get('start'), option['span'].get('end'), option['text']): option['ref']
        for option in options}
    ends = {}
    for option in options:
        unit = _unit(option['span'])
        ends[unit] = max(ends.get(unit, 0), option['span'].get('end') or 0)
    pairs = []
    for option in options:
        lines = unit_lines(option, offered, ends)
        pairs.append([option['ref'], [lines[0], lines[-1]] if lines else option['text']])
    return pairs


def lean_declaration(declaration, omitted):
    return {key: value for key, value in declaration.items() if key not in omitted}


def block_titles(blocks):
    """The other blocks by id and title: a coverage finding needs only to know which block shows a statement (D107)."""
    return [{key: value for key, value in block.items() if key in {'block', 'title'}} if isinstance(block, dict) else block
        for block in blocks]


def lean_dependency(result):
    return {'taskId': result['taskId'], 'disposition': result['disposition'], 'value': result['value']}


def lean_checks(checks):
    """Review checks grouped by target; inputs stored before grouping hold one entry per check."""
    if all(isinstance(check, dict) and 'check' in check for check in checks):
        from .template_review import grouped_checks
        return grouped_checks(checks)
    return checks


def lean_context(context, short=False):
    lean = {key: value for key, value in context.items() if key not in {'effectiveFactsHash', 'taskFactsHash'}}
    if isinstance(context.get('taskInput'), dict):
        lean['taskInput'] = {key: value for key, value in context['taskInput'].items()
            if key not in HIDDEN and key not in {'replyProtocol', 'evidence'}}
        if short and isinstance(lean['taskInput'].get('declaration'), dict):
            lean['taskInput']['declaration'] = lean_declaration(lean['taskInput']['declaration'], REVIEW_OMITS)
    if short and isinstance(context.get('otherBlocks'), list):
        lean['otherBlocks'] = block_titles(context['otherBlocks'])
    if isinstance(context.get('checks'), list):
        lean['checks'] = lean_checks(context['checks'])
        # The checks carry every entry's pointer, evidence and relation; the proposal adds only its values.
        if isinstance(context.get('proposal'), dict):
            lean['proposal'] = {'payload': context['proposal'].get('payload')}
    return lean


def lean_part(key, value, request=None):
    short = request is not None and compact(request)
    if key == 'evidence':
        return paired_evidence(value) if short else lean_evidence(value)
    if short and key == 'declaration' and isinstance(value, dict):
        return lean_declaration(value, EXTRACTION_OMITS)
    if short and key == 'otherBlocks' and isinstance(value, list):
        return block_titles(value)
    if key == 'effectiveCells' and isinstance(value, list):
        if request is not None and 'targets' in request:
            wanted = read_cells(request)
            value = [cell for cell in value if cell.get('id') in wanted]
        return [lean_cell(cell) for cell in value]
    if key == 'effectiveRecords' and isinstance(value, list):
        return [{**record, 'cells': [lean_cell(cell) for cell in record.get('cells', [])]} for record in value]
    if key == 'dependencies':
        return [lean_dependency(result) for result in value]
    if key == 'semanticContext' and isinstance(value, dict):
        return lean_context(value, short)
    return value


def model_prompt(value):
    # A review's relations are the proposal's own, named by internal ids; its relation checks show them by item.
    hidden = HIDDEN | ({'relations'} if 'targets' in value else set())
    keys = [key for key in LEADING if key in value and key not in hidden] + sorted(
        key for key in value if key not in LEADING and key not in hidden)
    parts = [json.dumps(key, ensure_ascii=False) + ':' + json.dumps(lean_part(key, value[key], value), ensure_ascii=False,
        sort_keys=True, separators=(',', ':'), allow_nan=False) for key in keys]
    return '{' + ','.join(parts) + '}'
