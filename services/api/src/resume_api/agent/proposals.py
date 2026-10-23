"""Assemble an unpublished candidate without borrowing live write authority."""

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_edits import Scope, compile_batch
from packages.resume_core.agent_store import AgentFailure, digest, identity, run_in
from packages.resume_core.assistant_proposals import content_digest, expiry
from packages.resume_core.models.agent import AgentPrepareRequest, AgentQuery, AgentQueryDependency
from packages.resume_core.models.assistant_proposals import (
    AssistantChangeV1, AssistantCoverageV1, AssistantProposalResultV1, AssistantProposalV1, AssistantStoredProposalV1,
)
from packages.resume_core.rich_fields import inline_groups
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation

from .capabilities import BY_ID
from .context import current_dependencies, query_fingerprint


def units(workspace, scope, *, allowed=None):
    allowed = allowed or Scope(workspace, scope)
    result = {}
    for block in workspace.project.document.blocks():
        if not allowed.whole and block.id not in allowed.complete and not any(key[0] == block.id for key in allowed.ranges):
            continue
        result["block:" + block.id] = (block.id, block.model_dump(mode="json", by_alias=True, exclude={"children"}))
        for container, spans in inline_groups(block):
            result[f"field:{block.id}:{container}"] = (block.id, [span.model_dump(mode="json", by_alias=True) for span in spans])
    return result


def coverage(session, baseline, candidate, scope, unchanged):
    allowed = Scope(baseline, scope)
    before, after = units(baseline, scope, allowed=allowed), units(candidate, scope, allowed=allowed)
    declared = {item.unit_id: item.reason for item in unchanged}
    if len(declared) != len(unchanged) or declared.keys() - before.keys():
        raise AgentFailure("AGENT_SCOPE_INVALID")
    read, cells = set(), set()
    for snapshot in session.book.by_snapshot:
        try:
            capture = session.book.require(snapshot, kind="document")
            read.update(block["id"] for block in capture.payload["blocks"])
            cells.update(part["cell"].id for part in capture.payload["cells"])
        except AgentFailure:
            continue
    result, changes = [], []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        changed = digest(old[1] if old else None) != digest(new[1] if new else None)
        was_read = old is None or old[0] in read or key.startswith("field:") and key.rsplit(":", 1)[-1] in cells
        state = "changed" if changed and was_read else "unchanged" if not changed and was_read and key in declared else "unresolved"
        reason = "Изменение вычислено из подготовленного документа." if state == "changed" else declared.get(key, "Нужно полное чтение и явный учёт этой части.")
        result.append(AssistantCoverageV1(unitId=key, state=state, reason=reason, read=was_read))
        if changed:
            changes.append(AssistantChangeV1(unitId=key, before=display(old[1]) if old else "",
                after=display(new[1]) if new else "", effect="wording" if key.startswith("field:") else "structure"))
    return result, changes


def display(value):
    if isinstance(value, list):
        return "".join(part.get("text", "") for part in value)
    if isinstance(value, dict):
        return str(value.get("type", "")) + ": " + str(value.get("id", ""))
    return str(value)


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


def compile_candidate(baseline, run, journal, command, book):
    try:
        _, batch = compile_batch(baseline, run, journal, command, book, "assistant_draft")
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
                current = AssistantStoredProposalV1(proposal=proposal, accountEpoch=run.connection_epoch,
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
            batch, candidate = compile_candidate(current.baseline, run, journal, command, session.book)
            current.batch, current.candidate = batch, candidate
            current.calls[request.key] = request_hash
            current.proposal.operation_count = len(current.operations)
            current.proposal.content_sha256 = content_digest(candidate)
            current.proposal.coverage, current.proposal.changes = coverage(session, current.baseline, candidate, current.scope, current.unchanged)
            if batch:
                current.dependencies = list({digest(item): item for item in [*current.dependencies, *batch.dependencies]}.values())
            if request.phase == "finalize":
                complete = all(unit.read and unit.state != "unresolved" for unit in current.proposal.coverage)
                current.no_change = batch is None and complete
                current.proposal.state = "invalid" if current.no_change else "ready" if complete and batch else "incomplete"
                current.proposal.reason = "Изменений нет. Документ и история не изменены." if current.no_change else (
                    "Вариант готов к просмотру. Применение требует отдельного действия пользователя." if current.proposal.state == "ready" else
                    "Полный вариант не завершён. Черновик сохранён; применение недоступно.")
            return current
        return result(service.proposals.update(project, extend))
