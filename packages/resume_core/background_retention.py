"""Bound private history without forgetting replay identity or unresolved authority."""

from .background_assets import elapsed, release_resolved_jobs
from .agent_store import digest
from .background_limits import LIMITS
from .background_store import BackgroundFailure, RESOLVED_PUBLICATION, TERMINAL_EXECUTION, expiration, job_in
from .project_store import owned_file, strict_json
from .storage import StorageFailure


def complete(job):
    return (job.execution in TERMINAL_EXECUTION and job.publication in RESOLVED_PUBLICATION
        and all(attempt.cleanup_verified for attempt in job.attempts))


class JobRetention:
    def __init__(self, jobs):
        self.jobs = jobs

    @staticmethod
    def pending_legacy(workspace, intent):
        return any(record.ready and record.action_id == intent.action_id and intent.steps_sha256 == digest([
            step.model_dump(mode="json", by_alias=True) for step in record.proposed_steps]) for record in workspace.sync_records)

    def compact_manual(self, project, history):
        from .models.template_publication import decode_canonical_candidate
        from .rich_project_store import RichProjectStore
        import hashlib
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            if project in self.jobs.fences or any(intent.phase not in {"receipt_stored", "reconciled"}
                    for intent in [*state.intents, *state.manual_intents]):
                return
            before = state.model_dump(by_alias=True)
            if state.manual_intents:
                current, checksum = RichProjectStore(self.jobs.root)._read_committed_unlocked(project, synchronize=True)
                history._ready(state, directory, checksum)
                for intent in list(state.manual_intents):
                    if any(inverse.command_ref == intent.candidate_ref for inverse in state.inverses):
                        continue
                    if intent.phase != "receipt_stored":
                        continue
                    path = directory / "canonical-candidates" / (intent.candidate_ref + ".json")
                    candidate = None
                    if not intent.candidate_pruned:
                        owned_file(path, LIMITS.sidecar_project_bytes)
                        raw = path.read_bytes()
                        if hashlib.sha256(raw).hexdigest() != intent.candidate_sha256:
                            continue
                        candidate = decode_canonical_candidate(strict_json(raw))
                        if candidate.manual_mutation is not None:
                            intent.action_id = candidate.manual_mutation.action_id
                            intent.steps_sha256 = digest([step.model_dump(mode="json", by_alias=True) for step in candidate.manual_mutation.steps])
                    proved = any(item.client_mutation_id == intent.client_mutation_id and item.request_sha256 == intent.request_sha256
                        for item in current.mutation_replay)
                    internal = candidate is not None and candidate.snapshot_write and intent.client_mutation_id.startswith("metadata_")
                    if not proved and not internal:
                        continue
                    if self.pending_legacy(current, intent):
                        intent.candidate_pruned = True
                    else:
                        state.manual_intents.remove(intent)
                    reference = str(path.relative_to(directory))
                    if not intent.candidate_pruned or path.exists():
                        state.cleanup_refs = sorted(set([*state.cleanup_refs, reference]))
            if state.model_dump(by_alias=True) != before:
                self.jobs._write(directory, state, self.jobs._all())
            cleanup = bool(state.cleanup_refs)
        if cleanup:
            self.sweep(project)

    def sweep(self, project):
        with self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            now, removed_files = self.jobs.clock(), []
            before = state.model_dump(by_alias=True)
            active = {intent.job_id for intent in state.intents if intent.phase not in {"receipt_stored", "reconciled"}}
            active.update(intent.history_job_id for intent in state.manual_intents if intent.history_job_id is not None
                and intent.phase not in {"receipt_stored", "reconciled"})
            from .models.assistant_artifacts import decode_assistant_artifact
            from .models.agent import TERMINAL_EDITS
            for job in state.jobs:
                if job.submission.input.kind != "agent_journal":
                    continue
                path = directory / "agent-artifacts" / (job.submission.input.id + ".json")
                if not path.exists():
                    continue
                owned_file(path, LIMITS.sidecar_project_bytes)
                artifact = decode_assistant_artifact(strict_json(path.read_bytes()))
                if any(item.batch.state not in TERMINAL_EDITS for item in getattr(artifact, "applications", [])):
                    active.add(job.id)
            folder = directory / "proposal-intents"
            if folder.exists():
                from .models.background import ProposalBindingV1
                for path in folder.glob("*.json"):
                    owned_file(path, LIMITS.proposal_bytes)
                    value = strict_json(path.read_bytes())
                    candidate = ProposalBindingV1.model_validate(value["candidate"])
                    if not any(proposal.id == candidate.id for proposal in state.proposals):
                        job = next((item for item in state.jobs if item.id == candidate.job_id), None)
                        if job is not None and job.publication not in {"discarded", "cancelled"}:
                            active.add(job.id)
            for inverse in list(state.inverses):
                closed = inverse.direction == "closed" and inverse.owner == "backend"
                if (inverse.owner == "transferring" or inverse.job_id in active
                        or not closed and elapsed(now, inverse.expires_at) < 0):
                    continue
                job = job_in(state, inverse.job_id)
                if not closed:
                    job.undo_expired = True
                job.event_cursor += 1
                state.asset_pins = [pin for pin in state.asset_pins if (pin.kind, pin.owner) != ("inverse", inverse.proposal_id)]
                state.inverses.remove(inverse)
            active_history = {item.job_id for item in state.inverses}
            state.history_commands = [item for item in state.history_commands if item.job_id in active_history
                or elapsed(now, item.completed_at) < LIMITS.inverse_seconds]
            retained_inverse = {item.job_id for item in state.inverses}
            current = None
            for intent in list(state.manual_intents):
                if intent.phase != "receipt_stored" or intent.resolved_at is None or elapsed(now, intent.resolved_at) < LIMITS.resolved_seconds:
                    continue
                if current is None:
                    from .rich_project_store import RichProjectStore
                    current = RichProjectStore(self.jobs.root)._read_committed_unlocked(project)[0]
                if self.pending_legacy(current, intent):
                    continue
                proved = any(item.client_mutation_id == intent.client_mutation_id and item.request_sha256 == intent.request_sha256
                    for item in current.mutation_replay)
                path = directory / "canonical-candidates" / (intent.candidate_ref + ".json")
                if intent.candidate_pruned:
                    if proved:
                        state.manual_intents.remove(intent)
                    continue
                owned_file(path, LIMITS.sidecar_project_bytes)
                import hashlib
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != intent.candidate_sha256:
                    continue
                value = strict_json(raw)
                if proved or value.get("snapshotWrite") is True and intent.client_mutation_id.startswith("metadata_"):
                    state.manual_intents.remove(intent)
                    removed_files.append(path)
            for job in list(state.jobs):
                if complete(job) and job.id not in active and elapsed(now, job.updated_at) >= LIMITS.resolved_seconds:
                    request = next(item for item in state.requests if item.job_id == job.id)
                    job.asset_pins_sha256 = None
                    request.archived_result = job.model_copy(deep=True)
                    state.jobs.remove(job)
                    state.asset_pins = [pin for pin in state.asset_pins if (pin.kind, pin.owner) != ("job", job.id)]
            if elapsed(now, state.request_epoch_expires_at) >= 0:
                state.expired_through_epoch = state.active_request_epoch
                state.active_request_epoch += 1
                state.request_epoch_expires_at = expiration(now, LIMITS.request_replay_seconds)
            state.fixed_invalidations = [item for item in state.fixed_invalidations
                if item.request_epoch > state.expired_through_epoch]
            for request in list(state.requests):
                job = job_in(state, request.job_id)
                if (not complete(job) or job.id in active or job.id in retained_inverse
                        or elapsed(now, request.expires_at) < 0 or request.identity.request_epoch > state.expired_through_epoch):
                    continue
                intents = [intent for intent in state.intents if intent.job_id == job.id]
                proposals = [proposal for proposal in state.proposals if proposal.job_id == job.id]
                for intent in intents:
                    removed_files.append(directory / "canonical-candidates" / (intent.candidate_ref + ".json"))
                for proposal in proposals:
                    removed_files.append(directory / "proposal-intents" / (proposal.id + ".json"))
                if job.submission.input.kind == "agent_journal":
                    removed_files.append(directory / "agent-artifacts" / (job.submission.input.id + ".json"))
                else:
                    removed_files.append(directory / "fixed-inputs" / (job.submission.input.id + ".json"))
                    if job.submission.kind == "processing":
                        removed_files.append(directory / "processing-candidates" / ("processing_" + job.submission.input.id[6:] + ".json"))
                removed_files.append(directory / "events" / (job.id + ".json"))
                state.intents = [intent for intent in state.intents if intent.job_id != job.id]
                state.proposals = [proposal for proposal in state.proposals if proposal.job_id != job.id]
                state.jobs = [item for item in state.jobs if item.id != job.id]
                state.requests.remove(request)
                state.asset_pins = [pin for pin in state.asset_pins if (pin.kind, pin.owner) != ("job", job.id)
                    and (pin.kind != "proposal" or pin.owner not in {proposal.id for proposal in proposals})]
            release_resolved_jobs(state)
            state.cleanup_refs = sorted(set(state.cleanup_refs) | {str(path.relative_to(directory)) for path in removed_files
                if path.exists() or path.is_symlink()})
            if state.model_dump(by_alias=True) != before:
                self.jobs._write(directory, state, self.jobs._all())
            try:
                for reference in list(state.cleanup_refs):
                    path = directory / reference
                    if path.exists() or path.is_symlink():
                        owned_file(path, LIMITS.sidecar_project_bytes)
                        path.unlink()
                        self.jobs._sync_namespace(path)
                    state.cleanup_refs.remove(reference)
                if state.cleanup_refs != before.get("cleanupRefs", []) or removed_files:
                    self.jobs._write(directory, state, self.jobs._all())
            except (OSError, StorageFailure):
                raise BackgroundFailure("JOB_STORE_UNAVAILABLE") from None
            return state

    def sweep_all(self):
        for project in self.jobs.snapshots():
            if project not in self.jobs.fences:
                self.sweep(project)
