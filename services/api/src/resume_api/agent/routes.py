"""Same-origin browser routes are separate from the private MCP capability."""

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from packages.resume_core.agent_store import AgentFailure, conversation_in, run_in
from packages.resume_core.models.agent import (
    AgentEmptyRequest, AgentSettingsRequest, AgentPageRequest, AgentLeaseOpen, AgentOwnerRequest,
    AgentRunRequest, AgentEventsRequest, AgentRunRead, AgentCommitRequest, AgentResultRequest,
)


def mount_agent(app, service):
    prefix = "/v1/rich/projects/{project_id}/assistant"
    def response(value, status=200):
        return JSONResponse(value.model_dump(mode="json", by_alias=True), status_code=status, headers={"Cache-Control": "no-store"})

    @app.exception_handler(AgentFailure)
    async def agent_error(_request: Request, error: AgentFailure):
        status = (404 if error.code == "AGENT_NOT_FOUND" else 410 if error.code == "AGENT_PROJECT_DELETED" else
            503 if error.code in {"AGENT_STORE_UNAVAILABLE", "AGENT_STORE_CORRUPT", "AGENT_CLEANUP_FAILED"} else 409)
        return JSONResponse({"error": {"code": error.code}}, status_code=status, headers={"Cache-Control": "no-store"})

    def project(project_id):
        value = service.projects.read(project_id)
        if value.project is None:
            raise AgentFailure("AGENT_NOT_FOUND")
        return value

    def owned_run(project_id, run_id):
        project(project_id)
        return run_in(service.store.load(project_id), run_id)

    @app.get("/v1/settings/assistant")
    async def settings():
        return response(service.settings.load())

    @app.put("/v1/settings/assistant")
    async def save_settings(payload: AgentSettingsRequest):
        prior = service.settings.load()
        connection = service.connection()
        saved = service.settings.save(payload, connection.models or None)
        if prior.enabled and not saved.enabled:
            await service.stop_all(reason="AGENT_DISABLED")
        return response(saved)

    @app.get(prefix + "/capabilities")
    async def capabilities(project_id: str, request: Request):
        project(project_id)
        values = {}
        for header, name in (("x-foldcv-agent-edits", "allow_edits"), ("x-foldcv-agent-web", "allow_web")):
            matches = [value for key, value in request.headers.raw if key.decode().lower() == header]
            if len(matches) > 1 or matches and matches[0] not in {b"0", b"1"}:
                raise AgentFailure("AGENT_TOOL_DENIED")
            values[name] = not matches or matches[0] == b"1"
        return response(service.capabilities(project_id, **values))

    @app.post(prefix + "/conversations/read")
    async def conversations(project_id: str, payload: AgentPageRequest):
        project(project_id)
        return response(service.store.conversations_page(project_id, payload))

    @app.post(prefix + "/conversations")
    async def conversation(project_id: str, payload: AgentEmptyRequest):
        project(project_id)
        return response(service.store.create_conversation(project_id), 201)

    @app.post(prefix + "/conversations/{conversation_id}/read")
    async def messages(project_id: str, conversation_id: str, payload: AgentPageRequest):
        project(project_id)
        return response(service.store.latest_messages_page(project_id, conversation_id, payload))

    @app.post(prefix + "/conversations/{conversation_id}/sources/read")
    async def sources(project_id: str, conversation_id: str, payload: AgentPageRequest):
        project(project_id)
        return response(service.store.page(project_id, conversation_id, "sources", payload))

    @app.post(prefix + "/conversations/{conversation_id}/findings/read")
    async def findings(project_id: str, conversation_id: str, payload: AgentPageRequest):
        project(project_id)
        return response(service.store.page(project_id, conversation_id, "findings", payload))

    @app.post(prefix + "/lease/open")
    async def open_lease(project_id: str, payload: AgentLeaseOpen):
        project(project_id)
        return response(service.leases.open(project_id, payload.session_id))

    @app.post(prefix + "/lease/renew")
    async def renew_lease(project_id: str, payload: AgentOwnerRequest):
        project(project_id)
        return response(service.leases.renew(project_id, payload.owner))

    @app.post(prefix + "/lease/close")
    async def close_lease(project_id: str, payload: AgentOwnerRequest):
        project(project_id)
        service.leases.close(project_id, payload.owner)
        service.request_project_stop(project_id, reason="AGENT_INTERRUPTED")
        await service.stop_project(project_id)
        return response(AgentEmptyRequest())

    @app.post(prefix + "/conversations/{conversation_id}/runs")
    async def submit(project_id: str, conversation_id: str, payload: AgentRunRequest):
        project(project_id)
        conversation_in(service.store.load(project_id), conversation_id)
        if payload.conversation_id != conversation_id:
            raise AgentFailure("AGENT_NOT_FOUND")
        run, created = service.submit(project_id, payload)
        service.start(project_id, run.id)
        return response(run, 202 if created else 200)

    @app.post(prefix + "/runs/{run_id}/events")
    async def events(project_id: str, run_id: str, payload: AgentEventsRequest):
        owned_run(project_id, run_id)
        service.events.owner(service, project_id, run_id, payload)
        return StreamingResponse(service.events.stream(service, project_id, run_id, payload),
            media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.post(prefix + "/runs/{run_id}/read")
    async def read_run(project_id: str, run_id: str, payload: AgentEmptyRequest):
        _, run, journal = owned_run(project_id, run_id)
        for item in journal.batches:
            if item.batch is not None and item.batch.state in {"applying", "outcome_unknown"}:
                try:
                    service.publication.recover(project_id, run_id, item.batch.id)
                except AgentFailure as error:
                    if error.code != "AGENT_OUTCOME_UNKNOWN":
                        raise
        _, run, journal = owned_run(project_id, run_id)
        return response(AgentRunRead(run=run, receipts=[item.receipt for item in journal.batches if item.receipt is not None]))

    @app.post(prefix + "/runs/{run_id}/cancel")
    async def cancel(project_id: str, run_id: str, payload: AgentOwnerRequest):
        _, run, _ = owned_run(project_id, run_id)
        service.leases.require(project_id, payload.owner, epoch=run.owner_epoch)
        return response(service.cancel(project_id, run_id))

    @app.post(prefix + "/runs/{run_id}/edits/{batch_id}/claim")
    async def claim(project_id: str, run_id: str, batch_id: str, payload: AgentOwnerRequest):
        owned_run(project_id, run_id)
        return response(service.publication.claim(project_id, run_id, batch_id, payload.owner))

    @app.post(prefix + "/runs/{run_id}/edits/{batch_id}/commit")
    async def commit(project_id: str, run_id: str, batch_id: str, payload: AgentCommitRequest):
        owned_run(project_id, run_id)
        return response(service.publication.commit(project_id, run_id, batch_id, payload))

    @app.post(prefix + "/runs/{run_id}/edits/{batch_id}/result")
    async def result(project_id: str, run_id: str, batch_id: str, payload: AgentResultRequest):
        owned_run(project_id, run_id)
        return response(service.publication.report(project_id, run_id, batch_id, payload))
