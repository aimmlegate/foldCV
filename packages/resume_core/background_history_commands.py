"""Conditional compensation keeps exact command replay and one inverse owner."""

import hashlib

from .agent_store import digest
from .background_assets import pin_snapshot
from .background_history import digest_bytes
from .background_store import BackgroundFailure, job_in
from .models.background import (HistoryCommandReceiptV1, HistoryCommitBindingV1, WriterCommitBindingV1,
    WriterHistoryResultV1)
from .project_store import encoded


def command_hash(request):
    return digest({"jobId": request.job_id, "proposalId": request.proposal_id, "transferId": request.transfer_id,
        "commandId": request.command_id, "direction": request.direction})


def apply_history_receipt(state, candidate, canonical, completed_at):
    binding = candidate.history_binding
    if binding is None or candidate.inverse is None:
        raise BackgroundFailure("OUTCOME_UNKNOWN")
    known = next((item for item in state.history_commands if (item.job_id, item.command_id) == (binding.job_id, binding.command_id)), None)
    if known is not None:
        if known.command_sha256 != binding.command_sha256 or known.request_sha256 != candidate.request_sha256:
            raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
        return
    inverse = next((item for item in state.inverses if item.job_id == binding.job_id and item.proposal_id == binding.proposal_id), None)
    if (inverse is None or (inverse.transfer_id, inverse.direction, inverse.command_ref) !=
            (binding.transfer_id, binding.direction, binding.previous_ref)):
        raise BackgroundFailure("OUTCOME_UNKNOWN")
    raw = encoded(candidate.inverse.model_dump(mode="json", by_alias=True))
    inverse.command_ref = candidate.id
    inverse.command_inverse_sha256, inverse.command_inverse_bytes = hashlib.sha256(raw).hexdigest(), len(raw)
    inverse.direction = "redo" if binding.direction == "undo" else "undo"
    inverse.guards = candidate.inverse_guards.model_copy(deep=True)
    pin_snapshot(state, canonical, candidate.workspace, "inverse", inverse.proposal_id, extend=True)
    state.history_commands.append(HistoryCommandReceiptV1(jobId=binding.job_id, proposalId=binding.proposal_id,
        commandId=binding.command_id, commandSha256=binding.command_sha256, clientMutationId=candidate.client_mutation_id,
        requestSha256=candidate.request_sha256, resultingRevision=candidate.workspace.project_revision,
        candidateRef=candidate.id, completedAt=completed_at))
    job = job_in(state, binding.job_id)
    job.event_cursor += 1
    job.updated_at = completed_at


class WriterCommands:
    def validate_history_binding(self, state, directory, workspace, binding):
        from .background_history_owner import at_expiry
        inverse = next((item for item in state.inverses if item.job_id == binding.job_id and item.proposal_id == binding.proposal_id), None)
        writer = state.writer
        if (inverse is None or writer is None or inverse.owner != "session"
                or (inverse.writer_epoch, inverse.incarnation) != (writer.epoch, writer.incarnation)
                or (inverse.transfer_id, inverse.direction, inverse.command_ref) !=
                    (binding.transfer_id, binding.direction, binding.previous_ref)):
            raise BackgroundFailure("WRITER_UNKNOWN")
        if at_expiry(self.jobs.clock(), inverse.expires_at):
            raise BackgroundFailure("REQUEST_EXPIRED")
        self.history.validate(state, directory, workspace, inverse.guards)

    def command_proof(self, state, directory, workspace, receipt):
        def matches(candidate):
            return any(item.client_mutation_id == receipt.client_mutation_id and item.request_sha256 == receipt.request_sha256
                and item.resulting_revision == receipt.resulting_revision for item in candidate.mutation_replay)
        if matches(workspace):
            return
        intent = next((item for item in state.manual_intents if item.candidate_ref == receipt.candidate_ref
            and item.phase == "receipt_stored" and not item.candidate_pruned), None)
        if intent is None:
            raise BackgroundFailure("REQUEST_EXPIRED")
        candidate = self.coordinator._load_candidate(state, directory, intent)
        if not matches(candidate.workspace) or candidate.history_binding is None or candidate.history_binding.command_sha256 != receipt.command_sha256:
            raise BackgroundFailure("OUTCOME_UNKNOWN")

    def history_command(self, project, request, *, originals=None, artifacts=None, images=None):
        logical_sha = command_hash(request)
        with self.guard(project) as (directory, state, workspace, checksum):
            self.require(state, request.proof, recovery=True, expired=True)
            known = next((item for item in state.history_commands if (item.job_id, item.command_id) == (request.job_id, request.command_id)), None)
            if known is not None:
                if known.command_sha256 != logical_sha:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                self.command_proof(state, directory, workspace, known)
                return WriterHistoryResultV1(schemaVersion=1, view=self.view(state, workspace, checksum), receipt=known, replayed=True)
            writer = self.require(state, request.proof)
            job, inverse, _original, mutation = self.history_material(directory, state, request, workspace)
            binding = HistoryCommitBindingV1(jobId=job.id, proposalId=inverse.proposal_id,
                transferId=inverse.transfer_id, direction=request.direction, previousRef=inverse.command_ref,
                commandId=request.command_id, commandSha256=logical_sha)
            self.validate_history_binding(state, directory, workspace, binding)
            command = mutation.model_copy(deep=True)
            command.client_mutation_id = "history_" + digest([state.lineage, job.id, request.command_id])[:40]
            command.action_id, command.kind = command.client_mutation_id, request.direction
            command.capture.session_id = writer.session_id
            command.capture.action_id, command.capture.action_token = command.action_id, 0
            command.capture.dependencies = []
        def authorize(current, before, owned_directory):
            self.require(current, request.proof)
            self.advance(current, before, digest_bytes(before), request)
            self.validate_history_binding(current, owned_directory, before, binding)
            self.write(owned_directory, current)
            writer = current.writer
            return WriterCommitBindingV1(epoch=writer.epoch, incarnation=writer.incarnation,
                actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation)
        self.coordinator.manual(project, command, authorize=authorize, history_binding=binding,
            originals=originals, artifacts=artifacts, images=images)
        with self.guard(project) as (directory, state, workspace, checksum):
            receipt = next((item for item in state.history_commands if (item.job_id, item.command_id) == (request.job_id, request.command_id)), None)
            if receipt is None:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            self.command_proof(state, directory, workspace, receipt)
            return WriterHistoryResultV1(schemaVersion=1, view=self.view(state, workspace, checksum), receipt=receipt, replayed=False)
