"""Assistant runs on the repository (D109, plan 2.8): one run per project, a pinned read snapshot, events in a ring
buffer and a JSON-lines file, and proposals that only the user applies.

The project stays editable during a run: the run pins the committed workspace object at its start and reads only
that object. Nothing here writes the project file except `proposals.apply`, which the user calls.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
import threading
import time
import typing

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.assistant_store import AgentFailure, AssistantStore, identity, timestamp
from packages.resume_core.models.agent import AgentError, AgentEvent, AgentMessage, AgentReference, AgentUsage, ErrorCode
from packages.resume_core.models.assistant import (TERMINAL, AssistantCapabilitiesV1, AssistantErrorV1,
    AssistantEventsV1, AssistantFileV1, AssistantMessagesV1, AssistantRunV1, ModelChoiceV1)
from packages.resume_core.project_repository import RepositoryFailure
from packages.resume_core.templates.presentation import snapshot_identity

from resume_api.agent.runtime import BASE_INSTRUCTIONS, RuntimeInput, RuntimeResult
from resume_api.inference_admission import INFERENCE
from resume_api.projects.errors import ProjectFailure

from . import context
from .skills import INSTRUCTIONS as SKILL_INSTRUCTIONS
from .tools import TOOL_NAMES, ToolSession

DEVELOPER_INSTRUCTIONS = ("Use only the bound FoldCV MCP tools and native web search when internet is allowed. Do not "
    "use shell, files, plugins, other agents or providers. Read before proposing. propose_changes stores a preview "
    "that the user applies in the panel; never claim that a proposal is saved. Keep unsupported facts as findings. "
    "If a tool returns an error with detail, correct the arguments and retry within the same turn; do not retry a "
    "permission refusal. Write final answers in plain Russian without internal codes, ids, paths or tool names."
    + SKILL_INSTRUCTIONS)
KNOWN_CODES = frozenset(typing.get_args(ErrorCode))
FILES_KEPT = 10
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentConnection:
    """The model connection as a run sees it: ready, the offered models, the epoch a run is bound to."""
    ready: bool
    models: tuple[str, ...]
    epoch: str
    reason: str | None = None
    reasoning: dict = field(default_factory=dict)

    def effort(self, model, chosen):
        """The chosen assistant effort, else the model's catalog default; None keeps the runtime default."""
        metadata = self.reasoning.get(model)
        return chosen or (metadata.default if metadata is not None else None)

    def refuses(self, model, effort):
        metadata = self.reasoning.get(model)
        return effort is not None and metadata is not None and effort not in metadata.supported


@dataclass
class Control:
    project_id: str
    conversation_id: str
    run: AssistantRunV1
    queued_at: float
    cancel: threading.Event = field(default_factory=threading.Event)
    task: asyncio.Task | None = None
    events: deque = field(default_factory=lambda: deque(maxlen=500))
    sequence: int = 0
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    text: str = ''
    tools: object = None
    # Set when the project is deleted: the ending run writes no more assistant files.
    deleted: bool = False
    effort: str | None = None

    @property
    def run_id(self):
        return self.run.id


class AssistantService:
    def __init__(self, projects, runtime, connection, *, fetcher=None, wait_seconds=15.0):
        self.projects, self.runtime, self.connection = projects, runtime, connection
        root = projects.repository.root
        self.store = AssistantStore(root)
        self.settings = AgentSettingsStore(root)
        self._fetcher = fetcher
        self.wait_seconds = wait_seconds
        self.controls: dict[str, Control] = {}
        self.files: OrderedDict = OrderedDict()
        self.lock = threading.RLock()
        self.loop = None
        self.closed = False
        self.verified = set()
        # Run files (event lines, the run state, the answer, sources, findings, proposals) are written on this one
        # thread: in order, and never on the event loop.
        self.writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix='assistant-files')

    async def write(self, work, *args):
        return await asyncio.wrap_future(self.writer.submit(work, *args))

    @property
    def fetcher(self):
        if self._fetcher is None:
            from resume_api.agent.web import PublicFetcher
            self._fetcher = PublicFetcher(self.projects.repository.root / 'assistant-fetch')
        return self._fetcher

    # Capabilities and settings

    def capabilities(self):
        connection = self.connection()
        settings = self.settings.load()
        model = settings.selected_agent_model
        reason = ('AGENT_DISABLED' if not settings.enabled else 'AGENT_CLEANUP_FAILED' if INFERENCE.blocked else
            'AGENT_RUNTIME_UNSUPPORTED' if self.runtime is None else
            connection.reason or 'AGENT_CONNECTION_UNAVAILABLE' if not connection.ready else
            'AGENT_MODEL_REQUIRED' if model is None else
            'AGENT_MODEL_UNAVAILABLE' if model not in connection.models else
            'AGENT_MODEL_INCOMPATIBLE' if connection.refuses(model, connection.effort(model, settings.reasoning_effort))
            else None)
        models = [ModelChoiceV1(model=value, state='verified' if (connection.epoch, value) in self.verified else 'unverified')
            for value in connection.models]
        return AssistantCapabilitiesV1(ready=reason is None, unavailable=AssistantErrorV1(code=reason) if reason else None,
            models=models, webAvailable=self.runtime is not None, tools=list(TOOL_NAMES))

    # Conversations

    def conversations(self, project_id):
        self._require_project(project_id)
        from packages.resume_core.models.assistant import AssistantConversationListV1
        return AssistantConversationListV1(items=self.store.conversations(project_id))

    def create_conversation(self, project_id):
        self._require_project(project_id)
        value = self.store.create_conversation(project_id)
        return self._conversation(value)

    @staticmethod
    def _conversation(stored):
        from packages.resume_core.models.assistant import AssistantConversationV1
        return AssistantConversationV1(id=stored.id, title=stored.title, createdAt=stored.created_at, updatedAt=stored.updated_at)

    def messages(self, project_id, conversation_id):
        stored = self.store.conversation(project_id, conversation_id)
        runs = [self._current_run(run) for run in stored.runs]
        with self.lock:
            files = [value[4] for value in self.files.values() if value[0] == project_id and value[5] == conversation_id]
        return AssistantMessagesV1(conversation=self._conversation(stored), messages=stored.messages, sources=stored.sources,
            findings=stored.findings, runs=runs, files=files)

    def _current_run(self, run):
        control = self.controls.get(run.id)
        if control is not None:
            return control.run
        if run.state not in TERMINAL:
            # A run of an earlier service process; its outcome is unknown and nothing was saved by it.
            return run.model_copy(update={'state': 'interrupted', 'error': AssistantErrorV1(code='AGENT_INTERRUPTED')})
        return run

    def _require_project(self, project_id):
        try:
            workspace = self.projects.repository.read(project_id)
        except RepositoryFailure as error:
            raise ProjectFailure(error.code, 404 if error.code in {'PROJECT_NOT_FOUND', 'PROJECT_DELETED'} else 409) from None
        if workspace.project is None:
            raise ProjectFailure('ASSISTANT_PROJECT_NOT_AUTHORED', 409)
        return workspace

    # Runs

    def active(self, project_id):
        # A control without a task is a run that submit is still starting.
        return any(control.project_id == project_id and (control.task is None or not control.task.done())
            for control in list(self.controls.values()))

    async def submit(self, project_id, conversation_id, request):
        if self.closed:
            raise ProjectFailure('AGENT_CONNECTION_UNAVAILABLE', 409)
        if not request.message.strip():
            raise ProjectFailure('INVALID_REQUEST', 422)
        existing, workspace, settings = await asyncio.to_thread(self._admit, project_id, conversation_id, request)
        if existing is not None:
            return self._current_run(existing)
        # No await from here to the reserved control, so two submits cannot both start a run.
        starting = next((control.run for control in self.controls.values() if control.conversation_id == conversation_id
            and control.run.client_request_id == request.client_request_id), None)
        if starting is not None:
            return starting
        if self.closed:
            raise ProjectFailure('AGENT_CONNECTION_UNAVAILABLE', 409)
        if self.active(project_id):
            raise ProjectFailure('ASSISTANT_RUN_ACTIVE', 409)
        now = timestamp()
        run = AssistantRunV1(id=identity('run'), conversationId=conversation_id, projectId=project_id,
            clientRequestId=request.client_request_id, state='queued', allowEdits=request.allow_edits,
            allowWeb=request.allow_web, model=settings.selected_agent_model, baseRevision=workspace.project_revision,
            createdAt=now, finishedAt=None, error=None, usage=None)
        message = AgentMessage(id=identity('message'), role='user', text=request.message, runId=run.id, timestamp=now,
            sources=[], findings=[], truncated=False, error=None)

        def record(conversation):
            if not conversation.title:
                conversation.title = request.message.strip().splitlines()[0][:120]
            conversation.messages.append(message)
            conversation.runs.append(run)
        control = self.controls[run.id] = Control(project_id, conversation_id, run, time.monotonic(),
            effort=self.connection().effort(run.model, settings.reasoning_effort))
        try:
            await asyncio.to_thread(self.store.update_conversation, project_id, conversation_id, record)
        except BaseException:
            self.controls.pop(run.id, None)
            raise
        self.loop = asyncio.get_running_loop()
        control.task = asyncio.create_task(self._drive(control, request))
        return run

    def _admit(self, project_id, conversation_id, request):
        """A submit's reads, in a worker thread: the run of an earlier send of this request, readiness, the project, settings."""
        stored = self.store.conversation(project_id, conversation_id)
        existing = next((run for run in stored.runs if run.client_request_id == request.client_request_id), None)
        if existing is not None:
            return existing, None, None
        capability = self.capabilities()
        if not capability.ready:
            raise ProjectFailure(capability.unavailable.code, 409)
        return None, self._require_project(project_id), self.settings.load()

    def _set_run(self, control, **changes):
        control.run = control.run.model_copy(update=changes)
        self._store_run(control)

    def _store_run(self, control):
        if control.deleted:
            return

        def record(conversation):
            conversation.runs = [control.run if run.id == control.run.id else run for run in conversation.runs]
        self.store.update_conversation(control.project_id, control.conversation_id, record)

    def _store_run_quietly(self, control):
        try:
            self._store_run(control)
        except AgentFailure:
            LOG.warning('assistant run state not saved')

    def emit(self, control, kind, payload, *, terminal=False):
        if control.cancel.is_set() and not terminal and kind not in {'run.state_changed'}:
            return
        with self.lock:
            event = self._event(control, kind, payload)
            control.events.append(event)
            # Deltas stay in memory only; the transcript keeps the final text. Under the lock the lines reach the
            # writer in sequence order.
            if kind != 'message.delta':
                self.writer.submit(self._append, control, event)
        self._wake(control)

    def _event(self, control, kind, payload):
        with self.lock:
            control.sequence += 1
            if kind == 'message.delta':
                control.text += payload.get('text', '')
            if kind == 'usage.reported':
                control.run = control.run.model_copy(update={'usage': AgentUsage.model_validate(payload)})
            return AgentEvent.model_validate({'schemaVersion': 1, 'id': identity('event'), 'sequence': control.sequence,
                'projectId': control.project_id, 'conversationId': control.conversation_id, 'runId': control.run_id,
                'timestamp': timestamp(), 'type': kind, 'payload': payload})

    def _append(self, control, event):
        if control.deleted:
            return
        try:
            self.store.append_event(control.project_id, control.run_id, event)
        except AgentFailure:
            pass

    def _wake(self, control):
        loop = self.loop
        if loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            control.changed.set()
        else:
            loop.call_soon_threadsafe(control.changed.set)

    def _running(self, control):
        if control.cancel.is_set():
            raise AgentFailure('AGENT_CANCELLED')
        # The runtime calls this on the event loop: the stored run state follows on the writer.
        control.run = control.run.model_copy(update={'state': 'running'})
        self.writer.submit(self._store_run_quietly, control)
        self.emit(control, 'run.state_changed', {'state': 'running', 'error': None, 'savedBatchId': None, 'outcomeUnknown': False})

    async def _drive(self, control, request):
        result = RuntimeResult(error='AGENT_RUNTIME_UNSUPPORTED')
        tools = None
        loop = asyncio.get_running_loop()
        pin = ExitStack()
        try:
            if self.runtime is None:
                raise AgentFailure('AGENT_RUNTIME_UNSUPPORTED')
            pinned, history = await asyncio.to_thread(self._pin, pin, control)
            prompt = context.prompt(pinned, message=request.message, history=history, allow_edits=control.run.allow_edits,
                allow_web=control.run.allow_web, selection=request.selection)
            tools = control.tools = ToolSession(self, control, pinned)
            await tools.start()

            def close_tools(timeout):
                asyncio.run_coroutine_threadsafe(tools.close(), loop).result(timeout=min(3, timeout))
            value = RuntimeInput(model=control.run.model, prompt=prompt, url=tools.url, token=tools.token,
                tools=tuple(tools.names), allow_web=control.run.allow_web, before_start=lambda: self._running(control),
                revoke=tools.revoke, close_tools=close_tools, queued_at=control.queued_at,
                developer_instructions=DEVELOPER_INSTRUCTIONS,
                **({'reasoning_effort': control.effort} if control.effort else {}))
            result = await self.runtime.run(value, control.cancel,
                lambda kind, payload: self.emit(control, kind, payload))
        except asyncio.CancelledError:
            result = RuntimeResult(state='cancelled', error='AGENT_CANCELLED')
        except AgentFailure as error:
            result = RuntimeResult(state='cancelled' if error.code == 'AGENT_CANCELLED' else 'failed', error=error.code)
        except (RepositoryFailure, ProjectFailure) as error:
            result = RuntimeResult(error=error.code)
        except Exception:
            LOG.exception('assistant run failed')
            result = RuntimeResult(error='AGENT_PROTOCOL')
        finally:
            if tools is not None:
                try:
                    await asyncio.wait_for(tools.close(), 3)
                except Exception:
                    INFERENCE.block()
                    result.state, result.error = 'failed', 'AGENT_CLEANUP_FAILED'
            if control.cancel.is_set() and result.state != 'completed':
                result.state, result.error = 'cancelled', 'AGENT_CANCELLED'
            terminal = None
            try:
                # The answer and the final run state follow the run's pending lines on the writer, then the terminal
                # line. The terminal event shows only with the control gone: a poll that sees it reads complete files
                # and a new run can start at once.
                terminal = await self.write(self._finish, control, result)
                if terminal is not None:
                    await self.write(self._append, control, terminal)
            finally:
                if terminal is not None:
                    with self.lock:
                        control.events.append(terminal)
                # From here the run is read from its files; the control would keep the pinned workspace alive.
                self.controls.pop(control.run_id, None)
                self._wake(control)
                try:
                    await asyncio.to_thread(pin.close)
                except Exception:
                    LOG.exception('assistant run unpin failed')

    def _pin(self, pin, control):
        """Pin the project for the run; read its committed workspace and the earlier messages. A worker-thread call:
        a load or a held project lock must not stall the event loop."""
        session = pin.enter_context(self.projects.repository.pinned(control.project_id))
        with session.lock:
            pinned = session.workspace
        return pinned, self.store.conversation(control.project_id, control.conversation_id).messages[:-1]

    def _finish(self, control, result):
        state = result.state if result.state in TERMINAL else 'failed'
        if control.deleted:
            control.run = control.run.model_copy(update={'state': state, 'finished_at': timestamp()})
            self._wake(control)
            return
        if state == 'completed' and result.tool_calls and getattr(self.runtime, 'native', False):
            self.verified.add((self.connection().epoch, control.run.model))
        text = (result.text or control.text).encode()[:limits.ASSISTANT_TEXT_BYTES].decode('utf-8', 'ignore')
        error = AssistantErrorV1(code=result.error) if result.error and state != 'completed' else None
        try:
            stored = self.store.conversation(control.project_id, control.conversation_id)
            sources = [AgentReference(id=source.id, label=source.title[:256] or source.final_url[:256])
                for source in stored.sources if source.run_id == control.run_id][:20]
            findings = [AgentReference(id=finding.id, label=finding.message[:256])
                for finding in stored.findings if finding.run_id == control.run_id][:20]
            message = AgentMessage(id=identity('message'), role='assistant', text=text, runId=control.run_id,
                timestamp=timestamp(), sources=sources, findings=findings, truncated=result.truncated,
                error=AgentError(code=error.code if error.code in KNOWN_CODES else 'AGENT_PROTOCOL') if error else None)

            def record(conversation):
                conversation.messages.append(message)
            self.store.update_conversation(control.project_id, control.conversation_id, record)
            self._set_run(control, state=state, error=error, finished_at=timestamp())
        except AgentFailure:
            control.run = control.run.model_copy(update={'state': state, 'error': error, 'finished_at': timestamp()})
        return self._event(control, 'run.state_changed', {'state': state, 'error': {'code': error.code
            if error.code in KNOWN_CODES else 'AGENT_PROTOCOL'} if error else None, 'savedBatchId': None,
            'outcomeUnknown': False})

    async def cancel(self, project_id, run_id):
        control = self.controls.get(run_id)
        if control is None or control.project_id != project_id:
            _conversation, run = await asyncio.to_thread(self.store.find_run, project_id, run_id)
            return self._current_run(run)
        if control.run.state not in TERMINAL:
            control.cancel.set()
            if control.run.state == 'queued' or control.run.state == 'running':
                control.run = control.run.model_copy(update={'state': 'cancelling'})
            self._wake(control)
        return control.run

    async def events(self, project_id, run_id, after=0, wait=None):
        control = self.controls.get(run_id)
        if control is None or control.project_id != project_id:
            return await asyncio.to_thread(self._stored_events, project_id, run_id, after)
        wait = self.wait_seconds if wait is None else max(0.0, min(float(wait), 30.0))
        deadline = time.monotonic() + wait
        while True:
            with self.lock:
                fresh = [event for event in control.events if event.root.sequence > after]
                control.changed.clear()
            remaining = deadline - time.monotonic()
            if fresh or control.run.state in TERMINAL or remaining <= 0:
                break
            try:
                await asyncio.wait_for(control.changed.wait(), remaining)
            except asyncio.TimeoutError:
                pass
        return AssistantEventsV1(run=control.run, events=fresh, next=fresh[-1].root.sequence if fresh else after)

    def _stored_events(self, project_id, run_id, after):
        _conversation, run = self.store.find_run(project_id, run_id)
        events = self.store.events(project_id, run_id, after)
        return AssistantEventsV1(run=self._current_run(run), events=events,
            next=events[-1].root.sequence if events else after)

    def record_source(self, control, source):
        if control.deleted:
            return

        def record(conversation):
            conversation.sources.append(source)
        self.store.update_conversation(control.project_id, control.conversation_id, record)
        self.emit(control, 'source.ready', {'id': source.id})

    def source_ids(self, control):
        stored = self.store.conversation(control.project_id, control.conversation_id)
        return {source.id for source in stored.sources}

    def record_findings(self, control, findings):
        if control.deleted:
            return

        def record(conversation):
            conversation.findings.extend(findings)
        self.store.update_conversation(control.project_id, control.conversation_id, record)
        for finding in findings:
            self.emit(control, 'finding.ready', {'id': finding.id})

    # Exports for the export_document tool: the ordinary export task, served by id for a while.

    async def export(self, project_id, fmt, control=None):
        workspace = await asyncio.to_thread(self.projects.repository.read, project_id)
        if fmt == 'docx':
            result = await self.projects.exports.export(project_id, snapshot_identity(workspace), None, trusted=True)
            data, filename, media = result.artifact, 'resume.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            from types import SimpleNamespace
            from resume_api.projects.archive import export_archive
            request = SimpleNamespace(editor_token=None, project_revision=workspace.project_revision,
                document_revision=workspace.document_revision)
            data = await asyncio.to_thread(export_archive, self.projects, project_id, request, trusted=True)
            filename, media = 'resume.foldcv', 'application/vnd.foldcv.project+zip'
        identifier = identity('file')
        value = AssistantFileV1(id=identifier, format=fmt, url=f'/v2/projects/{project_id}/assistant/files/{identifier}',
            filename=filename, size=len(data))
        with self.lock:
            self.files[identifier] = (project_id, filename, media, data, value, control.conversation_id if control else None)
            while len(self.files) > FILES_KEPT:
                self.files.popitem(last=False)
        if control is not None:
            self.emit(control, 'file.ready', {'id': identifier})
        return value

    def file(self, project_id, file_id):
        with self.lock:
            found = self.files.get(file_id)
        if found is None or found[0] != project_id:
            raise ProjectFailure('ASSISTANT_FILE_NOT_FOUND', 404)
        return found[1:4]

    # Lifecycle

    # The project callers run in worker threads while runs end on the event loop, so they iterate over copies.
    def stop_project(self, project_id):
        for control in list(self.controls.values()):
            if control.project_id == project_id:
                control.cancel.set()

    def stop_all(self):
        """A connection change ends every run; its result is recorded as cancelled."""
        for control in self.controls.values():
            control.cancel.set()
            self._wake(control)

    async def shutdown(self):
        self.closed = True
        tasks = [control.task for control in self.controls.values() if control.task is not None and not control.task.done()]
        for control in self.controls.values():
            control.cancel.set()
        if tasks:
            await asyncio.wait(tasks, timeout=5)
        await self.write(lambda: None)

    def project_deleted(self, project_id):
        for control in list(self.controls.values()):
            if control.project_id == project_id:
                control.deleted = True
        self.stop_project(project_id)
        with self.lock:
            for identifier in [key for key, value in self.files.items() if value[0] == project_id]:
                del self.files[identifier]
        # Writes queued before the flag skip themselves; waiting for them keeps a late one from recreating the files.
        self.writer.submit(lambda: None).result()
        self.store.delete_project(project_id)
