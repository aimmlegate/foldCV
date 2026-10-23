"""Capture the requested native history action before model execution."""

from typing import Literal

from .agent import AgentHistoryOffer, AgentId, ReferenceId
from .assistant_capabilities import AssistantProtocolV1


class AssistantHistoryTargetV1(AssistantProtocolV1):
    job_id: AgentId
    proposal_id: AgentId
    transfer_id: AgentId


class AssistantHistoryOfferV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    request_id: AgentId
    offer: AgentHistoryOffer
    undo_backend: AssistantHistoryTargetV1 | None = None
    redo_backend: AssistantHistoryTargetV1 | None = None


class AssistantHistoryCaptureV1(AssistantProtocolV1):
    direction: Literal["undo", "redo"]
    request_id: AgentId
    action_id: ReferenceId
    session_id: AgentId
    backend: AssistantHistoryTargetV1 | None = None
    previous_ref: AgentId | None = None


ASSISTANT_HISTORY_CONTRACTS = {"assistant_history_offer_v1": AssistantHistoryOfferV1}
