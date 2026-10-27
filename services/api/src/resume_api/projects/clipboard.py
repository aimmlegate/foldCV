"""Same-project clipboard: captures live in the open session (20 at most) and are verified against witnesses at paste."""

from __future__ import annotations

from packages.resume_core.models.projects import digest_request
from packages.resume_core.models.template_authoring import TemplateClipboardCaptureV1
from packages.resume_core.project_repository import RepositoryFailure
from packages.resume_core.rich_mutations import RichMutationFailure
from packages.resume_core.template_clipboard import capture_clipboard, selected_witnesses
from packages.resume_core.template_clipboard_witnesses import verify_witnesses
from packages.resume_core.templates.compiler import canonical, sha256
from packages.resume_core.templates.presentation import snapshot_identity

from .errors import ProjectFailure


def capture(service, project_id, request):
    session = service.repository.open(project_id)
    fingerprint = digest_request({'snapshot': request.snapshot.model_dump(mode='json', by_alias=True),
        'selection': request.selection.model_dump(mode='json', by_alias=True)})
    identifier = 'clipboard-' + sha256(canonical(['FoldCV clipboard v2', project_id, request.client_capture_id]))
    with session.lock:
        session.require_editor(request.editor_token)
        retained = session.clipboard.get(identifier)
        if retained is not None:
            if retained.request_hash != fingerprint:
                raise RepositoryFailure('MUTATION_ID_REUSED')
            return retained.capture.model_copy(deep=True)
        workspace = session.workspace
        if workspace.project is None or request.snapshot != snapshot_identity(workspace):
            raise RepositoryFailure('DEPENDENCY_CHANGED')
        value = TemplateClipboardCaptureV1(schemaVersion=1, clipboardCaptureId=identifier, projectId=project_id,
            sourceSnapshot=request.snapshot, selection=request.selection)
        try:
            retained = capture_clipboard(workspace, value, fingerprint)
        except (ValueError, RichMutationFailure):
            raise ProjectFailure('V7_INPUT_REJECTED', 422) from None
        session.remember_capture(identifier, retained)
        return value.model_copy(deep=True)


def for_paste(session, workspace, identifier):
    """The retained capture, refused when it was evicted or when a source it witnessed changed since the copy."""
    retained = session.clipboard.get(identifier)
    if retained is None:
        raise RepositoryFailure('REQUEST_EXPIRED')
    try:
        verify_witnesses(workspace.project, retained.witnesses, retained.package_fingerprint)
        if selected_witnesses(workspace.project, retained.payload) != retained.witnesses:
            raise ValueError('clipboard witness coverage changed')
    except ValueError:
        raise RepositoryFailure('DEPENDENCY_CHANGED') from None
    return retained
