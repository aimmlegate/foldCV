"""Assemble an unpublished candidate without borrowing live write authority."""

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_edits import Scope, compile_batch
from packages.resume_core.agent_store import AgentFailure, digest, identity, run_in
from packages.resume_core.assistant_proposals import POLICY_REVISION, content_digest, expiry, proposal_before_digest
from packages.resume_core.assistant_coverage import comparison, units
from packages.resume_core.models.agent import AgentPrepareRequest, AgentQuery, AgentQueryDependency, WholeResumeScope
from packages.resume_core.models.assistant_proposals import (
    AssistantChangeV1, AssistantCoverageV1, AssistantProposalResultV1, AssistantProposalV1, AssistantStoredProposalV1,
)
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation

from .capabilities import BY_ID
from .context import current_dependencies, query_fingerprint


def coverage(session, baseline, candidate, scope, unchanged, operations=()):
    allowed = Scope(baseline, scope)
    new_ids = {block.id for block in candidate.project.document.blocks()} - {block.id for block in baseline.project.document.blocks()}
    before, after = units(baseline, scope, allowed=allowed), units(candidate, scope, allowed=allowed, new_ids=new_ids)
    declared = {item.unit_id: item.reason for item in unchanged}
    if len(declared) != len(unchanged) or declared.keys() - before.keys():
        raise AgentFailure("AGENT_SCOPE_INVALID")
    read, cells, facts, context, facts_collection = set(), set(), set(), False, False
    for snapshot in session.book.by_snapshot:
        try:
            capture = session.book.require(snapshot)
            if capture.query.kind == "context":
                context = True
            elif capture.query.kind == "facts":
                facts.update(record.id for record in capture.payload["records"])
                facts_collection |= not capture.query.ids
            elif capture.query.kind == "document":
                read.update(block["id"] for block in capture.payload["blocks"])
                cells.update(part["cell"].id for part in capture.payload["cells"])
                cells.update(cell["id"] for block in capture.payload["blocks"] if block["type"] == "table"
                    for row in block["content"]["rows"] for cell in row["cells"])
        except AgentFailure:
            continue
    result = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        unit = old or new
        changed = digest(old.value if old else None) != digest(new.value if new else None)
        was_read = old is None or (context if unit.reader == "context" else facts_collection if unit.reader == "facts_collection" else
            unit.reader in facts if unit.kind == "fact" else unit.reader in read | cells)
        state = "changed" if changed and was_read else "unchanged" if not changed and was_read and key in declared else "unresolved"
        reason = "Изменение вычислено из подготовленного документа." if state == "changed" else declared.get(key, "Нужно полное чтение и явный учёт этой части.")
        result.append(AssistantCoverageV1(unitId=key, state=state, reason=reason, read=was_read))
    whole = WholeResumeScope(kind="resume")
    changes = comparison(units(baseline, whole), units(candidate, whole))
    if any(change.effect == "fact" for change in changes):
        for operation in operations:
            if operation.kind not in {"update_fact", "create_fact", "delete_fact"}:
                continue
            evidence = operation.evidence if operation.kind == "update_fact" else [operation.correction]
            descriptions = []
            for item in evidence:
                if item.kind == "user_correction":
                    descriptions.append("Сообщение пользователя: «" + item.quote + "».")
                elif item.kind == "source":
                    source = next(source for source in baseline.project.sources if source.id == item.source_id)
                    unit = next(unit for unit in source.units if unit.id == item.unit_id)
                    descriptions.append("Исходник «" + source.original_name + "», фрагмент " + item.unit_id + ":\n" + unit.text)
                else:
                    descriptions.append("Ссылка на текущую запись фактов " + item.record_id + ".")
            descriptions.append("Ссылки указывают поддержку коррекции; сами по себе они не подтверждают достоверность.")
            changes.append(AssistantChangeV1(unitId="support:" + digest(operation), before="", after="\n".join(descriptions), effect="fact"))
    return result, changes


def result(value):
    proposal = value.proposal
    pending = [unit for unit in proposal.coverage if unit.state == "unresolved"]
    visible = pending or proposal.coverage
    return AssistantProposalResultV1(disposition="no_change" if value.no_change else
        "draft_ready" if proposal.state == "ready" else "incomplete" if proposal.state == "incomplete" else "building",
        proposalId=None if value.no_change else proposal.id, version=proposal.version, contentSha256=proposal.content_sha256,
        changedUnits=sum(unit.state == "changed" for unit in proposal.coverage),
        unresolvedUnits=sum(unit.state == "unresolved" for unit in proposal.coverage),
        coverage=visible[:20], coverageTruncated=len(visible) > 20, unitCount=len(proposal.coverage),
        reason=proposal.reason or "Черновик сохранён для просмотра. Документ не изменён.")


def review(service, project_id):
    with service.projects.state_lock:
        service.approval.reconcile_reviews(project_id)
        service.action_approval.reconcile_reviews(project_id)
        values = service.proposals.list(project_id)
        if (not any(value.proposal.state == "ready" for value in values)
                or project_id in service.projects.agent_recovery_fences | service.projects.catalog_recovery_fences):
            return values
        workspace = service.projects.storage.read_committed(project_id)[0]
        archived = service.projects.catalog.get(project_id).archived
        for value in values:
            if value.proposal.state != "ready" or (proposal_before_digest(value, workspace, archived=archived) == value.proposal.before_sha256
                    and current_dependencies(workspace, value.dependencies)):
                continue
            def check(items):
                current = next(item for item in items if item.proposal.id == value.proposal.id and item.proposal.version == value.proposal.version)
                workspace = service.projects.storage._read_committed_unlocked(project_id)[0]
                if current.proposal.state == "ready" and (proposal_before_digest(current, workspace, archived=archived) != current.proposal.before_sha256
                        or not current_dependencies(workspace, current.dependencies)):
                    current.proposal.state = "stale"
                    current.proposal.reason = "Документ или его источники изменились. Текущие правки сохранены; подготовьте новый вариант для просмотра."
                return current
            service.proposals.update(project_id, check)
        return service.proposals.list(project_id)


def origin_status(service, value):
    from packages.resume_core.background_store import BackgroundFailure, TERMINAL_EXECUTION
    try:
        _, run, _ = run_in(service.store.load(value.proposal.project_id), value.proposal.origin_run_id)
        return (run.state in {"completed", "failed", "cancelled", "interrupted"} and (run.error is None or run.error.code != "AGENT_CLEANUP_FAILED"),
            run.state == "cancelled" or run.error is not None and run.error.code == "AGENT_CANCELLED")
    except AgentFailure as error:
        if error.code != "AGENT_NOT_FOUND":
            raise
    jobs = getattr(service.projects, "background_jobs", None)
    if jobs is not None:
        try:
            state = jobs.store.load(value.proposal.project_id)
            job = next((item for item in state.jobs if item.id == value.proposal.origin_run_id and item.submission.kind == "agent"), None)
            return (job is not None and job.execution in TERMINAL_EXECUTION and (job.error is None or job.error.code != "CLEANUP_FAILED"),
                job is not None and (job.execution == "cancelled" or job.error is not None and job.error.code == "CANCELLED"))
        except BackgroundFailure:
            return False, True
    return False, True


def generation_finished(service, value):
    return origin_status(service, value)[0]


def review_view(service, value, tasks):
    from packages.resume_core.models.assistant_actions import AssistantCapabilityReviewV1
    from .capabilities import availability
    stage = next(task.apply for task in tasks.tasks if task.id == value.proposal.task_id)
    finished, revoked = origin_status(service, value)
    if value.proposal.state not in {"ready", "failed_before_commit"}:
        stage = availability("temporarily_unavailable", "AGENT_STALE_READ", value.proposal.reason)
    elif value.proposal.state == "failed_before_commit" and (value.approval is None or value.approval.phase != "cancelled"
            or value.baseline is None or value.candidate is None and getattr(value, "record_kind", None) != "action_v1"
            or proposal_before_digest(value, service.projects.read(value.proposal.project_id),
                archived=service.projects.catalog.get(value.proposal.project_id).archived) != value.proposal.before_sha256
            or not current_dependencies(service.projects.read(value.proposal.project_id), value.dependencies)):
        stage = availability("temporarily_unavailable", "AGENT_STALE_READ", "Документ изменился. Подготовьте новый вариант для просмотра.")
    elif revoked:
        stage = availability("permission_disabled", "AGENT_CANCELLED", "Задача была остановлена. Подготовьте новый вариант.")
    elif not finished:
        stage = availability("temporarily_unavailable", "AGENT_BUSY", "Дождитесь завершения подготовки. Документ не изменён.")
    elif value.account_epoch != service.connection().epoch:
        stage = availability("permission_disabled", "AGENT_CONNECTION_CHANGED", "Вернитесь к исходной учётной записи и подготовьте новый вариант.")
    elif value.history is not None and (service.leases.leases.get(value.proposal.project_id) is None
            or service.leases.leases[value.proposal.project_id].session_id != value.history.session_id):
        stage = availability("temporarily_unavailable", "AGENT_NO_OWNER", "Откройте окно с исходным действием истории или подготовьте новый вариант.")
    return AssistantCapabilityReviewV1(proposal=value.proposal, apply=stage, generationFinished=finished,
        action=value.action.preview if getattr(value, "action", None) is not None else None)


def compile_candidate(baseline, run, journal, command, book, task_id):
    try:
        policy = {"rewrite_resume": "wording", "restructure": "structure", "correct_facts": "facts", "format_document": "format"}[task_id]
        _, batch = compile_batch(baseline, run, journal, command, book, "assistant_draft", assistant_policy=policy)
        candidate = apply_rich_mutation(baseline, batch.mutation)[0] if batch else baseline.model_copy(deep=True)
        return batch, candidate
    except AgentFailure:
        raise
    except (RichMutationFailure, ValueError, KeyError, AttributeError):
        raise AgentFailure("AGENT_EDIT_INVALID") from None


def assemble(session, request):
    service = getattr(session.service, "catalog_service", session.service)
    if not getattr(service, "assistant_protocol_enabled", False) or request.task_id != session.planned_task:
        raise AgentFailure("AGENT_TOOL_DENIED")
    if BY_ID[request.task_id].effect != "proposal" or request.task_id in {"undo", "redo"}:
        raise AgentFailure("AGENT_TOOL_DENIED")
    if len(request.model_dump_json(by_alias=True).encode()) > limits.TOOL_BYTES:
        raise AgentFailure("AGENT_TOOL_LIMIT")
    project = session.control.project_id
    with service.projects.state_lock:
        session.guard()
        workspace = session.service.projects.read(project)
        if workspace.schema_version != 6 or not session.book.validate(workspace):
            raise AgentFailure("AGENT_STALE_READ")
        _, run, journal = run_in(session.service.store.load(project), session.control.run_id)
        request_hash = digest(request)
        def extend(values):
            current = next((value for value in values if value.proposal.id == request.proposal_id and value.proposal.version == request.version), None) if request.proposal_id else next(
                (value for value in values if value.proposal.origin_run_id == run.id), None)
            if current is None:
                if request.proposal_id is not None or request.version != 1:
                    raise AgentFailure("AGENT_NOT_FOUND")
                before = content_digest(workspace)
                proposal = AssistantProposalV1(id=identity("proposal"), version=1, projectId=project,
                    lineage=digest([workspace.project_id, workspace.created_at]), editorFamily="ordinary",
                    originRequestId=run.client_request_id, originRunId=run.id, taskId=request.task_id, state="building",
                    createdAt=service.store.clock(), expiresAt=expiry(service.store.clock()), contentSha256=before,
                    beforeSha256=before, coverage=[], changes=[], operationCount=0, reason=None)
                query = AgentQuery(kind="resources")
                current = AssistantStoredProposalV1(policyRevision=POLICY_REVISION, proposal=proposal, accountEpoch=run.connection_epoch,
                    accessRevision=run.access_revision, scope=run.scope, dependencies=[AgentQueryDependency(kind="query",
                        query=query, fingerprint=query_fingerprint(workspace, query))], baseline=workspace.model_copy(deep=True),
                    candidate=workspace.model_copy(deep=True), batch=None, operations=[], snapshotIds=[], calls={}, unchanged=[], noChange=False)
            if current.proposal.origin_run_id != run.id or current.proposal.task_id != request.task_id or current.account_epoch != run.connection_epoch:
                raise AgentFailure("AGENT_TOOL_DENIED")
            if request.key in current.calls:
                if current.calls[request.key] != request_hash:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return current
            if current.proposal.state != "building" or current.no_change:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            committed = service.projects.storage._read_committed_unlocked(project)[0]
            if content_digest(committed) != current.proposal.before_sha256 or not current_dependencies(committed, current.dependencies):
                raise AgentFailure("AGENT_STALE_READ")
            current.operations.extend(request.operations)
            current.snapshot_ids = list(dict.fromkeys([*current.snapshot_ids, *request.snapshot_ids]))
            declared = {item.unit_id: item for item in current.unchanged}
            for item in request.unchanged:
                if item.unit_id in declared and declared[item.unit_id] != item:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                declared[item.unit_id] = item
            current.unchanged = list(declared.values())
            if len(current.operations) > limits.EDIT_OPERATIONS or len(current.snapshot_ids) > limits.TOOL_CALLS or len(current.calls) >= limits.TOOL_CALLS:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            if len(current.unchanged) > 2000:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            command = AgentPrepareRequest(key=current.proposal.id, snapshotIds=current.snapshot_ids, operations=current.operations)
            batch, candidate = compile_candidate(current.baseline, run, journal, command, session.book, request.task_id)
            current.batch, current.candidate = batch, candidate
            current.calls[request.key] = request_hash
            current.proposal.operation_count = len(current.operations)
            current.proposal.content_sha256 = content_digest(candidate)
            current.proposal.coverage, current.proposal.changes = coverage(session, current.baseline, candidate, current.scope, current.unchanged, current.operations)
            if batch:
                current.dependencies = list({digest(item): item for item in [*current.dependencies, *batch.dependencies]}.values())
            if request.phase == "finalize":
                complete = all(unit.read and unit.state != "unresolved" for unit in current.proposal.coverage)
                current.no_change = batch is None and complete
                current.proposal.state = "invalid" if current.no_change else "ready" if complete and batch else "incomplete"
                current.proposal.reason = "Изменений нет. Документ и история не изменены." if current.no_change else (
                    "Вариант готов к просмотру. Применение требует отдельного действия пользователя." if current.proposal.state == "ready" else
                    "Полный вариант не завершён. Черновик сохранён; применение недоступно.")
                gaps = sum(not source.units or bool(source.warnings or source.warning_details) for source in current.baseline.project.sources)
                if gaps:
                    current.proposal.reason += f" В {gaps} исходниках есть пропуски извлечения. Вариант охватывает текущий документ и не заполняет эти пропуски."
            return current
        return result(service.proposals.update(project, extend))
