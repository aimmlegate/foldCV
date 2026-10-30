"""Synthetic large V7 workspace of about the measured real shape: ~3 MB JSON, ~1.8 MB facts, 1774 coverage rows.

Built only from tests/templates fixtures; no user data. Deterministic. Usage: build(root_of_checkout) -> (workspace, sources).
"""

import hashlib
import json
import sys


def build(root, *, records=720, coverage=1774, cells=5, evidence_text=90, issues=24, block_every=2):
    sys.path[:0] = [str(root), str(root) + '/services/api/src']
    from packages.resume_core.models.contracts import Source
    from packages.resume_core.models.template_facts import ExtensionRecord, WorkingFactsV2
    from packages.resume_core.models.template_workspace import WorkspaceV7
    from packages.resume_core.template_identity import capture_span
    from packages.resume_core.templates.compiler import canonical, sha256
    from tests.templates.storage_fixtures import PAPER_SCHEMA, package, presentation

    captured = package()
    # One source unit whose lines are the evidence slices of every cell and coverage row.
    lines = []
    for index in range(max(records * cells, coverage)):
        lines.append(('Line %05d: ' % index) + ('evidence text ' * (evidence_text // 14))[:evidence_text] + '\n')
    text = ''.join(lines)
    raw = text.encode()
    src = Source(id='source-large', revision=1, originalName='large.txt', mimeType='text/plain',
        byteSha256=sha256(raw), byteRef='sources/large.txt', parser='text', parserVersion='1',
        units=[{'id': 'unit-large', 'revision': 1, 'order': 0, 'text': text,
            'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []}], overlays=[], warnings=[])
    unit = src.units[0]
    offsets, cursor = [], 0
    for line in lines:
        offsets.append((cursor, cursor + len(line)))
        cursor += len(line)

    def span(index):
        start, end = offsets[index % len(offsets)]
        return capture_span(src, unit, start, end).model_dump(by_alias=True)

    keys = list(PAPER_SCHEMA['required'])
    extensions = []
    for number in range(records):
        values = {'title': 'Paper title %d about a long subject' % number, 'journal': 'Journal %d' % (number % 40),
            'year': 2000 + number % 25, 'url': 'https://example.test/paper/%d' % number, 'status': 'published'}
        extensions.append(ExtensionRecord(schemaVersion=1, id='paper-%d' % number, itemHandle='handle-%d' % number,
            revision=1, semanticType='papers', semanticSchemaHash=sha256(canonical(PAPER_SCHEMA)),
            cells=[{'id': 'cell-%d-%s' % (number, key), 'fieldKey': key, 'revision': 1, 'rawInput': str(values[key]),
                'typedValue': values[key], 'state': 'admitted', 'origin': 'source', 'userCorrected': False,
                'evidence': [span(number * cells + position)], 'observationIds': [], 'admissionReceiptIds': [],
                'manualScopeId': None} for position, key in enumerate(keys[:cells])],
            relations=[], observationIds=[], active=True))
    facts = WorkingFactsV2(schemaVersion=2, revision=1, records=[], tombstones=[], extensions=extensions,
        observations=[], relations=[], manualScopes=[])
    blocks = []
    for record in extensions[::block_every]:
        cell = record.cells[0]
        blocks.append({'id': 'block-' + record.id, 'revision': 1, 'type': 'paragraph', 'props': {},
            'children': [], 'provenance': [], 'presentation': presentation(captured),
            'content': [{'type': 'fact_field', 'bindingId': 'fragment-' + record.id,
                'bindingRootId': 'occurrence-' + record.id, 'occurrenceId': 'occurrence-' + record.id,
                'recordId': record.id, 'fieldKey': 'title', 'cellId': cell.id,
                'text': cell.raw_input, 'styles': {}, 'syncedFactRevision': 1,
                'complete': True, 'presentation': presentation(captured)},
                {'type': 'text', 'text': ' published in ' + record.cells[1].raw_input + '.', 'styles': {},
                 'presentation': presentation(captured)}]})
    rows = []
    for index in range(coverage):
        block = blocks[index % len(blocks)]
        rows.append({'span': span(index), 'itemHandle': 'handle-%d' % (index % records), 'blockIds': [block['id']],
            'disposition': 'accepted', 'reason': None})
    import_issues = []
    for index in range(issues):
        block = blocks[index % len(blocks)]
        import_issues.append({'id': 'issue-%d' % index, 'ruleId': None, 'taskId': 'task-%d' % index, 'targetIds': [],
            'blockIds': [block['id']], 'category': 'uncertain_interpretation', 'code': 'uncertain-%d' % index,
            'message': 'Uncertain interpretation %d' % index, 'importedFingerprint': sha256(('issue-%d' % index).encode()),
            'reviewInputHash': None, 'lifecycleId': 'life-%d' % index, 'state': 'active', 'retiredByAction': None})
    data = {'schemaVersion': 7, 'projectId': 'large-project', 'projectRevision': 1, 'documentRevision': 1,
        'title': 'Synthetic large project', 'titleManuallySet': False, 'createdAt': '2026-10-21T00:00:00Z',
        'updatedAt': '2026-10-21T00:00:00Z', 'project': {'schemaVersion': 6, 'projectId': 'large-project',
            'revision': 1, 'createdAt': '2026-10-21T00:00:00Z', 'sources': [src.model_dump(by_alias=True)],
            'evidenceRecords': [], 'facts': facts.model_dump(by_alias=True),
            'document': {'schemaVersion': 2, 'revision': 1, 'regions': [
                {'id': region, 'role': region, 'revision': 1, 'blocks': blocks if region == 'main' else []}
                for region in ['header', 'sidebar', 'main']]},
            'assets': [], 'operations': [], 'renders': [], 'templatePackage': captured.model_dump(by_alias=True),
            'importCoverage': rows, 'importIssues': import_issues, 'templateOperations': [], 'exports': []},
        'preDraft': None, 'formattingAsOf': {'precision': 'day', 'year': 2026, 'month': 10, 'day': 21},
        'sourceObservedAt': None, 'rulesUsed': None, 'syncRecords': [], 'mutationReplay': [], 'warnings': []}
    return WorkspaceV7.model_validate(data), {src.id: raw}


def sizes(workspace):
    from packages.resume_core.project_repository import rich_snapshot_bytes
    from packages.resume_core.templates.compiler import canonical
    project = workspace.project
    return {'workspace': len(rich_snapshot_bytes(workspace)), 'facts': len(canonical(project.facts)),
        'document': len(canonical(project.document)), 'coverage': len(canonical([row.model_dump(mode='json', by_alias=True) for row in project.import_coverage])),
        'sources': len(canonical([src.model_dump(mode='json', by_alias=True) for src in project.sources])), 'package': len(canonical(project.template_package)),
        'blocks': len(list(project.document.blocks())), 'coverageRows': len(project.import_coverage),
        'extensionRecords': len(project.facts.extensions)}


if __name__ == '__main__':
    root = sys.argv[1]
    workspace, _sources = build(root)
    print(json.dumps(sizes(workspace), indent=1))
