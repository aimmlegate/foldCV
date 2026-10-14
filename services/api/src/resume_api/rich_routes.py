"""Authenticated new-format endpoints, separate from retained legacy wire types."""

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.gui_projects import GuiCreateProjectRequest, GuiArchiveRequest
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rendering.template import RenderFailure
from .contracts import EmptyRequest
from .extracting import UploadFailure, parse_one_part
from .gui_projects import ProjectFailure


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
        current = service.generations.get(identifier)
        if current:
            await service.cancel(identifier, current.id)
        return response(identifier)

    @app.post(prefix + "/{identifier}/mutations")
    async def mutate(identifier: str, payload: RichMutation):
        return JSONResponse(service.mutate(identifier, payload).model_dump(mode="json", by_alias=True),
            headers={"Cache-Control": "no-store"})

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
