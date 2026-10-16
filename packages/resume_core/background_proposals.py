"""Accept one payload reference per turn without borrowing a native capability's life."""

from __future__ import annotations

import asyncio
import hashlib

from .background_limits import LIMITS
from .background_store import BackgroundFailure, job_in
from .models.background import DeferredApplyV2, JobFailure, ProposalBindingV1
from .project_store import encoded, owned_file, strict_json
from .storage import atomic_write, private_directory


class JobProposals:
    def __init__(self, supervisor, payload_loader):
        self.supervisor = supervisor
        self.store = supervisor.store
        self.payload_loader = payload_loader
        self.tasks = {}

    def _live(self, control):
        if (self.supervisor.controls.get(control.job.id) is not control or self.supervisor.active is not control
                or control.revoked or control.cancel.is_set() or not control.ready.is_set()):
            raise BackgroundFailure("CANCELLED")
        if not control.job.submission.allow_edits:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        if control.active_deadline is None or self.supervisor.clock.now() >= control.active_deadline:
            raise BackgroundFailure("DEADLINE")
        if control.stage != len(control.job.submission.models) - 1:
            raise BackgroundFailure("JOB_SCOPE_INVALID")

    async def accept(self, control, candidate: ProposalBindingV1, *, needs_review=False):
        self._live(control)
        existing = self.tasks.get(control.job.id)
        if existing is not None:
            original, task = existing
            if (candidate.id, candidate.payload_sha256, candidate.payload) != (original.id, original.payload_sha256, original.payload):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            return await asyncio.shield(task)
        snapshot = candidate.model_copy(deep=True)
        task = asyncio.create_task(self._accept(control, snapshot, needs_review))
        self.tasks[control.job.id] = (snapshot, task)
        return await asyncio.shield(task)

    async def _accept(self, control, candidate, needs_review):
        self._live(control)
        project = control.job.submission.identity.project_id
        payload = self.payload_loader(candidate.payload)
        if (not isinstance(payload, bytes) or not payload or len(payload) > LIMITS.proposal_bytes
                or len(payload) != candidate.payload_bytes or hashlib.sha256(payload).hexdigest() != candidate.payload_sha256):
            raise BackgroundFailure("PROTOCOL")
        await self.supervisor.observer("before_payload_stored", control.job.id)
        with self.store.guard(project) as directory:
            state = self.store._read(project, directory)
            job = job_in(state, control.job.id)
            if (candidate.job_id != job.id or candidate.project_id != project or candidate.lineage != state.lineage
                    or candidate.account_generation != job.submission.account_generation
                    or candidate.account_generation != self.store._read_dispatch(self.store.background / "dispatch.json").account_generation
                    or candidate.execution_generation != job.execution_generation or candidate.scope != job.submission.scope
                    or candidate.authority != "active" or candidate.revocation is not None):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            if job.proposal_id is not None:
                old = next((p for p in state.proposals if p.id == job.proposal_id), None)
                if old is None or old.id != candidate.id or old.payload_sha256 != candidate.payload_sha256 or old.payload != candidate.payload:
                    raise BackgroundFailure("JOB_SCOPE_INVALID")
                return self.result(job)
            expected_kind = {"agent": "agent_journal", "processing": "processing", "rewrite": "rich_sync",
                "reconciliation": "rich_sync"}[job.submission.kind]
            if candidate.payload.kind != expected_kind:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            folder = private_directory(directory / "proposal-intents")
            path = folder / (candidate.id + ".json")
            intent = {"schemaVersion": 1, "phase": "payload_stored", "candidate": candidate.model_dump(mode="json", by_alias=True)}
            raw = encoded(intent)
            if path.exists():
                owned_file(path, LIMITS.proposal_bytes)
                previous = strict_json(path.read_bytes())
                if previous != intent:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
            self.store._capacity(state, self.store._all(), replacing=(path, len(raw)))
            atomic_write(path, raw)
            self.store._sync_namespace(path)
            accepted_elapsed = self.supervisor.clock.now()
            accepted_at = self.store.clock()
        if accepted_elapsed >= control.active_deadline:
            raise BackgroundFailure("DEADLINE")
        await self.supervisor.observer("payload_stored", control.job.id)
        accepted = candidate.model_dump(by_alias=True)
        accepted["acceptedAt"] = accepted_at
        accepted = ProposalBindingV1.model_validate(accepted)
        await self.supervisor.observer("before_binding_stored", control.job.id)

        def bind(state, job):
            current_account = self.store._read_dispatch(self.store.background / "dispatch.json").account_generation
            if (control.publication_revoked or job.publication == "cancelled" or state.tombstoned
                    or current_account != accepted.account_generation or state.account_generation != current_account):
                raise BackgroundFailure("CANCELLED")
            if job.proposal_id is not None:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            job.proposal_id = accepted.id
            job.publication = "needs_review" if needs_review else "waiting_for_sync"
            if needs_review:
                job.publication_error = JobFailure(code="DEPENDENCY_CHANGED")
            state.proposals.append(accepted)
        control.job = self.store.update(project, control.job.id, bind)
        await self.supervisor.observer("binding_stored", control.job.id)
        await self.supervisor.observer("proposal_durable", control.job.id)
        control.job = self.store.read(project, control.job.id)
        await self.supervisor._emit(control.job)
        return self.result(control.job)

    @staticmethod
    def result(job):
        if job.publication not in {"waiting_for_sync", "needs_review"} or job.proposal_id is None:
            raise BackgroundFailure("CANCELLED")
        return DeferredApplyV2(schemaVersion=2, disposition=job.publication, jobId=job.id,
            proposalId=job.proposal_id, proposalStored=True, durable=False,
            reason="DEPENDENCY_CHANGED" if job.publication == "needs_review" else "WRITER_UNKNOWN")

    async def shutdown(self):
        if self.tasks:
            await asyncio.gather(*(task for _, task in self.tasks.values()), return_exceptions=True)
