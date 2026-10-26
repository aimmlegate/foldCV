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
@pytest.mark.parametrize('review_failure', ['unknown', 'uncertain', 'unavailable'])
async def test_unusable_review_uses_source_fallback_and_no_review_retry(tmp_path, entry, review_failure):
    # Review protocol 3: a check the reply leaves out holds and a check listed twice merges (I1), so an entry naming an
    # unknown target is what leaves a reply unusable.
    fixture = RuntimeFixture(tmp_path)
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        if review_failure == 'unavailable':
            return '{invalid'
        results = [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
            'disposition': 'uncertain' if review_failure == 'uncertain' else 'satisfied',
            'reason': 'Attribution is unclear', 'actionable': False, 'evidence': []} for target in value['targets']]
        return {'results': [*results, {**results[0], 'targetId': 'unknown-target'}] if review_failure == 'unknown' else results}
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
            return {'results': [*results, {**results[0], 'targetId': 'unknown-target'}] if outcome == 'incomplete_review' else results}
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
async def test_a_repair_that_still_states_an_unbound_value_keeps_the_block_without_it(tmp_path):
    # I4 (2026-10-25): the first reply is refused with the binding named; a repair that repeats the unstated value loses
    # that value, the rest of the block is reviewed and accepted, and one notice names the removed text.
    fixture = RuntimeFixture(tmp_path)
    def script(_request, value):
        if 'targets' in value:
            return satisfied_review(value)
        reply = raw_proposal(fixture.source)
        without_journal(reply)
        return reply
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'accepted'
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'primary_repair', 'replacement_review']
    assert result.proposals[0].state == 'invalid' and result.proposals[1].state == 'accepted'
    assert [(value.pointer, value.text) for value in result.proposals[1].dropped_values] == [('/0/journal', 'Unstated Journal')]
    [issue] = result.issues
    assert issue.code == 'IMPORT_VALUE_UNBOUND' and issue.category == 'uncertain_interpretation' and issue.task_id == result.tasks[0].id
    assert 'Unstated Journal' in issue.message and issue.message.startswith('Убраны данные')
    assert 'Unstated Journal' not in fixture.text()
    assert not any(cell.raw_input == 'Unstated Journal' for record in fixture.current().project.facts.extensions for cell in record.cells)


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
    # The review never finished, so nothing was admitted and the notice still names the source text.
    assert result.issues[0].message.startswith('Показан исходный текст')


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
    # Admitted values stay, so the block is accepted. The result still carries the rejected line.
    assert result.tasks[0].state == 'accepted' and result.task_results[0].disposition == 'source_fallback'
    first, repair = result.proposals
    assert first.applied_receipt_id == result.receipts[0].id and repair.applied_receipt_id is None
    assert first.admitted_cell_ids
    [issue] = result.issues
    cell = next(target['targetId'] for target in reviews[0]['targets'] if not target['targetId'].startswith('scope-'))
    assert issue.target_ids == [cell, 'scope-' + result.tasks[0].id]
    assert issue.message.startswith('Проверка нашла ошибку') and not issue.message.startswith('Показан исходный текст')
    assert 'Ещё замечаний' not in issue.message and 'Неверно' in issue.message


def failing_review(value, failing):
    return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
        'disposition': 'violation' if target in failing else 'satisfied', 'reason': 'Неверно' if target in failing else '',
        'evidence': [], 'actionable': target in failing} for target in value['targets']]}


@pytest.mark.asyncio
async def test_two_findings_on_an_admitted_block_are_one_notice(tmp_path):
    # Two failing cells stay one notice. The count is in the sentence, and the block is not a failed import.
    fixture, reviews = RuntimeFixture(tmp_path, fallback=False), []
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        reviews.append(value)
        cells = [target for target in value['targets'] if not target['targetId'].startswith('scope-')]
        return failing_review(value, cells[:2])
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.tasks[0].state == 'accepted' and result.task_results[0].disposition == 'source_fallback'
    assert result.proposals[0].admitted_cell_ids and result.proposals[1].applied_receipt_id is None
    [issue] = result.issues
    assert issue.message.startswith('Проверка нашла ошибку') and 'Ещё замечаний: 1.' in issue.message
    assert not issue.message.startswith('Показан исходный текст')
    assert issue.target_ids[-1] == 'scope-' + result.tasks[0].id
    assert len(issue.target_ids) == 3


@pytest.mark.asyncio
async def test_a_review_that_admits_nothing_keeps_the_source_notice(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        return failing_review(value, list(value['targets']))
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.tasks[0].state == 'source_fallback' and result.task_results[0].disposition == 'source_fallback'
    assert not result.proposals[0].admitted_cell_ids
    [issue] = result.issues
    assert issue.message.startswith('Показан исходный текст') and 'Ещё замечаний:' in issue.message
    assert fixture.source.units[0].text in fixture.text()


@pytest.mark.asyncio
async def test_a_stopped_check_keeps_admitted_values_and_a_short_notice(tmp_path):
    # Admission is saved, then the process stops before the task result. The values stay and the notice is short.
    fixture = RuntimeFixture(tmp_path)
    original = fixture.pipeline.finish_task
    seen = {'n': 0}
    async def skip_first(*args, **kwargs):
        seen['n'] += 1
        if seen['n'] == 1:
            return None
        return await original(*args, **kwargs)
    fixture.pipeline.finish_task = skip_first
    operation = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted, finalize=False)
    assert not operation.task_results and operation.proposals[0].admitted_cell_ids
    operation = await fixture.pipeline.finish_fallbacks(fixture.project, operation.id)
    assert operation.tasks[0].state == 'accepted' and operation.task_results[0].disposition == 'source_fallback'
    assert operation.issues[0].message == 'Проверка не завершилась. Принятые данные в блоке сохранены.'
    assert 'IMPORT_PROCESSING_STOPPED' in operation.task_results[0].value['diagnostics']
    assert operation.issues[0].target_ids == ['scope-' + operation.tasks[0].id]
    holder = fixture.current().project or fixture.current().pre_draft
    assert len(holder.facts.extensions) == 2


@pytest.mark.asyncio
async def test_independent_blocks_overlap_within_the_captured_concurrency_and_match_the_sequential_result(tmp_path):
    # CT10: three blocks with concurrency 2 keep two calls in flight; admissions write facts concurrently and the
    # outcome equals the sequential run.
    import threading
    import time
    from tests.templates.pipeline_fixtures import blocks_package
    outcomes = {}
    for width in (1, 2):
        fixture = RuntimeFixture(tmp_path / str(width), captured=blocks_package(3), concurrency=width, cap=20)
        lock, state = threading.Lock(), {'now': 0, 'peak': 0}
        def script(_request, value, fixture=fixture, lock=lock, state=state):
            with lock:
                state['now'] += 1
                state['peak'] = max(state['peak'], state['now'])
            try:
                time.sleep(0.05)
                return satisfied_review(value) if 'targets' in value else raw_proposal(fixture.source)
            finally:
                with lock:
                    state['now'] -= 1
        fixture.transport.scripted = script
        result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        holder = fixture.current().project or fixture.current().pre_draft
        outcomes[width] = (state['peak'], result.state, [task.state for task in result.tasks],
            [next(value.disposition for value in result.task_results if value.task_id == task.id) for task in result.tasks],
            len(holder.facts.extensions),
            spent_calls(result), sorted(attempt.state for attempt in result.attempts))
    assert outcomes[1][0] == 1 and outcomes[2][0] == 2
    assert outcomes[1][1:] == outcomes[2][1:]
    assert outcomes[2][1] == 'published' and outcomes[2][2] == ['accepted'] * 3 and outcomes[2][4] == 6 and outcomes[2][5] == 6


def schedule(pipeline, dependencies, width, *, fail=None, cancel_at=None, slow=()):
    """Runs pipeline.run_tasks over fake tasks; returns the start and end events and the peak in flight."""
    import asyncio
    import threading
    from types import SimpleNamespace
    from packages.resume_core.template_import import TemplateImportFailure
    events, state, cancel = [], {'now': 0, 'peak': 0}, threading.Event()
    async def execute(_project, _operation, identifier, _deadline, _cancel):
        events.append(('start', identifier))
        state['now'] += 1
        state['peak'] = max(state['peak'], state['now'])
        try:
            await asyncio.sleep(0.05 if identifier in slow else 0.01)
            if identifier == cancel_at:
                cancel.set()
            if identifier == fail:
                raise TemplateImportFailure('IMPORT_AUTHORITY_REVOKED')
        finally:
            state['now'] -= 1
            events.append(('end', identifier))
    pipeline.execute_task = execute
    operation = SimpleNamespace(id='operation', tasks=[SimpleNamespace(id=name, dependencies=list(after)) for name, after in dependencies],
        capture=SimpleNamespace(policy=SimpleNamespace(concurrency=width)))
    return pipeline.run_tasks('project', operation, None, cancel), events, state


@pytest.mark.asyncio
@pytest.mark.parametrize('width,peak', [(1, 1), (2, 2), (4, 3)])
async def test_the_scheduler_starts_ready_tasks_in_declaration_order_up_to_its_width(tmp_path, width, peak):
    run, events, state = schedule(RuntimeFixture(tmp_path).pipeline, [('a', ()), ('b', ()), ('c', ())], width)
    await run
    assert [name for kind, name in events if kind == 'start'] == ['a', 'b', 'c'] and state['peak'] == peak
    assert {name for kind, name in events if kind == 'end'} == {'a', 'b', 'c'}


@pytest.mark.asyncio
async def test_a_task_waits_for_the_tasks_it_depends_on(tmp_path):
    run, events, _state = schedule(RuntimeFixture(tmp_path).pipeline, [('a', ()), ('b', ()), ('c', ('a',)), ('d', ('c', 'b'))], 4,
        slow={'a'})
    await run
    assert events.index(('end', 'a')) < events.index(('start', 'c'))
    assert max(events.index(('end', 'c')), events.index(('end', 'b'))) < events.index(('start', 'd'))


@pytest.mark.asyncio
async def test_a_failure_starts_nothing_new_lets_running_tasks_end_and_is_raised(tmp_path):
    from packages.resume_core.template_import import TemplateImportFailure
    run, events, _state = schedule(RuntimeFixture(tmp_path).pipeline, [('a', ()), ('b', ()), ('c', ())], 2, fail='a', slow={'b'})
    with pytest.raises(TemplateImportFailure, match='IMPORT_AUTHORITY_REVOKED'):
        await run
    assert ('start', 'c') not in events and ('end', 'b') in events


@pytest.mark.asyncio
async def test_a_cancel_starts_nothing_new_and_lets_running_tasks_end(tmp_path):
    run, events, _state = schedule(RuntimeFixture(tmp_path).pipeline, [('a', ()), ('b', ()), ('c', ())], 2, cancel_at='a', slow={'b'})
    await run
    assert ('start', 'c') not in events and ('end', 'b') in events


@pytest.mark.asyncio
async def test_a_dependency_cycle_runs_in_declaration_order_instead_of_waiting_forever(tmp_path):
    run, events, _state = schedule(RuntimeFixture(tmp_path).pipeline, [('a', ('b',)), ('b', ('a',)), ('c', ('z',))], 3)
    await run
    starts = [name for kind, name in events if kind == 'start']
    assert sorted(starts) == ['a', 'b', 'c'] and starts[0] in {'a', 'c'}


@pytest.mark.asyncio
async def test_a_review_goes_stale_only_when_its_own_items_change(tmp_path):
    # CT10: another block's observation leaves this block's review valid; one on this block's own item does not.
    from packages.resume_core.template_admission import task_facts_digest
    from tests.templates.pipeline_fixtures import blocks_package
    fixture = RuntimeFixture(tmp_path, captured=blocks_package(2), concurrency=2, cap=20)
    fixture.transport.scripted = lambda _request, value: satisfied_review(value) if 'targets' in value else raw_proposal(fixture.source)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    facts = (fixture.current().project or fixture.current().pre_draft).facts
    first, second = [task.id for task in result.tasks]
    before = task_facts_digest(result, first, facts)
    other = next(value for value in facts.observations if value.item_handle in result.tasks[1].allowed_handles)
    own = next(value for value in facts.observations if value.item_handle in result.tasks[0].allowed_handles)
    changed = facts.model_copy(update={'observations': [*facts.observations, other.model_copy(update={'id': 'observation-extra'})]})
    assert task_facts_digest(result, first, changed) == before and task_facts_digest(result, second, changed) != task_facts_digest(result, second, facts)
    changed = facts.model_copy(update={'observations': [*facts.observations, own.model_copy(update={'id': 'observation-extra'})]})
    assert task_facts_digest(result, first, changed) != before


def selecting_package():
    """Three blocks of papers; the last also selects the papers the first two produce."""
    import json
    from packages.resume_core.templates.compiler import compile_bytes
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    from tests.templates.pipeline_fixtures import blocks_package
    config = blocks_package(3).definition.model_dump(mode='json', by_alias=True)
    config['blocks'][2]['selectors'] = [*config['blocks'][2]['selectors'], {'kind': 'fact_type', 'id': 'papers'}]
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def test_a_block_that_selects_a_fact_type_waits_for_the_earlier_blocks_that_produce_it():
    from resume_api.importer.template_pipeline import implicit_dependencies
    from tests.templates.pipeline_fixtures import setup_operation
    package = selecting_package()
    operation = setup_operation(captured=package, concurrency=3)[0]
    first, second, third = [task.id for task in operation.tasks]
    assert implicit_dependencies(package, operation) == {first: set(), second: set(), third: {first, second}}


@pytest.mark.asyncio
async def test_a_selecting_block_reads_the_same_records_in_parallel_as_in_sequence(tmp_path):
    seen = {}
    for width in (1, 3):
        fixture = RuntimeFixture(tmp_path / str(width), captured=selecting_package(), concurrency=width, cap=20)
        def script(_request, value, fixture=fixture, width=width):
            if 'targets' in value:
                return satisfied_review(value)
            if value['declaration']['id'] == fixture.package.definition.blocks[2].id:
                seen[width] = len(value['allowedHandles'])
            return raw_proposal(fixture.source)
        fixture.transport.scripted = script
        result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
        assert result.state == 'published' and [task.state for task in result.tasks] == ['accepted'] * 3
    # The third block's request offers the four papers the first two admitted, in both modes.
    assert seen == {1: 4, 3: 4}
