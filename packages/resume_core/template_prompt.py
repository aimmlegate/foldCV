"""Model-facing text of a captured template request.

The stored request keeps every span, identity and hash; the reply names only references (S, H, E, R refs and
check refs C), so the model sees each offered entry as {ref, text} and none of the bookkeeping the
coordinator restores from those references. Parts shared by the tasks of one import come first so a provider
can reuse the cached prefix; block-specific parts follow. The text depends only on the request content, never
on key insertion order, so a request reloaded from storage reads the same.
"""

import json

LEADING = ('protocol', 'replyProtocol', 'modelInstructions', 'allowTextRewrite', 'formattingAsOf',
    'evidence', 'references', 'effectiveCells', 'effectiveRecords', 'manualScopes', 'relations', 'dependencies')
# Identities, hashes and spans a reply cannot use: it selects items, cells, relations and checks by reference.
HIDDEN = {'allowedHandles', 'capturedHandles', 'capturedRelations', 'tools', 'packageHash', 'handleMap', 'targets',
    'policy', 'proposalHash', 'sourceSpans', 'sourceTexts'}


# What a model can read in a cell: its identity, wording, value and standing; spans and receipts stay stored.
CELL_KEYS = ('id', 'fieldKey', 'rawInput', 'typedValue', 'state', 'origin')


def lean_cell(cell):
    return {key: cell[key] for key in CELL_KEYS if key in cell}


def read_cells(request):
    """The cells a review's proposal reads. A review input keeps every effective cell for its identity (receipt
    reuse), but the reviewer needs only these (LIVE-04: 250k characters of cells refused as INPUT_TOO_LARGE)."""
    proposal = (request.get('semanticContext') or {}).get('proposal') or {}
    return {cell for field in proposal.get('fields', []) for cell in field.get('effectiveCellIds', [])}


def lean_evidence(options):
    return [{'ref': option['ref'], 'text': option['text']} for option in options]


def lean_dependency(result):
    return {'taskId': result['taskId'], 'disposition': result['disposition'], 'value': result['value']}


def lean_context(context):
    lean = {key: value for key, value in context.items() if key != 'effectiveFactsHash'}
    if isinstance(context.get('taskInput'), dict):
        lean['taskInput'] = {key: value for key, value in context['taskInput'].items()
            if key not in HIDDEN and key not in {'replyProtocol', 'evidence'}}
    if isinstance(context.get('checks'), list):
        lean['checks'] = [{key: value for key, value in check.items() if key != 'targetId'} for check in context['checks']]
    return lean


def lean_part(key, value, request=None):
    if key == 'evidence':
        return lean_evidence(value)
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
        return lean_context(value)
    return value


def model_prompt(value):
    keys = [key for key in LEADING if key in value] + sorted(key for key in value if key not in LEADING and key not in HIDDEN)
    parts = [json.dumps(key, ensure_ascii=False) + ':' + json.dumps(lean_part(key, value[key], value), ensure_ascii=False,
        sort_keys=True, separators=(',', ':'), allow_nan=False) for key in keys]
    return '{' + ','.join(parts) + '}'
