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
@pytest.mark.parametrize('review_failure', ['repeated', 'uncertain', 'unavailable'])
async def test_unusable_review_uses_source_fallback_and_no_review_retry(tmp_path, entry, review_failure):
    # Review protocol 3: a check the reply leaves out holds, so a repeated entry is what leaves a reply incomplete.
    fixture = RuntimeFixture(tmp_path)
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        if review_failure == 'unavailable':
            return '{invalid'
        results = [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
            'disposition': 'uncertain' if review_failure == 'uncertain' else 'satisfied',
            'reason': 'Attribution is unclear', 'actionable': False, 'evidence': []} for target in value['targets']]
        return {'results': [*results, results[0]] if review_failure == 'repeated' else results}
    fixture.transport.scripted = script
    result = await run_entry(fixture, entry)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert len(fixture.transport.calls) == 2 and result.issues
    assert not fixture.current().project.facts.extensions
    assert fixture.source.units[0].text in fixture.text()
    assert len(result.receipts) == (1 if review_failure == 'uncertain' else 0)
    # One notice for the block, whatever the number of failing checks.
    [issue] = result.issues
    assert issue.message == ('Показан исходный текст: проверка не подтвердила извлечённые данные. Attribution is unclear. '
        'Ещё замечаний: ' + str(len(issue.target_ids) - 1) + '.' if review_failure == 'uncertain'
        else 'Показан исходный текст: проверку извлечённых данных не удалось завершить.')


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
            return {'results': [*results, results[0]] if outcome == 'incomplete_review' else results}
        return '' if outcome == 'no_reply' else '{"payload":null}' if outcome == 'null' else raw_proposal(fixture.source, empty=True)
    fixture.transport.scripted = script
    result = await run_entry(fixture, entry)
    if outcome == 'satisfied':
        assert result.tasks[0].state == 'empty' and not result.issues and result.receipts
        assert fixture.text() == ''
    else:
        # Not evidence of absence: the block is a source fallback with a notice, not empty. Its scope is the whole
        # source, which identifies no lines to show (LIVE-08), so none are placed.
        assert result.tasks[0].state == 'source_fallback' and result.issues and not result.receipts
        assert fixture.text() == '' and result.issues[0].message.startswith('Блок не заполнен')
    # A refused first reply gets one repair, then the fixture's fallback model; neither is reviewed (S7c).
    assert len(fixture.transport.calls) == (3 if outcome in {'no_reply', 'null'} else 2)
    if outcome in {'no_reply', 'null'}:
        assert [call['feedback'][0]['ruleId'] for call in fixture.transport.calls[1:]] == ['reply-format', 'reply-format']


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
    # P03: the prompt is a pure function of the stored request, so a reloaded attempt reads byte for byte the same.
    from packages.resume_core.template_prompt import model_prompt
    assert model_prompt(operation.attempts[0].request_value) == fixture.transport.prompts[0]
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
    # The block that never ran had the whole source as its scope, which identifies no lines (LIVE-08); its notice
    # says it is not filled, and the accepted block keeps its values.
    [issue] = [issue for issue in result.issues if issue.task_id == result.tasks[1].id]
    assert issue.message.startswith('Блок не заполнен') and 'Reliable Queues' in fixture.text()


@pytest.mark.asyncio
async def test_identical_replies_of_two_blocks_are_each_reviewed_against_their_own_scope(tmp_path):
    # Equal replies share a proposal hash; a reused review input would check the other block's scope and old facts.
    import json
    from packages.resume_core.templates.compiler import compile_bytes
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    from tests.templates.storage_fixtures import package
    config = package().definition.model_dump(mode='json', by_alias=True)
    config['blocks'].append({**config['blocks'][0], 'id': 'second-view', 'placement': {'region': 'main', 'order': 2}})
    fixture = RuntimeFixture(tmp_path, captured=compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent,
        original_format='json'))
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
                'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
        return raw_proposal(fixture.source, empty=True)
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and [task.state for task in result.tasks] == ['empty', 'empty']
    tasks = {attempt.id: attempt.task_id for attempt in result.attempts}
    assert sorted((tasks[record.attempt_id], sorted({target.target_id for target in record.value.targets
        if target.target_id.startswith('scope-')})) for record in result.review_inputs) == sorted(
        (task.id, ['scope-' + task.id]) for task in result.tasks)


def satisfied_review(value):
    return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
        'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}


def refused_first(fixture, refuse):
    """The first reply of the block is refused as refuse makes it; the repair and the review answer correctly."""
    def script(_request, value):
        if 'targets' in value:
            return satisfied_review(value)
        reply = raw_proposal(fixture.source)
        if value['slot'] == 'initial':
            refuse(reply)
        return reply
    return script


def without_journal(reply):
    # A value the source does not state word for word, sent without its entry: completion cannot cite it (S7d).
    reply['payload'][0]['journal'] = 'Unstated Journal'
    reply['fields'] = [field for field in reply['fields'] if field['pointer'] != '/0/journal']


@pytest.mark.asyncio
async def test_a_refused_first_reply_gets_one_repair_with_its_refusal_and_is_accepted(tmp_path):
    # P07: the repair request carries the refusal; the refused attempt keeps its raw return and gets no review.
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.scripted = refused_first(fixture, without_journal)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'accepted' and not result.issues
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'primary_repair', 'replacement_review']
    assert len(fixture.transport.calls) == spent_calls(result) == 3
    refused = result.attempts[0]
    assert refused.outcome == 'invalid_payload' and refused.raw_return and result.proposals[0].state == 'invalid'
    [feedback] = fixture.transport.calls[1]['feedback']
    assert (feedback['ruleId'], feedback['targetId']) == ('reply-format', 'scope-' + result.tasks[0].id)
    assert feedback['reason'].endswith('missing /0/journal (journal)') and feedback['reason'] == result.proposals[0].errors[0][:300]
    assert len(fixture.current().project.facts.extensions) == 2


@pytest.mark.asyncio
async def test_a_refused_first_reply_without_room_for_a_repair_and_its_review_falls_back(tmp_path):
    # P08: one call left after the first reply is not enough for a repair that must also be reviewed.
    fixture = RuntimeFixture(tmp_path, cap=2)
    fixture.transport.scripted = refused_first(fixture, without_journal)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert len(fixture.transport.calls) == 1
    [fallback] = result.task_results
    assert fallback.value['scope'] == 'cited' and fallback.value['diagnostics'][-1] == 'IMPORT_CALL_CAP'
    assert fixture.source.units[0].text in fixture.text()


def test_refusal_text_names_paths_and_rules_but_no_reply_values():
    # P09: a refused value may quote the source; the stored refusal and the repair note keep only its path and rule.
    from pydantic import BaseModel, ConfigDict, ValidationError
    from packages.resume_core.template_proposals import reply_error
    from packages.resume_core.templates.projection import SchemaFailure, validate_payload
    phrase = 'Example Labs Quality Award'
    schema = {'type': 'object', 'properties': {'year': {'type': 'integer'}, 'status': {'enum': ['published', 'draft']},
        'url': {'anyOf': [{'type': 'string'}, {'type': 'null'}]}}, 'required': ['year'], 'additionalProperties': False}
    reasons = []
    for value in [{'year': phrase}, {'year': 1, 'status': phrase}, {'year': 1, 'url': [phrase]}, {'year': 1, phrase: 1}, {}]:
        with pytest.raises(SchemaFailure) as failure:
            validate_payload(schema, value)
        reasons.append(reply_error(failure.value))
    class Strict(BaseModel):
        model_config = ConfigDict(extra='forbid', strict=True)
        year: int
    with pytest.raises(ValidationError) as failure:
        Strict.model_validate({'year': phrase})
    assert phrase in str(failure.value)
    reasons.append(reply_error(failure.value))
    assert not any(phrase in reason for reason in reasons)
    assert reasons == ['/payload/year: expected type "integer"', '/payload/status: expected one of ["published", "draft"]',
        '/payload/url: matches none of the allowed shapes', '/payload/: has a property the schema does not allow',
        "/payload/: 'year' is a required property", '/year: Input should be a valid integer']


@pytest.mark.asyncio
async def test_a_reply_the_transport_refuses_by_schema_is_repaired_without_its_quoted_value(tmp_path):
    # P09 end to end: the transport refuses a value quoting the source; the repair note names only path and rule.
    fixture = RuntimeFixture(tmp_path)
    phrase = 'Example Labs Quality Award'
    assert phrase in fixture.source.units[0].text
    fixture.transport.scripted = refused_first(fixture, lambda reply: reply['payload'][0].update(year=phrase))
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.tasks[0].state == 'accepted' and result.attempts[0].error_code == 'INVALID_RESULT'
    [feedback] = fixture.transport.calls[1]['feedback']
    assert '/0/year' in feedback['reason'] and phrase not in feedback['reason']
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'primary_repair', 'replacement_review']


def timing_out(fixture, limits, *, slots=('initial',), review=False):
    """Calls in slots (or the review) run out of time without a reply; the others answer correctly."""
    from resume_api.providers.content import ContentFailure, ReportedUsage
    def script(request, value):
        limits.append(request.policy.timeout_seconds)
        if ('targets' in value) == review and (review or value['slot'] in slots):
            raise ContentFailure('DEADLINE_EXCEEDED', logical_attempts=1, usage=ReportedUsage(None, None, None, False),
                cleanup_verified=True, dispatch_witness={'transport': 'controlled'})
        return satisfied_review(value) if 'targets' in value else raw_proposal(fixture.source)
    return script


@pytest.mark.asyncio
async def test_a_first_call_that_runs_out_of_time_is_retried_once_with_the_full_limit(tmp_path):
    # LIVE-04: the projects call stalled for 180 s; the same request then answered in 15-19 s (PROBE-02).
    from resume_api.importer.template_pipeline import CALL_SECONDS, RETRY_SECONDS
    fixture, limits = RuntimeFixture(tmp_path), []
    fixture.transport.scripted = timing_out(fixture, limits)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'accepted' and not result.issues
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'primary_repair', 'replacement_review']
    assert (result.attempts[0].outcome, result.attempts[0].error_code) == ('timed_out', 'DEADLINE_EXCEEDED')
    assert fixture.transport.calls[1]['feedback'] == [{'ruleId': 'reply-time', 'targetId': 'scope-' + result.tasks[0].id,
        'reason': 'No reply arrived within the call time limit. Return the whole reply.'}]
    assert limits == [CALL_SECONDS, RETRY_SECONDS, CALL_SECONDS] and CALL_SECONDS < RETRY_SECONDS == 180
    assert len(fixture.current().project.facts.extensions) == 2


@pytest.mark.asyncio
async def test_a_retry_that_also_runs_out_of_time_falls_back_without_a_third_call(tmp_path):
    fixture, limits = RuntimeFixture(tmp_path, fallback=False), []
    fixture.transport.scripted = timing_out(fixture, limits, slots=('initial', 'primary_repair'))
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert len(fixture.transport.calls) == 2 and [attempt.slot for attempt in result.attempts] == ['initial', 'primary_repair']
    assert fixture.text() == '' and result.issues[0].message.startswith('Блок не заполнен')


@pytest.mark.asyncio
async def test_a_review_that_runs_out_of_time_is_not_retried(tmp_path):
    # K01: an incomplete review follows source fallback; only extraction gets the retry.
    from resume_api.importer.template_pipeline import CALL_SECONDS
    fixture, limits = RuntimeFixture(tmp_path), []
    fixture.transport.scripted = timing_out(fixture, limits, review=True)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert limits == [CALL_SECONDS, CALL_SECONDS] and [attempt.slot for attempt in result.attempts] == ['initial', 'review']
    assert fixture.source.units[0].text in fixture.text()


@pytest.mark.asyncio
async def test_a_repair_whose_review_finds_more_problems_does_not_replace_the_first_reply(tmp_path):
    # LIVE-09: the first projects reply failed 7 of 397 checks, its repair 142 of 463; the first one now stays.
    fixture, reviews = RuntimeFixture(tmp_path, fallback=False), []
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        reviews.append(value)
        failing = [target for target in value['targets'] if not target['targetId'].startswith('scope-')]
        failing = failing[:1] if len(reviews) == 1 else failing
        return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
            'disposition': 'violation' if target in failing else 'satisfied', 'reason': 'Неверно' if target in failing else '',
            'evidence': [], 'actionable': True} for target in value['targets']]}
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'review', 'primary_repair', 'replacement_review']
    assert result.tasks[0].state == 'source_fallback'
    first, repair = result.proposals
    assert first.applied_receipt_id == result.receipts[0].id and repair.applied_receipt_id is None
    # The notice and the source lines come from the first review: one failing value.
    [issue] = result.issues
    assert issue.target_ids == [next(target['targetId'] for target in reviews[0]['targets'] if not target['targetId'].startswith('scope-'))]
    assert issue.message.startswith('Показан исходный текст: проверка нашла ошибку') and 'Ещё замечаний' not in issue.message
