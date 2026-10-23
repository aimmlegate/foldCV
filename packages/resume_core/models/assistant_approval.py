"""UI acceptance identities and private publication authority, separate from runs."""

from typing import Literal
from pydantic import Field

from .agent import AgentClaimResult, AgentCommitResult, AgentEditReceipt, AgentId, AgentRunRequest
from .assistant_capabilities import AssistantProtocolV1
from .assistant_proposals import AssistantProposalAcceptV1, AssistantProposalRequestV1, AssistantProposalV1
from .contracts import Sha256
from .background import WriterAdvanceV1, JobAgentRequestV1


class AssistantRunRequestV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    request: AgentRunRequest


class AssistantJobRequestV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    request: JobAgentRequestV1


class AssistantAcceptanceIdentityV1(AssistantProposalRequestV1):
    acceptance_id: AgentId


class AssistantAcceptanceV1(AssistantProposalAcceptV1):
    acceptance_id: AgentId


class AssistantApplicationClaimV1(AssistantProtocolV1):
    accepted: AssistantAcceptanceIdentityV1
    claim: AgentClaimResult


class AssistantApplicationCommitV1(AssistantAcceptanceV1):
    ticket: AgentId
    request_sha256: Sha256
    writer: WriterAdvanceV1 | None = None


class AssistantApplicationReportV1(AssistantAcceptanceV1):
    receipt: AgentEditReceipt


class AssistantApplicationRecoveryV1(AssistantProtocolV1):
    proposal: AssistantProposalV1 | None
    result: AgentCommitResult | None
    claim: AssistantApplicationClaimV1 | None
    saved_receipt: AgentEditReceipt | None = None
    reload_required: bool = Field(default=False, strict=True)
    reason: str | None = Field(default=None, max_length=2000)


ASSISTANT_APPROVAL_CONTRACTS = {
    "assistant_run_request_v1": AssistantRunRequestV1,
    "assistant_job_request_v1": AssistantJobRequestV1,
    "assistant_acceptance_v1": AssistantAcceptanceV1,
    "assistant_application_claim_v1": AssistantApplicationClaimV1,
    "assistant_application_commit_v1": AssistantApplicationCommitV1,
    "assistant_application_report_v1": AssistantApplicationReportV1,
    "assistant_application_recovery_v1": AssistantApplicationRecoveryV1,
}
