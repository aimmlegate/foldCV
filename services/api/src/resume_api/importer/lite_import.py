"""The lite import inside the template pipeline.

The lite scheme (packages/resume_core/importing/lite) makes its own model calls and gives each block's content with
the source spans of every value. The pipeline then runs as it always does, and every request it would send to a model
is answered here from that result: a block's extraction with the block's content, a review with «every check holds».
Admission, receipts, the document and the publication stay the pipeline's own."""

import contextvars
from copy import deepcopy
import json
import threading
import time

from packages.resume_core.importing.lite.checks import cues
from packages.resume_core.importing.lite.lines import CV
from packages.resume_core.importing.lite.scheme import Import
from packages.resume_core.importing.lite.words import line_words, words
from packages.resume_core.importing.template_identity import _binding_instances, empty_value
from packages.resume_core.importing.template_import import ACCOUNT_STOP
from jsonschema import Draft202012Validator

from packages.resume_core.templates.projection import (FORMAT_CHECKER, OFFLINE_REGISTRY, SchemaFailure, pointer_tokens,
    validate_payload)
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
WRITTEN_MESSAGE = ('Этот текст написан моделью по данным резюме: в исходном файле такого раздела нет. '
                   'Проверьте его и поправьте, если нужно.')


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

    def __init__(self, provider, adapter, model, effort, temp_root, cancel, remaining, permit, cap=None):
        """cap: the most model calls this import may make (its captured call cap); None, no limit."""
        self.provider, self.adapter, self.model, self.effort = provider, adapter, model, effort
        self.temp_root, self.cancel, self.remaining, self.permit = temp_root, cancel, remaining, permit
        self.rows, self.lock, self.cap, self.started = [], threading.Lock(), cap, 0
        self.envelope = adapter != 'claude_cli'

    def call(self, kind, block, prompt, schema):
        """One call: (the reply's object or None, its row with the usage and an error code)."""
        row = {'kind': kind, 'block': block, 'errorCode': None, 'usage': None, 'seconds': None}
        started, payload, usage = time.monotonic(), None, None
        with self.lock:
            # The import's call cap holds for the scheme's calls: one past it is not made, and the import stops.
            refused = self.cap is not None and self.started >= self.cap
            if refused:
                row['errorCode'], row['seconds'] = 'IMPORT_CALL_CAP', 0.0
                self.rows.append(row)
            else:
                self.started += 1
        if refused:
            return None, row
        try:
            with CALLS.hold(self.adapter, self.cancel):
                # The time left is read after the wait for a place, so a call that waited does not run past the import's
                # deadline.
                seconds = self.remaining()
                if self.cancel.is_set() or seconds <= 0:
                    raise ContentFailure('CANCELLED' if self.cancel.is_set() else 'DEADLINE_EXCEEDED')
                request = ContentInput(prompt, dynamic_result(schema) if self.envelope else root_model(schema),
                    GenerationPolicy(self.model, timeout_seconds=seconds, allow_repair=False, reasoning_effort=self.effort))
                with OperationFiles(self.temp_root).open() as files:
                    owned = getattr(self.provider, 'generate_owned', None)
                    if self.permit is not None and owned is not None:
                        result = owned(request, files, self.cancel, self.permit)
                    else:
                        result = self.provider.generate(request, files, self.cancel)
            value, usage = result.value, result.usage
            payload = value.payload if hasattr(value, 'payload') else value.model_dump(mode='json')
            try:
                # The whole reply against its schema, nested values too: the root model of the Claude path checks only
                # the top keys, and the scheme reads the reply without further checks.
                validate_payload(schema, payload)
            except SchemaFailure:
                payload, row['errorCode'] = None, 'INVALID_RESULT'
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

    # What snapshot() keeps: the reading as plain data. The lines' texts and order come from the sources again.
    KEPT = ('state', 'failure', 'table', 'failed', 'other', 'written', 'hidden', 'lack', 'forms', 'placed', 'kept', 'live',
            'cited', 'shown', 'spent')

    def snapshot(self):
        """The reading as JSON text, for the import's record: an import that stopped continues from it."""
        plain = lambda value: sorted(value) if isinstance(value, (set, frozenset)) else value
        value = {name: plain(getattr(self, name)) for name in self.KEPT}
        value['table'] = {block: [payload, evidence] for block, (payload, evidence) in self.table.items()}
        value['shown'] = {block: sorted(found) for block, found in self.shown.items()}
        value['spent'] = [[key, held] for key, held in self.spent.items()]
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

    @classmethod
    def restored(cls, text, sources, package, answered=()):
        """The reading an earlier run of this import kept. answered: the blocks whose tasks already have results; the
        tokens of the scheme's calls were reported with them."""
        value, self = json.loads(text), cls.__new__(cls)
        for name in cls.KEPT:
            setattr(self, name, value[name])
        self.table = {block: (payload, evidence) for block, (payload, evidence) in value['table'].items()}
        self.failed, self.hidden, self.forms, self.kept = (set(value[name]) for name in ('failed', 'hidden', 'forms', 'kept'))
        self.live = None if value['live'] is None else set(value['live'])
        self.shown = {block: set(found) for block, found in value['shown'].items()}
        lines = CV(sources).lines
        self.texts = {line.ref: ' '.join(line.text.split()) for line in lines}
        self.order = {line.ref: index for index, line in enumerate(lines)}
        self.notes, self.stop = {'dropped': []}, None
        # The scheme's calls were counted when the reading was kept; a kept reading makes none.
        self.calls, self.capped = None, False
        self.blocks = {block.id: block for block in package.definition.blocks}
        self.schemas = {block.id: block.full_schema for block in package.blocks}
        self.lock, self.answered = threading.Lock(), set(answered)
        # What is left to report: the calls of the blocks not answered yet (the map's went with the first answer).
        self.spent = {key: held for key, held in value['spent'] if key not in self.answered and (key is not None or not self.answered)}
        return self

    def __init__(self, importer, calls, package):
        self.state = importer.state
        self.table, self.failed = dict(importer.table), set(importer.failed)
        self.other, self.notes = list(importer.other), importer.notes
        # Blocks the source has no text for, written by the scheme from its lines: {block: [pointer]}.
        self.written = dict(importer.written)
        self.texts = {line.ref: ' '.join(line.text.split()) for line in importer.lines}
        self.order = {line.ref: index for index, line in enumerate(importer.lines)}
        self.hidden = set(importer.hidden)
        self.live = None if importer.live is None else {*importer.live, 'projects'}
        self.lack = dict(importer.lack)
        # Hidden lines that are form, not content: a label of a list («Задачи:») and a section heading of the CV.
        cue = cues(importer.data)
        self.forms = {ref for ref in self.hidden if label_like(self.texts[ref]) and ref in importer.labels
                      or heading_like(self.texts[ref], cue[ref])}
        placed = (importer.map or {}).get('blocks') or {}
        self.placed = {ref: block for block, refs in placed.items() for ref in reversed(refs)}
        self.kept = {ref for item in self.other for ref in item['refs']}
        # Each block's lines that the scheme's values cite, and the words those values show.
        units = {}
        for line in importer.lines:
            span = line.span.model_dump(mode='json', by_alias=True)
            units.setdefault((span['sourceId'], span['unitId']), []).append((span['start'], span['end'], line.ref))
        self.blocks = {block.id: block for block in package.definition.blocks}
        self.schemas = {block.id: block.full_schema for block in package.blocks}
        self.cited, self.shown = {}, {}
        for block, (payload, evidence) in list(self.table.items()):
            refs = {ref for spans in evidence.values() for span in spans
                    for start, end, ref in units.get((span['sourceId'], span['unitId']), ())
                    if start <= span['start'] and span['end'] <= end}
            self.cited[block] = sorted(refs, key=self.order.get)
            self.shown[block] = shown_words(payload)
            # A list item that breaks the template's own schema (a name with a comma, a value too long) is left out
            # alone; the whole block would be refused for it. Its lines then count as dropped.
            if block in self.schemas:
                self.table[block] = fitted(self.schemas[block], payload, evidence, self.notes, block)
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
        # The calls the scheme made of the import's cap, and whether it ran into the cap.
        self.calls = getattr(calls, 'started', None)
        if self.calls is None:
            self.calls = len(calls.rows)
        self.capped = any(row['errorCode'] == 'IMPORT_CALL_CAP' for row in calls.rows)
        # Why a scheme that read no map failed, as the import's own error code.
        codes = {row['errorCode'] for row in calls.rows}
        self.failure = ('CANCELLED' if 'CANCELLED' in codes else 'IMPORT_PROCESSING_EXHAUSTED' if 'DEADLINE_EXCEEDED' in codes
                        else 'IMPORT_INVALID_RESULT')

    def usage(self, block):
        with self.lock:
            total = [0, 0, 0]
            for key in ([block] if self.answered else [block, None]):
                for index, value in enumerate(self.spent.pop(key, [0, 0, 0])):
                    total[index] += value
            self.answered.add(block)
        return ReportedUsage(total[0], total[1], total[2], True)

    def offered(self, block, options):
        """Of the evidence a block's request offers, the refs its content needs: for each span the content cites, the
        smallest offered text that holds it (as evidence_ref finds it when the reply is built)."""
        units = {}
        for option in options:
            units.setdefault((option.span.source_id, option.span.unit_id), []).append(option)
        needed = set()
        for spans in self.table.get(block, (None, {}))[1].values():
            for span in spans:
                holders = [option for option in units.get((span['sourceId'], span['unitId']), ())
                           if option.span.start <= span['start'] and span['end'] <= option.span.end]
                if holders:
                    needed.add(min(holders, key=lambda option: option.span.end - option.span.start).ref)
        return needed

    def owner(self, name):
        """The block whose task keeps a line: its own, else identity (a line in no block of the template, or in a
        block this document does not fill: one of the other role branch)."""
        name = (name or 'identity').split('.')[0]
        return name if name in self.blocks and (self.live is None or name in self.live) else 'identity'

    # Each of the three gives rows (text, words): words are the words of the line the document does not show when it
    # shows the rest of the line, None when it shows nothing of it.

    def other_of(self, block):
        """The lines kept as «other» that belong to this block (those of no block go with identity)."""
        return [(self.texts[ref], self.lack.get(ref)) for item in self.other if self.owner(item['owner']) == block
                for ref in item['refs'] if ref in self.texts]

    def dropped_of(self, block, payload):
        """The lines whose value the scheme read and the admission dropped: the scheme's content showed every word of
        the line and the admitted content does not."""
        after, found = shown_words(payload), []
        for ref in self.cited.get(block, ()):
            need = line_words(self.texts[ref])
            if ref not in self.hidden and ref not in self.kept and need and need <= self.shown[block] and not need <= after:
                found.append((self.texts[ref], sorted(need - after) if need & after else None))
        return found

    def hidden_of(self, block, *, form=True):
        """The lines the map hid that stand in this block (those of no block go with identity). form=False leaves out
        the lines that are form: a list's label and a section heading."""
        return [(self.texts[ref], None) for ref in sorted(self.hidden - self.kept, key=self.order.get)
                if self.owner(self.placed.get(ref)) == block and any(char.isalnum() for char in self.texts[ref])
                and (form or ref not in self.forms)]


def writing_rules(package):
    """The rules for each block the scheme may write when the CV has no text for it: the template's rules of wording
    for that block (lite/rules.py), not the legacy import's prompts. A block the template gives no rewrite field is
    never written."""
    from packages.resume_core.importing.lite.prompts import WRITE
    from packages.resume_core.importing.lite.rules import block_rules
    return {block.id: block_rules(block.id, package.definition) for block in package.definition.blocks
            if block.id in WRITE and block.rewrite.fields}


def custom_blocks(package):
    """The template's own blocks: the ones a model fills that the scheme has no request of its own for. Each is read
    by its schema, with what it holds and its instructions in the template author's words."""
    from packages.resume_core.importing.lite import custom, prompts
    known = {name for name, _holds in prompts.MAP_BLOCKS}
    schemas = {block.id: block.full_schema for block in package.blocks}
    return {block.id: {'holds': custom.described(block), 'schema': schemas[block.id],
                       'instructions': [*block.extract, *block.rules]}
            for block in package.definition.blocks if block.mode == 'model' and block.id not in known}


def run(sources, package, calls, stage=None):
    """One lite import of these sources; calls: LiteCalls."""
    importer = Import(sources, calls, envelope=calls.envelope, writing=writing_rules(package),
        blocks=[block.id for block in package.definition.blocks], custom=custom_blocks(package))
    importer.stage = stage
    importer.run()
    return LiteResult(importer, calls, package)


def label_like(text):
    """A label of a list is a few words («Задачи:», «Tech stack:»); a longer line that ends with a colon is content."""
    return len(text.rstrip(':').split()) <= 3


def fitted(schema, payload, evidence, notes, block):
    """The content without the list items that break the template's schema, and the cited spans of the items left, under
    their new numbers. Content with a fault that is no list item's is returned as it is (the block then fails whole)."""
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER, registry=OFFLINE_REGISTRY)
    try:
        errors = list(validator.iter_errors(payload))
    except Exception:
        return payload, evidence
    bad = {}
    for error in errors:
        path = list(error.absolute_path)
        at = next((index for index in range(len(path) - 1, -1, -1) if isinstance(path[index], int)), None)
        if at is None:
            return payload, evidence
        bad.setdefault(tuple(path[:at]), set()).add(path[at])
    if not bad:
        return payload, evidence
    payload, moved = deepcopy(payload), {}
    for container, gone in bad.items():
        items = payload
        for token in container:
            items = items[token]
        kept = [index for index in range(len(items)) if index not in gone]
        moved[tuple(map(str, container))] = {str(old): str(new) for new, old in enumerate(kept)}
        items[:] = [items[index] for index in kept]
        notes['dropped'].extend({'block': block, 'pointer': pointer_of([*map(str, container), str(index)]),
                                 'why': 'breaks the template schema'} for index in sorted(gone))
    cited = {}
    for pointer, spans in evidence.items():
        tokens = pointer_tokens(pointer)
        for container, numbers in moved.items():
            size = len(container)
            if tuple(tokens[:size]) == container and len(tokens) > size:
                tokens = None if tokens[size] not in numbers else [*tokens[:size], numbers[tokens[size]], *tokens[size + 1:]]
                break
        if tokens is not None:
            cited[pointer_of(tokens)] = spans
    return payload, cited


def heading_like(text, cue):
    """A hidden line that reads as a section heading: a few words with no number, address or value, set as a heading,
    in bold or in capitals."""
    plain = text.strip().rstrip(':').strip()
    short = 0 < len(plain.split()) <= 5 and not any(char.isdigit() for char in plain) and '@' not in plain and ':' not in plain
    return short and (cue['heading'] or cue['bold'] or plain.isupper())


def shown_words(payload):
    """The words a block's content shows, as the scheme counts them: a period by its dates, not by its raw text."""
    found = set()

    def visit(value, key=None):
        if isinstance(value, dict):
            for name, part in value.items():
                if not (key == 'period' and name == 'raw'):
                    visit(part, name)
        elif isinstance(value, (list, tuple)):
            for part in value:
                visit(part, key)
        elif value is not None and not isinstance(value, bool):
            found.update(words(str(value)))
    visit(payload)
    return found


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
        # The block is shown as not filled. Its lines are kept and marked by the notices the pipeline makes from
        # other_of and hidden_of (a failed scheme never comes here: the import stops before its tasks).
        return INVALID, block.id
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
