"""Private assistant sidecars, independent of canonical snapshots and portable archives."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets

from pydantic import ValidationError

from . import agent_limits as limits
from .models.agent import (
    AgentConversation, AgentConversationPage, AgentConversationSummary, AgentEditReceipt,
    AgentBatchJournal, AgentError, AgentJournalRequest, AgentMessage, AgentMessagePage, AgentPageRequest, AgentPrepareResult,
    AgentProjectState, AgentResourcePage, AgentRun, AgentRunJournal, AgentRunRequest,
    TERMINAL_EDITS, TERMINAL_RUNS, wire_bytes,
)
from .project_store import ProjectStore, ProjectStoreFailure, SAFE_ID, owned_file, strict_json
from .rich_mutations import mutation_sha256
from .storage import StorageFailure, atomic_write, locked_root, private_directory


class AgentFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def identity(prefix: str) -> str:
    return prefix + "_" + secrets.token_hex(12)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value) -> str:
    data = value.model_dump(mode="json", by_alias=True) if hasattr(value, "model_dump") else value
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def journal_request(request: AgentRunRequest) -> AgentJournalRequest:
    # Owner capabilities are memory-only and do not change the logical retry key.
    return AgentJournalRequest.model_validate(request.model_dump(by_alias=True, exclude={"owner"}))


def run_in(state: AgentProjectState, run_id: str):
    for conversation in state.conversations:
        for run in conversation.runs:
            if run.id == run_id:
                journal = next(item for item in state.journals if item.run_id == run_id)
                return conversation, run, journal
    raise AgentFailure("AGENT_NOT_FOUND")


def conversation_in(state: AgentProjectState, conversation_id: str) -> AgentConversation:
    result = next((item for item in state.conversations if item.id == conversation_id), None)
    if result is None:
        raise AgentFailure("AGENT_NOT_FOUND")
    return result


def budget_parts(state: AgentProjectState, journal: AgentRunJournal):
    conversation, run, _ = run_in(state, journal.run_id)
    private = journal.model_dump(mode="json", by_alias=True, exclude={"events", "reserved"})
    public = {"run": run.model_dump(mode="json", by_alias=True),
        "events": [event.model_dump(mode="json", by_alias=True) for event in journal.events],
        **{key: [item.model_dump(mode="json", by_alias=True) for item in getattr(conversation, key)
                 if item.run_id == run.id] for key in ("messages", "sources", "findings")}}
    size = lambda value: len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return size(private), size(public)


def verify_journals(state: AgentProjectState):
    for journal in state.journals:
        if digest(journal.request) != journal.request_sha256:
            raise ValueError("changed request")
        for item in journal.batches:
            batch = item.batch
            if batch is not None and (mutation_sha256(batch.mutation) != batch.request_sha256 or
                    batch.id != item.result.batch_id or batch.tool_key != item.key or
                    batch.mutation.project_id != state.project_id):
                raise ValueError("changed prepared mutation")


class AgentStore:
    def __init__(self, root: Path, *, clock=timestamp):
        self.root = root
        self.assistant = root / "assistant"
        self.projects = self.assistant / "projects"
        self.canonical = ProjectStore(root)
        self.clock = clock

    @contextmanager
    def _guard(self, project_id: str, *, deleted=False):
        if SAFE_ID.fullmatch(project_id) is None:
            raise AgentFailure("AGENT_NOT_FOUND")
        try:
            # The canonical lifecycle guard always precedes the assistant lock.
            with locked_root(self.root, ".projects.lock"):
                registry = self.canonical._registry()
                entry = next((item for item in registry.entries if item.project_id == project_id), None)
                if entry is None:
                    raise AgentFailure("AGENT_NOT_FOUND")
                if entry.tombstoned != deleted:
                    raise AgentFailure("AGENT_PROJECT_DELETED" if entry.tombstoned else "AGENT_NOT_FOUND")
                if not deleted:
                    self.canonical._directory(project_id)
                with locked_root(self.assistant, ".assistant.lock"):
                    private_directory(self.projects)
                    directory = self.projects / project_id
                    if directory.is_symlink():
                        raise StorageFailure("UNSAFE_STORAGE")
                    yield directory
        except AgentFailure:
            raise
        except (StorageFailure, ProjectStoreFailure, OSError, ValueError):
            raise AgentFailure("AGENT_STORE_UNAVAILABLE") from None

    def _read(self, project_id: str, directory: Path) -> AgentProjectState:
        path = directory / "state.json"
        if not directory.exists():
            return AgentProjectState(schemaVersion=1, projectId=project_id, revision=1,
                ownerEpoch=0, conversations=[], journals=[])
        try:
            private_directory(directory)
            # An existing namespace without its state is damaged, never an empty replacement.
            owned_file(path, limits.PROJECT_BYTES)
            with path.open("rb") as stream:
                raw = stream.read(limits.PROJECT_BYTES + 1)
            if len(raw) > limits.PROJECT_BYTES:
                raise ValueError("oversized sidecar")
            state = AgentProjectState.model_validate(strict_json(raw))
            if state.project_id != project_id:
                raise ValueError("foreign sidecar")
            verify_journals(state)
            self._capacity(state, terminal=True)
            return state
        except (StorageFailure, OSError, ValueError, ValidationError, RecursionError, AgentFailure):
            raise AgentFailure("AGENT_STORE_CORRUPT") from None

    def _capacity(self, state: AgentProjectState, *, terminal=False):
        remaining = 0
        for conversation in state.conversations:
            reservations = {journal.run_id for journal in state.journals if journal.reserved}
            slots = sum(max(0, 2 - sum(msg.run_id == run.id for msg in conversation.messages))
                for run in conversation.runs if run.id in reservations)
            if len(conversation.messages) + slots > limits.CONVERSATION_MESSAGES:
                raise AgentFailure("AGENT_CONVERSATION_FULL")
        for journal in state.journals:
            private, public = budget_parts(state, journal)
            _, run, _ = run_in(state, journal.run_id)
            if private > limits.JOURNAL_BYTES:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            if public > limits.RUN_BYTES - (0 if terminal or run.state in TERMINAL_RUNS else limits.TERMINAL_BYTES):
                raise AgentFailure("AGENT_OUTPUT_LIMIT")
            if journal.reserved:
                remaining += limits.JOURNAL_BYTES - private + limits.RUN_BYTES - public
        if len(wire_bytes(state)) + remaining > limits.PROJECT_BYTES:
            raise AgentFailure("AGENT_PROJECT_FULL")

    def _write(self, directory: Path, state: AgentProjectState, *, terminal=False):
        try:
            self._capacity(state, terminal=terminal)
            validated = AgentProjectState.model_validate(state.model_dump(by_alias=True))
            verify_journals(validated)
            self._capacity(validated, terminal=terminal)
            atomic_write(directory / "state.json", wire_bytes(validated))
        except (StorageFailure, OSError):
            raise AgentFailure("AGENT_STORE_SAVE_FAILED") from None

    def load(self, project_id: str) -> AgentProjectState:
        with self._guard(project_id) as directory:
            return self._read(project_id, directory)

    def update(self, project_id: str, change, *, terminal=False):
        with self._guard(project_id) as directory:
            state = self._read(project_id, directory)
            result = change(state)
            state.revision += 1
            self._write(directory, state, terminal=terminal)
            return result

    def create_conversation(self, project_id: str) -> AgentConversation:
        def create(state):
            now = self.clock()
            conversation = AgentConversation(schemaVersion=1, id=identity("conversation"),
                projectId=project_id, createdAt=now, updatedAt=now,
                messages=[], runs=[], sources=[], findings=[])
            state.conversations.append(conversation)
            return conversation
        return self.update(project_id, create)

    def submit(self, project_id: str, request: AgentRunRequest, *, model: str,
               connection_epoch: str, validate_new=lambda: None):
        logical = journal_request(request)
        request_hash = digest(logical)
        with self._guard(project_id) as directory:
            state = self._read(project_id, directory)
            existing = next((item for item in state.journals if
                item.request.client_request_id == request.client_request_id), None)
            if existing is not None:
                if existing.request_sha256 != request_hash:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return run_in(state, existing.run_id)[1], False
            validate_new()
            conversation = conversation_in(state, request.conversation_id)
            if any(run.state not in TERMINAL_RUNS for run in conversation.runs):
                raise AgentFailure("AGENT_BUSY")
            now = self.clock()
            deadline = (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(
                seconds=limits.ADMISSION_SECONDS + limits.STARTUP_SECONDS + limits.ACTIVE_SECONDS + limits.CLEANUP_SECONDS)).isoformat()
            run = AgentRun(id=identity("run"), projectId=project_id, conversationId=conversation.id,
                clientRequestId=request.client_request_id, ownerEpoch=request.owner.epoch, state="queued",
                allowEdits=request.allow_edits, allowWeb=request.allow_web, scope=request.scope,
                model=model, connectionEpoch=connection_epoch, settingsRevision=request.settings_revision,
                createdAt=now, deadline=deadline, finishedAt=None, usage=None, error=None,
                savedBatchId=None, outcomeUnknown=False)
            conversation.runs.append(run)
            conversation.messages.append(AgentMessage(id=identity("message"), role="user",
                text=request.message, runId=run.id, timestamp=now, sources=[], findings=[], truncated=False, error=None))
            conversation.updated_at = now
            state.journals.append(AgentRunJournal(runId=run.id, request=logical,
                requestSha256=request_hash, reserved=True, snapshots=[], batches=[], events=[]))
            state.revision += 1
            self._write(directory, state)
            return run, True

    def find_request(self, project_id: str, request: AgentRunRequest):
        state = self.load(project_id)
        existing = next((item for item in state.journals if
            item.request.client_request_id == request.client_request_id), None)
        if existing is None:
            return None
        if existing.request_sha256 != digest(journal_request(request)):
            raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
        return run_in(state, existing.run_id)[1]

    def prepare(self, project_id: str, run_id: str, request, compile_batch):
        request_hash = digest(request)
        def prepare_batch(state):
            _, run, journal = run_in(state, run_id)
            existing = next((item for item in journal.batches if item.key == request.key), None)
            if existing is not None:
                if existing.payload_sha256 != request_hash:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return existing.result
            if not run.allow_edits or run.state in TERMINAL_RUNS or run.state == "cancelling":
                raise AgentFailure("AGENT_TOOL_DENIED")
            if any(item.receipt is not None and item.receipt.durable for item in journal.batches):
                raise AgentFailure("AGENT_EDIT_LIMIT")
            if any(item.batch is not None and item.batch.state not in TERMINAL_EDITS for item in journal.batches):
                raise AgentFailure("AGENT_BUSY")
            result, batch = (compile_batch(state, run, journal) if request.operations else
                (AgentPrepareResult(disposition="no_change", batchId=None, affected=[], preview=""), None))
            if (batch is None) != (result.disposition == "no_change"):
                raise AgentFailure("AGENT_EDIT_INVALID")
            if batch is not None and (batch.run_id != run.id or batch.tool_key != request.key or
                    batch.id != result.batch_id or mutation_sha256(batch.mutation) != batch.request_sha256):
                raise AgentFailure("AGENT_EDIT_INVALID")
            for item in journal.batches:
                # Retain the rejected command's identity/hash/disposition, not its large body.
                item.batch = None
            journal.batches.append(AgentBatchJournal(key=request.key, payloadSha256=request_hash,
                result=result, batch=batch, receipt=None))
            return result
        return self.update(project_id, prepare_batch)

    def record_receipt(self, project_id: str, run_id: str, receipt: AgentEditReceipt):
        def record(state):
            _, run, journal = run_in(state, run_id)
            item = next((item for item in journal.batches if item.result.batch_id == receipt.batch_id), None)
            if item is not None and item.receipt is not None and item.receipt.disposition != "outcome_unknown":
                if item.receipt != receipt:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return item.receipt
            if item is None or item.batch is None or (receipt.run_id, receipt.tool_key,
                    receipt.client_mutation_id, receipt.request_sha256) != (run.id, item.key,
                    item.batch.mutation.client_mutation_id, item.batch.request_sha256):
                raise AgentFailure("AGENT_EDIT_INVALID")
            if receipt.durable and run.saved_batch_id not in {None, receipt.batch_id}:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            item.receipt = receipt
            item.batch.state = receipt.disposition
            if run.state == "waiting_for_editor":
                run.state = "running"
            if receipt.durable:
                run.saved_batch_id = receipt.batch_id
            run.outcome_unknown = any(part.batch is not None and part.batch.state == "outcome_unknown"
                for part in journal.batches)
            journal.reserved = run.state not in TERMINAL_RUNS or any(part.batch is not None and
                part.batch.state not in TERMINAL_EDITS for part in journal.batches)
            return receipt
        return self.update(project_id, record, terminal=True)

    def finish(self, project_id: str, run_id: str, disposition: str, *, text="", error=None,
               sources=(), findings=(), truncated=False, native_completed=False):
        if disposition not in TERMINAL_RUNS or disposition == "completed" and not native_completed:
            raise AgentFailure("AGENT_PROTOCOL")
        def finish_run(state):
            conversation, run, journal = run_in(state, run_id)
            if run.state in TERMINAL_RUNS:
                return run
            for item in journal.batches:
                batch = item.batch
                if batch is None or batch.state in TERMINAL_EDITS:
                    continue
                if batch.state in {"applying", "outcome_unknown"}:
                    if disposition == "completed":
                        raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
                    batch.state = "outcome_unknown"
                    run.outcome_unknown = True
                else:
                    batch.state = "cancelled"
                item.receipt = AgentEditReceipt(batchId=batch.id, runId=run.id, toolKey=batch.tool_key,
                    clientMutationId=batch.mutation.client_mutation_id, requestSha256=batch.request_sha256,
                    disposition=batch.state, projectRevision=None, documentRevision=None, factsRevision=None,
                    durable=False, error={"code": "AGENT_OUTCOME_UNKNOWN" if run.outcome_unknown else "AGENT_CANCELLED"})
            run.state = disposition
            run.error = AgentError(code=error) if error else None
            run.finished_at = self.clock()
            conversation.updated_at = run.finished_at
            try:
                message = AgentMessage(id=identity("message"), role="assistant", text=text,
                    runId=run.id, timestamp=run.finished_at, sources=list(sources), findings=list(findings),
                    truncated=truncated, error=run.error)
            except ValidationError:
                raise AgentFailure("AGENT_OUTPUT_LIMIT") from None
            conversation.messages.append(message)
            journal.reserved = any(item.batch is not None and item.batch.state not in TERMINAL_EDITS
                for item in journal.batches)
            return run
        return self.update(project_id, finish_run, terminal=True)

    def recover(self, project_id: str) -> list[str]:
        def interrupt(state):
            state.owner_epoch += 1
            unresolved = []
            for conversation in state.conversations:
                for run in conversation.runs:
                    _, _, journal = run_in(state, run.id)
                    for item in journal.batches:
                        batch = item.batch
                        if batch is None or batch.state in TERMINAL_EDITS:
                            continue
                        batch.state = "outcome_unknown" if batch.state in {"applying", "outcome_unknown"} else "cancelled"
                        if batch.state == "outcome_unknown":
                            run.outcome_unknown = True
                            unresolved.append(batch.id)
                        item.receipt = AgentEditReceipt(batchId=batch.id, runId=run.id, toolKey=batch.tool_key,
                            clientMutationId=batch.mutation.client_mutation_id, requestSha256=batch.request_sha256,
                            disposition=batch.state, projectRevision=None, documentRevision=None, factsRevision=None,
                            durable=False, error={"code": "AGENT_OUTCOME_UNKNOWN" if run.outcome_unknown else "AGENT_INTERRUPTED"})
                    if run.state not in TERMINAL_RUNS:
                        run.state, run.finished_at = "interrupted", self.clock()
                        run.error = AgentError(code="AGENT_INTERRUPTED")
                        conversation.updated_at = run.finished_at
                        conversation.messages.append(AgentMessage(id=identity("message"), role="assistant", text="",
                            runId=run.id, timestamp=run.finished_at, sources=[], findings=[], truncated=False, error=run.error))
                    journal.reserved = any(item.batch is not None and item.batch.state not in TERMINAL_EDITS
                        for item in journal.batches)
            return unresolved
        return self.update(project_id, interrupt, terminal=True)

    def cleanup_deleted(self, project_id: str):
        with self._guard(project_id, deleted=True) as directory:
            def cleanup_status(status):
                registry = self.canonical._registry()
                entry = next(item for item in registry.entries if item.project_id == project_id)
                entry.cleanup_status = status
                self.canonical._write_registry(registry)
            try:
                if directory.exists():
                    private_directory(directory)
                    files = list(directory.iterdir())
                    for path in files:
                        if path.name != "state.json" and not path.name.startswith(".foldcv-write-"):
                            raise StorageFailure("UNSAFE_STORAGE")
                        owned_file(path, limits.PROJECT_BYTES)
                    for path in files:
                        path.unlink()
                    directory.rmdir()
                canonical = self.canonical.projects / project_id
                if not canonical.exists() and not canonical.is_symlink():
                    cleanup_status("complete")
            except (StorageFailure, OSError):
                try:
                    cleanup_status("failed")
                except (StorageFailure, OSError):
                    pass
                raise AgentFailure("AGENT_CLEANUP_INCOMPLETE") from None

    def recover_all(self):
        errors, unresolved = {}, {}
        registry = self.canonical.registry()
        for entry in registry.entries:
            try:
                if entry.tombstoned:
                    self.cleanup_deleted(entry.project_id)
                elif (self.projects / entry.project_id).exists():
                    unresolved[entry.project_id] = self.recover(entry.project_id)
            except AgentFailure as error:
                errors[entry.project_id] = error.code
        return unresolved, errors

    @staticmethod
    def _cursor(scope: str, offset: int) -> str:
        return base64.urlsafe_b64encode(json.dumps([1, digest(scope), offset], separators=(",", ":")).encode()).decode().rstrip("=")

    @staticmethod
    def _offset(scope: str, cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            version, key, offset = strict_json(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
            if version != 1 or key != digest(scope) or type(offset) is not int or offset < 0:
                raise ValueError()
            return offset
        except (ValueError, TypeError):
            raise AgentFailure("AGENT_NOT_FOUND") from None

    def conversations_page(self, project_id: str, request: AgentPageRequest):
        state = self.load(project_id)
        scope = project_id + ":conversations"
        start = self._offset(scope, request.cursor)
        selected = state.conversations[start:start + request.limit]
        return AgentConversationPage(items=[AgentConversationSummary(id=item.id, createdAt=item.created_at,
            updatedAt=item.updated_at, title=next((msg.text[:120] for msg in item.messages if msg.role == "user"), ""),
            activeRunId=next((run.id for run in item.runs if run.state not in TERMINAL_RUNS), None)) for item in selected],
            nextCursor=self._cursor(scope, start + len(selected)) if start + len(selected) < len(state.conversations) else None)

    def page(self, project_id: str, conversation_id: str, kind: str, request: AgentPageRequest):
        if kind not in {"messages", "sources", "findings"}:
            raise AgentFailure("AGENT_NOT_FOUND")
        conversation = conversation_in(self.load(project_id), conversation_id)
        scope = project_id + ":" + conversation_id + ":" + kind + ":" + digest(request.ids)
        items = getattr(conversation, kind)
        if request.ids:
            items = [item for item in items if item.id in request.ids]
            if {item.id for item in items} != set(request.ids):
                raise AgentFailure("AGENT_NOT_FOUND")
        start = self._offset(scope, request.cursor)
        selected = []
        result = AgentMessagePage(items=[], nextCursor=None) if kind == "messages" else AgentResourcePage(sources=[], findings=[], nextCursor=None)
        for item in items[start:start + request.limit]:
            candidate = [*selected, item]
            cursor = self._cursor(scope, start + len(candidate)) if start + len(candidate) < len(items) else None
            data = {"items": candidate} if kind == "messages" else {"sources": candidate if kind == "sources" else [],
                "findings": candidate if kind == "findings" else []}
            try:
                result = type(result)(**data, nextCursor=cursor)
            except ValidationError:
                if not selected:
                    raise AgentFailure("AGENT_STORE_CORRUPT") from None
                break
            selected = candidate
        return result
