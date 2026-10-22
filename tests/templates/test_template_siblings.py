"""Nine supported project entries survive one exact source fallback."""

import json

import pytest

from packages.resume_core.models.contracts import Source
from packages.resume_core.template_identity import capture_span
from packages.resume_core.template_import import spent_calls
from packages.resume_core.templates.compiler import compile_bytes, sha256
from packages.resume_core.templates.loading import load_definition
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_nine_accepted_projects_and_one_unresolved_scope_publish_together(tmp_path, entry):
    lines = ['Company ' + str(index) + ': Implemented queue processing.' for index in range(1, 11)]
    raw = ('\n'.join(lines) + '\n').encode()
    source = Source(id='source-x05', revision=1, originalName='X05-projects.txt', mimeType='text/plain', byteSha256=sha256(raw),
        byteRef='sources/x05.txt', parser='text', parserVersion='1', units=[{'id': 'project-source-' + str(index),
            'revision': 1, 'order': index, 'text': text, 'location': {'kind': 'pasted', 'index': index, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []} for index, text in enumerate(lines)], overlays=[], warnings=[])
    item = {'type': 'object', 'additionalProperties': False, 'required': ['employer', 'text'],
        'properties': {'employer': {'type': 'string'}, 'text': {'type': 'string'}}}
    config = load_definition(BUNDLED_TEMPLATE.read_bytes())
    config['template'] = {'id': 'synthetic-x05', 'revision': '1', 'name': 'X05 projects', 'default_locale': 'en'}
    config['content_definitions'], config['operations'] = {}, []
    config['fact_types'] = [{'id': 'projects', 'schema_version': '1', 'schema': item, 'builtin_kind': None, 'relations': []}]
    config['blocks'] = [{'id': 'arbitrary-paper-view', 'mode': 'model', 'selectors': [{'kind': 'source', 'id': 'all'}],
        'content_schema': {'type': 'array', 'items': item},
        'bindings': [{'pointer': '/*/' + field, 'semantic_type': 'projects', 'field': field, 'relation': None}
            for field in ['employer', 'text']], 'extract': [], 'rewrite': {'fields': [], 'instructions': []}, 'checks': [],
        'depends_on': [], 'operation': None, 'when': None, 'placement': {'region': 'main', 'order': 1},
        'view': {'mode': 'items', 'heading': 'none', 'title': {}, 'inset': 0, 'item_gap': 6,
            'nodes': [{'type': 'text', 'style': 'body', 'field': '/text'}]}}]
    package = compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    fixture = RuntimeFixture(tmp_path, captured=package, src=source, original_bytes=raw, cap=2)
    def script(_request, value):
        if 'targets' in value:
            failed = next(allocation['cellIds']['text'] for allocation in value['handleMap'] if allocation['key'] == 'p10')
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if target['targetId'] == failed else 'satisfied',
                'reason': 'Unsupported interpretation' if target['targetId'] == failed else '',
                'actionable': target['targetId'] == failed, 'evidence': []} for target in value['targets']]}
        return {'schemaVersion': 1, 'payload': [{'employer': 'Company ' + str(index + 1),
            'text': line if index != 9 else 'Invented project result'} for index, line in enumerate(lines)],
            'discoveries': [{'key': 'p' + str(index + 1), 'semanticType': 'projects', 'pointer': '/' + str(index)}
                for index in range(10)], 'fields': [{'item': {'kind': 'discovery_key', 'key': 'p' + str(index + 1)},
                'fieldKey': field, 'pointer': '/' + str(index) + '/' + field,
                'evidence': [capture_span(source, source.units[index]).model_dump(by_alias=True)], 'effectiveCellIds': []}
                for index in range(10) for field in ['employer', 'text']],
            'lineage': [{'kind': 'add', 'parents': [], 'children': ['p' + str(index) for index in range(1, 11)]}], 'relations': []}
    fixture.transport.scripted = script
    service = await service_for(fixture) if entry == 'queued' else None
    try:
        if service:
            await queued(service, fixture, fixture.command)
            result = fixture.current().project.template_operations[0]
        else:
            result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
    assert result.state == 'published' and result.issues and spent_calls(result) == 2
    project = fixture.current().project
    assert len(project.facts.extensions) == 10
    assert sum(cell.field_key == 'text' for record in project.facts.extensions for cell in record.cells) == 9
    assert all(line in fixture.text() for line in lines) and fixture.text().count(lines[-1]) == 1
    assert 'Invented project result' not in fixture.text()
    fallback = [value for value in project.import_coverage if value.disposition == 'fallback']
    accepted = [value for value in project.import_coverage if value.disposition != 'fallback']
    assert len(fallback) == 1 and fallback[0].span.unit_id == source.units[-1].id
    assert all(value.span.unit_id != source.units[-1].id for value in accepted)
