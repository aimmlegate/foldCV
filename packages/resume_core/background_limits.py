"""Versioned background limits; changed bounds retain a separate review record."""

from dataclasses import asdict, dataclass

from . import agent_limits
from .project_limits import (BACKGROUND_FACTOR, GLOBAL_PROJECTS, IMPORT_CEILING_SECONDS, INVERSE_BYTES, MIB,
    PROJECT_CEILING_BYTES, RENDER_WORKERS, USER_LIMITS, import_seconds as settings_import_seconds)


@dataclass(frozen=True)
class BackgroundLimits:
    policy_version: int = 4
    executions: int = 3
    noninteractive_executions: int = 2
    serial_executions: int = 1
    render_workers: int = RENDER_WORKERS
    pending_global: int = 20
    pending_project: int = 4
    pending_noninteractive_global: int = 16
    pending_noninteractive_project: int = 3
    reconciliation_dispatch_bound: int = 3
    startup_seconds: int = agent_limits.STARTUP_SECONDS
    active_seconds: int = agent_limits.ACTIVE_SECONDS
    # Ceilings: Settings choose the budgets below them; stored records are read under them.
    import_active_seconds: int = IMPORT_CEILING_SECONDS
    cleanup_seconds: int = agent_limits.CLEANUP_SECONDS
    writer_lease_seconds: int = agent_limits.LEASE_SECONDS
    writer_heartbeat_seconds: int = 5
    receipt_seconds: int = agent_limits.RECEIPT_SECONDS
    local_barrier_ms: int = 750
    sidecar_global_bytes: int = GLOBAL_PROJECTS * BACKGROUND_FACTOR * PROJECT_CEILING_BYTES
    sidecar_project_bytes: int = BACKGROUND_FACTOR * PROJECT_CEILING_BYTES
    metadata_global_records: int = 32768
    metadata_project_records: int = 4096
    proposal_bytes: int = agent_limits.RUN_BYTES
    inverse_bytes: int = INVERSE_BYTES
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


# Settings budgets; callers pass their module's LIMITS so a lowered ceiling still bounds them.
def import_seconds(limits=LIMITS):
    return settings_import_seconds(limits.import_active_seconds)


def background_project_bytes(limits=LIMITS):
    return min(limits.sidecar_project_bytes, BACKGROUND_FACTOR * USER_LIMITS.project_megabytes * MIB)


def background_global_bytes(limits=LIMITS):
    return min(limits.sidecar_global_bytes, GLOBAL_PROJECTS * BACKGROUND_FACTOR * USER_LIMITS.project_megabytes * MIB)


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
