"""One resumable editor writer; lost leases do not establish a clean boundary."""

from contextlib import contextmanager
from datetime import datetime
import hashlib
import hmac
import secrets

from .agent_store import digest
from .background_history import digest_bytes
from .background_drafts import WriterDrafts
from .background_history_owner import WriterHistory
from .background_limits import LIMITS
from .background_scopes import mutation_selectors, query_touches
from .background_store import BackgroundFailure, expiration, identity, records
from .models.background import (PublicationBarrierV1, WriterCommitBindingV1, WriterSessionV1,
    WriterTouchReceiptV1, WriterViewV1)
from .rich_api import RichProjectResponse
from .rich_identity import resume_identity
from .rich_presentation import presentation
from .rich_project_store import rich_snapshot_bytes
from .template_local_history import TemplateLocalHistory
from .template_preparation_store import TemplatePreparations
from .template_clipboard_store import TemplateClipboards
from .template_writer_preparation import TemplateWriterPreparation
from .template_writer_history import TemplateWriterHistory


def secret_hash(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def at_or_after(now, deadline):
    return datetime.fromisoformat(now.replace("Z", "+00:00")) >= datetime.fromisoformat(deadline.replace("Z", "+00:00"))


class WriterSessions(TemplateWriterPreparation, TemplateWriterHistory, WriterDrafts, WriterHistory):
    def __init__(self, coordinator, *, clock=None, observer=lambda _name, _project: None, blocked=lambda _project: False):
        self.coordinator, self.jobs, self.history = coordinator, coordinator.jobs, coordinator.history
        self.clock, self.observer = clock or coordinator.authority.clock, observer
        self.live = {}
        self.local_history = TemplateLocalHistory(self.jobs)
        if not hasattr(self.jobs, 'template_preparations'):
            self.jobs.template_preparations = TemplatePreparations(self.jobs)
        self.preparations = self.jobs.template_preparations
        if not hasattr(self.jobs, 'template_clipboards'):
            self.jobs.template_clipboards = TemplateClipboards(self.jobs)
        self.clipboards = self.jobs.template_clipboards
        self.blocked = blocked
        coordinator.writer_validator = self.validate_binding
        coordinator.history_validator = self.validate_history_binding

    @contextmanager
    def guard(self, project, *, uncertain=False):
        self.jobs.open(project)
        if not uncertain:
            if self.blocked(project):
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            self.coordinator.recover(project)
            self.history.open(project)
        with self.coordinator._writer(project), self.jobs.guard(project) as directory:
            state = self.jobs._read(project, directory)
            workspace, checksum = self.coordinator.canonical._read_committed_unlocked(project)
            if not uncertain:
                self.coordinator._writable(state)
                self.history._ready(state, directory, checksum)
            yield directory, state, workspace, checksum

    def write(self, directory, state):
        self.jobs._write(directory, state, self.jobs._all())

    def ensure(self, state, workspace):
        if state.writer is not None:
            state.writer_epoch = state.writer.epoch
            return state.writer
        if state.writer_epoch:
            raise BackgroundFailure("WRITER_UNKNOWN")
        state.writer_epoch = 1
        state.writer = WriterSessionV1(schemaVersion=1, projectId=state.project_id, lineage=state.lineage,
            epoch=1, sessionId="initial", incarnation="initial", resumeCredentialSha256=secret_hash(secrets.token_urlsafe(32)),
            leaseExpiresAt=self.jobs.clock(), status="clean_detached", acknowledgedRevision=workspace.project_revision,
            acknowledgedCursor=0, acknowledgedSha256=digest_bytes(workspace), touchGeneration=0,
            barrierGeneration=0, draftId=None)
        return state.writer

    def initialize(self, project):
        with self.guard(project) as (directory, state, workspace, _checksum):
            self.ensure(state, workspace)
            self.write(directory, state)

    def alive(self, writer):
        live = self.live.get(writer.project_id)
        return (live is not None and live[:2] == (writer.epoch, writer.incarnation)
            and self.clock.now() < live[2] and not at_or_after(self.jobs.clock(), writer.lease_expires_at))

    def require(self, state, proof, *, recovery=False, expired=False, detached=False):
        writer = state.writer
        statuses = {"attached", "recovering", "fenced"} if recovery else {"attached"}
        if detached:
            statuses.add("clean_detached")
        if (writer is None or proof.lineage != state.lineage or (proof.epoch, proof.session_id, proof.incarnation) !=
                (writer.epoch, writer.session_id, writer.incarnation)
                or not hmac.compare_digest(secret_hash(proof.credential), writer.resume_credential_sha256)
                or writer.status not in statuses
                or not expired and not self.alive(writer)):
            raise BackgroundFailure("WRITER_UNKNOWN")
        return writer

    def renew(self, writer):
        writer.lease_expires_at = expiration(self.jobs.clock(), LIMITS.writer_lease_seconds)
        self.live[writer.project_id] = (writer.epoch, writer.incarnation, self.clock.now() + LIMITS.writer_lease_seconds)

    def view(self, state, workspace, checksum):
        self.local_history.opening(state)
        self.preparations.opening(state)
        ready = not self.blocked(state.project_id) and state.project_id not in self.jobs.fences and all(intent.phase in {"receipt_stored", "reconciled"}
            for intent in [*state.intents, *state.manual_intents])
        fields = dict(workspace=workspace, durability='durable' if ready else 'failed',
            savedProjectRevision=workspace.project_revision if ready else None,
            savedDocumentRevision=workspace.document_revision if ready else None,
            saveError=None if ready else 'OUTCOME_UNKNOWN', generation=None, identity=resume_identity(workspace))
        if workspace.schema_version == 7:
            from .template_api import TemplateProjectResponseV1
            from .models.template_writer import WriterViewV2
            from .templates.presentation import project_presentation, snapshot_identity
            response = TemplateProjectResponseV1(schemaVersion=1, **fields, snapshot=snapshot_identity(workspace),
                presentation=project_presentation(workspace))
            view_type, version = WriterViewV2, 2
        else:
            response = RichProjectResponse(**fields,
                presentation=presentation(workspace.project.document, workspace.project.facts) if workspace.project else None)
            view_type, version = WriterViewV1, 1
        return view_type(schemaVersion=version, writer=state.writer.model_copy(deep=True), response=response,
            workspaceSha256=checksum, workspaceWire=rich_snapshot_bytes(workspace).decode(), canonicalReady=ready,
            drafts=state.drafts, inverses=state.inverses)

    def validate_binding(self, state, binding):
        writer = state.writer
        draft = next((item for item in state.drafts if item.id == binding.draft_id), None) if binding.draft_id else None
        resolving = (draft is not None and (draft.sequence, draft.payload_sha256) == (binding.draft_sequence, binding.draft_sha256)
            and writer is not None and writer.draft_id == binding.draft_id)
        if (writer is None or writer.status != ("recovering" if resolving else "attached")
                or (writer.draft_id is not None and not resolving) or (binding.draft_id is not None and not resolving) or not self.alive(writer)
                or (writer.epoch, writer.incarnation, writer.acknowledged_cursor, writer.touch_generation) !=
                (binding.epoch, binding.incarnation, binding.action_cursor, binding.touch_generation)):
            raise BackgroundFailure("WRITER_UNKNOWN")

    def save(self, project, request, *, originals=None, artifacts=None, images=None):
        if request.schema_version == 2:
            return self.save_template(project, request, originals=originals, artifacts=artifacts, images=images)
        def authorize(state, workspace, directory):
            writer = self.require(state, request.proof)
            if ((request.canonical_revision, request.canonical_sha256) !=
                    (writer.acknowledged_revision, writer.acknowledged_sha256)
                    or request.mutation.project_id != project or request.mutation.capture.session_id != writer.session_id):
                raise BackgroundFailure("WRITER_UNKNOWN")
            actual = request.model_copy(update={"canonical_revision": workspace.project_revision,
                "canonical_sha256": digest_bytes(workspace)}, deep=True)
            self.advance(state, workspace, digest_bytes(workspace), actual)
            self.write(directory, state)
            return WriterCommitBindingV1(epoch=writer.epoch, incarnation=writer.incarnation,
                actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation)
        _workspace, replayed = self.coordinator.manual(project, request.mutation, authorize=authorize,
            originals=originals, artifacts=artifacts, images=images)
        with self.guard(project) as (_directory, state, workspace, checksum):
            return self.mutation_view(state, workspace, checksum, request.mutation, replayed)

    def mutation_view(self, state, workspace, checksum, mutation, replayed):
        from .rich_mutations import mutation_sha256
        if not any(item.client_mutation_id == mutation.client_mutation_id and item.request_sha256 == mutation_sha256(mutation)
                for item in workspace.mutation_replay):
            raise BackgroundFailure("REQUEST_EXPIRED")
        view = self.view(state, workspace, checksum)
        return type(view).model_validate({**view.model_dump(by_alias=True), "replayed": replayed,
            "mutationWire": mutation.model_dump_json(by_alias=True)})

    def open(self, project, request):
        with self.guard(project) as (directory, state, workspace, checksum):
            previous = self.ensure(state, workspace)
            same_secret = hmac.compare_digest(secret_hash(request.credential), previous.resume_credential_sha256)
            same_identity = request.session_id == previous.session_id and same_secret
            if previous.status != "clean_detached":
                if same_identity and request.incarnation == previous.incarnation:
                    if not self.alive(previous):
                        raise BackgroundFailure("WRITER_UNKNOWN")
                    return self.view(state, workspace, checksum)
                if (not same_identity or request.previous_epoch != previous.epoch
                        or request.previous_incarnation != previous.incarnation
                        or previous.status == "attached" and self.alive(previous)):
                    raise BackgroundFailure("WRITER_UNKNOWN")
                clean = (request.canonical_revision == workspace.project_revision and request.canonical_sha256 == checksum
                    and request.action_cursor == previous.acknowledged_cursor and previous.draft_id is None
                    and request.draft_sequence == 0)
                self.return_history(state, previous)
                previous.incarnation = request.incarnation
                previous.status = "attached" if clean else "recovering"
                if clean:
                    previous.acknowledged_revision = workspace.project_revision
                    previous.acknowledged_sha256 = checksum
                writer = previous
            else:
                state.writer_epoch = max(state.writer_epoch, previous.epoch) + 1
                clean = request.draft_sequence == 0 and (request.action_cursor == 0 or same_identity
                    and request.previous_epoch == previous.epoch and request.previous_incarnation == previous.incarnation
                    and request.action_cursor == previous.acknowledged_cursor)
                writer = previous.model_copy(update={"epoch": state.writer_epoch, "session_id": request.session_id,
                    "incarnation": request.incarnation, "resume_credential_sha256": secret_hash(request.credential),
                    "status": "attached" if clean else "recovering",
                    "acknowledged_revision": workspace.project_revision, "acknowledged_cursor": 0, "touch_floor": 0,
                    "draft_sequence_floor": 0,
                    "acknowledged_sha256": checksum,
                    "draft_id": None, "barrier_generation": previous.barrier_generation + 1}, deep=True)
                state.writer, state.writer_touches = writer, []
            state.barrier = None
            self.coordinator.authority.acks.pop(project, None)
            self.renew(writer)
            self.write(directory, state)
            self.observer("writer_resumed", project)
            return self.view(state, workspace, checksum)

    def heartbeat(self, project, proof):
        with self.guard(project, uncertain=True) as (directory, state, workspace, checksum):
            writer = self.require(state, proof, recovery=True)
            self.renew(writer)
            self.write(directory, state)
            return self.view(state, workspace, checksum)

    def read_snapshot(self, project, proof):
        with self.guard(project, uncertain=True) as (_directory, state, workspace, checksum):
            self.require(state, proof, recovery=True, expired=True, detached=True)
            return self.view(state, workspace, checksum)

    def publication_claim(self, project, request):
        from .background_authority import WriterClaim
        with self.guard(project) as (_directory, state, workspace, _checksum):
            self.require(state, request.proof)
            barrier = state.barrier
            if (barrier is None or barrier.generation != request.generation or barrier.incarnation != request.proof.incarnation
                    or not hmac.compare_digest(barrier.token, request.token)):
                raise BackgroundFailure("WRITER_UNKNOWN")
            claim = self.coordinator.authority.require(state, workspace, now=self.jobs.clock())
            if claim != WriterClaim(request.proof.epoch, request.proof.incarnation, request.generation):
                raise BackgroundFailure("WRITER_UNKNOWN")
            return claim

    def reconcile(self, project, request):
        with self.local_history.guard(project), self.guard(project) as (directory, state, workspace, checksum):
            writer = self.require(state, request.proof, recovery=True)
            if writer.draft_id is not None:
                raise BackgroundFailure("WRITER_UNKNOWN")
            writer.status = "attached"
            if workspace.schema_version == 7:
                self.local_history.reconcile(self, state, workspace, directory)
            self.advance(state, workspace, checksum, request)
            self.renew(writer)
            self.write(directory, state)
            return self.view(state, workspace, checksum)

    def suspend(self, project, proof):
        with self.guard(project, uncertain=True) as (directory, state, workspace, checksum):
            writer = self.require(state, proof, recovery=True, expired=True)
            self.return_history(state, writer)
            writer.status = "recovering"
            if state.barrier is not None and state.barrier.state == "acked":
                state.barrier.state = "revoked"
            self.coordinator.authority.acks.pop(project, None)
            self.live.pop(project, None)
            self.write(directory, state)
            return self.view(state, workspace, checksum)

    def advance(self, state, workspace, checksum, request):
        if (request.schema_version == 2) != (workspace.schema_version == 7):
            raise BackgroundFailure('JOB_SCOPE_INVALID')
        writer = self.require(state, request.proof)
        opening = self.local_history.opening(state)
        if opening is not None:
            self.local_history.observe(opening, state)
        if (request.canonical_revision != workspace.project_revision or request.canonical_sha256 != checksum
                or writer.draft_id is not None or state.barrier is not None and state.barrier.state in {"acked", "commit_claimed"}):
            raise BackgroundFailure("WRITER_UNKNOWN")
        seen = {item.cursor: item.sha256 for item in state.writer_touches}
        cursors = [item.cursor for item in request.touches]
        if cursors != sorted(set(cursors)) or any(item > request.action_cursor for item in cursors):
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        touched = set()
        for item in request.touches:
            checksum_touch = digest(item.model_dump(mode="json", by_alias=True))
            if item.cursor <= writer.touch_floor:
                raise BackgroundFailure("REQUEST_EXPIRED")
            if item.cursor <= writer.acknowledged_cursor:
                if seen.get(item.cursor) != checksum_touch:
                    raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                continue
            if item.cursor != writer.acknowledged_cursor + 1:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            if item.mutation is not None:
                if item.mutation.project_id != state.project_id or item.mutation.capture.session_id != writer.session_id:
                    raise BackgroundFailure("JOB_SCOPE_INVALID")
                self.history.register(state, workspace, mutation_selectors(workspace, item.mutation), write=True)
                touched.update(query_touches(state, workspace, workspace, item.mutation))
                if item.mutation.kind not in {"undo", "redo"}:
                    self.drop_redo(state)
            writer.acknowledged_cursor = item.cursor
            state.writer_touches.append(WriterTouchReceiptV1(cursor=item.cursor, sha256=checksum_touch))
        if request.action_cursor != writer.acknowledged_cursor:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
        if touched:
            self.history.advance(state, workspace, workspace, touches=touched)
            writer.touch_generation += 1
        if opening is not None:
            opening.generations = {stamp.key: stamp.generation for stamp in state.generations}
        writer.acknowledged_revision = workspace.project_revision
        writer.acknowledged_sha256 = checksum
        overflow = max(0, records(state) - LIMITS.metadata_project_records)
        if overflow:
            removed = sorted(state.writer_touches, key=lambda item: item.cursor)[:overflow]
            if len(removed) != overflow:
                raise BackgroundFailure("JOB_STORAGE_FULL")
            writer.touch_floor = max([writer.touch_floor, *[item.cursor for item in removed]])
            state.writer_touches = [item for item in state.writer_touches if item.cursor > writer.touch_floor]
        return writer

    def flush(self, project, request):
        with self.guard(project) as (directory, state, workspace, checksum):
            self.advance(state, workspace, checksum, request)
            self.write(directory, state)
            self.observer("touch_watermark_durable", project)
            return self.view(state, workspace, checksum)

    def detach(self, project, request):
        with self.guard(project) as (directory, state, workspace, checksum):
            writer = self.advance(state, workspace, checksum, request)
            self.return_history(state, writer)
            writer.status = "clean_detached"
            self.write(directory, state)
            self.live.pop(project, None)
            self.coordinator.authority.acks.pop(project, None)
            self.local_history.discard(project)
            self.preparations.discard(project)
            self.observer("clean_detach_acked", project)
            return self.view(state, workspace, checksum)

    def barrier(self, project, request):
        with self.guard(project) as (directory, state, workspace, checksum):
            writer = self.require(state, request.proof)
            old = state.barrier
            if old is not None and request.generation == old.generation:
                if (old.state != "acked" or old.token != request.token or old.incarnation != writer.incarnation
                        or old.action_cursor != request.action_cursor or old.touch_generation != request.touch_generation
                        or old.acknowledged_revision != request.canonical_revision
                        or request.canonical_revision != workspace.project_revision or request.canonical_sha256 != checksum
                        or at_or_after(self.jobs.clock(), old.expires_at)):
                    raise BackgroundFailure("WRITER_UNKNOWN")
                return old.model_copy(deep=True)
            self.advance(state, workspace, checksum, request)
            if request.generation != writer.barrier_generation + 1 or request.touch_generation != writer.touch_generation:
                raise BackgroundFailure("WRITER_UNKNOWN")
            writer.barrier_generation = request.generation
            state.barrier = PublicationBarrierV1(schemaVersion=1, projectId=project, lineage=state.lineage,
                writerEpoch=writer.epoch, incarnation=writer.incarnation, generation=request.generation, token=request.token,
                acknowledgedRevision=workspace.project_revision, actionCursor=writer.acknowledged_cursor,
                touchGeneration=writer.touch_generation, expiresAt=expiration(self.jobs.clock(), LIMITS.local_barrier_ms / 1000),
                state="acked")
            self.write(directory, state)
            self.coordinator.authority.acknowledged(writer, state.barrier)
            self.observer("barrier_acked", project)
            return state.barrier.model_copy(deep=True)

    def revoke(self, project, request):
        with self.guard(project, uncertain=True) as (directory, state, _workspace, _checksum):
            self.require(state, request.proof, recovery=True, expired=True)
            barrier = state.barrier
            if (barrier is None or barrier.incarnation != request.proof.incarnation or barrier.generation != request.generation
                    or not hmac.compare_digest(barrier.token, request.token)):
                raise BackgroundFailure("WRITER_UNKNOWN")
            if barrier.state == "acked":
                barrier.state = "revoked"
                self.coordinator.authority.acks.pop(project, None)
                self.write(directory, state)
            return barrier.model_copy(deep=True)

    def recover_all(self):
        self.live.clear()
        self.local_history.openings.clear()
        self.preparations.openings.clear()
        self.clipboards.openings.clear()
        self.coordinator.authority.acks.clear()
        for project, state in self.jobs.snapshots().items():
            if state.writer is None or state.writer.status == "clean_detached":
                continue
            with self.coordinator._writer(project), self.jobs.guard(project) as directory:
                state = self.jobs._read(project, directory)
                if all(intent.phase in {"receipt_stored", "reconciled"}
                        for intent in [*state.intents, *state.manual_intents]):
                    self.return_history(state, state.writer)
                state.writer.status = "recovering"
                if state.barrier is not None and state.barrier.state == "acked":
                    state.barrier.state = "revoked"
                self.write(directory, state)

    def abandon(self, project, request):
        with self.guard(project) as (directory, state, workspace, checksum):
            if (request.canonical_revision, request.canonical_sha256) != (workspace.project_revision, checksum):
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            old = state.writer
            epoch = max(state.writer_epoch, old.epoch if old else 0)
            if old is not None:
                self.move_session_pins(state, old.incarnation, request.incarnation)
            if set(request.discard_drafts) - {item.id for item in state.drafts}:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            for record in list(state.drafts):
                if record.id in request.discard_drafts:
                    self.dispose_draft(state, record)
            self.history.advance(state, workspace, workspace, touches={item.key for item in state.history.definitions})
            self.drop_redo(state)
            for inverse in state.inverses:
                if inverse.owner in {"session", "transferring"} and inverse.writer_epoch == epoch:
                    inverse.owner, inverse.writer_epoch, inverse.incarnation = "backend", None, None
                    inverse.transfer_id = identity("transfer")
            state.writer_epoch = epoch + 1
            state.writer = WriterSessionV1(schemaVersion=1, projectId=project, lineage=state.lineage,
                epoch=state.writer_epoch, sessionId=request.session_id, incarnation=request.incarnation,
                resumeCredentialSha256=secret_hash(request.credential), leaseExpiresAt=self.jobs.clock(),
                status="attached", acknowledgedRevision=workspace.project_revision, acknowledgedSha256=checksum,
                acknowledgedCursor=0, touchGeneration=0, barrierGeneration=(old.barrier_generation if old else 0) + 1,
                draftId=None, abandonedEpoch=epoch)
            state.writer_touches, state.barrier = [], None
            self.coordinator.authority.acks.pop(project, None)
            self.renew(state.writer)
            self.write(directory, state)
            self.local_history.discard(project)
            self.preparations.discard(project)
            return self.view(state, workspace, checksum)

    @staticmethod
    def move_session_pins(state, previous, current):
        previous_owner, current_owner = "session_" + digest(previous)[:40], "session_" + digest(current)[:40]
        old = next((pin for pin in state.asset_pins if (pin.kind, pin.owner) == ("session", previous_owner)), None)
        if old is None or previous_owner == current_owner:
            return
        known = next((pin for pin in state.asset_pins if (pin.kind, pin.owner) == ("session", current_owner)), None)
        if known is None:
            old.owner = current_owner
            return
        references = {(ref.kind, ref.path): ref for ref in known.references}
        for ref in old.references:
            if (ref.kind, ref.path) in references and references[(ref.kind, ref.path)] != ref:
                raise BackgroundFailure("OUTCOME_UNKNOWN")
            references[(ref.kind, ref.path)] = ref
        if len(references) > 100:
            raise BackgroundFailure("JOB_STORAGE_FULL")
        known.references = list(references.values())
        state.asset_pins.remove(old)
