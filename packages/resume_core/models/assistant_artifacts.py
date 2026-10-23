"""Later UI receipts share the origin artifact without changing Job authority."""

from typing import Literal

from pydantic import Field, model_validator

from .agent import AgentBatchJournal, TERMINAL_EDITS
from .background import JobArtifactV1


class AssistantJobArtifactV1(JobArtifactV1):
    assistant_protocol_version: Literal[1]
    applications: list[AgentBatchJournal] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def owns_ui_applications(self):
        if self.job_id is None:
            raise ValueError("UI application needs a bound origin")
        if any(item.batch is None or item.batch.run_id != self.job_id or item.key != item.batch.id
                or item.receipt is not None and (item.receipt.run_id != self.job_id or item.receipt.batch_id != item.key
                    or item.receipt.request_sha256 != item.batch.request_sha256) for item in self.applications):
            raise ValueError("foreign UI application")
        if (sum(item.receipt is not None and item.receipt.durable for item in self.applications) > 1
                or sum(item.batch.state not in TERMINAL_EDITS for item in self.applications) > 1):
            raise ValueError("origin has more than one saved or active UI application")
        return self


def decode_assistant_artifact(value):
    model = AssistantJobArtifactV1 if "assistantProtocolVersion" in value else JobArtifactV1
    return model.model_validate(value)
