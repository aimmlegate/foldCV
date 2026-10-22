"""Export identity captures authored bytes and never grants inference authority."""

from .models.template_import import ExportAttempt
from .models.template_render import (CapturedTemplateRenderInputV1, TemplateExportCapture, TemplateRenderAsset, TemplateRenderRequestV1,
    TemplateSnapshotIdentity, presentation_value)
from .template_import import TemplateImportFailure, digest, identity


def snapshot_identity(workspace):
    project = workspace.project
    if workspace.schema_version != 7 or project is None:
        raise TemplateImportFailure('IMPORT_PROJECT_NOT_AUTHORED')
    return TemplateSnapshotIdentity(projectId=workspace.project_id, projectRevision=workspace.project_revision,
        documentRevision=workspace.document_revision, documentHash=digest(project.document), factsHash=digest(project.facts),
        packageHash=project.template_package.package_hash,
        presentationHash=digest(presentation_value(project.document, project.template_package)))


def capture_export(workspace, expected, renderer, *, publication_intent_id=None, retry_capture=None, id_factory=identity):
    if retry_capture is None:
        snapshot = snapshot_identity(workspace)
        if snapshot != expected:
            raise TemplateImportFailure('IMPORT_EXPORT_SNAPSHOT_STALE')
        project = workspace.project
        request = TemplateRenderRequestV1(schemaVersion=1, renderInputVersion=1, document=project.document,
            facts=project.facts, documentHash=snapshot.document_hash, factsHash=snapshot.facts_hash,
            presentationHash=snapshot.presentation_hash, package=project.template_package, packageHash=snapshot.package_hash,
            assets=[TemplateRenderAsset(id=asset.id, path=asset.path, sha256=asset.sha256, size=asset.size)
                for asset in project.template_package.assets], renderer=renderer)
    else:
        if retry_capture.snapshot.project_id != workspace.project_id or retry_capture.request.renderer != renderer:
            raise TemplateImportFailure('IMPORT_EXPORT_SNAPSHOT_STALE')
        snapshot, request = retry_capture.snapshot, retry_capture.request
    attempt = ExportAttempt(id=id_factory('export'), state='pending', documentHash=request.document_hash,
        factsHash=request.facts_hash, presentationHash=request.presentation_hash, packageHash=request.package_hash,
        assetsHash=digest(request.assets), rendererHash=digest(request.renderer), artifactHash=None, errorCode=None,
        publicationIntentId=publication_intent_id)
    retained = CapturedTemplateRenderInputV1.model_validate(request.model_dump(by_alias=True, exclude={'package'}))
    return attempt, TemplateExportCapture(attemptId=attempt.id, snapshot=snapshot, request=retained)
