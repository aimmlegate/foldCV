"""Retain compact publication proof separately from current canonical state."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime

from .background_limits import LIMITS
from .background_store import BackgroundFailure, expiration
from .canonical_patch import apply_patch, build_patch
from .models.template_delta import TemplatePreparedEditDeltaV1
from .models.template_writer import PreparedCommitProofV2, WriterPreparedSaveAckV2, WriterPreparedSaveRecoveryV2
from .rich_mutations import mutation_sha256
from .templates.compiler import canonical, sha256
from .templates.presentation import snapshot_identity


def deadline_passed(now, deadline):
    return datetime.fromisoformat(now.replace('Z', '+00:00')) >= datetime.fromisoformat(deadline.replace('Z', '+00:00'))


class TemplateCommitProofs:
    def prepare_commit(self, owner, state, before, after, candidate, request, history_opening):
        opening = self.opening(state)
        entry = opening.entries.get(request.mutation.client_mutation_id) if opening is not None else None
        if entry is None:
            return
        prepared = self.read(state, before, entry)
        if isinstance(prepared, TemplatePreparedEditDeltaV1):
            original = before.model_dump(mode='json', by_alias=True)
            if sha256(canonical(original)) != prepared.base_workspace_sha256:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            preview = apply_patch(original, prepared.workspace_patch)
            prepared_hash = prepared.result_workspace_sha256
            prepared_snapshot = prepared.result_snapshot
        else:
            preview = prepared.preview.workspace.model_dump(mode='json', by_alias=True)
            prepared_hash = sha256(canonical(preview))
            prepared_snapshot = prepared.preview.snapshot
        committed = after.model_dump(mode='json', by_alias=True)
        replay = next((item for item in after.mutation_replay if item.client_mutation_id == request.mutation.client_mutation_id), None)
        if (sha256(canonical(preview)) != prepared_hash or prepared_snapshot != snapshot_identity(after)
                or {key: value for key, value in preview.items() if key != 'updatedAt'}
                    != {key: value for key, value in committed.items() if key != 'updatedAt'}
                or replay is None or replay.request_sha256 != entry.mutation_hash or candidate.writer_binding is None):
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        planned_history = deepcopy(history_opening)
        owner.local_history._finish(planned_history, request.mutation.client_mutation_id,
            planned_history.pending[request.mutation.client_mutation_id], candidate)
        metadata = owner.view(state, after, candidate.after_workspace_sha256).response
        proof = PreparedCommitProofV2(clientMutationId=request.mutation.client_mutation_id,
            preparationRequestHash=entry.request_hash, mutationSha256=entry.mutation_hash, replay=replay,
            commitBinding=candidate.writer_binding, preparedWorkspaceSha256=prepared_hash,
            committedSnapshot=prepared_snapshot, committedWorkspaceSha256=candidate.after_workspace_sha256,
            commitPatch=build_patch(preview, committed),
            localHistoryAck=owner._history_ack(planned_history, request.mutation.action_id),
            committedIdentity=metadata.identity, committedGeneration=metadata.generation)
        raw = canonical(proof)
        if len(raw) > LIMITS.proposal_bytes:
            raise BackgroundFailure('JOB_STORAGE_FULL')
        updated = replace(entry, commit_proof=raw,
            proof_expires_at=expiration(self.jobs.clock(), LIMITS.inverse_seconds), committed=False)
        prospective = replace(opening, entries={**opening.entries, request.mutation.client_mutation_id: updated})
        self.jobs._capacity(state, self.jobs._all(), retained_usage={self.usage_key: self.usage(replacing=prospective)})
        self.openings[state.project_id] = prospective

    @staticmethod
    def verify_commit(entry, workspace, mutation):
        if entry.commit_proof is None:
            if not entry.committed:
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            return
        try:
            proof = PreparedCommitProofV2.model_validate_json(entry.commit_proof)
            replay = next(item for item in workspace.mutation_replay if item.client_mutation_id == mutation.client_mutation_id)
            if (proof.preparation_request_hash != entry.request_hash or proof.mutation_sha256 != entry.mutation_hash
                    or proof.mutation_sha256 != mutation_sha256(mutation) or proof.replay != replay):
                raise ValueError('retained proof differs from committed mutation')
        except (ValueError, StopIteration):
            raise BackgroundFailure('OUTCOME_UNKNOWN') from None

    def compact_response(self, state, workspace, checksum, request, replayed):
        opening = self.opening(state)
        entry = opening.entries.get(request.mutation.client_mutation_id) if opening is not None else None
        if entry is None or not entry.committed or request.preparation is None:
            raise BackgroundFailure('REQUEST_EXPIRED')
        if (entry.request_hash != request.preparation.request_hash or entry.mutation_hash != mutation_sha256(request.mutation)):
            raise BackgroundFailure('JOB_IDEMPOTENCY_CONFLICT')
        self.verify_commit(entry, workspace, request.mutation)
        replay = next((item for item in workspace.mutation_replay if item.client_mutation_id == request.mutation.client_mutation_id), None)
        if replay is None or replay.request_sha256 != entry.mutation_hash:
            raise BackgroundFailure('REQUEST_EXPIRED')
        if entry.commit_proof is not None and (entry.proof_expires_at is None or deadline_passed(self.jobs.clock(), entry.proof_expires_at)):
            entry = replace(entry, commit_proof=None, proof_expires_at=None)
            opening.entries[request.mutation.client_mutation_id] = entry
        common = dict(schemaVersion=2, writer=state.writer.model_copy(deep=True), clientMutationId=request.mutation.client_mutation_id,
            preparationRequestHash=entry.request_hash, mutationSha256=entry.mutation_hash, replay=replay,
            currentCanonicalRevision=workspace.project_revision, currentCanonicalSha256=checksum)
        if entry.commit_proof is None:
            return WriterPreparedSaveRecoveryV2(**common, kind='committed_recovery_required', reason='compact_commit_proof_expired')
        proof = PreparedCommitProofV2.model_validate_json(entry.commit_proof)
        return WriterPreparedSaveAckV2(**{**proof.model_dump(by_alias=True), **common}, kind='committed', replayed=replayed,
            currentEqualsCommitted=(workspace.project_revision, checksum)
                == (proof.committed_snapshot.project_revision, proof.committed_workspace_sha256))

    def rollback_commit_unpublished(self, owner, mutation):
        try:
            with owner.coordinator._writer(mutation.project_id), self.jobs.guard(mutation.project_id) as directory:
                state = self.jobs._read(mutation.project_id, directory)
                workspace, _checksum = owner.coordinator.canonical._read_committed_unlocked(mutation.project_id)
                if (any(item.client_mutation_id == mutation.client_mutation_id for item in state.manual_intents)
                        or any(item.client_mutation_id == mutation.client_mutation_id for item in workspace.mutation_replay)):
                    return
                opening = self.opening(state)
                entry = opening.entries.get(mutation.client_mutation_id) if opening is not None else None
                if entry is not None and not entry.committed and entry.mutation_hash == mutation_sha256(mutation):
                    opening.entries[mutation.client_mutation_id] = replace(entry, commit_proof=None, proof_expires_at=None)
        except Exception:
            # Unknown publication state must keep the original proof reservation.
            return
