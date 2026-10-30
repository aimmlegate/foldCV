"""Spending, resume and cleanup remain bound to the original captured operation."""

from dataclasses import replace
from itertools import count

import pytest

from packages.resume_core.models.template_import import CleanupOutcome
from packages.resume_core.template_import import (CleanupProof, ProcessingDeadline, TemplateImportFailure,
    admit_operation, cancel_operation, capture_task_input, digest, dispatch_attempt, observe_time, reconcile_cleanup,
    owed_reviews, record_return, recover_operation, reserve_attempt, resume_operation, spent_calls, start_operation)
from tests.templates.pipeline_fixtures import (NOW, blocks_package, cleaned, owner, ready_operation, resume_command, setup_operation,
    usage)


def reserve(operation, slot='initial', index=1):
    return reserve_attempt(operation, operation.tasks[0].id, slot, digest(slot),
        operation.capture.fallback if slot == 'fallback_repair' else operation.capture.primary, owner(index), NOW)


def returned(operation, attempt):
    operation = dispatch_attempt(operation, attempt, NOW)
    return record_return(operation, attempt, '{"payload":[]}', 'completed', usage(), cleaned())


def test_start_replays_only_with_the_same_project_request_and_exact_capture():
    operation, command, package, source, facts = setup_operation()
    again, created = start_operation(operation.project_id, command, package, [source], facts, [operation], NOW)
    assert not created and again == operation
    different = command.model_copy(deep=True)
    different.capture.allow_text_rewrite = False
    with pytest.raises(TemplateImportFailure, match='IMPORT_IDEMPOTENCY_CONFLICT'):
        start_operation(operation.project_id, different, package, [source], facts, [operation], NOW)
    different.client_request_id = 'explicit-new-request'
    with pytest.raises(TemplateImportFailure, match='IMPORT_OPERATION_ACTIVE'):
        start_operation(operation.project_id, different, package, [source], facts, [operation], NOW)
    prior = cancel_operation(operation)
    fresh, created = start_operation(operation.project_id, different, package, [source], facts, [prior], NOW)
    assert created and fresh.id != operation.id and not fresh.attempts


def test_admission_starts_one_deadline_and_queued_time_is_free():
    operation = setup_operation()[0]
    assert operation.admitted_at is None and operation.expires_at is None
    started = admit_operation(operation, '2026-10-21T01:00:00+00:00')
    assert started.expires_at == '2026-10-21T01:05:00+00:00'
    resumed = resume_operation(started, resume_command(started), '2026-10-21T01:04:00+00:00')
    assert resumed.expires_at == started.expires_at and resumed.capture == started.capture
    assert admit_operation(resumed, '2026-10-21T01:04:30+00:00').expires_at == started.expires_at


@pytest.mark.parametrize('wall,elapsed', [('2026-10-21T00:05:00+00:00', 1), (NOW, 300),
    ('2026-10-20T23:59:59+00:00', 1)])
def test_wall_elapsed_expiry_and_rollback_never_grant_more_inference(wall, elapsed):
    operation = ready_operation()
    clock = ProcessingDeadline.capture(operation, NOW, 0)
    assert clock.remaining(operation, wall, elapsed) == 0
    closed = observe_time(operation, wall, elapsed_remaining=clock.remaining(operation, wall, elapsed))
    assert closed.inference_closed and closed.state == 'cleanup_pending'
    resumed = resume_operation(closed, resume_command(closed), '2026-10-21T00:06:00+00:00')
    assert resumed.inference_closed and resumed.expires_at == operation.expires_at
    with pytest.raises(TemplateImportFailure, match='IMPORT_PROCESSING_EXHAUSTED'):
        reserve(resumed)


def test_reservations_are_sequential_and_not_refunded_from_usage():
    # Three calls: a repair needs room for its review, so the repair and that review fill the cap.
    operation = ready_operation(cap=3)
    operation, attempt = reserve(operation)
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        reserve(operation, 'primary_repair', 2)
    operation = returned(operation, attempt)
    operation.attempts[0].usage.complete = False
    assert spent_calls(operation) == 1
    with pytest.raises(TemplateImportFailure, match='IMPORT_SLOT_SPENT'):
        reserve(operation)
    operation, repair = reserve(operation, 'primary_repair', 2)
    operation = returned(operation, repair)
    with pytest.raises(TemplateImportFailure, match='IMPORT_CALL_CAP'):
        reserve(operation, 'fallback_repair', 3)


def parallel_operation(blocks, concurrency):
    operation, _command, _captured, src, _facts = setup_operation(captured=blocks_package(blocks), concurrency=concurrency, cap=20)
    operation = admit_operation(operation, NOW)
    for task in operation.tasks:
        operation = capture_task_input(operation, task.id, {'protocol': 'template_import_v1',
            'sources': [src.model_dump(mode='json', by_alias=True)], 'effectiveCells': [], 'tools': []}, [], NOW)
    return operation


def reserve_task(operation, task, slot, index):
    return reserve_attempt(operation, task, slot, digest([task, slot]), operation.capture.primary, owner(index), NOW)


def test_parallel_reservations_stay_within_the_captured_concurrency():
    # CT10: two blocks may be in flight at once; a third waits, and one block never has two attempts in flight.
    operation = parallel_operation(3, 2)
    first, second, third = [task.id for task in operation.tasks]
    operation, attempt = reserve_task(operation, first, 'initial', 1)
    operation, _other = reserve_task(operation, second, 'initial', 2)
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        reserve_task(operation, third, 'initial', 3)
    operation = dispatch_attempt(operation, attempt, NOW)
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        reserve_task(operation, first, 'review', 4)
    operation = record_return(operation, attempt, '{"payload":[]}', 'completed', usage(), cleaned())
    # A returned attempt with proved cleanup frees its place: the third block and the first block's review start.
    operation, _third = reserve_task(operation, third, 'initial', 5)
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        reserve_task(operation, first, 'review', 6)
    assert spent_calls(operation) == 3
    assert sorted(attempt.state for attempt in operation.attempts) == ['reserved', 'reserved', 'returned']


def test_one_concurrency_keeps_the_sequential_rule_across_blocks():
    operation = parallel_operation(2, 1)
    first, second = [task.id for task in operation.tasks]
    operation, attempt = reserve_task(operation, first, 'initial', 1)
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        reserve_task(operation, second, 'initial', 2)
    operation = returned(operation, attempt)
    reserve_task(operation, second, 'initial', 3)


def test_unknown_cleanup_of_one_parallel_block_stops_every_other_block():
    operation = parallel_operation(2, 2)
    first, second = [task.id for task in operation.tasks]
    operation, attempt = reserve_task(operation, first, 'initial', 1)
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, None, 'transport_failure', usage(),
        CleanupOutcome(state='unknown', evidenceHash=None, witness=None))
    assert operation.state == 'fenced'
    with pytest.raises(TemplateImportFailure):
        reserve_task(operation, second, 'initial', 2)


def test_a_restart_fences_every_parallel_attempt_still_in_flight():
    operation = parallel_operation(3, 3)
    first, second, _third = [task.id for task in operation.tasks]
    operation, attempt = reserve_task(operation, first, 'initial', 1)
    operation, _other = reserve_task(operation, second, 'initial', 2)
    recovered = recover_operation(dispatch_attempt(operation, attempt, NOW))
    assert recovered.state == 'fenced' and [value.state for value in recovered.attempts] == ['outcome_unknown', 'outcome_unknown']
    assert spent_calls(recovered) == 2
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        resume_operation(recovered, resume_command(recovered), NOW)


@pytest.mark.parametrize('value', [0, 5, True])
def test_the_captured_concurrency_is_a_bounded_integer(value):
    from pydantic import ValidationError
    from packages.resume_core.models.template_import import RuntimePolicy
    with pytest.raises(ValidationError):
        RuntimePolicy.model_validate({'callCap': 1, 'concurrency': value, 'processingSeconds': 300, 'cleanupSeconds': 5,
            'finalizationSeconds': 30, 'primaryRepairs': 1, 'fallbackRepairs': 1}, strict=True)


def test_unknown_fallback_dispatch_stays_charged_after_verified_cleanup_and_resume():
    operation = ready_operation()
    for index, slot in enumerate(['initial', 'primary_repair'], 1):
        operation, attempt = reserve(operation, slot, index)
        operation = returned(operation, attempt)
    operation, fallback = reserve(operation, 'fallback_repair', 3)
    operation = dispatch_attempt(operation, fallback, NOW)
    recovered = recover_operation(operation)
    assert recovered.state == 'fenced' and spent_calls(recovered) == 3
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        resume_operation(recovered, resume_command(recovered), NOW)
    proof = CleanupProof(fallback, digest(recovered.attempts[-1].owner), digest('owned-transport-terminal'), 'verified-owned-transport')
    reconciled = reconcile_cleanup(recovered, proof, NOW)
    resumed = resume_operation(reconciled, resume_command(reconciled), NOW)
    assert resumed.id == operation.id and resumed.capture == operation.capture and resumed.expires_at == operation.expires_at
    assert resumed.attempts[-1].state == 'outcome_unknown' and spent_calls(resumed) == 3
    with pytest.raises(TemplateImportFailure, match='IMPORT_SLOT_SPENT'):
        reserve(resumed, 'fallback_repair', 4)


def test_only_attempt_bound_never_dispatch_proof_releases_a_reservation():
    operation = ready_operation()
    operation, attempt = reserve(operation)
    proof = CleanupProof(attempt, digest(operation.attempts[0].owner), digest('trusted-no-launch'), 'reservation-never-launched', True)
    for wrong in [replace(proof, owner_hash=digest('reused-pid')), replace(proof, witness='')]:
        with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_PROOF_INVALID'):
            reconcile_cleanup(operation, wrong, NOW)
    released = reconcile_cleanup(operation, proof, NOW)
    assert spent_calls(released) == 0 and released.attempts[0].state == 'released'
    reserved, _ = reserve(released, index=2)
    assert spent_calls(reserved) == 1


def test_explicit_new_start_cannot_escape_unknown_cleanup_in_a_cancelled_operation():
    operation, attempt = reserve(ready_operation())
    operation = cancel_operation(dispatch_attempt(operation, attempt, NOW))
    _, command, package, source, facts = setup_operation()
    command.client_request_id = 'explicit-new-start'
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        start_operation(operation.project_id, command, package, [source], facts, [operation], NOW)


def test_persisted_return_replays_exactly_and_conflicts_never_replace_it():
    operation, attempt = reserve(ready_operation())
    operation = returned(operation, attempt)
    assert record_return(operation, attempt, '{"payload":[]}', 'completed', usage(), cleaned()) == operation
    with pytest.raises(TemplateImportFailure, match='IMPORT_RETURN_CONFLICT'):
        record_return(operation, attempt, '{"payload":[1]}', 'completed', usage(), cleaned())
    assert operation.attempts[0].raw_return == '{"payload":[]}'
    assert spent_calls(operation) == 1


def test_missing_pid_or_control_does_not_prove_cleanup():
    operation, attempt = reserve(ready_operation())
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, None, 'transport_failure', usage(),
        CleanupOutcome(state='unknown', evidenceHash=None, witness=None))
    assert operation.state == 'fenced' and spent_calls(operation) == 1
    assert operation.attempts[0].owner.pid is None
    with pytest.raises(TemplateImportFailure, match='IMPORT_CLEANUP_UNKNOWN'):
        resume_operation(operation, resume_command(operation), NOW)


def test_post_decode_failure_enriches_the_single_durable_transport_return():
    operation, attempt = reserve(ready_operation())
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, '{bad', 'completed', usage(), cleaned(), returned_at=NOW)
    enriched = record_return(operation, attempt, '{bad', 'invalid_payload', usage(), cleaned(), error_code='INVALID_RESULT')
    assert enriched.attempts[0].outcome == 'invalid_payload'
    assert enriched.attempts[0].returned_at == NOW and enriched.attempts[0].error_code == 'INVALID_RESULT'
    assert spent_calls(enriched) == 1
    for kwargs in [{'outcome': 'completed'}, {'outcome': 'invalid_payload', 'error_code': 'CLI_FAILED'},
                   {'outcome': 'invalid_payload', 'returned_at': '2026-10-21T00:00:01+00:00'}]:
        with pytest.raises(TemplateImportFailure, match='IMPORT_RETURN_CONFLICT'):
            record_return(enriched, attempt, '{bad', usage=usage(), cleanup=cleaned(), **kwargs)


def test_return_observed_during_wall_rollback_closes_inference_permanently():
    operation, attempt = reserve(ready_operation())
    operation = dispatch_attempt(operation, attempt, NOW)
    observed = record_return(operation, attempt, '{"payload":[]}', 'completed', usage(), cleaned(),
        returned_at='2026-10-20T23:59:59+00:00')
    assert observed.inference_closed and observed.attempts[0].raw_return == '{"payload":[]}'
    with pytest.raises(TemplateImportFailure, match='IMPORT_PROCESSING_EXHAUSTED'):
        reserve_attempt(observed, operation.tasks[0].id, 'review', digest('review'), operation.capture.primary,
            owner(2), '2026-10-21T00:00:01+00:00')


def test_task_input_is_immutable_and_cancelled_authority_needs_explicit_resume():
    operation = ready_operation()
    with pytest.raises(TemplateImportFailure, match='IMPORT_INPUT_IMMUTABLE'):
        capture_task_input(operation, operation.tasks[0].id, {'tools': ['save_import']}, [], NOW)
    cancelled = cancel_operation(operation)
    with pytest.raises(TemplateImportFailure, match='IMPORT_AUTHORITY_REVOKED'):
        reserve(cancelled)
    resumed = resume_operation(cancelled, resume_command(cancelled), NOW)
    assert resumed.capture == operation.capture and resumed.task_inputs == operation.task_inputs
    reserved, _ = reserve(resumed)
    assert spent_calls(reserved) == 1
    assert cancel_operation(reserved, commit_claimed=True) == reserved


def finished(operation, attempt, *, outcome='completed'):
    return record_return(dispatch_attempt(operation, attempt, NOW), attempt, '{}', outcome, usage(), cleaned(), returned_at=NOW)


def test_a_repair_holds_the_call_of_its_review_against_parallel_blocks():
    operation, _command, _captured, _src, _facts = setup_operation(captured=blocks_package(3), concurrency=3, cap=6)
    operation = admit_operation(operation, NOW)
    for task in operation.tasks:
        operation = capture_task_input(operation, task.id, {'protocol': 'template_import_v1'}, [], NOW)
    tasks, serial = operation.tasks, count(1)
    def take(value, task, slot):
        return reserve_task(value, task.id, slot, next(serial))
    for task in tasks[:2]:
        for slot in ['initial', 'review']:
            operation, attempt = take(operation, task, slot)
            operation = finished(operation, attempt)
    operation, repair = take(operation, tasks[0], 'primary_repair')
    # Five of six calls are spent: the sixth is the first repair's review, not free for another block.
    assert owed_reviews(operation) == 1
    for task, slot in [(tasks[1], 'primary_repair'), (tasks[2], 'initial')]:
        with pytest.raises(TemplateImportFailure) as caught:
            take(operation, task, slot)
        assert caught.value.code == 'IMPORT_CALL_CAP'
    # A refused repair gets no review, so the call comes free.
    refused = finished(operation, repair, outcome='invalid_payload')
    assert owed_reviews(refused) == 0
    assert take(refused, tasks[2], 'initial')
    # The review takes the call its repair held.
    done = finished(operation, repair)
    assert owed_reviews(done) == 1
    reviewed, _attempt = take(done, tasks[0], 'replacement_review')
    assert spent_calls(reviewed) == 6 and owed_reviews(reviewed) == 0
