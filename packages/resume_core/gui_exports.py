"""Current DOCX export intent and exact artifact cache identity."""

import hashlib
from .gui_derived import digest
from .gui_mutations import unicode_valid
from .models.contracts import Id, Revision, Wire
from .rendering.template import PACKAGE_SHA256


class GuiExportRequest(Wire):
    client_request_id: Id
    project_revision: Revision
    document_revision: Revision


def export_fingerprint(request):
    unicode_valid(request.model_dump())
    return digest(request.model_dump(mode="json", by_alias=True))


def matching_snapshot(workspace, snapshot, content, fingerprint, renderer):
    return bool(snapshot.artifact_available and snapshot.docx and content is not None
        and (snapshot.project_revision, snapshot.document_revision) == (workspace.project_revision, workspace.document_revision)
        and snapshot.render_input_fingerprint == fingerprint
        and (snapshot.template_id, snapshot.template_version, snapshot.template_sha256) == ("generic", "1.0.0", PACKAGE_SHA256)
        and (snapshot.renderer_version, snapshot.renderer_sha256) == ("1.0.0", renderer)
        and snapshot.docx.size == len(content) and snapshot.docx.sha256 == hashlib.sha256(content).hexdigest())


GUI_EXPORT_CONTRACTS = {"gui_export_request": GuiExportRequest}
