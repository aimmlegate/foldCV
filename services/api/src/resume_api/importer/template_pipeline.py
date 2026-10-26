"""One proposal-only coordinator for direct and queued template processing."""

import asyncio
from dataclasses import dataclass, replace
import json
import threading
import time

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_import import (CleanupOutcome, ImportIssue, ObservedUsage, ReferenceTable,
    ReviewInputRecord, TaskResultRecord)
from packages.resume_core.models.template_workspace import WorkspaceV7, validated_with_history
from packages.resume_core.models.template_authority import DeletedTemplateCleanupV1, TemplateFinalizationBinding
from packages.resume_core.template_admission import admit_proposal, task_facts_digest
from packages.resume_core.template_builtin_admission import current_handles
from packages.resume_core.template_effective import effective_cells
from packages.resume_core.template_capture import item_identities, prepare_builtin_identities
from packages.resume_core.template_finalization import capture_finalization
from packages.resume_core.template_identity import (capture_span, empty_value, evidence_options, line_spans,
    offered_evidence, source_slice)
from packages.resume_core.template_import import (CleanupProof, ProcessingDeadline, TemplateImportFailure, admit_operation, attempt_in,
    authorization, cancel_operation, capture_task_input, checked, digest, dispatch_attempt, identity, observe_time,
    record_return, reconcile_cleanup, recover_operation, reserve_attempt, resume_operation, spent_calls, start_operation,
    task_in)
from packages.resume_core.template_proposals import parse_proposal, transport_refusal
from packages.resume_core.template_review import decide_review, make_review_input, record_review, repair_wins, shown_values
from packages.resume_core.template_prompt import model_prompt
from packages.resume_core.templates.operations import operation_value
from packages.resume_core.templates.replies import BOOKKEEPING_KEYS, proposal_protocol, proposal_schema, review_schema, PROPOSAL_PROTOCOL

from ..providers.content import (ContentFailure, ContentInput, ContentTransportReturn, GenerationPolicy,
    MAX_GENERATION_SECONDS, outcome_state)
from ..providers.dynamic_result import dynamic_result
from .template_persistence import PersistenceWindow, TemplatePersistence
from .template_checkpoints import TemplateCheckpoints


# No later call of the import can succeed after these, so the import stops instead of saving empty blocks (D104).
ACCOUNT_STOP = frozenset({'QUOTA_EXHAUSTED', 'AUTH_REQUIRED', 'AUTH_MODE_MISMATCH', 'MODEL_DENIED'})


class AccountStop(TemplateImportFailure):
    pass


def stops_import(operation, attempt):
    # An unavailable fallback model fails only its own repair (E07); the import model being refused stops everything.
    return attempt.error_code in ACCOUNT_STOP and (attempt.error_code != 'MODEL_DENIED'
        or attempt.model.model == operation.capture.primary.model)


def account_stop(operation):
    """The account-wide failure that stopped this import, or None."""
    return next((attempt.error_code for attempt in operation.attempts if stops_import(operation, attempt)), None)


@dataclass(frozen=True)
class DerivedTask:
    value: object
    source_spans: tuple
    item_handles: tuple
    issues: tuple = ()


def reference_table(captured, cells, relations):
    """Request-local references for captured items, effective cells and existing relations (H, E and R refs)."""
    items = [{'ref': 'H' + str(index), 'itemHandle': value.item_handle, 'semanticType': value.semantic_type,
        'key': getattr(value, 'key', None)} for index, value in enumerate(captured, 1)]
    records = {value.record_id: item['ref'] for value, item in zip(captured, items, strict=True)}
    return ReferenceTable.model_validate({'items': items,
        'cells': [{'ref': 'E' + str(index), 'cellId': value['id'], 'fieldKey': value['fieldKey'], 'text': value['rawInput']}
            for index, value in enumerate(cells, 1)],
        'relations': [{'ref': 'R' + str(index), 'relationId': value.id, 'kind': value.kind,
            'subject': records.get(value.subject_id, value.subject_id), 'target': records.get(value.target_id, value.target_id)}
            for index, value in enumerate(relations, 1)]})


def owner(workspace):
    return workspace.project or workspace.pre_draft


def reply_refs(raw):
    """Evidence refs a refused reply named, read without trusting the rest of it."""
    try:
        payload = json.loads(raw)['payload']
    except (ValueError, TypeError, KeyError, RecursionError):
        return []
    refs = []
    for key in ('fields', 'relations'):
        entries = payload.get(key) if isinstance(payload, dict) else None
        for entry in entries if isinstance(entries, list) else []:
            evidence = entry.get('evidence') if isinstance(entry, dict) else None
            refs += [ref for ref in evidence if isinstance(ref, str)] if isinstance(evidence, list) else []
    return refs


def reply_feedback(task_id, errors):
    """The repair note for a refused reply: the first refusal, which names paths and rules but no reply values."""
    return {'ruleId': 'reply-format', 'targetId': 'scope-' + task_id, 'reason': (errors[0] if errors else 'invalid reply')[:300]}


# Normal calls take 3-35 s and the CLI streams nothing before the reply, so a stalled call (LIVE-04: 180 s) is
# only seen at its limit; a first call that runs out gets one retry with the full provider limit.
CALL_SECONDS, RETRY_SECONDS = 90, MAX_GENERATION_SECONDS


# The editor shows these notices in Russian; a reviewer's own reason (asked for in Russian since review protocol 3)
# follows the category sentence.
# I4: a repair that still states values no source line states keeps the block; the removed values are named once.
UNBOUND_MESSAGE = 'Убраны данные, которые источник не подтверждает: {values}. Остальное в блоке принято.'


def unbound_issues(id_factory, task_id, proposal, fingerprint):
    if not proposal.dropped_values:
        return []
    values = '; '.join('«' + value.text.strip()[:120] + '»' for value in proposal.dropped_values)
    return [ImportIssue(id=id_factory('issue'), ruleId=None, taskId=task_id, targetIds=['scope-' + task_id], blockIds=[],
        category='uncertain_interpretation', code='IMPORT_VALUE_UNBOUND', message=UNBOUND_MESSAGE.format(values=values),
        importedFingerprint=fingerprint, reviewInputHash=None, lifecycleId=id_factory('issue-lifecycle'), state='active',
        retiredByAction=None)]


FALLBACK_MESSAGES = {'content_violation': 'проверка нашла ошибку в извлечённых данных.',
    'uncertain_interpretation': 'проверка не подтвердила извлечённые данные.',
    'check_not_completed': 'проверку извлечённых данных не удалось завершить.'}
EMPTY_FALLBACK = 'Блок не заполнен: данные не удалось извлечь и проверить. Исходный текст сохранён в оригинале.'


def fallback_message(result, count=1, shown=True):
    """The notice names what the block shows: source lines, or only the values the review accepted."""
    if result is None:
        return 'Показан исходный текст: ' + FALLBACK_MESSAGES['check_not_completed'] if shown else EMPTY_FALLBACK
    category = FALLBACK_MESSAGES['content_violation' if result.disposition == 'violation' else 'uncertain_interpretation']
    text = 'Показан исходный текст: ' + category if shown else category[0].upper() + category[1:]
    reason = ' '.join(result.reason.split())
    if reason and reason[-1] not in '.!?…':
        reason += '.'
    more = ' Ещё замечаний: ' + str(count - 1) + '.' if count > 1 else ''
    return text + (' ' + reason if reason else '') + more


def failed_targets(receipt):
    return {result.target_id for result in receipt.reply.results if result.disposition != 'satisfied'}


def better_repair(operation, package, first_receipt, receipt, review, proposal):
    """Whether a reviewed repair replaces the admitted reply of its task (see repair_wins)."""
    first = next(value for value in operation.proposals if value.applied_receipt_id == first_receipt.id)
    task = task_in(operation, attempt_in(operation, first.attempt_id).task_id)
    block = next(value for value in package.definition.blocks if value.id == task.block_id)
    rewrite = block.rewrite.fields if operation.capture.allow_text_rewrite else []
    allocations = item_identities(operation)
    # What each review admitted; admitted_cell_ids leaves out cells an earlier admission already holds unchanged.
    first_review = next(value.value for value in operation.review_inputs if value.attempt_id == first_receipt.attempt_id)
    before = shown_values(first, set(decide_review(first_review, first_receipt, first).admitted_cell_ids), allocations, rewrite)
    admitted = decide_review(review, receipt, proposal).admitted_cell_ids
    # The view reads every active record, so items the repair does not send keep their admitted values.
    touched = {field.item_handle for field in proposal.resolved_fields}
    after = [value for value in before if value.item_handle not in touched]
    return repair_wins(before, failed_targets(first_receipt),
        after + shown_values(proposal, set(admitted), allocations, rewrite), failed_targets(receipt))


def previous_reply(proposal, offered, references):
    """The reviewed reply a repair corrects: each value's pointer, item and evidence by the request's references."""
    refs = {digest(option.span): ref for ref, option in (offered or {}).items()}
    items = {item.item_handle: item.ref for item in references.items} if references is not None else {}
    return {'payload': proposal.reply.payload, 'fields': [{'pointer': field.pointer, 'item': items.get(field.item_handle),
        'evidence': [refs[digest(span)] for span in field.evidence if digest(span) in refs]} for field in proposal.resolved_fields]}


def other_blocks(operation, task, package):
    """What the other blocks of this import collect, so coverage review leaves their content to them (D107)."""
    result = []
    for block in package.definition.blocks:
        if block.id == task.block_id:
            continue
        if block.when is not None:
            selected = operation_value([operation], block.when.operation)
            if selected is not None and selected['branch'] != block.when.equals:
                continue
        title = block.view.title
        result.append({'block': block.id, 'title': title.get(package.definition.template.default_locale)
            or next(iter(title.values()), None), 'extract': list(block.extract)})
    return result


def implicit_dependencies(package, operation):
    """A block or operation that selects a fact type waits for the earlier blocks that produce it: its input reads
    their admitted records, as it did when every task ran in declaration order (CT10)."""
    blocks = {block.id: block for block in package.definition.blocks}
    operations = {item.id: item for item in package.definition.operations}
    produced, result = {}, {}
    for task in operation.tasks:
        block = blocks.get(task.block_id)
        selectors = block.selectors if block is not None else operations[task.block_id].inputs if task.block_id in operations else []
        wanted = {ref.id for ref in selectors if ref.kind == 'fact_type'}
        result[task.id] = {producer for kind in wanted for producer in produced.get(kind, [])}
        for binding in (block.bindings if block is not None else []):
            produced.setdefault(binding.semantic_type, []).append(task.id)
    return result


def applied_receipt(operation, task_id):
    """The latest review of the task whose proposal was admitted."""
    task = task_in(operation, task_id)
    applied = {proposal.applied_receipt_id for proposal in operation.proposals if proposal.applied_receipt_id is not None}
    return next((value for value in reversed(operation.receipts) if value.id in task.receipt_ids and value.id in applied), None)


def timeout_feedback(task_id):
    return {'ruleId': 'reply-time', 'targetId': 'scope-' + task_id,
        'reason': 'No reply arrived within the call time limit. Return the whole reply.'}


def repair_feedback(feedback, task_id, errors):
    """Review findings a refused repair was fixing stay; the latest refusal replaces an earlier one."""
    return (*[value for value in feedback if value['ruleId'] != 'reply-format'], reply_feedback(task_id, errors))


def scope_units(offered, sources):
    """A block's whole source scope: the offered units, or the offered spans when it was offered no unit."""
    lengths = {(source.id, source.revision, unit.id, unit.revision): len(unit.text) for source in sources for unit in source.units}
    units = [option.span for option in offered.values() if option.span.start == 0 and option.span.end == lengths[(
        option.span.source_id, option.span.source_revision, option.span.unit_id, option.span.unit_revision)]]
    return units or [option.span for option in offered.values()]


def cited_spans(operation, task_id, offered):
    """The source lines the task's latest citing reply selected; a failed block shows only these (R05)."""
    for proposal in reversed(operation.proposals):
        if attempt_in(operation, proposal.attempt_id).task_id != task_id:
            continue
        if proposal.reply is not None:
            spans = [span for field in proposal.resolved_fields for span in field.evidence]
            spans += [span for relation in proposal.reply.relations for span in relation.evidence]
        else:
            spans = [offered[ref].span for ref in reply_refs(proposal.raw_return) if ref in offered]
        if spans:
            return list({digest(span): span for span in spans}.values())
    return []


def gated_branch(operation, task, data):
    """The selected branch when a block's declared condition does not hold; None when the block runs."""
    block = next((value for value in data.template_package.definition.blocks if value.id == task.block_id), None)
    if block is None or block.when is None:
        return None
    selected = operation_value([operation], block.when.operation)
    if selected is None:
        raise ValueError('conditional block runs before its condition')
    return None if selected['branch'] == block.when.equals else selected['branch']


def operation_in(workspace, identifier):
    value = next((value for value in owner(workspace).template_operations if value.id == identifier), None)
    if value is None:
        raise TemplateImportFailure('IMPORT_OPERATION_UNKNOWN')
    return value


class TemplatePipeline(TemplateCheckpoints):
    def __init__(self, publisher, transport, *, originals, authority, assemble, derive, artifacts=None, images=None,
                 wall, elapsed=time.monotonic, id_factory=identity):
        super().__init__(publisher, originals=originals, artifacts=artifacts, images=images, wall=wall, id_factory=id_factory)
        self.transport, self.authority, self.assemble, self.derive = transport, authority, assemble, derive
        self.elapsed = elapsed
        self.persistence = TemplatePersistence(publisher, wall=wall, elapsed=elapsed)
        self.locks, self.cancels = {}, {}
        publisher.template_authority = self.finalization_authority

    def finalization_authority(self, binding, before, _after):
        operation = operation_in(before, binding.operation_id)
        try:
            self.authority(operation, before)
            self.facts_current(operation, owner(before).facts)
        except TemplateImportFailure:
            raise BackgroundFailure('DEPENDENCY_CHANGED') from None

    def cleanup_deleted(self, project, identifier=None):
        jobs = self.publisher.jobs
        with jobs.guard(project, deleted=True) as directory:
            state = jobs._read(project, directory)
            latest = {value.operation_id: value for value in state.template_authorizations}
            if identifier is not None and identifier not in latest:
                raise TemplateImportFailure('IMPORT_AUTHORITY_REVOKED')
            for operation_id, authority in latest.items():
                if identifier is not None and operation_id != identifier:
                    continue
                if authority.deleted_cleanup is not None and authority.deleted_cleanup.complete:
                    continue
                operation, revision = self.publisher.canonical._read_template_cleanup_unlocked(project, operation_id,
                    with_revision=True)
                # Attempts of the running step may be saved only in the sidecar (S7e).
                operation, _facts = self.sidecar.overlay(project, revision, operation)
                owners = {attempt.id: attempt.owner for attempt in operation.attempts}
                retained = authority.deleted_cleanup
                if retained is not None:
                    if retained.capture_hash != digest(operation.capture) or retained.owners != owners:
                        raise TemplateImportFailure('IMPORT_CLEANUP_PROOF_CONFLICT')
                    for record in retained.records:
                        operation = reconcile_cleanup(operation, CleanupProof(record.attempt_id, record.owner_hash,
                            record.evidence_hash, record.witness, record.never_dispatched), record.verified_at)
                def persist():
                    authority.deleted_cleanup = DeletedTemplateCleanupV1(captureHash=digest(operation.capture),
                        owners=owners, records=operation.cleanup_records)
                    authority.state = 'cancelled'
                    jobs._write(directory, state, jobs._all())
                persist()
                for attempt in operation.attempts:
                    if attempt.cleanup.state != 'verified':
                        proof = self.transport.reconcile(attempt)
                        if proof is None:
                            return False
                        operation = reconcile_cleanup(operation, proof, self.wall())
                        persist()
            return True

    def update(self, project, identifier, transition):
        def apply(workspace):
            prior = operation_in(workspace, identifier)
            updated = transition(prior, owner(workspace), workspace)
            owner(workspace).template_operations[owner(workspace).template_operations.index(prior)] = checked(updated)
            return workspace
        return self.checkpoint(project, apply)

    def guard(self, project, operation):
        authorization(operation)
        workspace = self.read(project)
        self.authority(operation, workspace)
        if (owner(workspace).template_package.package_hash != operation.capture.package_hash
                or {source.id: source.byte_sha256 for source in owner(workspace).sources} != operation.capture.source_hashes):
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
        # The facts and the admissions that explain them come from one read: a parallel block may admit between an
        # earlier read of the operation and this one (CT10).
        current = next((value for value in owner(workspace).template_operations if value.id == operation.id), operation)
        self.facts_current(current, owner(workspace).facts)
        with self.publisher.jobs.guard(project) as directory:
            state = self.publisher.jobs._read(project, directory)
            self.publisher._writable(state)
            current = [value for value in state.template_authorizations if value.operation_id == operation.id]
            account = self.publisher.jobs._read_dispatch(self.publisher.jobs.background / 'dispatch.json').account_generation
            if (not current or current[-1].authorization_id != authorization(operation).id or current[-1].state != 'active'
                    or current[-1].account_generation != account):
                raise TemplateImportFailure('IMPORT_AUTHORITY_REVOKED')

    def facts_current(self, operation, facts):
        expected, relations = dict(operation.capture.fact_revisions), dict(operation.captured_relation_revisions)
        for proposal in operation.proposals:
            if proposal.applied_receipt_id is not None:
                expected.update(proposal.admitted_record_revisions)
                relations.update(proposal.admitted_relation_revisions)
        actual = {record.id: record.revision for record in [*facts.records, *facts.extensions]}
        active = {record.id for record in [*facts.records, *facts.extensions] if getattr(record, 'active', True)}
        if (any(actual.get(key) != revision for key, revision in expected.items()) or active - expected.keys()
                or relations != {relation.id: relation.revision for relation in facts.relations}):
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE')

    async def start(self, project, command):
        def capture(workspace):
            data = owner(workspace)
            if not any(value.client_request_id == command.client_request_id for value in data.template_operations):
                try:
                    data.facts = prepare_builtin_identities(data.facts, data.template_package, data.template_operations,
                        id_factory=self.id_factory)
                except ValueError:
                    raise TemplateImportFailure('IMPORT_IDENTITY_PREPARATION_REQUIRED') from None
            operation, created = start_operation(project, command, data.template_package, data.sources, data.facts,
                data.template_operations, self.wall(), id_factory=self.id_factory)
            self.authority(operation, workspace)
            if created:
                if workspace.project is not None:
                    raise TemplateImportFailure('IMPORT_PROJECT_ALREADY_AUTHORED')
                data.template_operations.append(operation)
            return workspace
        workspace = await asyncio.to_thread(self.checkpoint, project, capture)
        operation = next(value for value in owner(workspace).template_operations if value.client_request_id == command.client_request_id)
        return operation

    async def recover(self, project, identifier):
        await self.persistence.reconcile(project)
        current = self.read(project)
        retained = operation_in(current, identifier)
        if current.project is not None and retained.finalization is not None:
            return await self.finalize(project, identifier)
        def recover(operation, _data, _workspace):
            result = recover_operation(operation)
            for attempt in result.attempts:
                if attempt.state == 'outcome_unknown' or attempt.cleanup.state != 'verified':
                    proof = self.transport.reconcile(attempt)
                    if proof is not None:
                        result = reconcile_cleanup(result, proof, self.wall())
            return result
        workspace = await asyncio.to_thread(self.update, project, identifier, recover)
        return operation_in(workspace, identifier)

    async def cancel(self, project, identifier):
        won = await asyncio.to_thread(self.publisher.cancel_template, project, identifier)
        if not won:
            return False
        self.cancels.setdefault((project, identifier), threading.Event()).set()
        await asyncio.to_thread(self.update, project, identifier, lambda operation, _data, _workspace: cancel_operation(operation))
        return True

    async def run(self, project, command, *, admitted, finalize=True, cancel_event=None):
        if command.protocol != 'template_import_v1':
            raise TemplateImportFailure('IMPORT_PROTOCOL_MISMATCH')
        async with self.locks.setdefault(project, asyncio.Lock()):
            if command.kind == 'start_new_import':
                operation = await self.start(project, command)
                if operation.finalization is not None and self.read(project).project is not None:
                    return await self.recover(project, operation.id)
                if operation.attempts or operation.state in {'published', 'cancelled', 'failed', 'fenced'}:
                    return operation
            else:
                operation = await self.recover(project, command.operation_id)
                if operation.state == 'published' or operation.publication.state == 'saved':
                    return operation
                workspace = await asyncio.to_thread(self.update, project, operation.id,
                    lambda value, _data, workspace: self.resume(value, command, workspace))
                operation = operation_in(workspace, operation.id)
            cancel = self.cancels[(project, operation.id)] = cancel_event if cancel_event is not None else threading.Event()
            await asyncio.to_thread(self.publisher.authorize_template, project, operation)
            self.guard(project, operation)
            await admitted()
            workspace = await asyncio.to_thread(self.update, project, operation.id,
                lambda value, _data, _workspace: admit_operation(value, self.wall()))
            operation = operation_in(workspace, operation.id)
            deadline = ProcessingDeadline.capture(operation, self.wall(), self.elapsed())
            await self.run_tasks(project, operation, deadline, cancel,
                implicit=implicit_dependencies(owner(workspace).template_package, operation))
            workspace = self.read(project)
            operation = operation_in(workspace, operation.id)
            if cancel.is_set() or operation.state in {'cancelled', 'fenced'}:
                return operation
            return await self.finalize(project, operation.id) if finalize else operation

    async def run_tasks(self, project, operation, deadline, cancel, *, implicit=None):
        """Tasks start in declaration order once the tasks they depend on ended; up to the captured concurrency run
        at once (CT10). Concurrency 1 is the sequential loop. After a failure or a cancel nothing new starts, the
        running tasks end, and the first failure is raised."""
        order = [task.id for task in operation.tasks]
        width = operation.capture.policy.concurrency
        if width == 1:
            for identifier in order:
                if cancel.is_set():
                    break
                await self.execute_task(project, operation.id, identifier, deadline, cancel)
            return
        waits = {task.id: (set(task.dependencies) | (implicit or {}).get(task.id, set())) & set(order) for task in operation.tasks}
        pending, running, ended, failure = list(order), {}, set(), None
        try:
            while pending or running:
                if failure is None and not cancel.is_set():
                    ready = [value for value in pending if waits[value] <= ended]
                    if not ready and not running and pending:
                        # A dependency no task here can end (a cycle) runs in declaration order, as sequentially.
                        ready = pending[:1]
                    for identifier in ready[:width - len(running)]:
                        pending.remove(identifier)
                        running[asyncio.ensure_future(self.execute_task(project, operation.id, identifier, deadline, cancel))] = identifier
                if not running:
                    break
                finished, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for future in finished:
                    ended.add(running.pop(future))
                    if failure is None and not future.cancelled() and future.exception() is not None:
                        failure = future.exception()
        except BaseException:
            for future in running:
                future.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            raise
        if failure is not None:
            raise failure

    def resume(self, operation, command, workspace):
        self.authority(operation, workspace)
        return resume_operation(operation, command, self.wall())

    def task_input(self, operation, task, data):
        declaration = next(value for value in [*data.template_package.definition.operations, *data.template_package.definition.blocks]
            if value.id == task.block_id)
        selectors = declaration.inputs if hasattr(declaration, 'inputs') else declaration.selectors
        types = {value.id for value in selectors if value.kind == 'fact_type'}
        dependencies = [result for result in operation.task_results if result.task_id in task.dependencies]
        handles = {handle for value in dependencies for handle in value.item_handles}
        handles.update(record.item_handle for record in data.facts.extensions if record.active and record.semantic_type in types)
        records = [record for record in data.facts.extensions if record.active and record.item_handle in handles]
        builtin_records = {record.id: record for record in data.facts.records}
        handles.update(allocation.item_handle for allocation in item_identities(operation)
            if allocation.record_id in builtin_records and allocation.semantic_type in types)
        builtins = [(allocation, builtin_records[allocation.record_id]) for allocation in item_identities(operation)
            if allocation.record_id in builtin_records and allocation.item_handle in handles]
        selected = {record.id for record in records} | {record.id for _allocation, record in builtins}
        cells = effective_cells(data.facts, data.template_operations, selected)
        builtin_cells = {identifier: [cell for cell in cells if cell.id in {
            value.cell_id for value in allocation.canonical_fields.values()}]
            for allocation, record in builtins for identifier in [record.id]}
        source_requested = any(value.kind == 'source' for value in selectors)
        # Whole units, and each line of a multi-line unit, so a reply can cite one claim without its neighbours.
        spans = [span for source in data.sources for unit in source.units
            for span in [capture_span(source, unit), *line_spans(source, unit)]] if source_requested else []
        spans += [span for cell in cells for span in cell.evidence]
        spans += [span for result in dependencies for span in result.source_spans]
        spans = list({digest(span): span for span in spans}.values())
        value = {'protocol': 'template_import_v1', 'tools': [], 'replyProtocol': PROPOSAL_PROTOCOL,
            'packageHash': data.template_package.package_hash,
            'allowTextRewrite': operation.capture.allow_text_rewrite,
            'formattingAsOf': operation.capture.formatting_as_of.model_dump(mode='json', by_alias=True),
            'modelInstructions': data.template_package.definition.model.model_dump(mode='json', by_alias=True),
            'declaration': declaration.model_dump(mode='json', by_alias=True),
            'evidence': [option.model_dump(mode='json', by_alias=True) for option in evidence_options(spans, data.sources)],
            'effectiveCells': [cell.model_dump(mode='json', by_alias=True) for cell in cells],
            'manualScopes': [scope.model_dump(mode='json', by_alias=True) for scope in data.facts.manual_scopes
                if scope.id in {cell.manual_scope_id for cell in cells}],
            'effectiveRecords': [{**record.model_dump(mode='json', by_alias=True, exclude={'observation_ids'}),
                'cells': [cell.model_dump(mode='json', by_alias=True) for cell in record.cells
                    if cell.state in {'admitted', 'human_raw', 'pending_manual'}]} for record in records] + [
                {'id': record.id, 'itemHandle': allocation.item_handle, 'semanticType': allocation.semantic_type,
                    'revision': record.revision, 'builtinKind': record.kind,
                    'cells': [cell.model_dump(mode='json', by_alias=True) for cell in builtin_cells[record.id]]}
                for allocation, record in builtins],
            'relations': [relation.model_dump(mode='json', by_alias=True) for relation in data.facts.relations if relation.active
                and relation.subject_id in selected],
            'dependencies': [result.model_dump(mode='json', by_alias=True) for result in dependencies],
            'allowedHandles': sorted(handles)}
        return value, sorted(handles)

    async def execute_task(self, project, operation_id, task_id, deadline, cancel):
        workspace = self.read(project)
        operation, data = operation_in(workspace, operation_id), owner(workspace)
        task = task_in(operation, task_id)
        if any(result.task_id == task_id for result in operation.task_results):
            return
        branch = gated_branch(operation, task, data)
        if branch is not None:
            # A block for another declared branch ends empty without a model call.
            await self.finish_task(project, operation_id, task_id, {'branch': branch}, [], [], 'empty', [])
            return
        if task.state == 'pending' and not any(value.task_id == task_id for value in operation.task_inputs):
            value, handles = self.task_input(operation, task, data)
            workspace = await asyncio.to_thread(self.update_operation, project, operation_id,
                lambda value_op, _data, _workspace: capture_task_input(value_op, task_id, value, handles, self.wall(), id_factory=self.id_factory),
                copy_on_write=True)
            operation = operation_in(workspace, operation_id)
        if task.kind in {'derive', 'source_copy'}:
            derived = self.derive(operation, task_in(operation, task_id), owner(workspace))
            stored = next(value for value in operation.task_inputs if value.task_id == task_id)
            issues = [ImportIssue(id=self.id_factory('issue'), ruleId=None, taskId=task_id,
                targetIds=list(issue.target_ids) or ['scope-' + task_id], blockIds=[], category='uncertain_interpretation',
                code=issue.code, message=issue.message, importedFingerprint=digest(stored.value), reviewInputHash=None,
                lifecycleId=self.id_factory('issue-lifecycle'), state='active', retiredByAction=None)
                for issue in derived.issues]
            await self.finish_task(project, operation_id, task_id, derived.value, derived.source_spans,
                derived.item_handles, 'empty' if empty_value(derived.value) else 'derived', issues)
            return
        feedback, unresolved, previous = (), [], None
        for slot in ['initial', 'primary_repair', 'fallback_repair']:
            workspace = self.read(project)
            operation, data = operation_in(workspace, operation_id), owner(workspace)
            existing = next((attempt for attempt in operation.attempts if attempt.task_id == task_id
                and attempt.slot == slot and attempt.state != 'released'), None)
            if slot != 'initial' and not feedback:
                break
            if slot == 'fallback_repair' and operation.capture.fallback is None:
                break
            if existing is not None and existing.state == 'outcome_unknown':
                break
            # A repair counts only after its own review, so it starts only when both calls fit the cap.
            if existing is None and slot != 'initial' and operation.capture.policy.call_cap - spent_calls(operation) < 2:
                unresolved.append('IMPORT_CALL_CAP')
                break
            if existing is None:
                stored = next(value for value in operation.task_inputs if value.task_id == task_id)
                allowed = set(task_in(operation, task_id).allowed_handles)
                known_relations = {value.id: value for value in data.facts.relations}
                for retained in operation.proposals:
                    if attempt_in(operation, retained.attempt_id).task_id == task_id:
                        known_relations.update({value.id: value for value in retained.resolved_relations})
                captured = [allocation for allocation in item_identities(operation) if allocation.item_handle in allowed]
                relations = [value for value in known_relations.values()
                    if value.subject_id in {allocation.record_id for allocation in captured}]
                offered = offered_evidence(stored.value)
                request = {**stored.value, 'slot': slot, 'feedback': list(feedback),
                    'capturedHandles': [allocation.model_dump(mode='json', by_alias=True) for allocation in captured],
                    'capturedRelations': [value.model_dump(mode='json', by_alias=True) for value in relations]}
                references = None
                if offered is not None:
                    references = reference_table(captured, stored.value.get('effectiveCells', []), relations)
                    request['references'] = references.model_dump(mode='json', by_alias=True)
                    request['replyProtocol'] = proposal_protocol(references)
                if previous is not None:
                    # D107: a repair that saw only the findings wrote the block anew and lost admitted values.
                    request['previousReply'] = previous_reply(previous, offered, references)
                retry = any(value['ruleId'] == 'reply-time' for value in feedback)
                try:
                    attempt_id = await self.call(project, operation_id, task_id, slot, request,
                        proposal_schema(next(value.full_schema for value in data.template_package.blocks
                            if value.id == task.block_id), None if offered is None else list(offered), references), deadline, cancel,
                        seconds=RETRY_SECONDS if retry else CALL_SECONDS)
                except AccountStop:
                    raise
                except TemplateImportFailure as error:
                    unresolved.append(error.code)
                    break
            else:
                attempt_id = existing.id
            workspace = self.read(project)
            operation, data = operation_in(workspace, operation_id), owner(workspace)
            attempt = attempt_in(operation, attempt_id)
            if attempt.cleanup.state != 'verified' or operation.state == 'cancelled':
                return
            self.guard(project, operation)
            if attempt.outcome != 'completed' and attempt.proposal_record_id is None:
                unresolved.append(attempt.error_code or attempt.outcome or 'IMPORT_RETURN_UNKNOWN')
                refusal = transport_refusal(attempt, data.template_package, task.block_id) if (slot != 'fallback_repair'
                    and attempt.outcome == 'invalid_payload') else None
                if refusal is not None:
                    # A reply the transport refused by schema is repaired like a refused proposal.
                    feedback = repair_feedback(feedback, task_id, [refusal])
                    continue
                if slot == 'initial' and attempt.error_code == 'DEADLINE_EXCEEDED':
                    feedback = (timeout_feedback(task_id),)
                    continue
                if slot == 'primary_repair' and feedback:
                    continue
                break
            def parse(value, current, _workspace):
                from packages.resume_core.models.template_facts import Relation
                captured = [Relation.model_validate(relation) for relation in attempt_in(value, attempt_id).request_value.get('capturedRelations', [])]
                self.facts_current(value, current.facts)
                updated, facts, _proposal = parse_proposal(value, attempt_id, current.template_package,
                    current.sources, current.facts, captured_relations=captured, id_factory=self.id_factory)
                current.facts = facts
                return updated
            workspace = await asyncio.to_thread(self.update_operation, project, operation_id, parse, copy_on_write=True)
            operation, data = operation_in(workspace, operation_id), owner(workspace)
            proposal = next(value for value in operation.proposals if value.attempt_id == attempt_id)
            if proposal.state == 'invalid':
                unresolved.extend(proposal.errors)
                if slot != 'fallback_repair':
                    # The next repair names this refusal; it still needs room for itself and its review.
                    feedback = repair_feedback(feedback, task_id, proposal.errors)
                    continue
                break
            policy = attempt.model
            # Identical replies of different blocks share a proposal hash; only this task's own review input is reusable.
            prior_review = next((value.value for value in operation.review_inputs
                if value.value.proposal_hash == proposal.proposal_hash and value.value.policy == policy
                and attempt_in(operation, value.attempt_id).task_id == task_id), None)
            # The review offers its own evidence table under the same references, so the task input omits its copy.
            task_input = next(value.value for value in operation.task_inputs if value.task_id == task_id)
            review = prior_review or make_review_input(operation, proposal, data.template_package, data.sources, policy,
                # Only the cells the proposal reads: the reviewer sees no others and wording restores from these
                # (LIVE-08: every effective cell was 250 KB of each 320 KB review input).
                effective_cells=[cell for cell in effective_cells(data.facts, data.template_operations)
                    if cell.id in {identifier for field in proposal.resolved_fields for identifier in field.effective_cell_ids}],
                semantic_context={'taskInput': {key: value for key, value in task_input.items() if key != 'evidence'},
                    'taskFactsHash': task_facts_digest(operation, task_id, data.facts),
                    'otherBlocks': other_blocks(operation, task, data.template_package)})
            review_attempt = next((value for value in operation.attempts if value.task_id == task_id
                and value.slot in {'review', 'replacement_review'} and value.input_hash == digest(review)), None)
            try:
                if review_attempt is None:
                    review_id = await self.call(project, operation_id, task_id,
                        'review' if slot == 'initial' else 'replacement_review', review.model_dump(mode='json', by_alias=True),
                        review_schema(review), deadline, cancel, review=review)
                else:
                    review_id = review_attempt.id
                self.guard(project, operation_in(self.read(project), operation_id))
                kept_first = [False]
                def accept(value, current, _workspace):
                    self.facts_current(value, current.facts)
                    updated, receipt = record_review(value, review_id, current.sources, self.wall(), id_factory=self.id_factory)
                    admitted = applied_receipt(updated, task_id)
                    kept_first[:] = [admitted is not None and admitted.id != receipt.id and not better_repair(updated,
                        current.template_package, admitted, receipt, review, proposal)]
                    if kept_first[0]:
                        return updated
                    updated, facts = admit_proposal(updated, proposal.id, receipt.id, current.template_package, current.sources,
                        current.facts, expected_revisions={handle: record.revision
                            for handle, record in current_handles(updated, current.facts).items()},
                        expected_relation_revisions={relation.id: relation.revision for relation in current.facts.relations})
                    current.facts = facts
                    return updated
                workspace = await asyncio.to_thread(self.update_operation, project, operation_id, accept, copy_on_write=True)
                operation = operation_in(workspace, operation_id)
                receipt = next(value for value in operation.receipts if value.attempt_id == review_id)
                decision = decide_review(review, receipt, proposal)
            except AccountStop:
                raise
            except (TemplateImportFailure, ValueError) as error:
                unresolved.append(getattr(error, 'code', 'IMPORT_REVIEW_INVALID'))
                break
            feedback, previous = decision.feedback, proposal
            # A clean repair that was not better leaves the first reply and its findings in place.
            if not decision.unresolved_target_ids and not kept_first[0]:
                await self.finish_admitted(project, operation_id, task_id, proposal)
                return
            unresolved = list(decision.unresolved_target_ids)
        await self.fallback(project, operation_id, task_id, unresolved)

    async def finish_admitted(self, project, operation_id, task_id, proposal):
        workspace = self.read(project)
        operation, effective = operation_in(workspace, operation_id), owner(workspace).facts
        active_handles = {record.item_handle for record in effective.extensions if record.active}
        active_handles.update(allocation.item_handle for allocation in item_identities(operation)
            if allocation.record_id in {record.id for record in effective.records})
        handles = [handle for handle in [*[field.item_handle for field in proposal.resolved_fields],
            *[parent for link in proposal.lineage for parent in link.parents]] if handle in active_handles]
        fingerprint = digest(next(value for value in operation.task_inputs if value.task_id == task_id).value)
        await self.finish_task(project, operation_id, task_id, None, (), handles,
            'empty' if empty_value(proposal.reply.payload) else 'admitted', unbound_issues(self.id_factory, task_id, proposal, fingerprint))

    async def call(self, project, operation_id, task_id, slot, value, schema, deadline, cancel, *, review=None,
            seconds=CALL_SECONDS):
        workspace = self.read(project)
        operation = operation_in(workspace, operation_id)
        self.guard(project, operation)
        remaining = deadline.remaining(operation, self.wall(), self.elapsed())
        policy = review.policy if review is not None else operation.capture.fallback if slot == 'fallback_repair' else operation.capture.primary
        if review is None:
            block = next(value for value in owner(workspace).template_package.definition.blocks if value.id == task_in(operation, task_id).block_id)
            if block.effort and block.effort != policy.effort:
                # The block declares its own extraction effort (D101 probe H: the projects block is complete at high
                # where medium stopped after one to five jobs); the attempt records the policy actually used.
                policy = policy.model_copy(update={'effort': block.effort})
        launch_owner = self.transport.reserve_owner(operation, task_in(operation, task_id), policy)
        reserved = []
        def reserve(result, _data, _workspace):
            # The time observation shares this write: reserve_attempt observes the clock; a passed deadline is still
            # persisted, without a reservation.
            if remaining <= 0:
                observed = observe_time(result, self.wall(), elapsed_remaining=remaining)
                if observed.inference_closed:
                    return observed
            # A review's request is its review input record; storing it twice doubled the operation (LIVE-06: 5.3 MB).
            result, identifier = reserve_attempt(result, task_id, slot, digest(value), policy, launch_owner, self.wall(),
                request_value=None if review is not None else value, id_factory=self.id_factory)
            if review is not None:
                record = ReviewInputRecord(id=self.id_factory('review-input'), attemptId=identifier, inputHash=digest(review), value=review)
                result.review_inputs.append(record)
                attempt_in(result, identifier).review_input_record_id = record.id
            reserved.append(identifier)
            return result
        await asyncio.to_thread(self.update_operation, project, operation_id, reserve, copy_on_write=True)
        if not reserved:
            raise TemplateImportFailure('IMPORT_PROCESSING_EXHAUSTED')
        attempt_id = reserved[0]
        self.guard(project, operation_in(self.read(project), operation_id))
        def dispatch(result, _data, _workspace):
            now = self.wall()
            remaining = deadline.remaining(result, now, self.elapsed())
            result = observe_time(result, now, elapsed_remaining=remaining)
            if remaining <= 0:
                return self.reconcile_unlaunched(result, attempt_id, now)
            return dispatch_attempt(result, attempt_id, now)
        dispatched = await asyncio.to_thread(self.update_operation, project, operation_id, dispatch, copy_on_write=True)
        if attempt_in(operation_in(dispatched, operation_id), attempt_id).state != 'dispatch_started':
            return attempt_id
        def returned(frame):
            def retain(result, _data, _workspace):
                attempt = attempt_in(result, attempt_id)
                proof = self.transport.prove_return(attempt, frame)
                cleanup = CleanupOutcome(state='verified' if proof is not None else 'unknown',
                    evidenceHash=proof.evidence_hash if proof else None, witness=proof.witness if proof else None)
                observed = self.wall()
                remaining = deadline.remaining(result, observed, self.elapsed())
                result = observe_time(result, observed, elapsed_remaining=remaining)
                late = remaining <= 0 and frame.outcome == 'completed'
                result = record_return(result, attempt_id, frame.raw_return, 'timed_out' if late else frame.outcome,
                    ObservedUsage(inputTokens=frame.usage.input_tokens, cachedInputTokens=frame.usage.cached_input_tokens,
                        outputTokens=frame.usage.output_tokens, complete=frame.usage.complete), cleanup,
                    error_code=frame.original_code or ('IMPORT_PROCESSING_EXHAUSTED' if late else None), returned_at=observed)
                return reconcile_cleanup(result, proof, self.wall()) if proof is not None else result
            self.update_operation(project, operation_id, retain, copy_on_write=True)
        request = ContentInput(model_prompt(value), dynamic_result(schema, BOOKKEEPING_KEYS),
            GenerationPolicy(policy.model, timeout_seconds=min(seconds, max(0.001, remaining)), allow_repair=False,
                reasoning_effort=policy.effort), on_return=returned, request_value=value)
        def launch():
            current = operation_in(self.read(project), operation_id)
            self.guard(project, current)
            remaining = deadline.remaining(current, self.wall(), self.elapsed())
            if remaining <= 0:
                self.update_operation(project, operation_id, lambda result, _data, _workspace: self.reconcile_unlaunched(
                    observe_time(result, self.wall(), elapsed_remaining=0), attempt_id, self.wall()))
                return None
            bounded = replace(request, policy=replace(request.policy, timeout_seconds=min(seconds, remaining)))
            return self.transport.generate(bounded, cancel)
        try:
            response = await asyncio.to_thread(launch)
        except ContentFailure as error:
            operation = operation_in(self.read(project), operation_id)
            attempt = attempt_in(operation, attempt_id)
            if attempt.state == 'dispatch_started':
                returned(ContentTransportReturn(error.raw_return, outcome_state(error.code), error.code,
                    error.logical_attempts, error.usage, error.cleanup_verified, error.dispatch_witness, policy.effort))
            else:
                await asyncio.to_thread(self.update_operation, project, operation_id, lambda result, _data, _workspace:
                    record_return(result, attempt_id, error.raw_return,
                        attempt.outcome if attempt.outcome == 'timed_out' else outcome_state(error.code), attempt.usage,
                        attempt.cleanup, error_code=attempt.error_code if attempt.outcome == 'timed_out' else error.code))
        else:
            if attempt_in(operation_in(self.read(project), operation_id), attempt_id).state == 'dispatch_started':
                returned(ContentTransportReturn(response.raw_return, 'completed', None, response.logical_attempts,
                    response.usage, response.cleanup_verified, response.dispatch_witness, response.reasoning_effort))
        current = operation_in(self.read(project), operation_id)
        if stops_import(current, attempt_in(current, attempt_id)):
            raise AccountStop(attempt_in(current, attempt_id).error_code)
        return attempt_id

    def reconcile_unlaunched(self, operation, attempt_id, now):
        result = operation.model_copy(deep=True)
        attempt = attempt_in(result, attempt_id)
        attempt.error_code = 'IMPORT_PROCESSING_EXHAUSTED'
        proof = self.transport.reconcile(attempt)
        if proof is not None:
            return reconcile_cleanup(result, proof, now)
        attempt.state = 'outcome_unknown'
        attempt.cleanup = CleanupOutcome(state='unknown', evidenceHash=None, witness=None)
        result.state = 'fenced'
        return result

    async def finish_task(self, project, operation_id, task_id, value, spans, handles, disposition, issues, *, accepted=False):
        def finish(operation, _data, _workspace):
            task = task_in(operation, task_id)
            # A review remark on a block that already has admitted values is not a failed import. The result
            # disposition stays source_fallback so the lines the review named still appear under those values.
            task.state = 'accepted' if accepted else 'source_fallback' if disposition == 'source_fallback' else 'empty' if disposition == 'empty' else 'accepted'
            task.issue_ids = [issue.id for issue in issues]
            operation.issues.extend(issues)
            operation.task_results.append(TaskResultRecord(id=self.id_factory('task-result'), taskId=task_id,
                inputHash=task.input_hash, value=value, sourceSpans=list(spans), itemHandles=list(dict.fromkeys(handles)),
                issueIds=task.issue_ids, disposition=disposition))
            return operation
        await asyncio.to_thread(self.update_operation, project, operation_id, finish)

    async def fallback(self, project, operation_id, task_id, errors):
        current = self.read(project)
        operation = operation_in(current, operation_id)
        if operation.state in {'cancelled', 'fenced'}:
            return
        task = task_in(operation, task_id)
        stored = next(value for value in operation.task_inputs if value.task_id == task_id)
        from packages.resume_core.models.template_facts import SourceSpan
        offered = offered_evidence(stored.value)
        # The findings of the review whose proposal stays admitted: a repair that was not better is not shown.
        receipt = applied_receipt(operation, task_id) or next((value for value in reversed(operation.receipts)
            if value.id in task.receipt_ids), None)
        applied = next((value for value in reversed(operation.proposals) if receipt is not None
            and value.applied_receipt_id == receipt.id), None)
        # Admitted values stay. The remark does not mark the block as a failed import.
        kept = applied is not None and bool(applied.admitted_cell_ids)
        leftover = []
        failures = [result for result in receipt.reply.results if result.disposition != 'satisfied'] if receipt else []
        if kept and failures and len(task.receipt_ids) > 1:
            # D107: after a reviewed repair a coverage finding is not shown: the reviewer names a new partial list
            # each round, and its raw lines split the block. Findings on shown values stay.
            failures = [result for result in failures if not result.target_id.startswith('scope-')]
            if not failures:
                await self.finish_admitted(project, operation_id, task_id, applied)
                return
        sources = owner(current).sources
        if offered is None:
            # A request without references predates cited fallback and keeps its whole captured scope.
            spans, scope = [SourceSpan.model_validate(value) for value in stored.value['sourceSpans']], 'cited'
        elif failures:
            # A review named what fails, so its findings are the smallest reliable scope (R05): a rejected value shows
            # its own evidence, a coverage gap the lines the reviewer cites as missing; accepted values stay. LIVE-08:
            # showing every line the reply cited repeated the accepted values as raw text.
            rejected = {result.target_id for result in failures}
            proposal = next((value for value in reversed(operation.proposals) if value.applied_receipt_id == receipt.id), None)
            allocated = {value.item_handle: value for value in item_identities(operation)}
            affected = [span for field in proposal.resolved_fields
                if allocated[field.item_handle].cell_ids[field.field_key] in rejected for span in field.evidence] if proposal else []
            if proposal is not None:
                from packages.resume_core.template_proposals import relation_evidence
                affected.extend(span for identifier, spans in relation_evidence(operation, proposal).items()
                    if identifier in rejected for span in spans)
            cited = list({digest(span): span for span in affected}.values())
            # Lines the reviewer names as missing show only where no other block shows them (materialize).
            missing = [span for span in {digest(span): span for result in failures if result.target_id.startswith('scope-')
                for span in result.evidence}.values() if digest(span) not in {digest(value) for value in cited}]
            spans, scope, leftover = [*cited, *missing], 'cited', [digest(span) for span in missing]
        else:
            spans = cited_spans(operation, task_id, offered)
            scope = 'cited' if spans else 'uncited'
            if not spans:
                # No reply is not evidence of absence: a block offers its scope and the materializer places only the
                # lines no other block shows. A scope of the whole CV identifies nothing (LIVE-08: an empty open
                # source reply put every unshown line, contacts included, into the sidebar), so it places none.
                units = scope_units(offered, sources)
                whole = {(source.id, unit.id) for source in sources for unit in source.units if unit.text.strip()}
                spans = [] if whole <= {(span.source_id, span.unit_id) for span in units} else units
        # One notice per block (LIVE-07: 79 failing checks of one tools block were 79 notices): its first violation,
        # else its first uncertainty, names the rule and reason; every failing target stays a target.
        first = next((result for result in failures if result.disposition == 'violation'), failures[0] if failures else None)
        if kept and first is None:
            message = 'Проверка не завершилась. Принятые данные в блоке сохранены.'
        else:
            message = fallback_message(first, len(failures), shown=not kept and len(spans) > len(leftover))
        # A rejected cell is absent from the document. The scope target keeps the notice on this block's view.
        targets = list(dict.fromkeys(result.target_id for result in failures)) if failures else ['scope-' + task_id]
        if kept and not any(target.startswith('scope-') for target in targets):
            targets.append('scope-' + task_id)
        issues = [ImportIssue(id=self.id_factory('issue'), ruleId=first.rule_id if first else None, taskId=task_id,
            targetIds=targets,
            blockIds=[], category=('content_violation' if first.disposition == 'violation' else 'uncertain_interpretation')
                if first else 'check_not_completed', code='IMPORT_SOURCE_FALLBACK',
            message=message,
            importedFingerprint=digest(stored.value), reviewInputHash=receipt.review_input_hash if first else None,
            lifecycleId=self.id_factory('issue-lifecycle'), state='active', retiredByAction=None)]
        await self.finish_task(project, operation_id, task_id,
            {'sourceTexts': {digest(span): source_slice(owner(current).sources, span) for span in spans},
                'diagnostics': list(errors), 'scope': scope, **({'leftoverOnly': leftover} if leftover else {})}, spans,
            task.allowed_handles, 'source_fallback', issues, accepted=kept)

    async def finalize(self, project, operation_id):
        workspace = self.read(project)
        operation = operation_in(workspace, operation_id)
        if workspace.project is not None and operation.finalization is not None:
            candidate = operation.finalization
            binding = TemplateFinalizationBinding(operationId=operation.id, authorizationId=candidate.authorization_id,
                finalizationId=candidate.id)
            outcome = self.persistence.outcome(project, binding)
            if outcome.state != 'saved':
                operation = operation.model_copy(deep=True)
                operation.publication = outcome
                return operation
            if operation.state == 'published':
                return operation
            # Receipt reconciliation reports saved even if its metadata window has expired.
            result = operation.model_copy(deep=True)
            result.state, result.publication = 'published', outcome
            return result
        self.guard(project, operation)
        if any(attempt.cleanup.state != 'verified' for attempt in operation.attempts):
            return operation
        authored = self.assemble(workspace, operation)
        authored.document_revision = workspace.document_revision + 1
        authored.project.document.revision = authored.document_revision
        if operation.finalization is not None and operation.finalization.authorization_id != authorization(operation).id:
            candidate = await asyncio.to_thread(self.persistence.renew_candidate, project, operation, authored.project,
                self.wall(), id_factory=self.id_factory)
        else:
            candidate = capture_finalization(operation, authored.project, self.wall(), id_factory=self.id_factory)
        def prepare(result, _data, _workspace):
            if result.finalization is not None and result.finalization != candidate:
                result.finalization_history.append(result.finalization)
            result.finalization, result.state = candidate, 'finalizing'
            return result
        window = self.persistence.windows.setdefault((project, candidate.id), PersistenceWindow.capture(candidate.expires_at,
            self.wall(), self.elapsed(), started_at=candidate.started_at))
        try:
            before = await self.persistence.bounded(project, lambda: self.update(project, operation_id, prepare), window)
        except BackgroundFailure:
            from packages.resume_core.models.template_import import PublicationOutcome
            result = operation.model_copy(deep=True)
            result.state = 'fenced'
            result.publication = PublicationOutcome(state='outcome_unknown', intentId=None, workspaceHash=None,
                errorCode='OUTCOME_UNKNOWN')
            return result
        operation = operation_in(before, operation_id)
        authored.project.template_operations = owner(before).template_operations
        authored.project_revision = before.project_revision + 1
        authored.project.revision = authored.project_revision
        authored.document_revision = before.document_revision + 1
        authored.project.document.revision = authored.document_revision
        authored.updated_at = self.wall()
        authored = validated_with_history(authored)
        outcome = await self.persistence.publish(before, authored, operation, originals=self.originals,
            artifacts=self.artifacts, images=self.images)
        result = operation.model_copy(deep=True)
        if outcome.state == 'saved':
            result.publication, result.state = outcome, 'published'
            return result
        result.publication = outcome
        result.state = 'fenced' if outcome.state == 'outcome_unknown' else 'cancelled' if outcome.state == 'cancelled' else 'failed'
        return result

    async def finish_fallbacks(self, project, operation_id):
        for task_id in [task.id for task in operation_in(self.read(project), operation_id).tasks]:
            workspace = self.read(project)
            operation, data = operation_in(workspace, operation_id), owner(workspace)
            if operation.state in {'cancelled', 'fenced', 'published'}:
                return operation
            if any(result.task_id == task_id for result in operation.task_results):
                continue
            task = task_in(operation, task_id)
            if not any(value.task_id == task_id for value in operation.task_inputs):
                value, handles = self.task_input(operation, task, data)
                await asyncio.to_thread(self.update_operation, project, operation_id, lambda result, _data, _workspace:
                    capture_task_input(result, task_id, value, handles, self.wall(), id_factory=self.id_factory))
            await self.fallback(project, operation_id, task_id, ['IMPORT_PROCESSING_STOPPED'])
        return operation_in(self.read(project), operation_id)
