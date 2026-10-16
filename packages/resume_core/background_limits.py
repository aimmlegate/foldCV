"""Background policy v1. Changing a bound requires a new reviewed policy version."""

from dataclasses import asdict, dataclass

from . import agent_limits


@dataclass(frozen=True)
class BackgroundLimits:
    policy_version: int = 1
    executions: int = 3
    noninteractive_executions: int = 2
    serial_executions: int = 1
    render_workers: int = 2
    pending_global: int = 20
    pending_project: int = 4
    pending_noninteractive_global: int = 16
    pending_noninteractive_project: int = 3
    reconciliation_dispatch_bound: int = 3
    startup_seconds: int = agent_limits.STARTUP_SECONDS
    active_seconds: int = agent_limits.ACTIVE_SECONDS
    cleanup_seconds: int = agent_limits.CLEANUP_SECONDS
    writer_lease_seconds: int = agent_limits.LEASE_SECONDS
    writer_heartbeat_seconds: int = 5
    receipt_seconds: int = agent_limits.RECEIPT_SECONDS
    local_barrier_ms: int = 750
    sidecar_global_bytes: int = 64 * 1024 * 1024
    sidecar_project_bytes: int = agent_limits.PROJECT_BYTES
    metadata_global_records: int = 8192
    metadata_project_records: int = 512
    proposal_bytes: int = agent_limits.RUN_BYTES
    inverse_bytes: int = agent_limits.RUN_BYTES
    replay_events: int = 512
    replay_bytes: int = 256 * 1024
    resolved_seconds: int = 7 * 24 * 60 * 60
    resolved_global_records: int = 4096
    resolved_project_records: int = 256
    inverse_seconds: int = 24 * 60 * 60
    inverse_project_records: int = 20
    draft_global_bytes: int = 8 * 1024 * 1024
    draft_project_bytes: int = 2 * 1024 * 1024
    orphan_asset_seconds: int = 24 * 60 * 60
    request_replay_seconds: int = 30 * 24 * 60 * 60


LIMITS = BackgroundLimits()
OVERFLOW = {
    "pending": "JOB_QUEUE_FULL before dispatch; never evict an explicit request",
    "storage": "JOB_STORAGE_FULL before acceptance; preserve unresolved authority and drafts",
    "events": "Explicit cursor gap requires a current snapshot; never replay partial history as complete",
    "inverse": "Expire only eligible history and report expiry; uncertain saves have no inverse",
    "request": "Retained ID replays exactly; expired request epoch rejects without inference",
}


def policy() -> dict[str, object]:
    return {"limits": asdict(LIMITS), "overflow": dict(OVERFLOW),
        "queueConsumesActiveDeadline": False, "unresolvedPrunable": False}
