"""The template import coordinator: proposals, reviews and publication through the project repository, with the
running steps in the operation sidecar (S7e, D109)."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, replace
import hashlib
import json
import threading
import time

from packages.resume_core.project_repository import RepositoryFailure, decode_project, rich_snapshot_bytes, verifying
from packages.resume_core.project_store import strict_json
from packages.resume_core.models.template_import import (CleanupOutcome, ImportIssue, ObservedUsage, PublicationOutcome,
    ReferenceTable, ReviewInputRecord, TaskResultRecord)
from packages.resume_core.template_admission import admit_proposal, task_facts_digest
from packages.resume_core.template_builtin_admission import current_handles
from packages.resume_core.template_effective import effective_cells
from packages.resume_core.template_capture import item_identities, prepare_builtin_identities
from packages.resume_core.template_identity import (capture_span, empty_value, evidence_options, line_spans,
    offered_evidence, source_slice)
from packages.resume_core.template_entries import (closed_state, entry_part, entry_records, grouped, line_options,
    ordered_entries, outline_part, parse_outline, parse_outline_review, reorder_records, splits_entries)
from packages.resume_core.template_import import (GENERATION_SLOTS, CleanupProof, ProcessingDeadline, TemplateImportFailure,
    add_entry_tasks, add_outline_review, admit_operation, attempt_in, authorization, cancel_operation, capture_finalization,
    capture_task_input, checked, children_of, digest, dispatch_attempt, entries_of, identity, observe_time, record_return,
    reconcile_cleanup, recover_operation, reserve_attempt, resume_operation, spent_calls, start_operation, task_in)
from packages.resume_core.template_proposals import parse_proposal, transport_refusal
from packages.resume_core.template_review import decide_review, make_review_input, record_review, repair_wins, shown_values
from packages.resume_core.template_prompt import model_prompt
from packages.resume_core.templates.operations import operation_value
from packages.resume_core.templates.replies import (BOOKKEEPING_KEYS, OUTLINE_PROTOCOL, OUTLINE_REVIEW_PROTOCOL, outline_review_schema,
    outline_schema, proposal_protocol, proposal_schema, review_schema, PROPOSAL_PROTOCOL)

from ..providers.content import ContentFailure, ContentInput, ContentTransportReturn, GenerationPolicy, outcome_state
from ..providers.dynamic_result import dynamic_result
from .template_sidecar import OperationSidecar


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


@dataclass(frozen=True)
class Spawned:
    """What a task's run added to the import (D117): the tasks that now belong to the block task `parent`, and
    whether the task that ran stays open until the block's children ended (the block task) or ended itself."""
    parent: str
    children: tuple
    open: bool


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


# A call has no time limit of its own: it may use the import's remaining time (D114: on the projects block Sol
# took 84-127 s where a 90 s call limit stood and spent the repair slot). Only the import limit ends a silent call.
# Import reads kept, one per project; a running import hits its own between sidecar steps.
CACHED_READS = 4


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


# D117: the outline review of a block names what the outline missed (added as entries) or doubts (shown once).
OUTLINE_REMARK = 'Разметка записей блока под вопросом: {reasons}'
OUTLINE_UNCHECKED = 'Проверка полноты записей блока не завершилась.'


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


class TemplatePipeline:
    def __init__(self, transport, *, repository, authority, assemble, derive, wall, elapsed=time.monotonic,
                 id_factory=identity):
        self.repository, self.transport = repository, transport
        self.authority, self.assemble, self.derive = authority, assemble, derive
        self.wall, self.elapsed, self.id_factory = wall, elapsed, id_factory
        self.locks, self.cancels = {}, {}
        self.read_cache, self.cache_lock = OrderedDict(), threading.Lock()

    def read(self, project):
        session = self.repository.open(project)
        with session.lock:
            committed = workspace = session.workspace
            data = owner(workspace)
            if workspace.project is not None and not data.history_loaded:
                workspace = decode_project(session.directory, rich_snapshot_bytes(workspace), history=True)
                data = owner(workspace)
            sidecar = OperationSidecar(session.directory)
            keys = sidecar.keys(project, workspace)
            # The entry holds the committed object and compares it by identity: an id() key matched a later
            # workspace that CPython had placed at the address of a freed one.
            cached = self.read_cache.get(project)
            hit = cached is not None and cached[0] is committed and cached[1] == keys
            if hit and not verifying():
                return cached[2]
            overlays = [sidecar.overlay(project, session.revision, value) for value in data.template_operations]
            facts = [value for _operation, value in overlays if value is not None]
            if len(facts) > 1:
                raise RepositoryFailure('OUTCOME_UNKNOWN')
            view = workspace.model_copy(deep=True)
            holder = owner(view)
            holder.template_operations = [operation for operation, _facts in overlays]
            if facts:
                holder.facts = facts[0]
            if hit:
                if cached[2] != view:
                    raise RuntimeError('Import read cache changed')
                return cached[2]
            with self.cache_lock:
                self.read_cache.pop(project, None)
                self.read_cache[project] = (committed, keys, view)
                while len(self.read_cache) > CACHED_READS:
                    self.read_cache.popitem(last=False)
            return view

    async def view(self, project):
        """read() in a worker thread: it waits for the project lock and may copy the whole workspace."""
        return await asyncio.to_thread(self.read, project)

    def recheck(self, project, operation_id):
        self.guard(project, operation_in(self.read(project), operation_id))

    def checkpoint(self, project, transition, **_options):
        session = self.repository.open(project)
        with session.lock:
            before = self.read(project)
            after = transition(before.model_copy(deep=True))
            if after == before:
                return before
            identifier = self.id_factory('metadata_template')
            self.repository.replace(project, base_revision=before.project_revision, workspace=after, reason='import',
                client_mutation_id=identifier, request_sha256=hashlib.sha256(identifier.encode()).hexdigest())
            return self.read(project)

    def update_operation(self, project, operation_id, transition, *, copy_on_write=False):
        del copy_on_write
        session = self.repository.open(project)
        with session.lock:
            before = self.read(project)
            view = before.model_copy(deep=True)
            data = owner(view)
            prior = operation_in(view, operation_id)
            updated = checked(transition(prior, data, view))
            data.template_operations = [updated if value.id == operation_id else value for value in data.template_operations]
            if view == before:
                return before
            OperationSidecar(session.directory).write(project, before.project_revision, updated, data.facts)
            self.read_cache.pop(project, None)
            return self.read(project)

    def update(self, project, identifier, transition):
        def apply(workspace):
            prior = operation_in(workspace, identifier)
            updated = transition(prior, owner(workspace), workspace)
            owner(workspace).template_operations[owner(workspace).template_operations.index(prior)] = checked(updated)
            return workspace
        return self.checkpoint(project, apply)

    def guard(self, project, operation):
        workspace = self.read(project)
        self.authority(operation, workspace)
        data = owner(workspace)
        if (data.template_package.package_hash != operation.capture.package_hash or
                {value.id: value.byte_sha256 for value in data.sources} != operation.capture.source_hashes):
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
        self.facts_current(operation_in(workspace, operation.id), data.facts)

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
        workspace = await self.view(project)
        operation = operation_in(workspace, identifier)
        if workspace.project is not None and operation.finalization is not None:
            return await asyncio.to_thread(self.record_publication, project, identifier)
        def recover(value, _data, _workspace):
            updated = recover_operation(value)
            for attempt in updated.attempts:
                if attempt.state == 'outcome_unknown' or attempt.cleanup.state != 'verified':
                    proof = self.transport.reconcile(attempt)
                    if proof is not None:
                        updated = reconcile_cleanup(updated, proof, self.wall())
            return updated
        updated = await asyncio.to_thread(self.update, project, identifier, recover)
        return operation_in(updated, identifier)

    async def cancel(self, project, identifier):
        import threading
        self.cancels.setdefault((project, identifier), threading.Event()).set()
        await asyncio.to_thread(self.update, project, identifier,
            lambda operation, _data, _workspace: cancel_operation(operation))
        return True

    def authorize(self, project, operation):
        self.guard(project, operation)

    async def run(self, project, command, *, admitted, finalize=True, cancel_event=None):
        if command.protocol != 'template_import_v1':
            raise TemplateImportFailure('IMPORT_PROTOCOL_MISMATCH')
        async with self.locks.setdefault(project, asyncio.Lock()):
            if command.kind == 'start_new_import':
                operation = await self.start(project, command)
                if operation.finalization is not None and (await self.view(project)).project is not None:
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
            await asyncio.to_thread(self.authorize, project, operation)
            await admitted()
            workspace = await asyncio.to_thread(self.update, project, operation.id,
                lambda value, _data, _workspace: admit_operation(value, self.wall()))
            operation = operation_in(workspace, operation.id)
            deadline = ProcessingDeadline.capture(operation, self.wall(), self.elapsed())
            await self.run_tasks(project, operation, deadline, cancel,
                implicit=implicit_dependencies(owner(workspace).template_package, operation))
            operation = operation_in(await self.view(project), operation.id)
            if cancel.is_set() or operation.state in {'cancelled', 'fenced'}:
                return operation
            return await self.finalize(project, operation.id, cancel) if finalize else operation

    async def run_tasks(self, project, operation, deadline, cancel, *, implicit=None):
        """Tasks start in declaration order once the tasks they depend on ended; up to the captured concurrency run
        at once (CT10); concurrency 1 awaits each task in place. A block that extracts its entries on their own
        (D117) adds them while it runs, stays open until they all ended and then closes. After a failure or a
        cancel nothing new starts, the running tasks end, and the first failure is raised."""
        # The children a block added before (a resumed import) are reported by the block when it runs again.
        order = [task.id for task in operation.tasks if getattr(task, 'parent_task_id', None) is None]
        width = operation.capture.policy.concurrency
        waits = {task.id: (set(task.dependencies) | (implicit or {}).get(task.id, set())) & set(order) for task in operation.tasks}
        pending, running, ended, failure = list(order), {}, set(), None
        parents, children = {}, {}

        def ready_tasks():
            ready = [value for value in pending if waits[value] <= ended]
            if not ready and not running and pending:
                # A dependency no task here can end (a cycle) runs in declaration order, as sequentially.
                ready = pending[:1]
            return ready

        async def settle(identifier, spawned):
            if isinstance(spawned, Spawned):
                added = [child for child in spawned.children if child not in children.get(spawned.parent, set())]
                for child in added:
                    waits[child], parents[child] = waits[spawned.parent], spawned.parent
                    children.setdefault(spawned.parent, set()).add(child)
                # The entries are the rest of the block's chain, which its dependents wait for: they start before the
                # blocks still queued, not after them.
                pending[0:0] = added
                if spawned.open:
                    return
            ended.add(identifier)
            parent = parents.get(identifier)
            if parent is not None and parent not in ended and children[parent] <= ended and not cancel.is_set():
                await self.close_entries(project, operation.id, parent)
                ended.add(parent)

        if width == 1:
            while pending and not cancel.is_set():
                identifier = ready_tasks()[0]
                pending.remove(identifier)
                await settle(identifier, await self.execute_task(project, operation.id, identifier, deadline, cancel))
            return
        try:
            while pending or running:
                if failure is None and not cancel.is_set():
                    for identifier in ready_tasks()[:max(width - len(running), 0)]:
                        pending.remove(identifier)
                        running[asyncio.ensure_future(self.execute_task(project, operation.id, identifier, deadline, cancel))] = identifier
                if not running:
                    break
                finished, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for future in finished:
                    identifier = running.pop(future)
                    if future.cancelled() or future.exception() is not None or failure is not None:
                        ended.add(identifier)
                        if failure is None and not future.cancelled() and future.exception() is not None:
                            failure = future.exception()
                        continue
                    await settle(identifier, future.result())
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
        if task.parent_task_id is not None:
            # D117: an entry or the outline review reads the block's captured input, plus the part that names its scope.
            parent = next(value.value for value in operation.task_inputs if value.task_id == task.parent_task_id)
            offered = offered_evidence(parent) or {}
            part = ({'outline': outline_part(operation, task.parent_task_id, offered)} if task.kind == 'outline_review'
                else {'entry': entry_part(operation, task, offered)})
            return {**parent, **part}, list(task_in(operation, task.parent_task_id).allowed_handles)
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
        workspace = await self.view(project)
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
        if task.kind == 'outline_review':
            return await self.review_outline(project, operation_id, task_id, deadline, cancel)
        block = next(value for value in data.template_package.definition.blocks if value.id == task.block_id)
        if task.parent_task_id is None and splits_entries(block):
            spawned = await self.outline(project, operation_id, task_id, deadline, cancel)
            if spawned is not None:
                return spawned
        feedback, unresolved, previous, previous_receipt = (), [], None, None
        for slot in ['initial', 'primary_repair', 'fallback_repair']:
            workspace = await self.view(project)
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
                    request['replyProtocol'] = proposal_protocol(references, entry=task.entry is not None)
                if previous is not None:
                    # D107: a repair that saw only the findings wrote the block anew and lost admitted values.
                    request['previousReply'] = previous_reply(previous, offered, references)
                try:
                    attempt_id = await self.call(project, operation_id, task_id, slot, request,
                        proposal_schema(next(value.full_schema for value in data.template_package.blocks
                            if value.id == task.block_id), None if offered is None else list(offered), references), deadline, cancel)
                except AccountStop:
                    raise
                except TemplateImportFailure as error:
                    unresolved.append(error.code)
                    break
            else:
                attempt_id = existing.id
            workspace = await self.view(project)
            operation, data = operation_in(workspace, operation_id), owner(workspace)
            attempt = attempt_in(operation, attempt_id)
            if attempt.cleanup.state != 'verified' or operation.state == 'cancelled':
                return
            await asyncio.to_thread(self.guard, project, operation)
            if attempt.outcome != 'completed' and attempt.proposal_record_id is None:
                unresolved.append(attempt.error_code or attempt.outcome or 'IMPORT_RETURN_UNKNOWN')
                refusal = transport_refusal(attempt, data.template_package, task.block_id) if (slot != 'fallback_repair'
                    and attempt.outcome == 'invalid_payload') else None
                if refusal is not None:
                    # A reply the transport refused by schema is repaired like a refused proposal.
                    feedback = repair_feedback(feedback, task_id, [refusal])
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
            # Reviews run with the captured review model (D116: low); captures made before keep the proposal's.
            policy = operation.capture.review or attempt.model
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
                    'otherBlocks': other_blocks(operation, task, data.template_package)},
                # D115: what the repair left as it was keeps the reviewed reply's receipt results.
                previous=(previous, previous_receipt) if previous is not None and previous_receipt is not None else None)
            review_attempt = next((value for value in operation.attempts if value.task_id == task_id
                and value.slot in {'review', 'replacement_review'} and value.input_hash == digest(review)), None)
            try:
                if review_attempt is None:
                    review_id = await self.call(project, operation_id, task_id,
                        'review' if slot == 'initial' else 'replacement_review', review.model_dump(mode='json', by_alias=True),
                        review_schema(review), deadline, cancel, review=review)
                else:
                    review_id = review_attempt.id
                await asyncio.to_thread(self.recheck, project, operation_id)
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
            feedback, previous, previous_receipt = decision.feedback, proposal, receipt
            # A clean repair that was not better leaves the first reply and its findings in place.
            if not decision.unresolved_target_ids and not kept_first[0]:
                await self.finish_admitted(project, operation_id, task_id, proposal)
                return
            unresolved = list(decision.unresolved_target_ids)
        await self.fallback(project, operation_id, task_id, unresolved)

    async def finish_admitted(self, project, operation_id, task_id, proposal):
        workspace = await self.view(project)
        operation, effective = operation_in(workspace, operation_id), owner(workspace).facts
        active_handles = {record.item_handle for record in effective.extensions if record.active}
        active_handles.update(allocation.item_handle for allocation in item_identities(operation)
            if allocation.record_id in {record.id for record in effective.records})
        handles = [handle for handle in [*[field.item_handle for field in proposal.resolved_fields],
            *[parent for link in proposal.lineage for parent in link.parents]] if handle in active_handles]
        fingerprint = digest(next(value for value in operation.task_inputs if value.task_id == task_id).value)
        await self.finish_task(project, operation_id, task_id, None, (), handles,
            'empty' if empty_value(proposal.reply.payload) else 'admitted', unbound_issues(self.id_factory, task_id, proposal, fingerprint))

    async def outline(self, project, operation_id, task_id, deadline, cancel):
        """The outline call of a block that extracts its entries on their own (D117): what the block task added, or
        None when the block runs whole instead: it ran whole already, calls run one at a time, the outline would not
        fit the call cap, the call gave no reply, or the reply named no two entries on offered lines without a shared
        line."""
        workspace = await self.view(project)
        operation, data = operation_in(workspace, operation_id), owner(workspace)
        children = children_of(operation, task_id)
        if children:
            # Resumed after its entries were added: they run on and the block closes when they all ended.
            return Spawned(task_id, tuple(child.id for child in children), True)
        existing = next((attempt for attempt in operation.attempts if attempt.task_id == task_id and attempt.slot == 'outline'
            and attempt.state != 'released'), None)
        if existing is None:
            if any(attempt.task_id == task_id and attempt.slot in GENERATION_SLOTS for attempt in operation.attempts):
                return None
            stored = next(value for value in operation.task_inputs if value.task_id == task_id)
            offered = offered_evidence(stored.value)
            lines = line_options(offered, data.sources) if offered is not None else []
            # Two entries need two lines and two calls at once: one call at a time would run the groups one after
            # another, and the whole block is faster. The outline, its review and two groups of a call and a review
            # each must fit the cap; with less, the whole block's call and review are what admits values.
            if (len(lines) < 2 or operation.capture.policy.concurrency < 2
                    or operation.capture.policy.call_cap - spent_calls(operation) < 2 + 2 * 2):
                return None
            request = {**stored.value, 'slot': 'outline', 'replyProtocol': OUTLINE_PROTOCOL}
            try:
                # Bounds name lines only: a whole page or unit as a bound would move the entry's first line.
                attempt_id = await self.call(project, operation_id, task_id, 'outline', request,
                    outline_schema([option.ref for option in lines]), deadline, cancel)
            except AccountStop:
                raise
            except TemplateImportFailure:
                return None
        else:
            attempt_id = existing.id
        workspace = await self.view(project)
        operation, data = operation_in(workspace, operation_id), owner(workspace)
        attempt = attempt_in(operation, attempt_id)
        if attempt.cleanup.state != 'verified' or operation.state == 'cancelled':
            # A fenced or cancelled import: the task ends here like any block's, without a result.
            return Spawned(task_id, (), False)
        if attempt.outcome != 'completed' or attempt.raw_return is None:
            return None
        try:
            outer = strict_json(attempt.raw_return)
            if not isinstance(outer, dict) or set(outer) != {'payload'}:
                raise ValueError('outline needs its payload envelope')
            scopes = parse_outline(outer['payload'], offered_evidence(attempt.request_value), data.sources)
        except (ValueError, TypeError, KeyError, RecursionError):
            return None
        # Each group needs its call and its review after the outline review; other blocks spent calls meanwhile.
        room = (operation.capture.policy.call_cap - spent_calls(operation) - 1) // 2
        count = min(operation.capture.policy.concurrency, room)
        if len(scopes) < 2 or count < 2:
            return None
        groups = grouped(scopes, count)
        def spawn(value, _data, _workspace):
            # The review goes first so it starts beside the first entries and adds a missed one early.
            value = add_outline_review(value, task_id, id_factory=self.id_factory)
            return add_entry_tasks(value, task_id, groups, 'outline', id_factory=self.id_factory)
        workspace = await asyncio.to_thread(self.update_operation, project, operation_id, spawn, copy_on_write=True)
        operation = operation_in(workspace, operation_id)
        return Spawned(task_id, tuple(child.id for child in children_of(operation, task_id)), True)

    async def review_outline(self, project, operation_id, task_id, deadline, cancel):
        """The review of a block's outline (D117): an entry it names as missing joins the block; its remarks are
        the block's one notice; a review that did not complete says so. Returns the entries added."""
        workspace = await self.view(project)
        operation, data = operation_in(workspace, operation_id), owner(workspace)
        task = task_in(operation, task_id)
        parent_id = task.parent_task_id
        stored = next(value for value in operation.task_inputs if value.task_id == task_id)
        existing = next((attempt for attempt in operation.attempts if attempt.task_id == task_id
            and attempt.slot == 'outline_review' and attempt.state != 'released'), None)
        unresolved, missing, remarks = [], [], []
        if existing is None:
            offered = offered_evidence(stored.value) or {}
            request = {**stored.value, 'slot': 'outline_review', 'replyProtocol': OUTLINE_REVIEW_PROTOCOL,
                'otherBlocks': other_blocks(operation, task, data.template_package)}
            try:
                attempt_id = await self.call(project, operation_id, task_id, 'outline_review', request,
                    outline_review_schema([option.ref for option in line_options(offered, data.sources)]), deadline, cancel)
            except AccountStop:
                raise
            except TemplateImportFailure as error:
                unresolved.append(error.code)
                attempt_id = None
        else:
            attempt_id = existing.id
        workspace = await self.view(project)
        operation, data = operation_in(workspace, operation_id), owner(workspace)
        if attempt_id is not None:
            attempt = attempt_in(operation, attempt_id)
            if attempt.cleanup.state != 'verified' or operation.state == 'cancelled':
                return None
            if attempt.outcome == 'completed' and attempt.raw_return is not None:
                try:
                    outer = strict_json(attempt.raw_return)
                    if not isinstance(outer, dict) or set(outer) != {'payload'}:
                        raise ValueError('outline review needs its payload envelope')
                    taken = [span for entry in entries_of(operation, parent_id) for span in entry.entry.spans]
                    missing, remarks = parse_outline_review(outer['payload'], offered_evidence(attempt.request_value),
                        data.sources, taken=taken)
                except (ValueError, TypeError, KeyError, RecursionError):
                    unresolved.append('IMPORT_OUTLINE_REVIEW_INVALID')
            else:
                unresolved.append(attempt.error_code or attempt.outcome or 'IMPORT_RETURN_UNKNOWN')
        added = []
        if missing:
            before = {child.id for child in children_of(operation, parent_id)}
            # Each missed entry runs on its own: they are few, and the groups already run.
            workspace = await asyncio.to_thread(self.update_operation, project, operation_id, lambda value, _data, _workspace:
                add_entry_tasks(value, parent_id, [[scope] for scope in missing], 'review', id_factory=self.id_factory),
                copy_on_write=True)
            operation = operation_in(workspace, operation_id)
            added = [child.id for child in children_of(operation, parent_id) if child.id not in before]
        issues = []
        if unresolved or remarks:
            issues.append(ImportIssue(id=self.id_factory('issue'), ruleId=None, taskId=task_id, targetIds=['scope-' + task_id],
                blockIds=[], category='check_not_completed' if unresolved else 'uncertain_interpretation',
                code='IMPORT_OUTLINE_UNCHECKED' if unresolved else 'IMPORT_OUTLINE_REMARK',
                message=OUTLINE_UNCHECKED if unresolved else OUTLINE_REMARK.format(reasons=' '.join(remarks)),
                importedFingerprint=digest(stored.value), reviewInputHash=None, lifecycleId=self.id_factory('issue-lifecycle'),
                state='active', retiredByAction=None))
        await self.finish_task(project, operation_id, task_id, {'added': added, 'remarks': remarks, 'diagnostics': unresolved},
            (), (), 'derived', issues)
        return Spawned(parent_id, tuple(added), False)

    async def close_entries(self, project, operation_id, parent_id):
        """A block whose entries ran on their own ends with what they collected (D117): their handles, admitted when
        any entry was, its records in the entries' order. The entries' own results place their lines."""
        def close(operation, current, _workspace):
            if operation.state in {'cancelled', 'fenced'} or any(result.task_id == parent_id for result in operation.task_results):
                return operation
            parent = task_in(operation, parent_id)
            results = {result.task_id: result for result in operation.task_results}
            if any(child.id not in results for child in children_of(operation, parent_id)):
                raise TemplateImportFailure('IMPORT_TASK_NOT_READY')
            entries = ordered_entries(operation, parent_id, current.sources)
            done = [results[task.id] for task in entries]
            current.facts = reorder_records(current.facts, entry_records(operation, entries))
            parent.state, disposition = closed_state(entries)
            operation.task_results.append(TaskResultRecord(id=self.id_factory('task-result'), taskId=parent_id,
                inputHash=parent.input_hash, value={'entries': [task.id for task in entries]}, sourceSpans=[],
                itemHandles=list(dict.fromkeys(handle for result in done for handle in result.item_handles)), issueIds=[],
                disposition=disposition))
            return operation
        await asyncio.to_thread(self.update_operation, project, operation_id, close)

    async def call(self, project, operation_id, task_id, slot, value, schema, deadline, cancel, *, review=None):
        workspace = await self.view(project)
        operation = operation_in(workspace, operation_id)
        await asyncio.to_thread(self.guard, project, operation)
        remaining = deadline.remaining(operation, self.wall(), self.elapsed())
        # Every call runs the model and effort chosen for the import (D114 removed the block-level effort).
        policy = (review.policy if review is not None else operation.capture.fallback if slot == 'fallback_repair'
            else (operation.capture.review or operation.capture.primary) if slot == 'outline_review' else operation.capture.primary)
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
        await asyncio.to_thread(self.recheck, project, operation_id)
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
            GenerationPolicy(policy.model, timeout_seconds=max(0.001, remaining), allow_repair=False,
                reasoning_effort=policy.effort), on_return=returned, request_value=value)
        def launch():
            current = operation_in(self.read(project), operation_id)
            self.guard(project, current)
            remaining = deadline.remaining(current, self.wall(), self.elapsed())
            if remaining <= 0:
                self.update_operation(project, operation_id, lambda result, _data, _workspace: self.reconcile_unlaunched(
                    observe_time(result, self.wall(), elapsed_remaining=0), attempt_id, self.wall()))
                return None
            bounded = replace(request, policy=replace(request.policy, timeout_seconds=remaining))
            return self.transport.generate(bounded, cancel)
        try:
            response = await asyncio.to_thread(launch)
        except ContentFailure as error:
            operation = operation_in(await self.view(project), operation_id)
            attempt = attempt_in(operation, attempt_id)
            if attempt.state == 'dispatch_started':
                await asyncio.to_thread(returned, ContentTransportReturn(error.raw_return, outcome_state(error.code),
                    error.code, error.logical_attempts, error.usage, error.cleanup_verified, error.dispatch_witness,
                    policy.effort))
            else:
                await asyncio.to_thread(self.update_operation, project, operation_id, lambda result, _data, _workspace:
                    record_return(result, attempt_id, error.raw_return,
                        attempt.outcome if attempt.outcome == 'timed_out' else outcome_state(error.code), attempt.usage,
                        attempt.cleanup, error_code=attempt.error_code if attempt.outcome == 'timed_out' else error.code))
        else:
            if attempt_in(operation_in(await self.view(project), operation_id), attempt_id).state == 'dispatch_started':
                await asyncio.to_thread(returned, ContentTransportReturn(response.raw_return, 'completed', None,
                    response.logical_attempts, response.usage, response.cleanup_verified, response.dispatch_witness,
                    response.reasoning_effort))
        current = operation_in(await self.view(project), operation_id)
        if stops_import(current, attempt_in(current, attempt_id)):
            raise AccountStop(attempt_in(current, attempt_id).error_code)
        return attempt_id

    def reconcile_unlaunched(self, operation, attempt_id, now):
        """Release an attempt whose call stopped before the transport: that control flow is the never-dispatched proof."""
        result = operation.model_copy(deep=True)
        attempt = attempt_in(result, attempt_id)
        attempt.error_code = 'IMPORT_PROCESSING_EXHAUSTED'
        return reconcile_cleanup(result, CleanupProof(attempt.id, digest(attempt.owner), digest({'unlaunched': attempt.id}),
            'coordinator-never-launched', True), now)

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
        current = await self.view(project)
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
            if not spans and task.entry is not None:
                # One entry of a block (D117) shows its own lines: the outline named them for it.
                spans = list(task.entry.spans)
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

    async def finalize(self, project, identifier, cancel=None):
        """Publish the import. The publication commit is the point of no return: a cancel seen before it leaves the
        import unpublished and resumable."""
        stopped = cancel if cancel is not None else threading.Event()
        workspace = await self.view(project)
        operation = operation_in(workspace, identifier)
        if workspace.project is not None and operation.finalization is not None:
            return await asyncio.to_thread(self.record_publication, project, identifier)
        await asyncio.to_thread(self.guard, project, operation)
        if any(attempt.cleanup.state != 'verified' for attempt in operation.attempts):
            return operation
        authored = await asyncio.to_thread(self.assemble, workspace, operation)
        authored.document_revision = workspace.document_revision + 1
        authored.project.document.revision = authored.document_revision
        candidate = self.candidate(operation, authored.project)
        if stopped.is_set():
            return operation

        def prepare(value, _data, current):
            if current.project_revision != workspace.project_revision:
                raise RepositoryFailure('REVISION_CONFLICT', revision=current.project_revision)
            if value.finalization is not None and value.finalization != candidate:
                value.finalization_history.append(value.finalization)
            value.finalization, value.state = candidate, 'finalizing'
            return value

        before = await asyncio.to_thread(self.update, project, identifier, prepare)
        authored.project.template_operations = owner(before).template_operations
        authored.project_revision = before.project_revision + 1
        authored.project.revision = authored.project_revision
        authored.updated_at = self.wall()

        def publish():
            if stopped.is_set():
                return operation_in(self.read(project), identifier)
            mutation_id = 'template_publication_' + candidate.id
            self.repository.replace(project, base_revision=before.project_revision, workspace=authored,
                reason='publication', client_mutation_id=mutation_id, request_sha256=hashlib.sha256(mutation_id.encode()).hexdigest())
            return self.record_publication(project, identifier)

        return await asyncio.to_thread(publish)

    def candidate(self, operation, project):
        """The finalization to publish. A resume renews the one an earlier authorization saved before its publication
        failed or was cancelled. finalize() comes here only while the project is unpublished, so nothing was published
        with that candidate and the renewal takes the current content."""
        previous = operation.finalization
        if previous is None or previous.authorization_id == authorization(operation).id:
            return capture_finalization(operation, project, self.wall(), id_factory=self.id_factory)
        return capture_finalization(operation.model_copy(update={'finalization': None}), project, self.wall(),
            id_factory=self.id_factory)

    def record_publication(self, project, identifier):
        session = self.repository.open(project)
        with session.lock:
            workspace = self.read(project)
            operation = operation_in(workspace, identifier)
            if operation.publication.state == 'saved':
                return operation
            # A finalizing pre-draft becomes an authored project in the publication write itself.
            # After a crash, finish its outcome metadata; never assemble over later manual edits.
            if workspace.project is None or operation.finalization is None:
                raise RepositoryFailure('OUTCOME_UNKNOWN')
            outcome = PublicationOutcome(state='saved', intentId=operation.finalization.id,
                workspaceHash=hashlib.sha256(rich_snapshot_bytes(workspace)).hexdigest(), errorCode=None)
            def recorded(value, _data, _workspace):
                value.publication, value.state = outcome, 'published'
                return value
            return operation_in(self.update(project, identifier, recorded), identifier)

    async def finish_fallbacks(self, project, operation_id):
        for task_id in [task.id for task in operation_in(await self.view(project), operation_id).tasks]:
            workspace = await self.view(project)
            operation, data = operation_in(workspace, operation_id), owner(workspace)
            if operation.state in {'cancelled', 'fenced', 'published'}:
                return operation
            if any(result.task_id == task_id for result in operation.task_results):
                continue
            task = task_in(operation, task_id)
            if task.parent_task_id is None and children_of(operation, task_id):
                # A block with entries closes after them, below.
                continue
            if not any(value.task_id == task_id for value in operation.task_inputs):
                value, handles = self.task_input(operation, task, data)
                await asyncio.to_thread(self.update_operation, project, operation_id, lambda result, _data, _workspace:
                    capture_task_input(result, task_id, value, handles, self.wall(), id_factory=self.id_factory))
            if task.kind == 'outline_review':
                await self.finish_task(project, operation_id, task_id, None, (), (), 'empty', [])
                continue
            await self.fallback(project, operation_id, task_id, ['IMPORT_PROCESSING_STOPPED'])
        operation = operation_in(await self.view(project), operation_id)
        for task in operation.tasks:
            if (task.parent_task_id is None and children_of(operation, task.id)
                    and not any(result.task_id == task.id for result in operation.task_results)):
                await self.close_entries(project, operation_id, task.id)
        return operation_in(await self.view(project), operation_id)
