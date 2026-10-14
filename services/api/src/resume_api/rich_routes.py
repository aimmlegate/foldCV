"""Authenticated new-format endpoints, separate from retained legacy wire types."""

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.gui_projects import GuiCreateProjectRequest, GuiArchiveRequest, GuiRenameProjectRequest, GuiDeleteProjectRequest
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rendering.template import RenderFailure
from .contracts import EmptyRequest
from .extracting import UploadFailure, parse_one_part
from .gui_projects import ProjectFailure
from .rich_assets import ImageSessionRequest, ImageUploadCapture


def mount_rich_projects(app, service, problem):
    prefix = "/v1/rich/projects"
    def response(identifier, status=200):
        return JSONResponse(service.response(identifier).model_dump(mode="json", by_alias=True),
            status_code=status, headers={"Cache-Control": "no-store"})

    @app.get(prefix)
    async def projects():
        service.ensure_loaded()
        registry = service.storage.registry()
        return JSONResponse({"entries": [e.model_dump(mode="json", by_alias=True) for e in registry.entries if not e.tombstoned],
            "errors": [{"projectId": identifier, "errorCode": code} for identifier, code in service.load_errors.items()]},
            headers={"Cache-Control": "no-store"})

    @app.post(prefix)
    async def create(payload: GuiCreateProjectRequest):
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
    async def generation(identifier: str, _payload: EmptyRequest):
        service.start(identifier)
        return response(identifier, 202)

    @app.post(prefix + "/{identifier}/cancel")
    async def cancel(identifier: str, _payload: EmptyRequest):
        for pid, operation in list(service.tasks):
            if pid == identifier:
                await service.cancel(identifier, operation)
        return response(identifier)

    @app.post(prefix + "/{identifier}/mutations")
    async def mutate(identifier: str, payload: RichMutation):
        return JSONResponse(service.mutate(identifier, payload).model_dump(mode="json", by_alias=True),
            headers={"Cache-Control": "no-store"})

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
    async def export(identifier: str, _payload: EmptyRequest):
        try:
            snapshot, blob = await service.export(identifier)
        except RenderFailure as error:
            return problem(error.code, 422, "export")
        return Response(blob, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="resume.docx"',
                "X-FoldCV-Sha256": snapshot.docx_sha256})

    @app.post(prefix + "/{identifier}/archive")
    async def portable(identifier: str, payload: GuiArchiveRequest):
        workspace = service.read(identifier)
        if (workspace.project_revision, workspace.document_revision) != (payload.project_revision, payload.document_revision):
            raise ProjectFailure("STALE_ARCHIVE")
        return Response(service.portable(identifier), media_type="application/vnd.foldcv.project+zip",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="project.foldcv"'})
