"""Reuse agent reads and compilation with Job authority and deferred apply v2."""

import asyncio
import hashlib

from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.background import ProposalBindingV1

from ..agent.context import ReadBook, canonical_capture, current_dependencies, json_text
from ..agent.tools import TOOL_NAMES, ToolSession

APPLY_DESCRIPTION = (
    "Store one prepared proposal with apply protocol v2. waiting_for_sync or needs_review means "
    "proposalStored:true and durable:false: finish this turn without polling, another batch, regeneration "
    "or a save claim. Only saved with durable:true and an exact receipt proves a canonical save. "
    "Saved tool results use compact schemaVersion:3 with the exact receipt and workspaceSha256; "
    "the full project is available through paged read tools. Check-only mode forbids writes."
)
DEVELOPER_INSTRUCTIONS_V2 = (
    "Use only the captured FoldCV tools and native web search when enabled. Never use shell, files, "
    "plugins, skills, other agents or alternate providers. Read full targets and prepare at most one "
    "proposal. For literal substring edits, call find_resume_content with the exact old text and copy "
    "its UTF-16 start/end offsets unchanged; never count character positions. Read the full target "
    "with get_resume_context and use that full-read snapshotId with the search offsets, never the "
    "search snapshot as edit authority. apply_edit_batch uses protocol v2. A stored pending/review result ends the editing turn: "
    "do not poll, prepare another batch, regenerate, or claim a save. Report it as waiting for safe "
    "publication or review. Only durable:true with an exact saved receipt proves a save. Keep unsupported "
    "facts as findings. Correct declared argument shape errors only; never retry permission denial or "
    "start another model turn. Write final answers in plain Russian with stored source IDs for citations."
)
PROTOCOL_V2_SHA256 = hashlib.sha256((APPLY_DESCRIPTION + DEVELOPER_INSTRUCTIONS_V2).encode()).hexdigest()


class JobReadBook(ReadBook):
    def canonical_capture(self, _workspace, query):
        jobs = self.service.jobs
        def read(workspace):
            capture = canonical_capture(workspace, query)
            return capture, capture.dependencies
        capture, guards = jobs.history.observe(self.control.project_id, read, job_id=self.control.run_id)
        jobs.artifacts.observe(self.control.project_id, self.control.run_id, guards)
        return capture


class CanonicalProjects:
    def __init__(self, projects):
        self.projects = projects

    def read(self, project):
        return self.projects.storage.read_committed(project)[0]

    def __getattr__(self, name):
        return getattr(self.projects, name)


class JobToolSession(ToolSession):
    apply_description = APPLY_DESCRIPTION

    def __init__(self, service, control, run, fetcher):
        super().__init__(service, control, run, fetcher)
        self.book = JobReadBook(service, control)

    def register(self):
        super().register()
        for name in TOOL_NAMES:
            if name not in self.control.job.submission.tools:
                self.sdk.remove_tool(name)

    def guard(self):
        control, supervisor = self.control, self.service.jobs.supervisor
        if (not self.active or not supervisor.owns(control)
                or control.revoked or control.cancel.is_set() or not control.ready.is_set()):
            raise AgentFailure("AGENT_CANCELLED")
        job = supervisor.store.read(control.project_id, control.run_id)
        if supervisor.store.dispatch_state().account_generation != job.submission.account_generation:
            raise AgentFailure("AGENT_CONNECTION_CHANGED")
        if job.execution not in {"starting", "running"}:
            raise AgentFailure("AGENT_INTERRUPTED")
        if job.execution_generation != control.owner_epoch:
            raise AgentFailure("AGENT_OWNER_MISMATCH")
        _job, artifact = self.service.jobs.artifacts.record(control.project_id, control.run_id)
        if digest(self.service.projects.read(control.project_id).rules_used) != artifact.rules_sha256:
            raise AgentFailure("AGENT_STALE_READ")
        if control.active_deadline is not None and supervisor.clock.now() >= control.active_deadline:
            raise AgentFailure("AGENT_DEADLINE")

    def writer_session_id(self):
        # This compiles a candidate; NB02 adopts the actual writer when publishing.
        return "job_" + self.control.job.id

    async def call(self, name, arguments):
        if name != "apply_edit_batch":
            if name not in self.control.job.submission.tools:
                return {"error": {"code": "AGENT_TOOL_DENIED"}}
            try:
                return await super().call(name, arguments)
            except BackgroundFailure as error:
                return {"error": {"code": error.code}}
        try:
            async with self.gate:
                self.guard()
                from packages.resume_core import agent_limits as limits
                if self.calls >= limits.TOOL_CALLS or self.result_bytes > limits.TOOL_TOTAL_BYTES - 4096:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
                self.calls += 1
                job = self.control.job
                if not job.submission.allow_edits or name not in job.submission.tools:
                    raise AgentFailure("AGENT_TOOL_DENIED")
                self.write_guard()
                _, _, journal = run_in(self.service.store.load(self.control.project_id), job.id)
                item = next((item for item in journal.batches if item.result.batch_id == arguments.batch_id), None)
                if item is None or item.batch is None:
                    raise AgentFailure("AGENT_EDIT_INVALID")
                batch = item.batch
                artifact = self.service.jobs.artifacts.record(self.control.project_id, job.id)[1]
                if artifact.prepared_guards is None:
                    raise AgentFailure("AGENT_STALE_READ")
                reference = {"kind": "agent_journal", "conversationId": self.run.conversation_id,
                    "runId": job.id, "batchId": batch.id}
                from packages.resume_core.models.background import AgentPayloadReference
                payload = self.service.jobs.artifacts.payload_for(self.control.project_id,
                    AgentPayloadReference.model_validate(reference))
                candidate = ProposalBindingV1(schemaVersion=1, id="proposal_" + digest([job.id, batch.id])[:24],
                    jobId=job.id, projectId=self.control.project_id, lineage=job.submission.identity.lineage,
                    accountGeneration=job.submission.account_generation, executionGeneration=job.execution_generation,
                    turnId=job.id, payload=reference, payloadSha256=hashlib.sha256(payload).hexdigest(),
                    payloadBytes=len(payload), guards=artifact.prepared_guards, scope=job.submission.scope,
                    acceptedAt=self.service.jobs.store.clock(), executionDeadline=job.attempts[-1].active_deadline,
                    authority="active", revocation=None)
                current = self.service.projects.read(self.control.project_id)
                known = self.service.jobs.store.read(self.control.project_id, job.id)
                if known.receipt is not None:
                    result = self.service.jobs.publication.native_result(self.control.project_id, job.id)
                else:
                    manager = self.service.jobs.proposals_for(self.control.project_id)
                    result = await manager.accept(self.control, candidate,
                        needs_review=not current_dependencies(current, batch.dependencies))
                    published = await asyncio.to_thread(self.service.jobs.publication.publish,
                        self.control.project_id, job.id, candidate.payload_sha256)
                    await self.service.jobs.supervisor._emit(published)
                    result = (self.service.jobs.publication.native_result(self.control.project_id, job.id)
                        if published.receipt is not None else manager.result(published))
                if result.disposition == "saved":
                    from packages.resume_core.models.background import ToolSavedV3
                    saved = self.service.jobs.store.read(self.control.project_id, job.id)
                    result = ToolSavedV3(schemaVersion=3, disposition="saved", jobId=job.id,
                        proposalId=saved.proposal_id, proposalStored=True, durable=True,
                        receipt=result.result.receipt, workspaceSha256=saved.receipt.workspace_sha256,
                        projectRef=f"/v1/rich/projects/{self.control.project_id}")
                value = result.model_dump(mode="json", by_alias=True)
                self.result_bytes += len(json_text(value).encode())
                return value
        except BackgroundFailure as error:
            return {"error": {"code": error.code}}
        except AgentFailure as error:
            return {"error": {"code": error.code}}
        except (ValueError, TypeError):
            return {"error": {"code": "AGENT_EDIT_INVALID"}}
        except Exception:
            return {"error": {"code": "AGENT_PROTOCOL"}}


class JobTools:
    names = TOOL_NAMES

    def __init__(self, jobs, *, fetcher):
        self.jobs, self.fetcher = jobs, fetcher

    def session(self, control):
        from types import SimpleNamespace
        service = SimpleNamespace(projects=CanonicalProjects(self.jobs.projects), jobs=self.jobs,
            store=self.jobs.artifacts.bound(control.project_id, control.run_id),
            event=lambda *_args, **_kwargs: None,
            revoke=lambda bound, _reason=None: bound.stop(), cleanup_error=lambda _code: None)
        run, journal = run_in(service.store.load(control.project_id), control.run_id)[1:]
        session = JobToolSession(service, control, run, self.fetcher)
        session.names = tuple(control.job.submission.tools)
        try:
            session.prompt = session.book.initial(run, journal)
        except BaseException:
            session.revoke()
            session.listener.close()
            raise
        return session
