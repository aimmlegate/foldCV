"""Run-bound deterministic tools; models cannot select a project or grant writes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import threading

from pydantic import ValidationError

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure, digest, identity, run_in
from packages.resume_core.models.agent import AgentAnchor, AgentApplyRequest, AgentFinding, AgentPrepareRequest, AgentPublishFindings, AgentQuery, TERMINAL_RUNS
from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.rich_fields import inline_groups, working_field
from packages.resume_core.rich_mutations import inline_text, utf16_slice
from packages.resume_core.rich_timeline import timeline_report
from packages.resume_core.rendering.rich_docx import validate_export

from .context import ReadBook, clip, json_text
from .mcp import PrivateMcp
from .web import PublicFetcher

READ_TOOLS = {"get_resume_context": "context", "find_resume_content": "find", "get_working_facts": "facts",
    "get_original_source": "source", "get_conversation_context": "history"}
TOOL_NAMES = (*READ_TOOLS, "check_resume", "read_public_page", "publish_findings", "prepare_edit_batch", "apply_edit_batch")


class AgentTools:
    names = TOOL_NAMES

    def __init__(self, service, *, fetcher=None):
        self.service = service
        self.fetcher = fetcher or PublicFetcher(service.projects.temp_root)

    async def open(self, control, run, journal):
        session = ToolSession(self.service, control, run, self.fetcher)
        session.prompt = session.book.initial(run, journal)
        await session.start()
        return session


class ToolSession(PrivateMcp):
    names = TOOL_NAMES

    def __init__(self, service, control, run, fetcher):
        self.service, self.control, self.run, self.fetcher = service, control, run, fetcher
        self.book = ReadBook(service, control)
        self.calls, self.fetches, self.result_bytes = 0, 0, 0
        self.cache = {}
        self.fetch_cancel = threading.Event()
        self.fetch_tasks = set()
        self.gate = asyncio.Lock()
        super().__init__(self)
        self.register()

    def revoke(self):
        self.active = False
        self.fetch_cancel.set()

    async def close(self):
        return await super().close()

    async def _close(self):
        # PrivateMcp calls dispatcher.close; the dispatcher is this same session.
        self.active = False
        self.token = ""
        self.revoke()
        self.server.should_exit = True
        try:
            if self.fetch_tasks:
                await asyncio.wait_for(asyncio.gather(*self.fetch_tasks, return_exceptions=True), 2)
            if self.task is not None:
                await asyncio.wait_for(self.task, 2)
        finally:
            self.listener.close()
            self.prompt = ""
            self.book.captures.clear()
            self.book.by_snapshot.clear()
            self.book.cursors.clear()
            self.cache.clear()

    def guard(self):
        with self.service.projects.state_lock:
            if not self.active or self.control.revoked.is_set() or self.control.cancel.is_set():
                raise AgentFailure("AGENT_CANCELLED")
            self.service.leases.require(self.control.project_id, epoch=self.control.owner_epoch)
            connection = self.service.connection()
            if not connection.ready or connection.epoch != self.control.connection_epoch:
                raise AgentFailure("AGENT_CONNECTION_CHANGED")
            state = self.service.store.load(self.control.project_id)
            if state.owner_epoch != self.control.owner_epoch:
                raise AgentFailure("AGENT_OWNER_MISMATCH")
            _, run, _ = run_in(state, self.control.run_id)
            if run.state in TERMINAL_RUNS or run.state == "cancelling":
                raise AgentFailure("AGENT_INTERRUPTED")
            if datetime.now(timezone.utc) >= datetime.fromisoformat(run.deadline):
                raise AgentFailure("AGENT_DEADLINE")

    def register(self):
        def reader(name, kind):
            async def read(query: AgentQuery | None = None) -> dict:
                """Read a bounded page. Use snapshot IDs and nextCursor for full target reads; document IDs request full blocks/cells."""
                return await self.call(name, query or AgentQuery(kind=kind))
            self.sdk.tool(name=name)(read)
        for name, kind in READ_TOOLS.items():
            reader(name, kind)

        @self.sdk.tool()
        async def check_resume() -> dict:
            """Check current timeline, links, structure and export readiness without inference or edits."""
            return await self.call("check_resume", None)

        @self.sdk.tool()
        async def read_public_page(url: str) -> dict:
            """Fetch public HTML/plain text. Only returned stored source IDs can support final citations."""
            return await self.call("read_public_page", url)

        @self.sdk.tool()
        async def publish_findings(request: AgentPublishFindings) -> dict:
            """Store anchored observations from full read snapshots, with optional stored source IDs. Does not edit the resume."""
            return await self.call("publish_findings", request)

        @self.sdk.tool()
        async def prepare_edit_batch(request: AgentPrepareRequest) -> dict:
            """Compile typed operations from full current read snapshots. No resume changes occur here. One saved batch per turn."""
            return await self.call("prepare_edit_batch", request)

        @self.sdk.tool()
        async def apply_edit_batch(request: AgentApplyRequest) -> dict:
            """Offer a prepared batch to the mounted editor and wait for a durable receipt. Check-only mode forbids writes."""
            return await self.call("apply_edit_batch", request)

    async def call(self, name, arguments):
        try:
            async with self.gate:
                self.guard()
                if self.calls >= limits.TOOL_CALLS:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
                self.calls += 1
                if name in READ_TOOLS:
                    if name == "get_resume_context" and arguments.kind == "context" and arguments.ids:
                        arguments = arguments.model_copy(update={"kind": "document"})
                    expected = READ_TOOLS[name]
                    if arguments.kind != expected and not (name == "get_resume_context" and arguments.kind == "document"):
                        raise AgentFailure("AGENT_TOOL_DENIED")
                    with self.service.projects.state_lock:
                        self.guard()
                        result = self.book.read(arguments)
                elif name == "check_resume":
                    result = self.check()
                elif name == "read_public_page":
                    if not self.run.allow_web:
                        raise AgentFailure("AGENT_WEB_DISABLED")
                    if self.fetches >= limits.PAGE_FETCHES:
                        raise AgentFailure("AGENT_SOURCE_LIMIT")
                    self.fetches += 1
                    task = asyncio.create_task(self.fetcher.fetch(arguments, self.fetch_cancel))
                    self.fetch_tasks.add(task)
                    try:
                        source = await task
                    finally:
                        self.fetch_tasks.discard(task)
                    with self.service.projects.state_lock:
                        self.guard()
                        source.run_id = self.control.run_id
                        def record(state):
                            conversation, _, _ = run_in(state, self.control.run_id)
                            conversation.sources.append(source)
                        self.service.store.update(self.control.project_id, record)
                        self.service.event(self.control, "source.ready", {"id": source.id})
                    text, clipped = clip(source.text, 12000)
                    result = {"source": source.model_dump(mode="json", by_alias=True), "excerpt": text, "excerptTruncated": clipped}
                    result["source"].pop("text")
                elif name == "publish_findings":
                    result = self.findings(arguments)
                elif name == "prepare_edit_batch":
                    if not self.run.allow_edits:
                        raise AgentFailure("AGENT_TOOL_DENIED")
                    from .edits import prepare
                    result = prepare(self, arguments)
                elif name == "apply_edit_batch":
                    raise AgentFailure("AGENT_TOOL_DENIED")
                else:
                    raise AgentFailure("AGENT_TOOL_DENIED")
                self.guard()
                value = json.loads(json_text(result))
                size = len(json_text(value).encode())
                if size > limits.TOOL_BYTES or self.result_bytes + size > limits.TOOL_TOTAL_BYTES:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
                self.result_bytes += size
                return value
        except AgentFailure as error:
            if error.code == "AGENT_CLEANUP_FAILED":
                self.service.revoke(self.control, error.code)
                self.service.cleanup_error(error.code)
            return {"error": {"code": error.code}}
        except (ValidationError, ValueError):
            return {"error": {"code": "AGENT_TOOL_DENIED"}}
        except Exception:
            return {"error": {"code": "AGENT_PROTOCOL"}}

    def check(self):
        with self.service.projects.state_lock:
            self.guard()
            workspace = self.service.projects.read(self.control.project_id)
            try:
                type(workspace).model_validate(workspace.model_dump(by_alias=True))
                validate_export(workspace.project.document)
                export = "ready"
            except ValueError:
                export = "invalid"
            return {"changed": False, "documentRevision": workspace.document_revision,
                "factsRevision": workspace.project.facts.revision, "timeline": timeline_report(workspace),
                "structure": "valid", "links": "valid", "export": export,
                "semanticReview": "Use read tools and publish anchored findings; no semantic inference was run by this check."}

    def findings(self, request):
        key = digest(request)
        if key in self.cache:
            return self.cache[key]
        findings = []
        with self.service.projects.state_lock:
            self.guard()
            state = self.service.store.load(self.control.project_id)
            conversation, _, _ = run_in(state, self.control.run_id)
            sources = {source.id for source in conversation.sources}
            for finding in request.findings:
                if not set(finding.source_ids) <= sources:
                    raise AgentFailure("AGENT_EVIDENCE_INVALID")
                anchors = [self.anchor(target) for target in finding.targets]
                findings.append(AgentFinding(id=identity("finding"), runId=self.control.run_id, severity=finding.severity,
                    message=finding.message, anchors=anchors, sourceIds=finding.source_ids))
            def record(state):
                conversation, _, _ = run_in(state, self.control.run_id)
                conversation.findings.extend(findings)
            self.service.store.update(self.control.project_id, record)
            for finding in findings:
                self.service.event(self.control, "finding.ready", {"id": finding.id})
            result = {"findingIds": [finding.id for finding in findings]}
            self.cache[key] = result
            return result

    def anchor(self, target):
        capture = self.book.require(target.snapshot_id)
        project = capture.workspace.project
        if target.block_id is not None:
            if capture.query.kind != "document" or (capture.query.ids and target.block_id not in capture.query.ids
                    and target.cell_id not in capture.query.ids):
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            block = next((block for block in project.document.blocks() if block.id == target.block_id), None)
            if block is None or target.record_id is not None or target.field_key is not None:
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            groups = dict(inline_groups(block))
            spans = groups.get(target.cell_id or ("caption" if block.type == "image" else "content"))
            if spans is None:
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            text = "".join(inline_text(span) for span in spans)
            maximum = len(text.encode("utf-16-le")) // 2
            start, end = target.start or 0, target.end if target.end is not None else maximum
            if end > maximum:
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            text = utf16_slice(text, start, end)
            deps = [dependency(capture.workspace, "block", block.id)]
        elif target.record_id is not None:
            if capture.query.kind != "facts" or capture.query.ids and target.record_id not in capture.query.ids:
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            record = next((record for record in project.facts.records if record.id == target.record_id), None)
            if record is None or target.cell_id is not None:
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            field = working_field(record, target.field_key) if target.field_key else None
            if target.field_key and field is None:
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            text = field.raw_text if field else json_text(record)
            maximum = len(text.encode("utf-16-le")) // 2
            start, end = target.start or 0, target.end if target.end is not None else maximum
            if end > maximum:
                raise AgentFailure("AGENT_EVIDENCE_INVALID")
            text = utf16_slice(text, start, end)
            deps = [dependency(capture.workspace, "record", record.id)]
        else:
            raise AgentFailure("AGENT_EVIDENCE_INVALID")
        text, _ = clip(text[:4000], 4096)
        return AgentAnchor(blockId=target.block_id, cellId=target.cell_id, recordId=target.record_id,
            fieldKey=target.field_key, start=start, end=end, text=text, dependencies=deps)
