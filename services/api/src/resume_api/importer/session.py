"""Import-only capabilities with durable, revision-checked draft batches."""

import asyncio
from pathlib import Path
import json

from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from packages.resume_core.import_agent import (ImportFailure, checksum, import_identity,
    source_parts, finish_draft, unplaced_parts)
from packages.resume_core.import_content import source_paragraphs, update_content, draft_content, paragraph_refs
from packages.resume_core.models.importing import ImportContent, ImportContentFinish, ImportDraft, ImportFinish, ImportRead
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.agent_store import AgentFailure
from packages.resume_core import agent_limits as limits
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rules import RulesFailure

from ..agent.mcp import PrivateMcp
from ..agent.runtime import BASE_INSTRUCTIONS
from ..gui_projects import ProjectFailure

SKILL = (Path(__file__).parent / "skills/import-resume/SKILL.md").read_text()
SKILL_SHA256 = checksum(SKILL)
MODELS = {"read_import": ImportRead, "save_import": ImportContent, "finish_import": ImportContentFinish}


class ImportCoordinator:
    def __init__(self, projects, identifier, run_id, rules, cancel, *, guard=lambda: None):
        self.projects, self.identifier, self.run_id = projects, identifier, run_id
        self.rules, self.cancel, self.authorize = rules, cancel, guard
        self.failure_code = None
        self.workspace = projects.read(identifier).model_copy(deep=True)
        if self.workspace.project is not None or self.workspace.pre_draft is None:
            raise ImportFailure("IMPORT_ALREADY_CREATED")
        self.sources = [s for s in self.workspace.pre_draft.sources if s.id == self.workspace.pre_draft.selected_source_id]
        self.parts = source_parts(self.sources)
        self.paragraphs = source_paragraphs(self.sources, self.parts)
        if not any(part.text.strip() for part in self.parts):
            raise ImportFailure("NO_USABLE_TEXT")
        if len(self.parts) > 2000 or sum(len(part.text.encode()) for part in self.parts) > 256 * 1024:
            raise ImportFailure("IMPORT_INPUT_TOO_LARGE")
        self.source_sha256 = import_identity(self.workspace, rules, SKILL_SHA256)

    def guard(self):
        if self.failure_code:
            raise ImportFailure(self.failure_code)
        if self.cancel.is_set():
            raise ImportFailure("CANCELLED")
        self.authorize()
        current = self.projects.read(self.identifier)
        if import_identity(current, self.projects.rules.load(), SKILL_SHA256) != self.source_sha256:
            raise ImportFailure("STALE_GENERATION")
        return current

    def fail(self, code):
        self.failure_code = self.failure_code or code

    def load(self):
        current = self.guard()
        draft = current.pre_draft.import_draft
        if draft is None or draft.run_id != self.run_id or draft.source_sha256 != self.source_sha256:
            raise ImportFailure("IMPORT_STALE_BATCH")
        return draft.model_copy(deep=True)

    def save(self, draft, *, previous=None, begin=False):
        projects = self.projects
        with projects.state_lock:
            current = self.guard()
            old = current.pre_draft.import_draft
            if not begin and (old is None or old.run_id != self.run_id or checksum(old) != previous):
                raise ImportFailure("IMPORT_STALE_BATCH")
            after = current.model_copy(deep=True)
            after.pre_draft.import_draft = draft
            jobs = getattr(projects, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                stored, _ = jobs.publisher.snapshot(self.identifier, digest_bytes(current), after,
                    "import_" + checksum([self.run_id, draft])[:32], originals=projects.originals,
                    artifacts=projects.artifacts, images=projects.images)
                jobs.publication.adopt(self.identifier, stored, digest_bytes(stored))
            else:
                projects.storage.save(after, projects.originals, projects.artifacts, projects.images)
                projects.adopt_committed(self.identifier, after, digest_bytes(after))

    def begin(self):
        with self.projects.state_lock:
            current = self.guard()
            old = current.pre_draft.import_draft
            if old is not None and old.source_sha256 == self.source_sha256 and old.skill_sha256 == SKILL_SHA256:
                draft = old.model_copy(deep=True)
                draft.run_id, draft.finished = self.run_id, False
            else:
                draft = ImportDraft(sourceSha256=self.source_sha256, skillSha256=SKILL_SHA256, runId=self.run_id)
            self.save(draft, begin=True)

    def update(self, request):
        with self.projects.state_lock:
            before = self.load()
            after = update_content(before, request, self.paragraphs, self.parts)
            if after != before:
                self.save(after, previous=checksum(before))
            return {"durable": True, "completed": False, "facts": len(after.facts),
                "unassignedRefs": paragraph_refs([p.key for p in unplaced_parts(after, self.parts)], self.paragraphs)}

    def finish(self, request):
        with self.projects.state_lock:
            before = self.load()
            after = finish_draft(before, ImportFinish(sequence=before.sequence, issues=request.issues), self.parts)
            if after != before:
                self.save(after, previous=checksum(before))
            return {"durable": True, "completed": False, "readyForPublication": True,
                "unassignedRefs": paragraph_refs([p.key for p in unplaced_parts(after, self.parts)], self.paragraphs)}


class ImportDispatcher:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.active, self.calls, self.bytes = True, 0, 0
        self.gate = asyncio.Lock()
        self.argument_issues = []
        self.read_keys = set()

    def revoke(self):
        self.active = False

    async def close(self):
        self.revoke()

    def guard(self):
        if not self.active:
            raise ImportFailure("CANCELLED")
        if self.calls >= limits.TOOL_CALLS or self.bytes >= limits.TOOL_TOTAL_BYTES:
            self.coordinator.fail("IMPORT_TOOL_LIMIT")
            raise ImportFailure("IMPORT_TOOL_LIMIT")
        self.coordinator.guard()

    def preflight(self, params):
        self.argument_issues = []
        try:
            self.guard()
            if not isinstance(params, dict) or params.get("name") not in MODELS:
                raise ImportFailure("IMPORT_TOOL_DENIED")
            args = params.get("arguments", {})
            if not isinstance(args, dict) or set(args) != {"request"}:
                raise ImportFailure("IMPORT_ARGUMENTS_INVALID")
            MODELS[params["name"]].model_validate(args["request"])
        except ValidationError as error:
            self.calls += 1
            self.argument_issues = [{"path": list(e["loc"]), "type": e["type"], "message": e["msg"][:300]}
                for e in error.errors(include_input=False, include_url=False)]
            return "IMPORT_ARGUMENTS_INVALID"
        except (ImportFailure, ProjectFailure, AgentFailure, BackgroundFailure, ProjectStoreFailure, RulesFailure) as error:
            self.calls += 1
            return error.code
        return None

    def preflight_failure(self, code):
        return {"error": {"code": code}, "argumentIssues": self.argument_issues}

    def wire(self, value):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        self.bytes += len(text.encode())
        if len(text.encode()) > limits.TOOL_BYTES or self.bytes > limits.TOOL_TOTAL_BYTES:
            self.coordinator.fail("IMPORT_TOOL_LIMIT")
            self.revoke()
            return CallToolResult(content=[TextContent(type="text", text='{"error":{"code":"IMPORT_TOOL_LIMIT"}}')], isError=True)
        return CallToolResult(content=[TextContent(type="text", text=text)], isError="error" in value)

    async def call(self, name, request):
        async with self.gate:
            try:
                self.guard()
                self.calls += 1
                coordinator = self.coordinator
                if name == "save_import":
                    return coordinator.update(request)
                if name == "finish_import":
                    if self.read_keys != {p.ref for p in coordinator.paragraphs}:
                        raise ImportFailure("IMPORT_SOURCE_NOT_READ")
                    return coordinator.finish(request)
                if name != "read_import":
                    raise ImportFailure("IMPORT_TOOL_DENIED")
                draft = coordinator.load()
                source = request.section == "source"
                items = coordinator.paragraphs if source else draft_content(draft, coordinator.paragraphs)
                selected, used, page = [], 0, None
                for item in items[request.offset:]:
                    if source:
                        marker = f"Page {item.page}\n" if item.page is not None and item.page != page else ""
                        hints = f" (layout: {item.hints})" if item.hints else ""
                        value = marker + f"[{item.ref}]{hints}\n{item.text}\n"
                    else:
                        value = item
                    size = len(json.dumps(value, ensure_ascii=False).encode())
                    if selected and used + size > 48000:
                        break
                    selected.append(value)
                    used += size
                    if source:
                        self.read_keys.add(item.ref)
                        page = item.page
                end = request.offset + len(selected)
                return {"section": request.section, "text" if source else "items": "".join(selected) if source else selected,
                    "nextOffset": end if end < len(items) else None, "savedFacts": len(draft.facts),
                    "savedOutline": bool(draft.blocks)}
            except (BackgroundFailure, ProjectStoreFailure, RulesFailure, OSError) as error:
                self.coordinator.fail(getattr(error, "code", "PROJECT_SAVE_FAILED"))
                self.revoke()
                return {"error": {"code": getattr(error, "code", "PROJECT_SAVE_FAILED")}}
            except (ImportFailure, ProjectFailure, AgentFailure) as error:
                result = {"error": {"code": error.code}}
                if error.code == "IMPORT_REFERENCE_INVALID":
                    result["error"]["message"] = (f"Use existing paragraph refs p1 through p{len(self.coordinator.paragraphs)}, "
                        "or inclusive ranges such as p2-p5. A range must end at or after its start.")
                elif error.code == "IMPORT_EVIDENCE_TOO_LARGE":
                    result["error"]["message"] = "Use narrower supporting references for each fact or profile; evidence exceeds the storage limit."
                elif error.code == "IMPORT_DRAFT_TOO_LARGE":
                    result["error"]["message"] = "The draft exceeds the storage limit. Reduce repeated placements or shorten fact values."
                return result


class ImportSession(PrivateMcp):
    def __init__(self, coordinator):
        self.coordinator = coordinator
        dispatcher = ImportDispatcher(coordinator)
        super().__init__(dispatcher)
        self.prompt = json.dumps({"task": "Import the complete selected resume using the bundled instructions.",
            "sources": [source.original_name for source in coordinator.sources]}, ensure_ascii=False)
        if len((self.prompt + SKILL + BASE_INSTRUCTIONS).encode()) > limits.CONTEXT_BYTES:
            self.listener.close()
            raise ImportFailure("IMPORT_INPUT_TOO_LARGE")
        self.register()

    def revoke(self):
        self.active = False
        self.dispatcher.revoke()

    def register(self):
        @self.sdk.tool(structured_output=False)
        async def read_import(request: ImportRead) -> CallToolResult:
            """Read paragraph text. Start with {}; follow nextOffset if present. section=draft reads saved content."""
            return self.dispatcher.wire(await self.dispatcher.call("read_import", request))

        @self.sdk.tool(structured_output=False)
        async def save_import(request: ImportContent) -> CallToolResult:
            """Save facts, sections or profile. Each supplied field replaces its saved value; omitted fields stay unchanged."""
            return self.dispatcher.wire(await self.dispatcher.call("save_import", request))

        @self.sdk.tool(structured_output=False)
        async def finish_import(request: ImportContentFinish) -> CallToolResult:
            """Finish after saving useful facts and sections; list source uncertainties in issues. Python applies the template."""
            return self.dispatcher.wire(await self.dispatcher.call("finish_import", request))
