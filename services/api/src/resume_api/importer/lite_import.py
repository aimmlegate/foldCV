"""The lite import inside the template pipeline.

The lite scheme (packages/resume_core/importing/lite) makes its own model calls and gives each block's content with
the source spans of every value. The pipeline then runs as it always does, and every request it would send to a model
is answered here from that result: a block's extraction with the block's content, a review with «every check holds».
Admission, receipts, the document and the publication stay the pipeline's own."""

import contextvars
import json
import threading
import time

from packages.resume_core.importing.lite.scheme import Import
from packages.resume_core.importing.template_identity import _binding_instances, empty_value
from packages.resume_core.importing.template_import import ACCOUNT_STOP
from packages.resume_core.templates.projection import pointer_tokens
from packages.resume_core.templates.source_spans import payload_value
from ..inference_admission import CALLS, AdmissionCancelled
from ..lifecycle import OperationFiles
from ..providers.content import (ContentFailure, ContentInput, ContentResult, ContentTransportReturn, GenerationPolicy,
    ReportedUsage)
from ..providers.dynamic_result import dynamic_result

# The lite result of the import this context runs; the transport answers from it.
LITE = contextvars.ContextVar('template_lite_result', default=None)
INVALID = '{"payload": {"not": "a reply"}}'
WITNESS = {'transport': 'lite'}
# The scheme's stages, as the import's progress names them.
STAGES = {'map': 'Разметка резюме', 'entries': 'Записи опыта', 'blocks': 'Разделы резюме'}
OTHER_MESSAGE = 'Строки резюме без поля в шаблоне: {count}. {quotes} Они сохранены и в документе не показаны.'
OTHER_QUOTED = 3


def root_model(schema):
    """The reply schema as a closed model at the root: the Claude CLI gets the schema itself, with no {"payload"}
    envelope, so it never sends a large reply as a string inside one (that made it ask again)."""
    from copy import deepcopy
    from pydantic import ConfigDict, JsonValue, create_model
    model = create_model('Reply', __config__=ConfigDict(extra='forbid'),
                         **{name: (JsonValue, ...) for name in schema['properties']})
    model.model_json_schema = classmethod(lambda cls, *args, **kwargs: deepcopy(schema))
    return model


class LiteCalls:
    """The scheme's own model calls: the import's provider, model and effort, its permit, its cancel and its time."""

    def __init__(self, provider, adapter, model, effort, temp_root, cancel, remaining, permit):
        self.provider, self.adapter, self.model, self.effort = provider, adapter, model, effort
        self.temp_root, self.cancel, self.remaining, self.permit = temp_root, cancel, remaining, permit
        self.rows, self.lock = [], threading.Lock()
        self.envelope = adapter != 'claude_cli'

    def call(self, kind, block, prompt, schema):
        """One call: (the reply's object or None, its row with the usage and an error code)."""
        row = {'kind': kind, 'block': block, 'errorCode': None, 'usage': None, 'seconds': None}
        started, payload, usage = time.monotonic(), None, None
        try:
            seconds = self.remaining()
            if self.cancel.is_set() or seconds <= 0:
                raise ContentFailure('CANCELLED' if self.cancel.is_set() else 'DEADLINE_EXCEEDED')
            request = ContentInput(prompt, dynamic_result(schema) if self.envelope else root_model(schema),
                GenerationPolicy(self.model, timeout_seconds=seconds, allow_repair=False, reasoning_effort=self.effort))
            with CALLS.hold(self.adapter, self.cancel):
                with OperationFiles(self.temp_root).open() as files:
                    owned = getattr(self.provider, 'generate_owned', None)
                    if self.permit is not None and owned is not None:
                        result = owned(request, files, self.cancel, self.permit)
                    else:
                        result = self.provider.generate(request, files, self.cancel)
            value, usage = result.value, result.usage
            payload = value.payload if hasattr(value, 'payload') else value.model_dump(mode='json')
        except ContentFailure as error:
            usage, row['errorCode'] = error.usage, error.code
        except AdmissionCancelled:
            row['errorCode'] = 'CANCELLED'
        except Exception:
            # An unexpected provider error is this call's failure, as the transport reports it for a task's call.
            row['errorCode'] = 'PROCESS_FAILED'
        row['usage'], row['seconds'] = usage, round(time.monotonic() - started, 2)
        with self.lock:
            self.rows.append(row)
        return payload, row


class LiteResult:
    """What the transport answers from: each block's content and cited spans, and the usage of the scheme's calls."""

    def __init__(self, importer, calls, package):
        self.state = importer.state
        self.table, self.failed = dict(importer.table), set(importer.failed)
        self.other, self.notes = list(importer.other), importer.notes
        self.texts = {line.ref: ' '.join(line.text.split()) for line in importer.lines}
        self.blocks = {block.id: block for block in package.definition.blocks}
        self.schemas = {block.id: block.full_schema for block in package.blocks}
        self.lock, self.answered = threading.Lock(), set()
        # Each block's first answer reports the tokens the scheme spent on it; the map's go with the first block.
        self.spent = {}
        for row in calls.rows:
            usage = row['usage']
            if usage is None:
                continue
            key = row['block'].split('.')[0] if row['kind'] in {'fill', 'entry', 'split'} else None
            held = self.spent.setdefault(key, [0, 0, 0])
            for index, name in enumerate(('input_tokens', 'cached_input_tokens', 'output_tokens')):
                held[index] += getattr(usage, name, None) or 0
        self.stop = next((row['errorCode'] for row in calls.rows if row['errorCode'] in ACCOUNT_STOP), None)

    def usage(self, block):
        with self.lock:
            total = [0, 0, 0]
            for key in ([block] if self.answered else [block, None]):
                for index, value in enumerate(self.spent.pop(key, [0, 0, 0])):
                    total[index] += value
            self.answered.add(block)
        return ReportedUsage(total[0], total[1], total[2], True)

    def other_of(self, block):
        """The texts of the lines kept as «other» that belong to this block (those of no block go with identity)."""
        found = []
        for item in self.other:
            owner = (item['owner'] or 'identity').split('.')[0]
            if owner not in self.blocks:
                owner = 'identity'
            if owner == block:
                found += [self.texts[ref] for ref in item['refs'] if ref in self.texts]
        return found


def run(sources, package, calls, stage=None):
    """One lite import of these sources; calls: LiteCalls."""
    importer = Import(sources, calls, envelope=calls.envelope)
    importer.stage = stage
    importer.run()
    return LiteResult(importer, calls, package)


def other_text(texts):
    quotes = ', '.join('«' + (text if len(text) <= 80 else text[:79].rstrip() + '…') + '»' for text in texts[:OTHER_QUOTED])
    more = ' и ещё ' + str(len(texts) - OTHER_QUOTED) if len(texts) > OTHER_QUOTED else ''
    return OTHER_MESSAGE.format(count=len(texts), quotes=quotes + more + '.')


# ------------------------------------------------------------------------------------------------------- answers

def pointer_of(tokens):
    return ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in tokens)


def cites_for(evidence, pointer):
    """The spans cited for a value, else for the nearest enclosing value (a period's start cites the period)."""
    tokens = pointer_tokens(pointer)
    while True:
        found = evidence.get(pointer_of(tokens))
        if found:
            return list(found)
        if not tokens:
            return []
        tokens = tokens[:-1]


def evidence_ref(span, table):
    """The ref of the smallest text the request offers that holds this span; None when it offers none."""
    unit = (span['sourceId'], span['sourceRevision'], span['unitId'], span['unitRevision'])
    holders = [option for option in table
               if (option['span']['sourceId'], option['span']['sourceRevision'], option['span']['unitId'],
                   option['span']['unitRevision']) == unit
               and option['span']['start'] <= span['start'] and span['end'] <= option['span']['end']]
    if not holders:
        return None
    return min(holders, key=lambda option: option['span']['end'] - option['span']['start'])['ref']


def empty_content(block, schema):
    if block.view.mode == 'items':
        return []
    properties = schema.get('properties') or schema['$defs'][schema['$ref'].rsplit('/', 1)[1]]['properties']
    return {key: [] if (value.get('type') == 'array' or '$ref' in value and value['$ref'].endswith('/texts')) else None
            for key, value in properties.items()}


def block_reply(block, payload, evidence, table):
    """A block's content as the reference protocol replies: the payload, and for each bound value the refs it cites.
    Items, lineage and relations are left to the coordinator."""
    fields, seen = [], set()
    for pointer, _semantic, _field in sorted(_binding_instances(payload, block.bindings)):
        if pointer in seen or empty_value(payload_value(payload, pointer)):
            continue
        seen.add(pointer)
        refs = [ref for ref in (evidence_ref(span, table) for span in cites_for(evidence, pointer)) if ref is not None]
        if refs:
            fields.append({'pointer': pointer, 'evidence': list(dict.fromkeys(refs)), 'item': None, 'fieldKey': None,
                           'effectiveCells': None})
    return {'schemaVersion': 3, 'payload': payload, 'discoveries': None, 'fields': fields, 'lineage': None,
            'relations': None}


def raw_answer(value, lite):
    """The raw reply to one request of the pipeline, and the block whose content it is (None for a review)."""
    if 'targets' in value:
        return json.dumps({'payload': {'results': []}}), None     # every check holds
    if value.get('slot') == 'outline_review':
        return json.dumps({'payload': {'missing': [], 'remarks': []}}), None
    block = lite.blocks.get((value.get('declaration') or {}).get('id'))
    if block is None or value.get('slot') in {'outline', 'map', 'map_repair'}:
        return INVALID, None
    if lite.state != 'succeeded' or block.id in lite.failed:
        return INVALID, block.id      # the pipeline's own fallback shows the block's source lines
    if block.id in lite.table:
        payload, evidence = lite.table[block.id]
    else:
        payload, evidence = empty_content(block, lite.schemas[block.id]), {}
    reply = block_reply(block, payload, evidence, value.get('evidence') or [])
    return json.dumps({'payload': reply}, ensure_ascii=False), block.id


def generate(request, lite):
    """The pipeline's request answered from the lite result, in the shape a provider's return has."""
    raw, block = raw_answer(request.request_value, lite)
    first = block is not None and request.request_value.get('slot', 'initial') == 'initial'
    usage = lite.usage(block) if first else ReportedUsage(0, 0, 0, True)
    effort = request.policy.reasoning_effort
    if request.on_return is not None:
        request.on_return(ContentTransportReturn(raw, 'completed', None, 1, usage, True, dict(WITNESS), effort))
    try:
        decoded = request.result_type.decode_value(json.loads(raw))
    except ValueError:
        raise ContentFailure('INVALID_RESULT', logical_attempts=1, usage=usage, cleanup_verified=True,
            dispatch_witness=dict(WITNESS), raw_return=raw) from None
    return ContentResult(decoded, usage, 'lite', request.policy.model, 0.0, 1, cleanup_verified=True,
        dispatch_witness=dict(WITNESS), reasoning_effort=effort, raw_return=raw)
