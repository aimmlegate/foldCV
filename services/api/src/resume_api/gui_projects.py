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
from packages.resume_core.gui_rewriting import apply_rewrite, rewriting_input, rewrite_fingerprint
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rules import RulesFailure
from packages.resume_core.models.contracts import Source, Usage
from packages.resume_core.models.recovery import (WorkspaceV5, ProjectV4, Generation, GenerationStage,
    GuiOperation, GuiOperationEvent, Dependencies, RenderSnapshotV4, Annotation, record_slot, MutationResult, MutationReplay)
from packages.resume_core.rendering.docx_errors import DocxFailure
from packages.resume_core.rendering.template import PACKAGE_SHA256, renderer_sha256, RenderFailure
from .extracting import run_extract, UploadFailure
from .gui_admission import AdmissionCancelled, QueuedProvider
from .gui_normalization_content import GuiNormalizationContentService
from .gui_drafting_content import GuiDraftingContentService
from .gui_rendering import GuiDocxRenderer
from .gui_rewriting_content import GuiRewritingContentService
from .gui_exports import GuiExportMixin
from .gui_analysis import GuiAnalysisMixin
from .gui_management import GuiManagementMixin
from .gui_archives import GuiArchiveMixin
from .gui_errors import ProjectFailure
from .lifecycle import OperationFiles, SpikeError
from .providers.content import ContentFailure


def now():
    return datetime.now(timezone.utc)


def identity(prefix):
    return prefix + "-" + uuid.uuid4().hex


class GuiProjectService(GuiExportMixin, GuiAnalysisMixin, GuiManagementMixin, GuiArchiveMixin):
    def __init__(self, temp_root: Path, rules, provider_factory, *, clock=now,
                 worker_slot=None, cleanup_error=None, renderer=None, storage=None, preferences=None,
                 analysis_delay=0.5):
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
        self.preferences = preferences
        self.analysis_delay = analysis_delay
        self.analysis_timers = {}
        self.analysis_cleanup_failed = False
        self.deleted_ids = set()
        self.input_tasks, self.input_cancels, self.input_files = {}, {}, {}

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
            self.deleted_ids.update(entry.project_id for entry in _registry.entries if entry.tombstoned)
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
                    self.restore_analysis_pending(id)
                    self.persist(id)
            self.loaded = True

    def persist(self, id):
        if id in self.deleted_ids:
            self.save_errors[id] = "PROJECT_DELETED"
            return "failed"
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
        if self.storage is not None:
            try:
                if any(entry.project_id == id and entry.tombstoned for entry in self.storage.registry().entries):
                    self.deleted_ids.add(id)
            except ProjectStoreFailure as error:
                raise ProjectFailure(error.code, 503) from None
        if id in self.deleted_ids: raise ProjectFailure("PROJECT_DELETED", 410)
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
            if any(operation.id == mutation.root.client_mutation_id for operation in self.owner(self.workspaces[id]).operations):
                raise ProjectFailure("MUTATION_ID_RESERVED", 422)
            before = self.read_memory(id)
            known = any(item.client_mutation_id == mutation.root.client_mutation_id for item in self.workspaces[id].mutation_replay)
            try:
                rules_sha = self.rules.load().sha256 if mutation.root.kind == "apply-related-update" and not known else None
            except RulesFailure as error:
                raise ProjectFailure(error.code, 409) from None
            result = apply_mutation(self.workspaces[id], mutation, self.clock().isoformat(), rules_sha256=rules_sha)
            self.analysis_mutation(id, mutation.root, result, before)
            result.persistence = "durable" if self.persist(id) == "durable" else "memory" if self.storage is None else "failed"
            return result

    def rename(self, id, request):
        self.read(id)
        with self.state_lock:
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
        if id is not None: self.read(id)
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
        input_key = (id, source_id)
        self.input_files[input_key], self.input_cancels[input_key] = files, cancel
        self.input_tasks[input_key] = asyncio.current_task()
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
        except AdmissionCancelled:
            source.parser, source.warnings = "interrupted", ["EXTRACT_INTERRUPTED"]
            if self.selection_epochs[id] == source_id:
                pre.warnings = ["EXTRACT_INTERRUPTED", "NO_USABLE_TEXT"]
        except UploadFailure as error:
            source.parser, source.warnings = "failed", [error.code]
            if self.selection_epochs[id] == source_id:
                pre.warnings = [error.code, "NO_USABLE_TEXT"]
        except SpikeError as error:
            self.cleanup_error(error)
            if self.selection_epochs[id] == source_id:
                pre.warnings = [error.code, "NO_USABLE_TEXT"]
        finally:
            self.input_tasks.pop(input_key, None)
            self.input_files.pop(input_key, None)
            self.input_cancels.pop(input_key, None)
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
        old = self.generation(id, previous) if previous else None
        render_only = False
        if previous is None:
            if workspace.pre_draft is None:
                raise ProjectFailure("DOCUMENT_ALREADY_CREATED")
            pre = workspace.pre_draft
            if not pre.extracted_text.strip() or pre.extraction_fingerprint is None:
                raise ProjectFailure("NO_USABLE_TEXT", 422)
            source_ids = [pre.selected_source_id]
            if "portable_project_imported" not in workspace.migration_notices:
                workspace.formatting_as_of = partial_date(self.clock().date().isoformat())
        else:
            if old.status not in {"failed", "cancelled", "interrupted"} and not (
                    old.status == "completed" and old.stages[-1].status == "failed" and old.stages[-1].docx_error):
                raise ProjectFailure("GENERATION_NOT_RETRYABLE")
            if old.stages[3].status == "completed" and old.dependencies.document_revision != workspace.document_revision:
                raise ProjectFailure("STALE_GENERATION")
            if workspace.pre_draft:
                pre = workspace.pre_draft
                if not pre.extracted_text.strip() or pre.extraction_fingerprint is None:
                    raise ProjectFailure("NO_USABLE_TEXT", 422)
                source_ids = [pre.selected_source_id]
            else:
                source_ids = old.source_ids[:]
                render_only = (old.stages[3].status == "completed" and workspace.rules_used == old.rules_used
                    and workspace.formatting_as_of == old.formatting_as_of
                    and source_fingerprint([source for source in workspace.project.sources if source.id in source_ids]) == old.dependencies.source_fingerprint)
                if not render_only:raise ProjectFailure("STALE_GENERATION")
        selected = None if render_only else self.provider_factory()
        if not render_only and selected is None:
            raise ProjectFailure("CONNECTION_REQUIRED", 409)
        try:rules = old.rules_used if render_only else self.rules.load()
        except RulesFailure as error:raise ProjectFailure(error.code,503) from None
        deps = self.dependencies(workspace, source_ids, rules)
        generation = Generation(id=identity("generation"), projectId=id, status="queued", dependencies=deps,
            rulesUsed=rules, sourceIds=source_ids, formattingAsOf=workspace.formatting_as_of,
            stages=[GenerationStage(kind=kind, status="queued", dependencyFingerprint=deps.dependency_fingerprint,
                resultFingerprint=None, operationId=None, errorCode=None, docxError=None)
                for kind in ("extract", "normalize_semantics", "draft_prose", "assemble", "render")])
        cached = {}
        if old:
            if render_only:
                for index, stage in enumerate(old.stages[:4]):
                    if stage.status != "completed" or stage.dependency_fingerprint != old.dependencies.dependency_fingerprint:
                        raise ProjectFailure("STALE_GENERATION")
                    generation.stages[index] = stage.model_copy(deep=True)
                    generation.stages[index].dependency_fingerprint = deps.dependency_fingerprint
            elif old.dependencies == deps and old.rules_used == rules:
                available = self.cache.get((id, previous), {})
                for index, name in [(1, "normalized"), (2, "draft")]:
                    stage, result = old.stages[index], available.get(name)
                    if (stage.status != "completed" or stage.dependency_fingerprint != deps.dependency_fingerprint
                        or result is None or digest(result.model_dump(mode="json", by_alias=True)) != stage.result_fingerprint):break
                    cached[name] = result.model_copy(deep=True)
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
                    valid_facts = {fact.id for fact in owner.facts}
                    for source in owner.sources:
                        for unit in source.units:unit.represented_fact_ids = [ref for ref in unit.represented_fact_ids if ref in valid_facts]
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
                    workspace.annotations = [mark for mark in workspace.annotations if mark.code != "IMPORT_DOCX_WARNING"]
                    self.artifacts[(workspace.project_id, snapshot.id)] = content
                    result = snapshot
                stage.status = "completed"
                stage.result_fingerprint = digest(result.model_dump(mode="json", by_alias=True))
                if self.persist(workspace.project_id) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            generation.status = "completed"
        except (ContentFailure, AdmissionCancelled, ProjectFailure, UploadFailure, RenderFailure, DocxFailure, SpikeError, asyncio.TimeoutError) as error:
            cancelled = cancel.is_set() or isinstance(error, AdmissionCancelled)
            content_warning = (isinstance(error, DocxFailure) and error.code != "DOCX_RENDER_FAILED"
                and workspace.project is not None and stage.kind == "render" and not cancelled)
            if content_warning and self.dependencies(workspace, generation.source_ids, generation.rules_used) != generation.dependencies:
                content_warning = False
                error = ProjectFailure("STALE_GENERATION")
            generation.status = "cancelled" if cancelled else "completed" if content_warning else "failed"
            if not (isinstance(error, ProjectFailure) and error.code == "PROJECT_SAVE_FAILED" and stage.status == "completed"):
                stage.status = "failed" if content_warning else generation.status
            stage.error_code = "CANCELLED" if cancelled else getattr(error, "code", "OPERATION_TIMEOUT")
            if isinstance(error, DocxFailure):
                stage.docx_error = error.error
            if content_warning:
                workspace.annotations = [mark for mark in workspace.annotations if mark.code != "IMPORT_DOCX_WARNING"]
                workspace.annotations.append(Annotation(id=identity("annotation"), type="warning", code="IMPORT_DOCX_WARNING",
                    anchor={"kind": "document"}, dependencies=generation.dependencies.model_copy(deep=True),
                    factIds=[], reason="The resume is imported. Review its text or layout before exporting DOCX.",
                    evidence=[], resolved=False, updateSuggestionId=None, removedFocus=[]))
                if self.persist(workspace.project_id) == "failed":
                    generation.status, stage.error_code = "failed", "PROJECT_SAVE_FAILED"
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
        except Exception:
            generation.status = stage.status = "failed"
            stage.error_code = "INVALID_RESULT"
        finally:
            self.files.pop(key, None)
            self.persist(workspace.project_id)

    async def rewrite(self, id, request):
        self.read(id)
        key = (id, request.client_request_id)
        try:
            fingerprint = rewrite_fingerprint(request)
        except UnicodeError:
            raise ProjectFailure("INVALID_CONTENT_INPUT", 422) from None
        if not any(item.id == request.client_request_id for item in self.owner(self.workspaces[id]).operations):
            await self.prepare_analysis_rewrite(id)
        with self.state_lock:
            workspace = self.workspaces[id]
            if workspace.project is None or request.selection.project_id != id:
                raise ProjectFailure("SELECTION_STALE")
            previous = next((item for item in workspace.project.operations if item.id == request.client_request_id), None)
            if previous:
                if previous.kind != "rewrite_prose" or not previous.dependencies or previous.dependencies.dependency_fingerprint != fingerprint:
                    raise ProjectFailure("REQUEST_ID_REUSED")
                saved = next((item for item in workspace.mutation_replay if item.client_mutation_id == previous.id), None)
                if saved:
                    return MutationResult(status="replayed", projectRevision=saved.project_revision,
                        documentRevision=saved.document_revision, changedSlotIds=[], rejectionReason=saved.rejection_reason,
                        persistence="durable" if self.persist(id) == "durable" else "memory" if self.storage is None else "failed")
                if key not in self.tasks:
                    raise ProjectFailure("OPERATION_INTERRUPTED")
            else:
                renders = {item.id for item in workspace.project.operations if item.kind in {"render", "reconcile_edits"}}
                if any(not task.done() for (pid, oid), task in self.tasks.items() if pid == id and oid not in renders):
                    raise ProjectFailure("PROJECT_OPERATION_ACTIVE")
                if self.persist(id) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
                selected = self.provider_factory()
                if selected is None:
                    raise ProjectFailure("CONNECTION_REQUIRED")
                rules = self.rules.load()
                operation = GuiOperation(id=request.client_request_id, kind="rewrite_prose", status="queued",
                    baseRevision=workspace.project_revision, usage=None, events=[], projectId=id,
                    capturedDocumentRevision=None, dependencies=None, rulesUsed=rules,
                    targetFieldIds=[span.field_id for span in request.selection.spans], resultFingerprint=None, errorCode=None)
                workspace.project.operations.append(operation)
                operation.captured_document_revision = workspace.document_revision
                operation.dependencies = Dependencies(projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
                    rulesSha256=rules.sha256, sourceFingerprint=source_fingerprint(workspace.project.sources), dependencyFingerprint=fingerprint)
                captured = self.read_memory(id)
                self.cancels[key] = threading.Event()
                self.tasks[key] = asyncio.create_task(self._run_rewrite(captured, request.model_copy(deep=True), operation, selected))
        return await asyncio.shield(self.tasks[key])

    async def _run_rewrite(self, captured, request, operation, selected):
        id, oid = captured.project_id, operation.id
        key, cancel = (id, oid), self.cancels[(id, oid)]
        result = None
        files = OperationFiles(self.temp_root)
        self.files[key] = files

        def admitted():
            with self.state_lock:
                operation.status = "running"
                operation.usage = Usage(logicalAttempts=1, internalInferenceRequests=None, reportedInputTokens=None, reportedOutputTokens=None)
                self._event(operation, "operation.started")
                if id in self.save_errors:
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)

        try:
            prompt = rewriting_input(captured, request, operation.rules_used)
            if self.persist(id) == "failed":
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            provider, model = selected
            service = GuiRewritingContentService(QueuedProvider(provider, admitted), model)
            def run():
                with files.open():
                    return service.run(prompt, request.selection, files, cancel)
            async with self.worker_slot(cancel):
                proposal, response = await asyncio.to_thread(run)
            operation.usage = Usage(logicalAttempts=response.logical_attempts, internalInferenceRequests=response.internal_inference_count,
                reportedInputTokens=response.usage.input_tokens, reportedOutputTokens=response.usage.output_tokens)
            with self.state_lock:
                if cancel.is_set():
                    raise AdmissionCancelled()
                if self.rules.load().sha256 != operation.rules_used.sha256:
                    raise ProjectFailure("RULES_CHANGED")
                result = apply_rewrite(self.workspaces[id], request, proposal, operation.base_revision, self.clock().isoformat())
                operation.result_fingerprint = digest(proposal.model_dump(mode="json", by_alias=True))
                operation.status = "completed" if result.status == "applied" else "failed"
                operation.error_code = result.rejection_reason
                self._event(operation, "usage.updated", save=False)
                self._event(operation, "operation.completed" if result.status == "applied" else "operation.failed", save=False)
                if result.status == "applied":
                    fields = [span.field_id for span in request.selection.spans]
                    self.accumulate_analysis(id, fields, fields, enable=True)
                    self.schedule_analysis(id)
        except (ContentFailure, AdmissionCancelled, ProjectFailure, ValueError, SpikeError) as error:
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
            operation.status = "cancelled" if cancel.is_set() or isinstance(error, AdmissionCancelled) else "failed"
            safe_code = str(error) if isinstance(error, ValueError) and str(error) in {
                "SELECTION_STALE", "RULES_CHANGED", "NO_SAFE_CONTENT", "INPUT_TOO_LARGE", "INVALID_CONTENT_INPUT"} else "INVALID_RESULT"
            operation.error_code = "CANCELLED" if operation.status == "cancelled" else getattr(error, "code", safe_code)
            attempts = max(operation.usage.logical_attempts if operation.usage else 0, error.logical_attempts if isinstance(error, ContentFailure) else 0)
            usage = error.usage if isinstance(error, ContentFailure) else None
            if operation.usage is None or usage:
                operation.usage = Usage(logicalAttempts=attempts, internalInferenceRequests=None,
                    reportedInputTokens=usage.input_tokens if usage else None, reportedOutputTokens=usage.output_tokens if usage else None)
            self._event(operation, "cancelled" if operation.status == "cancelled" else "operation.failed", save=False)
        except Exception:
            operation.status, operation.error_code = "failed", "INVALID_RESULT"
            self._event(operation, "operation.failed", save=False)
        finally:
            self.files.pop(key, None)
        with self.state_lock:
            workspace = self.workspaces[id]
            result = result or MutationResult(status="rejected", projectRevision=workspace.project_revision,
                documentRevision=workspace.document_revision, changedSlotIds=[], rejectionReason=operation.error_code, persistence="memory")
            if result.status != "applied":
                pending = self.pending_analysis(id)
                if pending:
                    pending.analysis_batch.enabled = False
                    pending.error_code = operation.error_code or "REWRITE_FAILED"
            workspace.mutation_replay.append(MutationReplay(clientMutationId=oid, payloadSha256=rewrite_fingerprint(request),
                status=result.status, projectRevision=result.project_revision, documentRevision=result.document_revision,
                rejectionReason=result.rejection_reason))
            result.persistence = "durable" if self.persist(id) == "durable" else "memory" if self.storage is None else "failed"
        return result

    async def cancel(self, id, gid, *, allow_deleted=False):
        workspace = self.read_memory(id) if allow_deleted and id in self.workspaces else self.read(id)
        if not any(item.id == gid for item in workspace.generations) and not any(item.id == gid for item in self.owner(workspace).operations):
            raise ProjectFailure("OPERATION_NOT_FOUND", 404)
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
                self.analysis_cleanup_failed = True
                raise ProjectFailure(error.code, 503) from None
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=65)
        except asyncio.TimeoutError:
            self.cleanup_error(SpikeError("PROCESS_CLEANUP_FAILED"))
            self.analysis_cleanup_failed = True
            raise ProjectFailure("PROCESS_CLEANUP_FAILED", 503) from None

    def request_shutdown(self):
        for id in list(self.analysis_timers):
            self.stop_analysis_timer(id)
        for cancel in self.cancels.values():
            cancel.set()
        for cancel in self.input_cancels.values(): cancel.set()

    async def shutdown(self):
        self.request_shutdown()
        for id, gid in list(self.tasks):
            await self.cancel(id, gid, allow_deleted=id in self.deleted_ids)
        for id, sid in list(self.input_tasks): await self.cancel_input(id, sid)

    async def cancel_input(self, id, sid):
        key = (id, sid)
        task = self.input_tasks.get(key)
        if task is None or task.done(): return
        self.input_cancels[key].set()
        files = self.input_files.get(key)
        try:
            if files: files.stop_worker()
            await asyncio.wait_for(asyncio.shield(task), timeout=65)
        except ProjectFailure as error:
            if error.code != "PROJECT_DELETED": raise
        except (SpikeError, asyncio.TimeoutError):
            self.analysis_cleanup_failed = True
            self.cleanup_error(SpikeError("PROCESS_CLEANUP_FAILED"))
            raise ProjectFailure("PROCESS_CLEANUP_FAILED", 503) from None
