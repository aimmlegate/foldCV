"""Authenticated new-format endpoints, separate from retained legacy wire types."""

import asyncio
import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.gui_projects import GuiCreateProjectRequest, GuiStartGenerationRequest, GuiArchiveRequest, GuiRenameProjectRequest, GuiDeleteProjectRequest
from packages.resume_core.models.rich_mutations import RichMutation, ActionCapture
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_render import TemplateExportRequestV1
from packages.resume_core.models.contracts import Id, Wire
from packages.resume_core.rendering.template import RenderFailure
from .contracts import EmptyRequest
from .extracting import UploadFailure, parse_one_part
from .gui_projects import ProjectFailure
from .rich_assets import ImageSessionRequest, ImageUploadCapture
from .rewrite_timing import rewrite_timing
from .original_sources import mount_original_sources
from .template_responses import wire_response
from packages.resume_core.rich_sync import RichCompletionRequest, RichRewriteRequest, RichSyncDisposition
from packages.resume_core.text_rewrite import RichRewriteEditRequest
from packages.resume_core.rich_panel import RichPanelRequest, RichPanelSyncRequest
from packages.resume_core.rich_timeline import CascadeRequest, CascadeApplyRequest, timeline_report, cascade_proposal, cascade_mutation


class TemplateImportRequest(Wire):
    client_request_id: Id
    allow_text_rewrite: bool


def mount_rich_projects(app, service, problem):
    mount_original_sources(app, service)
    prefix = "/v1/rich/projects"
    def response(identifier, status=200):
        return wire_response(service.response(identifier), status=status)

    def legacy_fixed():
        jobs = getattr(service, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            from packages.resume_core.background_store import BackgroundFailure
            raise BackgroundFailure("JOB_SCOPE_INVALID")

    @app.get(prefix)
    async def projects():
        return JSONResponse(service.listing(), headers={"Cache-Control": "no-store"})

    @app.post(prefix)
    async def create(payload: GuiCreateProjectRequest):
        legacy_fixed()
        workspace = await service.select(payload.text.encode(), "pasted.txt", True)
        if service.durability(workspace.project_id) != "failed":
            service.start(workspace.project_id)
        return response(workspace.project_id, 202)

    @app.post(prefix + "/input")
    async def source(request: Request):
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get("content-type", ""))
        except UploadFailure as error:
            return problem(error.code, 422, "input")
        workspace = await service.select(data, name, pasted)
        return response(workspace.project_id, 201)

    @app.get("/v1/rich/template-import")
    async def template_import_status():
        return JSONResponse(service.template_import_status(), headers={"Cache-Control": "no-store"})

    @app.post(prefix + "/template-input")
    async def template_source(request: Request):
        # Strict template import: the upload becomes a V7 pre-draft with the store's active package.
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get("content-type", ""))
        except UploadFailure as error:
            return problem(error.code, 422, "input")
        workspace = await service.select_template(data, name, pasted)
        return response(workspace.project_id, 201)

    @app.post(prefix + "/{identifier}/template-import")
    async def template_import(identifier: str, payload: TemplateImportRequest):
        job, created = await service.start_template_import(identifier, payload.client_request_id, payload.allow_text_rewrite)
        return JSONResponse(job.model_dump(mode="json", by_alias=True), status_code=202 if created else 200,
            headers={"Cache-Control": "no-store"})

    @app.post(prefix + "/archive")
    async def portable_input(request: Request):
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get("content-type", ""), maximum=64 * 1024 * 1024)
            if pasted or not name.lower().endswith((".foldcv", ".zip")):
                return problem("ARCHIVE_FILE_UNSUPPORTED", 422, "archive")
        except UploadFailure as error:
            return problem(error.code, 422, "archive")
        return response(service.import_portable(data), 201)

    @app.get(prefix + "/{identifier}")
    async def read(identifier: str):
        return response(identifier)

    @app.post(prefix + "/{identifier}/activate")
    async def activate(identifier: str, _payload: EmptyRequest):
        return wire_response(service.activate(identifier))

    @app.post(prefix + "/{identifier}/catalog/archive")
    async def archive_entry(identifier: str, _payload: EmptyRequest):
        return JSONResponse(service.archive_entry(identifier, True), headers={"Cache-Control": "no-store"})

    @app.post(prefix + "/{identifier}/catalog/restore")
    async def restore_entry(identifier: str, _payload: EmptyRequest):
        return JSONResponse(service.archive_entry(identifier, False), headers={"Cache-Control": "no-store"})

    @app.put(prefix + "/{identifier}/title")
    async def rename(identifier: str, payload: GuiRenameProjectRequest):
        service.rename(identifier, payload)
        return response(identifier)

    @app.post(prefix + "/{identifier}/delete")
    async def delete(identifier: str, _payload: GuiDeleteProjectRequest):
        result = await service.delete_project(identifier)
        return JSONResponse(result.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.post(prefix + "/{identifier}/save")
    async def save(identifier: str, _payload: EmptyRequest):
        service.read(identifier); service.persist(identifier)
        return response(identifier)

    @app.post(prefix + "/{identifier}/generation")
    async def generation(identifier: str, payload: GuiStartGenerationRequest):
        legacy_fixed()
        service.start(identifier, allow_text_rewrite=payload.allow_text_rewrite)
        return response(identifier, 202)

    @app.post(prefix + "/{identifier}/cancel")
    async def cancel(identifier: str, _payload: EmptyRequest):
        exports = [key for key in getattr(service, 'template_export_keys', ()) if key[0] == identifier]
        if exports:
            for key in exports:
                await service.cancel(*key)
            return response(identifier)
        jobs = getattr(service, "background_jobs", None)
        generation = jobs.fixed.generation(identifier) if jobs is not None and jobs.enabled else None
        if generation is not None:
            await jobs.cancel(identifier, generation.id)
            control = jobs.supervisor.controls.get(generation.id)
            if control is not None and control.task is not None:
                await asyncio.shield(control.task)
            return response(identifier)
        for pid, operation in list(service.tasks):
            if pid == identifier:
                await service.cancel(identifier, operation)
        return response(identifier)

    @app.post(prefix + "/{identifier}/mutations")
    async def mutate(identifier: str, payload: RichMutation | TemplateMutationV1):
        return wire_response(service.mutate(identifier, payload))

    @app.post(prefix + "/{identifier}/preview")
    async def preview(identifier: str, payload: RichMutation | TemplateMutationV1):
        return wire_response(service.preview(identifier, payload))

    @app.post(prefix + "/{identifier}/completion")
    async def completion(identifier: str, payload: RichCompletionRequest):
        legacy_fixed()
        await service.complete_rich(identifier, payload)
        return response(identifier)

    @app.post(prefix + "/{identifier}/panel/preview")
    async def panel_preview(identifier: str, payload: RichPanelRequest):
        return wire_response(service.panel_preview(identifier, payload))

    @app.post(prefix + "/{identifier}/panel/sync")
    async def panel_sync(identifier: str, payload: RichPanelSyncRequest):
        legacy_fixed()
        await service.panel_rich(identifier, payload)
        return response(identifier)

    @app.get(prefix + "/{identifier}/timeline")
    async def timeline(identifier: str):
        try:
            report = timeline_report(service.read(identifier))
        except ValueError as error:
            raise ProjectFailure(str(error), 409) from None
        return JSONResponse(report.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.post(prefix + "/{identifier}/cascade")
    async def cascade(identifier: str, payload: CascadeRequest):
        try:
            proposal = cascade_proposal(service.read(identifier), payload)
        except ValueError as error:
            raise ProjectFailure(str(error), 409) from None
        return JSONResponse(proposal.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.post(prefix + "/{identifier}/cascade/preview")
    async def cascade_preview(identifier: str, payload: CascadeApplyRequest):
        try:
            mutation = cascade_mutation(service.read(identifier), payload)
        except ValueError as error:
            raise ProjectFailure(str(error), 409) from None
        return wire_response(service.preview(identifier, mutation))

    @app.post(prefix + "/{identifier}/rewrite/preview")
    async def rewrite_edit_preview(identifier: str, payload: RichRewriteEditRequest):
        return wire_response(service.rewrite_edit_preview(identifier, payload))

    @app.post(prefix + "/{identifier}/rewrite")
    async def rewrite(identifier: str, payload: RichRewriteRequest):
        legacy_fixed()
        with rewrite_timing(service.rules.root, len(payload.selection.block_ids)) as timing:
            result = await service.rewrite_rich(identifier, payload)
            timing.outcome = next(item.status for item in reversed(result.workspace.sync_records)
                if item.action_id == payload.selection.capture.action_id)
            return wire_response(result)

    @app.post(prefix + "/{identifier}/sync/{sync_id}")
    async def disposition(identifier: str, sync_id: str, payload: RichSyncDisposition):
        service.disposition(identifier, sync_id, payload.status, payload.error_code)
        return response(identifier)

    @app.post(prefix + "/{identifier}/sync/{sync_id}/resolve")
    async def resolve_conflict(identifier: str, sync_id: str, payload: ActionCapture):
        legacy_fixed()
        service.resolve_conflict(identifier, sync_id, payload)
        return response(identifier)

    @app.post(prefix + "/{identifier}/sync/{sync_id}/retry")
    async def retry_rewrite(identifier: str, sync_id: str, payload: ActionCapture):
        legacy_fixed()
        await service.retry_rewrite(identifier, sync_id, payload)
        return response(identifier)

    @app.post(prefix + "/{identifier}/cancel-action")
    async def cancel_action(identifier: str, payload: ActionCapture):
        await service.cancel_sync_action(identifier, payload)
        return response(identifier)

    @app.post(prefix + "/{identifier}/images/session")
    async def image_session(identifier: str, payload: ImageSessionRequest):
        service.update_image_session(identifier, payload)
        return response(identifier)

    @app.post(prefix + "/{identifier}/images/upload")
    async def image_upload(identifier: str, request: Request):
        from pydantic import ValidationError
        try:
            capture = ImageUploadCapture.model_validate({"sessionId": request.headers.get("x-foldcv-session"),
                "revision": int(request.headers.get("x-foldcv-revision", "0")), "actionId": request.headers.get("x-foldcv-action"),
                "reservationId": request.headers.get("x-foldcv-reservation"), "replacementId": request.headers.get("x-foldcv-replacement")})
            data, _, pasted = parse_one_part(await request.body(), request.headers.get("content-type", ""), maximum=10 * 1024 * 1024)
            if pasted:
                return problem("IMAGE_FORMAT_UNSUPPORTED", 422, "image")
        except (ValidationError, UploadFailure, ValueError) as error:
            return problem(getattr(error, "code", "INVALID_REQUEST"), 422, "image")
        asset_id = await service.ingest_image(identifier, data, capture)
        result = response(identifier, 201)
        result.headers["X-FoldCV-Asset"] = asset_id
        return result

    @app.get(prefix + "/{identifier}/images/{asset_id}")
    async def image_bytes(identifier: str, asset_id: str):
        workspace = service.read(identifier)
        asset = next((asset for asset in workspace.project.assets if asset.id == asset_id), None) if workspace.project else None
        blob = service.images.get((identifier, asset_id))
        if asset is None or blob is None:
            raise ProjectFailure("IMAGE_NOT_FOUND", 404)
        return Response(blob, media_type=asset.mime_type, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.post(prefix + "/{identifier}/export")
    async def export(identifier: str, payload: EmptyRequest | TemplateExportRequestV1):
        template = service.read(identifier).schema_version == 7
        if template != isinstance(payload, TemplateExportRequestV1):
            raise ProjectFailure('IMPORT_PROTOCOL_MISMATCH', 409)
        try:
            if template:
                return template_response(await service.export_template(identifier, payload.snapshot))
            snapshot, blob = await service.export(identifier)
        except RenderFailure as error:
            return problem(error.code, 422, "export")
        return Response(blob, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="resume.docx"',
                "X-FoldCV-Sha256": snapshot.docx_sha256})

    def template_response(result):
        return Response(result.artifact, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Cache-Control': 'no-store', 'Content-Disposition': 'attachment; filename="resume.docx"',
                'X-FoldCV-Sha256': result.attempt.artifact_hash, 'X-FoldCV-Export-Attempt': result.attempt.id,
                'X-FoldCV-Snapshot': json.dumps(result.snapshot.model_dump(mode='json', by_alias=True),
                    ensure_ascii=True, sort_keys=True, separators=(',', ':'))})

    @app.post(prefix + '/{identifier}/exports/{attempt_id}/retry')
    async def retry_export(identifier: str, attempt_id: str, _payload: EmptyRequest):
        return template_response(await service.export_template(identifier, None, retry_attempt_id=attempt_id))

    @app.post(prefix + "/{identifier}/archive")
    async def portable(identifier: str, payload: GuiArchiveRequest):
        workspace = service.read(identifier)
        if (workspace.project_revision, workspace.document_revision) != (payload.project_revision, payload.document_revision):
            raise ProjectFailure("STALE_ARCHIVE")
        return Response(service.portable(identifier), media_type="application/vnd.foldcv.project+zip",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="project.foldcv"'})
