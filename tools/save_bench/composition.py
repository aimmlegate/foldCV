"""Composition of a V7 workspace: bytes by section and by duplicate class. Reads only; nothing is copied. Usage:
python -I composition.py <checkout-root> generic F10|F07   (scripted import through the real pipeline, temporary store)
python -I composition.py <checkout-root> file <path/to/workspace.json>
python -I composition.py <checkout-root> synthetic
"""

import asyncio
import collections
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HEX = re.compile(r'^[0-9a-f]{64}$')


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def walk(value, visit, path=()):
    visit(value, path)
    if isinstance(value, dict):
        for key, item in value.items():
            walk(item, visit, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            walk(item, visit, (*path, index))


def analyze(data):
    project = data['project']
    out = {'total': size(data)}
    out['top'] = {key: size(value) for key, value in data.items() if key != 'project'}
    out['project'] = {key: size(value) for key, value in project.items()}
    facts = project['facts']
    out['facts'] = {key: size(value) for key, value in facts.items() if isinstance(value, (list, dict))}
    units = {(s['id'], u['id']): u['text'] for s in project['sources'] for u in s['units']}
    out['sourceTextBytes'] = sum(len(t.encode()) for t in units.values())
    counters = collections.Counter()
    hashes, hash_values = 0, collections.Counter()
    presentation_values, presentation_count = collections.Counter(), 0
    span_texts, span_copy_bytes, spans_with_text, spans_without_text = set(), 0, 0, 0
    nulls, empties = 0, 0
    keys_bytes = 0

    def visit(value, path):
        nonlocal hashes, presentation_count, span_copy_bytes, spans_with_text, spans_without_text, nulls, empties, keys_bytes
        if isinstance(value, str) and HEX.match(value):
            hashes += 1
            hash_values[value] += 1
        if value is None:
            nulls += 1
        if value == [] or value == {} or value == '':
            empties += 1
        if isinstance(value, dict):
            keys_bytes += sum(len(key) + 3 for key in value)
            if 'packageHash' in value and 'viewKey' in value and 'styleToken' in value:
                presentation_count += 1
                presentation_values[json.dumps(value, sort_keys=True)] += 1
                counters['presentationBytes'] += size(value)
            if 'sourceId' in value and 'unitId' in value and ('start' in value or 'text' in value):
                if isinstance(value.get('text'), str):
                    spans_with_text += 1
                    span_copy_bytes += len(value['text'].encode())
                    span_texts.add(value['text'])
                else:
                    spans_without_text += 1
                counters['spanBytes'] += size(value)
            if path and path[0] == 'project' and len(path) >= 4 and path[1] == 'document' and 'provenance' in value:
                counters['provenanceBytes'] += size(value['provenance'])
                counters['blocks'] += 1
            if isinstance(value.get('type'), str) and value.get('type') in {'text', 'fact_field', 'manual_scope', 'link'} and 'styles' in value:
                counters['inlineSpans'] += 1
                counters['inlineSpanBytes'] += size(value)
                counters['inlineTextBytes'] += len(value.get('text', '').encode())
    walk(data, visit)
    out['hashes'] = {'count': hashes, 'bytes': hashes * 66, 'distinct': len(hash_values),
        'top': hash_values.most_common(3)}
    out['presentationRefs'] = {'count': presentation_count, 'bytes': counters['presentationBytes'],
        'distinctValues': len(presentation_values)}
    out['evidenceSpans'] = {'withText': spans_with_text, 'withoutText': spans_without_text, 'bytes': counters['spanBytes'],
        'textCopyBytes': span_copy_bytes, 'uniqueTextBytes': sum(len(t.encode()) for t in span_texts)}
    out['document'] = {'blocks': counters['blocks'], 'provenanceBytes': counters['provenanceBytes'],
        'inlineSpans': counters['inlineSpans'], 'inlineSpanBytes': counters['inlineSpanBytes'],
        'inlineTextBytes': counters['inlineTextBytes']}
    out['coverage'] = {'rows': len(project['importCoverage']), 'bytes': size(project['importCoverage'])}
    out['replay'] = {'rows': len(data.get('mutationReplay', [])), 'bytes': size(data.get('mutationReplay', []))}
    out['nulls'] = nulls
    out['emptyValues'] = empties
    out['keyBytes'] = keys_bytes
    return out


async def generic(root, name):
    from tests.templates.generic_fixtures import generic_import
    work = tempfile.mkdtemp(prefix='foldcv-spc-compose-', dir='/private/tmp')
    from pathlib import Path
    _fixture, _result, workspace, _originals = await generic_import(Path(work), name)
    return workspace


def main():
    root, mode = sys.argv[1], sys.argv[2]
    sys.path[:0] = [root, root + '/services/api/src']
    if mode == 'file':
        data = json.load(open(sys.argv[3]))
    elif mode == 'synthetic':
        import fixture
        workspace, _ = fixture.build(root)
        data = workspace.model_dump(mode='json', by_alias=True)
    else:
        workspace = asyncio.run(generic(root, sys.argv[3]))
        data = workspace.model_dump(mode='json', by_alias=True)
        out = tempfile.mkstemp(prefix='foldcv-composition-' + sys.argv[3] + '-', suffix='.json')[1]
        json.dump(data, open(out, 'w'), ensure_ascii=False)
        print('saved', out)
    print(json.dumps(analyze(data), indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
