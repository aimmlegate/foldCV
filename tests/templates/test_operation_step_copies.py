"""Import steps share what they do not change with their input and never change the input itself (S8 speed)."""

from packages.resume_core.template_import import (CleanupProof, cancel_operation, digest, dispatch_attempt, observe_time,
    reconcile_cleanup, record_return, reserve_attempt, resume_operation)
from tests.templates.pipeline_fixtures import NOW, cleaned, model, owner, ready_operation, resume_command, usage

LATER = '2026-10-21T00:00:05+00:00'


def frozen(operation):
    return operation.model_dump_json(by_alias=True)


def test_each_attempt_step_returns_a_separate_operation_and_leaves_its_input_unchanged():
    operation = ready_operation()
    task = operation.tasks[0].id
    steps = []
    before = frozen(operation)
    reserved, attempt = reserve_attempt(operation, task, 'initial', digest('request'), model(), owner(1), NOW)
    steps.append((operation, before, reserved))
    before = frozen(reserved)
    dispatched = dispatch_attempt(reserved, attempt, NOW)
    steps.append((reserved, before, dispatched))
    before = frozen(dispatched)
    returned = record_return(dispatched, attempt, '{"payload": {}}', 'completed', usage(), cleaned(), returned_at=LATER)
    steps.append((dispatched, before, returned))
    before = frozen(returned)
    proof = CleanupProof(attempt, digest(returned.attempts[0].owner), digest('proof'), 'controlled-terminal')
    reconciled = reconcile_cleanup(returned, proof, LATER)
    steps.append((returned, before, reconciled))
    for given, unchanged, result in steps:
        assert frozen(given) == unchanged
        # The result shares no attempt, task or list with its input.
        assert all(new is not old for new in result.attempts for old in given.attempts)
        assert all(new is not old for new in result.tasks for old in given.tasks)
        assert result.attempts is not given.attempts and result.cleanup_records is not given.cleanup_records
    assert [value.state for value in reconciled.attempts] == ['returned'] and reconciled.cleanup_records


def test_observing_time_copies_only_the_fields_it_changes_and_resume_keeps_its_input():
    operation = ready_operation()
    before = frozen(operation)
    observed = observe_time(operation, LATER)
    assert observed.last_observed_at == LATER and operation.last_observed_at != LATER and frozen(operation) == before
    cancelled = cancel_operation(operation)
    before = frozen(cancelled)
    command = resume_command(cancelled)
    resumed = resume_operation(cancelled, command, LATER)
    assert frozen(cancelled) == before and resumed.authorizations[-1].id == command.authorization_id
    assert [task.state for task in cancelled.tasks] != [task.state for task in resumed.tasks] or cancelled.state != resumed.state
