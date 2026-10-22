"""A complete model review cannot retire human-owned facts through lineage."""

import json

import pytest

from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.human_authority_fixtures import HUMAN_TEXT, human_papers
from tests.templates.storage_fixtures import package
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('state', ['human_raw', 'pending_manual'])
async def test_reviewed_split_keeps_human_facts_visible_and_dependency_handles_valid(tmp_path, entry, state):
    config = package().definition.model_dump(mode='json', by_alias=True)
    config['blocks'][0]['selectors'].append({'kind': 'fact_type', 'id': 'papers'})
    captured = compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    fixture = RuntimeFixture(tmp_path, captured=captured)
    before = human_papers(state)
    fixture.command.capture.fact_revisions = {record.id: record.revision for record in before.extensions}
    def seed(workspace):
        workspace.pre_draft.facts = before.model_copy(deep=True)
        return workspace
    fixture.pipeline.checkpoint(fixture.project, seed)
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'satisfied', 'reason': '', 'actionable': False, 'evidence': []} for target in value['targets']]}
        proposal = raw_proposal(fixture.source)
        proposal['lineage'] = [{'kind': 'split', 'parents': ['handle-a'], 'children': ['a', 'b']}]
        return proposal
    fixture.transport.scripted = script
    service = await service_for(fixture) if entry == 'queued' else None
    pipeline = service.templates.pipeline if service else fixture.pipeline
    try:
        if service:
            await queued(service, fixture, fixture.command)
            result = fixture.current().project.template_operations[0]
        else:
            result = await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        effective = fixture.current().project.facts
        assert result.state == 'published' and len(result.receipts) == 1
        assert effective.extensions == before.extensions and effective.manual_scopes == before.manual_scopes
        assert not effective.tombstones and all(record.active for record in effective.extensions)
        assert all(observation.admission == 'uncertain' for observation in effective.observations)
        assert result.proposals[0].state == 'rejected' and not result.proposals[0].admitted_cell_ids
        assert result.task_results[0].item_handles == ['handle-a']
        assert HUMAN_TEXT in fixture.text()
        value = result.task_inputs[0].value
        assert value['allowedHandles'] == ['handle-a', 'handle-b']
        if state == 'pending_manual':
            assert value['manualScopes'][0]['rawInput'] == HUMAN_TEXT
        else:
            assert not value['manualScopes'] and any(cell['rawInput'] == HUMAN_TEXT for cell in value['effectiveCells'])
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()
