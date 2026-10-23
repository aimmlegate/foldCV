"""Run-bound deterministic tools; models cannot select a project or grant writes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import threading
from typing import Literal

from pydantic import Field, ValidationError, TypeAdapter
from mcp.types import CallToolResult, TextContent

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure, digest, identity, run_in
from packages.resume_core.models.agent import AgentAnchor, AgentApplyRequest, AgentFetchRequest, AgentFinding, AgentPrepareRequest, AgentProjectAction, AgentPublishFindings, AgentQuery, TERMINAL_RUNS
from packages.resume_core.models.assistant_capabilities import AssistantTaskRequestV1
from packages.resume_core.models.assistant_proposals import AssistantAssemblyRequestV1
from packages.resume_core.models.assistant_actions import AssistantProjectActionPrepareV1
from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.rich_fields import inline_groups, working_field
from packages.resume_core.rich_mutations import inline_text, utf16_slice
from packages.resume_core.rich_timeline import timeline_report
from packages.resume_core.rendering.rich_docx import validate_export

from .context import ReadBook, clip, json_text
from .mcp import PrivateMcp
from .skills import ApplicationSkillQuery, SkillBook
from .web import PublicFetcher

READ_TOOLS = {"get_resume_context": "context", "find_resume_content": "find", "get_working_facts": "facts",
    "get_original_source": "source", "get_conversation_context": "history", "get_project_resources": "resources"}
WRITE_TOOLS = {"prepare_edit_batch", "apply_edit_batch", "project_action"}
TOOL_NAMES = (*READ_TOOLS, "get_application_skills", "check_resume", "read_public_page", "publish_findings", "prepare_edit_batch", "apply_edit_batch", "project_action")


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


class ResourcesQuery(AgentQuery):
    kind: Literal["resources"] = "resources"


READ_QUERIES = {"get_resume_context": ContextQuery, "find_resume_content": FindQuery,
    "get_working_facts": FactsQuery, "get_original_source": SourceQuery, "get_conversation_context": HistoryQuery,
    "get_project_resources": ResourcesQuery}


class AgentTools:
    @property
    def names(self):
        return tuple(name for name in TOOL_NAMES if not getattr(self.service, "assistant_protocol_enabled", False) or name != "apply_edit_batch")

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
        self.skills = SkillBook()
        self.calls, self.fetches, self.result_bytes = 0, 0, 0
        self.cache = {}
        self.argument_issues = []
        self.planned_task = None
        self.planning_revoked = False
        self.capability_service = getattr(service, "catalog_service", service)
        self.cap_mode = getattr(self.capability_service, "assistant_protocol_enabled", False)
        self.names = tuple(name for name in TOOL_NAMES if not self.cap_mode or name != "apply_edit_batch")
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
            self.skills.clear()

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

    def write_guard(self):
        from packages.resume_core.project_catalog import AccessChanged
        from resume_api.gui_projects import ProjectFailure
        if not self.run.allow_edits:
            raise AgentFailure("AGENT_TOOL_DENIED")
        try:
            self.service.projects.require_agent_writable(self.control.project_id)
            self.service.projects.catalog.require_write(self.control.project_id, self.run.access_revision)
        except ProjectFailure as error:
            raise AgentFailure(error.code) from None
        except AccessChanged:
            raise AgentFailure("AGENT_TOOL_DENIED") from None

    def register(self):
        @self.sdk.tool(structured_output=False)
        async def get_resume_context(query: ContextQuery | None = None) -> CallToolResult:
            """Read the project index with query:{kind:"context"}. Read ALL document blocks with query:{kind:"document"}, or filter by ids. Each page contains whole blocks; only an oversized item uses json-fragments. Pass snapshot.nextCursor as query.cursor with the SAME query until nextCursor is null. Reading is complete only then. For substring edits, copy UTF-16 offsets from find_resume_content and use a full-read snapshotId."""
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
            """Read the original resume content from all saved PDF/DOCX/TXT/Markdown sources, including text omitted from the current layout. Always available in read-only mode, independently of the visible pane, without network. Returns stored extracted text, locations, layout cues, format and extraction warnings; not page images or rendered appearance. Omit query or use query:{kind:"source"}; filter by source or unit ids when needed. Follow snapshot.nextCursor with the SAME query until null; ordered json-fragments reconstruct an oversized item. Empty/unavailable extracted text does not prove that the original file is empty. Read originals before source comparisons, and report gaps instead of inferring missing content from the edited document."""
            return self.wire(await self.call("get_original_source", query or SourceQuery()))

        @self.sdk.tool(structured_output=False)
        async def get_conversation_context(query: HistoryQuery | None = None) -> CallToolResult:
            """Read conversation history. IDs load full stored sources, findings or messages without network. Use nextCursor with the same query for later pages."""
            return self.wire(await self.call("get_conversation_context", query or HistoryQuery()))

        async def get_project_resources(query: ResourcesQuery | None = None, task: AssistantTaskRequestV1 | None = None) -> CallToolResult:
            """Read retained assets, sources, dates, template, rules and history. Follow nextCursor with the same query until null. In assistant protocol 1, check a typed task first with task:{protocolVersion:1,taskId,stage,scope,inputAvailable}; omit query when checking a task. This returns availability, never approval."""
            if query is not None and task is not None:
                return self.wire({"error": {"code": "AGENT_ARGUMENT_INVALID"}})
            return self.wire(await self.call("get_project_resources", task or query or ResourcesQuery()))
        from .capabilities import TASKS
        get_project_resources.__doc__ += " Catalog task IDs: " + ", ".join(task.id for task in TASKS) + "."
        self.sdk.tool(structured_output=False)(get_project_resources)

        @self.sdk.tool(structured_output=False)
        async def get_application_skills(query: ApplicationSkillQuery | None = None) -> CallToolResult:
            """List bundled application skills when query is omitted. Read full instructions with query:{skillId:"import-resume"} or {skillId:"format-resume"}; resource defaults to SKILL.md. Read listed references using their exact resource names. Follow top-level nextCursor with the SAME skillId/resource until null; concatenate content in offset order. Available without edits or internet. These references do not grant permissions or expose import-only tools, scripts or files; current project rules and template take precedence over legacy instructions."""
            return self.wire(await self.call("get_application_skills", query))

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

        async def prepare_edit_batch(request: AgentPrepareRequest) -> CallToolResult:
            """Compile edits without saving. For template formatting, first read the entire document through nextCursor:null, then operations:[{kind:"format_template",snapshotId:"completed_read_id"}]. This preserves current wording and creates one shared undo action. Text edits use replace_text with target:{snapshotId,blockId,cellId:null,field:"content",start,end}, content:[{text:"..."}]. Copy exact UTF-16 offsets from find_resume_content. Insert headings/sections/lists with insert_blocks, tables with insert_table, retained images with insert_asset. Facts support create_fact/update_fact/delete_fact with evidence. Read real targets first. One saved batch per turn."""
            return self.wire(await self.call("prepare_edit_batch", request))
        if self.cap_mode:
            prepare_edit_batch.__annotations__["request"] = AssistantAssemblyRequestV1 | AssistantProjectActionPrepareV1
            prepare_edit_batch.__doc__ = (
                "Build a durable private draft, never a canonical save. Use protocolVersion:1, taskId, "
                "key and phase:append/finalize. Omit proposalId for the first call, then reuse returned "
                "proposalId/version. Each key is idempotent and each call extends the same baseline. "
                "Use operations and snapshotIds from complete paged reads. unchanged lists unitId/reason "
                "for preserved units; never infer coverage from an outline or search. An empty append "
                "starts the scope ledger. Results expose up to 20 unresolved unit IDs; read and account "
                "for those, append unchanged reasons and repeat within the same bounded turn. Finalize only after "
                "all scope units are read and accounted for. draft_ready ends generation and awaits UI "
                "review/Apply. incomplete retains useful work with Apply disabled. No operation publishes. "
                "Maximum 100 aggregate operations and current transport/call/time limits. Wording, "
                "facts/structure and formatting are separate tasks. Project action drafts, including in check-only "
                "mode, instead use request:{protocolVersion:1,request:{key,snapshotId,action,value?,targetId?}} "
                "after complete resources and typed task planning. This is the same non-mutating action preparation "
                "as project_action; the queued check-only tool set deliberately excludes direct project_action."
            )
        self.sdk.tool(structured_output=False)(prepare_edit_batch)

        async def apply_edit_batch(request: AgentApplyRequest) -> CallToolResult:
            return self.wire(await self.call("apply_edit_batch", request))
        apply_edit_batch.__doc__ = self.apply_description
        if not self.cap_mode:
            self.sdk.tool(structured_output=False)(apply_edit_batch)

        async def project_action(request: AgentProjectAction) -> CallToolResult:
            """Perform one explicit bound-project operation after a complete get_project_resources read. Use its snapshotId and a unique key. Actions: rename (value:title), formatting_date (value:ISO date), add_source_text (value:literal text), remove_source (targetId; only unreferenced), import_asset (value:base64 PNG/JPEG/WebP), remove_asset (targetId; only unreferenced), export_docx/export_project (returns durable download), archive/restore/delete, undo/redo. Destructive actions require the user's explicit command. Editing permission is checked again at commit. Finish the turn after a project operation."""
            return self.wire(await self.call("project_action", request))
        if self.cap_mode:
            project_action.__annotations__["request"] = AssistantProjectActionPrepareV1
            project_action.__doc__ = (
                "Use request:{protocolVersion:1,request:{key,snapshotId,action,value?,targetId?}} after a typed task check "
                "and complete get_project_resources read. Rename, formatting_date, add_source_text, remove_source, "
                "import_asset, remove_asset, archive, restore and delete prepare an exact private review only. "
                "They never save. Delete needs targetId equal to this project ID. Source text/image base64 must be "
                "literal user input, never generated evidence. export_docx/export_project return a durable download "
                "under current export readiness. UI review and explicit Apply are the only mutation authority."
            )
        self.sdk.tool(structured_output=False)(project_action)

    def wire(self, value):
        text = json_text(value)
        if value.get("error") is not None:
            size = len(text.encode())
            if self.result_bytes + size > limits.TOOL_TOTAL_BYTES:
                self.service.revoke(self.control, "AGENT_TOOL_LIMIT")
                return CallToolResult(content=[], isError=True)
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
                if name == "get_project_resources" and "task" in arguments:
                    if set(arguments) != {"task"}:
                        raise ValueError("task check cannot include a read query")
                    AssistantTaskRequestV1.model_validate(arguments["task"])
                    return None
                if arguments.keys() - {"query"}:
                    raise ValueError("invalid read envelope")
                query = arguments.get("query")
                READ_QUERIES[name].model_validate({} if query is None else query)
            elif name == "get_application_skills":
                if arguments.keys() - {"query"}:
                    raise ValueError("invalid skill envelope")
                if arguments.get("query") is not None:
                    ApplicationSkillQuery.model_validate(arguments["query"])
            elif name == "check_resume":
                if arguments:
                    raise ValueError("invalid check envelope")
            elif name == "read_public_page":
                AgentFetchRequest.model_validate(arguments)
            elif name in {"prepare_edit_batch", "apply_edit_batch", "publish_findings", "project_action"}:
                if set(arguments) != {"request"}:
                    raise ValueError("invalid request envelope")
                if name == "prepare_edit_batch" and self.cap_mode:
                    TypeAdapter(AssistantAssemblyRequestV1 | AssistantProjectActionPrepareV1).validate_python(arguments["request"])
                else:
                    {"prepare_edit_batch": AgentPrepareRequest, "apply_edit_batch": AgentApplyRequest,
                        "project_action": AssistantProjectActionPrepareV1 if self.cap_mode else AgentProjectAction,
                        "publish_findings": AgentPublishFindings}[name].model_validate(arguments["request"])
            else:
                raise ValueError("unknown tool")
            return None
        except AgentFailure as error:
            return error.code
        except ValidationError as error:
            self.calls += 1
            if name == "get_application_skills":
                self.argument_issues = [{"path": "skillQuery", "issue": "Omit query for the catalog, or use {skillId,resource?,cursor?} from it."}]
                return "AGENT_ARGUMENT_INVALID"
            if name in READ_TOOLS:
                self.argument_issues = [{"path": "query", "issue": "Use query:{kind,ids?,cursor?}; omit ids to read the whole collection."}]
                return "AGENT_ARGUMENT_INVALID"
            if name == "prepare_edit_batch":
                safe = {"operations", "target", "content", "text", "marks", "snapshotId", "blockId", "cellId", "field", "start", "end", "key", "snapshotIds", "kind", "replace_text"}
                if self.cap_mode:
                    safe |= {"protocolVersion", "proposalId", "version", "taskId", "phase", "unchanged", "unitId", "reason"}
                self.argument_issues = [{"path": ".".join(str(part) if type(part) is int and 0 <= part <= 100 else part if part in safe else "*" for part in issue["loc"])[:160],
                    "issue": issue["type"] if issue["type"] in {"missing", "extra_forbidden", "string_type", "list_type", "int_type", "literal_error", "union_tag_invalid", "union_tag_not_found", "too_long", "value_error", "greater_than_equal", "string_too_long"} else "invalid"}
                    for issue in error.errors(include_input=False, include_context=False, include_url=False)[:3]]
                return "AGENT_EDIT_INVALID"
            self.argument_issues = [{"path": "arguments", "issue": "Use the advertised tool argument schema."}]
            return "AGENT_ARGUMENT_INVALID"
        except (ValueError, TypeError):
            self.calls += 1
            if name == "get_application_skills":
                self.argument_issues = [{"path": "skillQuery", "issue": "Use {query:{skillId,resource?,cursor?}}, or {} for the catalog."}]
                return "AGENT_ARGUMENT_INVALID"
            if name in READ_TOOLS:
                self.argument_issues = [{"path": "query", "issue": "Use the query object wrapper, not top-level kind/ids/cursor."}]
                return "AGENT_ARGUMENT_INVALID"
            if name == "prepare_edit_batch":
                self.argument_issues = [{"path": "request", "issue": "expected_object"}]
                return "AGENT_EDIT_INVALID"
            if name in {"check_resume", "read_public_page", "apply_edit_batch", "publish_findings", "project_action"}:
                self.argument_issues = [{"path": "arguments", "issue": "Use the advertised tool argument wrapper."}]
                return "AGENT_ARGUMENT_INVALID"
            return "AGENT_TOOL_DENIED"

    def preflight_failure(self, code):
        result = {"error": {"code": code}}
        if self.argument_issues:
            result["argumentIssues"] = self.argument_issues
            if self.cap_mode and code == "AGENT_EDIT_INVALID":
                result["format"] = "Use request:{protocolVersion:1,taskId,key,phase:'append'|'finalize',proposalId?,version:1,operations:[],snapshotIds:[],unchanged:[]}. Correct shape errors only; no field grants Apply authority."
                return result
            if self.argument_issues[0]["path"] == "skillQuery":
                result["format"] = "Use {} for the catalog, or {query:{skillId:'import-resume',resource:'SKILL.md',cursor:null}}. Follow top-level nextCursor with the same skillId/resource."
                return result
            result["format"] = ("Read arguments use {query:{kind:'document',cursor:null}}. Omit ids to read all blocks, or pass known IDs. Follow nextCursor using the same query."
                if self.argument_issues[0]["path"] == "query" else "Use the advertised request wrapper. replace_text target requires snapshotId, blockId, cellId (null outside tables), field, start, end. content contains text and optional marks, not styles. Correct shape errors only; never retry permission denial.")
        return result

    async def call(self, name, arguments):
        try:
            async with self.gate:
                self.guard()
                from .capabilities import catalog, check_task, guard_tool
                task_check = name == "get_project_resources" and isinstance(arguments, AssistantTaskRequestV1)
                if self.calls >= limits.TOOL_CALLS:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
                self.calls += 1
                if not task_check:
                    guard_tool(self, name, arguments)
                if self.result_bytes >= limits.TOOL_TOTAL_BYTES:
                    raise AgentFailure("AGENT_TOOL_LIMIT")
                if task_check:
                    service = getattr(self.service, "catalog_service", self.service)
                    if not getattr(service, "assistant_protocol_enabled", False):
                        raise AgentFailure("AGENT_TOOL_DENIED")
                    result = check_task(catalog(service, self.control.project_id,
                        allow_edits=self.run.allow_edits, allow_web=self.run.allow_web), arguments)
                    if arguments.stage == "generation":
                        if result.availability.state != "available":
                            self.planning_revoked, self.planned_task = True, None
                        elif self.planning_revoked or self.planned_task is not None and arguments.task_id != self.planned_task:
                            from packages.resume_core.agent_edits import AgentPolicyFailure
                            self.planning_revoked, self.planned_task = True, None
                            raise AgentPolicyFailure("ASSISTANT_TASK_LOCKED", code="AGENT_TOOL_DENIED")
                        else:
                            self.planned_task = arguments.task_id
                elif name in READ_TOOLS:
                    if name == "get_resume_context" and arguments.kind == "context" and arguments.ids:
                        arguments = arguments.model_copy(update={"kind": "document"})
                    expected = READ_TOOLS[name]
                    if arguments.kind != expected and not (name == "get_resume_context" and arguments.kind == "document"):
                        raise AgentFailure("AGENT_TOOL_DENIED")
                    with self.service.projects.state_lock:
                        self.guard()
                        result = self.book.read(arguments)
                elif name == "get_application_skills":
                    result = self.skills.read(arguments)
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
                    if self.cap_mode:
                        if isinstance(arguments, AssistantProjectActionPrepareV1):
                            if arguments.request.action in {"undo", "redo"}:
                                from .history_proposals import prepare_history
                                result = prepare_history(self, arguments)
                            else:
                                from .action_proposals import prepare_action
                                result = await prepare_action(self, arguments)
                        elif isinstance(arguments, AssistantAssemblyRequestV1):
                            from .proposals import assemble
                            result = assemble(self, arguments)
                        else:
                            raise AgentFailure("AGENT_PROTOCOL")
                    elif not self.run.allow_edits:
                        raise AgentFailure("AGENT_TOOL_DENIED")
                    else:
                        from .edits import prepare
                        result = prepare(self, arguments)
                elif name == "apply_edit_batch":
                    if not self.run.allow_edits:
                        raise AgentFailure("AGENT_TOOL_DENIED")
                    result = await self.service.publication.offer(self, arguments.batch_id)
                elif name == "project_action":
                    if self.cap_mode:
                        if not isinstance(arguments, AssistantProjectActionPrepareV1):
                            raise AgentFailure("AGENT_PROTOCOL")
                        if arguments.request.action not in {"export_docx", "export_project"}:
                            if arguments.request.action in {"undo", "redo"}:
                                from .history_proposals import prepare_history
                                result = prepare_history(self, arguments)
                            else:
                                from .action_proposals import prepare_action
                                result = await prepare_action(self, arguments)
                        else:
                            from .project_actions import project_action
                            result = await project_action(self, arguments.request)
                    else:
                        from .project_actions import project_action
                        result = await project_action(self, arguments)
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
            if getattr(error, "reason_code", None):
                from .capabilities import availability
                failure["reason"] = availability("unsupported", error.reason_code).reason
            if name in READ_TOOLS and error.code in {"AGENT_SCOPE_INVALID", "AGENT_STALE_READ"}:
                failure["format"] = "The cursor is invalid, expired, or belongs to a changed snapshot. Restart this read with cursor:null; do not edit from the incomplete read."
            if name == "publish_findings" and error.code == "AGENT_EVIDENCE_INVALID":
                failure["format"] = "Use a full document read snapshot. Prose targets require cellId, recordId, fieldKey, start and end all null for the whole block. sourceIds must be stored IDs, not URLs."
            return failure
        except (ValidationError, ValueError):
            return {"error": {"code": "AGENT_ARGUMENT_INVALID"}, "format": "Correct the declared argument shape; access has not been denied."}
        except Exception:
            return {"error": {"code": "AGENT_PROTOCOL"}}

    def check(self):
        with self.service.projects.state_lock:
            self.guard()
            workspace = self.service.projects.read(self.control.project_id)
            structure, links = "valid", "valid"
            try:
                type(workspace).model_validate(workspace.model_dump(by_alias=True))
            except ValueError:
                structure, links = "invalid", "invalid"
            try:
                from packages.resume_core.agent_edits import validate_references
                validate_references(workspace)
            except AgentFailure:
                links = "invalid"
            try:
                validate_export(workspace.project.document)
                export = "ready"
            except ValueError:
                export = "invalid"
            return {"changed": False, "documentRevision": workspace.document_revision,
                "factsRevision": workspace.project.facts.revision, "timeline": timeline_report(workspace),
                "structure": structure, "links": links, "export": export,
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
