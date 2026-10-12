"""Protected project endpoints, mounted inside the existing local boundary."""

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.gui_projects import GuiCreateProjectRequest, GuiStartGenerationRequest, GuiProjectResponse
from .contracts import EmptyRequest
from .extracting import parse_one_part, UploadFailure
from .gui_projects import ProjectFailure


def mount_projects(app, service, problem):
    def response(id, generation_id=None, status=200):
        payload = GuiProjectResponse(workspace=service.read(id), durability="in_memory", generationId=generation_id)
        return JSONResponse(payload.model_dump(mode="json", by_alias=True), status_code=status, headers={"Cache-Control": "no-store"})

    @app.exception_handler(ProjectFailure)
    async def project_error(_request: Request, error: ProjectFailure):
        return problem(error.code, error.status, "project")

    @app.post("/v1/projects")
    async def create(payload: GuiCreateProjectRequest):
        workspace = await service.select(payload.text.encode("utf-8"), "pasted.txt", True)
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
