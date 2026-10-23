"""Bounded private input checkpoints; a local checkpoint never proves a save."""

import hashlib

from pydantic import ValidationError

from .agent_store import digest
from .agent_edits import semantic
from .background_assets import JobAssets, pin_snapshot
from .background_limits import LIMITS
from .background_store import BackgroundFailure
from .models.agent import wire_bytes
from .models.background import DraftCheckpointV1, DraftPayloadV1, WriterAdvanceV1, WriterDraftReadV1
from .project_store import owned_file, strict_json
from .rich_mutations import mutation_sha256
from .storage import StorageFailure, atomic_write, private_directory


def finish_draft_resolution(state, binding):
    if binding.draft_id is None:
        return
    record = next((item for item in state.drafts if item.id == binding.draft_id), None)
    if (record is None or (record.sequence, record.payload_sha256) != (binding.draft_sequence, binding.draft_sha256)
            or state.writer is None or state.writer.draft_id != record.id):
        raise BackgroundFailure("OUTCOME_UNKNOWN")
    state.drafts.remove(record)
    state.asset_pins = [pin for pin in state.asset_pins if (pin.kind, pin.owner) != ("draft", record.id)]
    state.cleanup_refs = sorted(set([*state.cleanup_refs, "drafts/" + record.payload_ref + ".json"]))
    state.writer.draft_id, state.writer.status = None, "attached"
    state.writer.draft_sequence_floor = max(state.writer.draft_sequence_floor, record.sequence)


def image_ids(value):
    if isinstance(value, dict):
        current = {value["assetId"]} if isinstance(value.get("assetId"), str) else set()
        return current | set().union(*(image_ids(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(image_ids(item) for item in value))
    return set()


class WriterDrafts:
    def checkpoint(self, project, request):
        raw = wire_bytes(request.payload)
        if len(raw) > LIMITS.draft_project_bytes:
            raise BackgroundFailure("JOB_STORAGE_FULL")
        checksum = hashlib.sha256(raw).hexdigest()
        self.observer("before_draft_checkpoint", project)
        with self.guard(project, uncertain=True) as (directory, state, workspace, _checksum):
            writer = self.require(state, request.proof, recovery=True, expired=True)
            if (request.schema_version == 2) != (workspace.schema_version == 7):
                raise BackgroundFailure('JOB_SCOPE_INVALID')
            previous = next((item for item in state.drafts if item.id == request.id), None)
            if previous is None and request.sequence <= writer.draft_sequence_floor:
                raise BackgroundFailure("REQUEST_EXPIRED")
            if previous is not None:
                if previous.writer_epoch != writer.epoch:
                    raise BackgroundFailure("WRITER_UNKNOWN")
                if previous.sequence > request.sequence:
                    return previous.model_copy(deep=True)
                if previous.sequence == request.sequence:
                    if (previous.payload_sha256, previous.action_cursor, previous.base_revision, previous.base_sha256) != (
                            checksum, request.action_cursor, request.base_revision, request.base_sha256):
                        raise BackgroundFailure("JOB_IDEMPOTENCY_CONFLICT")
                    self.owned_draft(state, directory, previous)
                    return previous.model_copy(deep=True)
                if request.action_cursor < previous.action_cursor:
                    raise BackgroundFailure("JOB_SCOPE_INVALID")
            if writer.draft_id not in {None, request.id}:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            if any(item.project_id != project or item.capture.session_id != writer.session_id for item in request.payload.outbox):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            if (len({item.client_mutation_id for item in request.payload.outbox}) != len(request.payload.outbox)
                    or len({item.command_id for item in request.payload.history_outbox}) != len(request.payload.history_outbox)
                    or any(item.action_cursor > request.action_cursor for item in request.payload.history_outbox)
                    or len({item.cursor for item in request.payload.touches}) != len(request.payload.touches)
                    or any(item.cursor > request.action_cursor for item in request.payload.touches)):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            required = image_ids(request.payload.model_dump(mode="json", by_alias=True))
            if required - set(request.payload.asset_pins):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            reference = "draft_" + digest([state.lineage, writer.epoch, request.id, request.sequence, checksum])[:40]
            path = private_directory(directory / "drafts") / (reference + ".json")
            record = DraftCheckpointV1(schemaVersion=1, id=request.id, projectId=project, lineage=state.lineage,
                writerEpoch=writer.epoch, incarnation=writer.incarnation, sequence=request.sequence,
                actionCursor=request.action_cursor, baseRevision=request.base_revision, baseSha256=request.base_sha256,
                payloadSha256=checksum, payloadBytes=len(raw), payloadRef=reference, touches=[], checkpointedAt=self.jobs.clock())
            state.drafts = [item for item in state.drafts if item.id != request.id] + [record]
            state.asset_pins = [item for item in state.asset_pins if (item.kind, item.owner) != ("draft", request.id)]
            pin = pin_snapshot(state, self.coordinator.canonical, workspace, "draft", request.id,
                images=set(request.payload.asset_pins))
            if pin.references:
                record.asset_pins_sha256 = digest([item.model_dump(mode="json", by_alias=True) for item in pin.references])
            writer.draft_id, writer.status = record.id, "recovering"
            writer.draft_sequence_floor = max(writer.draft_sequence_floor, record.sequence)
            if state.barrier is not None and state.barrier.state == "acked":
                state.barrier.state = "revoked"
            self.coordinator.authority.acks.pop(project, None)
            if previous is not None and previous.payload_ref != reference:
                state.cleanup_refs = sorted(set([*state.cleanup_refs, "drafts/" + previous.payload_ref + ".json"]))
            self.jobs._capacity(state, self.jobs._all(), replacing=(path, len(raw)))
            if path.exists():
                owned_file(path, LIMITS.draft_project_bytes)
                if path.read_bytes() != raw:
                    raise BackgroundFailure("OUTCOME_UNKNOWN")
            else:
                atomic_write(path, raw)
            self.jobs._sync_namespace(path)
            self.write(directory, state)
            self.observer("draft_checkpointed", project)
            return record.model_copy(deep=True)

    @staticmethod
    def _draft(directory, record):
        try:
            path = directory / "drafts" / (record.payload_ref + ".json")
            owned_file(path, LIMITS.draft_project_bytes)
            raw = path.read_bytes()
            if len(raw) != record.payload_bytes or hashlib.sha256(raw).hexdigest() != record.payload_sha256:
                raise ValueError("changed draft payload")
            value = strict_json(raw)
            if value.get('schemaVersion') == 2:
                from .models.template_writer import DraftPayloadV2
                return DraftPayloadV2.model_validate(value)
            return DraftPayloadV1.model_validate(value)
        except (OSError, ValueError, StorageFailure, ValidationError):
            raise BackgroundFailure("JOB_STORE_CORRUPT") from None

    def read_draft(self, project, request):
        with self.guard(project, uncertain=True) as (directory, state, _workspace, _checksum):
            self.require(state, request.proof, recovery=True, expired=True)
            record = next((item for item in state.drafts if item.id == request.id), None)
            if record is None:
                raise BackgroundFailure("JOB_NOT_FOUND")
            payload = self.owned_draft(state, directory, record)
            if payload.schema_version == 2:
                from .models.template_writer import WriterDraftReadV2
                return WriterDraftReadV2(schemaVersion=2, checkpoint=record, payload=payload)
            return WriterDraftReadV1(schemaVersion=1, checkpoint=record, payload=payload)

    def owned_draft(self, state, directory, record):
        payload = self._draft(directory, record)
        try:
            images, _sources = JobAssets(self.jobs).read_pin(state, "draft", record.id)
            if set(payload.asset_pins) - images.keys():
                raise BackgroundFailure("JOB_STORE_CORRUPT")
        except (StorageFailure, OSError, ValueError):
            raise BackgroundFailure("JOB_STORE_CORRUPT") from None
        return payload

    def dispose_draft(self, state, record):
        if state.writer is not None and record.writer_epoch == state.writer.epoch:
            state.writer.draft_sequence_floor = max(state.writer.draft_sequence_floor, record.sequence)
        state.drafts = [item for item in state.drafts if item.id != record.id]
        state.asset_pins = [item for item in state.asset_pins if (item.kind, item.owner) != ("draft", record.id)]
        state.cleanup_refs = sorted(set([*state.cleanup_refs, "drafts/" + record.payload_ref + ".json"]))

    def discard_draft(self, project, request):
        return self.resolve_draft(project, request, discard=True)

    def restore_saved_draft(self, project, request):
        return self.resolve_draft(project, request, discard=False)

    def pending_input_draft(self, project, request):
        """V7 recovery: the server draft ends and the writer reattaches while the local draft keeps the queue record,
        whose corrections then save one by one through the normal prepared path."""
        with self.guard(project, uncertain=True) as (directory, state, _workspace, _checksum):
            self.require(state, request.proof, recovery=True)
            record = next((item for item in state.drafts if item.id == request.id), None)
            if record is None or (record.sequence, record.payload_sha256) != (request.sequence, request.payload_sha256):
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            payload = self._draft(directory, record)
            if payload.schema_version != 2 or payload.template_queue is None:
                raise BackgroundFailure("JOB_SCOPE_INVALID")
        return self.resolve_draft(project, request, discard=True)

    @staticmethod
    def history_resolved(state, payload):
        from .background_history_commands import command_hash
        return all(any(item.job_id == pending.job_id and item.command_id == pending.command_id
            and item.command_sha256 == command_hash(pending) for item in state.history_commands)
            for pending in payload.history_outbox)

    def use_draft(self, project, request, *, originals=None, artifacts=None, images=None):
        from .models.background import WriterCommitBindingV1
        with self.guard(project) as (_directory, state, _workspace, _checksum):
            self.require(state, request.proof, recovery=True, expired=True)
            self.preparations.reject_registered(state, request.mutation.client_mutation_id)
        def authorize(state, workspace, directory):
            from .rich_mutations import apply_rich_mutation
            from .background_history import digest_bytes
            writer = self.require(state, request.proof, recovery=True)
            self.preparations.reject_registered(state, request.mutation.client_mutation_id)
            record = next((item for item in state.drafts if item.id == request.id), None)
            if (record is None or record.writer_epoch != writer.epoch or writer.draft_id != record.id
                    or (record.sequence, record.payload_sha256) != (request.sequence, request.payload_sha256)
                    or (workspace.project_revision, digest_bytes(workspace)) != (request.canonical_revision, request.canonical_sha256)
                    or request.mutation.project_id != project or request.mutation.capture.session_id != writer.session_id):
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            payload = self.owned_draft(state, directory, record)
            proposed, _replayed = apply_rich_mutation(workspace, request.mutation)
            if (proposed.project is None or semantic(proposed.project.document) != semantic(payload.document)
                    or semantic(proposed.project.facts) != semantic(payload.facts)
                    or payload.schema_version == 2 and (proposed.project.import_issues != payload.import_issues
                        or proposed.project.import_coverage != payload.import_coverage)):
                raise BackgroundFailure("JOB_SCOPE_INVALID")
            writer.status, writer.draft_id = "attached", None
            try:
                from .models.template_writer import WriterAdvanceV2
                advance_type = WriterAdvanceV2 if workspace.schema_version == 7 else WriterAdvanceV1
                self.advance(state, workspace, digest_bytes(workspace), advance_type(schemaVersion=request.schema_version, proof=request.proof,
                    canonicalRevision=workspace.project_revision, canonicalSha256=digest_bytes(workspace),
                    actionCursor=max(record.action_cursor, writer.acknowledged_cursor), touches=payload.touches))
            finally:
                writer.status, writer.draft_id = "recovering", record.id
            self.write(directory, state)
            return WriterCommitBindingV1(epoch=writer.epoch, incarnation=writer.incarnation,
                actionCursor=writer.acknowledged_cursor, touchGeneration=writer.touch_generation,
                draftId=record.id, draftSequence=record.sequence, draftSha256=record.payload_sha256)
        _workspace, replayed = self.coordinator.manual(project, request.mutation, authorize=authorize,
            originals=originals, artifacts=artifacts, images=images)
        with self.guard(project) as (_directory, state, workspace, checksum):
            self.require(state, request.proof, recovery=True, expired=True)
            return self.mutation_view(state, workspace, checksum, request.mutation, replayed)

    def resolve_draft(self, project, request, *, discard):
        with self.guard(project) as (directory, state, workspace, checksum):
            writer = self.require(state, request.proof, recovery=True)
            record = next((item for item in state.drafts if item.id == request.id), None)
            if record is None or (record.sequence, record.payload_sha256) != (request.sequence, request.payload_sha256):
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            if (request.canonical_revision, request.canonical_sha256) != (workspace.project_revision, checksum):
                raise BackgroundFailure("DEPENDENCY_CHANGED")
            payload = self._draft(directory, record)
            if not discard:
                replay = {item.client_mutation_id: item.request_sha256 for item in workspace.mutation_replay}
                if (workspace.project is None or semantic(payload.document) != semantic(workspace.project.document)
                        or semantic(payload.facts) != semantic(workspace.project.facts)
                        or payload.schema_version == 2 and (payload.import_issues != workspace.project.import_issues
                            or payload.import_coverage != workspace.project.import_coverage)
                        or any(replay.get(item.client_mutation_id) != mutation_sha256(item) for item in payload.outbox)
                        or not self.history_resolved(state, payload)):
                    raise BackgroundFailure("DEPENDENCY_CHANGED")
            if record.writer_epoch == writer.epoch:
                writer.draft_id, writer.status = None, "attached"
                from .models.template_writer import WriterAdvanceV2
                advance_type = WriterAdvanceV2 if workspace.schema_version == 7 else WriterAdvanceV1
                advance = advance_type(schemaVersion=payload.schema_version, proof=request.proof,
                    canonicalRevision=workspace.project_revision, canonicalSha256=checksum,
                    actionCursor=max(record.action_cursor, writer.acknowledged_cursor), touches=payload.touches)
                self.advance(state, workspace, checksum, advance)
            self.dispose_draft(state, record)
            if payload.history_outbox:
                writer.status = "recovering"
                self.live.pop(project, None)
            self.write(directory, state)
            return self.view(state, workspace, checksum)
