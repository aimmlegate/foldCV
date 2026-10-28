"""Template routes the workbench keeps on /v1: captured assets, the Settings template editor, the templates offered for
import and the upload that creates a V7 project with one of them (plan 2.4)."""

import asyncio
import base64
import re

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from packages.resume_core.storage import StorageFailure
from packages.resume_core.templates.models import asset_text, asset_type
from packages.resume_core.templates.store import UnknownTemplate

from .extracting import UploadFailure, parse_one_part
from .host_models import EmptyRequest
from .template_config import TemplateConfig, TemplateConfigRequest, TemplateDefaultRequest
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
        return config_reply(await asyncio.to_thread(intake.status))

    async def config_call(method, *args, write=False):
        """`method`'s reply, or a refusal of a template id nobody has; a write names a storage failure."""
        try:
            reply = await asyncio.to_thread(method, *args)
        except UnknownTemplate:
            return problem('TEMPLATE_NOT_FOUND', 404, 'template')
        except StorageFailure:
            if not write:
                raise
            return problem('SAVE_FAILED', 500, 'template', True)
        return reply if isinstance(reply, JSONResponse) else config_reply(reply)

    # Settings: the YAML of each template and the default one for new imports. Projects keep the package they captured.
    @app.get('/v1/rich/template-config')
    async def template_config_list():
        return config_reply({'schemaVersion': 1, **await asyncio.to_thread(TemplateConfig(root).catalog)})

    @app.put('/v1/rich/template-default')
    async def template_default(payload: TemplateDefaultRequest):
        return await config_call(TemplateConfig(root).set_default, payload.template_id, write=True)

    @app.get('/v1/rich/template-config/{template_id}')
    async def template_config_read(template_id: str):
        return await config_call(TemplateConfig(root).read, template_id)

    @app.post('/v1/rich/template-config/{template_id}/check')
    async def template_config_check(template_id: str, payload: TemplateConfigRequest):
        return await config_call(TemplateConfig(root).check, template_id, payload.text)

    @app.put('/v1/rich/template-config/{template_id}')
    async def template_config_save(template_id: str, payload: TemplateConfigRequest):
        def save():
            saved, refused = TemplateConfig(root).save(template_id, payload.text)
            return config_reply(refused, 422) if refused is not None else saved
        return await config_call(save, write=True)

    @app.post('/v1/rich/template-config/{template_id}/reset')
    async def template_config_reset(template_id: str, _payload: EmptyRequest):
        return await config_call(TemplateConfig(root).reset, template_id, write=True)

    async def create_from_upload(request, template_id):
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get('content-type', ''))
        except UploadFailure as error:
            return problem(error.code, 422, 'input')
        project_id = await intake.create(data, name, pasted, template_id)
        return wire_response(await asyncio.to_thread(projects.response, project_id), status=201)

    @app.post('/v1/rich/projects/template-input')
    async def template_source(request: Request):
        return await create_from_upload(request, None)

    @app.post('/v1/rich/projects/template-input/{template_id}')
    async def template_source_with(template_id: str, request: Request):
        return await create_from_upload(request, template_id)
