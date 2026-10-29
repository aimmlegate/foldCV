"""A block that extracts its entries on their own (D117): the papers package declared per_entry, a source with one
paper per line, and scripted replies for the outline, each entry and the outline review."""

import json
import re

from packages.resume_core.models.contracts import Source
from packages.resume_core.templates.compiler import compile_bytes, sha256
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.storage_fixtures import package

LINES = ['Alex Example', 'Publications',
    'Reliable Queues, Systems Notes, 2024, https://example.org/paper-a',
    'Reliable Queues, Queue Review, 2025, https://example.org/paper-b',
    'Reliable Queues, Stream Letters, 2026, https://example.org/paper-c',
    'Reliable Queues, Ledger Digest, 2027, https://example.org/paper-d']
TITLES = {'paper-a': 'Systems Notes', 'paper-b': 'Queue Review', 'paper-c': 'Stream Letters', 'paper-d': 'Ledger Digest'}


def entries_package():
    config = package().definition.model_dump(mode='json', by_alias=True)
    config['blocks'][0]['per_entry'] = True
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def lines_source(count=2):
    """The papers source with one paper per line: the first `count` papers after the heading lines."""
    raw = ('\n'.join(LINES[:2 + count]) + '\n').encode()
    value = Source(id='source-papers', revision=1, originalName='lines.txt', mimeType='text/plain',
        byteSha256=sha256(raw), byteRef='sources/papers.txt', parser='text', parserVersion='1',
        units=[{'id': 'unit-papers', 'revision': 1, 'order': 0, 'text': raw.decode(),
            'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []}], overlays=[], warnings=[])
    return value, raw


def ref_of(value, text):
    """The ref of the offered line that holds `text`, in the request `value`."""
    return next(option['ref'] for option in value['evidence'] if text in option['text'] and '\n' not in option['text'].strip())


def outline_answer(value, keys=('paper-a', 'paper-b')):
    return {'entries': [{'title': TITLES[key], 'first': ref_of(value, key), 'last': ref_of(value, key)} for key in keys]}


def entry_answer(value):
    """One paper per paper line of the entry, cited by its line; [] when the entry's lines state none."""
    table = {option['ref']: option for option in value['evidence']}
    papers, cited = [], []
    for ref in value['entry']['lines']:
        match = re.fullmatch(r'Reliable Queues, (.+), (\d{4}), (\S+)\n?', table[ref]['text'])
        if match:
            papers.append({'title': 'Reliable Queues', 'journal': match.group(1), 'year': int(match.group(2)),
                'url': match.group(3), 'status': 'published'})
            cited.append(table[ref]['span'])
    keys = ['p' + str(index) for index in range(len(papers))]
    return {'schemaVersion': 1, 'payload': papers,
        'discoveries': [{'key': key, 'semanticType': 'papers', 'pointer': '/' + str(index)} for index, key in enumerate(keys)],
        'fields': [{'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': field, 'pointer': '/' + str(index) + '/' + field,
            'evidence': [span], 'effectiveCellIds': []} for index, (key, paper, span) in enumerate(zip(keys, papers, cited)) for field in paper],
        'lineage': [{'kind': 'add', 'parents': [], 'children': keys}] if keys else [], 'relations': []}


def satisfied(value):
    return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
        'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}


def entries_script(*, outline=None, review=None, entry=None, reviews=None):
    """Scripted replies by request kind; each override gets the request value and returns the answer."""
    def script(_request, value):
        slot = value.get('slot')
        if slot == 'outline':
            return outline(value) if outline else outline_answer(value)
        if slot == 'outline_review':
            return review(value) if review else {'missing': [], 'remarks': []}
        if 'targets' in value:
            return reviews(value) if reviews else satisfied(value)
        return entry(value) if entry else entry_answer(value)
    return script
