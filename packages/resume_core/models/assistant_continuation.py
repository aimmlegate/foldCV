"""Explicit draft continuation and bounded, non-authoritative draft reads."""

from typing import Literal

from pydantic import Field

from .agent import AgentId, AgentJournalRequest, AgentRunRequest
from .assistant_capabilities import AssistantAvailabilityV1, AssistantProtocolV1
from .assistant_proposals import AssistantProposalRequestV1
from .background import JobAgentRequestV1
from .contracts import Sha256


class AssistantContinueRunV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    proposal: AssistantProposalRequestV1
    request: AgentRunRequest


class AssistantContinueJobV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    proposal: AssistantProposalRequestV1
    request: JobAgentRequestV1


class AssistantContinuationOptionV1(AssistantProtocolV1):
    proposal: AssistantProposalRequestV1
    availability: AssistantAvailabilityV1
    request: AgentJournalRequest | None
    operations_remaining: int = Field(ge=0, le=100, strict=True)
    versions_remaining: int = Field(ge=0, le=19, strict=True)
    tool_calls: Literal[64] = 64
    tool_bytes: Literal[65536] = 65536


class AssistantContinuationOptionsV1(AssistantProtocolV1):
    project_id: AgentId
    options: list[AssistantContinuationOptionV1] = Field(max_length=20)


class AssistantDraftReadV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    proposal_id: AgentId
    version: int = Field(ge=1, le=20, strict=True)
    cursor: AgentId | None = None


class AssistantDraftPageV1(AssistantProtocolV1):
    content: str = Field(max_length=16384)
    content_sha256: Sha256
    offset: int = Field(ge=0, strict=True)
    total_characters: int = Field(ge=0, strict=True)
    next_cursor: AgentId | None
    complete: bool = Field(strict=True)
    read_credit: Literal[False] = False


class AssistantRunOutcomeV1(AssistantProtocolV1):
    run_id: AgentId
    outcome: Literal["none", "no_change", "draft_ready", "incomplete", "applied", "stale", "failed", "outcome_unknown"]
    durable: bool = Field(strict=True)
    reason: str = Field(max_length=2000)


ASSISTANT_CONTINUATION_CONTRACTS = {
    "assistant_continue_run_v1": AssistantContinueRunV1,
    "assistant_continue_job_v1": AssistantContinueJobV1,
    "assistant_continuation_options_v1": AssistantContinuationOptionsV1,
    "assistant_draft_read_v1": AssistantDraftReadV1,
    "assistant_draft_page_v1": AssistantDraftPageV1,
    "assistant_run_outcome_v1": AssistantRunOutcomeV1,
}
