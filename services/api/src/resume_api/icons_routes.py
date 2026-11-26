"""The app's library of own Focus icons (D187): list, add and delete under /v2/icons. A résumé keeps its own copy of an
icon it uses, so a delete here never changes a résumé."""

from __future__ import annotations

import asyncio
import base64
import binascii

from pydantic import Field

from packages.resume_core.models.contracts import Wire
from resume_api.projects.errors import ProjectFailure
from resume_api.projects.routes import json_reply


class OwnIconRequestV1(Wire):
    name: str = Field(min_length=1, max_length=200)
    image: str = Field(min_length=4, max_length=2 * 1024 * 1024)


def mount_icon_routes(app, store):
    @app.get('/v2/icons')
    async def icons():
        return json_reply({'schemaVersion': 1, 'icons': await asyncio.to_thread(store.list)})

    @app.post('/v2/icons')
    async def add(payload: OwnIconRequestV1):
        try:
            data = base64.b64decode(payload.image, validate=True)
            icon = await asyncio.to_thread(store.add, payload.name, data)
        except (ValueError, binascii.Error) as error:
            code = str(error) if str(error).startswith(('IMAGE_', 'ICON_')) else 'IMAGE_INVALID'
            raise ProjectFailure(code, 422) from None
        return json_reply({'schemaVersion': 1, 'icon': icon}, 201)

    @app.delete('/v2/icons/{icon_id}')
    async def delete(icon_id: str):
        if not await asyncio.to_thread(store.delete, icon_id):
            raise ProjectFailure('ICON_NOT_FOUND', 404)
        return json_reply({'schemaVersion': 1})
