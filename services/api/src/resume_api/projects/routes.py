"""The /v2 project routes. Handlers run the synchronous repository work in a worker thread and never hold a project lock
across an await (D109, plan 2.4)."""

import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.models.projects import (ClipboardCaptureRequestV1, DeleteRequestV1, EditRequestV1,
    HistoryRequestV1, RenameRequestV1)

from . import clipboard, editing
from .errors import mount_errors

PREFIX = '/v2/projects'


def model_reply(value, status=200):
    return Response(value.model_dump_json(by_alias=True), status_code=status, media_type='application/json',
        headers={'Cache-Control': 'no-store'})


def json_reply(value, status=200):
    return JSONResponse(value, status_code=status, headers={'Cache-Control': 'no-store'})


def mount_projects_v2(app, service):
    mount_errors(app)

    @app.get(PREFIX)
    async def listing():
        return json_reply(await asyncio.to_thread(service.listing))

    @app.post(PREFIX + '/{project_id}/open')
    async def open_project(project_id: str, request: Request):
        return model_reply(await asyncio.to_thread(service.open, project_id))

    @app.get(PREFIX + '/{project_id}')
    async def read(project_id: str):
        return model_reply(await asyncio.to_thread(service.read, project_id))

    @app.post(PREFIX + '/{project_id}/edits')
    async def edit(project_id: str, payload: EditRequestV1):
        return model_reply(await asyncio.to_thread(editing.edit, service, project_id, payload))

    @app.post(PREFIX + '/{project_id}/history')
    async def history(project_id: str, payload: HistoryRequestV1):
        return model_reply(await asyncio.to_thread(editing.history, service, project_id, payload))

    @app.post(PREFIX + '/{project_id}/clipboard')
    async def capture(project_id: str, payload: ClipboardCaptureRequestV1):
        return model_reply(await asyncio.to_thread(clipboard.capture, service, project_id, payload))

    @app.post(PREFIX + '/{project_id}/rename')
    async def rename(project_id: str, payload: RenameRequestV1):
        return model_reply(await asyncio.to_thread(service.rename, project_id, payload))

    @app.post(PREFIX + '/{project_id}/archive')
    async def archive(project_id: str):
        return json_reply(await asyncio.to_thread(service.archive, project_id, True))

    @app.post(PREFIX + '/{project_id}/restore')
    async def restore(project_id: str):
        return json_reply(await asyncio.to_thread(service.archive, project_id, False))

    @app.delete(PREFIX + '/{project_id}')
    async def delete(project_id: str, payload: DeleteRequestV1):
        return json_reply(await asyncio.to_thread(service.delete, project_id, payload))

    @app.get(PREFIX + '/{project_id}/tasks')
    async def tasks(project_id: str):
        return json_reply({'schemaVersion': 1, 'tasks': await asyncio.to_thread(service.tasks.list, project_id)})
