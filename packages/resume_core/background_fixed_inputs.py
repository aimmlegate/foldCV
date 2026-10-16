"""Captured fixed requests and processing candidates have one owned private path."""

import hashlib

from .agent_store import digest
from .background_limits import LIMITS
from .background_store import BackgroundFailure
from .models.background import FixedInputV1, ProcessingCandidateV1
from .project_store import SAFE_ID, encoded, owned_file, strict_json
from .storage import StorageFailure, atomic_write, private_directory


class FixedInputs:
    def __init__(self, store):
        self.store = store

    def path(self, directory, folder, identifier):
        if SAFE_ID.fullmatch(identifier) is None:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        parent = directory / folder
        if parent.is_symlink():
            raise BackgroundFailure("JOB_STORE_CORRUPT")
        return parent / (identifier + ".json")

    def write(self, directory, state, folder, value, *, immutable=False):
        raw = encoded(value.model_dump(mode="json", by_alias=True))
        path = self.path(directory, folder, value.id)
        if path.exists():
            owned_file(path, LIMITS.sidecar_project_bytes)
            if path.read_bytes() == raw:
                return hashlib.sha256(raw).hexdigest()
            if immutable:
                raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
        self.store._capacity(state, self.store._all(), replacing=(path, len(raw)))
        private_directory(path.parent)
        atomic_write(path, raw)
        self.store._sync_namespace(path)
        return hashlib.sha256(raw).hexdigest()

    def prepare(self, directory, state, value):
        if value.identity.project_id != state.project_id or value.identity.lineage != state.lineage:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        return self.write(directory, state, "fixed-inputs", value, immutable=True)

    def read(self, directory, job):
        try:
            path = self.path(directory, "fixed-inputs", job.submission.input.id)
            owned_file(path, LIMITS.sidecar_project_bytes)
            raw = path.read_bytes()
            value = FixedInputV1.model_validate(strict_json(raw))
            if (value.id != path.stem or value.identity != job.submission.identity
                    or value.id != "fixed_" + digest(value.identity)[:32]
                    or hashlib.sha256(raw).hexdigest() != job.submission.input.sha256
                    or value.workspace.project_id != value.identity.project_id
                    or value.workspace.sync_records):
                raise ValueError("changed fixed input")
            return value
        except (StorageFailure, OSError, ValueError):
            raise BackgroundFailure("JOB_STORE_CORRUPT") from None

    def processing(self, directory, identifier):
        try:
            path = self.path(directory, "processing-candidates", identifier)
            owned_file(path, LIMITS.sidecar_project_bytes)
            value = ProcessingCandidateV1.model_validate(strict_json(path.read_bytes()))
            if value.id != identifier:
                raise ValueError("changed processing identity")
            return value
        except (StorageFailure, OSError, ValueError):
            raise BackgroundFailure("JOB_STORE_CORRUPT") from None

    def save_processing(self, directory, state, value):
        if any(p.payload.kind == "processing" and p.payload.candidate_id == value.id for p in state.proposals):
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        return self.write(directory, state, "processing-candidates", value)

    def payload(self, state, directory, reference):
        if reference.kind != "processing":
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        value = self.processing(directory, reference.candidate_id)
        if value.workspace is None or value.normalized is None or value.workspace.project_id != state.project_id:
            raise BackgroundFailure("OUTCOME_UNKNOWN")
        return encoded(value.model_dump(mode="json", by_alias=True))
