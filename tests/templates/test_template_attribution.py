"""Rejected F01 metrics never enter effective facts or dependent task input."""

import pytest

from packages.resume_core.template_import import spent_calls
from tests.templates.claim_runtime_fixtures import claim_fixture, claim_proposal
from tests.templates.template_runtime_fixtures import RuntimeFixture
from resume_api.importer.template_pipeline import DerivedTask


@pytest.mark.asyncio
async def test_f01_team_attribution_rejection_keeps_employer_and_exact_source_fallback(tmp_path):
    package, source, raw = claim_fixture(dependent=True)
    fixture = RuntimeFixture(tmp_path, captured=package, src=source, original_bytes=raw, cap=2)
    def script(_request, value):
        if 'targets' not in value:
            return claim_proposal(source)
        rejected = {cell for allocation in value['handleMap'] if allocation['semanticType'] == 'claims'
            for cell in allocation['cellIds'].values()}
        return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
            'disposition': 'violation' if target['targetId'] in rejected else 'satisfied',
            'reason': 'Source attributes 800 to 500 ms to the team; individual 80% is unsupported.'
                if target['targetId'] in rejected else '', 'evidence': [], 'actionable': target['targetId'] in rejected}
            for target in value['targets']]}
    fixture.transport.scripted = script
    dependent_inputs = []
    def derive(operation, task, _data):
        value = next(value.value for value in operation.task_inputs if value.task_id == task.id)
        dependent_inputs.append(value)
        assert {record['semanticType'] for record in value['effectiveRecords']} == {'employers'}
        assert all(cell['typedValue'] not in {80, 'individual', 'Reduced latency by 80%.'} for cell in value['effectiveCells'])
        return DerivedTask([], (), ())
    fixture.pipeline.derive = derive
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and spent_calls(result) == 2 and len(dependent_inputs) == 1
    current = fixture.current().project
    assert {record.semantic_type for record in current.facts.extensions} == {'employers'}
    assert any(value.typed_value == 80 and value.admission == 'rejected' for value in current.facts.observations)
    assert source.units[-1].text in fixture.text() and '80%' not in fixture.text()
    assert fixture.text().count(source.units[-1].text) == 1 and 'Example Labs' in fixture.text()
    assert result.tasks[-1].state == 'empty' and result.issues
    assert [value.span.unit_id for value in current.import_coverage if value.disposition == 'fallback'] == [source.units[-1].id]


@pytest.mark.asyncio
async def test_f01_named_repair_reuses_unadmitted_item_and_relation_identity(tmp_path):
    package, source, raw = claim_fixture()
    fixture = RuntimeFixture(tmp_path, captured=package, src=source, original_bytes=raw)
    reviews = []
    def script(_request, value):
        if 'targets' in value:
            reviews.append(value)
            rejected = {cell for allocation in value['handleMap'] if allocation['semanticType'] == 'claims'
                for cell in allocation['cellIds'].values()} if len(reviews) == 1 else set()
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if target['targetId'] in rejected else 'satisfied',
                'reason': 'Keep supported team wording; remove invented individual 80%.' if target['targetId'] in rejected else '',
                'actionable': target['targetId'] in rejected, 'evidence': []} for target in value['targets']]}
        proposal = claim_proposal(source)
        if value['slot'] != 'initial':
            assert value['feedback'] and len(value['capturedRelations']) == 1
            handles = {allocation['key']: allocation['itemHandle'] for allocation in value['capturedHandles']}
            proposal['payload']['claim'] = {'reduction': None, 'attribution': 'team', 'text': source.units[-1].text}
            proposal['discoveries'], proposal['lineage'] = [], []
            for field in proposal['fields']:
                field['item'] = {'kind': 'handle', 'itemHandle': handles[field['item']['key']]}
            relation = proposal['relations'][0]
            relation['relation'] = {'kind': 'relation_id', 'relationId': value['capturedRelations'][0]['id']}
            relation['subject'] = {'kind': 'handle', 'itemHandle': handles['claim']}
            relation['target'] = {'kind': 'handle', 'itemHandle': handles['employer']}
        return proposal
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and not result.issues and len(reviews) == 2 and spent_calls(result) == 4
    assert len(result.allocations) == 2 and len(result.relation_allocations) == 1
    current = fixture.current().project
    claim = next(value for value in current.facts.extensions if value.semantic_type == 'claims')
    assert {cell.field_key: cell.typed_value for cell in claim.cells} == {'attribution': 'team', 'text': source.units[-1].text}
    assert current.facts.relations[0].id == result.relation_allocations[0].relation_id
    assert any(value.typed_value == 80 and value.admission == 'rejected' for value in current.facts.observations)
    assert reviews[0]['proposalHash'] != reviews[1]['proposalHash']
