"""Compile a guarded history compensation through the existing batch publisher."""

from packages.resume_core.agent_edits import validate_references
from packages.resume_core.agent_store import AgentFailure, digest, identity
from packages.resume_core.models.agent import AgentEditBatch, AgentPrepareResult
from packages.resume_core.rich_mutations import apply_rich_mutation, mutation_sha256


def resolve_history(session, workspace, journal, request):
    from .project_actions import owned_projects
    from packages.resume_core.background_store import BackgroundFailure
    if len(request.operations) != 1 or session.run.scope.kind != "resume":
        raise AgentFailure("AGENT_SCOPE_INVALID")
    operation = request.operations[0]
    capture = session.book.require(operation.snapshot_id, kind="document")
    if capture.query.ids:
        raise AgentFailure("AGENT_SCOPE_INVALID")
    message = journal.request.message.casefold()
    words = ("отмен", "undo") if operation.direction == "undo" else ("повтор", "верни", "redo")
    if not any(word in message for word in words):
        raise AgentFailure("AGENT_TOOL_DENIED")
    projects = owned_projects(session)
    jobs = getattr(projects, "background_jobs", None)
    if jobs is None or not jobs.enabled:
        return session.service.publication.resolve_editor_history(workspace.project_id, session.run.owner_epoch,
            workspace.project_revision, operation.direction)
    if not workspace.mutation_replay:
        raise AgentFailure("AGENT_NO_OWNER")
    latest = workspace.mutation_replay[-1]
    if latest.resulting_revision != workspace.project_revision:
        raise AgentFailure("AGENT_STALE_READ")
    with jobs.publisher._writer(workspace.project_id), jobs.store.guard(workspace.project_id) as directory:
        state = jobs.store._read(workspace.project_id, directory)
        intent = next((item for item in [*state.intents, *state.manual_intents]
            if item.client_mutation_id == latest.client_mutation_id and item.phase == "receipt_stored"), None)
        if intent is None:
            raise AgentFailure("AGENT_NO_OWNER")
        candidate = jobs.publisher._load_candidate(state, directory, intent)
        original_kind = candidate.manual_mutation.kind if candidate.manual_mutation is not None else None
        if original_kind is None and candidate.payload is not None and candidate.payload.kind == "agent_journal":
            original_kind = AgentEditBatch.model_validate_json(jobs.artifacts.payload_unlocked(
                state, directory, candidate.payload)).mutation.kind
        if candidate.inverse is None or operation.direction == "redo" and original_kind != "undo":
            raise AgentFailure("AGENT_NO_OWNER")
        try:
            jobs.history.validate(state, directory, workspace, candidate.inverse_guards)
        except BackgroundFailure:
            raise AgentFailure("AGENT_STALE_READ") from None
        mutation = candidate.inverse.model_copy(deep=True)
    return mutation


def compile_history(workspace, run, journal, request, writer_session_id, mutation):
    operation = request.operations[0]
    batch_id = identity("batch")
    mutation.client_mutation_id = "agent_" + batch_id
    mutation.action_id = writer_session_id + ":agent:" + batch_id
    mutation.kind = operation.direction
    mutation.capture.session_id, mutation.capture.action_id = writer_session_id, mutation.action_id
    changed = apply_rich_mutation(workspace, mutation)[0]
    validate_references(changed)
    dependencies = list({digest(part): part for snapshot in journal.snapshots for part in snapshot.dependencies}.values())
    batch = AgentEditBatch(id=batch_id, runId=run.id, toolKey=request.key, ownerEpoch=run.owner_epoch,
        state="prepared", scope=run.scope, readSnapshotIds=[snapshot.id for snapshot in journal.snapshots],
        dependencies=dependencies, mutation=mutation, requestSha256=mutation_sha256(mutation),
        previewSha256=digest([step.model_dump(mode="json", by_alias=True) for step in mutation.steps]),
        affected=[], factRecordIds=[])
    return AgentPrepareResult(disposition="prepared", batchId=batch.id, affected=[],
        preview=f"{operation.direction.title()} the latest durable action through shared history."), batch
