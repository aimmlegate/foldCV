"""Canonical project state with guarded creation, edits and durable checkpoints."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import threading
import uuid

from packages.resume_core.dates import partial_date
from packages.resume_core.gui_annotations import initial_annotations
from packages.resume_core.gui_derived import digest, initial_derived
from packages.resume_core.gui_drafting import GuiDraftRequest
from packages.resume_core.gui_normalization import GuiNormalizeRequest, canonical_source, source_fingerprint
from packages.resume_core.gui_rendering import render_input
from packages.resume_core.gui_projection import compatibility_views
from packages.resume_core.gui_mutations import apply_mutation
from packages.resume_core.gui_selection import normalized_text
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.models.contracts import Source, Usage
from packages.resume_core.models.recovery import (WorkspaceV5, ProjectV4, Generation, GenerationStage,
    GuiOperation, GuiOperationEvent, Dependencies, RenderSnapshotV4, record_slot)
from packages.resume_core.rendering.docx_errors import DocxFailure
from packages.resume_core.rendering.template import PACKAGE_SHA256, renderer_sha256, RenderFailure
from .extracting import run_extract, UploadFailure
from .gui_admission import AdmissionCancelled, QueuedProvider
from .gui_normalization_content import GuiNormalizationContentService
from .gui_drafting_content import GuiDraftingContentService
from .gui_rendering import GuiDocxRenderer
from .lifecycle import OperationFiles, SpikeError
from .providers.content import ContentFailure


class ProjectFailure(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def now():
    return datetime.now(timezone.utc)


def identity(prefix):
    return prefix + "-" + uuid.uuid4().hex


class GuiProjectService:
    def __init__(self, temp_root: Path, rules, provider_factory, *, clock=now,
                 worker_slot=None, cleanup_error=None, renderer=None, storage=None):
        self.temp_root, self.rules, self.provider_factory = temp_root, rules, provider_factory
        self.clock = clock
        self.worker_slot = worker_slot or self._local_slot
        self.cleanup_error = cleanup_error or (lambda _error: None)
        self.renderer = renderer or GuiDocxRenderer()
        self.storage = storage
        self.loaded = storage is None
        self.state_lock = threading.RLock()
        self.save_errors, self.saved_hashes, self.saved_revisions, self.load_errors = {}, {}, {}, {}
        self.workspaces = {}
        self.originals = {}
        self.artifacts = {}
        self.tasks = {}
        self.cancels = {}
        self.files = {}
        self.cache = {}
        self.selection_epochs = {}

    def ensure_loaded(self):
        if self.loaded:
            return
        with self.state_lock:
            if self.loaded:
                return
            try:
                loaded, self.load_errors, _registry = self.storage.load_all()
            except ProjectStoreFailure as error:
                raise ProjectFailure(error.code, 503) from None
            for id, (workspace, originals, artifacts) in loaded.items():
                self.workspaces[id] = workspace
                self.originals.update(originals)
                self.artifacts.update(artifacts)
                owner = self.owner(workspace)
                changed = False
                for generation in workspace.generations:
                    if generation.status in {"queued", "running"}:
                        generation.status = "interrupted"
                        changed = True
                        for stage in generation.stages:
                            if stage.status in {"queued", "running"}:
                                stage.status, stage.error_code = "interrupted", "INTERRUPTED"
                for operation in owner.operations:
                    if operation.status in {"queued", "running"}:
                        operation.status, operation.error_code = "interrupted", "INTERRUPTED"
                        self._event(operation, "operation.failed", save=False)
                        changed = True
                if workspace.pre_draft:
                    active = next((source for source in owner.sources if source.id == workspace.pre_draft.selected_source_id), None)
                    if active and active.parser == "pending":
                        active.parser = "interrupted"
                        active.warnings = ["EXTRACT_INTERRUPTED"]
                        workspace.pre_draft.warnings = ["EXTRACT_INTERRUPTED", "NO_USABLE_TEXT"]
                        changed = True
                self.saved_hashes[id] = digest(workspace.model_dump(mode="json", by_alias=True))
                self.saved_revisions[id] = (workspace.project_revision, workspace.document_revision)
                if changed:
                    self.persist(id)
            self.loaded = True

    def persist(self, id):
        if self.storage is None:
            return "in_memory"
        with self.state_lock:
            if id not in self.workspaces:
                self.save_errors[id] = "PROJECT_DELETED"
                return "failed"
            workspace = self.workspaces[id]
            try:
                snapshot = self.read_memory(id)
                self.storage.save(snapshot, self.originals, self.artifacts)
                self.saved_hashes[id] = digest(snapshot.model_dump(mode="json", by_alias=True))
                self.saved_revisions[id] = (snapshot.project_revision, snapshot.document_revision)
                self.save_errors.pop(id, None)
                return "durable"
            except ProjectStoreFailure as error:
                self.save_errors[id] = error.code
                return "failed"

    def durability(self, id):
        if self.storage is None:
            return "in_memory"
        if id in self.save_errors:
            return "failed"
        if self.saved_hashes.get(id) == digest(self.workspaces[id].model_dump(mode="json", by_alias=True)):
            return "durable"
        return "pending"

    def read_memory(self, id):
        return WorkspaceV5.model_validate(self.workspaces[id].model_dump(by_alias=True))

    @asynccontextmanager
    async def _local_slot(self, cancel):
        if cancel.is_set():
            raise AdmissionCancelled()
        yield

    def read(self, id):
        self.ensure_loaded()
        workspace = self.workspaces.get(id)
        if workspace is None:
            if id in self.load_errors:
                raise ProjectFailure(self.load_errors[id], 409)
            raise ProjectFailure("PROJECT_NOT_FOUND", 404)
        with self.state_lock:
            return self.read_memory(id)

    def owner(self, workspace):
        return workspace.project or workspace.pre_draft

    def mutate(self, id, mutation):
        self.read(id)
        with self.state_lock:
            result = apply_mutation(self.workspaces[id], mutation, self.clock().isoformat())
            result.persistence = "durable" if self.persist(id) == "durable" else "memory" if self.storage is None else "failed"
            return result

    def rename(self, id, request):
        self.read(id)
        workspace = self.workspaces[id]
        if workspace.project_revision != request.base_revision:
            raise ProjectFailure("PROJECT_REVISION_CHANGED")
        title = request.title.strip()
        try:
            title.encode("utf-8")
        except UnicodeError:
            raise ProjectFailure("TITLE_INVALID", 422) from None
        if not title:
            raise ProjectFailure("TITLE_REQUIRED", 422)
        if title != workspace.title or not workspace.title_manually_set:
            workspace.title, workspace.title_manually_set = title, True
            workspace.project_revision += 1
            if workspace.project:
                workspace.project.revision = workspace.project_revision
            workspace.updated_at = self.clock().isoformat()
        self.persist(id)

    def allocate(self, title):
        self.ensure_loaded()
        stamp = self.clock()
        id = identity("project")
        workspace = WorkspaceV5.model_validate({"schemaVersion": 5, "projectId": id,
            "projectRevision": 1, "documentRevision": 1, "title": title, "titleManuallySet": False,
            "createdAt": stamp.isoformat(), "updatedAt": stamp.isoformat(), "project": None,
            "preDraft": {"sources": [], "facts": [], "operations": [], "renders": [],
                "selectedInput": "text", "selectedSourceId": None, "extractedText": "", "warnings": [], "extractionFingerprint": None},
            "formattingAsOf": partial_date(stamp.date().isoformat()).model_dump(),
            "sourceObservedAt": None, "rulesUsed": None, "editorialPlan": None, "annotations": [],
            "relatedUpdateSuggestions": [], "derivedState": None, "undoSlots": {}, "editSessions": {},
            "mutationReplay": [], "generations": [], "sourceExclusions": [], "migrationNotices": [], "legacyData": None})
        self.workspaces[id] = workspace
        self.persist(id)
        return id

    async def select(self, data, name, pasted, id=None):
        id = id or self.allocate("Новое резюме" if pasted else name)
        workspace = self.workspaces[id]
        if workspace.project is not None or any(not task.done() for (pid, _), task in self.tasks.items() if pid == id):
            raise ProjectFailure("PROJECT_GENERATION_ACTIVE")
        source_id = identity("source")
        self.selection_epochs[id] = source_id
        source = Source.model_validate({"id": source_id, "revision": 1, "originalName": name,
            "mimeType": "text/plain" if pasted else "application/octet-stream",
            "byteSha256": hashlib.sha256(data).hexdigest(), "byteRef": f"sources/{source_id}/original",
            "parser": "pending", "parserVersion": "1", "units": [], "overlays": [], "warnings": []})
        self.originals[(id, source_id)] = bytes(data)
        pre = workspace.pre_draft
        pre.sources.append(source)
        pre.selected_input = "text" if pasted else "file"
        pre.selected_source_id, pre.extracted_text = source_id, ""
        pre.extraction_fingerprint, pre.warnings = None, ["EXTRACT_PENDING"]
        self.persist(id)
        files, cancel = OperationFiles(self.temp_root), threading.Event()
        try:
            async with self.worker_slot(cancel):
                with files.open():
                    result = await run_extract(data, name, pasted, files)
            source = canonical_source(result, source_id=source_id)
            pre.sources = [source if item.id == source_id else item for item in pre.sources]
            if self.selection_epochs[id] == source_id:
                pre.extracted_text = "".join(unit.text for unit in source.units)
                pre.warnings = source.warnings[:]
                if not pre.extracted_text.strip():
                    pre.warnings = list(dict.fromkeys([*pre.warnings, "NO_USABLE_TEXT"]))
                pre.extraction_fingerprint = source_fingerprint([source])
        except UploadFailure as error:
            source.parser, source.warnings = "failed", [error.code]
            if self.selection_epochs[id] == source_id:
                pre.warnings = [error.code, "NO_USABLE_TEXT"]
        except SpikeError as error:
            self.cleanup_error(error)
            if self.selection_epochs[id] == source_id:
                pre.warnings = [error.code, "NO_USABLE_TEXT"]
        workspace.updated_at = self.clock().isoformat()
        self.persist(id)
        return self.read(id)

    def dependencies(self, workspace, source_ids, rules):
        sources = [item for item in self.owner(workspace).sources if item.id in source_ids]
        fingerprint = source_fingerprint(sources)
        return Dependencies(projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
            rulesSha256=rules.sha256, sourceFingerprint=fingerprint,
            dependencyFingerprint=digest({"source": fingerprint, "rules": rules.sha256,
                "formattingAsOf": workspace.formatting_as_of.model_dump(), "projectRevision": workspace.project_revision,
                "documentRevision": workspace.document_revision}))

    def start(self, id, previous=None):
        self.read(id)
        if self.persist(id) == "failed":
            raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
        workspace = self.workspaces.get(id)
        if workspace is None:
            raise ProjectFailure("PROJECT_NOT_FOUND", 404)
        if any(not task.done() for (pid, _), task in self.tasks.items() if pid == id):
            raise ProjectFailure("PROJECT_GENERATION_ACTIVE")
        if previous is None:
            if workspace.pre_draft is None:
                raise ProjectFailure("DOCUMENT_ALREADY_CREATED")
            pre = workspace.pre_draft
            if not pre.extracted_text.strip() or pre.extraction_fingerprint is None:
                raise ProjectFailure("NO_USABLE_TEXT", 422)
            source_ids = [pre.selected_source_id]
            workspace.formatting_as_of = partial_date(self.clock().date().isoformat())
        else:
            old = self.generation(id, previous)
            if old.status not in {"failed", "cancelled", "interrupted"}:
                raise ProjectFailure("GENERATION_NOT_RETRYABLE")
            if old.stages[3].status == "completed" and old.dependencies.document_revision != workspace.document_revision:
                raise ProjectFailure("STALE_GENERATION")
            source_ids = old.source_ids[:]
        selected = self.provider_factory()
        if selected is None:
            raise ProjectFailure("CONNECTION_REQUIRED", 409)
        rules = self.rules.load()
        deps = self.dependencies(workspace, source_ids, rules)
        generation = Generation(id=identity("generation"), projectId=id, status="queued", dependencies=deps,
            rulesUsed=rules, sourceIds=source_ids, formattingAsOf=workspace.formatting_as_of,
            stages=[GenerationStage(kind=kind, status="queued", dependencyFingerprint=deps.dependency_fingerprint,
                resultFingerprint=None, operationId=None, errorCode=None, docxError=None)
                for kind in ("extract", "normalize_semantics", "draft_prose", "assemble", "render")])
        cached = {}
        if previous:
            old = self.generation(id, previous)
            if old.dependencies == deps:
                cached = self.cache.get((id, previous), {}).copy()
                for index, stage in enumerate(old.stages):
                    if stage.status == "completed" and stage.dependency_fingerprint == deps.dependency_fingerprint:
                        generation.stages[index] = stage.model_copy(deep=True)
        generation.stages[0].status = "completed"
        generation.stages[0].result_fingerprint = deps.source_fingerprint
        workspace.generations.append(generation)
        if self.persist(id) == "failed":
            workspace.generations.remove(generation)
            raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
        key = (id, generation.id)
        self.cache[key] = cached
        self.cancels[key] = threading.Event()
        self.tasks[key] = asyncio.create_task(self._run(workspace, generation, selected))
        return generation.id

    def generation(self, id, gid):
        workspace = self.workspaces.get(id)
        generation = next((item for item in workspace.generations if item.id == gid), None) if workspace else None
        if generation is None:
            raise ProjectFailure("GENERATION_NOT_FOUND", 404)
        return generation

    def _event(self, operation, type, save=True):
        operation.events.append(GuiOperationEvent(requestId=operation.id, sequence=len(operation.events),
            type=type, stage=operation.kind, usage=operation.usage))
        if save:
            self.persist(operation.project_id)

    async def _content(self, workspace, generation, stage, request, selected):
        cancel = self.cancels[(workspace.project_id, generation.id)]
        operation = GuiOperation(id=identity("operation"), kind=stage.kind, status="queued",
            baseRevision=workspace.project_revision, usage=None, events=[], projectId=workspace.project_id,
            capturedDocumentRevision=workspace.document_revision, dependencies=generation.dependencies,
            rulesUsed=generation.rules_used, targetFieldIds=[], resultFingerprint=None, errorCode=None)
        self.owner(workspace).operations.append(operation)
        stage.operation_id = operation.id
        if self.persist(workspace.project_id) == "failed":
            raise ProjectFailure("PROJECT_SAVE_FAILED", 503)

        def admitted():
            with self.state_lock:
                operation.status, stage.status = "running", "running"
                operation.usage = Usage(logicalAttempts=1, internalInferenceRequests=None,
                    reportedInputTokens=None, reportedOutputTokens=None)
                self._event(operation, "operation.started")
                if workspace.project_id in self.save_errors:
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)

        provider, model = selected
        queued = QueuedProvider(provider, admitted)
        service = (GuiNormalizationContentService if stage.kind == "normalize_semantics" else GuiDraftingContentService)(queued, model)
        files = OperationFiles(self.temp_root)
        self.files[(workspace.project_id, generation.id)] = files

        def run():
            with files.open():
                return service.run(request, generation.rules_used, files, cancel)

        try:
            async with self.worker_slot(cancel):
                result, usage = await asyncio.to_thread(run)
            operation.usage = Usage(logicalAttempts=usage["logicalAttempts"], internalInferenceRequests=usage["inferenceCount"],
                reportedInputTokens=usage["inputTokens"], reportedOutputTokens=usage["outputTokens"])
            if cancel.is_set():
                raise ContentFailure("CANCELLED", logical_attempts=operation.usage.logical_attempts)
            operation.result_fingerprint = digest(result.model_dump(mode="json", by_alias=True))
            operation.status = "completed"
            self._event(operation, "usage.updated")
            self._event(operation, "operation.completed")
            return result
        except (ContentFailure, AdmissionCancelled) as error:
            attempts = error.logical_attempts if isinstance(error, ContentFailure) else 0
            usage = error.usage if isinstance(error, ContentFailure) else None
            operation.usage = Usage(logicalAttempts=attempts, internalInferenceRequests=None,
                reportedInputTokens=usage.input_tokens if usage else None, reportedOutputTokens=usage.output_tokens if usage else None)
            operation.status = "cancelled" if cancel.is_set() or isinstance(error, AdmissionCancelled) else "failed"
            operation.error_code = "CANCELLED" if operation.status == "cancelled" else error.code
            self._event(operation, "cancelled" if operation.status == "cancelled" else "operation.failed")
            raise
        except SpikeError as error:
            self.cleanup_error(error)
            operation.status, operation.error_code = "failed", error.code
            operation.usage = operation.usage or Usage(logicalAttempts=1 if operation.events else 0,
                internalInferenceRequests=None, reportedInputTokens=None, reportedOutputTokens=None)
            self._event(operation, "operation.failed")
            raise
        except Exception:
            operation.status, operation.error_code = "failed", "INVALID_RESULT"
            operation.usage = operation.usage or Usage(logicalAttempts=1 if operation.events else 0,
                internalInferenceRequests=None, reportedInputTokens=None, reportedOutputTokens=None)
            self._event(operation, "operation.failed")
            raise

    async def _run(self, workspace, generation, selected):
        key = (workspace.project_id, generation.id)
        cancel, cached = self.cancels[key], self.cache[key]
        stage = generation.stages[0]
        generation.status = "running"
        try:
            for stage in generation.stages[1:]:
                if cancel.is_set():
                    raise AdmissionCancelled()
                if stage.status == "completed":
                    continue
                if self.dependencies(workspace, generation.source_ids, generation.rules_used) != generation.dependencies:
                    raise ProjectFailure("STALE_GENERATION")
                if stage.kind == "normalize_semantics":
                    request = GuiNormalizeRequest(sources=[source for source in self.owner(workspace).sources if source.id in generation.source_ids],
                        formattingAsOf=generation.formatting_as_of, revision=workspace.project_revision)
                    normalized = await self._content(workspace, generation, stage, request, selected)
                    if self.dependencies(workspace, generation.source_ids, generation.rules_used) != generation.dependencies:
                        raise ProjectFailure("STALE_GENERATION")
                    cached["normalized"] = normalized
                    owner = self.owner(workspace)
                    normalized_sources = {source.id: source for source in normalized.sources}
                    owner.sources = [normalized_sources.get(source.id, source) for source in owner.sources]
                    owner.facts = normalized.facts[:]
                    workspace.source_observed_at = normalized.source_observed_at
                    result = normalized
                elif stage.kind == "draft_prose":
                    request = GuiDraftRequest(projectId=workspace.project_id, projectRevision=workspace.project_revision,
                        documentRevision=workspace.document_revision, normalized=cached["normalized"], formattingAsOf=generation.formatting_as_of)
                    result = await self._content(workspace, generation, stage, request, selected)
                    if self.dependencies(workspace, generation.source_ids, generation.rules_used) != generation.dependencies:
                        raise ProjectFailure("STALE_GENERATION")
                    cached["draft"] = result
                elif stage.kind == "assemble":
                    stage.status = "running"
                    result = cached["draft"]
                    pre = self.owner(workspace)
                    revision = workspace.project_revision + 1
                    document_revision = workspace.document_revision + 1
                    document = result.document.model_copy(deep=True)
                    from packages.resume_core.models.recovery import authored_fields
                    for record in document.records():
                        for field in authored_fields(record):
                            field.text = normalized_text(field.text)
                    project = ProjectV4(schemaVersion=4, projectId=workspace.project_id, revision=revision,
                        asOf=workspace.source_observed_at, createdAt=workspace.created_at, document=document,
                        employment=cached["normalized"].employment, views=compatibility_views(result.document, pre.facts), template=None,
                        review={"decisions": [], "acknowledgments": []}, proposals=[],
                        sources=pre.sources, facts=pre.facts, operations=pre.operations, renders=pre.renders)
                    derived = initial_derived(document, project.facts, project.employment,
                        workspace.source_observed_at, document_revision, result.editorial_plan.source_language)
                    workspace.project_revision, workspace.document_revision = revision, document_revision
                    workspace.project = project
                    workspace.pre_draft = None
                    workspace.rules_used, workspace.editorial_plan = generation.rules_used, result.editorial_plan.model_copy(deep=True)
                    workspace.undo_slots = {record_slot(record): None for record in result.document.records()}
                    workspace.derived_state = derived
                    if not workspace.title_manually_set and result.document.candidate.name.text.strip():
                        workspace.title = result.document.candidate.name.text
                    generation.dependencies = self.dependencies(workspace, generation.source_ids, generation.rules_used)
                    workspace.annotations = initial_annotations(workspace.project_id, document, cached["normalized"],
                        result.annotations, generation.dependencies)
                    for captured_stage in generation.stages:
                        captured_stage.dependency_fingerprint = generation.dependencies.dependency_fingerprint
                    workspace.updated_at = self.clock().isoformat()
                else:
                    stage.status = "running"
                    document, anchors, fingerprint = render_input(workspace)
                    captured_revisions = (workspace.project_revision, workspace.document_revision)
                    files = OperationFiles(self.temp_root)
                    self.files[key] = files
                    async with self.worker_slot(cancel):
                        with files.open():
                            content = await self.renderer.render(document, anchors, files)
                    if cancel.is_set():
                        raise AdmissionCancelled()
                    if captured_revisions != (workspace.project_revision, workspace.document_revision) or render_input(workspace)[2] != fingerprint:
                        raise ProjectFailure("STALE_GENERATION")
                    snapshot = RenderSnapshotV4(id=identity("render"), projectRevision=workspace.project_revision,
                        documentRevision=workspace.document_revision, renderInputFingerprint=fingerprint,
                        templateId="generic", templateVersion="1.0.0", templateSha256=PACKAGE_SHA256,
                        rendererVersion="1.0.0", rendererSha256=renderer_sha256(),
                        docx={"path": "renders/" + generation.id + "/resume.docx", "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)},
                        pdf=None, artifactAvailable=True)
                    workspace.project.renders.append(snapshot)
                    self.artifacts[(workspace.project_id, snapshot.id)] = content
                    result = snapshot
                stage.status = "completed"
                stage.result_fingerprint = digest(result.model_dump(mode="json", by_alias=True))
                if self.persist(workspace.project_id) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            generation.status = "completed"
        except (ContentFailure, AdmissionCancelled, ProjectFailure, UploadFailure, RenderFailure, DocxFailure, SpikeError, asyncio.TimeoutError) as error:
            cancelled = cancel.is_set() or isinstance(error, AdmissionCancelled)
            generation.status = "cancelled" if cancelled else "failed"
            if not (isinstance(error, ProjectFailure) and error.code == "PROJECT_SAVE_FAILED" and stage.status == "completed"):
                stage.status = generation.status
            stage.error_code = "CANCELLED" if cancelled else getattr(error, "code", "OPERATION_TIMEOUT")
            if isinstance(error, DocxFailure):
                stage.docx_error = error.error
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
        except Exception:
            generation.status = stage.status = "failed"
            stage.error_code = "INVALID_RESULT"
        finally:
            self.files.pop(key, None)
            self.persist(workspace.project_id)

    async def cancel(self, id, gid):
        generation = self.generation(id, gid)
        key = (id, gid)
        task = self.tasks.get(key)
        if task is None or task.done():
            return
        self.cancels[key].set()
        files = self.files.get(key)
        if files is not None:
            try:
                files.stop_worker()
            except SpikeError as error:
                self.cleanup_error(error)
                raise ProjectFailure(error.code, 503) from None
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=65)
        except asyncio.TimeoutError:
            self.cleanup_error(SpikeError("PROCESS_CLEANUP_FAILED"))
            raise ProjectFailure("PROCESS_CLEANUP_FAILED", 503) from None

    def request_shutdown(self):
        for cancel in self.cancels.values():
            cancel.set()

    async def shutdown(self):
        self.request_shutdown()
        for id, gid in list(self.tasks):
            await self.cancel(id, gid)
