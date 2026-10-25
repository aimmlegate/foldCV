"""Continue a private draft through existing admission, journals and bounded reads."""

import hashlib
import json
from types import SimpleNamespace

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure, digest, identity, run_in, journal_request
from packages.resume_core.assistant_proposals import POLICY_REVISION, content_digest, expiry
from packages.resume_core.models.agent import AgentPrepareRequest, AgentReadSnapshot
from packages.resume_core.models.assistant_continuation import (
    AssistantContinuationOptionV1, AssistantContinuationOptionsV1, AssistantDraftPageV1,
)
from packages.resume_core.models.assistant_proposals import AssistantProposalRequestV1
from packages.resume_core.models.assistant_read_proof import AssistantReadGroupV1, AssistantContinuationOriginV1

from .approval_journal import origin_journal
from .context import ReadBook, canonical_capture, current_dependencies, json_text
from .proposals import compile_candidate, coverage, origin_status

TASKS = {"rewrite_resume", "restructure", "correct_facts", "format_document"}


def root_service(service):
    return getattr(service, "catalog_service", service)


def current_draft(service, project, run_id):
    return next((value for value in service.proposals.list(project)
        if value.proposal.origin_run_id == run_id and getattr(value, "continuation", None) is not None), None)


def capture_groups(book, journal):
    stored = {snapshot.id: snapshot for snapshot in journal.snapshots}
    groups = []
    seen = set()
    for capture in book.captures.values():
        if not capture.complete or capture.query.kind == "history":
            continue
        if capture.carried is not None:
            group = capture.carried.model_copy(deep=True)
        else:
            snapshots = [stored[item] for item in capture.snapshots if item in stored]
            if len(snapshots) != len(capture.snapshots) or not snapshots:
                raise AgentFailure("AGENT_STALE_READ")
            group = AssistantReadGroupV1(query=capture.query, snapshots=snapshots)
        key = digest(group)
        if key not in seen:
            groups.append(group); seen.add(key)
    if len(groups) > limits.TOOL_CALLS:
        raise AgentFailure("AGENT_TOOL_LIMIT")
    return groups


def groups_for(service, value):
    if value.read_groups:
        return value.read_groups
    # Older private drafts can use the same server-recorded cursor completion proof.
    _, _, journal = run_in(origin_journal(service, value).load(value.proposal.project_id), value.proposal.origin_run_id)
    grouped = {}
    for snapshot in journal.snapshots:
        dependency = next((item for item in snapshot.dependencies if item.kind == "query"), None)
        if dependency is None or dependency.query.kind == "history":
            continue
        key = digest(dependency.query)
        grouped.setdefault(key, (dependency.query, []))[1].append(snapshot)
    return [AssistantReadGroupV1(query=query, snapshots=snapshots) for query, snapshots in grouped.values()
        if snapshots and not snapshots[-1].truncated]


def populate(book, value):
    for group in value.read_groups:
        if group.current_alias is None:
            raise AgentFailure("AGENT_STALE_READ")
        capture = canonical_capture(value.baseline, group.query)
        if not all(current_dependencies(value.baseline, item.dependencies) for item in group.snapshots):
            raise AgentFailure("AGENT_STALE_READ")
        capture.complete, capture.snapshots, capture.carried = True, [group.current_alias], group
        book.captures['carry:' + group.current_alias] = capture
        book.by_snapshot[group.current_alias] = capture


def restore_book(book, run, journal):
    service = root_service(book.service)
    if not getattr(service, 'assistant_protocol_enabled', False):
        return None
    value = current_draft(service, run.project_id, run.id)
    if value is None:
        return None
    if (value.continuation.journal_sha256 != digest(journal.request) or value.baseline is None
            or content_digest(book.service.projects.read(run.project_id)) != value.proposal.before_sha256
            or not current_dependencies(book.service.projects.read(run.project_id), value.dependencies)):
        raise AgentFailure("AGENT_STALE_READ")
    populate(book, value)
    return {"proposalId": value.proposal.id, "version": value.proposal.version, "taskId": value.proposal.task_id,
        "operationCount": value.proposal.operation_count,
        "readProof": "Carried server proof of complete reads from the same unchanged canonical baseline.",
        "readDraft": {"tool": "get_project_resources", "draft": {"protocolVersion": 1,
            "proposalId": value.proposal.id, "version": value.proposal.version, "cursor": None}}}


def identity_request(value):
    p = value.proposal
    return AssistantProposalRequestV1(protocolVersion=1, proposalId=p.id, version=p.version, contentSha256=p.content_sha256)


def eligible(service, project, target, *, allow_edits=True, allow_web=True):
    from .capabilities import catalog
    value = service.approval.value(project, target)
    if (getattr(value, 'record_kind', None) is not None or value.history is not None
            or value.proposal.task_id not in TASKS or value.proposal.state != 'incomplete'
            or value.baseline is None or value.candidate is None or value.policy_revision != POLICY_REVISION):
        raise AgentFailure('AGENT_TOOL_DENIED')
    retained = service.proposals.list(project)
    versions = [item.proposal.version for item in retained if item.proposal.id == value.proposal.id]
    if len(retained) >= 20:
        raise AgentFailure('AGENT_PROJECT_FULL')
    if value.proposal.version != max(versions) or value.proposal.version >= 20:
        raise AgentFailure('AGENT_EDIT_LIMIT')
    if not origin_status(service, value)[0]:
        raise AgentFailure('AGENT_BUSY')
    workspace = service.projects.read(project)
    connection = service.connection()
    if value.account_epoch != connection.epoch or connection.reason in {'AGENT_AUTH_REQUIRED', 'AGENT_CONNECTION_CHANGED'}:
        raise AgentFailure('AGENT_CONNECTION_CHANGED')
    if (digest([workspace.project_id, workspace.created_at]) != value.proposal.lineage
            or content_digest(workspace) != value.proposal.before_sha256
            or not current_dependencies(workspace, value.dependencies)):
        raise AgentFailure('AGENT_STALE_READ')
    task = next(item for item in catalog(service, project, allow_edits=allow_edits, allow_web=allow_web).tasks
        if item.id == value.proposal.task_id)
    if task.generation.state != 'available':
        error = AgentFailure(task.generation.reason_code or 'AGENT_TOOL_DENIED')
        error.capacity_reason = task.generation.remedy
        raise error
    if not groups_for(service, value):
        raise AgentFailure('AGENT_STALE_READ')
    return value


def options(service, project, *, allow_edits=True, allow_web=True):
    from .capabilities import availability
    result = []
    for value in service.proposals.list(project):
        if value.proposal.state != 'incomplete' or getattr(value, 'record_kind', None) is not None:
            continue
        request = None
        try:
            eligible(service, project, identity_request(value), allow_edits=allow_edits, allow_web=allow_web)
            _, _, journal = run_in(origin_journal(service, value).load(project), value.proposal.origin_run_id)
            request = journal.request
            stage = availability()
        except AgentFailure as error:
            stage = availability('temporarily_unavailable', error.code,
                getattr(error, 'capacity_reason', None) or 'Черновик сохранён для просмотра. Если документ или лимиты изменились, выберите меньшую задачу или подготовьте новый вариант.')
        result.append(AssistantContinuationOptionV1(proposal=identity_request(value), availability=stage, request=request,
            operationsRemaining=max(0, limits.EDIT_OPERATIONS-value.proposal.operation_count),
            versionsRemaining=max(0, min(20-value.proposal.version, 20-len(service.proposals.list(project))))))
    return AssistantContinuationOptionsV1(projectId=project, options=result)


def same_request(old, request):
    if any(getattr(old, key) != getattr(request, key) for key in ('conversation_id', 'message', 'scope', 'selection_context')):
        raise AgentFailure('AGENT_SCOPE_INVALID')


def existing(service, project, target, request):
    for value in service.proposals.list(project):
        if value.proposal.origin_request_id != request.client_request_id or getattr(value, "continuation", None) is None:
            continue
        proof = value.continuation
        if ((proof.proposal_id, proof.version, proof.content_sha256) != (target.proposal_id, target.version, target.content_sha256)
                or proof.request_sha256 != digest(journal_request(request))):
            raise AgentFailure('AGENT_IDEMPOTENCY_CONFLICT')
        return value
    return None


def clone(service, value, store, run, journal, *, client_request=None):
    if run.connection_epoch != value.account_epoch:
        raise AgentFailure('AGENT_CONNECTION_CHANGED')
    current = value.model_copy(deep=True)
    p = current.proposal
    p.version += 1
    p.origin_run_id, p.origin_request_id = run.id, client_request.client_request_id if client_request is not None else run.client_request_id
    p.created_at, p.expires_at = service.store.clock(), expiry(service.store.clock())
    p.state, p.reason = 'building', 'Продолжаем сохранённый черновик. Документ не изменён; применение недоступно.'
    current.continuation = AssistantContinuationOriginV1(proposalId=value.proposal.id, version=value.proposal.version,
        contentSha256=value.proposal.content_sha256, requestSha256=digest(journal_request(client_request)) if client_request is not None else digest(journal.request),
        journalSha256=digest(journal.request))
    current.approval, current.revoked_acceptances, current.calls = None, [], {}
    mapping, aliases, groups = {}, [], []
    for old in groups_for(service, value):
        group = old.model_copy(deep=True)
        alias = identity('carried_read')
        for identifier in [*(item.id for item in group.snapshots), *group.aliases]:
            mapping[identifier] = alias
        group.current_alias = alias
        group.aliases.append(alias)
        capture = canonical_capture(current.baseline, group.query)
        if not all(current_dependencies(current.baseline, item.dependencies) for item in group.snapshots):
            raise AgentFailure('AGENT_STALE_READ')
        aliases.append(AgentReadSnapshot(id=alias, runId=run.id, contentSha256=hashlib.sha256(json_text(capture.payload).encode()).hexdigest(),
            dependencies=capture.dependencies, truncated=False, nextCursor=None))
        groups.append(group)
    if len(aliases) >= limits.TOOL_CALLS:
        raise AgentFailure('AGENT_TOOL_LIMIT')
    def remap(data):
        if isinstance(data, dict):
            return {key: mapping.get(part, part) if key == 'snapshotId' else remap(part) for key, part in data.items()}
        return [remap(part) for part in data] if isinstance(data, list) else data
    from packages.resume_core.models.agent import AgentEditOperation
    from pydantic import TypeAdapter
    current.operations = [TypeAdapter(AgentEditOperation).validate_python(remap(op.model_dump(by_alias=True))) for op in current.operations]
    current.read_groups, current.snapshot_ids = groups, [item.id for item in aliases]
    journal = journal.model_copy(deep=True); journal.snapshots.extend(aliases)
    book = ReadBook(SimpleNamespace(projects=service.projects), SimpleNamespace())
    populate(book, current)
    command = AgentPrepareRequest(key=p.id, snapshotIds=current.snapshot_ids, operations=current.operations)
    current.batch, current.candidate = compile_candidate(current.baseline, run, journal, command, book, p.task_id)
    p.content_sha256 = content_digest(current.candidate)
    p.coverage, p.changes = coverage(SimpleNamespace(book=book), current.baseline, current.candidate, current.scope,
        current.unchanged, current.operations)
    def record(state):
        stored = run_in(state, run.id)[2]
        if stored.snapshots:
            raise AgentFailure('AGENT_IDEMPOTENCY_CONFLICT')
        stored.snapshots = aliases
    store.update(run.project_id, record)
    return service.proposals.update(run.project_id, lambda _values: current)


def submit_run(service, project, payload):
    with service.projects.state_lock:
        prior = existing(service, project, payload.proposal, payload.request)
        if prior is not None:
            return run_in(service.store.load(project), prior.proposal.origin_run_id)[1], False
        value = eligible(service, project, payload.proposal, allow_edits=payload.request.allow_edits, allow_web=payload.request.allow_web)
        _, _, old = run_in(origin_journal(service, value).load(project), value.proposal.origin_run_id)
        same_request(old.request, payload.request)
        if service.store.find_request(project, payload.request) is not None:
            raise AgentFailure('AGENT_IDEMPOTENCY_CONFLICT')
        run, created = service.submit(project, payload.request)
        try:
            journal = run_in(service.store.load(project), run.id)[2]
            clone(service, value, service.store, run, journal)
        except Exception:
            service.store.finish(project, run.id, 'failed', error='AGENT_SAVE_FAILED')
            raise
        return run, created


async def submit_job(service, jobs, project, payload):
    logical = payload.request.request
    with service.projects.state_lock:
        prior = existing(service, project, payload.proposal, logical)
        if prior is not None:
            job = jobs.store.read(project, prior.proposal.origin_run_id)
            if (job.submission.identity.lineage, job.submission.identity.request_epoch) != (payload.request.lineage, payload.request.request_epoch):
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            return job, False
        value = eligible(service, project, payload.proposal, allow_edits=logical.allow_edits, allow_web=logical.allow_web)
        _, _, old = run_in(origin_journal(service, value).load(project), value.proposal.origin_run_id)
        same_request(old.request, logical)
    def prepared(job):
        value = eligible(service, project, payload.proposal, allow_edits=logical.allow_edits, allow_web=logical.allow_web)
        store = jobs.artifacts.bound(project, job.id)
        _, run, journal = run_in(store.load(project), job.id)
        clone(service, value, store, run, journal, client_request=logical)
    job, created = await jobs.submit(project, payload.request, prepare=prepared)
    if not created and existing(service, project, payload.proposal, logical) is None:
        raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
    return job, created


def draft_page(session, request):
    service = root_service(session.service)
    value = current_draft(service, session.control.project_id, session.control.run_id)
    if value is None or (value.proposal.id, value.proposal.version) != (request.proposal_id, request.version):
        raise AgentFailure('AGENT_TOOL_DENIED')
    text = json_text({'operations': value.operations, 'coverage': value.proposal.coverage, 'changes': value.proposal.changes})
    checksum, offset = hashlib.sha256(text.encode()).hexdigest(), 0
    if request.cursor is not None:
        old = session.draft_cursors.pop(request.cursor, None)
        if old is None or old[0] != checksum:
            raise AgentFailure('AGENT_STALE_READ')
        offset = old[1]
    token = identity('draft_page')
    def page(size):
        end = offset+size
        return AssistantDraftPageV1(content=text[offset:end], contentSha256=checksum, offset=offset,
            totalCharacters=len(text), nextCursor=token if end<len(text) else None, complete=end==len(text))
    lo, hi = 0, min(len(text)-offset, limits.PAGE_BYTES)
    while lo<hi:
        mid=(lo+hi+1)//2
        if len(json_text(page(mid)).encode())<=limits.PAGE_BYTES:
            lo=mid
        else:
            hi=mid-1
    result=page(lo)
    if result.next_cursor is not None:
        session.draft_cursors[token]=(checksum,offset+lo)
    return result
