"""D155: a model call that never answered is made once more with the same request, as a new attempt of its slot,
before its task repairs or falls back; the second call counts toward the cap and needs the import's time."""

import pytest

from packages.resume_core.hashing import digest
from packages.resume_core.importing.template_import import CleanupProof, spent_calls
from resume_api.providers.content import ContentFailure, ContentTransportReturn, ReportedUsage
from tests.templates.entry_fixtures import entries_package, entries_script, lines_source
from tests.templates.pipeline_fixtures import resume_command
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_pipeline import refused_first, satisfied_review, without_journal


def failure(code, *, never_dispatched=False):
    """A call that ends without a reply, as the CLI adapter raises it; never_dispatched as before any process."""
    raise ContentFailure(code, logical_attempts=1, usage=ReportedUsage(None, None, None, False), cleanup_verified=True,
        dispatch_witness={'transport': 'controlled', **({'neverDispatched': True} if never_dispatched else {})})


def failing_first(fixture, code, *, review=False, times=1, never_dispatched=False):
    """The block's first `times` calls (or its review's) end with `code`; every other call answers."""
    failed = []
    def script(_request, value):
        if ('targets' in value) == review and len(failed) < times:
            failed.append(value)
            failure(code, never_dispatched=never_dispatched)
        return satisfied_review(value) if 'targets' in value else raw_proposal(fixture.source)
    return script


async def run(fixture):
    return await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)


def schemas_of(fixture):
    """The reply schema of each call, in order."""
    seen, generate = [], fixture.transport.generate
    def recording(request, cancel):
        seen.append(request.result_type)
        return generate(request, cancel)
    fixture.transport.generate = recording
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize('code,never_dispatched', [('STALLED', False), ('INVALID_RESULT', False),
    ('DEADLINE_EXCEEDED', False), ('DEADLINE_EXCEEDED', True)])
async def test_a_first_call_that_never_answered_is_made_once_more_and_the_block_admitted(tmp_path, code,
                                                                                         never_dispatched):
    # Findings 7 and 8: a stalled call, a reply the CLI refused against the schema, a provider bound short of the
    # import's time (a qualification) each cost the block. One that never started a process is released.
    fixture = RuntimeFixture(tmp_path, fallback=False)
    fixture.transport.scripted = failing_first(fixture, code, never_dispatched=never_dispatched)
    schemas = schemas_of(fixture)
    result = await run(fixture)
    assert result.state == 'published' and result.tasks[0].state == 'accepted' and not result.issues
    assert result.task_results[0].disposition == 'admitted' and len(fixture.current().project.facts.extensions) == 2
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'initial', 'review']
    first, again, _review = result.attempts
    assert (first.error_code, first.raw_return, first.proposal_record_id) == (code, None, None)
    assert again.outcome == 'completed'
    assert first.state == ('released' if never_dispatched else 'returned') and first.cleanup.state == 'verified'
    # The same request in a new attempt with its own owner; both are the task's and count unless one never ran.
    assert again.input_hash == first.input_hash and again.request_value == first.request_value
    assert fixture.transport.prompts[0] == fixture.transport.prompts[1] and schemas[0] == schemas[1]
    assert again.owner != first.owner
    assert result.tasks[0].attempt_ids == [attempt.id for attempt in result.attempts]
    assert spent_calls(result) == len(fixture.transport.calls) - never_dispatched == 3 - never_dispatched


@pytest.mark.asyncio
async def test_a_block_whose_second_call_stalls_too_falls_back_as_before(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    fixture.transport.scripted = failing_first(fixture, 'STALLED', times=2)
    result = await run(fixture)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert [(attempt.slot, attempt.error_code) for attempt in result.attempts] == [('initial', 'STALLED')] * 2
    assert len(fixture.transport.calls) == spent_calls(result) == 2
    assert result.task_results[0].value['diagnostics'] == ['STALLED']
    assert fixture.text() == '' and result.issues[0].message.startswith('Блок не заполнен')


@pytest.mark.asyncio
@pytest.mark.parametrize('times', [1, 2])
async def test_a_review_that_stalls_is_made_once_more_with_the_same_input(tmp_path, times):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    fixture.transport.scripted = failing_first(fixture, 'STALLED', review=True, times=times)
    schemas = schemas_of(fixture)
    result = await run(fixture)
    assert result.state == 'published'
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'review', 'review']
    first, again = result.attempts[1:]
    assert again.input_hash == first.input_hash and len(result.review_inputs) == 2 and schemas[1] == schemas[2]
    if times == 1:
        assert result.tasks[0].state == 'accepted' and not result.issues
        assert [receipt.attempt_id for receipt in result.receipts] == [again.id]
    else:
        # K01 after the one more call: an incomplete review falls back to the source text.
        assert result.tasks[0].state == 'source_fallback' and not result.receipts
        assert result.issues[0].message.startswith('Показан исходный текст')


@pytest.mark.asyncio
@pytest.mark.parametrize('refusal', ['proposal', 'transport'])
async def test_a_reply_that_came_back_refused_gets_its_repair_and_no_more_call(tmp_path, refusal):
    # IMPORT_PROPOSAL_INVALID, or INVALID_RESULT with the reply kept: the repair names the refusal, as before.
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.scripted = refused_first(fixture, without_journal if refusal == 'proposal'
        else lambda reply: reply['payload'][0].update(year='not a year'))
    result = await run(fixture)
    assert result.state == 'published' and result.tasks[0].state == 'accepted'
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'primary_repair', 'replacement_review']
    assert result.attempts[0].raw_return and result.attempts[0].error_code == (
        'IMPORT_PROPOSAL_INVALID' if refusal == 'proposal' else 'INVALID_RESULT')


@pytest.mark.asyncio
async def test_a_repair_that_stalls_is_made_once_more_before_the_next_repair(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    first = refused_first(fixture, without_journal)
    stalled = []
    def script(request, value):
        if value.get('slot') == 'primary_repair' and not stalled:
            stalled.append(value)
            failure('STALLED')
        return first(request, value)
    fixture.transport.scripted = script
    result = await run(fixture)
    assert result.state == 'published' and result.tasks[0].state == 'accepted' and not result.issues
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'primary_repair', 'primary_repair',
        'replacement_review']
    assert result.attempts[1].input_hash == result.attempts[2].input_hash and spent_calls(result) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('cap', [2, 3])
async def test_the_one_more_call_counts_toward_the_cap_and_needs_room_for_its_review(tmp_path, cap):
    fixture = RuntimeFixture(tmp_path, cap=cap, fallback=False)
    fixture.transport.scripted = failing_first(fixture, 'STALLED')
    result = await run(fixture)
    assert result.state == 'published'
    if cap == 2:
        # One call left could not review a reply: the block falls back as it did without D155.
        assert [attempt.slot for attempt in result.attempts] == ['initial'] and len(fixture.transport.calls) == 1
        assert result.tasks[0].state == 'source_fallback' and result.task_results[0].value['diagnostics'] == ['STALLED']
    else:
        assert [attempt.slot for attempt in result.attempts] == ['initial', 'initial', 'review']
        assert result.tasks[0].state == 'accepted' and spent_calls(result) == cap


@pytest.mark.asyncio
async def test_a_call_that_stalls_when_the_import_time_is_up_gets_no_more_call(tmp_path):
    fixture, elapsed = RuntimeFixture(tmp_path, fallback=False), [0.0]
    fixture.pipeline.elapsed = lambda: elapsed[0]
    def script(_request, _value):
        elapsed[0] = 301.0
        failure('STALLED')
    fixture.transport.scripted = script
    result = await run(fixture)
    assert result.state == 'published' and result.inference_closed and result.tasks[0].state == 'source_fallback'
    assert [attempt.slot for attempt in result.attempts] == ['initial'] and len(fixture.transport.calls) == 1


@pytest.mark.asyncio
async def test_an_outline_and_its_review_that_stall_are_made_once_more_and_the_block_splits(tmp_path):
    src, raw = lines_source(2)
    fixture = RuntimeFixture(tmp_path, captured=entries_package(), src=src, original_bytes=raw, concurrency=2, cap=30)
    answer, stalled = entries_script(), set()
    def script(request, value):
        if value.get('slot') in {'outline', 'outline_review'} - stalled:
            stalled.add(value['slot'])
            failure('STALLED')
        return answer(request, value)
    fixture.transport.scripted = script
    result = await run(fixture)
    assert result.state == 'published' and len(result.tasks) == 4 and not result.issues
    slots = [attempt.slot for attempt in result.attempts]
    assert (slots.count('outline'), slots.count('outline_review')) == (2, 2) and spent_calls(result) == 8
    journals = [cell.raw_input for record in fixture.current().project.facts.extensions for cell in record.cells
        if cell.field_key == 'journal']
    assert journals == ['Systems Notes', 'Queue Review']


@pytest.mark.asyncio
async def test_a_resume_after_a_saved_stall_makes_its_one_more_call(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    def script(request, value):
        if 'targets' in value:
            return satisfied_review(value)
        if len(fixture.transport.calls) == 1:
            # The stall is saved, then the process is lost before the next call.
            request.on_return(ContentTransportReturn(None, 'timed_out', 'STALLED', 1, ReportedUsage(), True,
                {'transport': 'controlled'}, 'medium'))
            raise SystemExit('controlled loss after a saved stall')
        return raw_proposal(fixture.source)
    fixture.transport.scripted = script
    with pytest.raises(SystemExit):
        await run(fixture)
    previous = fixture.current().pre_draft.template_operations[0]
    assert [(attempt.slot, attempt.state, attempt.error_code) for attempt in previous.attempts] == [
        ('initial', 'returned', 'STALLED')]
    result = await fixture.restart().run(fixture.project, resume_command(previous), admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'accepted' and not result.issues
    assert [attempt.slot for attempt in result.attempts] == ['initial', 'initial', 'review']
    assert fixture.transport.calls[1] == fixture.transport.calls[0] and spent_calls(result) == 3


@pytest.mark.asyncio
async def test_a_resume_after_a_lost_second_call_makes_no_third(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    def script(_request, _value):
        if len(fixture.transport.calls) == 1:
            failure('STALLED')
        raise SystemExit('controlled loss after the second dispatch')
    fixture.transport.scripted = script
    with pytest.raises(SystemExit):
        await run(fixture)
    previous = fixture.current().pre_draft.template_operations[0]
    assert [attempt.state for attempt in previous.attempts] == ['returned', 'dispatch_started']
    fixture.transport.reconcile = lambda attempt: CleanupProof(attempt.id, digest(attempt.owner), digest('terminal'),
        'controlled-owned-terminal')
    fixture.transport.scripted = lambda *_args: pytest.fail('a resume never makes a third call')
    result = await fixture.restart().run(fixture.project, resume_command(previous), admitted=fixture.admitted)
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert [attempt.state for attempt in result.attempts] == ['returned', 'outcome_unknown']
    assert spent_calls(result) == 2
    assert len(fixture.transport.calls) == 2
