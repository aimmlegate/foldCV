"""Rewrite preview and cancel. The model call is the existing one; the writer proof is not."""

from __future__ import annotations

import asyncio

from packages.resume_core.models.projects import TemplateRewritePreviewV1
from packages.resume_core.template_rewrite import rewrite_source

from .errors import ProjectFailure


def preview_source(service, project_id, payload):
    session = service.repository.open(project_id)
    with session.lock:
        session.require_editor(payload.editor_token)
        try:
            return rewrite_source(session.workspace, payload)
        except ValueError:
            raise ProjectFailure('V7_INPUT_REJECTED', 422) from None


async def preview(service, project_id, payload):
    selected = await asyncio.to_thread(preview_source, service, project_id, payload)
    task = service.tasks.start(project_id, 'rewrite', stage='queued', detail={'requestId': payload.request_id})
    try:
        text = await service.rewrite_text(project_id, payload.request_id, payload.instruction, selected,
            lambda: service.tasks.update(task.id, stage='generating'))
    except BaseException as error:
        code = getattr(error, 'code', 'PROCESS_FAILED')
        service.tasks.finish(task.id, 'cancelled' if code == 'CANCELLED' else 'failed', error=code)
        raise
    service.tasks.finish(task.id, 'succeeded')
    return TemplateRewritePreviewV1(schemaVersion=1, requestId=payload.request_id, snapshot=payload.snapshot,
        range=payload.range, source=selected, text=text)


def cancel(service, project_id, payload):
    service.repository.open(project_id).require_editor(payload.editor_token)
    return {'cancelled': service.rewrite_cancel(project_id, payload.request_id)}
