"""Synthetic extension data with identities independent of display wording."""

import json
from pathlib import Path

from packages.resume_core.models.contracts import Source
from packages.resume_core.models.template_facts import ExtensionRecord, WorkingFactsV2
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.template_identity import capture_span
from packages.resume_core.templates.compiler import canonical, compile_bytes, sha256
from packages.resume_core.templates.loading import load_definition
from packages.resume_core.templates.store import BUNDLED_TEMPLATE


PAPER_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['title', 'journal', 'year', 'url', 'status'],
    'properties': {
        'title': {'type': ['string', 'null']},
        'journal': {'type': ['string', 'null']},
        'year': {'type': ['integer', 'null']},
        'url': {'type': ['string', 'null']},
        'status': {'type': ['string', 'null'], 'enum': ['published', None]},
    },
}


def package():
    config = load_definition(BUNDLED_TEMPLATE.read_bytes())
    config['template'] = {'id': 'synthetic-storage', 'revision': '1', 'name': 'Storage fixture', 'default_locale': 'en'}
    config['content_definitions'] = {}
    config['operations'] = []
    config['fact_types'] = [{'id': 'papers', 'schema_version': '1', 'schema': PAPER_SCHEMA,
        'builtin_kind': None, 'relations': []}]
    config['blocks'] = [{'id': 'arbitrary-paper-view', 'mode': 'model',
        'selectors': [{'kind': 'source', 'id': 'all'}],
        'content_schema': {'type': 'array', 'items': PAPER_SCHEMA},
        'bindings': [{'pointer': '/*/' + key, 'semantic_type': 'papers', 'field': key, 'relation': None}
            for key in PAPER_SCHEMA['required']],
        'extract': [], 'rewrite': {'fields': [], 'instructions': []}, 'checks': [],
        'depends_on': [], 'operation': None, 'when': None, 'placement': {'region': 'main', 'order': 1},
        'view': {'mode': 'items', 'heading': 'none', 'title': {}, 'inset': 0, 'item_gap': 6,
            'nodes': [{'type': 'text', 'style': 'body', 'field': '/title'}]}}]
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def source():
    return source_fixture('F05')


def source_fixture(name):
    raw = Path('tests/fixtures/synthetic/templates/' + name + '.txt').read_bytes()
    text = raw.decode()
    value = Source(id='source-papers', revision=1, originalName=name + '.txt', mimeType='text/plain',
        byteSha256=sha256(raw), byteRef='sources/papers.txt', parser='text', parserVersion='1',
        units=[{'id': 'unit-papers', 'revision': 1, 'order': 0, 'text': text,
            'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []}], overlays=[], warnings=[])
    return value, raw


def presentation(captured):
    return {'packageHash': captured.package_hash, 'viewKey': 'arbitrary-paper-view', 'styleToken': 'body',
        'templateInstanceId': None, 'itemHandle': None,
        'overrides': {'font': None, 'size': None, 'color': None, 'alignment': None, 'bold': None, 'italic': None}}


def papers():
    src, _ = source()
    span = capture_span(src, src.units[0]).model_dump(by_alias=True)
    records = []
    for suffix, journal, year, url in [('a', 'Journal North', 2024, 'https://example.test/a'),
                                       ('b', 'Journal South', 2025, 'https://example.test/b')]:
        values = {'title': 'Shared title', 'journal': journal, 'year': year, 'url': url, 'status': 'published'}
        records.append(ExtensionRecord(schemaVersion=1, id='paper-' + suffix, itemHandle='handle-' + suffix,
            revision=1, semanticType='papers', semanticSchemaHash=sha256(canonical(PAPER_SCHEMA)),
            cells=[{'id': suffix + '-' + key, 'fieldKey': key, 'revision': 1,
                'rawInput': str(value), 'typedValue': value, 'state': 'admitted', 'origin': 'source',
                'userCorrected': False, 'evidence': [span], 'observationIds': [], 'admissionReceiptIds': [],
                'manualScopeId': None} for key, value in values.items()],
            relations=[], observationIds=[], active=True))
    return WorkingFactsV2(schemaVersion=2, revision=1, records=[], tombstones=[], extensions=records,
        observations=[], relations=[], manualScopes=[])


def workspace():
    captured = package()
    src, raw = source()
    facts = papers()
    blocks = []
    for record in facts.extensions:
        cell = record.cells[0]
        blocks.append({'id': 'block-' + record.id, 'revision': 1, 'type': 'paragraph', 'props': {},
            'children': [], 'provenance': [], 'presentation': presentation(captured),
            'content': [{'type': 'fact_field', 'bindingId': 'fragment-' + record.id,
                'bindingRootId': 'occurrence-' + record.id, 'occurrenceId': 'occurrence-' + record.id,
                'recordId': record.id, 'fieldKey': 'title', 'cellId': cell.id,
                'text': cell.raw_input, 'styles': {}, 'syncedFactRevision': 1,
                'complete': True, 'presentation': presentation(captured)}]})
    data = {'schemaVersion': 7, 'projectId': 'template-project', 'projectRevision': 1, 'documentRevision': 1,
        'title': 'Synthetic papers', 'titleManuallySet': False, 'createdAt': '2026-10-21T00:00:00Z',
        'updatedAt': '2026-10-21T00:00:00Z', 'project': {'schemaVersion': 6, 'projectId': 'template-project',
            'revision': 1, 'createdAt': '2026-10-21T00:00:00Z', 'sources': [src.model_dump(by_alias=True)],
            'evidenceRecords': [], 'facts': facts.model_dump(by_alias=True),
            'document': {'schemaVersion': 2, 'revision': 1, 'regions': [
                {'id': region, 'role': region, 'revision': 1, 'blocks': blocks if region == 'main' else []}
                for region in ['header', 'sidebar', 'main']]},
            'assets': [], 'operations': [], 'renders': [], 'templatePackage': captured.model_dump(by_alias=True),
            'importCoverage': [], 'importIssues': [], 'templateOperations': [], 'exports': []},
        'preDraft': None, 'formattingAsOf': {'precision': 'day', 'year': 2026, 'month': 10, 'day': 21},
        'sourceObservedAt': None, 'rulesUsed': None, 'syncRecords': [], 'mutationReplay': [], 'warnings': []}
    return WorkspaceV7.model_validate(data), {src.id: raw}


def literal(text, ref):
    return {'type': 'text', 'text': text, 'styles': {}, 'presentation': ref}


def field(key, cell, binding, occurrence, text, ref, *, complete=True):
    return {'type': 'fact_field', 'bindingId': binding, 'bindingRootId': occurrence, 'occurrenceId': occurrence,
        'recordId': 'paper-a', 'fieldKey': key, 'cellId': cell, 'text': text, 'styles': {}, 'syncedFactRevision': 1,
        'complete': complete, 'presentation': ref}


def joined(content=None):
    """The papers workspace whose first entry joins two bound fields with literal text."""
    before, _sources = workspace()
    data = before.model_dump(by_alias=True)
    block = data['project']['document']['regions'][2]['blocks'][0]
    ref = block['content'][0]['presentation']
    block['content'] = content(ref) if content else [literal('By ', ref),
        field('title', 'a-title', 'fragment-paper-a', 'occurrence-paper-a', 'Shared title', ref),
        literal(' / ', ref), field('journal', 'a-journal', 'binding-journal', 'occurrence-journal', 'Journal North', ref),
        literal('.', ref)]
    return WorkspaceV7.model_validate(data)
