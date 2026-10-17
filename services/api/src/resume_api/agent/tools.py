"""Run-bound deterministic tools; models cannot select a project or grant writes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import threading
from typing import Literal

from pydantic import Field, ValidationError
from mcp.types import CallToolResult, TextContent

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure, digest, identity, run_in
from packages.resume_core.models.agent import AgentAnchor, AgentApplyRequest, AgentFetchRequest, AgentFinding, AgentPrepareRequest, AgentPublishFindings, AgentQuery, TERMINAL_RUNS
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


class ContextQuery(AgentQuery):
    kind: Literal["context", "document"] = "context"


class FindQuery(AgentQuery):
    kind: Literal["find"] = "find"
    text: str = Field(min_length=1, max_length=1000)


class FactsQuery(AgentQuery):
    kind: Literal["facts"] = "facts"


class SourceQuery(AgentQuery):
    kind: Literal["source"] = "source"


class HistoryQuery(AgentQuery):
    kind: Literal["history"] = "history"


READ_QUERIES = {"get_resume_context": ContextQuery, "find_resume_content": FindQuery,
    "get_working_facts": FactsQuery, "get_original_source": SourceQuery, "get_conversation_context": HistoryQuery}


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
    apply_description = "Offer a prepared batch to the mounted editor and wait for a durable receipt. Check-only mode forbids writes."

    def __init__(self, service, control, run, fetcher):
        self.service, self.control, self.run, self.fetcher = service, control, run, fetcher
        self.book = ReadBook(service, control)
        self.calls, self.fetches, self.result_bytes = 0, 0, 0
        self.cache = {}
        self.argument_issues = []
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

    def writer_session_id(self):
        return self.service.leases.require(self.control.project_id, epoch=self.control.owner_epoch).session_id

    def register(self):
        @self.sdk.tool(structured_output=False)
        async def get_resume_context(query: ContextQuery | None = None) -> CallToolResult:
            """Read the resume outline, or full blocks/cells by IDs with query:{kind:"document",ids:["block_id"]}. For a literal substring edit, get exact UTF-16 start/end from find_resume_content, then read the full target here. Prepare with this full-read snapshotId and the unchanged search offsets; never count characters. Use nextCursor with the same query for later pages."""
            return self.wire(await self.call("get_resume_context", query or ContextQuery()))

        @self.sdk.tool(structured_output=False)
        async def find_resume_content(query: FindQuery) -> CallToolResult:
            """Search for nonempty literal text with kind:find. Matches provide exact UTF-16 start/end offsets; copy these unchanged for substring edits instead of counting characters. A match is not a full edit target. Read its block/cell with get_resume_context and use that full-read snapshotId with the search offsets. Use nextCursor with the same query for later pages."""
            return self.wire(await self.call("find_resume_content", query))

        @self.sdk.tool(structured_output=False)
        async def get_working_facts(query: FactsQuery | None = None) -> CallToolResult:
            """Read working facts, optionally filtered by record IDs. Use nextCursor with the same query for later pages."""
            return self.wire(await self.call("get_working_facts", query or FactsQuery()))

        @self.sdk.tool(structured_output=False)
        async def get_original_source(query: SourceQuery | None = None) -> CallToolResult:
            """Read stored original text, optionally filtered by source or unit IDs, without network. Use nextCursor with the same query for later pages."""
            return self.wire(await self.call("get_original_source", query or SourceQuery()))

        @self.sdk.tool(structured_output=False)
        async def get_conversation_context(query: HistoryQuery | None = None) -> CallToolResult:
            """Read conversation history. IDs load full stored sources, findings or messages without network. Use nextCursor with the same query for later pages."""
            return self.wire(await self.call("get_conversation_context", query or HistoryQuery()))

        @self.sdk.tool(structured_output=False)
        async def check_resume() -> CallToolResult:
            """Check current timeline, links, structure and export readiness without inference or edits."""
            return self.wire(await self.call("check_resume", None))

        @self.sdk.tool(structured_output=False)
        async def read_public_page(url: str) -> CallToolResult:
            """Fetch public HTML/plain text. Only returned stored source IDs can support final citations."""
            return self.wire(await self.call("read_public_page", url))

        @self.sdk.tool(structured_output=False)
        async def publish_findings(request: AgentPublishFindings) -> CallToolResult:
            """Store observations without editing. Use targets from a full document read, not the initial outline snapshot. A prose target has snapshotId, blockId, cellId:null, recordId:null, fieldKey:null, start:null, end:null. sourceIds are stored IDs returned by read_public_page, never URLs. findings use targets, not anchors."""
            return self.wire(await self.call("publish_findings", request))

        @self.sdk.tool(structured_output=False)
        async def prepare_edit_batch(request: AgentPrepareRequest) -> CallToolResult:
            """Compile edits without saving. Example arguments: {"request":{"key":"edit_1","snapshotIds":["read_id"],"operations":[{"kind":"replace_text","target":{"snapshotId":"read_id","blockId":"block_id","cellId":null,"field":"content","start":0,"end":1},"content":[{"text":"Existing claim rephrased"}]}]}}. Read real IDs/ranges first. cellId is required: use null outside tables. Content uses text/marks, not document styles. One saved batch per turn."""
            return self.wire(await self.call("prepare_edit_batch", request))

        async def apply_edit_batch(request: AgentApplyRequest) -> CallToolResult:
            return self.wire(await self.call("apply_edit_batch", request))
        apply_edit_batch.__doc__ = self.apply_description
        self.sdk.tool(structured_output=False)(apply_edit_batch)

    def wire(self, value):
        text = json_text(value)
        if value.get("error") is not None:
            size = len(text.encode())
            if self.result_bytes + size > limits.TOOL_TOTAL_BYTES:
                self.service.revoke(self.control, "AGENT_TOOL_LIMIT")
                return CallToolResult(content=[], isError=True)
            self.result_bytes += size
        return CallToolResult(content=[TextContent(type="text", text=text)], isError=value.get("error") is not None)

    def preflight(self, params):
        self.argument_issues = []
        name = None
        try:
            self.guard()
            if self.calls >= limits.TOOL_CALLS:
                raise AgentFailure("AGENT_TOOL_LIMIT")
            if not isinstance(params, dict) or params.keys() - {"name", "arguments", "_meta"}:
                raise ValueError("invalid tool envelope")
            name, arguments = params.get("name"), params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("invalid tool arguments")
            if name in READ_TOOLS:
                if arguments.keys() - {"query"}:
                    raise ValueError("invalid read envelope")
                query = arguments.get("query")
                READ_QUERIES[name].model_validate({} if query is None else query)
            elif name == "check_resume":
                if arguments:
                    raise ValueError("invalid check envelope")
            elif name == "read_public_page":
                AgentFetchRequest.model_validate(arguments)
            elif name in {"prepare_edit_batch", "apply_edit_batch", "publish_findings"}:
                if set(arguments) != {"request"}:
                    raise ValueError("invalid request envelope")
                {"prepare_edit_batch": AgentPrepareRequest, "apply_edit_batch": AgentApplyRequest,
                    "publish_findings": AgentPublishFindings}[name].model_validate(arguments["request"])
            else:
                raise ValueError("unknown tool")
            return None
        except AgentFailure as error:
            return error.code
        except ValidationError as error:
            self.calls += 1
            if name == "prepare_edit_batch":
                safe = {"operations", "target", "content", "text", "marks", "snapshotId", "blockId", "cellId", "field", "start", "end", "key", "snapshotIds", "kind", "replace_text"}
                self.argument_issues = [{"path": ".".join(str(part) if type(part) is int and 0 <= part <= 100 else part if part in safe else "*" for part in issue["loc"])[:160],
                    "issue": issue["type"] if issue["type"] in {"missing", "extra_forbidden", "string_type", "list_type", "int_type", "literal_error", "union_tag_invalid", "union_tag_not_found", "too_long", "value_error", "greater_than_equal", "string_too_long"} else "invalid"}
                    for issue in error.errors(include_input=False, include_context=False, include_url=False)[:3]]
                return "AGENT_EDIT_INVALID"
            return "AGENT_TOOL_DENIED"
        except (ValueError, TypeError):
            self.calls += 1
            if name == "prepare_edit_batch":
                self.argument_issues = [{"path": "request", "issue": "expected_object"}]
                return "AGENT_EDIT_INVALID"
            return "AGENT_TOOL_DENIED"

    def preflight_failure(self, code):
        result = {"error": {"code": code}}
        if self.argument_issues:
            result["argumentIssues"] = self.argument_issues
            result["format"] = "Use the advertised request wrapper. replace_text target requires snapshotId, blockId, cellId (null outside tables), field, start, end. content contains text and optional marks, not styles. Correct shape errors only; never retry permission denial."
        return result

    async def call(self, name, arguments):
        try:
            async with self.gate:
                self.guard()
                if self.calls >= limits.TOOL_CALLS:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
                self.calls += 1
                if self.result_bytes >= limits.TOOL_TOTAL_BYTES:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
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
                    if not self.run.allow_edits:
                        raise AgentFailure("AGENT_TOOL_DENIED")
                    result = await self.service.publication.offer(self, arguments.batch_id)
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
            failure = {"error": {"code": error.code}}
            if name == "publish_findings" and error.code == "AGENT_EVIDENCE_INVALID":
                failure["format"] = "Use a full document read snapshot. Prose targets require cellId, recordId, fieldKey, start and end all null for the whole block. sourceIds must be stored IDs, not URLs."
            return failure
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
