"""Review captured native navigation without inventing a new inverse action."""

from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core import agent_limits as limits
from packages.resume_core.assistant_coverage import units
from packages.resume_core.assistant_proposals import APPLICATION_BYTES, PROJECT_BYTES, VERSION_BYTES, POLICY_REVISION, content_digest, expiry
from packages.resume_core.models.agent import AgentEditBatch
from packages.resume_core.models.assistant_history import AssistantHistoryCaptureV1
from packages.resume_core.models.assistant_proposals import AssistantCoverageDeclarationV1, AssistantProposalV1, AssistantStoredProposalV1
from packages.resume_core.rich_mutations import apply_rich_mutation, mutation_sha256

from .proposals import coverage, result


def offer_history(service, project_id, payload):
    publication = service.publication
    with service.projects.state_lock:
        now = service.leases.clock()
        publication.assistant_history = {key: value for key, value in publication.assistant_history.items() if value[0] > now}
        key = project_id, payload.request_id
        prior = publication.assistant_history.get(key)
        if prior is not None:
            if prior[1] != payload:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            return
        if len(publication.assistant_history) >= 100:
            raise AgentFailure("AGENT_PROJECT_FULL")
        size = len(payload.model_dump_json(by_alias=True).encode())
        if size > VERSION_BYTES:
            raise AgentFailure("AGENT_EDIT_LIMIT")
        if (sum(value[3] for value in publication.assistant_history.values()) + size > APPLICATION_BYTES
                or sum(value[3] for (project, _request), value in publication.assistant_history.items() if project == project_id) + size > PROJECT_BYTES):
            raise AgentFailure("AGENT_PROJECT_FULL")
        publication.offer_editor_history(project_id, payload.offer, preview_only=True)
        references = {}
        jobs = getattr(service.projects, "background_jobs", None)
        for direction in ("undo", "redo"):
            target = getattr(payload, direction + "_backend")
            mutation = getattr(payload.offer, direction)
            if target is None:
                continue
            if jobs is None or mutation is None:
                raise AgentFailure("AGENT_STALE_READ")
            state = jobs.store.load(project_id)
            inverse = next((item for item in state.inverses if item.job_id == target.job_id and item.proposal_id == target.proposal_id), None)
            if inverse is None or inverse.direction != direction or inverse.transfer_id != target.transfer_id:
                raise AgentFailure("AGENT_STALE_READ")
            references[direction] = inverse.command_ref
        publication.assistant_history[key] = now + 300, payload.model_copy(deep=True), references, size


def prepare_history(session, wrapper):
    service = getattr(session.service, "catalog_service", session.service)
    project, request = session.control.project_id, wrapper.request
    direction = request.action
    if len(wrapper.model_dump_json(by_alias=True).encode()) > limits.TOOL_BYTES:
        raise AgentFailure("AGENT_TOOL_LIMIT")
    if request.value or request.target_id is not None:
        raise AgentFailure("AGENT_ARGUMENT_INVALID")
    with service.projects.state_lock:
        session.guard()
        if direction not in {"undo", "redo"} or session.planned_task != direction or session.run.scope.kind != "resume":
            raise AgentFailure("AGENT_SCOPE_INVALID")
        _conversation, run, _journal = run_in(session.service.store.load(project), session.control.run_id)
        identifier = "proposal_" + digest([project, run.id, request.key])[:48]
        checksum = digest(wrapper)
        prior = next((value for value in service.proposals.list(project) if value.proposal.origin_run_id == run.id), None)
        if prior is not None:
            if prior.proposal.id != identifier or prior.calls.get(request.key) != checksum:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            return result(prior).model_dump(mode="json", by_alias=True)
        key = project, run.client_request_id
        retained = service.publication.assistant_history.get(key)
        if retained is None or retained[0] <= service.leases.clock():
            raise AgentFailure("AGENT_NO_OWNER")
        offered, references = retained[1:3]
        mutation = getattr(offered.offer, direction)
        if mutation is None:
            raise AgentFailure("AGENT_NOT_FOUND")
        snapshot = session.book.require(request.snapshot_id, kind="document")
        workspace = session.service.projects.read(project).model_copy(deep=True)
        if snapshot.query.ids or not session.book.validate(workspace) or workspace.project_revision != offered.offer.project_revision:
            raise AgentFailure("AGENT_STALE_READ")
        mutation = mutation.model_copy(deep=True)
        mutation.client_mutation_id = "agent_" + identifier
        candidate, duplicate = apply_rich_mutation(workspace, mutation)
        if duplicate:
            raise AgentFailure("AGENT_STALE_READ")
        history = AssistantHistoryCaptureV1(direction=direction, requestId=run.client_request_id,
            actionId=mutation.action_id, sessionId=mutation.capture.session_id,
            backend=getattr(offered, direction + "_backend"), previousRef=references.get(direction))
        declared = [AssistantCoverageDeclarationV1(unitId=key, reason="Сохранено при навигации по выбранному действию истории.") for key in units(workspace, run.scope)]
        ledger, changes = coverage(session, workspace, candidate, run.scope, declared)
        if any(item.state == "unresolved" for item in ledger):
            raise AgentFailure("AGENT_STALE_READ")
        batch = AgentEditBatch(id="batch_" + digest(identifier)[:40], runId=run.id, toolKey=request.key, ownerEpoch=run.owner_epoch,
            state="prepared", scope=run.scope, readSnapshotIds=[request.snapshot_id], dependencies=snapshot.dependencies,
            mutation=mutation, requestSha256=mutation_sha256(mutation), previewSha256=digest([step.model_dump(mode="json", by_alias=True) for step in mutation.steps]),
            affected=[], factRecordIds=[])
        created = service.store.clock()
        proposal = AssistantProposalV1(id=identifier, version=1, projectId=project, lineage=digest([project, workspace.created_at]),
            editorFamily="ordinary", originRequestId=run.client_request_id, originRunId=run.id, taskId=direction,
            state="ready", createdAt=created, expiresAt=expiry(created), beforeSha256=content_digest(workspace),
            contentSha256=content_digest(candidate), coverage=ledger, changes=changes, operationCount=1,
            reason=("Отменить" if direction == "undo" else "Повторить") + " показанное действие истории. Это навигация по исходному действию, а не новая правка.")
        value = AssistantStoredProposalV1(policyRevision=POLICY_REVISION, history=history, proposal=proposal,
            accountEpoch=run.connection_epoch, accessRevision=run.access_revision, scope=run.scope,
            dependencies=snapshot.dependencies, baseline=workspace, candidate=candidate, batch=batch,
            operations=[{"kind": "history", "snapshotId": request.snapshot_id, "direction": direction}],
            snapshotIds=[request.snapshot_id], calls={request.key: checksum}, unchanged=declared, noChange=False)
        stored = service.proposals.update(project, lambda _values: value)
        service.publication.assistant_history.pop(key, None)
        return result(stored).model_dump(mode="json", by_alias=True)
