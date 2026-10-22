"""Controlled runtime tests bind review, partial admission and durable publication."""

import copy

import pytest

from packages.resume_core.template_import import CleanupProof, digest, reconcile_cleanup, spent_calls
from tests.templates.pipeline_fixtures import resume_command
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_finalization_flow import queued
from tests.templates.test_template_job_routing import service_for


async def run_entry(fixture, entry):
    service = await service_for(fixture) if entry == 'queued' else None
    try:
        if service:
            await queued(service, fixture, fixture.command)
            return fixture.current().project.template_operations[0]
        return await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    finally:
        if service:
            await service.shutdown()
            service.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_tool_free_new_protocol_runs_complete_review_and_publishes_once(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.publication.state == 'saved'
    assert len(fixture.transport.calls) == spent_calls(result) == 2
    assert fixture.transport.calls[0]['protocol'] == 'template_import_v1' and fixture.transport.calls[0]['tools'] == []
    assert len(result.receipts) == 1 and not result.issues
    assert len(fixture.current().project.facts.extensions) == 2
    before = copy.deepcopy(fixture.transport.calls)
    replay = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert replay == result and fixture.transport.calls == before and fixture.admissions == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('review_failure', ['missing', 'uncertain', 'unavailable'])
async def test_unusable_review_uses_source_fallback_and_no_review_retry(tmp_path, entry, review_failure):
    fixture = RuntimeFixture(tmp_path)
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        if review_failure == 'unavailable':
            return '{invalid'
        results = [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
            'disposition': 'uncertain' if review_failure == 'uncertain' else 'satisfied',
            'reason': 'Attribution is unclear', 'actionable': False, 'evidence': []} for target in value['targets']]
        return {'results': results[:-1] if review_failure == 'missing' else results}
    fixture.transport.scripted = script
    result = await run_entry(fixture, entry)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert len(fixture.transport.calls) == 2 and result.issues
    assert not fixture.current().project.facts.extensions
    assert fixture.source.units[0].text in fixture.text()
    assert len(result.receipts) == (1 if review_failure == 'uncertain' else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
@pytest.mark.parametrize('outcome', ['satisfied', 'no_reply', 'null', 'incomplete_review'])
async def test_empty_output_is_omitted_only_after_complete_absence_review(tmp_path, entry, outcome):
    from tests.templates.storage_fixtures import source_fixture
    source, raw = source_fixture('F02')
    fixture = RuntimeFixture(tmp_path, src=source, original_bytes=raw)
    def script(_request, value):
        if 'targets' in value:
            results = [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
                'reason': '', 'actionable': False, 'evidence': []} for target in value['targets']]
            return {'results': results[:-1] if outcome == 'incomplete_review' else results}
        return '' if outcome == 'no_reply' else '{"payload":null}' if outcome == 'null' else raw_proposal(fixture.source, empty=True)
    fixture.transport.scripted = script
    result = await run_entry(fixture, entry)
    if outcome == 'satisfied':
        assert result.tasks[0].state == 'empty' and not result.issues and result.receipts
        assert fixture.text() == ''
    else:
        assert result.tasks[0].state == 'source_fallback' and result.issues and not result.receipts
        assert fixture.source.units[0].text in fixture.text()
    assert len(fixture.transport.calls) == (1 if outcome in {'no_reply', 'null'} else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize('cutpoint', ['dispatch', 'return'])
async def test_restart_never_replays_an_unknown_call_and_can_consume_a_retained_return(tmp_path, cutpoint):
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.fail_at = cutpoint
    with pytest.raises(SystemExit):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    operation = fixture.current().pre_draft.template_operations[0]
    assert spent_calls(operation) == 1
    fixture.transport.fail_at = None
    fresh = fixture.fresh_pipeline()
    if cutpoint == 'dispatch':
        recovered = await fresh.recover(fixture.project, operation.id)
        assert recovered.state == 'fenced' and len(fixture.transport.calls) == 1
        proof = CleanupProof(operation.attempts[0].id, digest(operation.attempts[0].owner), digest('trusted-terminal'), 'controlled-terminal')
        await __import__('asyncio').to_thread(fresh.update, fixture.project, operation.id,
            lambda value, _data, _workspace: reconcile_cleanup(value, proof, fixture.now))
    result = await fresh.run(fixture.project, resume_command(operation), admitted=fixture.admitted)
    assert result.state == 'published'
    assert len(fixture.transport.calls) == (1 if cutpoint == 'dispatch' else 2)
    assert spent_calls(result) == len(fixture.transport.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_exhausted_processing_still_finalizes_after_verified_cleanup(tmp_path, entry):
    fixture = RuntimeFixture(tmp_path)
    def script(_request, _value):
        fixture.now = '2026-10-21T00:05:01+00:00'
        return raw_proposal(fixture.source)
    fixture.transport.scripted = script
    result = await run_entry(fixture, entry)
    assert result.state == 'published' and result.inference_closed
    assert result.tasks[0].state == 'source_fallback' and spent_calls(result) == 1
    assert not fixture.current().project.facts.extensions


@pytest.mark.asyncio
async def test_unknown_cleanup_fences_without_fallback_publication(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.cleanup_unknown = True
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'fenced' and len(fixture.transport.calls) == 1
    assert fixture.current().project is None


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['direct', 'queued'])
async def test_budget_expiry_retains_accepted_scopes_before_finalizing_remaining_source(tmp_path, entry):
    import json
    from packages.resume_core.templates.compiler import compile_bytes
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    from tests.templates.storage_fixtures import package
    config = package().definition.model_dump(mode='json', by_alias=True)
    config['blocks'].append({**config['blocks'][0], 'id': 'later-scope',
        'placement': {'region': 'main', 'order': 2}, 'depends_on': [config['blocks'][0]['id']]})
    captured = compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')
    fixture = RuntimeFixture(tmp_path, captured=captured)
    original = fixture.transport.generate
    def generate(request, cancel):
        if len(fixture.transport.calls) == 2:
            fixture.now = '2026-10-21T00:05:01+00:00'
        return original(request, cancel)
    fixture.transport.generate = generate
    result = await run_entry(fixture, entry)
    assert result.state == 'published' and result.inference_closed and spent_calls(result) == 3
    assert [task.state for task in result.tasks] == ['accepted', 'source_fallback']
    assert len(fixture.current().project.facts.extensions) == 2 and len(result.receipts) == 1
    assert fixture.source.units[0].text in fixture.text()
