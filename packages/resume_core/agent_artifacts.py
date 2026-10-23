"""Single-copy agent artifacts with a read-only projection of the Job lifecycle."""

from __future__ import annotations

import hashlib

from .agent_store import AgentFailure, AgentStore, digest, run_in, verify_journals
from .background_limits import LIMITS
from .background_store import BackgroundFailure, TERMINAL_EXECUTION, expiration, job_in
from .models.agent import AgentConversation, AgentError, AgentMessage, AgentProjectState, AgentRun, AgentRunJournal
from .models.background import JobArtifactV1, JobLegacyRunV2
from .models.assistant_artifacts import AssistantJobArtifactV1, decode_assistant_artifact
from .project_store import encoded, owned_file, strict_json
from .rich_mutations import mutation_sha256
from .storage import StorageFailure, atomic_write, private_directory, locked_root


def artifact_id(identity):
    return "input_" + digest(identity)[:24]


def legacy_request_id(identity):
    return "request_" + digest(identity)[:24]


class JobArtifacts(AgentStore):
    def __init__(self, jobs):
        super().__init__(jobs.root, clock=jobs.clock)
        self.jobs = jobs
        self.prepare_capture = None

    def _path(self, directory, identifier):
        from .project_store import SAFE_ID
        if SAFE_ID.fullmatch(identifier) is None:
            raise AgentFailure("AGENT_NOT_FOUND")
        folder = directory / "agent-artifacts"
        if folder.is_symlink():
            raise AgentFailure("AGENT_STORE_CORRUPT")
        return folder / (identifier + ".json")

    def _artifact(self, path):
        try:
            owned_file(path, LIMITS.sidecar_project_bytes)
            value = decode_assistant_artifact(strict_json(path.read_bytes()))
            if (value.id != path.stem or value.id != artifact_id(value.identity)
                    or value.request_sha256 != digest(value.request)
                    or value.identity.request_id != value.request.client_request_id):
                raise ValueError("changed input")
            for item in [*value.batches, *getattr(value, "applications", [])]:
                batch = item.batch
                if batch is not None and (batch.run_id != value.job_id or batch.id != item.result.batch_id
                        or batch.tool_key != item.key or batch.mutation.project_id != value.identity.project_id
                        or mutation_sha256(batch.mutation) != batch.request_sha256):
                    raise ValueError("changed prepared payload")
            return value
        except (OSError, StorageFailure, ValueError, RecursionError):
            raise AgentFailure("AGENT_STORE_CORRUPT") from None

    def _save(self, directory, state, artifact):
        value = decode_assistant_artifact(artifact.model_dump(by_alias=True))
        if isinstance(value, AssistantJobArtifactV1):
            from .models.agent import TERMINAL_EDITS
            value.application_control_padding = ""
            active = any(item.batch.state not in TERMINAL_EDITS for item in value.applications)
            if active:
                size = lambda: len(encoded(value.model_dump(mode="json", by_alias=True)))
                if value.application_control_capacity == 0:
                    value.application_control_capacity = size() + 32768
                    value.application_control_capacity = size() + 32768
                remaining = value.application_control_capacity - size()
                if not 0 <= remaining <= value.application_control_capacity:
                    raise AgentFailure("AGENT_PROJECT_FULL")
                value.application_control_padding = "_" * remaining
            else:
                value.application_control_capacity = 0
        path = self._path(directory, value.id)
        raw = encoded(value.model_dump(mode="json", by_alias=True))
        accepted = next((item for item in state.proposals if item.job_id == value.job_id), None)
        if accepted is not None and accepted.payload.kind == "agent_journal":
            import hashlib
            batch = next((item.batch for item in value.batches if item.result.batch_id == accepted.payload.batch_id), None)
            if batch is None or hashlib.sha256(encoded(batch.model_dump(mode="json", by_alias=True))).hexdigest() != accepted.payload_sha256:
                raise AgentFailure("AGENT_TOOL_DENIED")
        self.jobs._capacity(state, self.jobs._all(), replacing=(path, len(raw)))
        private_directory(path.parent)
        try:
            atomic_write(path, raw)
            self.jobs._sync_namespace(path)
        except (OSError, StorageFailure):
            # A lost reply is confirmed from these exact artifact bytes, never regenerated.
            self.jobs._confirm_file(path, raw)

    def prepare_input(self, identity, request, connection_epoch, rules_sha256):
        conversation = next((item for item in super().load(identity.project_id).conversations
            if item.id == request.conversation_id), None)
        if conversation is None:
            raise AgentFailure("AGENT_NOT_FOUND")
        with self.jobs.guard(identity.project_id) as directory:
            state = self.jobs._read(identity.project_id, directory)
            path = self._path(directory, artifact_id(identity))
            if path.exists():
                prior = self._artifact(path)
                if prior.identity != identity or prior.request != request:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                return prior
            reserved_messages = 0
            if path.parent.exists():
                for stored in path.parent.glob("*.json"):
                    old = self._artifact(stored)
                    if old.request.conversation_id == request.conversation_id:
                        reserved_messages += 2
            from .agent_limits import CONVERSATION_MESSAGES
            if len(conversation.messages) + reserved_messages + 2 > CONVERSATION_MESSAGES:
                raise AgentFailure("AGENT_CONVERSATION_FULL")
            value = JobArtifactV1(schemaVersion=1, id=artifact_id(identity), identity=identity, request=request,
                requestSha256=digest(request), connectionEpoch=connection_epoch, jobId=None, createdAt=self.clock(),
                rulesSha256=rules_sha256,
                snapshots=[], batches=[], sources=[], findings=[], reply=None, usage=None)
            self._save(directory, state, value)
            return value

    def bind(self, job):
        project = job.submission.identity.project_id
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            current = job_in(state, job.id)
            record = self._artifact(self._path(directory, current.submission.input.id))
            if (record.identity != current.submission.identity or record.request_sha256 != current.submission.input.sha256
                    or record.job_id not in {None, current.id}):
                raise AgentFailure("AGENT_STORE_CORRUPT")
            record.job_id = current.id
            self._save(directory, state, record)
            return record

    def record(self, project, job_id):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            job = job_in(state, job_id)
            record = self._artifact(self._path(directory, job.submission.input.id))
            if (record.job_id != job.id or record.identity != job.submission.identity
                    or record.request_sha256 != job.submission.input.sha256):
                raise AgentFailure("AGENT_STORE_CORRUPT")
            return job, record

    def bound(self, project, job_id):
        return JobArtifactView(self, project, job_id)

    def observe(self, project, job_id, guards):
        from .models.background import ScopeGuardV1
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            job = job_in(state, job_id)
            if job.proposal_id is not None:
                return
            record = self._artifact(self._path(directory, job.submission.input.id))
            if record.job_id != job.id:
                raise AgentFailure("AGENT_STORE_CORRUPT")
            original = record.observed_guards
            reads = {(stamp.kind, stamp.key): stamp for stamp in original.reads} if original else {}
            for stamp in guards.reads:
                # A later read cannot erase a dependency already observed by this turn.
                reads.setdefault((stamp.kind, stamp.key), stamp)
            if len(reads) > 4096:
                raise BackgroundFailure("JOB_STORAGE_FULL")
            record.observed_guards = ScopeGuardV1(schemaVersion=1, reads=list(reads.values()),
                writes=original.writes if original else [])
            self._save(directory, state, record)

    def payload_for(self, project, reference):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            return self.payload_unlocked(state, directory, reference)

    def payload_unlocked(self, state, directory, reference):
        job = job_in(state, reference.run_id)
        record = self._artifact(self._path(directory, job.submission.input.id))
        if reference.kind != "agent_journal" or record.request.conversation_id != reference.conversation_id:
            raise AgentFailure("AGENT_EDIT_INVALID")
        item = next((item for item in record.batches if item.result.batch_id == reference.batch_id), None)
        if item is None or item.batch is None or item.batch.run_id != job.id:
            raise AgentFailure("AGENT_EDIT_INVALID")
        return encoded(item.batch.model_dump(mode="json", by_alias=True))

    def finish(self, project, job_id, result):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            job = job_in(state, job_id)
            record = self._artifact(self._path(directory, job.submission.input.id))
            if record.job_id != job.id:
                raise AgentFailure("AGENT_STORE_CORRUPT")
            record.usage = result.usage
            if result.text:
                record.reply = AgentMessage(id="reply_" + record.id, role="assistant", text=result.text,
                    runId=job.id, timestamp=self.clock(), sources=[], findings=[], truncated=result.truncated, error=None)
            self._save(directory, state, record)

    @staticmethod
    def projection(job, record, history=None):
        request = record.request.model_copy(update={"client_request_id": legacy_request_id(record.identity)})
        terminal = job.execution in TERMINAL_EXECUTION
        error_map = {"RATE_LIMITED": "AGENT_QUOTA", "AUTH_REQUIRED": "AGENT_AUTH_REQUIRED",
            "MODEL_DENIED": "AGENT_MODEL_INCOMPATIBLE", "ACCOUNT_CHANGED": "AGENT_CONNECTION_CHANGED",
            "PROJECT_DELETED": "AGENT_PROJECT_DELETED"}
        code = None if job.error is None else error_map.get(job.error.code, "AGENT_" + job.error.code)
        if code is not None:
            try:
                error = AgentError(code=code)
            except ValueError:
                error = AgentError(code="AGENT_INTERRUPTED")
        else:
            error = None
        saved_batch = next((item.batch.id for item in record.batches if item.batch is not None
            and job.receipt is not None and hashlib.sha256(encoded(item.batch.model_dump(mode="json", by_alias=True))).hexdigest()
                == job.receipt.proposal_sha256), None)
        run = AgentRun(id=job.id, projectId=record.identity.project_id, conversationId=request.conversation_id,
            clientRequestId=request.client_request_id, ownerEpoch=job.execution_generation,
            state="queued" if job.execution == "starting" else job.execution,
            allowEdits=job.submission.allow_edits, allowWeb=job.submission.allow_web, scope=job.submission.scope,
            selectionContext=request.selection_context, accessRevision=job.submission.access_revision,
            model=job.submission.models[-1].model, connectionEpoch=record.connection_epoch,
            settingsRevision=request.settings_revision, createdAt=job.created_at,
            deadline=job.attempts[-1].active_deadline if job.attempts else expiration(job.created_at, 195),
            finishedAt=job.updated_at if terminal else None, usage=record.usage, error=error,
            savedBatchId=saved_batch,
            outcomeUnknown=job.publication == "outcome_unknown")
        messages = [AgentMessage(id="user_" + record.id, role="user", text=record.request.message,
            runId=job.id, timestamp=record.created_at, sources=[], findings=[], truncated=False, error=None)]
        if record.reply is not None:
            messages.append(record.reply)
        previous = next((item for item in history.conversations if item.id == request.conversation_id), None) if history else None
        conversation = AgentConversation(schemaVersion=1, id=request.conversation_id, projectId=record.identity.project_id,
            createdAt=record.created_at, updatedAt=job.updated_at, messages=messages, runs=[run],
            sources=record.sources, findings=record.findings) if previous is None else AgentConversation(
                schemaVersion=1, id=request.conversation_id, projectId=record.identity.project_id,
                createdAt=previous.created_at, updatedAt=job.updated_at,
                messages=previous.messages + messages, runs=previous.runs + [run],
                sources=previous.sources + record.sources, findings=previous.findings + record.findings)
        journal = AgentRunJournal(runId=job.id, request=request, requestSha256=digest(request), reserved=False,
            snapshots=record.snapshots, batches=[*record.batches, *getattr(record, "applications", [])], events=[])
        state = AgentProjectState(schemaVersion=1, projectId=record.identity.project_id,
            revision=job.event_cursor, ownerEpoch=job.execution_generation, conversations=[conversation],
            journals=([item for item in history.journals if item.request.conversation_id == request.conversation_id] if history else []) + [journal])
        verify_journals(state)
        return state


class JobArtifactView(AgentStore):
    def __init__(self, artifacts, project, job_id):
        super().__init__(artifacts.root, clock=artifacts.clock)
        self.artifacts, self.project, self.job_id = artifacts, project, job_id

    def load(self, project):
        if project != self.project:
            raise AgentFailure("AGENT_NOT_FOUND")
        job, record = self.artifacts.record(project, self.job_id)
        # Older journals stay unchanged; only terminal runs enter this compatibility view.
        old = super().load(project)
        history = next((item for item in old.conversations if item.id == record.request.conversation_id), None)
        if history is not None:
            ids = {run.id for run in history.runs if run.state in TERMINAL_EXECUTION}
            for name in ("runs", "messages", "sources", "findings"):
                items = [item for item in getattr(history, name) if (item.id if name == "runs" else item.run_id) in ids]
                setattr(history, name, items)
            old.conversations = [history]
            old.journals = [item for item in old.journals if item.run_id in ids]
        else:
            old.conversations, old.journals = [], []
        state = AgentProjectState.model_validate(old.model_dump(by_alias=True))
        for previous in self.artifacts.jobs.load(project).jobs:
            if previous.id != job.id and previous.execution not in TERMINAL_EXECUTION or previous.submission.kind != "agent":
                continue
            previous, artifact = (job, record) if previous.id == job.id else self.artifacts.record(project, previous.id)
            if artifact.request.conversation_id == record.request.conversation_id:
                state = self.artifacts.projection(previous, artifact, state)
        state.revision, state.owner_epoch = job.event_cursor, job.execution_generation
        return state

    def legacy(self):
        job, _record = self.artifacts.record(self.project, self.job_id)
        run = run_in(self.load(self.project), self.job_id)[1]
        return JobLegacyRunV2(schemaVersion=2, jobId=job.id, publication=job.publication, run=run)

    def update_under_canonical_lock(self, project, change):
        if project != self.project:
            raise AgentFailure("AGENT_NOT_FOUND")
        # The coordinator owns canonical/background locks; only the assistant lock remains.
        with locked_root(self.assistant, ".assistant.lock"):
            directory = self.artifacts.jobs.projects / project
            sidecar = self.artifacts.jobs._read(project, directory)
            job = job_in(sidecar, self.job_id)
            record = self.artifacts._artifact(self.artifacts._path(directory, job.submission.input.id))
            view = self.artifacts.projection(job, record)
            original = run_in(view, job.id)[1].model_copy(deep=True)
            result = change(view)
            _, run, journal = run_in(view, job.id)
            if run != original:
                raise AgentFailure("AGENT_TOOL_DENIED")
            verify_journals(AgentProjectState.model_validate(view.model_dump(by_alias=True)))
            old_keys = {item.key for item in record.batches}
            if not isinstance(record, AssistantJobArtifactV1) or any(item not in journal.batches for item in record.batches):
                raise AgentFailure("AGENT_TOOL_DENIED")
            record.applications = [item for item in journal.batches if item.key not in old_keys]
            self.artifacts._save(directory, sidecar, record)
            return result

    def update(self, project, change, *, terminal=False):
        return self._update(project, change, terminal=terminal)

    def update_reviewed(self, project, change, *, terminal=False):
        return self._update(project, change, terminal=terminal, reviewed=True)

    def _update(self, project, change, *, terminal=False, reviewed=False):
        if project != self.project:
            raise AgentFailure("AGENT_NOT_FOUND")
        view = self.load(project)
        with self.artifacts.jobs.guard(project) as directory, locked_root(self.assistant, ".assistant.lock"):
            sidecar = self.artifacts.jobs._read(project, directory)
            job = job_in(sidecar, self.job_id)
            path = self.artifacts._path(directory, job.submission.input.id)
            record = self.artifacts._artifact(path)
            if record.job_id != job.id:
                raise AgentFailure("AGENT_STORE_CORRUPT")
            current_run = run_in(view, job.id)[1]
            if current_run != run_in(self.artifacts.projection(job, record,
                    self._without_current(view)), job.id)[1]:
                raise AgentFailure("AGENT_INTERRUPTED")
            before = view.model_dump(by_alias=True)
            result = change(view)
            conversation, run, journal = run_in(view, job.id)
            before_run = next(item for item in before["conversations"][0]["runs"] if item["id"] == job.id)
            before_journal = next(item for item in before["journals"] if item["runId"] == job.id)
            if (run.model_dump(by_alias=True) != before_run
                    or journal.request.model_dump(by_alias=True) != before_journal["request"]
                    or self._without_current(view).model_dump(by_alias=True) != self._without_current(
                        AgentProjectState.model_validate(before)).model_dump(by_alias=True) or journal.events):
                raise AgentFailure("AGENT_TOOL_DENIED")
            old_keys = {item.key for item in record.batches}
            applications = getattr(record, "applications", [])
            if reviewed:
                if any(item not in journal.batches for item in record.batches):
                    raise AgentFailure("AGENT_TOOL_DENIED")
                if not isinstance(record, AssistantJobArtifactV1):
                    record = AssistantJobArtifactV1.model_validate({**record.model_dump(by_alias=True),
                        "assistantProtocolVersion": 1, "applications": []})
                record.applications = [item for item in journal.batches if item.key not in old_keys]
            else:
                keys = {item.key for item in applications}
                if [item for item in journal.batches if item.key in keys] != applications:
                    raise AgentFailure("AGENT_TOOL_DENIED")
                record.batches = [item for item in journal.batches if item.key not in keys]
            record.snapshots = journal.snapshots
            record.sources = [item for item in conversation.sources if item.run_id == job.id]
            record.findings = [item for item in conversation.findings if item.run_id == job.id]
            users = [message for message in conversation.messages if message.role == "user" and message.run_id == job.id]
            replies = [message for message in conversation.messages if message.role == "assistant" and message.run_id == job.id]
            if [item.model_dump(by_alias=True) for item in users] != [item for item in before["conversations"][0]["messages"]
                    if item["role"] == "user" and item["runId"] == job.id] or len(replies) > 1:
                raise AgentFailure("AGENT_TOOL_DENIED")
            record.reply = replies[0] if replies else None
            verify_journals(AgentProjectState.model_validate(view.model_dump(by_alias=True)))
            old_keys = {item["key"] for item in before_journal["batches"]}
            prepared = [item.batch for item in journal.batches if item.key not in old_keys and item.batch is not None]
            if prepared and not reviewed and self.artifacts.prepare_capture is not None:
                self.artifacts.prepare_capture(directory, sidecar, record, prepared[0])
            self.artifacts._save(directory, sidecar, record)
            return result

    def _without_current(self, view):
        value = view.model_copy(deep=True)
        for conversation in value.conversations:
            conversation.runs = [run for run in conversation.runs if run.id != self.job_id]
            for name in ("messages", "sources", "findings"):
                setattr(conversation, name, [item for item in getattr(conversation, name) if item.run_id != self.job_id])
        value.journals = [journal for journal in value.journals if journal.run_id != self.job_id]
        return value
