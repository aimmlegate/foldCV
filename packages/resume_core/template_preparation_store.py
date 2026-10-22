"""Bound prepared transactions to one writer opening and shared storage limits."""

from dataclasses import dataclass, field, replace
import json

from .background_store import BackgroundFailure, RetainedUsage
from .models.template_authoring import TemplatePreparedEditV1
from .models.template_delta import TemplatePreparedEditDeltaV1
from .rich_mutations import mutation_sha256
from .template_local_history import TemplateLocalHistory
from .template_commit_proofs import TemplateCommitProofs
from .template_preparation import preparation_hash
from .templates.compiler import canonical, sha256
from .templates.presentation import snapshot_identity


@dataclass(frozen=True)
class PreparedEntry:
    request_hash: str
    mutation_hash: str | None
    payload: bytes | None
    response_form: str = 'full'
    commit_proof: bytes | None = None
    proof_expires_at: str | None = None
    committed: bool = False


@dataclass
class PreparationOpening:
    key: tuple
    backing: dict | None
    entries: dict[str, PreparedEntry] = field(default_factory=dict)


class TemplatePreparations(TemplateCommitProofs):
    usage_key = 'template_preparations'

    def __init__(self, jobs):
        self.jobs, self.openings = jobs, {}
        jobs.usage_providers[self.usage_key] = self.usage
        jobs.state_observers[self.usage_key] = self.observe

    def observe(self, state):
        if state.tombstoned:
            self.discard(state.project_id)
        else:
            self.opening(state)

    def opening(self, state):
        value = self.openings.get(state.project_id)
        if value is not None and (state.writer is None or state.writer.status == 'clean_detached'
                or value.key != TemplateLocalHistory.key(state)):
            self.discard(state.project_id)
            return None
        return value

    def discard(self, project):
        self.openings.pop(project, None)

    @staticmethod
    def backing(workspace):
        if workspace.schema_version != 7 or workspace.project is None:
            raise BackgroundFailure('JOB_SCOPE_INVALID')
        package = workspace.project.template_package
        return {'projectId': workspace.project_id, 'packageHash': package.package_hash,
            'fullPackageFingerprint': sha256(canonical(package))}

    def usage(self, *, replacing=None, states=None):
        openings = dict(self.openings)
        if replacing is not None:
            openings[replacing.key[0]] = replacing
        result = {}
        for project, value in openings.items():
            state = states.get(project) if states is not None else None
            if state is not None and (state.tombstoned or state.writer is None or state.writer.status == 'clean_detached'
                    or value.key != TemplateLocalHistory.key(state)):
                continue
            entries = {key: {'requestHash': entry.request_hash, 'mutationHash': entry.mutation_hash,
                'responseForm': entry.response_form, 'payload': entry.payload.decode() if entry.payload is not None else None,
                'commitProof': entry.commit_proof.decode() if entry.commit_proof is not None else None,
                'proofExpiresAt': entry.proof_expires_at, 'committed': entry.committed}
                for key, entry in value.entries.items()}
            draft = sum(len(entry.payload) for entry in value.entries.values() if entry.payload is not None)
            owned = len(canonical({'key': list(value.key), 'backing': value.backing, 'entries': entries}))
            result[project] = RetainedUsage(draft, owned, 1 + len(entries) + sum(entry.commit_proof is not None for entry in value.entries.values()))
        return result

    def find(self, state, request, *, response_form='full'):
        opening = self.opening(state)
        entry = opening.entries.get(request.client_mutation_id) if opening is not None else None
        if entry is not None and entry.request_hash != preparation_hash(request):
            raise BackgroundFailure('JOB_IDEMPOTENCY_CONFLICT')
        if entry is not None and entry.response_form != response_form:
            raise BackgroundFailure('PREPARATION_RESPONSE_FORM_CONFLICT')
        return entry

    def read(self, state, workspace, entry):
        opening = self.opening(state)
        if opening is None or entry.payload is None:
            raise BackgroundFailure('REQUEST_EXPIRED')
        try:
            if entry.response_form == 'delta':
                result = TemplatePreparedEditDeltaV1.model_validate_json(entry.payload)
                fingerprint = sha256(result.mutation_wire.encode()) if result.mutation_wire is not None else None
            else:
                if entry.response_form != 'full' or opening.backing != self.backing(workspace):
                    raise ValueError('missing full-preview package backing')
                value = json.loads(entry.payload)
                value['preview']['workspace']['project']['templatePackage'] = workspace.project.template_package.model_dump(mode='json', by_alias=True)
                result = TemplatePreparedEditV1.model_validate(value)
                fingerprint = mutation_sha256(result.mutation) if result.mutation is not None else None
            if (result.request_hash != entry.request_hash or fingerprint != entry.mutation_hash
                    or result.base_snapshot.project_id != state.project_id
                    or opening.entries.get(result.client_mutation_id) is not entry):
                raise ValueError('retained preparation differs from its entry binding')
            return result
        except (ValueError, KeyError, TypeError, RecursionError):
            raise BackgroundFailure('REQUEST_EXPIRED') from None

    def admit(self, state, workspace, prepared):
        current = self.opening(state)
        response_form = 'delta' if isinstance(prepared, TemplatePreparedEditDeltaV1) else 'full'
        backing = current.backing if current is not None else None
        if response_form == 'full' or backing is not None:
            captured = self.backing(workspace)
        if backing is not None and backing != captured:
            raise BackgroundFailure('REQUEST_EXPIRED')
        if response_form == 'full':
            backing = captured
        identifier = prepared.client_mutation_id
        if current is not None and identifier in current.entries:
            raise BackgroundFailure('JOB_IDEMPOTENCY_CONFLICT')
        compact = prepared.model_dump(mode='json', by_alias=True)
        if response_form == 'full':
            del compact['preview']['workspace']['project']['templatePackage']
            fingerprint = mutation_sha256(prepared.mutation) if prepared.mutation is not None else None
        else:
            fingerprint = sha256(prepared.mutation_wire.encode()) if prepared.mutation_wire is not None else None
        entry = PreparedEntry(prepared.request_hash, fingerprint, canonical(compact), response_form)
        candidate = PreparationOpening(TemplateLocalHistory.key(state), backing,
            {**(current.entries if current is not None else {}), identifier: entry})
        self.jobs._capacity(state, self.jobs._all(), retained_usage={self.usage_key: self.usage(replacing=candidate)})
        self.openings[state.project_id] = candidate
        return prepared.model_copy(deep=True)

    def save_guard(self, state, workspace, request):
        opening = self.opening(state)
        identifier = request.mutation.client_mutation_id
        entry = opening.entries.get(identifier) if opening is not None else None
        if entry is None:
            if request.preparation is not None:
                raise BackgroundFailure('REQUEST_EXPIRED')
            return
        if request.preparation is None:
            raise BackgroundFailure('JOB_SCOPE_INVALID')
        if entry.request_hash != request.preparation.request_hash or entry.mutation_hash != mutation_sha256(request.mutation):
            raise BackgroundFailure('JOB_IDEMPOTENCY_CONFLICT')
        replay = next((item for item in workspace.mutation_replay if item.client_mutation_id == identifier), None)
        intent = next((item for item in state.manual_intents if item.client_mutation_id == identifier), None)
        if (replay is not None and replay.request_sha256 == entry.mutation_hash
                or intent is not None and intent.phase == 'receipt_stored' and intent.request_sha256 == entry.mutation_hash):
            return
        if entry.payload is None:
            raise BackgroundFailure('REQUEST_EXPIRED')
        prepared = self.read(state, workspace, entry)
        if prepared.base_snapshot != snapshot_identity(workspace):
            raise BackgroundFailure('DEPENDENCY_CHANGED')

    def reject_registered(self, state, identifier):
        opening = self.opening(state)
        if opening is not None and identifier in opening.entries:
            raise BackgroundFailure('JOB_SCOPE_INVALID')

    def committed(self, state, workspace, mutation):
        opening = self.opening(state)
        entry = opening.entries.get(mutation.client_mutation_id) if opening is not None else None
        if entry is None:
            return
        fingerprint = mutation_sha256(mutation)
        if fingerprint != entry.mutation_hash or not any(item.client_mutation_id == mutation.client_mutation_id
                and item.request_sha256 == fingerprint for item in workspace.mutation_replay):
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        self.verify_commit(entry, workspace, mutation)
        opening.entries[mutation.client_mutation_id] = replace(entry, payload=None, committed=True)
