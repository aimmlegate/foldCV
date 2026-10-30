"""The ten run-bound tools (plan 2.8). Reads serve the pinned workspace; only `propose_changes` and
`publish_findings` store anything, and neither writes the project."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import threading
from typing import Literal

from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from packages.resume_core import agent_limits as limits
from packages.resume_core.assistant_compiler import CompileFailure
from packages.resume_core.assistant_store import AgentFailure, identity
from packages.resume_core.models.agent import AgentAnchor, AgentFetchRequest, AgentFinding
from packages.resume_core.models.assistant import ProposeChangesV1, PublishFindingsV1
from packages.resume_core.project_repository import RepositoryFailure
from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.rich_fields import inline_groups
from packages.resume_core.rich_mutations import inline_text, utf16_slice

from resume_api.agent.mcp import PrivateMcp
from resume_api.agent.web import bind_run
from resume_api.projects.errors import ProjectFailure

from . import context
from .skills import read_skill

TOOL_NAMES = ('read_resume', 'find_text', 'read_facts', 'read_original', 'read_skill', 'check_resume',
    'read_public_page', 'export_document', 'propose_changes', 'publish_findings')


@dataclass(frozen=True)
class Stored:
    """A reply whose `save` (the store write and its event) runs only after the reply passed every limit."""
    value: dict
    save: object


class ToolSession(PrivateMcp):
    names = TOOL_NAMES

    def __init__(self, service, control, pinned):
        self.service, self.control, self.pinned = service, control, pinned
        self.calls = self.fetches = self.result_bytes = 0
        self.fetch_cancel = threading.Event()
        self.gate = asyncio.Lock()
        super().__init__(self)
        self.register()

    def revoke(self):
        self.active = False
        self.fetch_cancel.set()

    async def _close(self):
        # PrivateMcp's own close calls dispatcher.close; the dispatcher is this session.
        self.active, self.token = False, ''
        self.revoke()
        self.server.should_exit = True
        try:
            if self.task is not None:
                await asyncio.wait_for(self.task, 2)
        finally:
            self.listener.close()

    def register(self):
        tool = self.sdk.tool(structured_output=False)

        @tool
        async def read_resume(page: int = 0) -> CallToolResult:
            """Read the resume blocks in document order, one page at a time, starting at page 0; follow nextPage until it
            is null. Each block
            has id, type, parentId, afterId and containers (key content/caption/cell id, text, field occurrences)."""
            return await self.call('read_resume', lambda: context.paged(context.document_entries(self.pinned), page))

        @tool
        async def find_text(query: str) -> CallToolResult:
            """Find literal text in the resume and facts. Matches give blockId, container key and UTF-16 start/end."""
            if not 0 < len(query) <= 1000:
                return self.failure('AGENT_ARGUMENT_INVALID')
            return await self.call('find_text', lambda: context.find(self.pinned, query))

        @tool
        async def read_facts(page: int = 0) -> CallToolResult:
            """Read the working facts (builtin records and template entities), one page at a time."""
            return await self.call('read_facts', lambda: context.paged(context.fact_entries(self.pinned), page))

        @tool
        async def read_original(sourceId: str | None = None, page: int = 0) -> CallToolResult:  # noqa: N803
            """Without sourceId: the list of original sources. With sourceId: its extracted text units, paged. Empty or
            unavailable extraction does not mean the original file is empty; report it instead of guessing."""
            return await self.call('read_original', lambda: context.paged(context.source_entries(self.pinned, sourceId), page))

        @tool
        async def read_skill(name: Literal['import-resume', 'format-resume'], resource: str = 'SKILL.md') -> CallToolResult:
            """Read a bundled skill (SKILL.md) or one of its listed references. Skills grant no permission."""
            return await self.call('read_skill', lambda: read_skill_resource(name, resource))

        @tool
        async def check_resume() -> CallToolResult:
            """Deterministic checks of the resume (empty blocks, links without target, open import issues); no edits."""
            return await self.call('check_resume', lambda: context.check(self.pinned))

        @tool
        async def read_public_page(url: str) -> CallToolResult:
            """Fetch a public HTML or plain-text page when internet is allowed. Cite it by the returned source id."""
            return await self.call('read_public_page', lambda: self.fetch(url))

        @tool
        async def export_document(format: Literal['docx', 'foldcv']) -> CallToolResult:  # noqa: A002
            """Export the saved resume (not an unapplied proposal) as DOCX or a .foldcv project file; returns a link."""
            return await self.call('export_document', lambda: self.export(format))

        @tool
        async def propose_changes(request: ProposeChangesV1) -> CallToolResult:
            """Store one proposal for the user to preview and apply; it does not change the resume. Ops:
            set_block_text {blockId, cellId?, field?, text} rewrites a whole container and must keep every field
            occurrence and link text verbatim and in order; replace_text {blockId, find, replace} changes one exact
            phrase inside one span; insert_blocks {afterBlockId or parentId, blocks:[{kind,text,level?}]};
            delete_blocks {blockIds}; move_block {blockId, afterBlockId or parentId}; format_block {blockId, kind?,
            level?, alignment?, textColor?, backgroundColor?}; update_fact {recordId, field, value}; create_fact
            {kind, values, jobId?, targetId?}: kind employment (values employer, role, start, end, present), period
            (jobId; values start, end, present) or technology (values display; jobId for a job's line; targetId when a
            refusal lists several lines); delete_fact {recordId}. history {direction} and action {action: rename,
            formatting_date, archive, restore or delete; value?; targetId?} are proposals of their own. One call carries
            at most 64 KiB of JSON and 100 ops; split a larger edit into several proposals over different blocks."""
            return await self.call('propose_changes', lambda: self.propose(request))

        @tool
        async def publish_findings(request: PublishFindingsV1) -> CallToolResult:
            """Store remarks without editing. A target names blockId (with optional cellId, start, end) or recordId
            (with optional fieldKey). sourceIds are ids returned by read_public_page. One call carries at most 64 KiB
            of JSON and 20 findings; publish more in further calls."""
            return await self.call('publish_findings', lambda: self.findings(request))

    # The listener's envelope checks before the SDK sees a call (agent/mcp.py).
    def preflight(self, params, size):
        if not self.active or self.control.cancel.is_set():
            return 'AGENT_CANCELLED'
        if self.calls >= limits.TOOL_CALLS:
            return 'AGENT_TOOL_LIMIT'
        if (not isinstance(params, dict) or params.keys() - {'name', 'arguments', '_meta'} or params.get('name') not in TOOL_NAMES
                or not isinstance(params.get('arguments', {}), dict)):
            self.calls += 1
            return 'AGENT_ARGUMENT_INVALID'
        if size > limits.CALL_BYTES:
            self.calls += 1
            return 'AGENT_CALL_TOO_LARGE'
        return None

    def preflight_failure(self, code, size):
        if code == 'AGENT_CALL_TOO_LARGE':
            return {'error': {'code': code}, 'detail': [f'This call is {size} bytes of JSON; one call may carry at most '
                f'{limits.CALL_BYTES} bytes ({limits.CALL_BYTES // 1024} KiB). Split it into several smaller calls.']}
        return {'error': {'code': code}}

    def wire(self, value):
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(value))], isError='error' in value)

    def failure(self, code, detail=()):
        value = {'error': {'code': code}}
        if detail:
            value['detail'] = list(detail)
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(value))], isError=True)

    def guard(self):
        if not self.active or self.control.cancel.is_set():
            raise AgentFailure('AGENT_CANCELLED')

    async def call(self, name, work):
        async with self.gate:
            try:
                self.guard()
                if self.calls >= limits.TOOL_CALLS:
                    raise AgentFailure('AGENT_TOOL_LIMIT')
                self.calls += 1
                value = work()
                if asyncio.iscoroutine(value):
                    value = await value
                self.guard()
                value, save = (value.value, value.save) if isinstance(value, Stored) else (value, None)
                text = context.json_text(value)
                size = len(text.encode())
                if size > limits.TOOL_BYTES or self.result_bytes + size > limits.TOOL_TOTAL_BYTES:
                    raise AgentFailure('AGENT_TOOL_LIMIT')
                if save is not None:
                    # A stored draft, finding or source must reach the model as a success, so it is stored last.
                    await save()
                self.result_bytes += size
                return CallToolResult(content=[TextContent(type='text', text=text)], isError=False)
            except AgentFailure as error:
                return self.failure(error.code, getattr(error, 'detail', ()))
            except CompileFailure as error:
                return self.failure(error.code, error.detail)
            except (ProjectFailure, RepositoryFailure) as error:
                return self.failure(error.code)
            except ValidationError:
                return self.failure('AGENT_ARGUMENT_INVALID')
            except Exception:
                return self.failure('AGENT_PROTOCOL')

    async def fetch(self, url):
        if not self.control.run.allow_web:
            raise AgentFailure('AGENT_WEB_DISABLED')
        if self.fetches >= limits.PAGE_FETCHES:
            raise AgentFailure('AGENT_SOURCE_LIMIT')
        self.fetches += 1
        source = await self.service.fetcher.fetch(AgentFetchRequest(url=url), self.fetch_cancel)
        source = bind_run(source, self.control.run_id)
        excerpt, clipped = context.clip(source.text, 12000)
        value = source.model_dump(mode='json', by_alias=True)
        value.pop('text')
        return Stored({'source': value, 'excerpt': excerpt, 'excerptTruncated': clipped},
            lambda: self.service.write(self.service.record_source, self.control, source))

    async def export(self, fmt):
        # The export records itself in the project before its link reply exists; that reply stays under 1 KiB.
        if self.result_bytes + 1024 > limits.TOOL_TOTAL_BYTES:
            raise AgentFailure('AGENT_TOOL_LIMIT')
        return await self.service.export(self.control.project_id, fmt, self.control)

    async def propose(self, request):
        from .proposals import propose
        # Compiling may load the project or wait for its lock: off the event loop.
        proposal = await asyncio.to_thread(propose, self.service, self.control.run, self.pinned, request)

        def save():
            if getattr(self.control, 'deleted', False):
                return
            self.service.store.save_proposal(proposal)
            self.service.emit(self.control, 'proposal.ready', {'id': proposal.id})
        # The panel shows the preview; a reply carrying it could pass the reply limits for a large proposal.
        return Stored({'proposalId': proposal.id, 'kind': proposal.kind, 'changes': len(proposal.preview),
            'note': 'Stored as a preview; the user applies or discards it in the panel.'},
            lambda: self.service.write(save))

    async def findings(self, request):
        known = await asyncio.to_thread(self.service.source_ids, self.control)
        stored = []
        for item in request.findings:
            if not set(item.source_ids) <= known:
                raise AgentFailure('AGENT_EVIDENCE_INVALID')
            stored.append(AgentFinding(id=identity('finding'), runId=self.control.run_id, severity=item.severity,
                message=item.message, anchors=[self.anchor(target) for target in item.targets], sourceIds=item.source_ids))
        return Stored({'findingIds': [finding.id for finding in stored]},
            lambda: self.service.write(self.service.record_findings, self.control, stored))

    def anchor(self, target):
        project = self.pinned.project
        if target.block_id is not None:
            block = next((value for value in project.document.blocks() if value.id == target.block_id), None)
            spans = dict(inline_groups(block)).get(target.cell_id or 'content') if block is not None else None
            if spans is None and block is not None:
                spans = dict(inline_groups(block)).get('caption')
            if spans is None:
                raise AgentFailure('AGENT_EVIDENCE_INVALID')
            text = ''.join(inline_text(span) for span in spans)
            stamp = dependency(self.pinned, 'block', block.id)
        else:
            record = next((value for value in project.facts.records if value.id == target.record_id), None)
            if record is None:
                raise AgentFailure('AGENT_EVIDENCE_INVALID')
            text = context.record_text(self.pinned, record.id)
            stamp = dependency(self.pinned, 'record', record.id)
        maximum = len(text.encode('utf-16-le')) // 2
        start = target.start or 0
        end = target.end if target.end is not None else maximum
        if end > maximum:
            raise AgentFailure('AGENT_EVIDENCE_INVALID')
        text, _ = context.clip(utf16_slice(text, start, end)[:4000], 4096)
        return AgentAnchor(blockId=target.block_id, cellId=target.cell_id, recordId=target.record_id,
            fieldKey=target.field_key, start=target.start, end=target.end, text=text, dependencies=[stamp])


def read_skill_resource(name, resource):
    return read_skill(name, resource)
