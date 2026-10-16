"""Small synthetic captures shared by contract and protocol tests."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from packages.resume_core.models.rich_workspace import WorkspaceV6

HASH = "a" * 64
TIME = "2026-10-16T12:00:00Z"


def stamp(key="block-one", generation=1):
    return {"kind": "entity", "key": key, "generation": generation, "fingerprint": HASH}


def guard():
    return {"schemaVersion": 1, "reads": [stamp()], "writes": [stamp()]}


def submission():
    return {"schemaVersion": 1, "identity": {"projectId": "project-one", "lineage": "lineage-one",
        "requestEpoch": 1, "requestId": "request-one"}, "payloadSha256": HASH, "kind": "agent",
        "schedulingClass": "background", "input": {"kind": "agent_journal", "id": "request-one", "sha256": HASH},
        "models": [{"stage": "agent", "model": "synthetic-model", "configSha256": HASH}],
        "accountGeneration": 1, "tools": ["get_resume_context", "prepare_edit_batch", "apply_edit_batch"],
        "allowEdits": True, "allowWeb": False, "scope": {"kind": "resume"}, "guards": guard(), "submittedAt": TIME}


def snapshot():
    return {"schemaVersion": 1, "id": "job-one", "submission": submission(), "execution": "completed",
        "publication": "waiting_for_sync", "executionGeneration": 1, "attempts": [], "eventCursor": 1,
        "proposalId": "proposal-one", "receipt": None, "error": None, "publicationError": None,
        "undoExpired": False, "assetPinsSha256": None, "createdAt": TIME, "updatedAt": TIME}


def examples():
    project = WorkspaceV6.model_validate_json((Path(__file__).resolve().parents[2] / "tests/fixtures/rich_workspace.json").read_text()).model_dump(mode="json", by_alias=True)["project"]
    result = {
        "background_submission_v1": submission(), "background_snapshot_v1": snapshot(),
        "background_scope_guard_v1": guard(),
        "background_proposal_v1": {"schemaVersion": 1, "id": "proposal-one", "jobId": "job-one",
            "projectId": "project-one", "lineage": "lineage-one", "accountGeneration": 1, "executionGeneration": 1,
            "turnId": "turn-one", "payload": {"kind": "agent_journal", "conversationId": "conversation-one",
                "runId": "run-one", "batchId": "batch-one"}, "payloadSha256": HASH, "payloadBytes": 128,
            "guards": guard(), "scope": {"kind": "resume"}, "acceptedAt": TIME,
            "executionDeadline": "2026-10-16T12:03:00Z", "authority": "active", "revocation": None},
        "background_writer_v1": {"schemaVersion": 1, "projectId": "project-one", "lineage": "lineage-one",
            "epoch": 1, "sessionId": "session-one", "incarnation": "connection-one", "resumeCredentialSha256": HASH,
            "leaseExpiresAt": "2026-10-16T12:00:15Z", "status": "attached", "acknowledgedRevision": 1,
            "acknowledgedCursor": 0, "touchGeneration": 0, "barrierGeneration": 0, "draftId": None},
        "background_barrier_v1": {"schemaVersion": 1, "projectId": "project-one", "lineage": "lineage-one",
            "writerEpoch": 1, "incarnation": "connection-one", "generation": 1, "token": "synthetic_" * 4,
            "acknowledgedRevision": 1, "actionCursor": 0, "touchGeneration": 0,
            "expiresAt": "2026-10-16T12:00:00.750Z", "state": "acked"},
        "background_draft_v1": {"schemaVersion": 1, "id": "draft-one", "projectId": "project-one", "lineage": "lineage-one",
            "writerEpoch": 1, "incarnation": "connection-one", "sequence": 1, "actionCursor": 2,
            "baseRevision": 1, "baseSha256": HASH, "payloadSha256": HASH, "payloadBytes": 128,
            "payloadRef": "draft-payload-one", "touches": [stamp()], "checkpointedAt": TIME},
        "background_receipt_v1": {"schemaVersion": 1, "projectId": "project-one", "lineage": "lineage-one",
            "jobId": "job-one", "proposalId": "proposal-one", "clientMutationId": "mutation-one",
            "requestSha256": HASH, "proposalSha256": HASH, "workspaceSha256": HASH, "generationsSha256": HASH,
            "projectRevision": 2, "documentRevision": 2, "factsRevision": 1, "durable": True, "persistedAt": TIME},
        "background_apply_v2": {"schemaVersion": 2, "disposition": "waiting_for_sync", "jobId": "job-one",
            "proposalId": "proposal-one", "proposalStored": True, "durable": False, "reason": "WRITER_DIRTY"},
        "background_event_v1": {"schemaVersion": 1, "projectId": "project-one", "lineage": "lineage-one", "jobId": "job-one",
            "generation": 1, "cursor": 1, "type": "job.snapshot", "snapshot": snapshot()},
        "background_intent_v1": {"schemaVersion": 1, "id": "intent-one", "jobId": "job-one", "proposalId": "proposal-one",
            "projectId": "project-one", "lineage": "lineage-one", "clientMutationId": "mutation-one", "requestSha256": HASH,
            "beforeWorkspaceSha256": HASH, "afterWorkspaceSha256": HASH, "afterGenerationsSha256": HASH,
            "candidateRef": "candidate-one", "previousRef": "previous-one", "writerEpoch": 1,
            "incarnation": "connection-one", "barrierGeneration": 1, "phase": "intent_stored", "assetPins": [],
            "candidateSha256": None, "beforeGenerationsSha256": None, "resolvedAt": None},
        "background_undo_v1": {"schemaVersion": 1, "jobId": "job-one", "proposalId": "proposal-one", "owner": "backend",
            "writerEpoch": None, "incarnation": None, "transferId": "transfer-one", "inverseRef": "inverse-one",
            "inverseSha256": HASH, "inverseBytes": 128, "expiresAt": "2026-10-17T12:00:00Z", "guards": guard(),
            "assetPinsSha256": None},
        "background_sidecar_v1": {"schemaVersion": 1, "projectId": "project-one", "lineage": "lineage-one",
            "accountGeneration": 1, "activeRequestEpoch": 1, "expiredThroughEpoch": 0,
            "requestEpochExpiresAt": "2026-11-15T12:00:00Z", "tombstoned": False, "jobs": [], "requests": [],
            "proposals": [], "writer": None, "barrier": None, "drafts": [], "generations": [], "intents": [], "inverses": [],
            "history": None, "historyNamespace": None, "manualIntents": [], "assetPins": [], "orphanAssets": [], "cleanupRefs": []},
        "background_attempt_v1": {"schemaVersion": 1, "id": "attempt-one", "stage": "agent", "executionGeneration": 1,
            "state": "completed", "dispatchedAt": TIME, "startupDeadline": "2026-10-16T12:00:15Z",
            "activeDeadline": "2026-10-16T12:03:00Z", "nativeStarted": True, "childStartedAt": TIME,
            "cleanupVerified": True, "error": None},
        "background_draft_payload_v1": {"schemaVersion": 1, "document": project["document"], "facts": project["facts"],
            "outbox": [], "assetPins": []},
        "background_dispatch_v1": {"schemaVersion": 1, "accountGeneration": 1, "paused": None},
    }
    request = {"clientRequestId": "request-one", "conversationId": "conversation-one", "message": "Check synthetic evidence.",
        "allowEdits": True, "allowWeb": False, "scope": {"kind": "resume"}, "settingsRevision": 1,
        "projectRevision": 1, "documentRevision": 1, "factsRevision": 1}
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()
    result["background_agent_request_v1"] = {"schemaVersion": 1, "lineage": "lineage-one", "requestEpoch": 1, "request": request}
    result["background_artifact_v1"] = {"schemaVersion": 1,
        "id": "input_" + digest(submission()["identity"])[:24], "identity": submission()["identity"],
        "request": request, "requestSha256": digest(request), "connectionEpoch": "connection-one",
        "rulesSha256": digest(None), "jobId": "job-one", "createdAt": TIME,
        "snapshots": [], "batches": [], "sources": [], "findings": [], "reply": None, "usage": None,
        "observedGuards": None, "preparedGuards": None}
    result["background_legacy_run_v2"] = {"schemaVersion": 2, "jobId": "job-one", "publication": "waiting_for_sync",
        "run": {"id": "job-one", "conversationId": "conversation-one", "projectId": "project-one",
            "clientRequestId": "request_" + digest(submission()["identity"])[:24], "ownerEpoch": 1,
            "state": "completed", "allowEdits": True, "allowWeb": False, "scope": {"kind": "resume"},
            "model": "synthetic-model", "connectionEpoch": "connection-one", "settingsRevision": 1,
            "createdAt": TIME, "deadline": "2026-10-16T12:03:00Z", "finishedAt": TIME,
            "usage": None, "error": None, "savedBatchId": None, "outcomeUnknown": False}}
    result["background_project_v1"] = {"schemaVersion": 1, "projectId": "project-one", "lineage": "lineage-one",
        "requestEpoch": 1, "jobs": [snapshot()]}
    result["background_replay_request_v1"] = {"schemaVersion": 1, "generation": 1, "after": 0}
    result["background_replay_v1"] = {"schemaVersion": 1, "events": [result["background_event_v1"]]}
    return deepcopy(result)
