"""An elapsed processing deadline also bounds a completed review return."""

import pytest

from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal


@pytest.mark.asyncio
@pytest.mark.parametrize('malformed', [False, True])
async def test_review_return_after_elapsed_expiry_cannot_admit_effective_facts(tmp_path, malformed):
    fixture = RuntimeFixture(tmp_path)
    elapsed = [0.0]
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        elapsed[0] = 301.0
        if malformed:
            return '{invalid late review'
        return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
            'disposition': 'satisfied', 'reason': '', 'actionable': False, 'evidence': []} for target in value['targets']]}
    fixture.transport.scripted = script
    fixture.pipeline.elapsed = lambda: elapsed[0]
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.inference_closed
    assert result.tasks[0].state == 'source_fallback' and result.issues
    assert not fixture.current().project.facts.extensions and not result.receipts
    assert len(fixture.transport.calls) == 2 and result.attempts[-1].outcome == 'timed_out'
    assert result.attempts[-1].raw_return and result.attempts[-1].cleanup.state == 'verified'
