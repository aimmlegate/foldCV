"""Template routes the workbench keeps on /v1: captured assets, the Settings template editor, import availability and
the upload that creates a V7 project (plan 2.4)."""

import asyncio
import base64
import re

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.storage import StorageFailure
from packages.resume_core.templates.models import asset_text, asset_type

from .extracting import UploadFailure, parse_one_part
from .host_models import EmptyRequest
from .template_config import TemplateConfig, TemplateConfigRequest
from .template_responses import wire_response


def mount_template_routes(app, *, root, intake, projects, problem):
    def config_reply(body, status=200):
        return JSONResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})

    @app.get('/v1/rich/template-assets/{digest}')
    async def template_asset(digest: str):
        # Captured fonts and icons by hash: immutable, so the browser keeps them instead of one copy per reply (D104).
        text = asset_text(digest) if re.fullmatch(r'[0-9a-f]{64}', digest) else None
        if text is None:
            return problem('TEMPLATE_ASSET_NOT_FOUND', 404, 'template')
        return Response(base64.b64decode(text), media_type=asset_type(digest) or 'application/octet-stream',
            headers={'Cache-Control': 'private, max-age=31536000, immutable'})

    @app.get('/v1/rich/template-import')
    async def template_import_status():
        return config_reply(intake.status())

    # Settings: the YAML of the active template for new imports. Projects keep the package they captured.
    @app.get('/v1/rich/template-config')
    async def template_config_read():
        return config_reply(await asyncio.to_thread(TemplateConfig(root).read))

    @app.post('/v1/rich/template-config/check')
    async def template_config_check(payload: TemplateConfigRequest):
        return config_reply(await asyncio.to_thread(TemplateConfig(root).check, payload.text))

    @app.put('/v1/rich/template-config')
    async def template_config_save(payload: TemplateConfigRequest):
        try:
            saved, refused = await asyncio.to_thread(TemplateConfig(root).save, payload.text)
        except StorageFailure:
            return problem('SAVE_FAILED', 500, 'template', True)
        return config_reply(refused, 422) if refused is not None else config_reply(saved)

    @app.post('/v1/rich/template-config/reset')
    async def template_config_reset(_payload: EmptyRequest):
        try:
            return config_reply(await asyncio.to_thread(TemplateConfig(root).reset))
        except StorageFailure:
            return problem('SAVE_FAILED', 500, 'template', True)

    @app.post('/v1/rich/projects/template-input')
    async def template_source(request: Request):
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get('content-type', ''))
        except UploadFailure as error:
            return problem(error.code, 422, 'input')
        project_id = await intake.create(data, name, pasted)
        return wire_response(await asyncio.to_thread(projects.response, project_id), status=201)
