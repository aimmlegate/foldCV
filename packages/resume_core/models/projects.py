"""Wire models of the /v2 project routes (D109): one request per edit, the full response back."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..project_limits import REWRITE_INSTRUCTION_CHARS
from .contracts import Id, Revision, Sha256, Wire
from .template_authoring import AuthoredRange, ClipboardSelection, TemplateEditPreparationV1
from .template_render import TemplateSnapshotIdentity
from .template_response import TemplateProjectResponseV1


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


class RewritePreviewRequestV1(Wire):
    editor_token: str = Field(min_length=1, max_length=128)
    request_id: Id
    snapshot: TemplateSnapshotIdentity
    range: AuthoredRange
    instruction: str = Field(min_length=1, max_length=REWRITE_INSTRUCTION_CHARS)


class TemplateRewritePreviewV1(Wire):
    """A rewrite preview: the selected source and the model's text; the document changes only through Apply."""
    schema_version: Literal[1]
    request_id: Id
    snapshot: TemplateSnapshotIdentity
    range: AuthoredRange
    source: str
    text: str = Field(min_length=1, max_length=65536)


class RewriteCancelRequestV1(Wire):
    editor_token: str = Field(min_length=1, max_length=128)
    request_id: Id


class RevisionConflictV1(Wire):
    """The body of a 409 for a stale base: the client drops what was applied and re-issues or reports the rest."""
    error: dict
    revision: Revision
    applied_client_mutation_ids: list[Id]


class RenameRequestV1(Wire):
    editor_token: str = Field(min_length=1, max_length=128)
    base_revision: Revision
    title: str = Field(min_length=1, max_length=200)


class DateCheckRequestV1(Wire):
    """The date dialog's values before Save (D182): the job, or none for a new one, and its period fields by dialog key."""
    record_id: Id | None
    values: dict[str, str] = Field(max_length=150)


class DateCheckWarningV1(Wire):
    """One warning of the date dialog: another job's period it overlaps, or a period whose end is before its start."""
    kind: Literal['overlap', 'reversed']
    record_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    period: str | None = Field(default=None, exclude_if=lambda value: value is None)
    period_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)


class DateCheckResultV1(Wire):
    schema_version: Literal[1]
    warnings: list[DateCheckWarningV1]


class AnonymizedPreviewRequestV1(Wire):
    """The anonymized export's dialog (D186): the name to show; none for the remembered or proposed one."""
    name: str | None = Field(default=None, max_length=200)


class AnonymizedNoticeV1(Wire):
    """A place the user should check: a contact taken out of a sentence, the family name in a sentence, a link kept
    without its address."""
    kind: Literal['contact', 'family', 'link']
    quote: str = Field(max_length=200)


class AnonymizedPreviewV1(Wire):
    schema_version: Literal[1]
    name: str
    proposal: str
    left_out: str
    notices: list[AnonymizedNoticeV1]
    # For the print copy: the top blocks the anonymized page leaves out, and the new plain text of changed blocks.
    removed: list[Id]
    texts: dict[Id, str]


class AnonymizedRememberV1(Wire):
    """The name the user confirmed for an anonymized PDF; the DOCX export remembers it itself."""
    editor_token: str = Field(min_length=1, max_length=128)
    name: str = Field(max_length=200)


class PhotoRequestV1(Wire):
    """D187: the résumé's new photo (the cropped square, base64 JPEG or PNG), or null to remove it."""
    editor_token: str = Field(min_length=1, max_length=128)
    base_revision: Revision
    client_mutation_id: Id
    image: str | None = Field(default=None, max_length=5 * 1024 * 1024)


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
    'date_check_request_v1': DateCheckRequestV1,
    'anonymized_preview_request_v1': AnonymizedPreviewRequestV1,
    'anonymized_preview_v1': AnonymizedPreviewV1,
    'anonymized_remember_v1': AnonymizedRememberV1,
    'photo_request_v1': PhotoRequestV1,
    'date_check_result_v1': DateCheckResultV1,
    'rewrite_preview_request_v1': RewritePreviewRequestV1,
    'rewrite_cancel_request_v1': RewriteCancelRequestV1,
}


def digest_request(value) -> Sha256:
    from ..hashing import canonical, sha256
    return sha256(canonical(value))
