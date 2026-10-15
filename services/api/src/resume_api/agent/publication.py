"""Prepared publication is candidate-first; receipts describe durable store proof."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import time

from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.models.agent import (
    AgentClaimResult, AgentCommitResult, AgentEditReceipt, AgentHistoryAction, AgentPublicationStamp, TERMINAL_RUNS,
)
from packages.resume_core.rich_project_store import rich_snapshot_bytes
from packages.resume_core.rich_mutations import apply_rich_mutation, mutation_sha256
from packages.resume_core.storage import locked_root

from .context import current_dependencies


@dataclass
class Ticket:
    project_id: str
    run_id: str
    batch_id: str
    owner_epoch: int
    request_sha256: str
    token_sha256: str
    expires: float


def item_in(state, run_id, batch_id):
    conversation, run, journal = run_in(state, run_id)
    item = next((item for item in journal.batches if item.result.batch_id == batch_id), None)
    if item is None or item.batch is None:
        raise AgentFailure("AGENT_NOT_FOUND")
    return conversation, run, journal, item


class AgentPublication:
    def __init__(self, service, *, clock=time.monotonic):
        self.service, self.clock = service, clock
        self.tickets = {}

    def _load(self, project_id, run_id, batch_id):
        state = self.service.store.load(project_id)
        return state, item_in(state, run_id, batch_id)

    def _gate(self, project_id, run_id, batch_id, *, owner=None, state=None):
        service = self.service
        if state is None:
            state = service.store.load(project_id)
        _, run, _, item = item_in(state, run_id, batch_id)
        control = service.controls.get(run_id)
        if (control is None or control.project_id != project_id or control.revoked.is_set() or control.cancel.is_set()
                or run.state in TERMINAL_RUNS or run.state == "cancelling"):
            raise AgentFailure("AGENT_CANCELLED")
        lease = service.leases.require(project_id, owner, epoch=run.owner_epoch)
        if state.owner_epoch != run.owner_epoch or item.batch.owner_epoch != run.owner_epoch:
            raise AgentFailure("AGENT_OWNER_MISMATCH")
        connection = service.connection()
        if not connection.ready or run.connection_epoch != connection.epoch:
            raise AgentFailure("AGENT_CONNECTION_CHANGED")
        if not run.allow_edits:
            raise AgentFailure("AGENT_TOOL_DENIED")
        if datetime.now(timezone.utc) >= datetime.fromisoformat(run.deadline):
            raise AgentFailure("AGENT_DEADLINE")
        if run.saved_batch_id is not None:
            raise AgentFailure("AGENT_EDIT_LIMIT")
        if mutation_sha256(item.batch.mutation) != item.batch.request_sha256:
            raise AgentFailure("AGENT_EDIT_INVALID")
        return run, item, lease

    def _receipt(self, batch, disposition, *, error=None, workspace=None, publication=None):
        return AgentEditReceipt(batchId=batch.id, runId=batch.run_id, toolKey=batch.tool_key,
            clientMutationId=batch.mutation.client_mutation_id, requestSha256=batch.request_sha256,
            disposition=disposition, projectRevision=publication.project_revision if publication else workspace.project_revision if workspace else None,
            documentRevision=publication.document_revision if publication else workspace.document_revision if workspace else None,
            factsRevision=publication.facts_revision if publication else workspace.project.facts.revision if workspace else None,
            durable=disposition == "saved", error={"code": error} if error else None)

    def _record(self, project_id, receipt):
        service = self.service
        try:
            result = service.store.record_receipt(project_id, receipt.run_id, receipt)
        except AgentFailure:
            self._fence(project_id, receipt.batch_id)
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None
        self.tickets.pop(receipt.batch_id, None)
        control = service.controls.get(receipt.run_id)
        if control is not None:
            try:
                service.event(control, "edit.result", {"batchId": receipt.batch_id,
                    "disposition": receipt.disposition, "error": receipt.error.model_dump(by_alias=True) if receipt.error else None}, terminal=True)
            except AgentFailure:
                service.startup_errors[project_id] = "AGENT_STORE_UNAVAILABLE"
        return result

    def _fence(self, project_id, batch_id):
        service = self.service
        service.unresolved.setdefault(project_id, [])
        if batch_id not in service.unresolved[project_id]:
            service.unresolved[project_id].append(batch_id)
        service.projects.agent_recovery_fences.add(project_id)
        service.projects.save_errors[project_id] = "AGENT_OUTCOME_UNKNOWN"
        for control in service.controls.values():
            if control.project_id == project_id:
                service.revoke(control, "AGENT_OUTCOME_UNKNOWN")

    def _adopt(self, project_id, workspace, checksum):
        projects = self.service.projects
        projects.workspaces[project_id] = workspace
        projects.storage.expected[project_id] = checksum
        projects.saved_hashes[project_id] = digest(workspace.model_dump(mode="json", by_alias=True))
        projects.saved_revisions[project_id] = (workspace.project_revision, workspace.document_revision)
        projects.save_errors.pop(project_id, None)

    async def offer(self, session, batch_id):
        service, control = self.service, session.control
        project_id, run_id = control.project_id, control.run_id
        with service.projects.state_lock:
            session.guard()
            _, (_, _, _, item) = self._load(project_id, run_id, batch_id)
            if item.receipt is not None:
                return item.receipt
            self._gate(project_id, run_id, batch_id)
            if item.batch.state not in {"prepared", "offered"}:
                raise AgentFailure("AGENT_TICKET_INVALID")
            def offered(state):
                _, run, _, item = item_in(state, run_id, batch_id)
                item.batch.state, run.state = "offered", "waiting_for_editor"
            service.store.update(project_id, offered)
            service.event(control, "edit.offered", {"batchId": batch_id, "disposition": "offered", "error": None})
        deadline = self.clock() + 15
        while True:
            with service.projects.state_lock:
                _, (_, run, _, item) = self._load(project_id, run_id, batch_id)
                if item.receipt is not None:
                    return item.receipt
                if control.cancel.is_set() or control.revoked.is_set() or self.clock() >= deadline:
                    code = "AGENT_CANCELLED" if control.cancel.is_set() or control.revoked.is_set() else "AGENT_RECEIPT_TIMEOUT"
                    return self._record(project_id, self._receipt(item.batch, "cancelled" if code == "AGENT_CANCELLED" else "rejected", error=code))
            await asyncio.sleep(0.05)

    def claim(self, project_id, run_id, batch_id, owner):
        with self.service.projects.state_lock:
            run, item, lease = self._gate(project_id, run_id, batch_id, owner=owner)
            if item.receipt is not None or item.batch.state != "offered":
                raise AgentFailure("AGENT_TICKET_INVALID")
            workspace = self.service.projects.read(project_id)
            if not current_dependencies(workspace, item.batch.dependencies):
                self._record(project_id, self._receipt(item.batch, "stale", error="AGENT_STALE_READ"))
                raise AgentFailure("AGENT_STALE_READ")
            token = secrets.token_urlsafe(32)
            remaining = min(15, max(0, lease.expires - self.service.leases.clock()))
            self.tickets[batch_id] = Ticket(project_id, run_id, batch_id, run.owner_epoch,
                item.batch.request_sha256, hashlib.sha256(token.encode()).hexdigest(), self.clock() + remaining)
            return AgentClaimResult(ticket=token,
                expiresAt=(datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat(), batch=item.batch)

    def _ticket(self, project_id, run_id, batch_id, request):
        ticket = self.tickets.get(batch_id)
        if (ticket is None or (ticket.project_id, ticket.run_id, ticket.batch_id) != (project_id, run_id, batch_id)
                or self.clock() >= ticket.expires or ticket.owner_epoch != request.owner.epoch
                or ticket.request_sha256 != request.request_sha256
                or not hmac.compare_digest(ticket.token_sha256, hashlib.sha256(request.ticket.encode()).hexdigest())):
            raise AgentFailure("AGENT_TICKET_INVALID")

    def commit(self, project_id, run_id, batch_id, request):
        service, projects = self.service, self.service.projects
        with projects.state_lock:
            _, (_, _, _, known) = self._load(project_id, run_id, batch_id)
            service.leases.require(project_id, request.owner)
            if known.receipt is not None:
                if known.batch.request_sha256 != request.request_sha256:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return AgentCommitResult(receipt=known.receipt, project=projects.response(project_id))
            self._ticket(project_id, run_id, batch_id, request)
            run, item, _ = self._gate(project_id, run_id, batch_id, owner=request.owner)
            batch = item.batch
            current = projects.read(project_id)
            if projects.durability(project_id) != "durable":
                raise AgentFailure("AGENT_SAVE_FAILED")
            if not current_dependencies(current, batch.dependencies):
                receipt = self._record(project_id, self._receipt(batch, "stale", error="AGENT_STALE_READ"))
                return AgentCommitResult(receipt=receipt, project=projects.response(project_id))
            candidate, duplicate = apply_rich_mutation(current, batch.mutation)
            if duplicate:
                raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
            candidate.updated_at = projects.clock().isoformat()
            publication = AgentPublicationStamp(workspaceSha256=hashlib.sha256(rich_snapshot_bytes(candidate)).hexdigest(),
                projectRevision=candidate.project_revision, documentRevision=candidate.document_revision,
                factsRevision=candidate.project.facts.revision)
            old_hash = projects.storage.expected.get(project_id)
            phase = {"durable": False}
            def applying(state):
                _, _, _, item = item_in(state, run_id, batch_id)
                if item.batch.state != "offered" or item.receipt is not None:
                    raise AgentFailure("AGENT_TICKET_INVALID")
                item.batch.state = "applying"
                item.publication = publication
            service.store.update(project_id, applying)
            def publication_gate():
                # RichProjectStore already owns the canonical lifecycle lock here.
                with locked_root(service.store.assistant, ".assistant.lock"):
                    state = service.store._read(project_id, service.store.projects / project_id)
                    _, current_item, _ = self._gate(project_id, run_id, batch_id, owner=request.owner, state=state)
                    self._ticket(project_id, run_id, batch_id, request)
                    if current_item.batch.state != "applying" or current_item.batch.mutation != batch.mutation:
                        raise AgentFailure("AGENT_TICKET_INVALID")
            failure = None
            try:
                projects.storage.save(candidate, projects.originals, projects.artifacts, projects.images,
                    before_workspace=publication_gate, after_workspace=lambda _checksum: phase.update(durable=True))
            except Exception as error:
                failure = error
            try:
                persisted, checksum = projects.storage.read_committed(project_id)
                proof = next((item for item in persisted.mutation_replay if item.client_mutation_id == batch.mutation.client_mutation_id), None)
                exact = proof is not None and proof.request_sha256 == batch.request_sha256 and proof.resulting_revision == publication.project_revision
                if persisted.project_revision == publication.project_revision and checksum != publication.workspace_sha256:
                    exact = False
            except Exception:
                persisted, checksum, exact = None, None, False
            if persisted is not None and exact and phase["durable"]:
                self._adopt(project_id, persisted, checksum)
                receipt = self._receipt(batch, "saved", publication=publication)
            elif persisted is not None and checksum == old_hash and not exact:
                code = failure.code if isinstance(failure, AgentFailure) else "AGENT_SAVE_FAILED"
                disposition = "stale" if code == "AGENT_STALE_READ" else "cancelled" if code in {
                    "AGENT_CANCELLED", "AGENT_CONNECTION_CHANGED", "AGENT_OWNER_MISMATCH", "AGENT_LEASE_EXPIRED"} else "save_failed"
                receipt = self._receipt(batch, disposition, error=code)
            else:
                self._fence(project_id, batch_id)
                receipt = self._receipt(batch, "outcome_unknown", error="AGENT_OUTCOME_UNKNOWN")
            receipt = self._record(project_id, receipt)
            return AgentCommitResult(receipt=receipt, project=projects.response(project_id))

    def report(self, project_id, run_id, batch_id, request):
        with self.service.projects.state_lock:
            self.service.leases.require(project_id, request.owner)
            _, (_, _, _, item) = self._load(project_id, run_id, batch_id)
            if item.receipt is not None:
                if item.receipt != request.receipt:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                return item.receipt
            receipt = request.receipt
            batch = item.batch
            if (receipt.batch_id, receipt.run_id, receipt.tool_key, receipt.client_mutation_id, receipt.request_sha256) != (
                    batch.id, batch.run_id, batch.tool_key, batch.mutation.client_mutation_id, batch.request_sha256):
                raise AgentFailure("AGENT_EDIT_INVALID")
            if receipt.disposition not in {"rejected", "stale", "cancelled"} or batch.state not in {"prepared", "offered"}:
                raise AgentFailure("AGENT_TICKET_INVALID")
            return self._record(project_id, receipt)

    def recover(self, project_id, run_id, batch_id):
        with self.service.projects.state_lock:
            _, (_, _, _, item) = self._load(project_id, run_id, batch_id)
            if item.receipt is not None and item.receipt.disposition != "outcome_unknown" and batch_id not in self.service.unresolved.get(project_id, []):
                return item.receipt
            if item.batch.state not in {"applying", "outcome_unknown"}:
                raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
            try:
                persisted, checksum = self.service.projects.storage.read_committed(project_id, synchronize=True)
                proof = next((part for part in persisted.mutation_replay if part.client_mutation_id == item.batch.mutation.client_mutation_id), None)
                if (proof is None or proof.request_sha256 != item.batch.request_sha256 or item.publication is None
                        or proof.resulting_revision != item.publication.project_revision):
                    raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
                if persisted.project_revision == item.publication.project_revision and checksum != item.publication.workspace_sha256:
                    raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
                self._adopt(project_id, persisted, checksum)
                receipt = self._record(project_id, self._receipt(item.batch, "saved", publication=item.publication))
                self.service.unresolved[project_id] = [identifier for identifier in self.service.unresolved.get(project_id, []) if identifier != batch_id]
                if not self.service.unresolved[project_id]:
                    self.service.projects.agent_recovery_fences.discard(project_id)
                return receipt
            except Exception:
                self._fence(project_id, batch_id)
                raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None

    def recover_all(self):
        service = self.service
        if not any(service.unresolved.values()):
            return
        service.projects.ensure_loaded()
        for project_id, identifiers in list(service.unresolved.items()):
            for batch_id in list(identifiers):
                try:
                    state = service.store.load(project_id)
                    run_id = next(journal.run_id for journal in state.journals if any(item.result.batch_id == batch_id for item in journal.batches))
                    self.recover(project_id, run_id, batch_id)
                except Exception:
                    self._fence(project_id, batch_id)

    def manual_allowed(self, project_id, request):
        reserved = request.client_mutation_id.startswith("agent_") or ":agent:" in request.action_id
        if not reserved:
            return True
        if request.client_mutation_id.startswith("agent_") or request.kind not in {"undo", "redo"}:
            return False
        state = self.service.store.load(project_id)
        return any(item.batch is not None and item.receipt is not None and item.receipt.durable
            and item.batch.mutation.action_id == request.action_id
            and item.batch.mutation.capture.session_id == request.capture.session_id
            for journal in state.journals for item in journal.batches)

    def record_history(self, project_id, request):
        if ":agent:" not in request.action_id or request.kind not in {"undo", "redo"}:
            return
        def record(state):
            for journal in state.journals:
                for item in journal.batches:
                    if item.batch is None or item.batch.mutation.action_id != request.action_id:
                        continue
                    if any(action.client_mutation_id == request.client_mutation_id for action in item.history_actions):
                        return
                    item.history_actions.append(AgentHistoryAction(kind=request.kind, clientMutationId=request.client_mutation_id,
                        requestSha256=mutation_sha256(request), projectRevision=self.service.projects.workspaces[project_id].project_revision,
                        timestamp=self.service.store.clock()))
                    if len(item.history_actions) > 100:
                        item.history_actions.pop(0); item.history_actions_omitted += 1
        try:
            self.service.store.update(project_id, record, terminal=True)
        except AgentFailure:
            self.service.startup_errors[project_id] = "AGENT_STORE_UNAVAILABLE"
