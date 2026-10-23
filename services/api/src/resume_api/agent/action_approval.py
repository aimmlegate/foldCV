"""Apply a reviewed project command through existing catalog and canonical writers."""

import base64
from datetime import datetime, timedelta, timezone
import hmac
import secrets

from packages.resume_core.agent_store import AgentFailure, digest
from packages.resume_core.assistant_actions import action_content_digest, workspace_action_candidate
from packages.resume_core.assistant_proposals import VERSION_BYTES, encoded, proposal_before_digest
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.agent import AgentProjectOperation
from packages.resume_core.models.assistant_actions import AssistantProjectActionClaimV1, AssistantProjectActionResultV1, AssistantStoredActionV1
from packages.resume_core.models.assistant_approval import AssistantAcceptanceIdentityV1
from packages.resume_core.models.assistant_proposals import AssistantApprovalRecordV1, AssistantProposalV1
from packages.resume_core.models.rich_workspace import RichMutationReplay
from packages.resume_core.project_catalog import AccessChanged
from packages.resume_core.storage import atomic_write, locked_root

from .approval import AssistantApproval
from .context import current_dependencies
from .project_action_recovery import reconcile_action
from .proposals import origin_status


class AssistantActionApproval(AssistantApproval):
    def reconcile_reviews(self, project_id):
        service = self.service
        for value in service.proposals.list(project_id):
            binding = value.approval
            if not isinstance(value, AssistantStoredActionV1) or binding is None or value.proposal.state not in {"applying", "outcome_unknown"}:
                continue
            ticket = self.tickets.get((project_id, binding.batch_id))
            lease = service.leases.leases.get(project_id)
            if (binding.phase == "accepted" and ticket is not None and ticket[1] > service.leases.clock()
                    and lease is not None and lease.expires > service.leases.clock()
                    and (lease.epoch, lease.session_id) == (binding.owner_epoch, binding.session_id)):
                continue
            identity = AssistantAcceptanceIdentityV1(protocolVersion=1, proposalId=value.proposal.id,
                version=value.proposal.version, contentSha256=value.proposal.content_sha256, acceptanceId=binding.acceptance_id)
            try:
                self.recover(project_id, identity)
            except Exception:
                service.projects.catalog_recovery_fences.add(project_id)
                self.settle_action(project_id, identity, "applying")

    def recover_all(self):
        for directory in self.service.proposals.root.iterdir() if self.service.proposals.root.exists() else []:
            try:
                self.reconcile_reviews(directory.name)
            except AgentFailure as error:
                self.service.startup_errors[directory.name] = error.code

    def value(self, project_id, payload):
        value = super().value(project_id, payload)
        if not isinstance(value, AssistantStoredActionV1):
            raise AgentFailure("AGENT_PROTOCOL")
        return value

    def reply(self, payload, token, expires, checksum):
        return AssistantProjectActionClaimV1(accepted=AssistantAcceptanceIdentityV1.model_validate(
            payload.model_dump(by_alias=True, exclude={"owner"})), ticket=token, expiresAt=expires, requestSha256=checksum)

    def claim(self, project_id, payload):
        service = self.service
        with service.projects.state_lock:
            value = self.value(project_id, payload)
            if payload.acceptance_id in value.revoked_acceptances or self.revoked(project_id, payload):
                raise AgentFailure("AGENT_CANCELLED")
            if len(value.revoked_acceptances) >= 100:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            key, binding = self.key(payload), value.approval
            if binding is not None and binding.batch_id == key:
                self.bound(value, payload)
                self.current(project_id, value, payload.owner)
                ticket = self.tickets.get((project_id, key))
                if binding.phase != "accepted" or ticket is None or ticket[1] <= service.leases.clock():
                    raise AgentFailure("AGENT_TICKET_INVALID")
                return self.reply(payload, ticket[0], binding.expires_at, binding.request_sha256)
            if value.proposal.state != "ready" or value.action is None or value.baseline is None:
                raise AgentFailure("AGENT_TICKET_INVALID")
            finished, cancelled = origin_status(service, value)
            if not finished or cancelled:
                raise AgentFailure("AGENT_CANCELLED" if cancelled else "AGENT_BUSY")
            workspace, lease, access = self.current(project_id, value, payload.owner)
            self.rebuild(project_id, value, workspace)
            remaining = min(15, max(0, lease.expires - service.leases.clock()))
            expires = (datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat()
            binding = AssistantApprovalRecordV1(acceptanceId=payload.acceptance_id, ownerSha256=self.owner_digest(payload.owner),
                ownerEpoch=lease.epoch, sessionId=lease.session_id, accessRevision=access.access_revision,
                accountEpoch=value.account_epoch, batchId=key, requestSha256=digest([key, value.proposal.content_sha256]),
                beforeWorkspaceSha256=digest_bytes(workspace), expiresAt=expires, phase="accepted")
            def accept(values):
                current = next(item for item in values if (item.proposal.id, item.proposal.version) == (payload.proposal_id, payload.version))
                if current.proposal.state != "ready":
                    raise AgentFailure("AGENT_STALE_READ")
                current.approval, current.proposal.state = binding, "applying"
                current.proposal.reason = "Действие принято. Проверяем и сохраняем показанный результат."
                return current
            service.proposals.update(project_id, accept)
            token = secrets.token_urlsafe(32)
            self.tickets[project_id, key] = token, service.leases.clock() + remaining
            return self.reply(payload, token, expires, binding.request_sha256)

    def rebuild(self, project_id, value, workspace):
        action = value.action
        if action is None:
            raise AgentFailure("ASSISTANT_PROPOSAL_MISSING")
        request = action.request
        if request.action in {"archive", "restore", "delete"}:
            from packages.resume_core.assistant_actions import lifecycle_preview
            lifecycle_preview(workspace, request, archived=action.archived_before)
            return None
        source = next((item for item in value.candidate.project.sources if item.id not in
            {old.id for old in workspace.project.sources}), None) if request.action == "add_source_text" else None
        asset = next((item for item in value.candidate.project.assets if item.id not in
            {old.id for old in workspace.project.assets}), None) if request.action == "import_asset" else None
        candidate, _metadata = workspace_action_candidate(workspace, request, source=source, asset=asset,
            image_references=self.service.projects.image_references(project_id) if request.action == "remove_asset" else None)
        if action_content_digest(candidate) != action_content_digest(value.candidate):
            raise AgentFailure("AGENT_EDIT_INVALID")
        return candidate

    def claim_boundary(self, project_id, payload, ticket):
        service, projects = self.service, self.service.projects
        with locked_root(service.store.assistant, ".assistant.lock"):
            value = service.proposals._read(service.proposals.directory(project_id) / (payload.proposal_id + "-" + str(payload.version) + ".json"))
            binding = self.bound(value, payload)
            lease = service.leases.require(project_id, payload.owner)
            connection = service.connection()
            if self.revoked(project_id, payload) or payload.acceptance_id in value.revoked_acceptances:
                raise AgentFailure("AGENT_CANCELLED")
            if (not service.assistant_protocol_enabled or not service.settings.load().enabled
                    or lease.session_id != binding.session_id):
                raise AgentFailure("AGENT_DISABLED")
            if connection.epoch != binding.account_epoch or connection.reason in {"AGENT_AUTH_REQUIRED", "AGENT_CONNECTION_CHANGED"}:
                raise AgentFailure("AGENT_CONNECTION_CHANGED")
            if ticket[1] <= service.leases.clock() or binding.phase != "accepted" or value.proposal.state != "applying":
                raise AgentFailure("AGENT_TICKET_INVALID")
            access = projects.catalog.require_write(project_id, binding.access_revision)
            workspace = projects.storage._read_committed_unlocked(project_id)[0]
            archived = projects.catalog.get(project_id).archived
            if (project_id in projects.agent_recovery_fences | projects.catalog_recovery_fences
                    or proposal_before_digest(value, workspace, archived=archived) != value.proposal.before_sha256
                    or not current_dependencies(workspace, value.dependencies)):
                raise AgentFailure("AGENT_STALE_READ")
            self.rebuild(project_id, value, workspace)
            value.approval.phase = "commit_claimed"
            raw = encoded(value)
            if len(raw) > VERSION_BYTES:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            atomic_write(service.proposals.directory(project_id) / service.proposals.filename(value), raw)

    def _commit(self, project_id, payload):
        service, projects = self.service, self.service.projects
        with projects.state_lock:
            known = projects.catalog.actions().get(self.key(payload))
            if known is not None:
                if known.get("payloadSha256") != payload.request_sha256:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                self.recover(project_id, payload)
                return
            value = self.value(project_id, payload)
            binding = self.bound(value, payload)
            key = binding.batch_id
            if binding.request_sha256 != payload.request_sha256:
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            if key in projects.catalog.actions():
                return
            if binding.phase != "accepted" or value.proposal.state != "applying" or payload.acceptance_id in value.revoked_acceptances:
                raise AgentFailure("AGENT_CANCELLED")
            ticket = self.tickets.get((project_id, key))
            if ticket is None or not hmac.compare_digest(ticket[0], payload.ticket) or ticket[1] <= service.leases.clock():
                raise AgentFailure("AGENT_TICKET_INVALID")
            try:
                workspace, _lease, _access = self.current(project_id, value, payload.owner)
                candidate = self.rebuild(project_id, value, workspace)
                request = value.action.request
                result = {"action": request.action, "projectId": project_id, "durable": True}
                retained_proof = value.proposal.model_dump(mode="json", by_alias=True)
                retained_proof.update(changes=[], coverage=[])
                command = {"projectId": project_id, "runId": value.proposal.origin_run_id, "key": key,
                    "action": request.action, "accessRevision": binding.access_revision, "projectRevision": workspace.project_revision,
                    "payloadSha256": binding.request_sha256, "status": "applying", "result": result,
                    "assistantProtocolVersion": 1, "accepted": payload.model_dump(mode="json", by_alias=True, exclude={"owner", "ticket", "request_sha256", "writer"}),
                    "proposal": retained_proof}
                with projects.catalog.authority(project_id, binding.access_revision):
                    if request.action in {"archive", "restore"}:
                        command["commitKind"] = "catalog"
                        self.claim_boundary(project_id, payload, ticket)
                        projects.catalog.archive_action(project_id, request.action == "archive", key, {**command, "status": "completed"})
                        return
                    if request.action == "delete":
                        command.update(commitKind="delete", status="pending")
                        projects.catalog.reserve_action(key, command)
                        self.claim_boundary(project_id, payload, ticket)
                        projects.storage.tombstone(project_id)
                        projects.deleted_ids.add(project_id)
                        projects.catalog.record_action(key, {**command, "status": "deleting"})
                        return
                    candidate.project_revision += 1
                    candidate.project.revision = candidate.project_revision
                    candidate.updated_at = projects.clock().isoformat()
                    proof_id = "catalog_" + key
                    candidate.mutation_replay.append(RichMutationReplay(clientMutationId=proof_id,
                        requestSha256=binding.request_sha256, resultingRevision=candidate.project_revision))
                    candidate.mutation_replay = candidate.mutation_replay[-100:]
                    result["projectRevision"] = candidate.project_revision
                    command.update(commitKind="workspace", proofId=proof_id, beforeSha256=digest_bytes(workspace))
                    originals, images = dict(projects.originals), dict(projects.images)
                    if value.action.blob_base64 is not None:
                        blob = base64.b64decode(value.action.blob_base64, validate=True)
                        if request.action == "add_source_text":
                            source = next(item for item in candidate.project.sources if item.id not in {old.id for old in workspace.project.sources})
                            originals[project_id, source.id] = blob
                        elif request.action == "import_asset":
                            asset = next(item for item in candidate.project.assets if item.id not in {old.id for old in workspace.project.assets})
                            images[project_id, asset.id] = blob
                    jobs = getattr(projects, "background_jobs", None)
                    if jobs is not None and jobs.enabled:
                        if payload.writer is None:
                            raise AgentFailure("AGENT_NO_OWNER")
                        from packages.resume_core.assistant_publication import AssistantSnapshotGrant
                        from packages.resume_core.models.background import WriterCommitBindingV1
                        def writer_authority(state, before, directory):
                            writer = jobs.writers.require(state, payload.writer.proof)
                            if (writer.session_id != binding.session_id or (payload.writer.canonical_revision, payload.writer.canonical_sha256)
                                    != (writer.acknowledged_revision, writer.acknowledged_sha256)):
                                raise AgentFailure("AGENT_OWNER_MISMATCH")
                            jobs.writers.advance(state, before, digest_bytes(before), payload.writer)
                            jobs.writers.write(directory, state)
                            return WriterCommitBindingV1(epoch=writer.epoch, incarnation=writer.incarnation,
                                actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation)
                        grant = AssistantSnapshotGrant(project_id, proof_id, digest_bytes(candidate), writer_authority,
                            lambda: self.claim_boundary(project_id, payload, ticket))
                        projects.catalog.reserve_action(key, command)
                        jobs.publisher.reviewed_snapshot(project_id, digest_bytes(workspace), candidate, grant,
                            originals=originals, artifacts=projects.artifacts, images=images)
                    else:
                        projects.catalog.reserve_action(key, command)
                        projects.storage.save(candidate, originals, projects.artifacts, images,
                            before_workspace=lambda: self.claim_boundary(project_id, payload, ticket))
            except Exception:
                known = projects.catalog.actions(synchronize=True).get(key)
                if known is None:
                    self.settle_action(project_id, payload, "failed")
                    raise
                if known.get("commitKind") == "workspace":
                    jobs = getattr(projects, "background_jobs", None)
                    if jobs is not None and jobs.enabled:
                        jobs.publisher.recover(project_id)
                else:
                    raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None

    async def commit(self, project_id, payload):
        from asyncio import to_thread
        await to_thread(self._commit, project_id, payload)
        command = self.service.projects.catalog.actions().get(self.key(payload))
        if command is not None and command.get("commitKind") == "delete":
            await self.service.projects.drain_catalog_actions(run_id=command["runId"])
        return self.recover(project_id, payload)

    def settle_action(self, project_id, payload, status):
        def settle(values):
            value = next(item for item in values if (item.proposal.id, item.proposal.version) == (payload.proposal_id, payload.version))
            if value.approval is None:
                return value
            if value.approval.batch_id != self.key(payload):
                return value
            if value.proposal.state in {"applying", "outcome_unknown"}:
                value.proposal.state = "applied" if status in {"completed", "deleted"} else "outcome_unknown" if status in {"applying", "deleting", "cleanup_incomplete"} else "failed_before_commit"
                value.approval.phase = "receipt_stored" if value.proposal.state == "applied" else "commit_claimed" if value.proposal.state == "outcome_unknown" else "cancelled"
                value.proposal.reason = "Показанное действие выполнено." if value.proposal.state == "applied" else "Результат действия проверяется. Не повторяйте применение." if value.proposal.state == "outcome_unknown" else "Действие не выполнено. Вариант сохранён для просмотра."
                if (value.proposal.state == "failed_before_commit" and value.approval.acceptance_id not in value.revoked_acceptances
                        and len(value.revoked_acceptances) < 100):
                    value.revoked_acceptances.append(value.approval.acceptance_id)
            return value
        value = self.service.proposals.update(project_id, settle)
        if status not in {"applying", "deleting", "cleanup_incomplete"}:
            self.tickets.pop((project_id, self.key(payload)), None)
        return value

    def recover(self, project_id, payload, *, resume=False):
        projects = self.service.projects
        with projects.state_lock:
            key = self.key(payload)
            command = projects.catalog.actions(synchronize=True).get(key)
            if command is not None:
                accepted = command.get("accepted")
                expected = AssistantAcceptanceIdentityV1.model_validate(payload.model_dump(by_alias=True,
                    include={"schema_version", "protocol_version", "proposal_id", "version", "content_sha256", "acceptance_id"})).model_dump(mode="json", by_alias=True)
                if command.get("assistantProtocolVersion") != 1 or accepted != expected:
                    raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
                if command["commitKind"] == "delete" and command["status"] == "pending":
                    tombstoned = any(item.project_id == project_id and item.tombstoned for item in projects.storage.registry().entries)
                    command["status"] = "deleting" if tombstoned else "cancelled"
                    command["result"] = {"durable": False, "error": {"code": "AGENT_OUTCOME_UNKNOWN" if tombstoned else "AGENT_SAVE_FAILED"}}
                    projects.catalog.record_action(key, command)
                if command["status"] == "applying" and command["commitKind"] == "workspace":
                    reconcile_action(projects, key, command)
                    command = projects.catalog.actions()[key]
                proposal = AssistantProposalV1.model_validate(command["proposal"])
                deleted = command["commitKind"] == "delete" and command["status"] in {"deleted", "cleanup_incomplete", "deleting"}
                if deleted:
                    proposal.state = "applied" if command["status"] == "deleted" else "outcome_unknown"
                    proposal.reason = "Проект удалён." if command["status"] == "deleted" else "Удаление принято. Завершение очистки проверяется; не повторяйте действие."
                else:
                    try:
                        proposal = self.settle_action(project_id, payload, command["status"]).proposal
                    except AgentFailure:
                        if command["status"] not in {"completed", "failed", "cancelled"}:
                            raise
                        proposal.state = "applied" if command["status"] == "completed" else "failed_before_commit"
                    if command["status"] == "completed":
                        proposal.state, proposal.reason = "applied", "Показанное действие выполнено."
                result = command["result"]
                if command["status"] == "completed" and command["commitKind"] == "workspace":
                    try:
                        value = self.value(project_id, payload)
                    except AgentFailure:
                        value = None
                    if value is not None and value.action is not None and value.action.blob_base64 is not None:
                        blob = base64.b64decode(value.action.blob_base64, validate=True)
                        if value.action.request.action == "add_source_text":
                            resource = next(item for item in value.candidate.project.sources if item.id not in {old.id for old in value.baseline.project.sources})
                            projects.originals[project_id, resource.id] = blob
                        elif value.action.request.action == "import_asset":
                            resource = next(item for item in value.candidate.project.assets if item.id not in {old.id for old in value.baseline.project.assets})
                            projects.images[project_id, resource.id] = blob
                operation = AgentProjectOperation(id=key, projectId=project_id, runId=command["runId"], action=command["action"],
                    status=command["status"], durable=command["status"] in {"completed", "deleted"} and bool(result.get("durable")), downloadUrl=None,
                    errorCode=result.get("errorCode") or result.get("error", {}).get("code"))
                self.tickets.pop((project_id, key), None)
                return AssistantProjectActionResultV1(proposal=proposal, operation=operation, project=None if deleted else projects.response(project_id))
            value = self.value(project_id, payload)
            if value.approval is not None and value.approval.batch_id == key:
                ticket = self.tickets.get((project_id, key))
                if resume and ticket is not None and ticket[1] > self.service.leases.clock():
                    self.bound(value, payload)
                    self.current(project_id, value, payload.owner)
                    return AssistantProjectActionResultV1(proposal=value.proposal, operation=None, project=None,
                        claim=self.reply(payload, ticket[0], value.approval.expires_at, value.approval.request_sha256))
                value = self.settle_action(project_id, payload, "failed")
            elif resume:
                return self.cancel(project_id, payload)
            return AssistantProjectActionResultV1(proposal=value.proposal, operation=None, project=None)

    def cancel(self, project_id, payload):
        subject = self.signal_cancel(project_id, payload)
        with self.service.projects.state_lock:
            value = self.value(project_id, payload)
            if value.approval is not None and value.approval.batch_id == self.key(payload) and value.approval.phase != "accepted":
                return self.recover(project_id, payload)
            if value.approval is not None and value.approval.batch_id == self.key(payload):
                self.settle_action(project_id, payload, "failed")
            else:
                def revoke(values):
                    value = next(item for item in values if (item.proposal.id, item.proposal.version) == (payload.proposal_id, payload.version))
                    if payload.acceptance_id not in value.revoked_acceptances:
                        if len(value.revoked_acceptances) >= 100:
                            value.proposal.state = "discarded"
                        else:
                            value.revoked_acceptances.append(payload.acceptance_id)
                    return value
                self.service.proposals.update(project_id, revoke)
            reply = self.recover(project_id, payload)
        with self.revocation_lock:
            self.revocations.pop(subject, None)
        return reply

    def retry(self, project_id, payload):
        with self.service.projects.state_lock:
            value = self.value(project_id, payload)
            if (value.proposal.state != "failed_before_commit" or value.approval is None
                    or value.approval.acceptance_id == payload.acceptance_id or payload.acceptance_id in value.revoked_acceptances):
                raise AgentFailure("AGENT_TICKET_INVALID")
            if len(value.revoked_acceptances) >= 100:
                raise AgentFailure("AGENT_EDIT_LIMIT")
            self.current(project_id, value, payload.owner)
            def ready(values):
                value = next(item for item in values if (item.proposal.id, item.proposal.version) == (payload.proposal_id, payload.version))
                value.proposal.state = "ready"
                value.proposal.reason = "Действие проверено. Для выполнения нажмите «Применить»."
                return value
            return self.service.proposals.update(project_id, ready).proposal
