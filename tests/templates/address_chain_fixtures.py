"""Two-step chains prove client translation against Python's own preparation."""

import json
import sys
from pathlib import Path

from packages.resume_core.template_address_map import build_address_map
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.address_map_fixtures import (ROOT, block_of, field, joined, literal, operation_request, text_request,
    trimmed)
from tests.templates.storage_fixtures import workspace
from tests.templates.test_template_preparation import proof, response

CHAINS = ROOT / 'tests/fixtures/synthetic/templates/address-chains.json'
STYLES = {'bold': False, 'italic': False, 'underline': False, 'strike': False, 'code': False,
    'textColor': 'default', 'backgroundColor': 'default'}


def content(block, kind='content', cell=None):
    return {'blockId': block, 'kind': kind, 'cellId': cell}


def key(container):
    return json.dumps([container['blockId'], container['kind'], container['cellId']], separators=(',', ':'))


def block_text(value, identifier):
    return ''.join(span.text if hasattr(span, 'text') else ''.join(child.text for child in span.content)
        for span in block_of(value, identifier).content)


def typing(container, offset, side, text='Y', end=None):
    return {'kind': 'replace_text', 'container': container, 'start': offset, 'end': offset if end is None else end,
        'text': text, 'styles': STYLES, 'side': side}


def repeated():
    return joined(lambda ref: [field('title', 'a-title', 'first-binding', 'first-occurrence', 'Shared title', ref),
        literal(' = ', ref), field('title', 'a-title', 'second-binding', 'second-occurrence', 'Shared title', ref)])


def segment_binding(address, role, start=None, end=None, block=None):
    found = [segment for entry in address.containers for segment in entry.segments
        if (block is None or entry.output.block_id == block) and segment.role == role
        and (start is None or segment.result.start == start) and (end is None or segment.result.end == end)]
    assert len(found) == 1, (role, start, end, found)
    span = found[0].result.span
    return {'kind': 'field', 'bindingId': span.binding_id} if span.kind == 'field' else (
        {'kind': 'manual_scope', 'fragmentId': span.fragment_id} if span.kind == 'manual_scope' else {'kind': 'literal'})


def created_block(address):
    [entry] = [entry for entry in address.containers if entry.created is not None]
    return entry.output.block_id


def plans():
    field_target = {'kind': 'field', 'bindingId': 'fragment-paper-a'}
    paper = content('block-paper-a')
    insert = lambda value: text_request(value, 8, 8, target=field_target)
    literal_edge = lambda value: text_request(value, 15, 15, '!', target={'kind': 'literal'})
    scoped = lambda value: text_request(value, 10, 22, 'merged')
    split = lambda value: operation_request(value, {'kind': 'split_block', 'blockId': 'block-paper-a',
        'beforeRevision': 1, 'offset': 8})
    merge = lambda value: operation_request(value, {'kind': 'merge_blocks', 'leadingId': 'block-paper-a',
        'leadingRevision': 1, 'trailingId': 'block-paper-b', 'trailingRevision': 1})
    inserted = lambda address: segment_binding(address, 'inserted')
    # Each expectation names Python's own result piece; translation must reach it from offset and side alone.
    return [
        ('delayed-inserted-before', joined, insert, typing(paper, 9, 'before'), {}, inserted),
        ('delayed-inserted-after', joined, insert, typing(paper, 9, 'after'), {},
            lambda address: segment_binding(address, 'retained_suffix', start=9)),
        ('delayed-inserted-interior', joined, insert, typing(paper, 9, 'interior'), {}, inserted),
        ('field-side-at-literal-insert', joined, literal_edge, typing(paper, 15, 'before'), {}, lambda _address: field_target),
        ('literal-side-after-insert', joined, literal_edge, typing(paper, 16, 'after'), {}, lambda _address: {'kind': 'literal'}),
        ('repeated-first-occurrence', repeated,
            lambda value: text_request(value, 15, 15, 'Q', target={'kind': 'field', 'bindingId': 'second-binding'}),
            typing(paper, 12, 'before'), {}, lambda _address: {'kind': 'field', 'bindingId': 'first-binding'}),
        ('scope-continue', joined, scoped, typing(paper, 16, 'before'), {}, inserted),
        ('scope-prefix-field', joined, scoped, typing(paper, 10, 'before'), {},
            lambda address: segment_binding(address, 'retained_prefix', end=10)),
        ('scope-interior-conflict', joined, scoped, typing(paper, 16, 'interior'), {}, None),
        ('empty-anchor', joined, lambda value: text_request(value, 3, 15, ''), typing(paper, 3, 'anchor'), {}, inserted),
        ('split-type-right', joined, split, typing(content('local-right'), 0, 'after'), {'created': 'local-right'},
            lambda address: segment_binding(address, 'retained_suffix', start=0, block=created_block(address))),
        ('split-type-left', joined, split, typing(paper, 8, 'before'), {},
            lambda address: segment_binding(address, 'retained_prefix', end=8, block='block-paper-a')),
        ('marks-interior', joined, lambda value: text_request(value, 5, 20, kind='set_marks', styles={'bold': True}),
            typing(paper, 6, 'interior'), {}, lambda address: segment_binding(address, 'restyled', start=5)),
        ('merge-type-trailing', lambda: workspace()[0], merge, typing(paper, 12, 'after'), {},
            lambda _address: {'kind': 'field', 'bindingId': 'fragment-paper-b'}),
        ('removed-block-conflict', lambda: workspace()[0], merge, typing(content('block-paper-b'), 0, 'after'), {'prior': 'Shared title'}, None),
        ('text-mismatch-conflict', joined, insert, typing(paper, 9, 'before'), {'prior': 'Different text'}, None),
        ('range-after-insert', joined, insert, typing(paper, 5, None, 'Z', end=12), {}, lambda _address: 'none'),
        ('split-after-insert', joined, insert, {'kind': 'split_block', 'container': paper, 'offset': 9,
            'created': 'local-next'}, {}, lambda _address: 'none'),
    ]


def expected(after, address, intent, locals_, expect):
    if expect is None:
        return {'kind': 'conflict'}
    operation, target = intent['operation'], expect(address)
    block = block_of(after, locals_.get(operation['container']['blockId'], operation['container']['blockId']))
    if operation['kind'] == 'split_block':
        return {'kind': 'operation', 'operation': {'kind': 'split_block', 'opId': intent['localId'], 'blockId': block.id,
            'beforeRevision': block.revision, 'offset': operation['offset']}}
    selected = {'blockId': block.id, 'beforeRevision': block.revision, 'cellId': None, 'field': 'content',
        'start': operation['start'], 'end': operation['end']}
    if target != 'none':
        selected['insertionTarget'] = target
    return {'kind': 'operation', 'operation': {'kind': 'replace_text', 'opId': intent['localId'], 'text': operation['text'],
        'styles': operation['styles'], 'range': selected}}


def chains():
    result = []
    for name, build, head, operation, options, expect in plans():
        value = build()
        request = head(value)
        base = response(value)
        prepared = prepare_edit(base, request)
        address = build_address_map(base, request, prepared)
        after = prepared.preview.workspace
        locals_ = {options['created']: created_block(address)} if options.get('created') else {}
        container = operation['container']
        prior = {key(container): options.get('prior') or block_text(after, locals_.get(container['blockId'], container['blockId']))}
        intent = {'localId': 'next-' + name, 'operation': operation, 'prior': prior}
        result.append({'name': name, 'resultWire': trimmed(prepared.preview), 'mapWire': canonical(address).decode(),
            'locals': locals_, 'intent': intent, 'expected': expected(after, address, intent, locals_, expect)})
    return {'scope': 'Head preparation results and maps for pure client translation; expectations are checked by Python',
        'cases': result}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


if __name__ == '__main__':
    if sys.argv[1:] != ['--write']:
        raise SystemExit('usage: address_chain_fixtures.py --write')
    CHAINS.write_text(encoded(chains()), encoding='utf-8')
