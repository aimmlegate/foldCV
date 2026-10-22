"""Canonical saves cannot erase spending, captured inputs or completed review evidence."""

from .project_store import ProjectStoreFailure
from .template_import import instant


def fail():
    raise ProjectStoreFailure('PROJECT_SAVE_FAILED')


def _append_only(before, after, *, key=lambda value: value.id, mutable=()):
    if [key(value) for value in after[:len(before)]] != [key(value) for value in before]:
        fail()
    for old, new in zip(before, after):
        if old.model_dump(exclude=set(mutable)) != new.model_dump(exclude=set(mutable)):
            fail()


def retain_operation(before, after):
    if (before.id, before.project_id, before.client_request_id, before.capture, before.captured_relation_revisions,
            before.captured_items) != (after.id, after.project_id, after.client_request_id, after.capture,
            after.captured_relation_revisions, after.captured_items):
        fail()
    if before.inference_closed and not after.inference_closed:
        fail()
    if before.last_observed_at is not None and (after.last_observed_at is None or instant(after.last_observed_at) < instant(before.last_observed_at)):
        fail()
    for name in ('allocations', 'relation_allocations', 'task_inputs', 'review_inputs', 'receipts', 'cleanup_records', 'finalization_history',
                 'task_results', 'issues'):
        key = ((lambda value: (value.task_id, value.discovery_attempt_id, value.key)) if name in {'allocations', 'relation_allocations'}
            else (lambda value: value.attempt_id) if name == 'cleanup_records' else (lambda value: value.id))
        _append_only(getattr(before, name), getattr(after, name), key=key)
    _append_only(before.authorizations, after.authorizations, mutable={'state'})
    for old, new in zip(before.authorizations, after.authorizations):
        if old.state == 'cancelled' and new.state != 'cancelled':
            fail()
    if [value.id for value in before.tasks] != [value.id for value in after.tasks]:
        fail()
    captured = {value.task_id for value in before.task_inputs}
    for old, new in zip(before.tasks, after.tasks):
        if any(getattr(old, name) != getattr(new, name) for name in ('operation_id', 'block_id', 'kind', 'dependencies')):
            fail()
        if old.id in captured and old.input_hash != new.input_hash:
            fail()
        if not set(old.allowed_handles) <= set(new.allowed_handles) or new.attempt_ids[:len(old.attempt_ids)] != old.attempt_ids:
            fail()
    _append_only(before.attempts, after.attempts, mutable={'state', 'owner', 'dispatched_at', 'return_hash', 'usage', 'cleanup',
        'proposal_record_id', 'review_input_record_id', 'review_receipt_id', 'raw_return', 'raw_return_hash',
        'outcome', 'error_code', 'returned_at'})
    transitions = {'reserved': {'reserved', 'dispatch_started', 'outcome_unknown', 'released'},
        'dispatch_started': {'dispatch_started', 'returned', 'outcome_unknown', 'released'},
        'returned': {'returned', 'reconciled', 'released'}, 'outcome_unknown': {'outcome_unknown', 'returned', 'reconciled', 'released'},
        'reconciled': {'reconciled'}, 'released': {'released'}}
    for old, new in zip(before.attempts, after.attempts):
        if new.state not in transitions[old.state]:
            fail()
        if any(getattr(old.owner, name) != getattr(new.owner, name) for name in ('reservation_id', 'incarnation_id', 'generation', 'lease_id')):
            fail()
        for name in ('process_start_witness', 'transport_session_id', 'transport_turn_id', 'pid'):
            if getattr(old.owner, name) is not None and getattr(old.owner, name) != getattr(new.owner, name):
                fail()
        for name in ('dispatched_at', 'return_hash', 'raw_return', 'raw_return_hash', 'returned_at',
                     'proposal_record_id', 'review_input_record_id', 'review_receipt_id', 'error_code'):
            if getattr(old, name) is not None and getattr(old, name) != getattr(new, name):
                fail()
        for name in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
            if getattr(old.usage, name) is not None and getattr(old.usage, name) != getattr(new.usage, name):
                fail()
        if old.usage.complete and not new.usage.complete or old.cleanup.state == 'verified' and old.cleanup != new.cleanup:
            fail()
        if old.outcome is not None and new.outcome != old.outcome and not (old.outcome == 'completed'
                and old.state != 'reconciled' and new.outcome in {'invalid_payload', 'transport_failure', 'cleanup_failure', 'cancelled', 'timed_out'}):
            fail()
        if new.state == 'released' and old.state != 'released' and not any(
                proof.attempt_id == new.id and proof.never_dispatched for proof in after.cleanup_records):
            fail()
    _append_only(before.proposals, after.proposals, mutable={'state', 'applied_receipt_id', 'admitted_cell_ids', 'admitted_relation_ids',
        'admitted_record_revisions', 'admitted_relation_revisions'})
    for old, new in zip(before.proposals, after.proposals):
        if old.applied_receipt_id is not None and (old.state, old.applied_receipt_id, old.admitted_cell_ids, old.admitted_relation_ids) != (
                new.state, new.applied_receipt_id, new.admitted_cell_ids, new.admitted_relation_ids):
            fail()
        if old.applied_receipt_id is not None and (old.admitted_record_revisions, old.admitted_relation_revisions) != (
                new.admitted_record_revisions, new.admitted_relation_revisions):
            fail()
    if before.finalization is not None and before.finalization != after.finalization:
        if (before.finalization not in after.finalization_history or after.finalization is None
                or before.finalization.candidate_hash != after.finalization.candidate_hash
                or not after.authorizations or after.authorizations[-1].kind != 'resume'
                or after.finalization.authorization_id != after.authorizations[-1].id
                or before.finalization.authorization_id == after.finalization.authorization_id):
            fail()
    if before.state == 'published' and (after.state != 'published' or before.publication != after.publication):
        fail()
    retain_exports(before.export_attempts, after.export_attempts)


def retain_exports(before, after):
    _append_only(before, after, mutable={'state', 'artifact_hash', 'error_code'})
    export_states = {'pending': {'pending', 'running', 'completed', 'failed'}, 'running': {'running', 'completed', 'failed'},
        'completed': {'completed'}, 'failed': {'failed'}}
    for old, new in zip(before, after):
        if new.state not in export_states[old.state] or old.state in {'completed', 'failed'} and old != new:
            fail()
