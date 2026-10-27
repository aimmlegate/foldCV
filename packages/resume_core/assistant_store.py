"""Assistant files of one project: conversations with their runs, run events and change proposals (D109, plan 2.8).

Layout under the data root: `assistant/<project>/conversations/<id>.json`, `runs/<id>.jsonl` and
`proposals/<id>.json`. The project file is never written here; Apply goes through the repository.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import threading

from typing import Literal

from pydantic import Field, ValidationError

from . import agent_limits as limits
from .models.agent import AgentEvent, AgentFinding, AgentMessage, AgentWebSource
from .models.assistant import AssistantChangeProposalV1, AssistantConversationV1, AssistantRunV1, Stamp
from .models.contracts import Id, Wire
from .project_store import SAFE_ID
from .storage import StorageFailure, atomic_write, private_directory

CONVERSATIONS = 50
RUNS_KEPT = 20
EVENTS_KEPT = 500
PROPOSALS_KEPT = 100
SOURCES_KEPT = 100
FINDINGS_KEPT = 200


class ConversationFile(Wire):
    schema_version: Literal[1]
    id: Id
    project_id: Id
    title: str = Field(max_length=120)
    created_at: Stamp
    updated_at: Stamp
    messages: list[AgentMessage]
    sources: list[AgentWebSource]
    findings: list[AgentFinding]
    runs: list[AssistantRunV1]


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


def _safe(identifier):
    if not isinstance(identifier, str) or not SAFE_ID.fullmatch(identifier):
        raise AgentFailure("AGENT_NOT_FOUND")
    return identifier


class AssistantStore:
    def __init__(self, root: Path):
        self.root = Path(root) / "assistant"
        self.lock = threading.RLock()

    def directory(self, project_id, *parts):
        return self.root.joinpath(_safe(project_id), *parts)

    def _read(self, path, model):
        try:
            if path.is_symlink():
                raise StorageFailure("UNSAFE_STORAGE")
            return model.model_validate_json(path.read_bytes())
        except FileNotFoundError:
            return None
        except (OSError, ValidationError, ValueError, StorageFailure):
            raise AgentFailure("AGENT_STORE_UNAVAILABLE") from None

    def _write(self, path, value):
        raw = value.model_dump_json(by_alias=True).encode()
        if len(raw) > limits.RUN_BYTES * 8:
            raise AgentFailure("AGENT_STORE_FULL")
        try:
            atomic_write(path, raw)
        except (OSError, StorageFailure):
            raise AgentFailure("AGENT_SAVE_FAILED") from None

    # Conversations

    def conversations(self, project_id):
        folder = self.directory(project_id, "conversations")
        with self.lock:
            items = []
            for path in sorted(folder.glob("*.json")) if folder.exists() else []:
                stored = self._read(path, ConversationFile)
                if stored is not None:
                    items.append(AssistantConversationV1(id=stored.id, title=stored.title, createdAt=stored.created_at,
                        updatedAt=stored.updated_at))
            return sorted(items, key=lambda item: item.updated_at, reverse=True)[:CONVERSATIONS]

    def create_conversation(self, project_id, title=""):
        now = timestamp()
        value = ConversationFile(schemaVersion=1, id=identity("conversation"), projectId=project_id, title=title[:120],
            createdAt=now, updatedAt=now, messages=[], sources=[], findings=[], runs=[])
        with self.lock:
            self._write(self.directory(project_id, "conversations", value.id + ".json"), value)
            self._trim_conversations(project_id)
        return value

    def _trim_conversations(self, project_id):
        folder = self.directory(project_id, "conversations")
        kept = {item.id for item in self.conversations(project_id)}
        for path in folder.glob("*.json"):
            if path.stem not in kept:
                path.unlink(missing_ok=True)

    def conversation(self, project_id, conversation_id):
        with self.lock:
            value = self._read(self.directory(project_id, "conversations", _safe(conversation_id) + ".json"), ConversationFile)
            if value is None or value.project_id != project_id:
                raise AgentFailure("AGENT_NOT_FOUND")
            return value

    def update_conversation(self, project_id, conversation_id, change):
        """`change` edits a copy; the file is replaced atomically with the bounded result."""
        with self.lock:
            value = self.conversation(project_id, conversation_id).model_copy(deep=True)
            result = change(value)
            value.messages = value.messages[-limits.CONVERSATION_MESSAGES:]
            value.sources = value.sources[-SOURCES_KEPT:]
            value.findings = value.findings[-FINDINGS_KEPT:]
            value.runs = value.runs[-RUNS_KEPT:]
            value.updated_at = timestamp()
            self._write(self.directory(project_id, "conversations", value.id + ".json"), value)
            return result

    def find_run(self, project_id, run_id):
        folder = self.directory(project_id, "conversations")
        with self.lock:
            for path in folder.glob("*.json") if folder.exists() else []:
                stored = self._read(path, ConversationFile)
                if stored is None:
                    continue
                for run in stored.runs:
                    if run.id == run_id:
                        return stored, run
        raise AgentFailure("AGENT_NOT_FOUND")

    # Run events: one JSON line per event; the reader stops at the first malformed line.

    def append_event(self, project_id, run_id, event):
        path = self.directory(project_id, "runs", _safe(run_id) + ".jsonl")
        line = event.model_dump_json(by_alias=True).encode() + b"\n"
        with self.lock:
            try:
                private_directory(path.parent)
                with open(path, "ab") as handle:
                    handle.write(line)
            except OSError:
                raise AgentFailure("AGENT_SAVE_FAILED") from None

    def events(self, project_id, run_id, after=0):
        path = self.directory(project_id, "runs", _safe(run_id) + ".jsonl")
        result = []
        with self.lock:
            try:
                lines = path.read_bytes().splitlines() if not path.is_symlink() else []
            except FileNotFoundError:
                return result
            for line in lines:
                try:
                    event = AgentEvent.model_validate_json(line)
                except (ValidationError, ValueError):
                    break
                if event.root.sequence > after:
                    result.append(event)
        return result[:EVENTS_KEPT]

    # Proposals

    def save_proposal(self, proposal):
        with self.lock:
            self._write(self.directory(proposal.project_id, "proposals", _safe(proposal.id) + ".json"), proposal)
            self._trim_proposals(proposal.project_id)

    def _trim_proposals(self, project_id):
        folder = self.directory(project_id, "proposals")
        stored = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for path in stored[PROPOSALS_KEPT:]:
            path.unlink(missing_ok=True)

    def proposal(self, project_id, proposal_id):
        with self.lock:
            value = self._read(self.directory(project_id, "proposals", _safe(proposal_id) + ".json"), AssistantChangeProposalV1)
        if value is None or value.project_id != project_id:
            raise AgentFailure("ASSISTANT_PROPOSAL_NOT_FOUND")
        return value

    def proposals(self, project_id, conversation_id=None):
        folder = self.directory(project_id, "proposals")
        with self.lock:
            items = [self._read(path, AssistantChangeProposalV1) for path in folder.glob("*.json")] if folder.exists() else []
        items = [item for item in items if item is not None and (conversation_id is None or item.conversation_id == conversation_id)]
        return sorted(items, key=lambda item: item.created_at)

    def delete_project(self, project_id):
        import shutil
        with self.lock:
            shutil.rmtree(self.directory(project_id), ignore_errors=True)
