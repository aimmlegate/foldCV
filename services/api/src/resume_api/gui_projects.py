"""In-memory creation state; durable project storage belongs to task A12."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import threading
import uuid

from packages.resume_core.dates import partial_date
from packages.resume_core.gui_derived import digest, initial_derived
from packages.resume_core.gui_drafting import GuiDraftRequest
from packages.resume_core.gui_normalization import GuiNormalizeRequest, canonical_source, source_fingerprint
from packages.resume_core.gui_rendering import render_input
from packages.resume_core.gui_projection import compatibility_views
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
                 worker_slot=None, cleanup_error=None, renderer=None):
        self.temp_root, self.rules, self.provider_factory = temp_root, rules, provider_factory
        self.clock = clock
        self.worker_slot = worker_slot or self._local_slot
        self.cleanup_error = cleanup_error or (lambda _error: None)
        self.renderer = renderer or GuiDocxRenderer()
        self.workspaces = {}
        self.originals = {}
        self.artifacts = {}
        self.tasks = {}
        self.cancels = {}
        self.files = {}
        self.cache = {}
        self.selection_epochs = {}

    @asynccontextmanager
    async def _local_slot(self, cancel):
        if cancel.is_set():
            raise AdmissionCancelled()
        yield

    def read(self, id):
        workspace = self.workspaces.get(id)
        if workspace is None:
            raise ProjectFailure("PROJECT_NOT_FOUND", 404)
        return WorkspaceV5.model_validate(workspace.model_dump(by_alias=True))

    def owner(self, workspace):
        return workspace.project or workspace.pre_draft

    def allocate(self, title):
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

    def _event(self, operation, type):
        operation.events.append(GuiOperationEvent(requestId=operation.id, sequence=len(operation.events),
            type=type, stage=operation.kind, usage=operation.usage))

    async def _content(self, workspace, generation, stage, request, selected):
        cancel = self.cancels[(workspace.project_id, generation.id)]
        operation = GuiOperation(id=identity("operation"), kind=stage.kind, status="queued",
            baseRevision=workspace.document_revision, usage=None, events=[], projectId=workspace.project_id,
            capturedDocumentRevision=workspace.document_revision, dependencies=generation.dependencies,
            rulesUsed=generation.rules_used, targetFieldIds=[], resultFingerprint=None, errorCode=None)
        self.owner(workspace).operations.append(operation)
        stage.operation_id = operation.id

        def admitted():
            operation.status, stage.status = "running", "running"
            self._event(operation, "operation.started")

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
                    workspace.annotations = result.annotations
                    workspace.undo_slots = {record_slot(record): None for record in result.document.records()}
                    workspace.derived_state = derived
                    if not workspace.title_manually_set and result.document.candidate.name.text.strip():
                        workspace.title = result.document.candidate.name.text
                    generation.dependencies = self.dependencies(workspace, generation.source_ids, generation.rules_used)
                    for captured_stage in generation.stages:
                        captured_stage.dependency_fingerprint = generation.dependencies.dependency_fingerprint
                    workspace.updated_at = self.clock().isoformat()
                else:
                    stage.status = "running"
                    document, anchors, fingerprint = render_input(workspace)
                    files = OperationFiles(self.temp_root)
                    self.files[key] = files
                    async with self.worker_slot(cancel):
                        with files.open():
                            content = await self.renderer.render(document, anchors, files)
                    if cancel.is_set():
                        raise AdmissionCancelled()
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
            generation.status = "completed"
        except (ContentFailure, AdmissionCancelled, ProjectFailure, UploadFailure, RenderFailure, DocxFailure, SpikeError, asyncio.TimeoutError) as error:
            cancelled = cancel.is_set() or isinstance(error, AdmissionCancelled)
            generation.status = stage.status = "cancelled" if cancelled else "failed"
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
