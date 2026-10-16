"""Transfer one guarded inverse between the journal and a verified writer."""

import hashlib
from datetime import datetime

from .background_retention import JobRetention
from .background_history_commands import WriterCommands
from .background_store import BackgroundFailure, identity, job_in
from .models.background import WriterHistoryOfferV1
from .project_store import encoded
from .rich_api import RichProjectResponse
from .rich_identity import resume_identity
from .rich_mutations import apply_rich_mutation
from .rich_presentation import presentation
from .rich_project_store import rich_snapshot_bytes


def project_response(workspace, *, durable):
    return RichProjectResponse(workspace=workspace, durability="durable" if durable else "pending",
        savedProjectRevision=workspace.project_revision if durable else None,
        savedDocumentRevision=workspace.document_revision if durable else None, saveError=None, generation=None,
        identity=resume_identity(workspace), presentation=presentation(workspace.project.document, workspace.project.facts))


def close_redo(state, now):
    for inverse in state.inverses:
        if inverse.direction == "redo":
            inverse.direction, inverse.owner = "closed", "backend"
            inverse.writer_epoch, inverse.incarnation = None, None
            inverse.transfer_id = identity("transfer")
            job = job_in(state, inverse.job_id)
            job.event_cursor += 1
            job.updated_at = now


class WriterHistory(WriterCommands):
    def drop_redo(self, state):
        close_redo(state, self.jobs.clock())

    def return_history(self, state, writer):
        if any(intent.phase not in {"receipt_stored", "reconciled"} for intent in [*state.intents, *state.manual_intents]):
            return
        for inverse in state.inverses:
            if inverse.owner in {"session", "transferring"} and (inverse.writer_epoch, inverse.incarnation) == (writer.epoch, writer.incarnation):
                inverse.owner, inverse.writer_epoch, inverse.incarnation = "backend", None, None
                inverse.transfer_id = identity("transfer")
                job = job_in(state, inverse.job_id)
                job.event_cursor += 1
                job.updated_at = self.jobs.clock()

    def history_owner(self, state, request):
        job = job_in(state, request.job_id)
        inverse = next((item for item in state.inverses if item.job_id == job.id and item.proposal_id == request.proposal_id), None)
        if job.receipt is None or job.proposal_id != request.proposal_id or inverse is None or inverse.direction == "closed":
            raise BackgroundFailure("JOB_NOT_FOUND")
        if inverse.transfer_id != request.transfer_id:
            raise BackgroundFailure("WRITER_UNKNOWN")
        if inverse.owner != "transferring" and at_expiry(self.jobs.clock(), inverse.expires_at):
            raise BackgroundFailure("REQUEST_EXPIRED")
        return job, inverse

    def history_material(self, directory, state, request, workspace):
        job, inverse = self.history_owner(state, request)
        intent = next((item for item in state.intents if item.job_id == job.id and item.phase == "receipt_stored"), None)
        if intent is None:
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        original = self.coordinator._load_candidate(state, directory, intent)
        if self.coordinator._receipt_value(original, job.receipt.persisted_at) != job.receipt:
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        active = original
        if inverse.command_ref is not None:
            command = next((item for item in state.manual_intents if item.candidate_ref == inverse.command_ref
                and item.phase == "receipt_stored"), None)
            if command is None:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            active = self.coordinator._load_candidate(state, directory, command)
        mutation = active.inverse
        if (mutation is None or active.inverse_guards != inverse.guards
                or hashlib.sha256(encoded(mutation.model_dump(mode="json", by_alias=True))).hexdigest() !=
                    (inverse.command_inverse_sha256 or inverse.inverse_sha256)
                or len(encoded(mutation.model_dump(mode="json", by_alias=True))) != (inverse.command_inverse_bytes or inverse.inverse_bytes)):
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        self.history.validate(state, directory, workspace, inverse.guards)
        return job, inverse, original, mutation

    def history_offer(self, project, request):
        JobRetention(self.jobs).sweep(project)
        with self.guard(project) as (directory, state, workspace, checksum):
            self.require(state, request.proof, recovery=True)
            job, inverse, original, mutation = self.history_material(directory, state, request, workspace)
            preview = mutation.model_copy(deep=True)
            preview.client_mutation_id = "preview_" + inverse.transfer_id
            try:
                proposed, _duplicate = apply_rich_mutation(workspace, preview)
            except ValueError:
                raise BackgroundFailure("DEPENDENCY_CHANGED") from None
            proposal = next(item for item in state.proposals if item.id == job.proposal_id)
            return WriterHistoryOfferV1(schemaVersion=1, view=self.view(state, workspace, checksum), job=job,
                proposal=proposal, saved=project_response(original.workspace, durable=True),
                preview=project_response(proposed, durable=False), ownership=inverse,
                savedWire=rich_snapshot_bytes(original.workspace).decode(),
                mutationWire=encoded(mutation.model_dump(mode="json", by_alias=True)).decode(),
                batchId=proposal.payload.batch_id if proposal.payload.kind == "agent_journal" else None)

    def begin_history_transfer(self, project, request):
        with self.guard(project) as (directory, state, workspace, checksum):
            writer = self.advance(state, workspace, checksum, request)
            job, inverse, _original, _mutation = self.history_material(directory, state, request, workspace)
            if inverse.owner in {"session", "transferring"}:
                if (inverse.writer_epoch, inverse.incarnation) != (writer.epoch, writer.incarnation):
                    raise BackgroundFailure("WRITER_UNKNOWN")
                self.write(directory, state)
                return inverse.model_copy(deep=True)
            if inverse.owner != "backend":
                raise BackgroundFailure("WRITER_UNKNOWN")
            self.observer("before_undo_owner_transfer_prepared", project)
            inverse.owner, inverse.writer_epoch, inverse.incarnation = "transferring", writer.epoch, writer.incarnation
            job.event_cursor += 1
            job.updated_at = self.jobs.clock()
            self.write(directory, state)
            self.observer("undo_owner_transfer_prepared", project)
            return inverse.model_copy(deep=True)

    def acknowledge_history_transfer(self, project, request):
        with self.guard(project) as (directory, state, workspace, checksum):
            writer = self.advance(state, workspace, checksum, request)
            job, inverse = self.history_owner(state, request)
            if inverse.owner not in {"transferring", "session"} or (inverse.writer_epoch, inverse.incarnation) != (writer.epoch, writer.incarnation):
                raise BackgroundFailure("WRITER_UNKNOWN")
            if inverse.owner == "transferring":
                self.observer("before_undo_owner_transfer", project)
                inverse.owner = "session"
                job.event_cursor += 1
                job.updated_at = self.jobs.clock()
                self.write(directory, state)
                self.observer("undo_owner_transfer", project)
            else:
                self.write(directory, state)
            return inverse.model_copy(deep=True)


def at_expiry(now, deadline):
    return datetime.fromisoformat(now.replace("Z", "+00:00")) >= datetime.fromisoformat(deadline.replace("Z", "+00:00"))
