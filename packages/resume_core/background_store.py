"""Private job authority, separate from canonical resumes and artifact payloads."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import secrets
import re

from . import agent_limits
from .background_limits import LIMITS, background_global_bytes, background_project_bytes
from .models.background import BackgroundSidecarV1, DispatchStateV1, JobFailure, JobSnapshotV1, JobSubmissionV1, RequestReplayV1
from .project_repository import RepositoryFailure as BackgroundFailure
from .project_store import ProjectStore, ProjectStoreFailure, SAFE_ID, encoded, owned_file, strict_json
from .storage import StorageFailure, atomic_write, locked_root, private_directory

TERMINAL_EXECUTION = frozenset({"completed", "failed", "cancelled", "interrupted"})
RESOLVED_PUBLICATION = frozenset({"none", "saved", "no_change", "discarded", "cancelled"})


@dataclass(frozen=True)
class RetainedUsage:
    draft_bytes: int = 0
    owned_bytes: int = 0
    records: int = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity(prefix: str) -> str:
    return prefix + "_" + secrets.token_hex(12)


def expiration(now: str, seconds: int) -> str:
    return (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(seconds=seconds)).isoformat()


def job_in(state: BackgroundSidecarV1, job_id: str) -> JobSnapshotV1:
    result = next((job for job in state.jobs if job.id == job_id), None)
    if result is None:
        result = next((request.archived_result for request in state.requests if request.job_id == job_id
            and request.archived_result is not None), None)
    if result is None:
        raise BackgroundFailure("JOB_NOT_FOUND")
    return result


def records(state: BackgroundSidecarV1) -> int:
    return (sum(len(getattr(state, key)) for key in ("jobs", "requests", "proposals", "drafts", "generations", "intents", "inverses", "manual_intents", "asset_pins", "orphan_assets", "cleanup_refs", "writer_touches", "history_commands", "fixed_invalidations"))
        + len(state.template_authorizations) + int(state.writer is not None) + int(state.barrier is not None)
        + (1 + len(state.history.definitions) if state.history is not None else 0))


def claimed(state, job_id):
    return any(intent.job_id == job_id and intent.phase not in {"intent_stored", "reconciled", "receipt_stored"}
        for intent in state.intents)


class JobStore:
    def __init__(self, root: Path, *, clock=utc_now):
        self.root = root
        self.background = root / "background"
        self.projects = self.background / "projects"
        self.canonical = ProjectStore(root)
        self.clock = clock
        self.fences: dict[str, str] = {}
        self.fixed_sizes = {}
        self.fixed_unknown = set()
        self.usage_providers = {}
        self.state_observers = {}

    @contextmanager
    def guard(self, project_id: str, *, deleted=False):
        if SAFE_ID.fullmatch(project_id) is None:
            raise BackgroundFailure("JOB_NOT_FOUND")
        try:
            with locked_root(self.root, ".projects.lock"):
                entry = next((item for item in self.canonical._registry().entries if item.project_id == project_id), None)
                if entry is None:
                    raise BackgroundFailure("JOB_NOT_FOUND")
                if entry.tombstoned and not deleted:
                    raise BackgroundFailure("PROJECT_DELETED")
                if deleted and not entry.tombstoned:
                    raise BackgroundFailure("JOB_SCOPE_INVALID")
                if not deleted:
                    self.canonical._directory(project_id)
                with locked_root(self.background, ".jobs.lock"):
                    private_directory(self.projects)
                    directory = self.projects / project_id
                    if directory.is_symlink():
                        raise StorageFailure("UNSAFE_STORAGE")
                    yield directory
        except BackgroundFailure:
            raise
        except (StorageFailure, ProjectStoreFailure, OSError, ValueError):
            raise BackgroundFailure("JOB_STORE_UNAVAILABLE") from None

    def _read(self, project_id: str, directory: Path) -> BackgroundSidecarV1:
        try:
            owned_file(directory / "state.json", LIMITS.sidecar_project_bytes)
            state = BackgroundSidecarV1.model_validate(strict_json((directory / "state.json").read_bytes()))
            if state.project_id != project_id:
                raise ValueError("foreign job namespace")
            self._validate_bindings(state)
            for observe in self.state_observers.values():
                observe(state)
            return state
        except (OSError, StorageFailure, ValueError, RecursionError):
            self.fences[project_id] = "JOB_STORE_CORRUPT"
            raise BackgroundFailure("JOB_STORE_CORRUPT") from None

    @staticmethod
    def _validate_bindings(state):
        jobs = {job.id: job for job in state.jobs}
        archived = {request.job_id: request.archived_result for request in state.requests if request.archived_result is not None}
        from .agent_store import digest
        for kind, owners in (("job", {**jobs, **archived}), ("inverse", {item.proposal_id: item for item in state.inverses}),
                ("draft", {item.id: item for item in state.drafts})):
            pins = {pin.owner: pin for pin in state.asset_pins if pin.kind == kind}
            for identifier, owner in owners.items():
                if owner.asset_pins_sha256 is not None and (identifier not in pins or digest([
                        ref.model_dump(mode="json", by_alias=True) for ref in pins[identifier].references]) != owner.asset_pins_sha256):
                    raise ValueError("missing or changed asset ownership")
            if kind != "draft" and pins.keys() - owners.keys():
                raise ValueError("orphan asset owner")
        for request in state.requests:
            if request.archived_result is None and (request.job_id not in jobs or
                    request.identity != jobs[request.job_id].submission.identity):
                raise ValueError("orphan request authority")
        proposals = {proposal.id: proposal for proposal in state.proposals}
        if len(proposals) != len(state.proposals) or len({proposal.job_id for proposal in state.proposals}) != len(state.proposals):
            raise ValueError("duplicate proposal authority")
        for proposal in state.proposals:
            job = jobs.get(proposal.job_id) or archived.get(proposal.job_id)
            if (job is None or job.proposal_id != proposal.id or proposal.scope != job.submission.scope
                    or proposal.account_generation != job.submission.account_generation
                    or proposal.execution_generation != job.execution_generation
                    or proposal.payload.kind != job.submission.input.kind or job.publication == "none"
                    or job.publication in {"cancelled", "discarded"} and proposal.authority != "revoked"
                    or job.publication not in RESOLVED_PUBLICATION and proposal.authority != "active" and not claimed(state, job.id)
                    or proposal.payload.kind == "agent_journal" and proposal.payload.run_id != job.id
                    or job.receipt is not None and job.receipt.proposal_sha256 != proposal.payload_sha256):
                raise ValueError("proposal authority does not match its Job")
        for job in state.jobs:
            if job.submission.protocol == 'template_import_v1':
                if job.proposal_id is not None:
                    raise ValueError('template application publication has no worker proposal authority')
                if job.template_outcome is not None and job.template_outcome.state == 'saved':
                    proof = next((intent for intent in state.manual_intents if intent.id == job.template_outcome.intent_id), None)
                    if (proof is None or proof.phase != 'receipt_stored' or proof.project_id != job.submission.identity.project_id
                            or proof.template_finalization is None or proof.template_finalization.operation_id != job.submission.input.id
                            or proof.after_workspace_sha256 != job.template_outcome.workspace_hash
                            or not any(value.operation_id == proof.template_finalization.operation_id
                                and value.authorization_id == proof.template_finalization.authorization_id
                                for value in state.template_authorizations)):
                        raise ValueError('template saved outcome lacks its exact typed publication intent')
            elif job.publication not in RESOLVED_PUBLICATION and job.proposal_id not in proposals:
                raise ValueError("unresolved publication has no proposal authority")
        intents = [*state.intents, *state.manual_intents]
        if (len({intent.id for intent in intents}) != len(intents)
                or len({intent.client_mutation_id for intent in state.manual_intents}) != len(state.manual_intents)):
            raise ValueError("duplicate canonical intent authority")
        active = [intent.job_id for intent in state.intents if intent.phase != "reconciled"]
        if len(set(active)) != len(active):
            raise ValueError("one job cannot own two canonical candidates")
        for intent in state.intents:
            job = jobs.get(intent.job_id) or archived.get(intent.job_id)
            proposal = proposals.get(intent.proposal_id)
            if (job is None or proposal is None or job.proposal_id != proposal.id or proposal.job_id != job.id
                    or intent.phase == "receipt_stored" and job.receipt is None
                    or job.receipt is not None and intent.phase == "receipt_stored" and (
                        job.receipt.client_mutation_id != intent.client_mutation_id or
                        job.receipt.request_sha256 != intent.request_sha256 or
                        job.receipt.workspace_sha256 != intent.after_workspace_sha256 or
                        job.receipt.generations_sha256 != intent.after_generations_sha256)):
                raise ValueError("canonical intent does not match its Job")
        if len({item.proposal_id for item in state.inverses}) != len(state.inverses):
            raise ValueError("duplicate inverse ownership")
        for inverse in state.inverses:
            job = jobs.get(inverse.job_id) or archived.get(inverse.job_id)
            if (job is None or job.receipt is None or job.proposal_id != inverse.proposal_id
                    or not any(intent.job_id == job.id and intent.proposal_id == inverse.proposal_id
                        and intent.candidate_ref == inverse.inverse_ref and intent.phase == "receipt_stored"
                        for intent in state.intents)):
                raise ValueError("inverse ownership needs its exact saved Job")
            if inverse.command_ref is not None and not any(item.candidate_ref == inverse.command_ref
                    and item.phase == "receipt_stored" for item in state.manual_intents):
                raise ValueError("active compensation needs its durable manual candidate")
        for command in state.history_commands:
            job = jobs.get(command.job_id) or archived.get(command.job_id)
            if job is None or job.receipt is None or job.proposal_id != command.proposal_id:
                raise ValueError("history command needs its exact saved Job")

    def _all(self) -> dict[str, BackgroundSidecarV1]:
        result = {}
        for directory in sorted(self.projects.iterdir()):
            if directory.is_symlink() or not directory.is_dir() or SAFE_ID.fullmatch(directory.name) is None:
                raise BackgroundFailure("JOB_STORE_CORRUPT")
            try:
                result[directory.name] = self._read(directory.name, directory)
            except BackgroundFailure:
                self.fences[directory.name] = "JOB_STORE_CORRUPT"
        return result

    @staticmethod
    def _reserved_bytes(state: BackgroundSidecarV1) -> int:
        return sum(agent_limits.TERMINAL_BYTES for job in state.jobs
            if job.execution not in TERMINAL_EXECUTION or job.publication not in RESOLVED_PUBLICATION)

    def _extra_bytes(self, project_id: str, *, excluding: Path | None = None) -> int:
        directory = self.projects / project_id
        if not directory.exists():
            return 0
        total = 0
        for folder, directories, names in os.walk(directory):
            if any((Path(folder) / name).is_symlink() for name in directories):
                raise BackgroundFailure("JOB_STORE_CORRUPT")
            for name in names:
                path = Path(folder) / name
                if path == directory / "state.json" or path == excluding:
                    continue
                owned_file(path, LIMITS.sidecar_project_bytes)
                total += path.stat().st_size
        return total

    def _capacity(self, state: BackgroundSidecarV1, states: dict[str, BackgroundSidecarV1], *, replacing=None,
            canonical_fixed_bytes=None, retained_usage=None):
        states = {**states, state.project_id: state}
        retained = {}
        overrides = retained_usage or {}
        for key, provider in self.usage_providers.items():
            for project, usage in (overrides[key] if key in overrides else provider(states=states)).items():
                previous = retained.get(project, RetainedUsage())
                retained[project] = RetainedUsage(previous.draft_bytes + usage.draft_bytes,
                    previous.owned_bytes + usage.owned_bytes, previous.records + usage.records)
        sizes, budget, total = {}, background_project_bytes(LIMITS), background_global_bytes(LIMITS)
        for project, value in states.items():
            replacement = replacing if replacing is not None and replacing[0].is_relative_to(self.projects / project) else None
            sizes[project] = (len(encoded(value.model_dump(mode="json", by_alias=True))) + self._reserved_bytes(value)
                + self._extra_bytes(project, excluding=replacement[0] if replacement else None)
                + (canonical_fixed_bytes if project == state.project_id and canonical_fixed_bytes is not None else self._fixed_bytes(value))
                + (replacement[1] if replacement else 0))
            if project in self.fixed_unknown:
                sizes[project] = max(sizes[project], budget)
        for project, usage in retained.items():
            sizes[project] = sizes.get(project, 0) + usage.owned_bytes
        unknown = set(self.fences) - states.keys()
        draft_sizes = {project: sum(item.payload_bytes for item in value.drafts) for project, value in states.items()}
        for project, usage in retained.items():
            draft_sizes[project] = draft_sizes.get(project, 0) + usage.draft_bytes
        resolved = {project: sum(job.execution in TERMINAL_EXECUTION and job.publication in RESOLVED_PUBLICATION
            for job in value.jobs) for project, value in states.items()}
        if (records(state) + retained.get(state.project_id, RetainedUsage()).records > LIMITS.metadata_project_records or
                resolved[state.project_id] > LIMITS.resolved_project_records or
                sum(resolved.values()) > LIMITS.resolved_global_records or
                draft_sizes[state.project_id] > LIMITS.draft_project_bytes or
                sum(draft_sizes.values()) + len(unknown) * LIMITS.draft_project_bytes > LIMITS.draft_global_bytes or
                sizes[state.project_id] > budget or
                sum(sizes.values()) + len(unknown) * budget > total or
                sum(records(value) for value in states.values()) + sum(value.records for value in retained.values())
                    + len(unknown) * LIMITS.metadata_project_records > LIMITS.metadata_global_records):
            raise BackgroundFailure("JOB_STORAGE_FULL")

    def _fixed_bytes(self, state):
        jobs = [*state.jobs, *[request.archived_result for request in state.requests if request.archived_result is not None]]
        ids = {job.submission.input.id for job in jobs if job.submission.input.kind == "rich_sync"}
        if state.tombstoned:
            return sum(proposal.payload_bytes for proposal in state.proposals if proposal.payload.kind == "rich_sync")
        from .background_fixed import stored_fixed_bytes
        from .rich_limits import WORKSPACE_BYTES
        from .rich_project_store import RichProjectStore
        try:
            path = self.canonical.projects / state.project_id / "workspace.json"
            owned_file(path, WORKSPACE_BYTES)
            stamp = path.stat()
            key = (stamp.st_dev, stamp.st_ino, stamp.st_size, stamp.st_mtime_ns, stamp.st_ctime_ns, tuple(sorted(ids)))
            cached = self.fixed_sizes.get(state.project_id)
            if cached is not None and cached[0] == key:
                self.fixed_unknown.discard(state.project_id)
                return cached[1]
            workspace, _checksum = RichProjectStore(self.root)._read_committed_unlocked(state.project_id)
            value = stored_fixed_bytes(state, workspace)
            self.fixed_sizes[state.project_id] = (key, value)
            self.fixed_unknown.discard(state.project_id)
            return value
        except (ProjectStoreFailure, StorageFailure, OSError, ValueError):
            entry = next((entry for entry in self.canonical._registry().entries if entry.project_id == state.project_id), None)
            if entry is not None and entry.tombstoned:
                return sum(proposal.payload_bytes for proposal in state.proposals if proposal.payload.kind == "rich_sync")
            self.fixed_unknown.add(state.project_id)
            self.fences.setdefault(state.project_id, "OUTCOME_UNKNOWN")
            return 0

    def _write(self, directory: Path, state: BackgroundSidecarV1, states: dict[str, BackgroundSidecarV1]):
        self._capacity(state, states)
        value = BackgroundSidecarV1.model_validate(state.model_dump(by_alias=True))
        self._validate_bindings(value)
        self._capacity(value, states)
        raw = encoded(value.model_dump(mode="json", by_alias=True))
        try:
            atomic_write(directory / "state.json", raw)
            self._sync_namespace(directory / "state.json")
        except (StorageFailure, OSError):
            # Confirm a lost atomic-write reply without applying the transition again.
            self._confirm(directory, raw)
        for observe in self.state_observers.values():
            observe(value)

    def _confirm(self, directory: Path, raw: bytes):
        self._confirm_file(directory / "state.json", raw)

    def _confirm_state(self, directory, state):
        path = directory / "state.json"
        try:
            owned_file(path, LIMITS.sidecar_project_bytes)
            raw = path.read_bytes()
            stored = BackgroundSidecarV1.model_validate(strict_json(raw))
            self._validate_bindings(stored)
            if stored != state:
                raise ValueError("different state")
        except (StorageFailure, OSError, ValueError):
            self.fences[state.project_id] = "JOB_STORE_UNAVAILABLE"
            raise BackgroundFailure("JOB_STORE_UNAVAILABLE") from None
        # Additive private fields need not rewrite an older exact retry's bytes.
        self._confirm_file(path, raw)

    def _confirm_file(self, path: Path, raw: bytes):
        try:
            owned_file(path, LIMITS.sidecar_project_bytes)
            if path.read_bytes() != raw:
                raise OSError("different state")
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
            self._sync_namespace(path)
        except (StorageFailure, OSError):
            self.fences[path.relative_to(self.projects).parts[0]] = "JOB_STORE_UNAVAILABLE"
            raise BackgroundFailure("JOB_STORE_UNAVAILABLE") from None

    def _sync_namespace(self, path):
        if not path.is_relative_to(self.root):
            raise StorageFailure("UNSAFE_STORAGE")
        for directory in path.parents:
            fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            if directory == self.root:
                break

    def open(self, project_id: str, *, account_generation: int | None = None) -> BackgroundSidecarV1:
        with self.guard(project_id) as directory:
            if directory.exists():
                return self._read(project_id, directory)
            current_account = self._read_dispatch(self.background / "dispatch.json").account_generation
            if not (self.background / "dispatch.json").exists():
                atomic_write(self.background / "dispatch.json", encoded(DispatchStateV1(
                    schemaVersion=1, accountGeneration=current_account, paused=None).model_dump(by_alias=True)))
            if account_generation is not None and account_generation != current_account:
                raise BackgroundFailure("ACCOUNT_CHANGED")
            now = self.clock()
            state = BackgroundSidecarV1(schemaVersion=1, projectId=project_id, lineage=identity("lineage"),
                accountGeneration=current_account, activeRequestEpoch=1, expiredThroughEpoch=0,
                requestEpochExpiresAt=expiration(now, LIMITS.request_replay_seconds), tombstoned=False,
                jobs=[], requests=[], proposals=[], writer=None, barrier=None, drafts=[], generations=[], intents=[], inverses=[])
            self._write(directory, state, self._all())
            return state

    def load(self, project_id: str) -> BackgroundSidecarV1:
        with self.guard(project_id) as directory:
            return self._read(project_id, directory)

    def snapshots(self) -> dict[str, BackgroundSidecarV1]:
        try:
            with locked_root(self.root, ".projects.lock"):
                allowed = {entry.project_id for entry in self.canonical._registry().entries if not entry.tombstoned}
                with locked_root(self.background, ".jobs.lock"):
                    private_directory(self.projects)
                    return {project: state for project, state in self._all().items() if project in allowed and not state.tombstoned}
        except (StorageFailure, OSError, ValueError):
            raise BackgroundFailure("JOB_STORE_UNAVAILABLE") from None

    @contextmanager
    def _dispatch_guard(self):
        try:
            with locked_root(self.root, ".projects.lock"):
                with locked_root(self.background, ".jobs.lock"):
                    yield self.background / "dispatch.json"
        except BackgroundFailure:
            raise
        except (StorageFailure, OSError, ValueError):
            raise BackgroundFailure("JOB_STORE_UNAVAILABLE") from None

    @staticmethod
    def _read_dispatch(path) -> DispatchStateV1:
        if not path.exists() and not path.is_symlink():
            projects = path.parent / "projects"
            if projects.exists() and any(projects.iterdir()):
                raise BackgroundFailure("JOB_STORE_CORRUPT")
            return DispatchStateV1(schemaVersion=1, accountGeneration=1, paused=None)
        owned_file(path, agent_limits.TERMINAL_BYTES)
        return DispatchStateV1.model_validate(strict_json(path.read_bytes()))

    def dispatch_state(self) -> DispatchStateV1:
        with self._dispatch_guard() as path:
            return self._read_dispatch(path)

    def pause_dispatch(self, reason):
        with self._dispatch_guard() as path:
            state = self._read_dispatch(path)
            state.paused = reason
            validated = DispatchStateV1.model_validate(state.model_dump(by_alias=True))
            atomic_write(path, encoded(validated.model_dump(mode="json", by_alias=True)))
            self._sync_namespace(path)

    def resume_dispatch(self, account_generation: int):
        if type(account_generation) is not int or account_generation < 1:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        with self._dispatch_guard() as path:
            state = self._read_dispatch(path)
            if account_generation != state.account_generation:
                raise BackgroundFailure("ACCOUNT_CHANGED")
            state.paused = None
            atomic_write(path, encoded(state.model_dump(mode="json", by_alias=True)))
            self._sync_namespace(path)

    def replace_account(self, account_generation: int):
        if type(account_generation) is not int or account_generation < 1:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        with self._dispatch_guard() as path:
            dispatch = self._read_dispatch(path)
            if account_generation < dispatch.account_generation:
                raise BackgroundFailure("ACCOUNT_CHANGED")
            if account_generation != dispatch.account_generation:
                dispatch.account_generation, dispatch.paused = account_generation, "AUTH_REQUIRED"
            # This revokes old authority even if a later per-project write is interrupted.
            atomic_write(path, encoded(dispatch.model_dump(mode="json", by_alias=True)))
            self._sync_namespace(path)
            states = self._all()
            for project, state in states.items():
                self._revoke_account(state, account_generation)
                self._write(self.projects / project, state, states)

    def _revoke_account(self, state, account_generation):
        state.account_generation = account_generation
        for job in state.jobs:
            changed = False
            if job.submission.account_generation != account_generation:
                if job.execution not in TERMINAL_EXECUTION:
                    job.execution = "cancelled" if job.execution == "queued" else "cancelling"
                    changed = True
                if (job.submission.allow_edits and job.publication not in {"saved", "no_change", "discarded", "cancelled"}
                        and not claimed(state, job.id)):
                    job.publication = "cancelled"
                    changed = True
                if changed:
                    job.error = JobFailure(code="ACCOUNT_CHANGED")
                    job.event_cursor += 1
                    job.updated_at = self.clock()
        for proposal in state.proposals:
            if proposal.account_generation != account_generation and proposal.authority == "active":
                proposal.authority, proposal.revocation = "revoked", "account_changed"

    def submit(self, submission: JobSubmissionV1, *, supersede_ids=()) -> tuple[JobSnapshotV1, bool]:
        project_id = submission.identity.project_id
        with self.guard(project_id) as directory:
            state = self._read(project_id, directory)
            if state.tombstoned:
                raise BackgroundFailure("PROJECT_DELETED")
            request = submission.identity
            if request.lineage != state.lineage:
                raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
            existing = next((item for item in state.requests if item.identity == request), None)
            if existing is not None:
                if existing.payload_sha256 != submission.payload_sha256:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                self._confirm_state(directory, state)
                return job_in(state, existing.job_id), False
            now = self.clock()
            if (request.request_epoch != state.active_request_epoch or request.request_epoch <= state.expired_through_epoch
                    or datetime.fromisoformat(now.replace("Z", "+00:00")) >= datetime.fromisoformat(state.request_epoch_expires_at)):
                raise BackgroundFailure("REQUEST_EXPIRED")
            if (submission.account_generation != state.account_generation or submission.account_generation !=
                    self._read_dispatch(self.background / "dispatch.json").account_generation):
                raise BackgroundFailure("ACCOUNT_CHANGED")
            states = self._all()
            superseded = [job for job in state.jobs if job.id in supersede_ids]
            if (len(set(supersede_ids)) != len(supersede_ids) or len(superseded) != len(supersede_ids)
                    or any(job.execution != "queued" or job.submission.kind != "reconciliation"
                        or job.proposal_id is not None for job in superseded)):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            pending = [job for value in states.values() for job in value.jobs
                if job.execution == "queued" and job.id not in supersede_ids]
            local = [job for job in pending if job.submission.identity.project_id == project_id]
            unknown = len(set(self.fences) - states.keys())
            noninteractive = submission.scheduling_class != "interactive"
            if (len(pending) + unknown * LIMITS.pending_project >= LIMITS.pending_global or len(local) >= LIMITS.pending_project
                    or noninteractive and (sum(job.submission.scheduling_class != "interactive" for job in pending)
                        + unknown * LIMITS.pending_noninteractive_project >= LIMITS.pending_noninteractive_global
                        or sum(job.submission.scheduling_class != "interactive" for job in local) >= LIMITS.pending_noninteractive_project)):
                raise BackgroundFailure("JOB_QUEUE_FULL")
            job = JobSnapshotV1(schemaVersion=1, id=identity("job"), submission=submission, execution="queued",
                publication="none", executionGeneration=1, attempts=[], eventCursor=1, proposalId=None,
                receipt=None, error=None, createdAt=now, updatedAt=now)
            state.jobs.append(job)
            for previous in superseded:
                previous.execution, previous.publication = "cancelled", "cancelled"
                previous.error, previous.event_cursor, previous.updated_at = JobFailure(code="CANCELLED"), previous.event_cursor + 1, now
            from .background_assets import pin_snapshot
            from .rich_project_store import RichProjectStore
            canonical = RichProjectStore(self.root)
            workspace, _checksum = canonical._read_committed_unlocked(project_id)
            pin_snapshot(state, canonical, workspace, "job", job.id)
            state.requests.append(RequestReplayV1(identity=request, payloadSha256=submission.payload_sha256,
                jobId=job.id, expiresAt=expiration(now, LIMITS.request_replay_seconds), archivedResult=None))
            self._write(directory, state, states)
            return job, True

    def read(self, project_id: str, job_id: str) -> JobSnapshotV1:
        return job_in(self.load(project_id), job_id)

    def update(self, project_id: str, job_id: str, change, *, deleted=False) -> JobSnapshotV1:
        with self.guard(project_id, deleted=deleted) as directory:
            state = self._read(project_id, directory)
            job = next((item for item in state.jobs if item.id == job_id), None)
            if job is None:
                raise BackgroundFailure("JOB_NOT_FOUND")
            before = job.model_dump(by_alias=True)
            before_state = state.model_dump(by_alias=True)
            change(state, job)
            if job.id != before["id"] or job.submission.model_dump(by_alias=True) != before["submission"]:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            after_state = state.model_dump(by_alias=True)
            if (next((item for item in state.jobs if item.id == job_id), None) is not job or
                    {key: value for key, value in after_state.items() if key not in {"jobs", "proposals"}} !=
                    {key: value for key, value in before_state.items() if key not in {"jobs", "proposals"}} or
                    [item for item in after_state["jobs"] if item["id"] != job_id] !=
                    [item for item in before_state["jobs"] if item["id"] != job_id] or
                    [item for item in after_state["proposals"] if item["jobId"] != job_id] !=
                    [item for item in before_state["proposals"] if item["jobId"] != job_id]):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            if after_state == before_state:
                self._confirm_state(directory, state)
                return job
            job.event_cursor += 1
            job.updated_at = self.clock()
            from .background_assets import release_resolved_jobs
            release_resolved_jobs(state)
            self._write(directory, state, self._all())
            return job

    def cancel(self, project_id: str, job_id: str) -> JobSnapshotV1:
        def cancel(_state, job):
            if job.execution not in TERMINAL_EXECUTION:
                job.execution = "cancelled" if job.execution == "queued" else "cancelling"
                job.error = JobFailure(code="CANCELLED")
            if (job.submission.allow_edits and job.publication not in {"saved", "no_change", "discarded", "cancelled"}
                    and not claimed(_state, job.id)):
                job.publication = "cancelled"
            for proposal in _state.proposals:
                if proposal.job_id == job_id and proposal.authority == "active":
                    proposal.authority, proposal.revocation = "revoked", "stop"
        return self.update(project_id, job_id, cancel)

    def discard(self, project_id, job_id, *, superseded=False):
        def discard(state, job):
            if job.publication in {"saved", "no_change"}:
                return
            if job.execution not in TERMINAL_EXECUTION:
                job.execution = "cancelled" if job.execution == "queued" else "cancelling"
                job.error = JobFailure(code="CANCELLED")
            if not claimed(state, job.id):
                job.publication = "discarded" if job.proposal_id is not None else "cancelled"
            for proposal in state.proposals:
                if proposal.job_id == job.id and proposal.authority == "active":
                    proposal.authority, proposal.revocation = "revoked", "superseded" if superseded else "discard"
        return self.update(project_id, job_id, discard)

    def mark_deleted(self, project_id):
        with self.guard(project_id, deleted=True) as directory:
            state = self._read(project_id, directory)
            state.tombstoned = True
            for job in state.jobs:
                if job.execution not in TERMINAL_EXECUTION:
                    job.execution = "cancelled" if job.execution == "queued" else "cancelling"
                    job.error = JobFailure(code="PROJECT_DELETED")
                if (job.submission.allow_edits and job.publication not in {"saved", "no_change", "discarded", "cancelled"}
                        and not claimed(state, job.id)):
                    job.publication = "cancelled"
                job.event_cursor += 1
                job.updated_at = self.clock()
            for proposal in state.proposals:
                if proposal.authority == "active":
                    proposal.authority, proposal.revocation = "revoked", "deleted"
            self._write(directory, state, self._all())
            return state

    def cleanup_deleted(self, project_id):
        with self.guard(project_id, deleted=True) as directory:
            if not directory.exists():
                return
            state = self._read(project_id, directory)
            if (not state.tombstoned or any(job.execution not in TERMINAL_EXECUTION
                    or any(not attempt.cleanup_verified for attempt in job.attempts) for job in state.jobs)):
                raise BackgroundFailure("CLEANUP_FAILED")
            allowed = {"agent-artifacts", "canonical-candidates", "proposal-intents", "events", "drafts",
                "fixed-inputs", "processing-candidates"}
            files, folders = [], []
            for path in directory.iterdir():
                if path.name in {"state.json", ".canonical.lock", "history-activation.json"}:
                    owned_file(path, LIMITS.sidecar_project_bytes)
                    if path.name == "history-activation.json":
                        files.append(path)
                elif path.name in allowed and path.is_dir() and not path.is_symlink():
                    for blob in path.iterdir():
                        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}\.json", blob.name) is None:
                            raise BackgroundFailure("JOB_STORE_UNAVAILABLE")
                        owned_file(blob, LIMITS.sidecar_project_bytes)
                        files.append(blob)
                    folders.append(path)
                else:
                    raise BackgroundFailure("JOB_STORE_UNAVAILABLE")
            for name in ("jobs", "requests", "proposals", "drafts", "generations", "intents", "inverses",
                    "manual_intents", "asset_pins", "orphan_assets", "cleanup_refs", "writer_touches", "history_commands", "fixed_invalidations"):
                setattr(state, name, [])
            state.writer, state.barrier, state.history = None, None, None
            self._write(directory, state, self._all())
            try:
                for path in files:
                    path.unlink()
                    self._sync_namespace(path)
                for path in folders:
                    path.rmdir()
                    self._sync_namespace(path)
            except (OSError, StorageFailure):
                raise BackgroundFailure("JOB_STORE_UNAVAILABLE") from None
            self.fences.pop(project_id, None)

    def rotate_request_epoch(self, project_id: str) -> BackgroundSidecarV1:
        with self.guard(project_id) as directory:
            state = self._read(project_id, directory)
            now = self.clock()
            if datetime.fromisoformat(now.replace("Z", "+00:00")) < datetime.fromisoformat(state.request_epoch_expires_at):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            state.expired_through_epoch = state.active_request_epoch
            state.active_request_epoch += 1
            state.request_epoch_expires_at = expiration(now, LIMITS.request_replay_seconds)
            self._write(directory, state, self._all())
            return state

    def recover(self, project_id: str) -> BackgroundSidecarV1:
        with self.guard(project_id) as directory:
            state = self._read(project_id, directory)
            changed = False
            account = self._read_dispatch(self.background / "dispatch.json").account_generation
            if state.account_generation != account:
                self._revoke_account(state, account)
                changed = True
            for job in state.jobs:
                if job.execution not in TERMINAL_EXECUTION:
                    job.execution = "interrupted"
                    if job.error is None or job.error.code != "ACCOUNT_CHANGED":
                        job.error = JobFailure(code="INTERRUPTED")
                    job.event_cursor += 1
                    job.updated_at = self.clock()
                    for attempt in job.attempts:
                        if not attempt.cleanup_verified:
                            attempt.state = "interrupted"
                            self.fences[project_id] = "CLEANUP_FAILED"
                    changed = True
            if changed:
                self._write(directory, state, self._all())
            return state
