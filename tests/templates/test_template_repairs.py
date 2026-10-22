"""Named semantic feedback alone authorizes captured primary/fallback repair slots."""

import pytest

from packages.resume_core.template_import import spent_calls
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for
from resume_api.providers.content import ContentFailure


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('repair', ['primary', 'fallback', 'fallback_failure', 'fallback_unavailable', 'no_fallback'])
async def test_repairs_keep_siblings_and_use_only_configured_slots(tmp_path, entry, repair):
    fixture = RuntimeFixture(tmp_path, fallback=repair != 'no_fallback')
    rejected, reviews, models = [], [], []
    def script(request, value):
        models.append(request.policy.model)
        if 'targets' in value:
            reviews.append(value)
            if not rejected:
                rejected.extend(allocation['cellIds']['journal'] for allocation in value['handleMap'] if allocation['key'] == 'b')
            fail = len(reviews) == 1 or repair == 'fallback_failure'
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if fail and target['targetId'] in rejected else 'satisfied',
                'reason': 'Journal is not supported by source' if fail and target['targetId'] in rejected else '',
                'actionable': fail and target['targetId'] in rejected, 'evidence': []} for target in value['targets']]}
        result = raw_proposal(fixture.source)
        if value['slot'] == 'initial':
            result['payload'][1]['journal'] = 'Invented journal'
            return result
        assert value['feedback'] and all(item['ruleId'] and item['targetId'] and item['reason'] for item in value['feedback'])
        if repair in {'fallback', 'fallback_unavailable', 'no_fallback'} and value['slot'] == 'primary_repair':
            return '{invalid primary repair'
        if repair == 'fallback_unavailable' and value['slot'] == 'fallback_repair':
            raise ContentFailure('MODEL_DENIED', logical_attempts=0, cleanup_verified=True,
                dispatch_witness={'transport': 'controlled', 'neverDispatched': True})
        handles = {allocation['key']: allocation['itemHandle'] for allocation in value['capturedHandles']}
        result['discoveries'], result['lineage'] = [], []
        for field in result['fields']:
            field['item'] = {'kind': 'handle', 'itemHandle': handles[field['item']['key']]}
        return result
    fixture.transport.scripted = script
    service = await service_for(fixture) if entry == 'queued' else None
    try:
        if service:
            await queued(service, fixture, fixture.command)
            operation = fixture.current().project.template_operations[0]
        else:
            operation = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
    assert operation.state == 'published' and len(operation.allocations) == 2
    assert spent_calls(operation) == len(fixture.transport.calls) - (repair == 'fallback_unavailable')
    facts = fixture.current().project.facts
    assert len(facts.extensions) == 2
    assert facts.extensions[0].cells[0].revision == 1
    assert next(value for value in facts.observations if value.typed_value == 'Invented journal').admission == 'rejected'
    if repair in {'primary', 'fallback'}:
        assert not operation.issues and operation.tasks[0].state == 'accepted'
        assert next(cell for record in facts.extensions for cell in record.cells if cell.id == rejected[0]).typed_value == 'Queue Review'
        assert len(operation.receipts) == 2 and reviews[0] != reviews[-1]
        assert len(fixture.transport.calls) == (4 if repair == 'primary' else 5)
    else:
        assert operation.issues and operation.tasks[0].state == 'source_fallback'
        assert rejected[0] not in {cell.id for record in facts.extensions for cell in record.cells}
        assert len(fixture.transport.calls) == (3 if repair == 'no_fallback' else 4 if repair == 'fallback_unavailable' else 6)
        if repair == 'fallback_unavailable':
            assert operation.attempts[-1].state == 'released' and operation.cleanup_records[-1].never_dispatched
    assert ('synthetic-fallback' in models) == (repair in {'fallback', 'fallback_failure', 'fallback_unavailable'})
