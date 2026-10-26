"""Bind post-run publication to a fresh UI acceptance, never a model control."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import threading

from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.assistant_proposals import POLICY_REVISION, VERSION_BYTES, content_digest, encoded, proposal_before_digest
from packages.resume_core.models.agent import AgentBatchJournal, AgentClaimResult, AgentCommitResult, AgentPrepareResult
from packages.resume_core.models.assistant_approval import AssistantAcceptanceIdentityV1, AssistantApplicationClaimV1, AssistantApplicationRecoveryV1
from packages.resume_core.models.assistant_proposals import AssistantApprovalRecordV1
from packages.resume_core.rich_mutations import apply_rich_mutation, mutation_sha256
from packages.resume_core.storage import atomic_write

from .context import current_dependencies
from .proposals import origin_status
from .publication import item_in
from .approval_journal import origin_journal, origin_publication, known_application, journal_for_run


class AssistantApproval:
    def __init__(self, service):
        self.service = service
        self.tickets = {}
        self.revocations = {}
        self.revocation_lock = threading.Lock()
        self.compaction_errors = {}

    def signal_cancel(self, project_id, payload):
        self.service.leases.require(project_id, payload.owner)
        now = self.service.leases.clock()
        subject = project_id, self.key(payload)
        with self.revocation_lock:
            self.revocations = {key: expiry for key, expiry in self.revocations.items() if expiry > now}
            self.revocations[subject] = now + 30
        return subject

    def revoked(self, project_id, payload):
        with self.revocation_lock:
            return self.revocations.get((project_id, self.key(payload)), 0) > self.service.leases.clock()

    def is_reviewed(self, project_id, run_id, batch):
        if batch.id.startswith("accepted_") and batch.tool_key == batch.id:
            return True
        return any(value.proposal.origin_run_id == run_id and value.approval is not None
            and (value.approval.batch_id, value.approval.request_sha256) == (batch.id, batch.request_sha256)
            for value in self.service.proposals._items(project_id))

    def recover_all(self):
        service = self.service
        if not service.proposals.root.exists():
            self.recover_queued_journals()
            return
        for directory in service.proposals.root.iterdir():
            unresolved = None
            try:
                for value in service.proposals.list(directory.name):
                    if getattr(value, "record_kind", None) == "action_v1":
                        continue
                    if value.approval is not None and value.proposal.state in {"applying", "outcome_unknown"}:
                        unresolved = value.approval.batch_id
                        if getattr(service.projects, "background_jobs", None) is None:
                            try:
                                run_in(service.store.load(directory.name), value.proposal.origin_run_id)
                            except AgentFailure as error:
                                if error.code != "AGENT_NOT_FOUND":
                                    raise
                                service.publication._fence(directory.name, value.approval.batch_id)
                                continue
                        identity = AssistantAcceptanceIdentityV1(protocolVersion=1, proposalId=value.proposal.id,
                            version=value.proposal.version, contentSha256=value.proposal.content_sha256,
                            acceptanceId=value.approval.acceptance_id)
                        self.recover(directory.name, identity)
                        unresolved = None
            except (AgentFailure, BackgroundFailure) as error:
                code = error.code if isinstance(error, AgentFailure) else "AGENT_OUTCOME_UNKNOWN"
                service.proposal_errors[directory.name] = code
                if unresolved is not None:
                    service.publication._fence(directory.name, unresolved)
                    jobs = getattr(service.projects, "background_jobs", None)
                    if jobs is not None:
                        jobs.store.fences.setdefault(directory.name, "OUTCOME_UNKNOWN")
        self.recover_queued_journals()

    def recover_queued_journals(self):
        service = self.service
        jobs = getattr(service.projects, "background_jobs", None)
        if jobs is None or not jobs.enabled:
            return
        for entry in service.projects.storage.registry().entries:
            project = entry.project_id
            if entry.tombstoned or not (jobs.store.projects / project).exists():
                continue
            for job in jobs.store.load(project).jobs:
                if job.submission.kind != "agent" or not jobs.artifacts._path(jobs.store.projects / project, job.submission.input.id).exists():
                    continue
                _job, artifact = jobs.artifacts.record(project, job.id)
                for item in getattr(artifact, "applications", []):
                    if item.receipt is not None and item.receipt.disposition != "outcome_unknown":
                        continue
                    ticket = self.tickets.get((project, item.key))
                    if ticket is not None and ticket[1] > service.leases.clock():
                        continue
                    if item.publication is None:
                        receipt = service.publication._receipt(item.batch, "cancelled", error="AGENT_INTERRUPTED")
                        def unclaimed(current):
                            if current.key != item.key or current.publication is not None or current.batch != item.batch:
                                raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
                        jobs.artifacts.bound(project, job.id).record_reviewed_receipt(project, job.id, receipt, unclaimed)
                        continue
                    try:
                        self.recover_saved_journal(project, jobs.artifacts.bound(project, job.id), item)
                    except (AgentFailure, BackgroundFailure):
                        service.publication._fence(project, item.key)

    def recover_batch(self, project_id, run_id, batch_id):
        value = next((value for value in self.service.proposals.list(project_id)
            if value.proposal.origin_run_id == run_id and value.approval is not None and value.approval.batch_id == batch_id), None)
        if value is None:
            return None
        identity = AssistantAcceptanceIdentityV1(protocolVersion=1, proposalId=value.proposal.id, version=value.proposal.version,
            contentSha256=value.proposal.content_sha256, acceptanceId=value.approval.acceptance_id)
        recovered = self.recover(project_id, identity)
        return recovered.saved_receipt or (recovered.result.receipt if recovered.result is not None else None)

    def reconcile_reviews(self, project_id):
        service = self.service
        with service.projects.state_lock:
            for value in service.proposals.list(project_id):
                binding = value.approval
                if (getattr(value, "record_kind", None) == "action_v1" or binding is None
                        or value.proposal.state not in {"applying", "outcome_unknown"}):
                    continue
                ticket = self.tickets.get((project_id, binding.batch_id))
                lease = service.leases.leases.get(project_id)
                if (value.proposal.state == "applying" and binding.phase == "accepted" and ticket is not None
                        and ticket[1] > service.leases.clock() and lease is not None and lease.expires > service.leases.clock()
                        and (lease.epoch, lease.session_id, self.owner_digest(lease)) ==
                            (binding.owner_epoch, binding.session_id, binding.owner_sha256)):
                    continue
                identity = AssistantAcceptanceIdentityV1(protocolVersion=1, proposalId=value.proposal.id, version=value.proposal.version,
                    contentSha256=value.proposal.content_sha256, acceptanceId=binding.acceptance_id)
                try:
                    self.recover(project_id, identity)
                except AgentFailure:
                    service.publication._fence(project_id, binding.batch_id)
                    def unknown(values):
                        current = next(item for item in values if (item.proposal.id, item.proposal.version) == (value.proposal.id, value.proposal.version))
                        current.proposal.state = "outcome_unknown"
                        current.proposal.reason = "Результат сохранения проверяется. Не повторяйте применение. Черновик доступен для просмотра."
                        return current
                    service.proposals.update(project_id, unknown)

    @staticmethod
    def key(payload):
        return "accepted_" + digest([payload.proposal_id, payload.version, payload.content_sha256, payload.acceptance_id])[:40]

    @staticmethod
    def owner_digest(owner):
        return hashlib.sha256(owner.token.encode()).hexdigest()

    def value(self, project_id, payload):
        value = self.service.proposals.get(project_id, payload.proposal_id, payload.version)
        if value.proposal.content_sha256 != payload.content_sha256:
            raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
        return value

    def current(self, project_id, value, owner):
        service = self.service
        if not service.assistant_protocol_enabled or not service.settings.load().enabled:
            raise AgentFailure("AGENT_DISABLED")
        if project_id in service.projects.agent_recovery_fences | service.projects.catalog_recovery_fences:
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
        lease = service.leases.require(project_id, owner)
        connection = service.connection()
        if value.account_epoch != connection.epoch or connection.reason in {"AGENT_AUTH_REQUIRED", "AGENT_CONNECTION_CHANGED"}:
            raise AgentFailure("AGENT_CONNECTION_CHANGED")
        access = service.projects.catalog.get(project_id)
        if access.read_only:
            raise AgentFailure("AGENT_TOOL_DENIED")
        workspace = service.projects.read(project_id)
        if workspace.schema_version != 6 or value.policy_revision != POLICY_REVISION:
            raise AgentFailure("AGENT_PROTOCOL")
        if value.proposal.lineage != digest([workspace.project_id, workspace.created_at]):
            raise AgentFailure("AGENT_STALE_READ")
        if service.projects.durability(project_id) != "durable":
            raise AgentFailure("AGENT_SAVE_FAILED")
        if proposal_before_digest(value, workspace, archived=access.archived) != value.proposal.before_sha256 or not current_dependencies(workspace, value.dependencies):
            raise AgentFailure("AGENT_STALE_READ")
        return workspace, lease, access

    def rebound(self, value, payload, lease):
        if value.history is not None and value.history.session_id != lease.session_id:
            raise AgentFailure("AGENT_NO_OWNER")
        batch = value.batch.model_copy(deep=True)
        batch.id = batch.tool_key = self.key(payload)
        batch.owner_epoch, batch.state = lease.epoch, "offered"
        batch.mutation.client_mutation_id = "agent_" + digest([value.proposal.id, value.proposal.version, payload.acceptance_id])[:40]
        batch.mutation.capture.session_id = lease.session_id
        batch.mutation.capture.action_token = 0
        batch.request_sha256 = mutation_sha256(batch.mutation)
        if content_digest(apply_rich_mutation(value.baseline, batch.mutation)[0]) != value.proposal.content_sha256:
            raise AgentFailure("AGENT_EDIT_INVALID")
        return batch

    def claim(self, project_id, payload):
        service = self.service
        with service.projects.state_lock:
            self.tickets = {key: ticket for key, ticket in self.tickets.items() if ticket[1] > service.leases.clock()}
            value = self.value(project_id, payload)
            if len(value.revoked_acceptances) >= 100:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            if payload.acceptance_id in value.revoked_acceptances or self.revoked(project_id, payload):
                raise AgentFailure("AGENT_CANCELLED")
            key = self.key(payload)
            approval = value.approval
            if approval is not None and approval.batch_id == key:
                service.leases.require(project_id, payload.owner)
                if approval.owner_epoch != payload.owner.epoch or not hmac.compare_digest(approval.owner_sha256, self.owner_digest(payload.owner)):
                    raise AgentFailure("AGENT_OWNER_MISMATCH")
                ticket = self.tickets.get((project_id, key))
                if ticket is None or ticket[1] <= service.leases.clock():
                    raise AgentFailure("AGENT_TICKET_INVALID")
                _, _, journal = run_in(origin_journal(service, value).load(project_id), value.proposal.origin_run_id)
                item = next(item for item in journal.batches if item.key == key)
                if approval.phase != "accepted" or item.receipt is not None:
                    raise AgentFailure("AGENT_TICKET_INVALID")
                self.current(project_id, value, payload.owner)
                return self.reply(payload, ticket[0], approval.expires_at, item.batch)
            if value.proposal.state != "ready" or value.batch is None or value.baseline is None or value.candidate is None:
                raise AgentFailure("AGENT_TICKET_INVALID")
            finished, cancelled = origin_status(service, value)
            if cancelled:
                raise AgentFailure("AGENT_CANCELLED")
            if not finished:
                raise AgentFailure("AGENT_BUSY")
            _, lease, access = self.current(project_id, value, payload.owner)
            batch = self.rebound(value, payload, lease)
            remaining = min(15, max(0, lease.expires - service.leases.clock()))
            expires = (datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat()
            approval = AssistantApprovalRecordV1(acceptanceId=payload.acceptance_id, ownerSha256=self.owner_digest(payload.owner),
                ownerEpoch=lease.epoch, sessionId=lease.session_id, accessRevision=access.access_revision,
                accountEpoch=value.account_epoch, batchId=batch.id, requestSha256=batch.request_sha256,
                beforeWorkspaceSha256=service.projects.storage.expected[project_id], expiresAt=expires, phase="accepted")
            def register(state):
                _, _, journal = run_in(state, value.proposal.origin_run_id)
                if any(item.key == key for item in journal.batches):
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                result = AgentPrepareResult(disposition="prepared", batchId=batch.id, affected=batch.affected,
                    affectedCount=batch.affected_count, preview="Вариант принят интерфейсом; сохранение ещё не завершено.")
                journal.batches.append(AgentBatchJournal(key=key, payloadSha256=digest(payload.model_dump(exclude={"owner"}, by_alias=True)),
                    result=result, batch=batch, receipt=None))
                journal.reserved = True
            def accepted(values):
                current = next(item for item in values if item.proposal.id == payload.proposal_id and item.proposal.version == payload.version)
                if current.proposal.state != "ready" or current.proposal.content_sha256 != payload.content_sha256:
                    raise AgentFailure("AGENT_STALE_READ")
                current.approval, current.proposal.state = approval, "applying"
                current.proposal.reason = "Вариант принят. Проверяем и сохраняем показанные изменения."
                return current
            try:
                origin_journal(service, value).update_reviewed(project_id, register)
                service.proposals.update(project_id, accepted)
            except Exception:
                self.abort_preparation(project_id, value, key)
                raise
            token = secrets.token_urlsafe(32)
            self.tickets[project_id, key] = (token, service.leases.clock() + remaining)
            return self.reply(payload, token, expires, batch)

    def bound(self, value, payload):
        approval = value.approval
        if approval is None or approval.batch_id != self.key(payload) or approval.acceptance_id != payload.acceptance_id:
            raise AgentFailure("AGENT_TICKET_INVALID")
        if approval.owner_epoch != payload.owner.epoch or not hmac.compare_digest(approval.owner_sha256, self.owner_digest(payload.owner)):
            raise AgentFailure("AGENT_OWNER_MISMATCH")
        return approval

    def commit(self, project_id, payload):
        from packages.resume_core.project_catalog import AccessChanged
        service = self.service
        with service.projects.state_lock:
            value = self.value(project_id, payload)
            approval = self.bound(value, payload)
            publisher = origin_publication(service, value)
            _, (_, _, _, item) = publisher._load(project_id, value.proposal.origin_run_id, approval.batch_id)
            if approval.request_sha256 != payload.request_sha256:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            if item.receipt is not None:
                return self.recover(project_id, payload).result
            ticket = self.tickets.get((project_id, approval.batch_id))
            if ticket is None or ticket[1] <= service.leases.clock() or not hmac.compare_digest(ticket[0], payload.ticket):
                raise AgentFailure("AGENT_TICKET_INVALID")
            if value.proposal.state != "applying" or approval.phase != "accepted":
                raise AgentFailure("AGENT_TICKET_INVALID")
            try:
                self.current(project_id, value, payload.owner)
            except AgentFailure:
                self.abort_preparation(project_id, value, approval.batch_id)
                raise
            def authorize(state):
                # The shared writer already holds both canonical and assistant locks.
                current = service.proposals._read(service.proposals.directory(project_id) / service.proposals.filename(value))
                binding = self.bound(current, payload)
                if self.revoked(project_id, payload) or payload.acceptance_id in current.revoked_acceptances:
                    raise AgentFailure("AGENT_CANCELLED")
                if project_id in service.projects.agent_recovery_fences | service.projects.catalog_recovery_fences:
                    raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
                lease = service.leases.require(project_id, payload.owner)
                connection = service.connection()
                if not service.settings.load().enabled or binding.session_id != lease.session_id:
                    raise AgentFailure("AGENT_NO_OWNER")
                if connection.epoch != binding.account_epoch or connection.reason in {"AGENT_AUTH_REQUIRED", "AGENT_CONNECTION_CHANGED"}:
                    raise AgentFailure("AGENT_CONNECTION_CHANGED")
                if ticket[1] <= service.leases.clock():
                    raise AgentFailure("AGENT_TICKET_INVALID")
                service.projects.catalog.require_write(project_id, binding.access_revision)
                _, run, _, active = item_in(state, value.proposal.origin_run_id, binding.batch_id)
                if run.state not in {"completed", "failed", "interrupted"} or run.error is not None and run.error.code in {"AGENT_CANCELLED", "AGENT_CLEANUP_FAILED"}:
                    raise AgentFailure("AGENT_CANCELLED")
                workspace = service.projects.storage._read_committed_unlocked(project_id)[0]
                if (current.proposal.state != "applying" or binding.phase != "accepted"
                        or content_digest(workspace) != current.proposal.before_sha256
                        or not current_dependencies(workspace, current.dependencies)):
                    raise AgentFailure("AGENT_STALE_READ")
                current.approval.phase = "commit_claimed"
                from packages.resume_core.assistant_proposals import fit_control_capacity
                fit_control_capacity(current)
                raw = encoded(current)
                if len(raw) > VERSION_BYTES:
                    raise AgentFailure("AGENT_EDIT_LIMIT")
                atomic_write(service.proposals.directory(project_id) / service.proposals.filename(current), raw)
                return active
            def verify(candidate):
                if content_digest(candidate) != value.proposal.content_sha256:
                    raise AgentFailure("AGENT_EDIT_INVALID")
            jobs = getattr(service.projects, "background_jobs", None)
            write = None
            if jobs is not None and jobs.enabled:
                from packages.resume_core.assistant_publication import AssistantMutationGrant
                from packages.resume_core.background_history import digest_bytes
                from packages.resume_core.models.background import WriterCommitBindingV1
                if payload.writer is None:
                    self.abort_preparation(project_id, value, approval.batch_id)
                    raise AgentFailure("AGENT_NO_OWNER")
                def write(mutation, claim, prepared):
                    history_binding = None
                    if value.history is not None and value.history.backend is not None:
                        from packages.resume_core.models.background import HistoryCommitBindingV1
                        target = value.history.backend
                        history_binding = HistoryCommitBindingV1(jobId=target.job_id, proposalId=target.proposal_id,
                            transferId=target.transfer_id, direction=value.history.direction, previousRef=value.history.previous_ref,
                            commandId=approval.batch_id, commandSha256=digest({"jobId": target.job_id, "proposalId": target.proposal_id,
                                "transferId": target.transfer_id, "commandId": approval.batch_id, "direction": value.history.direction}))
                    def writer_authority(state, workspace, directory):
                        writer = jobs.writers.require(state, payload.writer.proof)
                        if (writer.session_id != mutation.capture.session_id or (payload.writer.canonical_revision,
                                payload.writer.canonical_sha256) != (writer.acknowledged_revision, writer.acknowledged_sha256)):
                            raise AgentFailure("AGENT_OWNER_MISMATCH")
                        jobs.writers.advance(state, workspace, digest_bytes(workspace), payload.writer)
                        if history_binding is not None:
                            jobs.writers.validate_history_binding(state, directory, workspace, history_binding)
                            # The editor builds the chat steps itself; they must do what the stored backend inverse does.
                            stored = jobs.writers.history_material(directory, state, history_binding, workspace)[3].model_copy(deep=True)
                            stored.client_mutation_id = "preview_" + history_binding.transfer_id
                            try:
                                expected, _duplicate = apply_rich_mutation(workspace, stored)
                            except ValueError:
                                raise AgentFailure("AGENT_STALE_READ") from None
                            if content_digest(expected) != value.proposal.content_sha256:
                                raise AgentFailure("AGENT_STALE_READ")
                        jobs.writers.write(directory, state)
                        return WriterCommitBindingV1(epoch=writer.epoch, incarnation=writer.incarnation,
                            actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation)
                    def claim_ui():
                        try:
                            claim()
                        except AgentFailure as error:
                            code = {"AGENT_CANCELLED": "CANCELLED", "AGENT_DISABLED": "CANCELLED",
                                "AGENT_CONNECTION_CHANGED": "ACCOUNT_CHANGED", "AGENT_NO_OWNER": "WRITER_UNKNOWN",
                                "AGENT_OWNER_MISMATCH": "WRITER_UNKNOWN", "AGENT_LEASE_EXPIRED": "WRITER_UNKNOWN",
                                "AGENT_STALE_READ": "DEPENDENCY_CHANGED", "AGENT_TICKET_INVALID": "REQUEST_EXPIRED",
                                "AGENT_TOOL_DENIED": "CANCELLED"}.get(error.code)
                            if code is None:
                                raise
                            raise BackgroundFailure(code) from None
                    grant = AssistantMutationGrant(project_id, payload.request_sha256, writer_authority, claim_ui, prepared, history_binding)
                    try:
                        return jobs.publisher.apply_reviewed(project_id, mutation, grant, originals=service.projects.originals,
                            artifacts=service.projects.artifacts, images=service.projects.images)
                    except Exception:
                        state = jobs.publisher.recover(project_id)
                        known = next((intent for intent in state.manual_intents
                            if intent.client_mutation_id == mutation.client_mutation_id), None)
                        if known is not None and known.phase == "reconciled" and known.reconciled_reason is not None:
                            code = {"CANCELLED": "AGENT_CANCELLED", "ACCOUNT_CHANGED": "AGENT_CONNECTION_CHANGED",
                                "WRITER_UNKNOWN": "AGENT_NO_OWNER", "DEPENDENCY_CHANGED": "AGENT_STALE_READ",
                                "REQUEST_EXPIRED": "AGENT_TICKET_INVALID"}.get(known.reconciled_reason.code, "AGENT_SAVE_FAILED")
                            raise AgentFailure(code) from None
                        if known is None or known.request_sha256 != payload.request_sha256 or known.phase != "receipt_stored":
                            raise
            try:
                with service.projects.catalog.authority(project_id, approval.access_revision):
                    result = publisher.publish_candidate(project_id, value.proposal.origin_run_id, item.batch,
                        authorize, verify=verify, record_receipt=lambda receipt: self.record(project_id, value, receipt), write=write)
            except AccessChanged:
                self.abort_preparation(project_id, value, approval.batch_id)
                raise AgentFailure("AGENT_TOOL_DENIED") from None
            self.settle(project_id, payload, result.receipt)
            return result

    def abort_preparation(self, project_id, value, key, *, cancelled=False):
        service = self.service
        try:
            store = origin_journal(service, value)
            _, _, journal = run_in(store.load(project_id), value.proposal.origin_run_id)
            item = next((part for part in journal.batches if part.key == key), None)
            if item is None:
                return
            if item.publication is not None or item.batch.state in {"applying", "outcome_unknown"}:
                if not cancelled or value.approval is None or value.approval.phase != "accepted":
                    raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
            receipt = item.receipt or store.record_reviewed_receipt(project_id, value.proposal.origin_run_id,
                service.publication._receipt(item.batch, "cancelled", error="AGENT_CANCELLED"), lambda _item: None)
            current = service.proposals.get(project_id, value.proposal.id, value.proposal.version)
            if current.approval is not None and current.approval.batch_id == key:
                self.settle(project_id, current.proposal, receipt)
            self.tickets.pop((project_id, key), None)
        except Exception:
            service.publication._fence(project_id, key)
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None

    def recover(self, project_id, payload, *, resume=False):
        service = self.service
        with service.projects.state_lock:
            try:
                value = self.value(project_id, payload)
            except AgentFailure:
                known = known_application(service, project_id, self.key(payload))
                if known is None:
                    raise
                if known.receipt is not None and not known.receipt.durable and known.receipt.disposition != "outcome_unknown":
                    return AssistantApplicationRecoveryV1(proposal=None, result=AgentCommitResult(receipt=known.receipt,
                        project=service.projects.response(project_id)), claim=None, reloadRequired=True,
                        reason="Изменения не сохранены. Данные предпросмотра недоступны; подготовьте новый вариант.")
                if known.receipt is None or not known.receipt.durable:
                    receipt = self.recover_saved_journal(project_id, journal_for_run(service, project_id, known.batch.run_id), known)
                    known = known.model_copy(update={"receipt": receipt})
                return self.saved_recovery(project_id, known, None,
                    "Изменения сохранены. Данные предпросмотра недоступны; откройте резюме заново для продолжения.")
            binding = value.approval
            if binding is not None and binding.acceptance_id != payload.acceptance_id:
                if resume:
                    return self.cancel(project_id, payload)
                prior = known_application(service, project_id, self.key(payload))
                if prior is not None and prior.receipt is not None and prior.receipt.disposition != "outcome_unknown":
                    if prior.receipt.durable:
                        return self.saved_recovery(project_id, prior, value.proposal)
                    return AssistantApplicationRecoveryV1(proposal=value.proposal,
                        result=AgentCommitResult(receipt=prior.receipt, project=service.projects.response(project_id)), claim=None)
                return AssistantApplicationRecoveryV1(proposal=value.proposal, result=None, claim=None)
            if resume and (binding is None or binding.acceptance_id != payload.acceptance_id):
                # The unanswered claim may still arrive; revoke this click before reporting no claim.
                return self.cancel(project_id, payload)
            if binding is None:
                return AssistantApplicationRecoveryV1(proposal=value.proposal, result=None, claim=None)
            _, (_, _, _, item) = origin_publication(service, value)._load(project_id, value.proposal.origin_run_id, binding.batch_id)
            receipt, claim = item.receipt, None
            if receipt is None and binding.phase == "accepted" and resume:
                self.bound(value, payload)
                self.current(project_id, value, payload.owner)
                ticket = self.tickets.get((project_id, binding.batch_id))
                if ticket is not None and ticket[1] > service.leases.clock():
                    claim = self.reply(payload, ticket[0], binding.expires_at, item.batch)
                    return AssistantApplicationRecoveryV1(proposal=value.proposal, result=None, claim=claim)
            if receipt is None or receipt.disposition == "outcome_unknown":
                try:
                    jobs = getattr(service.projects, "background_jobs", None)
                    if jobs is not None and jobs.enabled:
                        jobs.publisher.recover(project_id)
                    persisted, checksum = service.projects.storage.read_committed(project_id, synchronize=True)
                    proof = next((part for part in persisted.mutation_replay
                        if part.client_mutation_id == item.batch.mutation.client_mutation_id), None)
                    exact = (proof is not None and proof.request_sha256 == binding.request_sha256 and item.publication is not None
                        and proof.resulting_revision == item.publication.project_revision)
                    if exact and persisted.project_revision == item.publication.project_revision:
                        exact = checksum == item.publication.workspace_sha256
                    if exact:
                        service.publication._adopt(project_id, persisted, checksum)
                        receipt = service.publication._receipt(item.batch, "saved", publication=item.publication)
                    elif checksum == binding.before_workspace_sha256:
                        receipt = service.publication._receipt(item.batch, "save_failed", error="AGENT_SAVE_FAILED")
                    else:
                        raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
                    receipt = self.record(project_id, value, receipt)
                except Exception:
                    service.publication._fence(project_id, binding.batch_id)
                    receipt = service.publication._receipt(item.batch, "outcome_unknown", error="AGENT_OUTCOME_UNKNOWN")
                    self.settle(project_id, value.proposal, receipt)
                    raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None
            try:
                self.settle(project_id, value.proposal, receipt)
            except Exception:
                if not receipt.durable:
                    raise
                return self.saved_recovery(project_id, item.model_copy(update={"receipt": receipt}), None,
                    "Изменения сохранены. Не удалось обновить данные предпросмотра; откройте резюме заново.")
            self.tickets.pop((project_id, binding.batch_id), None)
            service.unresolved[project_id] = [key for key in service.unresolved.get(project_id, []) if key != binding.batch_id]
            if not service.unresolved[project_id]:
                service.projects.agent_recovery_fences.discard(project_id)
                if service.projects.save_errors.get(project_id) == "AGENT_OUTCOME_UNKNOWN":
                    service.projects.save_errors.pop(project_id, None)
            value = self.value(project_id, payload)
            if receipt.durable:
                return self.saved_recovery(project_id, item.model_copy(update={"receipt": receipt}), value.proposal)
            return AssistantApplicationRecoveryV1(proposal=value.proposal,
                result=AgentCommitResult(receipt=receipt, project=service.projects.response(project_id)), claim=None)

    def saved_recovery(self, project_id, item, proposal, reason=None):
        receipt = item.receipt
        if receipt is None or not receipt.durable:
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
        result = None
        try:
            result = AgentCommitResult(receipt=receipt, project=self.service.projects.response(project_id))
        except Exception:
            pass
        return AssistantApplicationRecoveryV1(proposal=proposal, result=result, claim=None, savedReceipt=receipt,
            reloadRequired=result is None or proposal is None,
            reason=reason or ("Изменения сохранены. Откройте резюме заново для продолжения." if result is None else None))

    def recover_saved_journal(self, project_id, store, item):
        service = self.service
        if not item.key.startswith("accepted_") or item.batch is None or item.publication is None:
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
        jobs = getattr(service.projects, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            jobs.publisher.recover(project_id)
        workspace, checksum = service.projects.storage.read_committed(project_id, synchronize=True)
        proof = next((part for part in workspace.mutation_replay if part.client_mutation_id == item.batch.mutation.client_mutation_id), None)
        if (proof is None or proof.request_sha256 != item.batch.request_sha256
                or proof.resulting_revision != item.publication.project_revision
                or workspace.project_revision == item.publication.project_revision and checksum != item.publication.workspace_sha256):
            service.publication._fence(project_id, item.key)
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
        receipt = service.publication._receipt(item.batch, "saved", publication=item.publication)
        def authorize(current):
            if current.key != item.key or current.batch != item.batch or current.publication != item.publication:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
        try:
            receipt = store.record_reviewed_receipt(project_id, item.batch.run_id, receipt, authorize)
        except Exception:
            service.publication._fence(project_id, item.key)
            return receipt
        service.publication._adopt(project_id, workspace, checksum)
        service.unresolved[project_id] = [key for key in service.unresolved.get(project_id, []) if key != item.key]
        if not service.unresolved[project_id]:
            service.projects.agent_recovery_fences.discard(project_id)
            if service.projects.save_errors.get(project_id) == "AGENT_OUTCOME_UNKNOWN":
                service.projects.save_errors.pop(project_id, None)
        return receipt

    def cancel(self, project_id, payload):
        subject = self.signal_cancel(project_id, payload)
        reply = self._cancel(project_id, payload)
        with self.revocation_lock:
            self.revocations.pop(subject, None)
        return reply

    def _cancel(self, project_id, payload):
        service = self.service
        with service.projects.state_lock:
            service.leases.require(project_id, payload.owner)
            value = self.value(project_id, payload)
            if value.proposal.state in {"incomplete", "stale", "expired", "discarded", "invalid", "cancelled", "applied"}:
                return self.recover(project_id, payload)
            if value.approval is not None and value.approval.acceptance_id == payload.acceptance_id:
                if value.approval.phase == "accepted":
                    self.abort_preparation(project_id, value, value.approval.batch_id, cancelled=True)
                else:
                    recovered = self.recover(project_id, payload)
                    if recovered.proposal is None or recovered.proposal.state != "failed_before_commit":
                        return recovered
            def revoke(values):
                current = next(part for part in values if (part.proposal.id, part.proposal.version) == (payload.proposal_id, payload.version))
                if payload.acceptance_id not in current.revoked_acceptances:
                    if len(current.revoked_acceptances) >= 100:
                        current.proposal.state = "cancelled" if current.proposal.state == "building" else "discarded"
                        current.proposal.reason = "Применение остановлено. Для новой попытки подготовьте новый вариант."
                    else:
                        current.revoked_acceptances.append(payload.acceptance_id)
                return current
            service.proposals.update(project_id, revoke)
            return self.recover(project_id, payload)

    def report(self, project_id, payload):
        service = self.service
        with service.projects.state_lock:
            service.leases.require(project_id, payload.owner)
            value = self.value(project_id, payload)
            binding = self.bound(value, payload)
            _, (_, _, _, item) = origin_publication(service, value)._load(project_id, value.proposal.origin_run_id, binding.batch_id)
            if item.receipt is not None:
                if payload.receipt != item.receipt:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            else:
                if (binding.phase != "accepted" or item.batch.state != "offered"
                        or payload.receipt.disposition not in {"stale", "cancelled", "rejected"}):
                    raise AgentFailure("AGENT_TICKET_INVALID")
                self.record(project_id, value, payload.receipt)
            self.settle(project_id, payload, payload.receipt)
            return self.value(project_id, payload).proposal

    def retry(self, project_id, payload):
        service = self.service
        with service.projects.state_lock:
            value = self.value(project_id, payload)
            if value.proposal.state != "failed_before_commit":
                raise AgentFailure("AGENT_TICKET_INVALID")
            previous = AssistantAcceptanceIdentityV1(protocolVersion=1, proposalId=value.proposal.id,
                version=value.proposal.version, contentSha256=value.proposal.content_sha256,
                acceptanceId=value.approval.acceptance_id) if value.approval is not None else payload
            recovered = self.recover(project_id, previous)
            if recovered.proposal is None or recovered.proposal.state != "failed_before_commit" or payload.acceptance_id in value.revoked_acceptances:
                raise AgentFailure("AGENT_TICKET_INVALID")
            if len(value.revoked_acceptances) >= 100:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            self.current(project_id, value, payload.owner)
            if value.approval is None or value.approval.acceptance_id == payload.acceptance_id:
                raise AgentFailure("AGENT_TICKET_INVALID")
            def ready(values):
                current = next(part for part in values if (part.proposal.id, part.proposal.version) == (payload.proposal_id, payload.version))
                current.proposal.state, current.proposal.reason = "ready", "Вариант проверен. Для сохранения нажмите «Применить»."
                return current
            return service.proposals.update(project_id, ready).proposal

    def record(self, project_id, value, receipt):
        def authorize(item):
            current = self.service.proposals._read(self.service.proposals.directory(project_id) / self.service.proposals.filename(value))
            binding = current.approval
            if (binding is None or binding.batch_id != item.key or binding.request_sha256 != item.batch.request_sha256
                    or item.batch.run_id != current.proposal.origin_run_id):
                raise AgentFailure("AGENT_TICKET_INVALID")
        try:
            return origin_journal(self.service, value).record_reviewed_receipt(project_id, value.proposal.origin_run_id, receipt, authorize)
        except Exception:
            self.service.publication._fence(project_id, receipt.batch_id)
            raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None

    def settle(self, project_id, payload, receipt):
        identifier = payload.proposal_id if hasattr(payload, "proposal_id") else payload.id
        existing = self.service.proposals.get(project_id, identifier, payload.version)
        if existing.approval is None or existing.approval.batch_id != receipt.batch_id:
            raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
        if existing.proposal.state not in {"applying", "outcome_unknown"}:
            if receipt.durable and existing.proposal.state == "applied":
                self.compact(project_id, identifier, payload.version, receipt)
            self.tickets.pop((project_id, receipt.batch_id), None)
            return
        if receipt.durable:
            try:
                self.service.proposals.compact_applied(project_id, identifier, payload.version, receipt=receipt, settle=True)
                self.compaction_errors.pop(project_id, None)
                self.tickets.pop((project_id, receipt.batch_id), None)
                return
            except Exception:
                self.compaction_errors[project_id] = "AGENT_STORE_UNAVAILABLE"
        def settled(values):
            current = next(value for value in values if value.proposal.id == identifier and value.proposal.version == payload.version)
            approval = current.approval
            if approval is None or approval.batch_id != receipt.batch_id:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            if current.proposal.state in {"applying", "outcome_unknown"}:
                current.proposal.state = "applied" if receipt.durable else "outcome_unknown" if receipt.disposition == "outcome_unknown" else "failed_before_commit"
                current.proposal.reason = ("Показанные изменения сохранены." if receipt.durable else
                    "Результат сохранения проверяется. Не повторяйте применение." if receipt.disposition == "outcome_unknown" else
                    "Изменения не сохранены. Черновик сохранён для просмотра.")
                approval.phase = "receipt_stored" if receipt.durable else "commit_claimed" if receipt.disposition == "outcome_unknown" else "cancelled"
                if (not receipt.durable and receipt.disposition != "outcome_unknown"
                        and approval.acceptance_id not in current.revoked_acceptances and len(current.revoked_acceptances) < 100):
                    current.revoked_acceptances.append(approval.acceptance_id)
            return current
        current = self.service.proposals.update(project_id, settled)
        if receipt.disposition != "outcome_unknown":
            self.tickets.pop((project_id, receipt.batch_id), None)
        if receipt.durable and current.proposal.state == "applied":
            # The existing journal owns save proof; retention may now drop the large private candidate.
            self.compact(project_id, identifier, payload.version, receipt)

    def compact(self, project_id, identifier, version, receipt):
        try:
            self.service.proposals.compact_applied(project_id, identifier, version, receipt=receipt)
            self.compaction_errors.pop(project_id, None)
        except Exception:
            # Cleanup cannot revoke a save already proved by the canonical writer and journal.
            self.compaction_errors[project_id] = "AGENT_STORE_UNAVAILABLE"

    @staticmethod
    def reply(payload, token, expires, batch):
        return AssistantApplicationClaimV1(accepted=AssistantAcceptanceIdentityV1(protocolVersion=1,
            proposalId=payload.proposal_id, version=payload.version, contentSha256=payload.content_sha256,
            acceptanceId=payload.acceptance_id), claim=AgentClaimResult(ticket=token, expiresAt=expires, batch=batch))
