"""The explicit resume check of the Facts panel: the assistant's deterministic check over the committed workspace."""

from __future__ import annotations

from packages.resume_core.models.projects import ProjectCheckResultV1

from ..assistant.context import check
from .errors import ProjectFailure


def run(service, project_id, request):
    session = service.repository.open(project_id)
    with session.lock:
        session.require_editor(request.editor_token)
        workspace = session.workspace
    if workspace.project is None:
        raise ProjectFailure('EDITOR_NOT_READY', 409)
    # A committed workspace is replaced on commit, never changed in place, so it is read after the lock is released.
    report = {key: value for key, value in check(workspace).items() if key != 'semanticReview'}
    return ProjectCheckResultV1.model_validate({'schemaVersion': 1, **report})
