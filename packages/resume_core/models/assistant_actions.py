"""Versioned project-action review ports, separate from editor mutations."""

from typing import Literal

from pydantic import Field, model_validator

from .agent import AgentId, AgentProjectAction, AgentProjectOperation, Timestamp
from .assistant_approval import AssistantAcceptanceIdentityV1
from .assistant_capabilities import AssistantProtocolV1
from .assistant_proposals import AssistantProposalV1, AssistantReviewV1, AssistantStoredProposalV1
from .contracts import Sha256
from ..rich_api import RichProjectResponse


class AssistantProjectActionPrepareV1(AssistantProtocolV1):
    protocol_version: Literal[1]
    request: AgentProjectAction


class AssistantProjectActionPreviewV1(AssistantProtocolV1):
    action: Literal["rename", "formatting_date", "add_source_text", "remove_source", "import_asset", "remove_asset", "archive", "restore", "delete"]
    target_id: AgentId
    target_label: str = Field(min_length=1, max_length=512)
    consequence: str = Field(min_length=1, max_length=2000)
    image_preview_url: str | None = Field(default=None, max_length=1024,
        pattern=r"^/v1/rich/projects/[A-Za-z0-9_-]+/assistant/proposals/[A-Za-z0-9_-]+/versions/[0-9]+/image-preview$")


class AssistantCapabilityReviewV1(AssistantReviewV1):
    action: AssistantProjectActionPreviewV1 | None = None


class AssistantCapabilityReviewsV1(AssistantProtocolV1):
    project_id: AgentId
    reviews: list[AssistantCapabilityReviewV1] = Field(max_length=20)


class AssistantProjectActionClaimV1(AssistantProtocolV1):
    accepted: AssistantAcceptanceIdentityV1
    ticket: AgentId
    expires_at: Timestamp
    request_sha256: Sha256


class AssistantProjectActionResultV1(AssistantProtocolV1):
    proposal: AssistantProposalV1
    operation: AgentProjectOperation | None
    project: RichProjectResponse | None
    claim: AssistantProjectActionClaimV1 | None = None


class AssistantProjectActionPayloadV1(AssistantProtocolV1):
    request: AgentProjectAction
    archived_before: bool = Field(strict=True)
    archived_after: bool | None = Field(strict=True)
    blob_base64: str | None = Field(max_length=512000)
    blob_sha256: Sha256 | None
    preview: AssistantProjectActionPreviewV1


class AssistantStoredActionV1(AssistantStoredProposalV1):
    record_kind: Literal["action_v1"] = "action_v1"
    action: AssistantProjectActionPayloadV1 | None

    @model_validator(mode="after")
    def exact_content(self):
        from ..assistant_actions import action_baseline_digest, action_proposal_digest
        if self.batch is not None or self.operations or self.proposal.operation_count != 0 or len(self.calls) > 64:
            raise ValueError("project action cannot carry an editor mutation")
        if self.action is None:
            if self.proposal.state not in {"applied", "expired"} or self.baseline is not None or self.candidate is not None:
                raise ValueError("missing project action payload")
            if self.proposal.state == "applied" and (not self.compacted or self.approval is None or self.approval.phase != "receipt_stored"):
                raise ValueError("compacted action needs its saved receipt identity")
            return self
        if (self.baseline is None or self.action.preview.target_id != self.proposal.project_id
                or self.action.preview.target_label != self.baseline.title):
            raise ValueError("project action needs its exact frozen target")
        if self.action.preview.action != self.action.request.action or self.scope.kind != "resume":
            raise ValueError("project action preview must name the captured operation")
        lifecycle = self.action.request.action in {"archive", "restore", "delete"}
        if (self.candidate is None) != lifecycle or self.action.request.action in {"undo", "redo", "export_docx", "export_project"}:
            raise ValueError("project action needs its own supported application port")
        expected_image = (f"/v1/rich/projects/{self.proposal.project_id}/assistant/proposals/{self.proposal.id}/versions/{self.proposal.version}/image-preview"
            if self.action.request.action in {"import_asset", "remove_asset"} else None)
        if self.action.preview.image_preview_url != expected_image:
            raise ValueError("image preview must belong to this exact action version")
        if (self.proposal.before_sha256 != action_baseline_digest(self.baseline, self.action.archived_before)
                or self.proposal.content_sha256 != action_proposal_digest(self.action, self.candidate)):
            raise ValueError("changed project action candidate")
        if self.proposal.state == "ready" and (self.no_change or any(not unit.read or unit.state == "unresolved" for unit in self.proposal.coverage)):
            raise ValueError("ready project action needs complete resources")
        return self


ASSISTANT_ACTION_CONTRACTS = {
    "assistant_project_action_prepare_v1": AssistantProjectActionPrepareV1,
    "assistant_capability_review_v1": AssistantCapabilityReviewV1,
    "assistant_capability_reviews_v1": AssistantCapabilityReviewsV1,
    "assistant_project_action_claim_v1": AssistantProjectActionClaimV1,
    "assistant_project_action_result_v1": AssistantProjectActionResultV1,
}
