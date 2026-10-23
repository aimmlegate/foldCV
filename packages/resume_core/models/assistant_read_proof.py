"""Private provenance for actual complete reads carried between bounded draft runs."""

from pydantic import Field, model_validator

from .agent import AgentId, AgentQuery, AgentReadSnapshot
from .assistant_capabilities import AssistantProtocolV1
from .contracts import Sha256


class AssistantReadGroupV1(AssistantProtocolV1):
    query: AgentQuery
    snapshots: list[AgentReadSnapshot] = Field(min_length=1, max_length=64)
    aliases: list[AgentId] = Field(default_factory=list, max_length=20)
    current_alias: AgentId | None = None

    @model_validator(mode="after")
    def complete_read(self):
        if self.query.cursor is not None or self.query.kind == "history" or self.snapshots[-1].truncated:
            raise ValueError("carry proof requires a complete canonical read")
        if self.current_alias is not None and self.current_alias not in self.aliases:
            raise ValueError("carry alias needs its provenance")
        if len({item.id for item in self.snapshots}) != len(self.snapshots):
            raise ValueError("duplicate read proof")
        return self


class AssistantContinuationOriginV1(AssistantProtocolV1):
    proposal_id: AgentId
    version: int = Field(ge=1, le=19, strict=True)
    content_sha256: Sha256
    request_sha256: Sha256
    journal_sha256: Sha256
