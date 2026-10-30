"""Pure, durable import transitions; workers never own spending or publication."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

from .models.template_import import (AttemptCleanupRecord, CleanupOutcome, EntryPart, EntryScope, FinalizationCandidate, ImportAttempt,
    ImportAuthorization, ImportOperation, ImportTask, ObservedUsage, PublicationOutcome, TaskInputRecord)
from .templates.compiler import canonical, dependency_order, sha256


TERMINAL_TASKS = frozenset({'accepted', 'empty', 'source_fallback', 'cancelled', 'technical_failure'})
GENERATION_SLOTS = frozenset({'initial', 'primary_repair', 'fallback_repair'})
REPAIR_SLOTS = frozenset({'primary_repair', 'fallback_repair'})
# D117: the outline of a block that extracts its entries on their own, and the review of that outline.
OUTLINE_SLOTS = frozenset({'outline', 'outline_review'})
IN_FLIGHT = frozenset({'reserved', 'dispatch_started'})


def processing_protocol(submission):
    if submission.kind != 'processing':
        return None
    if submission.protocol is not None:
        return submission.protocol
    return 'agent_import_v1' if 'save_import' in submission.tools else 'fixed_v1'


class TemplateImportFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def identity(prefix):
    return prefix + '-' + uuid.uuid4().hex


def same_captured_model(model, expected):
    """The captured model, effort included: every call runs the effort chosen for the import (D114)."""
    return expected is not None and model == expected


def digest(value):
    def wire(item):
        if hasattr(item, 'model_dump'):
            return item.model_dump(mode='json', by_alias=True)
        if isinstance(item, dict):
            return {key: wire(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [wire(child) for child in item]
        return item
    return sha256(canonical(wire(value)))


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('import timestamps require an explicit timezone')
    return parsed.astimezone(timezone.utc)


def expiry(value, seconds):
    return (instant(value) + timedelta(seconds=seconds)).isoformat()


def checked(operation):
    # The JSON round trip validates the same model about a quarter faster than through Python objects.
    return ImportOperation.model_validate_json(operation.model_dump_json(by_alias=True))


def fork(operation, *, attempts=(), tasks=(), lists=()):
    """A working copy for a step that changes only the given attempts and tasks and appends only to the given lists:
    those are copied, everything else is shared with the input, which stays as it was. The step ends in checked(),
    which builds a separate operation; a deep copy of the whole operation per step was most of the local import time."""
    update = {name: list(getattr(operation, name)) for name in lists}
    if attempts:
        update['attempts'] = [value.model_copy(deep=True) if value.id in attempts else value
            for value in update.get('attempts', operation.attempts)]
    if tasks:
        update['tasks'] = [value.model_copy(deep=True) if value.id in tasks else value for value in operation.tasks]
    return operation.model_copy(update=update)


def task_in(operation, identifier):
    task = next((task for task in operation.tasks if task.id == identifier), None)
    if task is None:
        raise TemplateImportFailure('IMPORT_TASK_UNKNOWN')
    return task


def attempt_in(operation, identifier):
    attempt = next((attempt for attempt in operation.attempts if attempt.id == identifier), None)
    if attempt is None:
        raise TemplateImportFailure('IMPORT_ATTEMPT_UNKNOWN')
    return attempt


def children_of(operation, parent_id):
    """The tasks a block task added while running (D117): its entries and its outline review, in the order added."""
    return [task for task in operation.tasks if task.parent_task_id == parent_id]


def entries_of(operation, parent_id):
    return [task for task in children_of(operation, parent_id) if task.entry is not None]


def authorization(operation):
    current = operation.authorizations[-1] if operation.authorizations else None
    if (current is None or current.state != 'active' or current.authority_hash != operation.capture.authority_hash
            or current.dependency_hash != operation.capture.dependency_hash):
        raise TemplateImportFailure('IMPORT_AUTHORITY_REVOKED')
    return current


def start_operation(project_id, command, package, sources, facts, existing, now, *, id_factory=identity):
    for operation in existing:
        if operation.project_id == project_id and operation.client_request_id == command.client_request_id:
            if digest(operation.capture) != digest(command.capture):
                raise TemplateImportFailure('IMPORT_IDEMPOTENCY_CONFLICT')
            return operation.model_copy(deep=True), False
    if any(attempt.cleanup.state != 'verified' for operation in existing for attempt in operation.attempts):
        raise TemplateImportFailure('IMPORT_CLEANUP_UNKNOWN')
    if any(operation.state not in {'cancelled', 'failed', 'published'} for operation in existing):
        raise TemplateImportFailure('IMPORT_OPERATION_ACTIVE')
    capture = command.capture
    if (capture.package_hash != package.package_hash or capture.source_hashes != {s.id: s.byte_sha256 for s in sources}
            or capture.fact_revisions != {record.id: record.revision for record in [*facts.records, *facts.extensions]
                if getattr(record, 'active', True)}):
        raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
    instant(now)
    from .template_capture import capture_existing_items
    try:
        captured_items = capture_existing_items(facts, package, existing)
    except ValueError:
        raise TemplateImportFailure('IMPORT_IDENTITY_PREPARATION_REQUIRED') from None
    identifier = id_factory('import')
    order = dependency_order(package.definition)
    declarations = {item.id: item for item in [*package.definition.operations, *package.definition.blocks]}
    operations = {item.id for item in package.definition.operations}
    task_ids = {key: id_factory('task') for key in sorted(order, key=order.get)}
    tasks = []
    for key in sorted(order, key=order.get):
        item = declarations[key]
        dependencies = set(item.depends_on)
        refs = item.inputs if key in operations else item.selectors
        dependencies.update(ref.id for ref in refs if ref.kind in {'operation', 'block'})
        if key not in operations:
            if item.operation:
                dependencies.add(item.operation)
            if item.when:
                dependencies.add(item.when.operation)
        kind = ('derive' if key in operations or item.mode == 'derived' else 'source_copy' if item.mode == 'source_copy'
            else 'rewrite' if capture.allow_text_rewrite and item.rewrite.fields else 'extract')
        tasks.append(ImportTask(id=task_ids[key], operationId=identifier, blockId=key, kind=kind,
            dependencies=[task_ids[dep] for dep in sorted(dependencies, key=order.get)],
            inputHash=digest({'capture': capture, 'declaration': item}), allowedHandles=[], expectedChecks=[],
            state='pending', attemptIds=[], proposalHash=None, receiptIds=[], issueIds=[]))
    operation = ImportOperation(schemaVersion=1, id=identifier, projectId=project_id, capture=capture,
        state='captured', admittedAt=None, expiresAt=None, lastObservedAt=None, tasks=tasks, allocations=[],
        capturedItems=captured_items,
        attempts=[], proposals=[], reviewInputs=[], receipts=[], finalization=None,
        publication=PublicationOutcome(state='pending', intentId=None, workspaceHash=None, errorCode=None),
        exportAttempts=[], clientRequestId=command.client_request_id,
        capturedRelationRevisions={value.id: value.revision for value in facts.relations},
        authorizations=[ImportAuthorization(id=id_factory('authorization'), kind='start', state='active',
            authorizedAt=now, authorityHash=capture.authority_hash, dependencyHash=capture.dependency_hash)])
    return checked(operation), True


def admit_operation(operation, now):
    result = operation.model_copy(deep=True)
    authority = authorization(result)
    if result.admitted_at is None:
        result.admitted_at, result.expires_at = now, expiry(now, result.capture.policy.processing_seconds)
        result.last_observed_at = now
    if result.state == 'captured':
        result.state = 'processing'
    return checked(observe_time(result, now))


def observe_time(operation, now, *, elapsed_remaining=None):
    # Only top-level time and state fields change, which no operation validator reads, so a shallow copy is safe;
    # a deep copy and full check per observation were most of the local time between calls (LIVE-08 replay).
    current = instant(now)
    change = {}
    if operation.last_observed_at is not None and current < instant(operation.last_observed_at):
        change['inference_closed'] = True
    elif operation.expires_at is not None and (current >= instant(operation.expires_at)
            or elapsed_remaining is not None and elapsed_remaining <= 0):
        change['inference_closed'] = True
    else:
        change['last_observed_at'] = now
    if change.get('inference_closed', operation.inference_closed) and operation.state == 'processing':
        change['state'] = 'cleanup_pending'
    return operation.model_copy(update=change)


@dataclass(frozen=True)
class ProcessingDeadline:
    operation_id: str
    elapsed_expiry: float

    @classmethod
    def capture(cls, operation, wall_now, elapsed_now):
        remaining = max(0, (instant(operation.expires_at) - instant(wall_now)).total_seconds())
        if operation.last_observed_at is not None and instant(wall_now) < instant(operation.last_observed_at):
            remaining = 0
        return cls(operation.id, elapsed_now + remaining)

    def remaining(self, operation, wall_now, elapsed_now):
        if operation.id != self.operation_id or operation.inference_closed:
            return 0
        if operation.last_observed_at is not None and instant(wall_now) < instant(operation.last_observed_at):
            return 0
        return max(0, min(self.elapsed_expiry - elapsed_now,
            (instant(operation.expires_at) - instant(wall_now)).total_seconds()))


def capture_task_input(operation, task_id, value, handles, now, *, id_factory=identity):
    result = operation.model_copy(deep=True)
    task = task_in(result, task_id)
    checksum = digest(value)
    existing = next((record for record in result.task_inputs if record.task_id == task_id), None)
    if existing is not None:
        if existing.input_hash != checksum or not set(handles) <= set(task.allowed_handles):
            raise TemplateImportFailure('IMPORT_INPUT_IMMUTABLE')
        return result
    if task.state != 'pending' or task.attempt_ids or any(task_in(result, dep).state not in {'accepted', 'empty', 'source_fallback'}
            for dep in task.dependencies):
        raise TemplateImportFailure('IMPORT_TASK_NOT_READY')
    task.input_hash, task.allowed_handles = checksum, list(handles)
    result.task_inputs.append(TaskInputRecord(id=id_factory('input'), taskId=task_id, inputHash=checksum,
        value=value, capturedAt=now))
    return checked(result)


ENTRY_TITLE = 120


def add_entry_tasks(operation, parent_id, groups, origin, *, id_factory=identity):
    """The entry tasks of a block task (D117), one per group of consecutive outline entries ((title, spans) each),
    after the entries it has, in this order. An entry task extracts as its block does, under the same dependencies,
    and reads the block's captured input."""
    result = fork(operation, lists=('tasks',))
    parent = task_in(result, parent_id)
    if (parent.parent_task_id is not None or parent.kind not in {'extract', 'rewrite'} or parent.state in TERMINAL_TASKS
            or not any(record.task_id == parent_id for record in result.task_inputs) or not all(groups)):
        raise TemplateImportFailure('IMPORT_TASK_NOT_READY')
    taken = max([task.entry.index for task in entries_of(result, parent_id)], default=0)
    for offset, group in enumerate(groups, 1):
        title = ', '.join(title for title, _spans in group)
        title = title if len(title) <= ENTRY_TITLE else title[:ENTRY_TITLE - 1].rstrip() + '…'
        scope = EntryScope(index=taken + offset, title=title, spans=[span for _title, spans in group for span in spans],
            parts=[EntryPart(title=part, spans=list(spans)) for part, spans in group], origin=origin)
        result.tasks.append(ImportTask(id=id_factory('task'), operationId=result.id, blockId=parent.block_id, kind=parent.kind,
            dependencies=list(parent.dependencies), inputHash=digest({'parent': parent.input_hash, 'entry': scope}),
            allowedHandles=[], expectedChecks=[], state='pending', attemptIds=[], proposalHash=None, receiptIds=[], issueIds=[],
            parentTaskId=parent_id, entry=scope))
    return checked(result)


def add_outline_review(operation, parent_id, *, id_factory=identity):
    """The one review of a block's outline (D117), added with the block's entries."""
    result = fork(operation, lists=('tasks',))
    parent = task_in(result, parent_id)
    if (parent.parent_task_id is not None or parent.kind not in {'extract', 'rewrite'} or parent.state in TERMINAL_TASKS
            or any(task.kind == 'outline_review' for task in children_of(result, parent_id))):
        raise TemplateImportFailure('IMPORT_TASK_NOT_READY')
    result.tasks.append(ImportTask(id=id_factory('task'), operationId=result.id, blockId=parent.block_id, kind='outline_review',
        dependencies=list(parent.dependencies), inputHash=digest({'parent': parent.input_hash, 'outline': 'review'}),
        allowedHandles=[], expectedChecks=[], state='pending', attemptIds=[], proposalHash=None, receiptIds=[], issueIds=[],
        parentTaskId=parent_id))
    return checked(result)


def spent_calls(operation):
    return sum(attempt.state != 'released' for attempt in operation.attempts)


def owed_reviews(operation, *, excluding=None):
    """Repairs still waiting for their review, each holding one call of the cap: a repair counts only after its review.
    A refused repair goes unreviewed and an ended task owes nothing."""
    ended = {task.id for task in operation.tasks if task.state in TERMINAL_TASKS}
    reviewed, owed = set(), 0
    for attempt in reversed(operation.attempts):
        if attempt.state == 'released' or attempt.task_id in ended or attempt.task_id == excluding:
            continue
        if attempt.slot in {'review', 'replacement_review'}:
            reviewed.add(attempt.task_id)
        elif attempt.slot in REPAIR_SLOTS and attempt.task_id not in reviewed and attempt.outcome in {None, 'completed'}:
            reviewed.add(attempt.task_id)
            owed += 1
    return owed


def cleanup_verified(operation):
    return all(attempt.cleanup.state == 'verified' for attempt in operation.attempts)


def reserve_attempt(operation, task_id, slot, input_hash, model, owner, now, *, request_value=None, id_factory=identity):
    result = fork(observe_time(operation, now), tasks={task_id}, lists=('attempts',))
    authority = authorization(result)
    if result.state != 'processing' or result.inference_closed or result.admitted_at is None:
        raise TemplateImportFailure('IMPORT_PROCESSING_EXHAUSTED')
    task = task_in(result, task_id)
    if task.state in TERMINAL_TASKS or not any(record.task_id == task_id for record in result.task_inputs):
        raise TemplateImportFailure('IMPORT_TASK_NOT_READY')
    # A finished attempt without cleanup proof fences new work. Attempts still in flight share the captured
    # concurrency (CT10), and one task never has two in flight; concurrency 1 keeps the sequential rule.
    in_flight = [attempt for attempt in result.attempts if attempt.state in IN_FLIGHT]
    if (any(attempt.state not in {'released', *IN_FLIGHT} and attempt.cleanup.state != 'verified' for attempt in result.attempts)
            or len(in_flight) >= result.capture.policy.concurrency or any(attempt.task_id == task_id for attempt in in_flight)):
        raise TemplateImportFailure('IMPORT_CLEANUP_UNKNOWN')
    # A repair takes its review's call with its own, in this one transition: parallel blocks saw the same free calls.
    needed = 2 if slot in REPAIR_SLOTS else 1
    held = owed_reviews(result, excluding=task_id if slot in {'review', 'replacement_review'} else None)
    if spent_calls(result) + held + needed > result.capture.policy.call_cap:
        raise TemplateImportFailure('IMPORT_CALL_CAP')
    prior = [attempt for attempt in result.attempts if attempt.task_id == task_id and attempt.state != 'released']
    if slot in GENERATION_SLOTS:
        if any(attempt.slot == slot for attempt in prior):
            raise TemplateImportFailure('IMPORT_SLOT_SPENT')
        expected = result.capture.fallback if slot == 'fallback_repair' else result.capture.primary
        if expected is None or not same_captured_model(model, expected):
            raise TemplateImportFailure('IMPORT_MODEL_NOT_CAPTURED')
        if slot != 'initial' and not any(attempt.slot == 'initial' for attempt in prior):
            raise TemplateImportFailure('IMPORT_REPAIR_WITHOUT_INITIAL')
        if slot == 'fallback_repair' and not any(attempt.slot == 'primary_repair' for attempt in prior):
            raise TemplateImportFailure('IMPORT_REPAIR_ORDER')
    elif slot in {'review', 'replacement_review'}:
        if not any(attempt.slot in GENERATION_SLOTS and attempt.state in {'returned', 'reconciled'}
                and attempt.outcome == 'completed' for attempt in prior):
            raise TemplateImportFailure('IMPORT_REVIEW_WITHOUT_PROPOSAL')
        if not any(same_captured_model(model, captured) for captured in [result.capture.primary, result.capture.fallback,
                result.capture.review]) or any(
                attempt.slot in {'review', 'replacement_review'} and attempt.input_hash == input_hash for attempt in prior):
            raise TemplateImportFailure('IMPORT_REVIEW_ALREADY_SPENT')
    elif slot == 'outline':
        # D117: a block task outlines its entries once, with the import model, before any extraction of its own.
        if task.parent_task_id is not None or task.kind not in {'extract', 'rewrite'}:
            raise TemplateImportFailure('IMPORT_ATTEMPT_SLOT')
        if any(attempt.slot in GENERATION_SLOTS or attempt.slot == 'outline' for attempt in prior):
            raise TemplateImportFailure('IMPORT_SLOT_SPENT')
        if not same_captured_model(model, result.capture.primary):
            raise TemplateImportFailure('IMPORT_MODEL_NOT_CAPTURED')
    elif slot == 'outline_review':
        if task.kind != 'outline_review':
            raise TemplateImportFailure('IMPORT_ATTEMPT_SLOT')
        if any(attempt.slot == 'outline_review' for attempt in prior):
            raise TemplateImportFailure('IMPORT_SLOT_SPENT')
        if not any(same_captured_model(model, captured) for captured in [result.capture.primary, result.capture.review]):
            raise TemplateImportFailure('IMPORT_MODEL_NOT_CAPTURED')
    else:
        raise TemplateImportFailure('IMPORT_ATTEMPT_SLOT')
    if any(attempt.owner.reservation_id == owner.reservation_id for attempt in result.attempts):
        raise TemplateImportFailure('IMPORT_LAUNCH_OWNER_REUSED')
    if request_value is not None and digest(request_value) != input_hash:
        raise TemplateImportFailure('IMPORT_ATTEMPT_INPUT_MISMATCH')
    attempt = ImportAttempt(id=id_factory('attempt'), operationId=result.id, taskId=task_id, slot=slot,
        inputHash=input_hash, model=model, state='reserved', owner=owner, reservedAt=now, dispatchedAt=None,
        returnHash=None, usage=ObservedUsage(inputTokens=None, cachedInputTokens=None, outputTokens=None, complete=False),
        cleanup=CleanupOutcome(state='pending', evidenceHash=None, witness=None), proposalRecordId=None,
        reviewInputRecordId=None, reviewReceiptId=None, rawReturn=None, rawReturnHash=None, requestValue=request_value,
        authorizationId=authority.id)
    result.attempts.append(attempt)
    task.attempt_ids.append(attempt.id)
    task.state = ('checking' if slot in {'review', 'replacement_review'}
        else 'running' if slot == 'initial' or slot in OUTLINE_SLOTS else 'repairing')
    return checked(result), attempt.id


def dispatch_attempt(operation, attempt_id, now):
    result = fork(observe_time(operation, now), attempts={attempt_id})
    authority = authorization(result)
    attempt = attempt_in(result, attempt_id)
    if (result.state != 'processing' or result.inference_closed or attempt.state != 'reserved'
            or attempt.authorization_id != authority.id):
        raise TemplateImportFailure('IMPORT_DISPATCH_DENIED')
    attempt.state, attempt.dispatched_at = 'dispatch_started', now
    return checked(result)


def record_return(operation, attempt_id, raw_return, outcome, usage, cleanup, *, error_code=None, returned_at=None):
    result = fork(observe_time(operation, returned_at) if returned_at is not None else operation, attempts={attempt_id})
    attempt = attempt_in(result, attempt_id)
    checksum = sha256(raw_return.encode()) if raw_return is not None else None
    if returned_at is not None:
        instant(returned_at)
    if attempt.state in {'returned', 'reconciled'}:
        if (attempt.raw_return_hash, attempt.usage, attempt.cleanup) != (checksum, usage, cleanup) or (
                returned_at is not None and attempt.returned_at != returned_at):
            raise TemplateImportFailure('IMPORT_RETURN_CONFLICT')
        if attempt.outcome != outcome:
            if (attempt.state != 'returned' or attempt.outcome != 'completed'
                    or outcome not in {'invalid_payload', 'transport_failure', 'cleanup_failure', 'cancelled', 'timed_out'}):
                raise TemplateImportFailure('IMPORT_RETURN_CONFLICT')
            attempt.outcome = outcome
        if error_code is not None:
            if attempt.error_code is not None and attempt.error_code != error_code:
                raise TemplateImportFailure('IMPORT_RETURN_CONFLICT')
            attempt.error_code = error_code
        return checked(result)
    if attempt.state not in {'dispatch_started', 'outcome_unknown'}:
        raise TemplateImportFailure('IMPORT_RETURN_WITHOUT_DISPATCH')
    attempt.state, attempt.outcome, attempt.error_code = 'returned', outcome, error_code
    attempt.raw_return, attempt.raw_return_hash, attempt.return_hash = raw_return, checksum, checksum
    attempt.returned_at = returned_at
    attempt.usage, attempt.cleanup = usage, cleanup
    if cleanup.state != 'verified':
        result.state = 'fenced'
    return checked(result)


@dataclass(frozen=True)
class CleanupProof:
    attempt_id: str
    owner_hash: str
    evidence_hash: str
    witness: str
    never_dispatched: bool = False


def reconcile_cleanup(operation, proof, now):
    result = fork(operation, attempts={proof.attempt_id}, lists=('cleanup_records',))
    attempt = attempt_in(result, proof.attempt_id)
    if (proof.owner_hash != digest(attempt.owner) or not proof.witness
            or proof.never_dispatched and (attempt.raw_return_hash is not None or attempt.outcome in {
                'completed', 'invalid_payload', 'refused', 'incomplete'} or attempt.state == 'reconciled')):
        raise TemplateImportFailure('IMPORT_CLEANUP_PROOF_INVALID')
    record = AttemptCleanupRecord(attemptId=attempt.id, ownerHash=proof.owner_hash,
        evidenceHash=proof.evidence_hash, witness=proof.witness, neverDispatched=proof.never_dispatched, verifiedAt=now)
    known = next((value for value in result.cleanup_records if value.attempt_id == attempt.id), None)
    if known is not None:
        if known.model_dump(exclude={'verified_at'}) != record.model_dump(exclude={'verified_at'}):
            raise TemplateImportFailure('IMPORT_CLEANUP_PROOF_CONFLICT')
        return result
    result.cleanup_records.append(record)
    attempt.cleanup = CleanupOutcome(state='verified', evidenceHash=proof.evidence_hash, witness=proof.witness)
    if proof.never_dispatched:
        attempt.state = 'released'
    elif attempt.state in {'reserved', 'dispatch_started'}:
        attempt.state = 'outcome_unknown'
    return checked(result)


def recover_operation(operation):
    result = operation.model_copy(deep=True)
    for attempt in result.attempts:
        if attempt.state in {'reserved', 'dispatch_started'}:
            attempt.state = 'outcome_unknown'
    if any(attempt.state == 'outcome_unknown' or attempt.cleanup.state != 'verified' for attempt in result.attempts):
        result.state = 'fenced'
    return checked(result)


def resume_operation(operation, command, now):
    if command.operation_id != operation.id or command.authority_hash != operation.capture.authority_hash:
        raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
    if operation.state == 'published':
        return operation.model_copy(deep=True)
    result = observe_time(operation, now)
    # Resuming changes the authorizations, the publication and task states: those are copied, the rest is shared.
    result = fork(result, tasks={task.id for task in result.tasks if task.state == 'cancelled'}, lists=('authorizations',))
    result.publication = result.publication.model_copy()
    if not cleanup_verified(result):
        raise TemplateImportFailure('IMPORT_CLEANUP_UNKNOWN')
    known = next((item for item in result.authorizations if item.id == command.authorization_id), None)
    if known is not None:
        if known != result.authorizations[-1] or known.state != 'active':
            raise TemplateImportFailure('IMPORT_AUTHORITY_REVOKED')
    else:
        result.authorizations.append(ImportAuthorization(id=command.authorization_id, kind='resume', state='active',
            authorizedAt=now, authorityHash=command.authority_hash, dependencyHash=result.capture.dependency_hash))
    result.state = 'cleanup_pending' if result.inference_closed else 'captured' if result.admitted_at is None else 'processing'
    if result.publication.state == 'cancelled':
        result.publication.state = 'pending'
    for task in result.tasks:
        if task.state == 'cancelled':
            task.state = 'pending'
    return checked(result)


def cancel_operation(operation, *, commit_claimed=False):
    result = operation.model_copy(deep=True)
    if commit_claimed or result.state == 'published':
        return result
    if result.authorizations:
        result.authorizations[-1].state = 'cancelled'
    result.state, result.publication.state = 'cancelled', 'cancelled'
    for task in result.tasks:
        if task.state not in TERMINAL_TASKS:
            task.state = 'cancelled'
    return checked(result)


# A sidecar may only move an operation forward: spending, captured inputs and review evidence are append-only.
def _refuse():
    from .project_store import ProjectStoreFailure
    raise ProjectStoreFailure('PROJECT_SAVE_FAILED')


def _append_only(before, after, *, key=lambda value: value.id, mutable=()):
    if [key(value) for value in after[:len(before)]] != [key(value) for value in before]:
        _refuse()
    # Compared field by field, not through two dumps per record: every import step checks every retained record.
    for old, new in zip(before, after):
        if old is new:
            continue
        if any(getattr(old, name) != getattr(new, name) for name in type(old).model_fields if name not in mutable):
            _refuse()


def retain_operation(before, after):
    if (before.id, before.project_id, before.client_request_id, before.capture, before.captured_relation_revisions,
            before.captured_items) != (after.id, after.project_id, after.client_request_id, after.capture,
            after.captured_relation_revisions, after.captured_items):
        _refuse()
    if before.inference_closed and not after.inference_closed:
        _refuse()
    if before.last_observed_at is not None and (after.last_observed_at is None or instant(after.last_observed_at) < instant(before.last_observed_at)):
        _refuse()
    for name in ('allocations', 'relation_allocations', 'task_inputs', 'review_inputs', 'receipts', 'cleanup_records', 'finalization_history',
                 'task_results', 'issues'):
        key = ((lambda value: (value.task_id, value.discovery_attempt_id, value.key)) if name in {'allocations', 'relation_allocations'}
            else (lambda value: value.attempt_id) if name == 'cleanup_records' else (lambda value: value.id))
        _append_only(getattr(before, name), getattr(after, name), key=key)
    _append_only(before.authorizations, after.authorizations, mutable={'state'})
    for old, new in zip(before.authorizations, after.authorizations):
        if old.state == 'cancelled' and new.state != 'cancelled':
            _refuse()
    if [value.id for value in after.tasks[:len(before.tasks)]] != [value.id for value in before.tasks]:
        _refuse()
    # D117: a running block task adds its entry tasks and outline review after the captured tasks; nothing else is added.
    added = after.tasks[len(before.tasks):]
    if added and (before.state not in {'processing', 'cleanup_pending'} or any(value.parent_task_id is None for value in added)):
        _refuse()
    captured = {value.task_id for value in before.task_inputs}
    for old, new in zip(before.tasks, after.tasks):
        if any(getattr(old, name) != getattr(new, name) for name in ('operation_id', 'block_id', 'kind', 'dependencies',
                'parent_task_id', 'entry')):
            _refuse()
        if old.id in captured and old.input_hash != new.input_hash:
            _refuse()
        if not set(old.allowed_handles) <= set(new.allowed_handles) or new.attempt_ids[:len(old.attempt_ids)] != old.attempt_ids:
            _refuse()
    _append_only(before.attempts, after.attempts, mutable={'state', 'owner', 'dispatched_at', 'return_hash', 'usage', 'cleanup',
        'proposal_record_id', 'review_input_record_id', 'review_receipt_id', 'raw_return', 'raw_return_hash',
        'outcome', 'error_code', 'returned_at'})
    transitions = {'reserved': {'reserved', 'dispatch_started', 'outcome_unknown', 'released'},
        'dispatch_started': {'dispatch_started', 'returned', 'outcome_unknown', 'released'},
        'returned': {'returned', 'reconciled', 'released'}, 'outcome_unknown': {'outcome_unknown', 'returned', 'reconciled', 'released'},
        'reconciled': {'reconciled'}, 'released': {'released'}}
    for old, new in zip(before.attempts, after.attempts):
        if new.state not in transitions[old.state]:
            _refuse()
        if any(getattr(old.owner, name) != getattr(new.owner, name) for name in ('reservation_id', 'incarnation_id', 'generation', 'lease_id')):
            _refuse()
        for name in ('process_start_witness', 'transport_session_id', 'transport_turn_id', 'pid'):
            if getattr(old.owner, name) is not None and getattr(old.owner, name) != getattr(new.owner, name):
                _refuse()
        for name in ('dispatched_at', 'return_hash', 'raw_return', 'raw_return_hash', 'returned_at',
                     'proposal_record_id', 'review_input_record_id', 'review_receipt_id', 'error_code'):
            if getattr(old, name) is not None and getattr(old, name) != getattr(new, name):
                _refuse()
        for name in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
            if getattr(old.usage, name) is not None and getattr(old.usage, name) != getattr(new.usage, name):
                _refuse()
        if old.usage.complete and not new.usage.complete or old.cleanup.state == 'verified' and old.cleanup != new.cleanup:
            _refuse()
        if old.outcome is not None and new.outcome != old.outcome and not (old.outcome == 'completed'
                and old.state != 'reconciled' and new.outcome in {'invalid_payload', 'transport_failure', 'cleanup_failure', 'cancelled', 'timed_out'}):
            _refuse()
        if new.state == 'released' and old.state != 'released' and not any(
                proof.attempt_id == new.id and proof.never_dispatched for proof in after.cleanup_records):
            _refuse()
    _append_only(before.proposals, after.proposals, mutable={'state', 'applied_receipt_id', 'admitted_cell_ids', 'admitted_relation_ids',
        'admitted_record_revisions', 'admitted_relation_revisions'})
    for old, new in zip(before.proposals, after.proposals):
        if old.applied_receipt_id is not None and (old.state, old.applied_receipt_id, old.admitted_cell_ids, old.admitted_relation_ids) != (
                new.state, new.applied_receipt_id, new.admitted_cell_ids, new.admitted_relation_ids):
            _refuse()
        if old.applied_receipt_id is not None and (old.admitted_record_revisions, old.admitted_relation_revisions) != (
                new.admitted_record_revisions, new.admitted_relation_revisions):
            _refuse()
    if before.finalization is not None and before.finalization != after.finalization:
        # A resume may renew a candidate nothing was published with, also with new content (a formatting date
        # changed meanwhile); a saved publication keeps its candidate.
        if (before.finalization not in after.finalization_history or after.finalization is None
                or before.publication.state == 'saved'
                or not after.authorizations or after.authorizations[-1].kind != 'resume'
                or after.finalization.authorization_id != after.authorizations[-1].id
                or before.finalization.authorization_id == after.finalization.authorization_id):
            _refuse()
    if before.state == 'published' and (after.state != 'published' or before.publication != after.publication):
        _refuse()
    retain_exports(before.export_attempts, after.export_attempts)


def retain_exports(before, after):
    _append_only(before, after, mutable={'state', 'artifact_hash', 'error_code'})
    export_states = {'pending': {'pending', 'running', 'completed', 'failed'}, 'running': {'running', 'completed', 'failed'},
        'completed': {'completed'}, 'failed': {'failed'}}
    for old, new in zip(before, after):
        if new.state not in export_states[old.state] or old.state in {'completed', 'failed'} and old != new:
            _refuse()


def finalization_hashes(operation, project):
    return {'operationId': operation.id, 'sourceHash': digest(operation.capture.source_hashes),
        'dependencyHash': operation.capture.dependency_hash, 'authorityHash': operation.capture.authority_hash,
        'packageHash': project.template_package.package_hash, 'documentHash': digest(project.document),
        'factsHash': digest(project.facts), 'issuesHash': digest(project.import_issues),
        'coverageHash': digest(project.import_coverage)}


def capture_finalization(operation, project, now, *, id_factory=identity):
    from .project_repository import RepositoryFailure
    current = authorization(operation)
    if any(task.state not in {'accepted', 'empty', 'source_fallback'} for task in operation.tasks):
        raise RepositoryFailure('JOB_SCOPE_INVALID')
    if any(attempt.cleanup.state != 'verified' for attempt in operation.attempts):
        raise RepositoryFailure('CLEANUP_FAILED')
    values = finalization_hashes(operation, project)
    if operation.finalization is not None:
        previous = operation.finalization
        if previous.candidate_hash != digest(values) or previous.authorization_id != current.id:
            raise RepositoryFailure('DEPENDENCY_CHANGED')
        return previous.model_copy(deep=True)
    if project.template_package.package_hash != operation.capture.package_hash:
        raise RepositoryFailure('DEPENDENCY_CHANGED')
    return FinalizationCandidate(id=id_factory('finalization'), authorizationId=current.id, **values,
        candidateHash=digest(values), startedAt=now, expiresAt=expiry(now, operation.capture.policy.finalization_seconds))
