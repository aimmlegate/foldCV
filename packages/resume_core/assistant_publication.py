"""Internal UI authority at the shared writer's admission and durable claim."""

from dataclasses import dataclass
from typing import Callable

from .background_store import BackgroundFailure
from .rich_mutations import mutation_sha256
from .models.background import HistoryCommitBindingV1


@dataclass(frozen=True)
class AssistantMutationGrant:
    project_id: str
    request_sha256: str
    authorize: Callable
    claim: Callable
    prepared: Callable
    history_binding: HistoryCommitBindingV1 | None = None

    def require(self, project, mutation):
        if project != self.project_id or mutation_sha256(mutation) != self.request_sha256:
            raise BackgroundFailure("JOB_SCOPE_INVALID")


@dataclass(frozen=True)
class AssistantSnapshotGrant:
    project_id: str
    command_id: str
    after_sha256: str
    authorize: Callable
    claim: Callable

    def require(self, project, candidate):
        from .background_history import digest_bytes
        if project != self.project_id:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        if hasattr(candidate, "workspace"):
            if not candidate.snapshot_write or candidate.client_mutation_id != self.command_id:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            candidate = candidate.workspace
        if digest_bytes(candidate) != self.after_sha256:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
