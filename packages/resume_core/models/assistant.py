"""Assistant wire models on the repository (D109, plan 2.8): conversations, runs, proposals and the change ops."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .. import agent_limits as limits
from .agent import AgentEvent, AgentFinding, AgentMessage, AgentUsage, AgentWebSource
from .contracts import Id, Revision, Sha256, Wire
from .projects import EditResultV1
from .rich_document import InlineStyles

Code = Annotated[str, Field(pattern=r'^[A-Z][A-Z0-9_]{1,63}$')]
Stamp = Annotated[str, Field(min_length=1, max_length=64)]
RunState = Literal['queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled', 'interrupted']
TERMINAL = frozenset({'completed', 'failed', 'cancelled', 'interrupted'})


class AssistantErrorV1(Wire):
    code: Code
    detail: list[str] = Field(default_factory=list, max_length=20)


class AssistantSelectionV1(Wire):
    block_ids: list[Id] = Field(max_length=100)
    text: str = Field(max_length=4000)


class AssistantRunRequestV2(Wire):
    client_request_id: Id
    message: str = Field(min_length=1, max_length=limits.USER_CHARS)
    allow_edits: bool
    allow_web: bool
    selection: AssistantSelectionV1 | None = None


class AssistantRunV1(Wire):
    id: Id
    conversation_id: Id
    project_id: Id
    client_request_id: Id
    state: RunState
    allow_edits: bool
    allow_web: bool
    model: str = Field(max_length=80)
    base_revision: Revision
    created_at: Stamp
    finished_at: Stamp | None
    error: AssistantErrorV1 | None
    usage: AgentUsage | None


class AssistantConversationV1(Wire):
    id: Id
    title: str = Field(max_length=120)
    created_at: Stamp
    updated_at: Stamp


class AssistantConversationListV1(Wire):
    items: list[AssistantConversationV1] = Field(max_length=100)


class AssistantMessagesV1(Wire):
    conversation: AssistantConversationV1
    messages: list[AgentMessage] = Field(max_length=limits.CONVERSATION_MESSAGES)
    sources: list[AgentWebSource] = Field(max_length=100)
    findings: list[AgentFinding] = Field(max_length=200)
    runs: list[AssistantRunV1] = Field(max_length=20)
    # Export links made by the export tool in this service process; files are not kept across a restart.
    files: list[AssistantFileV1] = Field(default_factory=list, max_length=10)


class AssistantEventsV1(Wire):
    run: AssistantRunV1
    events: list[AgentEvent] = Field(max_length=500)
    next: int = Field(ge=0)


# Change ops: the model writes these; the compiler turns them into authored operations (plan 2.8 table).

class SetBlockTextOp(Wire):
    op: Literal['set_block_text']
    block_id: Id
    cell_id: Id | None = None
    field: Literal['content', 'caption'] = 'content'
    text: str = Field(max_length=16000)
    marks: InlineStyles | None = None


class ReplaceTextOp(Wire):
    op: Literal['replace_text']
    block_id: Id
    cell_id: Id | None = None
    field: Literal['content', 'caption'] = 'content'
    find: str = Field(min_length=1, max_length=4000)
    replace: str = Field(max_length=4000)


class NewBlock(Wire):
    kind: Literal['paragraph', 'heading', 'bullet', 'numbered'] = 'paragraph'
    level: Literal[1, 2, 3] = 2
    text: str = Field(max_length=16000)


class InsertBlocksOp(Wire):
    op: Literal['insert_blocks']
    after_block_id: Id | None = None
    parent_id: Id | None = None
    blocks: list[NewBlock] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def anchored(self):
        if (self.after_block_id is None) == (self.parent_id is None):
            raise ValueError('insert_blocks needs afterBlockId or parentId')
        return self


class DeleteBlocksOp(Wire):
    op: Literal['delete_blocks']
    block_ids: list[Id] = Field(min_length=1, max_length=100)


class MoveBlockOp(Wire):
    op: Literal['move_block']
    block_id: Id
    after_block_id: Id | None = None
    parent_id: Id | None = None

    @model_validator(mode='after')
    def anchored(self):
        if (self.after_block_id is None) == (self.parent_id is None):
            raise ValueError('move_block needs afterBlockId or parentId')
        return self


class FormatBlockOp(Wire):
    op: Literal['format_block']
    block_id: Id
    kind: Literal['paragraph', 'heading', 'bullet', 'numbered'] | None = None
    level: Literal[1, 2, 3] | None = None
    alignment: Literal['left', 'center', 'right', 'justify'] | None = None
    text_color: str | None = Field(default=None, max_length=32)
    background_color: str | None = Field(default=None, max_length=32)


class UpdateFactOp(Wire):
    op: Literal['update_fact']
    record_id: Id
    field: Id
    value: str = Field(max_length=4000)


class CreateFactOp(Wire):
    op: Literal['create_fact']
    kind: Literal['candidate', 'employment', 'technology', 'education', 'language', 'claim', 'period']
    values: dict[str, str] = Field(default_factory=dict, max_length=20)
    job_id: Id | None = None
    # The line a technology joins when its scope has several (the refusal lists them).
    target_id: Id | None = None


class DeleteFactOp(Wire):
    op: Literal['delete_fact']
    record_id: Id


class HistoryOp(Wire):
    op: Literal['history']
    direction: Literal['undo', 'redo']


ProjectAction = Literal['rename', 'formatting_date', 'archive', 'restore', 'delete']


class ActionOp(Wire):
    op: Literal['action']
    action: ProjectAction
    value: str | None = Field(default=None, max_length=200)
    target_id: Id | None = None


DocumentOp = Annotated[SetBlockTextOp | ReplaceTextOp | InsertBlocksOp | DeleteBlocksOp | MoveBlockOp | FormatBlockOp |
    UpdateFactOp | CreateFactOp | DeleteFactOp, Field(discriminator='op')]
AssistantOp = Annotated[SetBlockTextOp | ReplaceTextOp | InsertBlocksOp | DeleteBlocksOp | MoveBlockOp | FormatBlockOp |
    UpdateFactOp | CreateFactOp | DeleteFactOp | HistoryOp | ActionOp, Field(discriminator='op')]


class ProposeChangesV1(Wire):
    summary: str = Field(min_length=1, max_length=2000)
    ops: list[AssistantOp] = Field(min_length=1, max_length=limits.EDIT_OPERATIONS)

    @model_validator(mode='after')
    def single_navigation(self):
        if any(op.op in {'history', 'action'} for op in self.ops) and len(self.ops) != 1:
            raise ValueError('a history or project action is a proposal of its own')
        return self


class PreviewEntryV1(Wire):
    target: str = Field(max_length=256)
    label: str = Field(max_length=256)
    before: str = Field(max_length=16000)
    after: str = Field(max_length=16000)


class AssistantChangeProposalV1(Wire):
    schema_version: Literal[1]
    id: Id
    project_id: Id
    conversation_id: Id
    run_id: Id
    kind: Literal['edit', 'history', 'action']
    summary: str = Field(max_length=2000)
    base_revision: Revision
    touched: dict[str, Sha256] = Field(max_length=500)
    # The undo or redo top when a history proposal was made; Apply requires the same top.
    expected_action_id: Id | None = None
    ops: list[AssistantOp] = Field(max_length=limits.EDIT_OPERATIONS)
    preview: list[PreviewEntryV1] = Field(max_length=limits.EDIT_OPERATIONS * 2)
    state: Literal['draft', 'applied', 'discarded']
    applied_revision: Revision | None
    created_at: Stamp
    updated_at: Stamp


class AssistantChangeProposalListV1(Wire):
    items: list[AssistantChangeProposalV1] = Field(max_length=100)


class AssistantApplyRequestV1(Wire):
    editor_token: str = Field(min_length=1, max_length=256)
    client_mutation_id: Id
    # The panel's edits flag now; Apply is refused while it is off (G8).
    allow_edits: bool


class AssistantActionResultV1(Wire):
    action: ProjectAction
    title: str | None
    archived: bool | None
    deleted: bool


class AssistantApplyResultV1(Wire):
    proposal: AssistantChangeProposalV1
    edit: EditResultV1 | None
    action: AssistantActionResultV1 | None


class FindingTargetV1(Wire):
    block_id: Id | None = None
    cell_id: Id | None = None
    record_id: Id | None = None
    field_key: Id | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def one_target(self):
        if (self.block_id is None) == (self.record_id is None):
            raise ValueError('a finding target names a block or a record')
        if (self.start is None) != (self.end is None) or self.start is not None and self.end < self.start:
            raise ValueError('a finding range needs ordered start and end')
        return self


class FindingInputV1(Wire):
    severity: Literal['info', 'warning', 'error'] = 'info'
    message: str = Field(min_length=1, max_length=4000)
    targets: list[FindingTargetV1] = Field(default_factory=list, max_length=20)
    source_ids: list[Id] = Field(default_factory=list, max_length=20)


class PublishFindingsV1(Wire):
    findings: list[FindingInputV1] = Field(min_length=1, max_length=20)


class ModelChoiceV1(Wire):
    model: str = Field(max_length=80)
    state: Literal['unverified', 'verified', 'incompatible']
    # The provider's display name; the model list groups by it, as Settings does (D119).
    provider: str | None = Field(default=None, max_length=40)


class AssistantCapabilitiesV1(Wire):
    ready: bool
    unavailable: AssistantErrorV1 | None
    models: list[ModelChoiceV1] = Field(max_length=100)
    web_available: bool
    tools: list[str] = Field(max_length=32)


class AssistantFileV1(Wire):
    id: Id
    format: Literal['docx', 'foldcv']
    url: str = Field(max_length=512)
    filename: str = Field(max_length=200)
    size: int = Field(ge=0)


class AssistantSkillV1(Wire):
    id: Id
    title: str = Field(max_length=200)
    description: str = Field(max_length=2000)


class AssistantSkillListV1(Wire):
    items: list[AssistantSkillV1] = Field(max_length=20)


ASSISTANT_CONTRACTS = {
    'assistant_error_v1': AssistantErrorV1,
    'assistant_run_request_v2': AssistantRunRequestV2,
    'assistant_run_v1': AssistantRunV1,
    'assistant_conversation_v1': AssistantConversationV1,
    'assistant_conversation_list_v1': AssistantConversationListV1,
    'assistant_messages_v1': AssistantMessagesV1,
    'assistant_events_v1': AssistantEventsV1,
    'assistant_change_proposal_v1': AssistantChangeProposalV1,
    'assistant_change_proposal_list_v1': AssistantChangeProposalListV1,
    'assistant_apply_request_v1': AssistantApplyRequestV1,
    'assistant_apply_result_v1': AssistantApplyResultV1,
    'assistant_skill_list_v1': AssistantSkillListV1,
    'propose_changes_v1': ProposeChangesV1,
    'publish_findings_v1': PublishFindingsV1,
    'assistant_capabilities_v1': AssistantCapabilitiesV1,
    'assistant_file_v1': AssistantFileV1,
}


AssistantMessagesV1.model_rebuild()
