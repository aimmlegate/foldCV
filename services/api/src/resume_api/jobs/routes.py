"""Same-origin Job routes; models cannot submit server capabilities."""

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.agent import AgentEmptyRequest
from packages.resume_core.models.background import JobAgentRequestV1, JobReplayRequestV1, JobReplayV1, JobFixedRequestV1


def mount_jobs(app, service):
    from .writers import mount_writers
    mount_writers(app, service)
    prefix = "/v1/rich/projects/{project_id}/jobs"

    def response(value, status=200):
        return JSONResponse(value.model_dump(mode="json", by_alias=True), status_code=status,
            headers={"Cache-Control": "no-store"})

    @app.exception_handler(BackgroundFailure)
    async def failure(_request: Request, error: BackgroundFailure):
        status = (404 if error.code == "JOB_NOT_FOUND" else 410 if error.code == "PROJECT_DELETED" else
            503 if error.code in {"JOB_STORE_CORRUPT", "JOB_STORE_UNAVAILABLE", "CLEANUP_FAILED"} else 409)
        return JSONResponse({"error": {"code": error.code}}, status_code=status, headers={"Cache-Control": "no-store"})

    @app.get(prefix)
    async def project_jobs(project_id: str):
        return response(service.project(project_id))

    @app.post(prefix + "/agent")
    async def submit(project_id: str, payload: JobAgentRequestV1):
        job, created = await service.submit(project_id, payload)
        return response(job, 202 if created else 200)

    @app.post(prefix + "/fixed")
    async def fixed(project_id: str, payload: JobFixedRequestV1):
        value, created = await service.fixed.submit(project_id, payload)
        return response(value, 202 if created else 200)

    @app.get(prefix + "/{job_id}/fixed")
    async def fixed_result(project_id: str, job_id: str):
        service.project(project_id)
        return response(service.fixed.reply(service.store.read(project_id, job_id)))

    @app.post(prefix + "/{job_id}/read")
    async def read(project_id: str, job_id: str, payload: AgentEmptyRequest):
        service.project(project_id)
        return response(service.store.read(project_id, job_id))

    @app.post(prefix + "/{job_id}/legacy-v2")
    async def legacy(project_id: str, job_id: str, payload: AgentEmptyRequest):
        service.project(project_id)
        return response(service.artifacts.bound(project_id, job_id).legacy())

    @app.post(prefix + "/{job_id}/proposal/read")
    async def proposal(project_id: str, job_id: str, payload: AgentEmptyRequest):
        service.project(project_id)
        from packages.resume_core.background_publication import proposal_in
        state = service.store.load(project_id)
        job = service.store.read(project_id, job_id)
        return response(proposal_in(state, job))

    @app.post(prefix + "/{job_id}/conversation/read")
    async def conversation(project_id: str, job_id: str, payload: AgentEmptyRequest):
        from packages.resume_core.agent_store import conversation_in
        service.project(project_id)
        view = service.artifacts.bound(project_id, job_id)
        state = view.load(project_id)
        run = view.legacy().run
        return response(conversation_in(state, run.conversation_id))

    @app.post(prefix + "/{job_id}/cancel")
    async def cancel(project_id: str, job_id: str, payload: AgentEmptyRequest):
        service.project(project_id)
        return response(await service.supervisor.cancel(project_id, job_id))

    @app.post(prefix + "/{job_id}/replay")
    async def replay(project_id: str, job_id: str, payload: JobReplayRequestV1):
        service.project(project_id)
        return response(JobReplayV1(schemaVersion=1, events=service.supervisor.events.replay(project_id, job_id,
            after=payload.after, generation=payload.generation)))

    @app.post(prefix + "/{job_id}/events")
    async def events(project_id: str, job_id: str, payload: JobReplayRequestV1):
        service.project(project_id)
        service.store.read(project_id, job_id)
        return StreamingResponse(service.stream(project_id, job_id, payload), media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
