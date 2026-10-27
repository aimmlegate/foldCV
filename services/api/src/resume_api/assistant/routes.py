"""The /v2 assistant routes (plan 2.8) and the assistant settings on /v1. Handlers run file work in worker threads
and never hold a project lock across an await."""

from __future__ import annotations

import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse

from packages.resume_core.assistant_store import AgentFailure
from packages.resume_core.models.agent import AgentSettingsRequest
from packages.resume_core.models.assistant import AssistantApplyRequestV1, AssistantRunRequestV2, AssistantSkillListV1, AssistantSkillV1
from packages.resume_core.models.assistant import AssistantChangeProposalListV1

from resume_api.projects.errors import ProjectFailure
from resume_api.projects.routes import file_reply, model_reply

from . import proposals
from .skills import skill_catalog

PREFIX = '/v2/projects/{project_id}/assistant'
MISSING = {'AGENT_NOT_FOUND', 'ASSISTANT_PROPOSAL_NOT_FOUND'}


def translated(error):
    return ProjectFailure(error.code, 404 if error.code in MISSING else 409)


async def worker(function, *args, **kwargs):
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except AgentFailure as error:
        raise translated(error) from None


def mount_assistant(app, service):
    @app.exception_handler(AgentFailure)
    async def agent_error(_request: Request, error: AgentFailure):
        status = (404 if error.code == 'AGENT_NOT_FOUND' else 410 if error.code == 'AGENT_PROJECT_DELETED' else
            503 if error.code in {'AGENT_STORE_UNAVAILABLE', 'AGENT_STORE_CORRUPT', 'AGENT_CLEANUP_FAILED'} else 409)
        return JSONResponse({'error': {'code': error.code}}, status_code=status, headers={'Cache-Control': 'no-store'})

    def settings_reply(value):
        return JSONResponse(value.model_dump(mode='json', by_alias=True), headers={'Cache-Control': 'no-store'})

    @app.get('/v1/settings/assistant')
    async def settings():
        return settings_reply(service.settings.load())

    @app.put('/v1/settings/assistant')
    async def save_settings(payload: AgentSettingsRequest):
        prior = service.settings.load()
        saved = service.settings.save(payload, service.connection().models or None)
        if prior.enabled and not saved.enabled:
            service.stop_all()
        return settings_reply(saved)

    @app.get(PREFIX + '/capabilities')
    async def capabilities(project_id: str):
        return model_reply(await worker(service.capabilities))

    @app.get(PREFIX + '/conversations')
    async def conversations(project_id: str):
        return model_reply(await worker(service.conversations, project_id))

    @app.post(PREFIX + '/conversations')
    async def create_conversation(project_id: str):
        return model_reply(await worker(service.create_conversation, project_id), 201)

    @app.get(PREFIX + '/conversations/{conversation_id}/messages')
    async def messages(project_id: str, conversation_id: str):
        return model_reply(await worker(service.messages, project_id, conversation_id))

    @app.post(PREFIX + '/conversations/{conversation_id}/runs')
    async def submit(project_id: str, conversation_id: str, payload: AssistantRunRequestV2):
        try:
            return model_reply(service.submit(project_id, conversation_id, payload), 201)
        except AgentFailure as error:
            raise translated(error) from None

    # The boundary refuses query strings, so the cursor is a path segment; the wait is the service's.
    @app.get(PREFIX + '/runs/{run_id}/events/{after}')
    async def events(project_id: str, run_id: str, after: int):
        try:
            return model_reply(await service.events(project_id, run_id, max(0, after)))
        except AgentFailure as error:
            raise translated(error) from None

    @app.post(PREFIX + '/runs/{run_id}/cancel')
    async def cancel(project_id: str, run_id: str):
        try:
            return model_reply(service.cancel(project_id, run_id))
        except AgentFailure as error:
            raise translated(error) from None

    @app.get(PREFIX + '/proposals')
    async def list_proposals(project_id: str):
        items = await worker(service.store.proposals, project_id)
        return model_reply(AssistantChangeProposalListV1(items=items[-100:]))

    @app.get(PREFIX + '/proposals/{proposal_id}')
    async def proposal(project_id: str, proposal_id: str):
        return model_reply(await worker(service.store.proposal, project_id, proposal_id))

    @app.post(PREFIX + '/proposals/{proposal_id}/apply')
    async def apply(project_id: str, proposal_id: str, payload: AssistantApplyRequestV1):
        return model_reply(await worker(proposals.apply, service, project_id, proposal_id, payload))

    @app.post(PREFIX + '/proposals/{proposal_id}/discard')
    async def discard(project_id: str, proposal_id: str):
        return model_reply(await worker(proposals.discard, service, project_id, proposal_id))

    @app.get(PREFIX + '/skills')
    async def skills(project_id: str):
        return model_reply(AssistantSkillListV1(items=[AssistantSkillV1(id=item['id'], title=item['title'],
            description=item['description']) for item in skill_catalog()]))

    @app.get(PREFIX + '/files/{file_id}')
    async def file(project_id: str, file_id: str):
        filename, media, data = service.file(project_id, file_id)
        return file_reply(data, media, {'Content-Disposition': f'attachment; filename="{filename}"'})
