"""One proposal-only coordinator for direct and queued template processing."""

import asyncio
from dataclasses import dataclass, replace
import threading
import time

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_import import (CleanupOutcome, ImportIssue, ObservedUsage, ReviewInputRecord,
    TaskResultRecord)
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.models.template_authority import DeletedTemplateCleanupV1, TemplateFinalizationBinding
from packages.resume_core.template_admission import admit_proposal
from packages.resume_core.template_builtin_admission import current_handles
from packages.resume_core.template_effective import effective_cells
from packages.resume_core.template_capture import item_identities, prepare_builtin_identities
from packages.resume_core.template_finalization import capture_finalization
from packages.resume_core.template_identity import capture_span, empty_value, source_slice
from packages.resume_core.template_import import (CleanupProof, ProcessingDeadline, TemplateImportFailure, admit_operation, attempt_in,
    authorization, cancel_operation, capture_task_input, checked, digest, dispatch_attempt, identity, observe_time,
    record_return, reconcile_cleanup, recover_operation, reserve_attempt, resume_operation, start_operation, task_in)
from packages.resume_core.template_proposals import parse_proposal
from packages.resume_core.template_review import decide_review, make_review_input, record_review
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.replies import proposal_schema, review_schema, PROPOSAL_PROTOCOL

from ..providers.content import ContentFailure, ContentInput, ContentTransportReturn, GenerationPolicy, outcome_state
from ..providers.dynamic_result import dynamic_result
from .template_persistence import PersistenceWindow, TemplatePersistence
from .template_checkpoints import TemplateCheckpoints


@dataclass(frozen=True)
class DerivedTask:
    value: object
    source_spans: tuple
    item_handles: tuple


def owner(workspace):
    return workspace.project or workspace.pre_draft


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
                operation = self.publisher.canonical._read_template_cleanup_unlocked(project, operation_id)
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
        self.facts_current(operation, owner(workspace).facts)
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
            for identifier in [task.id for task in operation.tasks]:
                if cancel.is_set():
                    break
                await self.execute_task(project, operation.id, identifier, deadline, cancel)
            workspace = self.read(project)
            operation = operation_in(workspace, operation.id)
            if cancel.is_set() or operation.state in {'cancelled', 'fenced'}:
                return operation
            return await self.finalize(project, operation.id) if finalize else operation

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
        spans = [capture_span(source, unit) for source in data.sources for unit in source.units] if source_requested else []
        spans += [span for cell in cells for span in cell.evidence]
        spans += [span for result in dependencies for span in result.source_spans]
        spans = list({digest(span): span for span in spans}.values())
        value = {'protocol': 'template_import_v1', 'tools': [], 'replyProtocol': PROPOSAL_PROTOCOL,
            'packageHash': data.template_package.package_hash,
            'allowTextRewrite': operation.capture.allow_text_rewrite,
            'formattingAsOf': operation.capture.formatting_as_of.model_dump(mode='json', by_alias=True),
            'modelInstructions': data.template_package.definition.model.model_dump(mode='json', by_alias=True),
            'declaration': declaration.model_dump(mode='json', by_alias=True),
            'sourceSpans': [span.model_dump(mode='json', by_alias=True) for span in spans],
            'sourceTexts': {digest(span): source_slice(data.sources, span) for span in spans},
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
        if task.state == 'pending' and not any(value.task_id == task_id for value in operation.task_inputs):
            value, handles = self.task_input(operation, task, data)
            workspace = await asyncio.to_thread(self.update, project, operation_id,
                lambda value_op, _data, _workspace: capture_task_input(value_op, task_id, value, handles, self.wall(), id_factory=self.id_factory))
            operation = operation_in(workspace, operation_id)
        if task.kind in {'derive', 'source_copy'}:
            derived = self.derive(operation, task_in(operation, task_id), owner(workspace))
            await self.finish_task(project, operation_id, task_id, derived.value, derived.source_spans,
                derived.item_handles, 'empty' if empty_value(derived.value) else 'derived', [])
            return
        feedback, unresolved = (), []
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
            if existing is None:
                stored = next(value for value in operation.task_inputs if value.task_id == task_id)
                allowed = set(task_in(operation, task_id).allowed_handles)
                known_relations = {value.id: value for value in data.facts.relations}
                for retained in operation.proposals:
                    if attempt_in(operation, retained.attempt_id).task_id == task_id:
                        known_relations.update({value.id: value for value in retained.resolved_relations})
                request = {**stored.value, 'slot': slot, 'feedback': list(feedback),
                    'capturedHandles': [allocation.model_dump(mode='json', by_alias=True) for allocation in item_identities(operation)
                        if allocation.item_handle in allowed],
                    'capturedRelations': [value.model_dump(mode='json', by_alias=True) for value in known_relations.values()
                        if value.subject_id in {allocation.record_id for allocation in item_identities(operation) if allocation.item_handle in allowed}]}
                try:
                    attempt_id = await self.call(project, operation_id, task_id, slot, request,
                        proposal_schema(next(value.full_schema for value in data.template_package.blocks
                            if value.id == task.block_id)), deadline, cancel)
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
            workspace = await asyncio.to_thread(self.update, project, operation_id, parse)
            operation, data = operation_in(workspace, operation_id), owner(workspace)
            proposal = next(value for value in operation.proposals if value.attempt_id == attempt_id)
            if proposal.state == 'invalid':
                unresolved.extend(proposal.errors)
                if slot == 'primary_repair' and feedback:
                    continue
                break
            policy = attempt.model
            prior_review = next((value.value for value in operation.review_inputs
                if value.value.proposal_hash == proposal.proposal_hash and value.value.policy == policy), None)
            review = prior_review or make_review_input(operation, proposal, data.template_package, data.sources, policy,
                effective_cells=effective_cells(data.facts, data.template_operations),
                semantic_context={'taskInput': next(value.value for value in operation.task_inputs if value.task_id == task_id),
                    'effectiveFactsHash': digest(data.facts), 'proposal': proposal.reply.model_dump(mode='json', by_alias=True)})
            review_attempt = next((value for value in operation.attempts if value.task_id == task_id
                and value.slot in {'review', 'replacement_review'} and value.input_hash == digest(review)), None)
            try:
                if review_attempt is None:
                    review_id = await self.call(project, operation_id, task_id,
                        'review' if slot == 'initial' else 'replacement_review', review.model_dump(mode='json', by_alias=True),
                        review_schema(), deadline, cancel, review=review)
                else:
                    review_id = review_attempt.id
                self.guard(project, operation_in(self.read(project), operation_id))
                def accept(value, current, _workspace):
                    self.facts_current(value, current.facts)
                    updated, receipt = record_review(value, review_id, current.sources, self.wall(), id_factory=self.id_factory)
                    updated, facts = admit_proposal(updated, proposal.id, receipt.id, current.template_package, current.sources,
                        current.facts, expected_revisions={handle: record.revision
                            for handle, record in current_handles(updated, current.facts).items()},
                        expected_relation_revisions={relation.id: relation.revision for relation in current.facts.relations})
                    current.facts = facts
                    return updated
                workspace = await asyncio.to_thread(self.update, project, operation_id, accept)
                operation = operation_in(workspace, operation_id)
                receipt = next(value for value in operation.receipts if value.attempt_id == review_id)
                decision = decide_review(review, receipt, proposal)
            except (TemplateImportFailure, ValueError) as error:
                unresolved.append(getattr(error, 'code', 'IMPORT_REVIEW_INVALID'))
                break
            feedback = decision.feedback
            if not decision.unresolved_target_ids:
                effective = owner(workspace).facts
                active_handles = {record.item_handle for record in effective.extensions if record.active}
                active_handles.update(allocation.item_handle for allocation in item_identities(operation)
                    if allocation.record_id in {record.id for record in effective.records})
                handles = [handle for handle in [*[field.item_handle for field in proposal.resolved_fields],
                    *[parent for link in proposal.lineage for parent in link.parents]] if handle in active_handles]
                await self.finish_task(project, operation_id, task_id, None, (), handles,
                    'empty' if empty_value(proposal.reply.payload) else 'admitted', [])
                return
            unresolved = list(decision.unresolved_target_ids)
        await self.fallback(project, operation_id, task_id, unresolved)

    async def call(self, project, operation_id, task_id, slot, value, schema, deadline, cancel, *, review=None):
        workspace = self.read(project)
        operation = operation_in(workspace, operation_id)
        self.guard(project, operation)
        remaining = deadline.remaining(operation, self.wall(), self.elapsed())
        workspace = await asyncio.to_thread(self.update, project, operation_id, lambda result, _data, _workspace:
            observe_time(result, self.wall(), elapsed_remaining=remaining))
        operation = operation_in(workspace, operation_id)
        policy = review.policy if review is not None else operation.capture.fallback if slot == 'fallback_repair' else operation.capture.primary
        launch_owner = self.transport.reserve_owner(operation, task_in(operation, task_id), policy)
        reserved = []
        def reserve(result, _data, _workspace):
            result, identifier = reserve_attempt(result, task_id, slot, digest(value), policy, launch_owner, self.wall(),
                request_value=value, id_factory=self.id_factory)
            if review is not None:
                record = ReviewInputRecord(id=self.id_factory('review-input'), attemptId=identifier, inputHash=digest(review), value=review)
                result.review_inputs.append(record)
                attempt_in(result, identifier).review_input_record_id = record.id
            reserved.append(identifier)
            return result
        await asyncio.to_thread(self.update, project, operation_id, reserve)
        attempt_id = reserved[0]
        self.guard(project, operation_in(self.read(project), operation_id))
        def dispatch(result, _data, _workspace):
            now = self.wall()
            remaining = deadline.remaining(result, now, self.elapsed())
            result = observe_time(result, now, elapsed_remaining=remaining)
            if remaining <= 0:
                return self.reconcile_unlaunched(result, attempt_id, now)
            return dispatch_attempt(result, attempt_id, now)
        dispatched = await asyncio.to_thread(self.update, project, operation_id, dispatch)
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
            self.update(project, operation_id, retain)
        request = ContentInput(canonical(value).decode(), dynamic_result(schema),
            GenerationPolicy(policy.model, timeout_seconds=min(180, max(0.001, remaining)), allow_repair=False,
                reasoning_effort=policy.effort), on_return=returned)
        def launch():
            current = operation_in(self.read(project), operation_id)
            self.guard(project, current)
            remaining = deadline.remaining(current, self.wall(), self.elapsed())
            if remaining <= 0:
                self.update(project, operation_id, lambda result, _data, _workspace: self.reconcile_unlaunched(
                    observe_time(result, self.wall(), elapsed_remaining=0), attempt_id, self.wall()))
                return None
            bounded = replace(request, policy=replace(request.policy, timeout_seconds=min(180, remaining)))
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
                await asyncio.to_thread(self.update, project, operation_id, lambda result, _data, _workspace:
                    record_return(result, attempt_id, error.raw_return,
                        attempt.outcome if attempt.outcome == 'timed_out' else outcome_state(error.code), attempt.usage,
                        attempt.cleanup, error_code=attempt.error_code if attempt.outcome == 'timed_out' else error.code))
        else:
            if attempt_in(operation_in(self.read(project), operation_id), attempt_id).state == 'dispatch_started':
                returned(ContentTransportReturn(response.raw_return, 'completed', None, response.logical_attempts,
                    response.usage, response.cleanup_verified, response.dispatch_witness, response.reasoning_effort))
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

    async def finish_task(self, project, operation_id, task_id, value, spans, handles, disposition, issues):
        def finish(operation, _data, _workspace):
            task = task_in(operation, task_id)
            task.state = 'source_fallback' if disposition == 'source_fallback' else 'empty' if disposition == 'empty' else 'accepted'
            task.issue_ids = [issue.id for issue in issues]
            operation.issues.extend(issues)
            operation.task_results.append(TaskResultRecord(id=self.id_factory('task-result'), taskId=task_id,
                inputHash=task.input_hash, value=value, sourceSpans=list(spans), itemHandles=list(dict.fromkeys(handles)),
                issueIds=task.issue_ids, disposition=disposition))
            return operation
        await asyncio.to_thread(self.update, project, operation_id, finish)

    async def fallback(self, project, operation_id, task_id, errors):
        current = self.read(project)
        operation = operation_in(current, operation_id)
        if operation.state in {'cancelled', 'fenced'}:
            return
        task = task_in(operation, task_id)
        stored = next(value for value in operation.task_inputs if value.task_id == task_id)
        from packages.resume_core.models.template_facts import SourceSpan
        spans = [SourceSpan.model_validate(value) for value in stored.value['sourceSpans']]
        receipt = next((value for value in reversed(operation.receipts) if value.id in task.receipt_ids), None)
        failures = [result for result in receipt.reply.results if result.disposition != 'satisfied'] if receipt else []
        if failures and not any(result.target_id.startswith('scope-') for result in failures):
            rejected = {result.target_id for result in failures}
            proposal = next((value for value in reversed(operation.proposals) if value.applied_receipt_id == receipt.id), None)
            allocated = {value.item_handle: value for value in item_identities(operation)}
            affected = [span for field in proposal.resolved_fields
                if allocated[field.item_handle].cell_ids[field.field_key] in rejected for span in field.evidence] if proposal else []
            if proposal is not None:
                from packages.resume_core.template_proposals import relation_evidence
                affected.extend(span for identifier, spans in relation_evidence(operation, proposal).items()
                    if identifier in rejected for span in spans)
            if affected:
                spans = list({digest(span): span for span in affected}.values())
        issues = [ImportIssue(id=self.id_factory('issue'), ruleId=result.rule_id if result else None, taskId=task_id,
            targetIds=[result.target_id] if result else ['scope-' + task_id], blockIds=[],
            category=('content_violation' if result.disposition == 'violation' else 'uncertain_interpretation')
                if result else 'check_not_completed', code='IMPORT_SOURCE_FALLBACK',
            message=result.reason if result and result.reason.strip() else
                'Source wording retained because interpretation checks did not complete.',
            importedFingerprint=digest(stored.value), reviewInputHash=receipt.review_input_hash if result else None,
            lifecycleId=self.id_factory('issue-lifecycle'), state='active', retiredByAction=None)
            for result in failures or [None]]
        await self.finish_task(project, operation_id, task_id,
            {'sourceTexts': {digest(span): source_slice(owner(current).sources, span) for span in spans},
                'diagnostics': list(errors)}, spans,
            task.allowed_handles, 'source_fallback', issues)

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
        authored = WorkspaceV7.model_validate(authored.model_dump(by_alias=True))
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
                await asyncio.to_thread(self.update, project, operation_id, lambda result, _data, _workspace:
                    capture_task_input(result, task_id, value, handles, self.wall(), id_factory=self.id_factory))
            await self.fallback(project, operation_id, task_id, ['IMPORT_PROCESSING_STOPPED'])
        return operation_in(self.read(project), operation_id)
