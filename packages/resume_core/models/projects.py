"""Wire models of the /v2 project routes (D109): one request per edit, the full response back."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import Id, Revision, Sha256, Wire
from .template_authoring import ClipboardSelection, TemplateEditPreparationV1
from .template_render import TemplateSnapshotIdentity
from ..template_api import TemplateProjectResponseV1


class HistoryActionV1(Wire):
    action_id: Id
    kind: Literal['edit']


class HistoryStateV1(Wire):
    undo: HistoryActionV1 | None
    redo: HistoryActionV1 | None


class TaskStatusV1(Wire):
    id: Id
    project_id: Id
    kind: Literal['import', 'export', 'rewrite']
    state: Literal['running', 'succeeded', 'failed', 'cancelled']
    stage: str | None
    started_at: str
    elapsed: float = Field(ge=0)
    detail: dict
    error: Id | None


class ProjectOpenResultV1(Wire):
    schema_version: Literal[1]
    editor_token: str = Field(min_length=16, max_length=128)
    response: TemplateProjectResponseV1
    history: HistoryStateV1
    tasks: list[TaskStatusV1]


class EditRequestV1(Wire):
    editor_token: str = Field(min_length=1, max_length=128)
    base_revision: Revision
    preparation: TemplateEditPreparationV1


class EditResultV1(Wire):
    schema_version: Literal[1]
    revision: Revision
    document_revision: Revision
    client_mutation_id: Id
    replayed: bool
    created_ids: dict[str, dict[str, Id]]
    created_blocks: dict[str, list[Id]]
    changed_block_ids: list[Id]
    history: HistoryStateV1
    response: TemplateProjectResponseV1


class HistoryRequestV1(Wire):
    editor_token: str = Field(min_length=1, max_length=128)
    base_revision: Revision
    direction: Literal['undo', 'redo']
    client_mutation_id: Id
    expected_action_id: Id | None


class ClipboardCaptureRequestV1(Wire):
    editor_token: str = Field(min_length=1, max_length=128)
    client_capture_id: Id
    snapshot: TemplateSnapshotIdentity
    selection: ClipboardSelection


class RevisionConflictV1(Wire):
    """The body of a 409 for a stale base: the client drops what was applied and re-issues or reports the rest."""
    error: dict
    revision: Revision
    applied_client_mutation_ids: list[Id]


class RenameRequestV1(Wire):
    editor_token: str | None = Field(default=None, max_length=128)
    base_revision: Revision
    title: str = Field(min_length=1, max_length=200)


class DeleteRequestV1(Wire):
    confirmed: Literal[True]


PROJECT_CONTRACTS = {
    'history_state_v1': HistoryStateV1,
    'task_status_v1': TaskStatusV1,
    'project_open_result_v1': ProjectOpenResultV1,
    'edit_request_v1': EditRequestV1,
    'edit_result_v1': EditResultV1,
    'history_request_v1': HistoryRequestV1,
    'clipboard_capture_request_v1': ClipboardCaptureRequestV1,
    'revision_conflict_v1': RevisionConflictV1,
    'rename_request_v1': RenameRequestV1,
    'delete_request_v1': DeleteRequestV1,
}


def digest_request(value) -> Sha256:
    from ..templates.compiler import canonical, sha256
    return sha256(canonical(value))
