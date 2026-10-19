"""Durable scoped proposals with one admitted attempt and no publication on reply."""

import asyncio
import threading
import time
from pydantic import ValidationError
from packages.resume_core.background_store import BackgroundFailure

from packages.resume_core.models.rich_mutations import RichMutation, PutRecord
from packages.resume_core.models.rich_workspace import RichSyncRecord
from packages.resume_core.rich_dependencies import dependencies_current
from packages.resume_core.rich_fields import set_text, working_field, occurrences
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_snapshot_merge import reconcile
from packages.resume_core.rich_assembly import identity
from packages.resume_core.rich_sync import (RichReconcileProposal, exact_completion,
    scoped_dependencies, selection_parts, selection_checksum, sync_prompt, linked_field_steps, RichCompletionRequest)
from packages.resume_core.preferences import PreferencesFailure
from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt, selection_targets, selection_text, plain_rewrite_steps
from .rewrite_timing import add_phase, measure
from .gui_admission import QueuedProvider, AdmissionCancelled
from .gui_content import generate_admitted
from .gui_projects import ProjectFailure
from .lifecycle import OperationFiles, SpikeError
from .providers.content import ContentFailure, ContentInput, GenerationPolicy


class RichSynchronization:
    def panel_preview(self, identifier, request):
        from packages.resume_core.rich_panel import panel_mutation
        try:
            mutation = panel_mutation(self.read(identifier), request)
        except ValueError as error:
            raise ProjectFailure(str(error), 409) from None
        return self.response(identifier) if mutation is None else self.preview(identifier, mutation)

    async def panel_rich(self, identifier, request):
        from packages.resume_core.rich_panel import RichPanelProposal, narrative_steps, has_exact_fields
        workspace = self.read(identifier)
        ids = set(request.record_ids)
        records = {record.id: record for record in workspace.project.facts.records}
        blocks = [block for block in workspace.project.document.blocks() if any(
            link.kind == "citation" and link.record_id in ids for link in block.provenance)
            and not any(link.kind == "field_binding" for link in block.provenance) and not has_exact_fields(block)]
        digest_ids = {key for key in ids & records.keys() if records[key].kind == "claim"}
        protected = [block for block in workspace.project.document.blocks() if has_exact_fields(block)
            and any(link.kind == "citation" and link.record_id in digest_ids for link in block.provenance)]
        sync = self.add_sync(identifier, request.capture, [block.id for block in [*blocks, *protected]], "panel", sorted(ids & records.keys()))
        sync.fact_ids = sorted(ids)
        if any(link.kind == "citation" and link.record_id in ids - records.keys() for block in blocks for link in block.provenance):
            sync.status, sync.error_code = "conflict", "DELETED_RECORD_MENTIONS"
            self.publish_sync(identifier, sync)
            return self.response(identifier)
        if not blocks:
            sync.status = "conflict" if protected else "applied"
            sync.error_code = "NARRATIVE_REQUIRES_SCOPED_EDIT" if protected else None
            self.publish_sync(identifier, sync)
            return self.response(identifier)
        try:
            proposal = await self.sync_content(identifier, sync, {"blocks": [block.model_dump(mode="json", by_alias=True) for block in blocks],
                "facts": [records[id].model_dump(mode="json", by_alias=True) for id in sorted(ids & records.keys())],
                "deletedRecordIds": sorted(ids - records.keys())}, RichPanelProposal)
            sync.proposed_steps = narrative_steps(workspace, blocks, proposal)
            sync.ready = bool(sync.proposed_steps)
            sync.status = "conflict" if proposal.uncertain or protected else "pending" if sync.ready else "applied"
            if protected:
                sync.error_code = "NARRATIVE_REQUIRES_SCOPED_EDIT"
            if not dependencies_current(self.workspaces[identifier], sync.dependencies):
                sync.status, sync.ready, sync.error_code = "stale", False, "STALE_SYNC"
        except (ContentFailure, AdmissionCancelled, ProjectFailure, SpikeError, ValidationError, ValueError) as error:
            sync.status, sync.error_code = "failed", getattr(error, "code", "INVALID_RESULT")
        self.publish_sync(identifier, sync)
        return self.response(identifier)

    def publish_sync(self, identifier, sync):
        with self.state_lock:
            if identifier in self.deleted_ids:
                return
            jobs = getattr(self, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                committed, _checksum = self.storage.read_committed(identifier)
                previous = next((item for item in committed.sync_records if item.id == sync.id), None)
                if previous is not None and previous.status in {"stale", "applied"} and not previous.ready and not previous.proposed_steps:
                    reconcile(sync, previous)
                    return
            records = self.workspaces[identifier].sync_records
            for index, item in enumerate(records):
                if item.id == sync.id:
                    records[index] = sync
                    break
            if self.persist(identifier) == "failed":
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)

    def preview(self, identifier, request):
        workspace = self.read(identifier)
        try:
            result, _ = apply_rich_mutation(workspace, request)
        except (ValueError, ValidationError) as error:
            raise ProjectFailure(getattr(error, "code", "RICH_CONTENT_INVALID"), 409) from None
        response = self.response(identifier)
        response.workspace = result
        return response

    async def cancel_sync_action(self, identifier, capture):
        jobs = getattr(self, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            return await jobs.fixed.invalidate_action(identifier, capture)
        workspace = self.read(identifier)
        for sync in workspace.sync_records:
            if sync.action_id == capture.action_id:
                jobs = getattr(self, "background_jobs", None)
                if jobs is not None and jobs.enabled:
                    self.disposition(identifier, sync.id, "stale", "CANCELLED")
                if (identifier, sync.id) in self.tasks:
                    await self.cancel(identifier, sync.id)
        return self.response(identifier)

    async def sync_content(self, identifier, sync, payload, result_type):
        selected = self.provider_factory()
        if selected is None:
            raise ContentFailure("CONNECTION_REQUIRED")
        plain = result_type is PlainTextReply
        try:
            effort = self.preferences.load().rewrite_reasoning_effort if plain and self.preferences else None
        except PreferencesFailure as error:
            raise ContentFailure(error.code) from None
        key = (identifier, sync.id)
        cancel, files = threading.Event(), OperationFiles(self.temp_root)
        self.tasks[key], self.cancels[key], self.files[key] = asyncio.current_task(), cancel, files
        operation = self.new_operation(identifier, "rewrite_prose" if sync.kind == "rewrite" else "reconcile_edits")
        operation.action_id, operation.dependencies = sync.action_id, sync.dependencies
        def admitted():
            with self.state_lock:
                self.finish_operation(identifier, operation.id, "running")
                if self.persist(identifier) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
        prompt = plain_prompt(payload["instruction"], payload["text"]) if plain else sync_prompt(
            sync.kind if sync.kind in {"rewrite", "panel"} else "reconcile", payload, self.workspaces[identifier].rules_used)
        request = ContentInput(prompt, result_type, GenerationPolicy(model=selected[1], timeout_seconds=180,
            allow_repair=False, reasoning_effort=effort))
        def run():
            with files.open():
                return generate_admitted(QueuedProvider(selected[0], admitted), request, files, cancel)
        try:
            waiting = time.perf_counter()
            async with self.worker_slot(cancel):
                add_phase("worker_queue", time.perf_counter() - waiting)
                response = await asyncio.to_thread(run)
            if cancel.is_set():
                raise ContentFailure("CANCELLED")
            value = result_type.model_validate(response.value)
            with self.state_lock:
                # The caller saves this status and the compiled proposal together before returning.
                self.finish_operation(identifier, operation.id, "completed")
            return value
        except Exception as error:
            with self.state_lock:
                self.finish_operation(identifier, operation.id, "cancelled" if cancel.is_set() else "failed", getattr(error, "code", "INVALID_RESULT"))
                self.persist(identifier)
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
            raise
        finally:
            self.tasks.pop(key, None); self.cancels.pop(key, None); self.files.pop(key, None)

    def add_sync(self, identifier, capture, block_ids, kind, records=()):
        with self.state_lock:
            self.require_agent_writable(identifier)
            workspace = self.read(identifier)
            if not dependencies_current(workspace, capture.dependencies):
                raise ProjectFailure("STALE_MUTATION", 409)
            try:
                stamps = scoped_dependencies(workspace, block_ids, records)
            except ValueError:
                raise ProjectFailure("STALE_SELECTION", 409) from None
            sync = RichSyncRecord(id=identity("sync"), status="pending", actionId=capture.action_id,
                blockIds=block_ids, fieldKeys=[], factIds=list(records), dependencies=stamps, errorCode=None, kind=kind)
            self.workspaces[identifier].sync_records.append(sync)
            if self.persist(identifier) == "failed":
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            return sync

    def disposition(self, identifier, sync_id, status, error_code=None):
        with self.state_lock:
            self.read(identifier)
            self.require_agent_writable(identifier)
            jobs = getattr(self, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                state = jobs.store.open(identifier)
                if any(job.submission.input.kind == "rich_sync" and job.submission.input.id == sync_id for job in state.jobs):
                    raise ProjectFailure("JOB_SCOPE_INVALID", 409)
            sync = next((item for item in self.workspaces[identifier].sync_records if item.id == sync_id), None)
            if sync is None:
                raise ProjectFailure("SYNC_NOT_FOUND", 404)
            if jobs is not None and jobs.enabled and status == "applied" and sync.proposed_steps:
                try:
                    if not jobs.publisher.legacy_sync_saved(identifier, sync):
                        raise ProjectFailure("JOB_SCOPE_INVALID", 409)
                except BackgroundFailure as error:
                    raise ProjectFailure(error.code, 409) from None
            sync.status, sync.ready, sync.proposed_steps = ("conflict" if status == "applied" and sync.status == "conflict" else status), False, []
            sync.error_code = error_code
            self.publish_sync(identifier, sync)
            return self.response(identifier)

    def resolve_conflict(self, identifier, sync_id, capture):
        with self.state_lock:
            workspace = self.read(identifier)
            original = next((item for item in workspace.sync_records if item.id == sync_id), None)
            if original is None:
                raise ProjectFailure("SYNC_NOT_FOUND", 404)
            steps = linked_field_steps(workspace, original.fact_ids, original.field_keys)
            current_ids = {record.id for record in workspace.project.facts.records}
            jobs = getattr(self, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                self.disposition(identifier, sync_id, "stale", "SYNC_SUPERSEDED")
            sync = self.add_sync(identifier, capture, [step.block.id for step in steps], "conflict", [id for id in original.fact_ids if id in current_ids])
            sync.proposed_steps, sync.ready = steps, bool(steps)
            sync.status = "pending" if steps else "conflict"
            if not steps:
                sync.error_code = "NARRATIVE_REQUIRES_SCOPED_EDIT"
            self.publish_sync(identifier, sync)
            return self.response(identifier)

    async def retry_rewrite(self, identifier, sync_id, capture):
        from packages.resume_core.rich_sync import RichRewriteRequest
        workspace = self.read(identifier)
        sync = next((item for item in workspace.sync_records if item.id == sync_id), None)
        if sync is None or sync.selection is None or sync.instruction is None:
            if sync is None or sync.kind != "panel":
                raise ProjectFailure("SYNC_NOT_FOUND", 404)
            if not dependencies_current(workspace, sync.dependencies):
                self.disposition(identifier, sync_id, "stale")
                raise ProjectFailure("STALE_SELECTION", 409)
            from packages.resume_core.rich_panel import RichPanelSyncRequest
            jobs = getattr(self, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                self.disposition(identifier, sync_id, "stale", "SYNC_SUPERSEDED")
            return await self.panel_rich(identifier, RichPanelSyncRequest(capture=capture, recordIds=sync.fact_ids))
        if not dependencies_current(workspace, sync.dependencies):
            self.disposition(identifier, sync_id, "stale")
            raise ProjectFailure("STALE_SELECTION", 409)
        selection = sync.selection.model_copy(deep=True)
        selection.capture = capture
        jobs = getattr(self, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            self.disposition(identifier, sync_id, "stale", "SYNC_SUPERSEDED")
        return await self.rewrite_rich(identifier, RichRewriteRequest(selection=selection, instruction=sync.instruction))

    async def complete_rich(self, identifier, request):
        workspace = self.read(identifier)
        steps, conflicts = exact_completion(workspace, request)
        touched = {step.record.id if isinstance(step, PutRecord) else step.record_id for step in steps}
        blocks = [block for block in workspace.project.document.blocks() if block.id in request.block_ids]
        linked = {link.record_id for block in blocks for link in block.provenance if link.kind == "citation"}
        records = {record.id: record for record in workspace.project.facts.records}
        digest_ids = {key for key in linked if key in records and records[key].kind == "claim"}
        related = [block for block in workspace.project.document.blocks() if block.id not in request.block_ids
            and any(link.kind == "citation" and link.record_id in digest_ids for link in block.provenance)]
        sync = self.add_sync(identifier, request.capture, request.block_ids, "completion", sorted(touched | linked))
        if related:
            sync.dependencies = scoped_dependencies(workspace, [*request.block_ids, *[b.id for b in related]], sorted(touched | linked))
        sync.proposed_steps, sync.ready = steps, bool(steps)
        sync.field_keys = [key for _, key in conflicts]
        sync.status = "conflict" if conflicts else "pending"
        try:
            # Exact fields and moves are deterministic. Only linked narrative needs interpretation.
            exact_blocks = {identifier for group in occurrences(workspace.project.document).values() for identifier in group.block_ids}
            narrative = [block for block in blocks if any(link.kind == "citation" for link in block.provenance)
                and (any(link.kind == "citation" and link.record_id in digest_ids - touched for link in block.provenance)
                    or block.id not in exact_blocks and not any(link.kind == "field_binding" for link in block.provenance))]
            if request.interpret and narrative and linked - touched:
                sync.kind = "reconciliation"
                proposal = await self.sync_content(identifier, sync, {"blocks": [block.model_dump(mode="json", by_alias=True) for block in narrative],
                    "relatedBlocks": [block.model_dump(mode="json", by_alias=True) for block in related],
                    "facts": [records[key].model_dump(mode="json", by_alias=True) for key in sorted(linked - touched) if key in records]}, RichReconcileProposal)
                edits = {step.record.id: step.record for step in steps if isinstance(step, PutRecord)}
                for record in proposal.records:
                    original = records.get(record.id)
                    if original is None or record.id not in linked - touched or any(getattr(original, key, None) != getattr(record, key, None)
                            for key in ("kind", "origin", "evidence", "job_id", "subproject_id")):
                        raise ValueError("RECONCILE_SCOPE_INVALID")
                    edits[record.id] = record
                    record.user_corrected = True
                for update in proposal.updates:
                    original = records.get(update.record_id)
                    if original is None or update.record_id not in linked - touched:
                        raise ValueError("RECONCILE_SCOPE_INVALID")
                    target = working_field(original, update.field_key)
                    if target is None or (target.value is not None and not isinstance(target.value, str)):
                        raise ValueError("RECONCILE_SCOPE_INVALID")
                    copy = edits.setdefault(original.id, original.model_copy(deep=True))
                    set_text(copy, update.field_key, update.text)
                for update in proposal.uncertain:
                    original = records.get(update.record_id)
                    if original is None or original.id not in linked - touched:
                        raise ValueError("RECONCILE_SCOPE_INVALID")
                    copy = edits.setdefault(original.id, original.model_copy(deep=True))
                    target = working_field(copy, update.field_key)
                    if target is None:
                        raise ValueError("RECONCILE_SCOPE_INVALID")
                    target.status, target.pending_raw_text = "pending", update.text
                    copy.user_corrected = True
                    sync.status = "conflict"
                    sync.field_keys.append(update.field_key)
                sync.proposed_steps = [*[step for step in steps if not isinstance(step, PutRecord)],
                    *[PutRecord(kind="put_record", beforeRevision=records[key].revision, record=value) for key, value in edits.items()]]
                sync.ready = bool(sync.proposed_steps)
            if not dependencies_current(self.workspaces[identifier], sync.dependencies):
                sync.status, sync.ready, sync.error_code = "stale", False, "STALE_SYNC"
            elif not sync.ready and sync.status != "conflict":
                sync.status = "applied"
        except (ContentFailure, AdmissionCancelled, ProjectFailure, SpikeError, ValidationError, ValueError) as error:
            sync.status, sync.error_code = "failed", getattr(error, "code", "INVALID_RESULT")
        self.publish_sync(identifier, sync)
        return self.response(identifier)

    async def rewrite_rich(self, identifier, request):
        with measure("prepare"):
            workspace = self.read(identifier)
            try:
                parts = selection_parts(workspace, request.selection)
                if selection_checksum(parts) != request.selection.text_sha256:
                    raise ValueError("STALE_SELECTION")
                targets = selection_targets(workspace, request.selection)
            except ValueError as error:
                raise ProjectFailure(str(error), 409) from None
            target_ids = list(dict.fromkeys([*request.selection.block_ids, *(target.block.id for target in targets)]))
            records = {link.record_id for target in targets for link in target.block.provenance if link.kind in {"citation", "field_binding"}}
            sync = self.add_sync(identifier, request.selection.capture, target_ids, "rewrite", sorted(records))
            sync.selection, sync.instruction = request.selection, request.instruction
        try:
            with measure("content"):
                proposal = await self.sync_content(identifier, sync, {"instruction": request.instruction,
                    "text": selection_text(targets)}, PlainTextReply)
                sync.rewrite_source, sync.rewrite_result = selection_text(targets), proposal.text
            with measure("proposal"):
                steps = plain_rewrite_steps(workspace, request.selection, proposal)
                candidate = workspace
                if steps:
                    preview = RichMutation(schemaVersion=1, projectId=identifier, clientMutationId=identity("preview"),
                        actionId=sync.action_id, kind="rewrite", capture=request.selection.capture, steps=steps)
                    candidate, _ = apply_rich_mutation(workspace, preview)
                remaining = occurrences(candidate.project.document)
                removed = [{"recordId": group.record_id, "fieldKey": group.key, "rootId": group.root}
                    for key, group in occurrences(workspace.project.document).items()
                    if key not in remaining and set(group.block_ids) & set(target_ids)]
                completion = RichCompletionRequest(capture=request.selection.capture, blockIds=[block.id for block in candidate.project.document.blocks()
                    if block.id not in {old.id for old in workspace.project.document.blocks()} or block.id in target_ids],
                    movedIds=[], removedFields=removed, interpret=False)
                fact_steps, conflicts = exact_completion(candidate, completion) if steps else ([], [])
                sync.proposed_steps, sync.ready = [*steps, *fact_steps], bool(steps or fact_steps)
                sync.status = "conflict" if conflicts else "pending" if sync.ready else "applied"
                if not dependencies_current(self.workspaces[identifier], sync.dependencies):
                    sync.status, sync.ready, sync.error_code = "stale", False, "STALE_SYNC"
        except (ContentFailure, AdmissionCancelled, ProjectFailure, SpikeError, ValidationError, ValueError) as error:
            sync.status, sync.error_code = "failed", getattr(error, "code", "INVALID_RESULT")
        with measure("publish"):
            self.publish_sync(identifier, sync)
        with measure("response"):
            return self.response(identifier)
