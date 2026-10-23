"""Same-origin browser routes are separate from the private MCP capability."""

from fastapi import Request
from asyncio import to_thread
from fastapi.responses import JSONResponse, StreamingResponse, Response

from packages.resume_core.agent_store import AgentFailure, conversation_in, run_in
from packages.resume_core.models.agent import (
    AgentEmptyRequest, AgentSettingsRequest, AgentPageRequest, AgentLeaseOpen, AgentOwnerRequest,
    AgentRunRequest, AgentEventsRequest, AgentRunRead, AgentCommitRequest, AgentResultRequest,
    AgentAccess, AgentAccessRequest,
    AgentHistoryOffer,
    AgentProjectOperation, AgentProjectOperations,
)
from packages.resume_core.models.assistant_capabilities import AssistantMessageCheckV1
from packages.resume_core.models.assistant_proposals import AssistantProposalListV1, AssistantProposalRequestV1, AssistantReviewListV1
from packages.resume_core.models.assistant_approval import (AssistantAcceptanceV1, AssistantApplicationCommitV1,
    AssistantApplicationReportV1, AssistantRunRequestV1)
from packages.resume_core.models.assistant_actions import AssistantCapabilityReviewsV1
from packages.resume_core.models.assistant_history import AssistantHistoryOfferV1


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

    def protocol(request):
        versions = [value for key, value in request.headers.raw if key.lower() == b"x-foldcv-assistant-protocol"]
        if versions != [b"1"]:
            raise AgentFailure("AGENT_PROTOCOL")

    def flags(request):
        result = {}
        for header, name in ((b"x-foldcv-agent-edits", "allow_edits"), (b"x-foldcv-agent-web", "allow_web")):
            values = [value for key, value in request.headers.raw if key.lower() == header]
            if len(values) > 1 or values and values[0] not in {b"0", b"1"}:
                raise AgentFailure("AGENT_TOOL_DENIED")
            result[name] = not values or values[0] == b"1"
        return result

    @app.get(prefix + "/tasks")
    async def tasks(project_id: str, request: Request):
        from .capabilities import catalog
        protocol(request)
        return response(catalog(service, project_id, **flags(request)))

    @app.post(prefix + "/tasks/check-message")
    async def task_message(project_id: str, request: Request, payload: AssistantMessageCheckV1):
        from .capabilities import catalog, check_message
        protocol(request)
        return response(check_message(catalog(service, project_id,
            allow_edits=payload.allow_edits, allow_web=payload.allow_web), payload))

    def proposal_protocol(request):
        protocol(request)
        if not service.assistant_protocol_enabled:
            raise AgentFailure("AGENT_PROTOCOL")

    @app.get(prefix + "/proposals")
    async def proposals(project_id: str, request: Request):
        from .proposals import review
        proposal_protocol(request)
        project(project_id)
        return response(AssistantProposalListV1(projectId=project_id,
            proposals=[item.proposal for item in review(service, project_id) if not item.no_change]))

    @app.get(prefix + "/proposals/{proposal_id}/versions/{version}")
    async def proposal(project_id: str, proposal_id: str, version: int, request: Request):
        from .proposals import review
        proposal_protocol(request)
        project(project_id)
        review(service, project_id)
        return response(service.proposals.get(project_id, proposal_id, version).proposal)

    @app.post(prefix + "/proposals/discard")
    async def discard_proposal(project_id: str, request: Request, payload: AssistantProposalRequestV1):
        proposal_protocol(request)
        project(project_id)
        def discard(values):
            value = next((item for item in values if item.proposal.id == payload.proposal_id and item.proposal.version == payload.version), None)
            if value is None:
                raise AgentFailure("AGENT_NOT_FOUND")
            if value.proposal.content_sha256 != payload.content_sha256:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            if value.proposal.state not in {"ready", "incomplete", "stale", "failed_before_commit", "discarded"}:
                raise AgentFailure("AGENT_TOOL_DENIED")
            value.proposal.state = "discarded"
            return value
        return response(service.proposals.update(project_id, discard).proposal)

    @app.get(prefix + "/reviews")
    async def reviews(project_id: str, request: Request):
        from .proposals import review, review_view
        from .capabilities import catalog
        proposal_protocol(request)
        project(project_id)
        tasks = catalog(service, project_id, **flags(request))
        return response(AssistantCapabilityReviewsV1(projectId=project_id,
            reviews=[review_view(service, item, tasks) for item in review(service, project_id) if not item.no_change]))

    @app.get(prefix + "/reviews/{proposal_id}/versions/{version}")
    async def review_one(project_id: str, proposal_id: str, version: int, request: Request):
        from .proposals import review, review_view
        from .capabilities import catalog
        proposal_protocol(request)
        project(project_id)
        tasks = catalog(service, project_id, **flags(request))
        values = review(service, project_id)
        item = next((item for item in values if item.proposal.id == proposal_id and item.proposal.version == version), None)
        if item is None:
            raise AgentFailure("ASSISTANT_PROPOSAL_MISSING")
        return response(review_view(service, item, tasks))

    @app.post(prefix + "/applications/claim")
    async def accept_proposal(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.approval.claim(project_id, payload))

    @app.post(prefix + "/history/offer-v1")
    async def history_review_offer(project_id: str, request: Request, payload: AssistantHistoryOfferV1):
        from .history_proposals import offer_history
        proposal_protocol(request)
        offer_history(service, project_id, payload)
        return response(AgentEmptyRequest())

    @app.post(prefix + "/applications/commit")
    async def apply_proposal(project_id: str, request: Request, payload: AssistantApplicationCommitV1):
        proposal_protocol(request)
        return response(await to_thread(service.approval.commit, project_id, payload))

    @app.post(prefix + "/applications/recover")
    async def recover_proposal(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.approval.recover(project_id, payload))

    @app.post(prefix + "/applications/cancel")
    async def cancel_application(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(await to_thread(service.approval.cancel, project_id, payload))

    @app.post(prefix + "/applications/resume")
    async def resume_application(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.approval.recover(project_id, payload, resume=True))

    @app.post(prefix + "/applications/retry")
    async def retry_application(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.approval.retry(project_id, payload))

    @app.post(prefix + "/applications/result")
    async def application_result(project_id: str, request: Request, payload: AssistantApplicationReportV1):
        proposal_protocol(request)
        return response(service.approval.report(project_id, payload))

    @app.post(prefix + "/actions/claim")
    async def accept_action(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.action_approval.claim(project_id, payload))

    @app.post(prefix + "/actions/commit")
    async def apply_action(project_id: str, request: Request, payload: AssistantApplicationCommitV1):
        proposal_protocol(request)
        return response(await service.action_approval.commit(project_id, payload))

    @app.post(prefix + "/actions/recover")
    async def recover_action(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.action_approval.recover(project_id, payload))

    @app.post(prefix + "/actions/resume")
    async def resume_action(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.action_approval.recover(project_id, payload, resume=True))

    @app.post(prefix + "/actions/cancel")
    async def cancel_action(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(await to_thread(service.action_approval.cancel, project_id, payload))

    @app.post(prefix + "/actions/retry")
    async def retry_action(project_id: str, request: Request, payload: AssistantAcceptanceV1):
        proposal_protocol(request)
        return response(service.action_approval.retry(project_id, payload))

    @app.get(prefix + "/proposals/{proposal_id}/versions/{version}/image-preview")
    async def action_image(project_id: str, proposal_id: str, version: int):
        import base64
        value = service.proposals.get(project_id, proposal_id, version)
        action = getattr(value, "action", None)
        if action is None or action.request.action not in {"import_asset", "remove_asset"}:
            raise AgentFailure("AGENT_NOT_FOUND")
        if action.request.action == "import_asset":
            asset = next(item for item in value.candidate.project.assets if item.id not in {old.id for old in value.baseline.project.assets})
            data = base64.b64decode(action.blob_base64, validate=True)
        else:
            asset = next(item for item in value.baseline.project.assets if item.id == action.request.target_id)
            data = service.projects.images.get((project_id, asset.id))
            if data is None:
                raise AgentFailure("AGENT_NOT_FOUND")
        return Response(data, media_type=asset.mime_type, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

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
            jobs = getattr(service.projects, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                await jobs.stop_agents()
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

    @app.get(prefix + "/access")
    async def access(project_id: str):
        project(project_id)
        entry = service.projects.catalog.get(project_id)
        return response(AgentAccess(revision=entry.access_revision, readOnly=entry.read_only))

    @app.post(prefix + "/history/offer")
    async def history_offer(project_id: str, payload: AgentHistoryOffer):
        project(project_id)
        service.publication.offer_editor_history(project_id, payload)
        return JSONResponse({}, headers={"Cache-Control": "no-store"})

    @app.get(prefix + "/operations")
    async def operations(project_id: str):
        items = []
        for key, command in service.projects.catalog.actions().items():
            if command["projectId"] != project_id:
                continue
            result = command["result"]
            error = result.get("error") or {}
            items.append(AgentProjectOperation(id=key, projectId=project_id, runId=command["runId"],
                action=command["action"], status=command["status"], durable=command["status"] in {"completed", "deleted"} and result.get("durable", False),
                downloadUrl=result.get("downloadUrl"), errorCode=result.get("errorCode") or error.get("code")))
        return response(AgentProjectOperations(items=items))

    @app.put(prefix + "/access")
    async def set_access(project_id: str, payload: AgentAccessRequest):
        from packages.resume_core.project_catalog import AccessChanged
        with service.projects.state_lock:
            project(project_id)
            try:
                entry = service.projects.catalog.update(project_id, read_only=payload.read_only,
                    expected_revision=payload.expected_revision)
            except AccessChanged:
                raise AgentFailure("AGENT_SETTINGS_CONFLICT") from None
            return response(AgentAccess(revision=entry.access_revision, readOnly=entry.read_only))

    @app.get(prefix + "/exports/{filename}")
    async def exported(project_id: str, filename: str):
        import hashlib
        import re
        from packages.resume_core.project_store import owned_file
        from packages.resume_core.storage import StorageFailure
        project(project_id)
        if re.fullmatch(r"[0-9a-f]{64}\.(?:docx|foldcv)", filename) is None:
            raise AgentFailure("AGENT_NOT_FOUND")
        path = service.projects.storage._directory(project_id) / "renders" / filename
        try:
            owned_file(path, 64 * 1024 * 1024)
            raw = path.read_bytes()
        except (OSError, ValueError, StorageFailure):
            raise AgentFailure("AGENT_NOT_FOUND") from None
        if hashlib.sha256(raw).hexdigest() != filename.split(".", 1)[0]:
            raise AgentFailure("AGENT_NOT_FOUND")
        extension = filename.rsplit(".", 1)[1]
        return Response(raw, media_type="application/vnd.foldcv.project+zip" if extension == "foldcv" else
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="resume.{extension}"'})

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
        closed = service.leases.close(project_id, payload.owner)
        project(project_id)
        if closed is not None:
            service.request_owner_stop(project_id, closed.epoch)
            await service.stop_project(project_id, owner_epoch=closed.epoch)
        return response(AgentEmptyRequest())

    @app.post(prefix + "/conversations/{conversation_id}/runs")
    async def submit(project_id: str, conversation_id: str, payload: AgentRunRequest):
        if service.assistant_protocol_enabled:
            raise AgentFailure("AGENT_PROTOCOL")
        return submit_run(project_id, conversation_id, payload)

    @app.post(prefix + "/conversations/{conversation_id}/requests")
    async def submit_assistant(project_id: str, conversation_id: str, request: Request, payload: AssistantRunRequestV1):
        proposal_protocol(request)
        return submit_run(project_id, conversation_id, payload.request)

    def submit_run(project_id, conversation_id, payload):
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
