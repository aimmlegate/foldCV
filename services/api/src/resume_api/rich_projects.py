"""New rich projects with explicit version dispatch and converter-free export."""

import asyncio
import hashlib
import threading
from pydantic import ValidationError

from packages.resume_core.dates import partial_date
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.gui_archive_zip import ArchiveFailure
from packages.resume_core.gui_normalization import GuiNormalizeRequest, canonical_source
from packages.resume_core.models.contracts import Source
from packages.resume_core.models.rich_workspace import RichOperation, RichRenderSnapshot, RichWarning, WorkspaceV6
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_api import RichGenerationState, RichProjectResponse
from packages.resume_core.rich_archive import archive_payload, export_rich_archive, open_rich_archive
from packages.resume_core.rich_assembly import identity
from packages.resume_core.rich_import import assemble_import
from packages.resume_core.rich_identity import resume_identity
from packages.resume_core.gui_annotations import unresolved_source_units
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.rendering.rich_docx import RENDERER_VERSION, current_snapshot, renderer_sha256, validate_export
from packages.resume_core.rendering.rich_template import PACKAGE_SHA256
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.rules import RulesFailure
from .extracting import UploadFailure, run_extract
from .gui_admission import AdmissionCancelled, QueuedProvider
from .gui_normalization_content import GuiNormalizationContentService
from .gui_projects import GuiProjectService, ProjectFailure, digest
from .gui_rendering import RichDocxRenderer
from .lifecycle import OperationFiles, SpikeError
from .providers.content import ContentFailure
from .rich_assets import RichAssets
from .rich_synchronization import RichSynchronization
from .resume_assessment_content import ResumeAssessmentContentService


class RichProjectService(RichSynchronization, RichAssets, GuiProjectService):
    def __init__(self, temp_root, rules, provider_factory, **options):
        options.setdefault("storage", RichProjectStore(rules.root))
        options.setdefault("renderer", RichDocxRenderer())
        super().__init__(temp_root, rules, provider_factory, **options)
        self.images = {}
        self.generations = {}
        self.agent_recovery_fences = set()
        self.initialize_images()

    def require_agent_writable(self, identifier):
        if identifier in self.agent_recovery_fences:
            raise ProjectFailure("AGENT_OUTCOME_UNKNOWN", 409)

    def rename(self, identifier, request):
        self.require_agent_writable(identifier)
        return super().rename(identifier, request)

    def ensure_loaded(self):
        if self.loaded:
            return
        with self.state_lock:
            if self.loaded:
                return
            try:
                loaded, self.load_errors, registry = self.storage.load_all()
            except ProjectStoreFailure as error:
                raise ProjectFailure(error.code, 503) from None
            self.deleted_ids.update(entry.project_id for entry in registry.entries if entry.tombstoned)
            self.loaded = True
            for identifier, (workspace, originals, artifacts, images) in loaded.items():
                self.workspaces[identifier] = workspace
                self.originals.update(originals); self.artifacts.update(artifacts); self.images.update(images)
                changed = False
                for operation in self.owner(workspace).operations:
                    if operation.status in {"running", "queued"}:
                        operation.status, operation.error_code = "interrupted", "OPERATION_INTERRUPTED"
                        changed = True
                for sync in workspace.sync_records:
                    if sync.status == "pending":
                        sync.error_code, sync.ready = "OPERATION_INTERRUPTED", False; changed = True
                if workspace.pre_draft and "EXTRACT_PENDING" in workspace.pre_draft.warnings:
                    workspace.pre_draft.warnings = ["EXTRACT_INTERRUPTED", "NO_USABLE_TEXT"]; changed = True
                self.saved_hashes[identifier] = digest(workspace.model_dump(mode="json", by_alias=True))
                self.saved_revisions[identifier] = (workspace.project_revision, workspace.document_revision)
                if changed:
                    self.persist(identifier)

    def read_memory(self, identifier):
        return WorkspaceV6.model_validate(self.workspaces[identifier].model_dump(by_alias=True))

    def persist(self, identifier):
        with self.state_lock:
            if identifier in self.agent_recovery_fences:
                self.save_errors[identifier] = "AGENT_OUTCOME_UNKNOWN"
                return "failed"
            if identifier in self.deleted_ids:
                self.save_errors[identifier] = "PROJECT_DELETED"; return "failed"
            try:
                snapshot = self.read_memory(identifier)
                jobs = getattr(self, "background_jobs", None)
                if jobs is not None and jobs.enabled and (jobs.store.projects / identifier).exists():
                    state = jobs.store.load(identifier)
                    if state.history is not None or (jobs.store.projects / identifier / "history-activation.json").exists():
                        _current, checksum = jobs.publisher.confirm_snapshot(identifier, snapshot)
                        jobs.publication.adopt(identifier, snapshot, checksum)
                        return "durable"
                self.storage.save(snapshot, self.originals, self.artifacts, self.images)
                self.saved_hashes[identifier] = digest(snapshot.model_dump(mode="json", by_alias=True))
                self.saved_revisions[identifier] = (snapshot.project_revision, snapshot.document_revision)
                self.save_errors.pop(identifier, None)
                return "durable"
            except (ProjectStoreFailure, BackgroundFailure) as error:
                self.save_errors[identifier] = error.code
                return "failed"

    def response(self, identifier):
        from packages.resume_core.rich_presentation import presentation
        workspace = self.read(identifier)
        saved = self.saved_revisions.get(identifier)
        return RichProjectResponse(workspace=workspace, durability=self.durability(identifier),
            savedProjectRevision=saved[0] if saved else None, savedDocumentRevision=saved[1] if saved else None,
            saveError=self.save_errors.get(identifier), generation=self.generations.get(identifier),
            presentation=presentation(workspace.project.document, workspace.project.facts) if workspace.project else None,
            identity=resume_identity(workspace))

    def listing(self):
        self.ensure_loaded()
        entries = []
        for entry in self.storage.registry().entries:
            if entry.tombstoned:
                continue
            value = entry.model_dump(mode="json", by_alias=True)
            if entry.project_id in self.workspaces:
                identity = resume_identity(self.workspaces[entry.project_id])
                value.update(title=identity.title, subtitle=identity.subtitle)
            entries.append(value)
        return {"entries": entries, "errors": [{"projectId": identifier, "errorCode": code} for identifier, code in self.load_errors.items()]}

    def allocate(self, title):
        self.ensure_loaded()
        stamp, identifier = self.clock(), identity("project")
        self.workspaces[identifier] = WorkspaceV6.model_validate({"schemaVersion": 6, "projectId": identifier,
            "projectRevision": 1, "documentRevision": 1, "title": title, "titleManuallySet": False,
            "createdAt": stamp.isoformat(), "updatedAt": stamp.isoformat(), "project": None,
            "preDraft": {"sources": [], "facts": {"revision": 1, "records": [], "tombstones": []},
                "selectedInput": "text", "selectedSourceId": None, "operations": [], "warnings": []},
            "formattingAsOf": partial_date(stamp.date().isoformat()).model_dump(by_alias=True), "sourceObservedAt": None,
            "rulesUsed": None, "syncRecords": [], "mutationReplay": [], "warnings": []})
        self.persist(identifier)
        return identifier

    async def select(self, data, name, pasted, id=None):
        if id:
            self.read(id)
        identifier = id or self.allocate("Новое резюме" if pasted else name)
        workspace = self.workspaces[identifier]
        if workspace.project or any(pid == identifier and not task.done() for (pid, _), task in self.tasks.items()):
            raise ProjectFailure("PROJECT_GENERATION_ACTIVE")
        source_id = identity("source")
        self.selection_epochs[identifier] = source_id
        source = Source.model_validate({"id": source_id, "revision": 1, "originalName": name,
            "mimeType": "text/plain" if pasted else "application/octet-stream", "byteSha256": hashlib.sha256(data).hexdigest(),
            "byteRef": f"sources/{source_id}/original", "parser": "pending", "parserVersion": "1", "units": [], "overlays": [], "warnings": []})
        pre = workspace.pre_draft
        pre.sources.append(source); pre.selected_input = "text" if pasted else "file"
        pre.selected_source_id, pre.warnings = source_id, ["EXTRACT_PENDING"]
        self.originals[(identifier, source_id)] = bytes(data)
        self.persist(identifier)
        files, cancel = OperationFiles(self.temp_root), threading.Event()
        key = (identifier, source_id)
        self.input_tasks[key], self.input_files[key], self.input_cancels[key] = asyncio.current_task(), files, cancel
        try:
            async with self.worker_slot(cancel):
                with files.open():
                    result = await run_extract(data, name, pasted, files)
            extracted = canonical_source(result, source_id=source_id)
            pre.sources = [extracted if item.id == source_id else item for item in pre.sources]
            if self.selection_epochs[identifier] == source_id:
                pre.warnings = extracted.warnings[:]
                if not any(unit.text.strip() for unit in extracted.units):
                    pre.warnings.append("NO_USABLE_TEXT")
        except (UploadFailure, SpikeError, AdmissionCancelled) as error:
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
            if self.selection_epochs[identifier] == source_id:
                pre.warnings = [getattr(error, "code", "EXTRACT_INTERRUPTED"), "NO_USABLE_TEXT"]
        finally:
            self.input_tasks.pop(key, None); self.input_files.pop(key, None); self.input_cancels.pop(key, None)
        workspace.updated_at = self.clock().isoformat()
        self.persist(identifier)
        return self.read(identifier)

    def start(self, identifier, previous=None):
        self.require_agent_writable(identifier)
        workspace = self.read(identifier)
        if self.persist(identifier) == "failed":
            raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
        if any(pid == identifier and not task.done() for (pid, _), task in self.tasks.items()):
            raise ProjectFailure("PROJECT_GENERATION_ACTIVE")
        if workspace.project:
            raise ProjectFailure("DOCUMENT_ALREADY_CREATED")
        sources = [source for source in workspace.pre_draft.sources if source.id == workspace.pre_draft.selected_source_id]
        if not sources or not any(unit.text.strip() for unit in sources[0].units):
            raise ProjectFailure("NO_USABLE_TEXT", 422)
        selected = self.provider_factory()
        if selected is None:
            raise ProjectFailure("CONNECTION_REQUIRED")
        try:
            rules = self.rules.load()
        except RulesFailure as error:
            raise ProjectFailure(error.code, 503) from None
        generation = RichGenerationState(id=identity("generation"), status="queued", stage="assess_resume", errorCode=None)
        self.generations[identifier] = generation
        key = (identifier, generation.id)
        self.cancels[key] = threading.Event()
        self.tasks[key] = asyncio.create_task(self._run_rich(identifier, generation, sources, rules, selected))
        return generation.id

    def new_operation(self, identifier, kind):
        operation = RichOperation(id=identity("operation"), kind=kind, status="queued", actionId=None, dependencies=[], errorCode=None)
        self.owner(self.workspaces[identifier]).operations.append(operation)
        if self.persist(identifier) == "failed":
            raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
        return operation

    def finish_operation(self, identifier, operation_id, status, error_code=None):
        with self.state_lock:
            operation = next(op for op in self.owner(self.workspaces[identifier]).operations if op.id == operation_id)
            operation.status, operation.error_code = status, error_code

    async def content(self, identifier, generation, request, rules, selected):
        key = (identifier, generation.id)
        cancel = self.cancels[key]
        operation = self.new_operation(identifier, generation.stage)
        def admitted():
            with self.state_lock:
                operation.status = "running"
                if self.persist(identifier) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
        service_type = ResumeAssessmentContentService if generation.stage == "assess_resume" else GuiNormalizationContentService
        service = service_type(QueuedProvider(selected[0], admitted), selected[1])
        files = OperationFiles(self.temp_root)
        self.files[key] = files
        def run():
            with files.open():
                return service.run(request, rules, files, cancel)[0]
        try:
            async with self.worker_slot(cancel):
                result = await asyncio.to_thread(run)
            if cancel.is_set():
                raise AdmissionCancelled()
            operation.status = "completed"
            self.persist(identifier)
            return result
        except Exception as error:
            operation.status = "cancelled" if cancel.is_set() else "failed"
            operation.error_code = getattr(error, "code", "INVALID_RESULT")
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
            self.persist(identifier)
            raise
        finally:
            self.files.pop(key, None)

    async def _run_rich(self, identifier, generation, sources, rules, selected):
        generation.status = "running"
        workspace = self.workspaces[identifier]
        try:
            request = GuiNormalizeRequest(sources=sources, formattingAsOf=workspace.formatting_as_of, revision=workspace.project_revision)
            assessment = await self.content(identifier, generation, request, rules, selected)
            codes = {"unlikely": "source_not_resume", "uncertain": "source_resume_uncertain"}
            if assessment.verdict in codes:
                code = codes[assessment.verdict]
                if not any(warning.code == code for warning in workspace.warnings):
                    workspace.warnings.append(RichWarning(id=identity("warning"), code=code, blockIds=[], recordIds=[], evidence=[]))
                if self.persist(identifier) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            generation.stage = "normalize_semantics"
            normalized = await self.content(identifier, generation, request, rules, selected)
            if self.cancels[(identifier, generation.id)].is_set():
                raise AdmissionCancelled()
            generation.stage = "assemble"
            project = assemble_import(workspace, normalized)
            workspace.project, workspace.pre_draft = project, None
            workspace.project_revision, workspace.document_revision = project.revision, project.document.revision
            workspace.rules_used, workspace.source_observed_at = rules, normalized.source_observed_at
            if not workspace.title_manually_set:
                workspace.title = normalized.candidate.name.text or workspace.title
            unresolved = ["source_details_unresolved"] if normalized._native_recovery_count or unresolved_source_units(normalized) else []
            for code in dict.fromkeys([*[code for source in normalized.sources for code in source.warnings], *unresolved]):
                workspace.warnings.append(RichWarning(id=identity("warning"), code=code, blockIds=[], recordIds=[], evidence=[]))
            if self.persist(identifier) == "failed":
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            generation.stage = "render"
            try:
                await self.export(identifier, generation.id)
            except RenderFailure as error:
                if error.code != "RICH_EXPORT_UNSUPPORTED":
                    raise
                workspace.warnings.append(RichWarning(id=identity("warning"), code=error.code, blockIds=[], recordIds=[], evidence=[]))
            generation.status = "completed"
        except (ContentFailure, ProjectFailure, RenderFailure, SpikeError, AdmissionCancelled, asyncio.TimeoutError) as error:
            generation.status = "cancelled" if self.cancels[(identifier, generation.id)].is_set() else "failed"
            generation.error_code = getattr(error, "code", "CANCELLED" if isinstance(error, AdmissionCancelled) else "OPERATION_TIMEOUT")
        except Exception:
            generation.status, generation.error_code = "failed", "INVALID_RESULT"
        finally:
            self.persist(identifier)

    def mutate(self, identifier, request):
        with self.state_lock:
            self.require_agent_writable(identifier)
            self.read(identifier)
            agent = getattr(self, "agent", None)
            if agent is not None and not agent.publication.manual_allowed(identifier, request):
                raise ProjectFailure("AGENT_TICKET_INVALID", 409)
            jobs = getattr(self, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                jobs.store.open(identifier)
                try:
                    workspace, _replay = jobs.publisher.manual(identifier, request, originals=self.originals,
                        artifacts=self.artifacts, images=self.images)
                except (BackgroundFailure, RichMutationFailure, ProjectStoreFailure) as error:
                    self.save_errors[identifier] = error.code
                    raise ProjectFailure(error.code, 409) from None
                current, checksum = self.storage.read_committed(identifier)
                jobs.publication.adopt(identifier, current, checksum)
                if agent is not None:
                    agent.publication.record_history(identifier, request)
                return self.response(identifier)
            try:
                workspace, replay = apply_rich_mutation(self.workspaces[identifier], request)
                archive_payload(workspace, {sid: blob for (pid, sid), blob in self.originals.items() if pid == identifier},
                    {aid: blob for (pid, aid), blob in self.images.items() if pid == identifier})
            except (RichMutationFailure, ArchiveFailure) as error:
                raise ProjectFailure(error.code, 409) from None
            except ValidationError:
                raise ProjectFailure("RICH_CONTENT_INVALID", 422) from None
            workspace.updated_at = self.clock().isoformat()
            self.workspaces[identifier] = workspace
            self.persist(identifier)
            if agent is not None and self.durability(identifier) == "durable":
                agent.publication.record_history(identifier, request)
            self.reclaim_images(identifier)
            return self.response(identifier)

    async def export(self, identifier, generation_id=None):
        self.require_agent_writable(identifier)
        captured = self.read(identifier)
        if captured.project is None:
            raise ProjectFailure("DOCUMENT_NOT_CREATED")
        validate_export(captured.project.document)
        available = {rid: blob for (pid, rid), blob in self.artifacts.items() if pid == identifier}
        cache = current_snapshot(captured, available)
        if cache:
            return cache
        operation = self.new_operation(identifier, "render")
        operation.status = "running"
        key = (identifier, generation_id or operation.id)
        cancel = self.cancels.get(key, threading.Event())
        files = OperationFiles(self.temp_root)
        self.files[key] = files
        if not generation_id:
            self.tasks[key], self.cancels[key] = asyncio.current_task(), cancel
        try:
            async with self.worker_slot(cancel):
                with files.open():
                    blob = await self.renderer.render(captured.project.document,
                        {aid: data for (pid, aid), data in self.images.items() if pid == identifier}, files, captured.project.facts)
            with self.state_lock:
                current = self.workspaces[identifier]
                if identifier in self.deleted_ids or cancel.is_set() or current.document_revision != captured.document_revision or current.project.facts.revision != captured.project.facts.revision:
                    raise ProjectFailure("STALE_EXPORT")
                snapshot = RichRenderSnapshot(id=identity("render"), documentRevision=captured.document_revision,
                    factsRevision=captured.project.facts.revision, templateSha256=PACKAGE_SHA256,
                    rendererVersion=RENDERER_VERSION, rendererSha256=renderer_sha256(), docxSha256=hashlib.sha256(blob).hexdigest(),
                    docxSize=len(blob), docxPath="renders/" + identity("docx") + ".docx")
                current.project.renders = [snapshot]
                self.artifacts[(identifier, snapshot.id)] = blob
                self.finish_operation(identifier, operation.id, "completed")
                self.persist(identifier)
                return snapshot, blob
        except Exception as error:
            self.finish_operation(identifier, operation.id, "cancelled" if cancel.is_set() else "failed",
                "CANCELLED" if cancel.is_set() else getattr(error, "code", "RICH_RENDER_FAILED"))
            self.persist(identifier)
            raise
        finally:
            self.files.pop(key, None)
            if not generation_id:
                self.tasks.pop(key, None); self.cancels.pop(key, None)

    async def shutdown(self, *, close_agent=True):
        agent = getattr(self, "agent", None)
        if agent is not None:
            if close_agent:
                await agent.shutdown()
            else:
                await agent.stop_all()
        for session in self.image_sessions.values():
            session.closed = True
        await super().shutdown()
        if self.image_tasks:
            await asyncio.gather(*list(self.image_tasks), return_exceptions=True)

    def portable(self, identifier):
        self.require_agent_writable(identifier)
        workspace = self.read(identifier)
        artifacts = {rid: blob for (pid, rid), blob in self.artifacts.items() if pid == identifier}
        try:
            return export_rich_archive(workspace,
                {sid: blob for (pid, sid), blob in self.originals.items() if pid == identifier}, artifacts,
                {aid: blob for (pid, aid), blob in self.images.items() if pid == identifier})
        except (ArchiveFailure, RenderFailure) as error:
            raise ProjectFailure(error.code, 422) from None

    def import_portable(self, data):
        self.ensure_loaded()
        identifier = identity("project")
        try:
            workspace, originals, artifacts, images = open_rich_archive(data, identifier)
        except ArchiveFailure as error:
            raise ProjectFailure(error.code, 422) from None
        self.workspaces[identifier] = workspace
        self.originals.update({(identifier, sid): blob for sid, blob in originals.items()})
        self.images.update({(identifier, aid): blob for aid, blob in images.items()})
        self.persist(identifier)
        return identifier

    async def delete_project(self, identifier):
        # Verify the rich version before the shared tombstone can alter its registry entry.
        self.ensure_loaded()
        tombstoned = any(entry.project_id == identifier and entry.tombstoned for entry in self.storage.registry().entries)
        if not tombstoned:
            self.read(identifier)
        agent = getattr(self, "agent", None)
        agent_error = None
        if agent is not None:
            from packages.resume_core.agent_store import AgentFailure
            try:
                with self.state_lock:
                    self.storage.tombstone(identifier)
                    self.deleted_ids.add(identifier)
                    agent.request_project_stop(identifier)
                await agent.stop_project(identifier)
            except AgentFailure as error:
                agent_error = error.code
            except ProjectStoreFailure as error:
                raise ProjectFailure(error.code, 409) from None
        jobs = getattr(self, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            self.storage.tombstone(identifier)
            self.deleted_ids.add(identifier)
            await jobs.stop_project(identifier)
        for (pid, _), session in self.image_sessions.items():
            if pid == identifier:
                session.closed = True
        result = await super().delete_project(identifier)
        if agent is not None:
            try:
                agent.store.cleanup_deleted(identifier)
            except AgentFailure as error:
                agent_error = agent_error or error.code
        if agent_error is not None:
            from packages.resume_core.gui_projects import GuiDeleteProjectResult
            return GuiDeleteProjectResult(projectId=identifier, status="cleanup_incomplete", errorCode=agent_error)
        if result.status == "deleted":
            for key in list(self.images):
                if key[0] == identifier:
                    self.images.pop(key, None)
        return result

    async def cancel(self, identifier, generation_id, **_options):
        key = (identifier, generation_id)
        task = self.tasks.get(key)
        if task is None or task.done():
            return
        cancel = self.cancels[key]
        cancel.set()
        files = self.files.get(key)
        if files:
            files.stop_worker()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=65)
        except asyncio.TimeoutError:
            self.cleanup_error(SpikeError("PROCESS_CLEANUP_FAILED"))
            raise ProjectFailure("PROCESS_CLEANUP_FAILED", 503) from None
        except (ProjectFailure, RenderFailure, AdmissionCancelled) as error:
            if getattr(error, "code", None) == "PROCESS_CLEANUP_FAILED" or not cancel.is_set():
                raise
