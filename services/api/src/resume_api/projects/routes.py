"""The /v2 project routes. Handlers run the synchronous repository work in a worker thread and never hold a project lock
across an await (D109, plan 2.4).

.foldcv owns POST /archive (download) and POST /v2/projects/archive (upload). Catalog flags are
POST /catalog/archive and POST /catalog/restore. POST /restore stays catalog restore.
"""

import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.models.projects import (ClipboardCaptureRequestV1, DeleteRequestV1, EditRequestV1,
    HistoryRequestV1, ProjectCheckRequestV1, RenameRequestV1, RewritePreviewRequestV1, RewriteCancelRequestV1)
from packages.resume_core.project_limits import ARCHIVE_BYTES

from . import check, clipboard, editing, images, rewrite, sources
from .archive import ArchiveDownload, export_archive, import_archive
from .errors import ProjectFailure, mount_errors
from .exports import ExportCommand, ExportRetry
from .imports import ImportCommand

PREFIX = '/v2/projects'
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
FOLD = 'application/vnd.foldcv.project+zip'


def model_reply(value, status=200):
    return Response(value.model_dump_json(by_alias=True), status_code=status, media_type='application/json',
        headers={'Cache-Control': 'no-store'})


def json_reply(value, status=200):
    return JSONResponse(value, status_code=status, headers={'Cache-Control': 'no-store'})


def file_reply(data, media_type, headers):
    return Response(data, media_type=media_type, headers={'Cache-Control': 'no-store', **headers})


def mount_projects_v2(app, service):
    mount_errors(app)

    @app.post(PREFIX + '/archive')
    async def import_foldcv(request: Request):
        from ..extracting import UploadFailure, parse_one_part
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get('content-type', ''),
                maximum=ARCHIVE_BYTES)
        except UploadFailure as error:
            raise ProjectFailure(error.code, 422) from None
        if pasted or not name.lower().endswith(('.foldcv', '.zip')):
            raise ProjectFailure('ARCHIVE_FILE_UNSUPPORTED', 422)
        return model_reply(await asyncio.to_thread(import_archive, service, data), 201)

    @app.get(PREFIX)
    async def listing():
        return json_reply(await asyncio.to_thread(service.listing))

    @app.post(PREFIX + '/{project_id}/open')
    async def open_project(project_id: str):
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

    @app.post(PREFIX + '/{project_id}/check')
    async def check_project(project_id: str, payload: ProjectCheckRequestV1):
        return model_reply(await asyncio.to_thread(check.run, service, project_id, payload))

    @app.post(PREFIX + '/{project_id}/rewrite/preview')
    async def preview_rewrite(project_id: str, payload: RewritePreviewRequestV1):
        return model_reply(await rewrite.preview(service, project_id, payload))

    @app.post(PREFIX + '/{project_id}/rewrite/cancel')
    async def cancel_rewrite(project_id: str, payload: RewriteCancelRequestV1):
        return json_reply(await asyncio.to_thread(rewrite.cancel, service, project_id, payload))

    @app.post(PREFIX + '/{project_id}/import')
    async def import_task(project_id: str, payload: ImportCommand):
        if payload.kind == 'cancel':
            return json_reply(await service.imports.cancel(project_id, payload))
        started = asyncio.Event()
        task_id = await service.imports.start(project_id, payload, started)
        try:
            await asyncio.wait_for(started.wait(), 30)
        except asyncio.TimeoutError:
            # The task is registered and still running: the client follows it through /tasks, as it does a waiting one.
            pass
        found = next(item for item in service.tasks.list(project_id) if item['id'] == task_id)
        return json_reply(found, 202)

    @app.post(PREFIX + '/{project_id}/export')
    async def export(project_id: str, payload: ExportCommand):
        result = await service.exports.export(project_id, payload.snapshot, payload.editor_token)
        return _export_reply(result)

    @app.post(PREFIX + '/{project_id}/exports/{attempt_id}/retry')
    async def retry_export(project_id: str, attempt_id: str, payload: ExportRetry):
        result = await service.exports.export(project_id, None, payload.editor_token, retry_attempt_id=attempt_id)
        return _export_reply(result)

    @app.post(PREFIX + '/{project_id}/archive')
    async def download_archive(project_id: str, payload: ArchiveDownload):
        data = await asyncio.to_thread(export_archive, service, project_id, payload)
        return file_reply(data, FOLD, {'Content-Disposition': 'attachment; filename="project.foldcv"'})

    @app.post(PREFIX + '/{project_id}/catalog/archive')
    async def catalog_archive(project_id: str):
        return json_reply(await asyncio.to_thread(service.archive, project_id, True))

    @app.post(PREFIX + '/{project_id}/catalog/restore')
    async def catalog_restore(project_id: str):
        return json_reply(await asyncio.to_thread(service.archive, project_id, False))

    @app.post(PREFIX + '/{project_id}/restore')
    async def restore(project_id: str):
        return json_reply(await asyncio.to_thread(service.archive, project_id, False))

    @app.delete(PREFIX + '/{project_id}')
    async def delete(project_id: str, payload: DeleteRequestV1):
        return json_reply(await asyncio.to_thread(service.delete, project_id, payload))

    @app.post(PREFIX + '/{project_id}/rename')
    async def rename(project_id: str, payload: RenameRequestV1):
        return model_reply(await asyncio.to_thread(service.rename, project_id, payload))

    @app.get(PREFIX + '/{project_id}/tasks')
    async def tasks(project_id: str):
        return json_reply({'schemaVersion': 1, 'tasks': await asyncio.to_thread(service.imports.statuses, project_id)})

    @app.get(PREFIX + '/{project_id}/images/{sha}')
    async def image(project_id: str, sha: str):
        return await asyncio.to_thread(images.image_bytes, service, project_id, sha)

    @app.get(PREFIX + '/{project_id}/sources/{source_id}/original')
    async def original(project_id: str, source_id: str):
        return await asyncio.to_thread(sources.original, service, project_id, source_id)

    @app.get(PREFIX + '/{project_id}/sources/{source_id}/original/download')
    async def original_download(project_id: str, source_id: str):
        return await asyncio.to_thread(sources.original, service, project_id, source_id, download=True)


def _export_reply(result):
    import json
    return file_reply(result.artifact, DOCX, {
        'Content-Disposition': 'attachment; filename="resume.docx"',
        'X-FoldCV-Sha256': result.attempt.artifact_hash,
        'X-FoldCV-Export-Attempt': result.attempt.id,
        'X-FoldCV-Snapshot': json.dumps(result.snapshot.model_dump(mode='json', by_alias=True),
            ensure_ascii=True, sort_keys=True, separators=(',', ':')),
    })
