"""F01 keeps employer and team-result evidence in distinct retained source units."""

import json
from unittest import mock
from pathlib import Path

from packages.resume_core.models.contracts import Source
from packages.resume_core.template_identity import capture_span
from packages.resume_core.templates.compiler import compile_bytes, sha256
from packages.resume_core.templates import compiler
from packages.resume_core.templates.loading import load_definition
from packages.resume_core.templates.store import BUNDLED_TEMPLATE


def claim_fixture(*, dependent=False):
    raw = Path('tests/fixtures/synthetic/templates/F01.txt').read_bytes()
    source = Source(id='source-f01', revision=1, originalName='F01.txt', mimeType='text/plain', byteSha256=sha256(raw),
        byteRef='sources/f01.txt', parser='text', parserVersion='1', units=[{'id': 'f01-line-' + str(index),
            'revision': 1, 'order': index, 'text': text, 'location': {'kind': 'pasted', 'index': index, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []} for index, text in enumerate(raw.decode().splitlines())],
        overlays=[], warnings=[])
    employment = {'type': 'object', 'additionalProperties': False, 'required': ['employer', 'role'],
        'properties': {'employer': {'type': 'string'}, 'role': {'type': 'string'}}}
    metric = {'type': 'object', 'additionalProperties': False, 'required': ['reduction', 'attribution', 'text'],
        'properties': {'reduction': {'type': ['number', 'null']}, 'attribution': {'type': 'string'}, 'text': {'type': 'string'}}}
    config = load_definition(BUNDLED_TEMPLATE.read_bytes())
    config['template'] = {'id': 'synthetic-f01-admission', 'revision': '1', 'name': 'F01 admission', 'default_locale': 'en'}
    config['content_definitions'], config['operations'] = {}, []
    config['fact_types'] = [{'id': 'employers', 'schema_version': '1', 'schema': employment, 'builtin_kind': None, 'relations': []},
        {'id': 'claims', 'schema_version': '1', 'schema': metric, 'builtin_kind': None,
            'relations': [{'kind': 'owned_by', 'target_types': ['employers']}]}]
    config['blocks'] = [{'id': 'arbitrary-paper-view', 'mode': 'model', 'selectors': [{'kind': 'source', 'id': 'all'}],
        'content_schema': {'type': 'object', 'additionalProperties': False, 'required': ['employment', 'claim'],
            'properties': {'employment': employment, 'claim': metric}},
        'bindings': [{'pointer': '/' + path + '/' + field, 'semantic_type': semantic, 'field': field, 'relation': None}
            for path, semantic, schema in [('employment', 'employers', employment), ('claim', 'claims', metric)]
            for field in schema['required']], 'extract': [], 'rewrite': {'fields': [], 'instructions': []}, 'checks': [],
        'depends_on': [], 'operation': None, 'when': None, 'placement': {'region': 'main', 'order': 1},
        'view': {'mode': 'object', 'heading': 'none', 'title': {}, 'inset': 0, 'item_gap': 6,
            'nodes': [{'type': 'text', 'style': 'body', 'field': '/employment/employer'}]}}]
    if dependent:
        config['operations'] = [{'id': 'dependent-facts', 'kind': 'preserve_stated_text', 'version': 1,
            'inputs': [{'kind': 'fact_type', 'id': 'claims'}, {'kind': 'fact_type', 'id': 'employers'},
                {'kind': 'block', 'id': 'arbitrary-paper-view'}], 'depends_on': [], 'parameters': {}}]
    # `dependent-facts` models a stored package whose operation kind the runtime refuses; a new package would not compile.
    with mock.patch.object(compiler, 'check_runs', lambda _definition: None):
        captured = compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    return captured, source, raw


def claim_proposal(source):
    employer = capture_span(source, source.units[2]).model_dump(by_alias=True)
    metric = capture_span(source, source.units[-1]).model_dump(by_alias=True)
    return {'schemaVersion': 1, 'payload': {'employment': {'employer': 'Example Labs', 'role': 'backend engineer'},
        'claim': {'reduction': 80, 'attribution': 'individual', 'text': 'Reduced latency by 80%.'}},
        'discoveries': [{'key': 'employer', 'semanticType': 'employers', 'pointer': '/employment'},
            {'key': 'claim', 'semanticType': 'claims', 'pointer': '/claim'}],
        'fields': [{'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': field,
            'pointer': '/' + path + '/' + field, 'evidence': [employer if key == 'employer' else metric], 'effectiveCellIds': []}
            for key, path, fields in [('employer', 'employment', ['employer', 'role']),
                ('claim', 'claim', ['reduction', 'attribution', 'text'])] for field in fields],
        'lineage': [{'kind': 'add', 'parents': [], 'children': ['employer', 'claim']}],
        'relations': [{'relation': {'kind': 'discovery_key', 'key': 'claim-owner'}, 'kind': 'owned_by',
            'subject': {'kind': 'discovery_key', 'key': 'claim'}, 'target': {'kind': 'discovery_key', 'key': 'employer'},
            'evidence': [metric]}]}
