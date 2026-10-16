"""One immutable fixed payload stays in its canonical RichSyncRecord."""

from .agent_store import digest
from .background_store import BackgroundFailure
from .models.rich_mutations import RichMutation
from .project_store import encoded
from .background_limits import LIMITS


def fixed_payload(record):
    return encoded(record.model_dump(mode="json", by_alias=True, exclude={"status", "ready", "error_code"}))


def fixed_mutation(project, record):
    if not record.proposed_steps:
        return None
    return RichMutation(schemaVersion=1, projectId=project, clientMutationId="fixed_" + digest(record.id)[:40],
        actionId=record.action_id, kind="rewrite" if record.kind == "rewrite" else "reconciliation",
        capture={"sessionId": "backend", "actionId": record.action_id, "actionToken": 0,
            "dependencies": [item.model_dump(by_alias=True) for item in record.dependencies]}, steps=record.proposed_steps)


def guard_fixed_records(state, before, after):
    jobs = [*state.jobs, *[request.archived_result for request in state.requests if request.archived_result is not None]]
    bound = {job.submission.input.id for job in jobs if job.submission.input.kind == "rich_sync"}
    previous = {record.id: record for record in before.sync_records}
    latest = {record.id: record for record in after.sync_records}
    for identifier in bound:
        if identifier in previous and (identifier not in latest or previous[identifier] != latest[identifier]):
            raise BackgroundFailure("JOB_SCOPE_INVALID")
    for record in after.sync_records:
        original = previous.get(record.id)
        if (record.proposed_steps or record.id in bound) and (original is None or fixed_payload(original) != fixed_payload(record)):
            if len(fixed_payload(record)) > LIMITS.proposal_bytes:
                raise BackgroundFailure("JOB_STORAGE_FULL")


def stored_fixed_bytes(state, workspace):
    jobs = [*state.jobs, *[request.archived_result for request in state.requests if request.archived_result is not None]]
    bound = {job.submission.input.id for job in jobs if job.submission.input.kind == "rich_sync"}
    return sum(len(fixed_payload(record)) for record in workspace.sync_records if record.proposed_steps or record.id in bound)
