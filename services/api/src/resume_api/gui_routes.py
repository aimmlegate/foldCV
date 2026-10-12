"""Protected project endpoints, mounted inside the existing local boundary."""

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.gui_projects import GuiCreateProjectRequest, GuiStartGenerationRequest, GuiProjectResponse, GuiRenameProjectRequest
from packages.resume_core.gui_selection import selection_fingerprint
from packages.resume_core.gui_source_context import source_context
from packages.resume_core.models.recovery import SourceContextRequest, Mutation
from packages.resume_core.gui_rewriting import GuiRewriteRequest
from packages.resume_core.gui_exports import GuiExportRequest
from packages.resume_core.gui_reconciliation import GuiAnalysisRequest
from .contracts import EmptyRequest
from .extracting import parse_one_part, UploadFailure
from .gui_projects import ProjectFailure


def mount_projects(app, service, problem):
    def response(id, generation_id=None, status=200):
        workspace = service.read(id)
        saved = service.saved_revisions.get(id)
        payload = GuiProjectResponse(workspace=workspace, durability=service.durability(id), generationId=generation_id,
            selectionFingerprint=selection_fingerprint(workspace), savedProjectRevision=saved[0] if saved else None,
            savedDocumentRevision=saved[1] if saved else None, saveError=service.save_errors.get(id))
        return JSONResponse(payload.model_dump(mode="json", by_alias=True), status_code=status, headers={"Cache-Control": "no-store"})

    @app.exception_handler(ProjectFailure)
    async def project_error(_request: Request, error: ProjectFailure):
        return problem(error.code, error.status, "project")

    @app.post("/v1/projects")
    async def create(payload: GuiCreateProjectRequest):
        workspace = await service.select(payload.text.encode("utf-8"), "pasted.txt", True)
        if service.durability(workspace.project_id) == "failed":
            return response(workspace.project_id, status=201)
        return response(workspace.project_id, service.start(workspace.project_id), 202)

    async def upload(request, id=None):
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get("content-type", ""))
        except UploadFailure as error:
            return problem(error.code, 413 if error.code == "INPUT_TOO_LARGE" else 422)
        workspace = await service.select(data, name, pasted, id)
        return response(workspace.project_id, status=201 if id is None else 200)

    @app.post("/v1/projects/input")
    async def select_file(request: Request):
        return await upload(request)

    @app.put("/v1/projects/{id}/input")
    async def replace_file(id: str, request: Request):
        service.read(id)
        return await upload(request, id)

    @app.get("/v1/projects/{id}")
    async def read(id: str):
        return response(id)

    @app.post("/v1/projects/{id}/source-context")
    async def context(id: str, payload: SourceContextRequest):
        result = source_context(service.read(id), payload)
        return JSONResponse(result.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.post("/v1/projects/{id}/mutations")
    async def mutate(id: str, payload: Mutation):
        result = service.mutate(id, payload)
        return JSONResponse(result.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.post("/v1/projects/{id}/rewrite")
    async def rewrite(id: str, payload: GuiRewriteRequest):
        result = await service.rewrite(id, payload)
        return JSONResponse(result.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.post("/v1/projects/{id}/analysis")
    async def analysis(id: str, payload: GuiAnalysisRequest):
        await service.analysis_action(id, payload)
        return response(id)

    @app.post("/v1/projects/{id}/exports")
    async def export(id: str, payload: GuiExportRequest):
        service.start_export(id, payload)
        return response(id, status=202)

    @app.get("/v1/projects/{id}/exports/{oid}/docx")
    async def export_artifact(id: str, oid: str):
        content = service.export_artifact(id, oid)
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="resume.docx"'})

    @app.post("/v1/projects/{id}/operations/{oid}/cancel")
    async def cancel_operation(id: str, oid: str, _payload: EmptyRequest):
        await service.cancel(id, oid)
        return response(id)

    @app.patch("/v1/projects/{id}/metadata")
    async def metadata(id: str, payload: GuiRenameProjectRequest):
        service.rename(id, payload)
        return response(id)

    @app.post("/v1/projects/{id}/save")
    async def save(id: str, _payload: EmptyRequest):
        service.read(id)
        service.persist(id)
        return response(id)

    @app.post("/v1/projects/{id}/generations")
    async def start(id: str, payload: GuiStartGenerationRequest):
        service.read(id)
        if payload.text is not None:
            await service.select(payload.text.encode("utf-8"), "pasted.txt", True, id)
        return response(id, service.start(id), 202)

    @app.get("/v1/projects/{id}/generations/{gid}")
    async def generation(id: str, gid: str):
        return JSONResponse(service.generation(id, gid).model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.post("/v1/projects/{id}/generations/{gid}/cancel")
    async def cancel(id: str, gid: str, _payload: EmptyRequest):
        await service.cancel(id, gid)
        return response(id, gid)

    @app.post("/v1/projects/{id}/generations/{gid}/retry")
    async def retry(id: str, gid: str, _payload: EmptyRequest):
        return response(id, service.start(id, gid), 202)

    @app.get("/v1/projects/{id}/operations/{oid}")
    async def operation(id: str, oid: str):
        workspace = service.read(id)
        value = next((item for item in service.owner(workspace).operations if item.id == oid), None)
        if value is None:
            raise ProjectFailure("OPERATION_NOT_FOUND", 404)
        return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.get("/v1/projects/{id}/renders/{rid}")
    async def render(id: str, rid: str):
        workspace = service.read(id)
        value = next((item for item in service.owner(workspace).renders if item.id == rid), None)
        if value is None:
            raise ProjectFailure("RENDER_NOT_FOUND", 404)
        return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.get("/v1/projects/{id}/renders/{rid}/docx")
    async def artifact(id: str, rid: str):
        service.read(id)
        content = service.artifacts.get((id, rid))
        if content is None:
            raise ProjectFailure("ARTIFACT_UNAVAILABLE", 404)
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="resume.docx"'})
