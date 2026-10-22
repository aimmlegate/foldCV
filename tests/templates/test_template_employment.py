"""Controlled direct/queued imports publish the real employment assembly."""

import pytest

from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_import import spent_calls
from tests.templates.employment_fixtures import employment_package, employment_proposal, employment_source
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for


class EmploymentFixture(RuntimeFixture):
    def assemble(self, before, operation):
        return assemble_template(before, operation)


def scripted_employment(src, *, unsupported=False):
    bad_cells = set()
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if target['targetId'] in bad_cells else 'satisfied',
                'reason': 'Individual 80% is unsupported by the source' if target['targetId'] in bad_cells else '',
                'actionable': False, 'evidence': []} for target in value['targets']]}
        reply = employment_proposal(src, unsupported=unsupported)
        captured = {item['key']: item for item in value.get('capturedHandles', []) if 'key' in item}
        if captured:
            if unsupported:
                bad_cells.add(captured['results-entry']['cellIds']['value'])
            for field in reply['fields']:
                field['item'] = {'kind': 'handle', 'itemHandle': captured[field['item']['key']]['itemHandle']}
            known = {(relation['kind'], relation['subjectId'], relation['targetId']): relation['id']
                for relation in value['capturedRelations']}
            for relation in reply['relations']:
                subject, target = captured[relation['subject']['key']], captured[relation['target']['key']]
                relation['subject'] = {'kind': 'handle', 'itemHandle': subject['itemHandle']}
                relation['target'] = {'kind': 'handle', 'itemHandle': target['itemHandle']}
                relation['relation'] = {'kind': 'relation_id', 'relationId': known[(relation['kind'], subject['recordId'], target['recordId'])]}
            reply['discoveries'], reply['lineage'] = [], []
        return reply
    def observe(_request, value):
        if 'targets' in value and unsupported:
            bad_cells.update(item['cellIds']['value'] for item in value['handleMap']
                if item.get('key') == 'results-entry')
        return script(_request, value)
    return observe


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('case', ['F01', 'F02', 'invalid_metric'])
async def test_real_materializer_publishes_current_employment_and_exact_fallback(tmp_path, entry, case):
    src, raw = employment_source('F02' if case == 'F02' else 'F01')
    unsupported = case == 'invalid_metric'
    fixture = EmploymentFixture(tmp_path, captured=employment_package(), src=src, original_bytes=raw,
        scripted=scripted_employment(src, unsupported=unsupported), cap=4, fallback=False)
    service = await service_for(fixture) if entry == 'queued' else None
    try:
        if service:
            job = await queued(service, fixture, fixture.command)
            assert job.template_outcome.state == 'saved'
        else:
            result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
            assert result.publication.state == 'saved'
        current = fixture.current()
        operation = current.project.template_operations[0]
        assert operation.state == 'published'
        assert spent_calls(operation) == len(fixture.transport.calls) == (4 if unsupported else 2)
        assert len([record for record in current.project.facts.records if record.kind == 'employment']) == 1
        assert fixture.text().count('Implemented queue processing.') == 1
        assert '80%' not in fixture.text()
        if unsupported:
            assert fixture.text().count('Our team reduced median latency from 800 ms to 500 ms.') == 1
            assert current.project.import_issues and all(finding.block_ids for finding in current.project.import_issues)
            assert not any('80%' in str(record.value.value) for record in current.project.facts.records if record.kind == 'claim')
            assert operation.task_results[0].disposition == 'source_fallback'
        elif case == 'F02':
            assert 'Results:' not in fixture.text() and not current.project.import_issues
        else:
            assert 'Results:' in fixture.text() and not current.project.import_issues
        assert current.project.template_package == fixture.package
        assert current.project.sources == [src]
        assert any(part.type == 'fact_field' and part.presentation.node_index is not None
            for block in current.project.document.blocks() for part in block.content)
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
