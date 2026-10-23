"""Private draft assembly and public review data; none conveys write authority."""

from typing import Literal

from pydantic import Field, model_validator

from .agent import AgentEditBatch, AgentEditOperation, AgentId, AgentScope, AgentSnapshotDependency, Timestamp
from .assistant_capabilities import AssistantProtocolV1, TaskId
from .contracts import Sha256
from .rich_workspace import WorkspaceV6

ProposalState = Literal["building", "ready", "incomplete", "invalid", "cancelled", "applying", "applied",
    "stale", "discarded", "expired", "failed_before_commit", "outcome_unknown"]


class AssistantCoverageV1(AssistantProtocolV1):
    unit_id: str = Field(min_length=1, max_length=256)
    state: Literal["changed", "unchanged", "unresolved"]
    reason: str = Field(max_length=1000)
    read: bool = Field(strict=True)


class AssistantCoverageDeclarationV1(AssistantProtocolV1):
    unit_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=1000)


class AssistantChangeV1(AssistantProtocolV1):
    unit_id: str = Field(min_length=1, max_length=256)
    before: str = Field(max_length=256000)
    after: str = Field(max_length=256000)
    effect: Literal["wording", "structure", "fact", "format"]


class AssistantAssemblyRequestV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    proposal_id: AgentId | None = None
    version: int = Field(default=1, ge=1, le=20, strict=True)
    key: AgentId
    task_id: TaskId
    phase: Literal["append", "finalize"]
    snapshot_ids: list[AgentId] = Field(default_factory=list, max_length=64)
    operations: list[AgentEditOperation] = Field(default_factory=list, max_length=100)
    unchanged: list[AssistantCoverageDeclarationV1] = Field(default_factory=list, max_length=2000)


class AssistantProposalV1(AssistantProtocolV1):
    id: AgentId
    version: int = Field(ge=1, le=20, strict=True)
    project_id: AgentId
    lineage: Sha256
    editor_family: Literal["ordinary"]
    origin_request_id: AgentId
    origin_run_id: AgentId
    task_id: TaskId
    state: ProposalState
    created_at: Timestamp
    expires_at: Timestamp
    content_sha256: Sha256
    before_sha256: Sha256
    coverage: list[AssistantCoverageV1] = Field(max_length=20000)
    changes: list[AssistantChangeV1] = Field(max_length=2000)
    operation_count: int = Field(ge=0, le=100, strict=True)
    reason: str | None = Field(max_length=2000)


class AssistantProposalRequestV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    proposal_id: AgentId
    version: int = Field(ge=1, le=20, strict=True)
    content_sha256: Sha256


class AssistantProposalListV1(AssistantProtocolV1):
    project_id: AgentId
    proposals: list[AssistantProposalV1] = Field(max_length=20)


class AssistantProposalResultV1(AssistantProtocolV1):
    disposition: Literal["building", "draft_ready", "incomplete", "no_change"]
    proposal_id: AgentId | None
    version: int = Field(ge=1, le=20, strict=True)
    content_sha256: Sha256
    changed_units: int = Field(ge=0, strict=True)
    unresolved_units: int = Field(ge=0, strict=True)
    coverage: list[AssistantCoverageV1] = Field(max_length=20)
    coverage_truncated: bool = Field(strict=True)
    unit_count: int = Field(ge=0, strict=True)
    durable: Literal[False] = False
    reason: str


class AssistantStoredProposalV1(AssistantProtocolV1):
    proposal: AssistantProposalV1
    account_epoch: AgentId
    access_revision: int = Field(ge=1, strict=True)
    scope: AgentScope
    dependencies: list[AgentSnapshotDependency] = Field(max_length=2000)
    baseline: WorkspaceV6 | None
    candidate: WorkspaceV6 | None
    batch: AgentEditBatch | None
    operations: list[AgentEditOperation] = Field(max_length=100)
    snapshot_ids: list[AgentId] = Field(max_length=64)
    calls: dict[AgentId, Sha256]
    unchanged: list[AssistantCoverageDeclarationV1] = Field(max_length=2000)
    no_change: bool = Field(strict=True)

    @model_validator(mode="after")
    def exact_content(self):
        from ..assistant_proposals import content_digest
        from ..rich_mutations import apply_rich_mutation, mutation_sha256
        if len(self.calls) > 64 or self.proposal.operation_count != len(self.operations):
            raise ValueError("proposal exceeds its frozen assembly")
        if self.baseline is not None and self.proposal.before_sha256 != content_digest(self.baseline):
            raise ValueError("changed baseline")
        if self.candidate is not None and self.proposal.content_sha256 != content_digest(self.candidate):
            raise ValueError("changed candidate")
        if self.batch is not None:
            if self.baseline is None or self.candidate is None or self.batch.mutation.project_id != self.proposal.project_id:
                raise ValueError("missing candidate authority")
            rebuilt = apply_rich_mutation(self.baseline, self.batch.mutation)[0]
            if (mutation_sha256(self.batch.mutation) != self.batch.request_sha256
                    or content_digest(rebuilt) != self.proposal.content_sha256):
                raise ValueError("candidate differs from the canonical compiler")
        if self.proposal.state == "ready" and (self.candidate is None or self.batch is None or self.no_change
                or any(unit.state == "unresolved" or not unit.read for unit in self.proposal.coverage)):
            raise ValueError("ready requires a complete immutable candidate")
        return self


ASSISTANT_PROPOSAL_CONTRACTS = {
    "assistant_assembly_request_v1": AssistantAssemblyRequestV1,
    "assistant_proposal_v1": AssistantProposalV1,
    "assistant_proposal_request_v1": AssistantProposalRequestV1,
    "assistant_proposal_list_v1": AssistantProposalListV1,
    "assistant_proposal_result_v1": AssistantProposalResultV1,
}
