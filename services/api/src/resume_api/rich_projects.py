"""New rich projects with explicit version dispatch and converter-free export."""

import asyncio
import hashlib
import threading
from pydantic import ValidationError

from packages.resume_core.dates import partial_date
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import identity as command_identity
from packages.resume_core.gui_archive_zip import ArchiveFailure
from packages.resume_core.gui_normalization import canonical_source
from packages.resume_core.models.contracts import Source
from packages.resume_core.models.rich_workspace import RichOperation, RichRenderSnapshot, WorkspaceV6
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.project_catalog import ProjectCatalog
from packages.resume_core.rich_api import RichGenerationState, RichProjectResponse
from packages.resume_core.rich_archive import archive_payload, export_rich_archive, open_rich_archive
from packages.resume_core.rich_assembly import identity
from packages.resume_core.rich_identity import resume_identity
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.rich_snapshot_merge import merge_snapshot, reconcile
from packages.resume_core.rendering.rich_docx import RENDERER_VERSION, current_snapshot, renderer_sha256, validate_export
from packages.resume_core.rendering.rich_template import PACKAGE_SHA256
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.rules import RulesFailure
from .extracting import UploadFailure, run_extract
from .gui_admission import AdmissionCancelled
from .gui_projects import GuiProjectService, ProjectFailure, digest
from .gui_rendering import RichDocxRenderer
from .lifecycle import OperationFiles, SpikeError
from .rich_assets import RichAssets
from .rich_synchronization import RichSynchronization


class RichProjectService(RichSynchronization, RichAssets, GuiProjectService):
    def __init__(self, temp_root, rules, provider_factory, *, import_runtime=None, import_provider_factory=None, **options):
        options.setdefault("storage", RichProjectStore(rules.root))
        options.setdefault("renderer", RichDocxRenderer())
        super().__init__(temp_root, rules, provider_factory, **options)
        self.catalog = ProjectCatalog(self.storage)
        self.storage.catalog = self.catalog
        self.images = {}
        self.generations = {}
        self.saved_baselines = {}
        self.agent_recovery_fences = set()
        self.catalog_recovery_fences = set()
        self.import_runtime = import_runtime
        self.import_provider_factory = import_provider_factory or (lambda: self.provider_factory())
        self.initialize_images()

    def require_agent_writable(self, identifier):
        if identifier in self.agent_recovery_fences or identifier in self.catalog_recovery_fences:
            raise ProjectFailure("AGENT_OUTCOME_UNKNOWN", 409)
        jobs = getattr(self, "background_jobs", None)
        if jobs is not None and jobs.enabled and (jobs.store.projects / identifier).exists():
            try:
                state = jobs.store.load(identifier)
                jobs.publisher._writable(state)
            except BackgroundFailure as error:
                raise ProjectFailure(error.code, 409) from None

    def rename(self, identifier, request):
        self.require_agent_writable(identifier)
        return super().rename(identifier, request)

    def ensure_loaded(self):
        if self.loaded:
            return
        with self.state_lock:
            if self.loaded:
                return
            from .agent.project_action_recovery import recover_actions
            recover_actions(self)
            try:
                loaded, self.load_errors, registry = self.storage.load_all()
            except ProjectStoreFailure as error:
                raise ProjectFailure(error.code, 503) from None
            self.deleted_ids.update(entry.project_id for entry in registry.entries if entry.tombstoned)
            self.loaded = True
            for identifier, (workspace, originals, artifacts, images) in loaded.items():
                self.workspaces[identifier] = workspace
                jobs = getattr(self, "background_jobs", None)
                baseline = self.storage.read_committed(identifier)[0] if jobs is not None and jobs.enabled else workspace.model_copy(deep=True)
                self.saved_baselines[identifier] = baseline
                self.originals.update(originals); self.artifacts.update(artifacts); self.images.update(images)
                bound = set()
                if jobs is not None and jobs.enabled and (jobs.store.projects / identifier).exists():
                    state = jobs.store.load(identifier)
                    bound = {job.submission.input.id for job in state.jobs if job.submission.input.kind == "rich_sync"}
                changed = workspace != baseline
                for operation in self.owner(workspace).operations:
                    if operation.status in {"running", "queued"}:
                        operation.status, operation.error_code = "interrupted", "OPERATION_INTERRUPTED"
                        changed = True
                for sync in workspace.sync_records:
                    if sync.status == "pending" and sync.id not in bound:
                        sync.error_code, sync.ready = "OPERATION_INTERRUPTED", False; changed = True
                if workspace.pre_draft and "EXTRACT_PENDING" in workspace.pre_draft.warnings:
                    workspace.pre_draft.warnings = ["EXTRACT_INTERRUPTED", "NO_USABLE_TEXT"]; changed = True
                self.saved_hashes[identifier] = digest(baseline.model_dump(mode="json", by_alias=True))
                self.saved_revisions[identifier] = (baseline.project_revision, baseline.document_revision)
                if changed:
                    self.persist(identifier)

    def read_memory(self, identifier):
        return WorkspaceV6.model_validate(self.workspaces[identifier].model_dump(by_alias=True))

    def read(self, identifier):
        super().read(identifier)
        jobs = getattr(self, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            with self.state_lock:
                try:
                    if (jobs.store.projects / identifier).exists():
                        with jobs.store.guard(identifier) as directory:
                            state = jobs.store._read(identifier, directory)
                            jobs.publisher._writable(state)
                            current, checksum = self.storage._read_committed_unlocked(identifier)
                            if state.history is not None or (directory / "history-activation.json").exists():
                                jobs.publisher.history._ready(state, directory, checksum)
                    else:
                        current, checksum = self.storage.read_committed(identifier)
                    base = self.saved_baselines.get(identifier)
                    if base is not None:
                        merged = merge_snapshot(base, self.read_memory(identifier), current)
                        self.adopt_committed(identifier, current, checksum, cache=merged)
                except (BackgroundFailure, ProjectStoreFailure) as error:
                    self.save_errors[identifier] = error.code
        return self.read_memory(identifier)

    def persist(self, identifier):
        with self.state_lock:
            if identifier in self.agent_recovery_fences or identifier in self.catalog_recovery_fences:
                self.save_errors[identifier] = "AGENT_OUTCOME_UNKNOWN"
                return "failed"
            if identifier in self.deleted_ids:
                self.save_errors[identifier] = "PROJECT_DELETED"; return "failed"
            try:
                snapshot = self.read_memory(identifier)
                jobs = getattr(self, "background_jobs", None)
                base = self.saved_baselines.get(identifier)
                if jobs is not None and jobs.enabled and base is not None:
                    jobs.store.open(identifier)
                    current, _duplicate = jobs.publisher.snapshot(identifier, digest_bytes(base), snapshot,
                        command_identity("metadata"), originals=self.originals, artifacts=self.artifacts,
                        images=self.images, base=base)
                    jobs.publication.adopt(identifier, current, digest_bytes(current), preserve=False)
                    return "durable"
                self.storage.save(snapshot, self.originals, self.artifacts, self.images)
                self.saved_baselines[identifier] = snapshot.model_copy(deep=True)
                self.saved_hashes[identifier] = digest(snapshot.model_dump(mode="json", by_alias=True))
                self.saved_revisions[identifier] = (snapshot.project_revision, snapshot.document_revision)
                self.save_errors.pop(identifier, None)
                return "durable"
            except (ProjectStoreFailure, BackgroundFailure) as error:
                self.save_errors[identifier] = error.code
                return "failed"

    def adopt_committed(self, identifier, workspace, checksum, *, cache=None, preserve=False):
        with self.state_lock:
            cached = self.workspaces.get(identifier)
            if preserve and cached is not None and identifier in self.saved_baselines:
                base = self.saved_baselines[identifier]
                if cached.project_revision < base.project_revision or cached.document_revision < base.document_revision:
                    cache = None
                else:
                    try:
                        cache = merge_snapshot(base, self.read_memory(identifier), workspace)
                    except BackgroundFailure as error:
                        self.save_errors[identifier] = error.code
                        return
            value = cache if cache is not None else workspace
            self.workspaces[identifier] = reconcile(cached, value) if cached is not None else value.model_copy(deep=True)
            self.saved_baselines[identifier] = workspace.model_copy(deep=True)
            self.storage.expected[identifier] = checksum
            self.saved_hashes[identifier] = digest(workspace.model_dump(mode="json", by_alias=True))
            self.saved_revisions[identifier] = (workspace.project_revision, workspace.document_revision)
            if cache is None or cache == workspace:
                self.save_errors.pop(identifier, None)

    def response(self, identifier):
        from packages.resume_core.rich_presentation import presentation
        workspace = self.read(identifier)
        saved = self.saved_revisions.get(identifier)
        jobs = getattr(self, "background_jobs", None)
        generation = jobs.fixed.generation(identifier) if jobs is not None and jobs.enabled else None
        return RichProjectResponse(workspace=workspace, durability=self.durability(identifier),
            savedProjectRevision=saved[0] if saved else None, savedDocumentRevision=saved[1] if saved else None,
            saveError=self.save_errors.get(identifier), generation=generation or self.generations.get(identifier),
            presentation=presentation(workspace.project.document, workspace.project.facts) if workspace.project else None,
            identity=resume_identity(workspace))

    def listing(self):
        self.ensure_loaded()
        entries = []
        catalog = self.catalog.entries()
        for entry in self.storage.registry().entries:
            if entry.tombstoned and entry.cleanup_status == "complete":
                continue
            value = entry.model_dump(mode="json", by_alias=True)
            meta = catalog.get(entry.project_id)
            value.update(lastOpenedAt=meta.last_opened_at if meta else None, archived=meta.archived if meta else False)
            if entry.project_id in self.workspaces:
                identity = resume_identity(self.workspaces[entry.project_id])
                value.update(title=identity.title, subtitle=identity.subtitle)
            entries.append(value)
        entries.sort(key=lambda entry: (entry["lastOpenedAt"] or entry["updatedAt"], entry["projectId"]), reverse=True)
        return {"entries": entries, "errors": [{"projectId": identifier, "errorCode": code} for identifier, code in self.load_errors.items()]}

    def activate(self, identifier):
        result = self.response(identifier)
        self.catalog.update(identifier, opened=True)
        return result

    def archive_entry(self, identifier, archived):
        with self.state_lock:
            self.catalog.update(identifier, archived=archived)
            return self.listing()

    async def drain_catalog_actions(self, *, run_id=None):
        from packages.resume_core.agent_store import AgentFailure
        from packages.resume_core.project_catalog import AccessChanged
        for key, command in self.catalog.actions().items():
            if command.get("action") != "delete" or command.get("status") not in {"pending", "deleting"}:
                continue
            if run_id is not None and command["runId"] != run_id:
                continue
            identifier = command["projectId"]
            entry = next((entry for entry in self.storage.registry().entries if entry.project_id == identifier), None)
            if command["status"] == "pending" and entry is not None and entry.tombstoned:
                command["status"] = "deleting"
                self.catalog.record_action(key, command)
            if command["status"] == "pending":
                completed = False
                jobs, agent = getattr(self, "background_jobs", None), getattr(self, "agent", None)
                current_revision = None
                try:
                    if entry is not None and jobs is not None and jobs.enabled:
                        job = next((job for job in jobs.store.load(identifier).jobs if job.id == command["runId"]), None)
                        completed = job is not None and job.execution == "completed" and job.error is None
                    elif entry is not None and agent is not None:
                        from packages.resume_core.agent_store import run_in
                        run = run_in(agent.store.load(identifier), command["runId"])[1]
                        completed = run.state == "completed" and run.error is None
                    if completed:
                        current_revision = self.read(identifier).project_revision
                except (AgentFailure, BackgroundFailure, ProjectFailure, ProjectStoreFailure, OSError, ValueError):
                    completed = False
                if not completed or current_revision != command.get("projectRevision"):
                    command["status"] = "cancelled"
                    command["result"] = {"durable": False, "error": {"code": "AGENT_CANCELLED" if not completed else "AGENT_STALE_READ"}}
                    self.catalog.record_action(key, command)
                    continue
                try:
                    with self.state_lock, self.catalog.authority(identifier, command["accessRevision"]):
                        self.storage.tombstone(identifier)
                        self.deleted_ids.add(identifier)
                        command["status"] = "deleting"
                        self.catalog.record_action(key, command)
                except AccessChanged:
                    command["status"] = "cancelled"
                    command["result"] = {"durable": False, "error": {"code": "AGENT_TOOL_DENIED"}}
                    self.catalog.record_action(key, command)
                    continue
            try:
                result = await self.delete_project(identifier)
            except (ProjectFailure, ProjectStoreFailure) as error:
                from packages.resume_core.gui_projects import GuiDeleteProjectResult
                result = GuiDeleteProjectResult(projectId=identifier, status="cleanup_incomplete", errorCode=error.code)
            command["status"] = result.status
            command["result"] = {"durable": result.status == "deleted", **result.model_dump(mode="json", by_alias=True)}
            self.catalog.record_action(key, command)

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
        with self.state_lock:
            pre = workspace.pre_draft
            pre.sources.append(source); pre.selected_input = "text" if pasted else "file"
            pre.selected_source_id, pre.warnings = source_id, ["EXTRACT_PENDING"]
            self.originals[(identifier, source_id)] = bytes(data)
            self.persist(identifier)
        files, cancel = OperationFiles(self.temp_root), threading.Event()
        key = (identifier, source_id)
        self.input_tasks[key], self.input_files[key], self.input_cancels[key] = asyncio.current_task(), files, cancel
        extracted, source_error = None, None
        try:
            async with self.worker_slot(cancel):
                with files.open():
                    result = await run_extract(data, name, pasted, files)
            extracted = canonical_source(result, source_id=source_id)
        except (UploadFailure, SpikeError, AdmissionCancelled) as error:
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
            source_error = getattr(error, "code", "EXTRACT_INTERRUPTED")
        finally:
            self.input_tasks.pop(key, None); self.input_files.pop(key, None); self.input_cancels.pop(key, None)
        with self.state_lock:
            workspace = self.workspaces.get(identifier)
            pre = workspace.pre_draft if workspace is not None else None
            if identifier not in self.deleted_ids and pre is not None and any(item.id == source_id for item in pre.sources):
                if extracted is not None:
                    pre.sources = [extracted if item.id == source_id else item for item in pre.sources]
                if self.selection_epochs[identifier] == source_id:
                    pre.warnings = [source_error, "NO_USABLE_TEXT"] if source_error else extracted.warnings[:]
                    if extracted is not None and not any(unit.text.strip() for unit in extracted.units):
                        pre.warnings.append("NO_USABLE_TEXT")
                workspace.updated_at = self.clock().isoformat()
                self.persist(identifier)
        return self.read(identifier)

    def start(self, identifier, previous=None, *, allow_text_rewrite=True):
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
        selected = self.import_provider_factory()
        if selected is None:
            raise ProjectFailure("CONNECTION_REQUIRED")
        try:
            rules = self.rules.load()
        except RulesFailure as error:
            raise ProjectFailure(error.code, 503) from None
        generation = RichGenerationState(id=identity("generation"), status="queued", stage="normalize_semantics",
            errorCode=None, startedAt=self.clock().isoformat())
        self.generations[identifier] = generation
        key = (identifier, generation.id)
        self.cancels[key] = threading.Event()
        from .importer.direct import run_import
        self.tasks[key] = asyncio.create_task(run_import(self, identifier, generation, rules, selected,
            allow_text_rewrite=allow_text_rewrite))
        return generation.id

    def new_operation(self, identifier, kind):
        with self.state_lock:
            self.require_agent_writable(identifier)
            operation = RichOperation(id=identity("operation"), kind=kind, status="queued", actionId=None, dependencies=[], errorCode=None)
            self.owner(self.workspaces[identifier]).operations.append(operation)
            if self.persist(identifier) == "failed":
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            return operation

    def finish_operation(self, identifier, operation_id, status, error_code=None):
        with self.state_lock:
            operation = next(op for op in self.owner(self.workspaces[identifier]).operations if op.id == operation_id)
            operation.status, operation.error_code = status, error_code

    def mutate(self, identifier, request):
        with self.state_lock:
            self.require_agent_writable(identifier)
            self.read(identifier)
            agent = getattr(self, "agent", None)
            if agent is not None and not agent.publication.manual_allowed(identifier, request):
                raise ProjectFailure("AGENT_TICKET_INVALID", 409)
            jobs = getattr(self, "background_jobs", None)
            if jobs is not None and jobs.enabled:
                if getattr(jobs, "writers", None) is not None:
                    raise ProjectFailure("WRITER_UNKNOWN", 409)
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
        jobs = getattr(self, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            from packages.resume_core.background_assets import JobAssets
            assets, owner = JobAssets(jobs.store), command_identity("export")
            try:
                captured, _checksum = assets.capture(identifier, "export", owner)
                images, _sources = assets.bytes_for(identifier, "export", owner)
                return await self._export(identifier, generation_id, captured, images, pinned=True)
            except BackgroundFailure as error:
                raise ProjectFailure(error.code, 409) from None
            finally:
                assets.release(identifier, "export", owner)
        return await self._export(identifier, generation_id, self.read(identifier),
            {aid: data for (pid, aid), data in self.images.items() if pid == identifier})

    async def _export(self, identifier, generation_id, captured, images, *, pinned=False):
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
                        images, files, captured.project.facts)
            with self.state_lock:
                if pinned and identifier not in self.deleted_ids and self.persist(identifier) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
                current = self.workspaces[identifier]
                if identifier in self.deleted_ids or cancel.is_set() or not pinned and (
                        current.document_revision != captured.document_revision or current.project.facts.revision != captured.project.facts.revision):
                    raise ProjectFailure("STALE_EXPORT")
                snapshot = RichRenderSnapshot(id=identity("render"), documentRevision=captured.document_revision,
                    factsRevision=captured.project.facts.revision, templateSha256=PACKAGE_SHA256,
                    rendererVersion=RENDERER_VERSION, rendererSha256=renderer_sha256(), docxSha256=hashlib.sha256(blob).hexdigest(),
                    docxSize=len(blob), docxPath="renders/" + identity("docx") + ".docx")
                if not pinned or not any(item.document_revision > snapshot.document_revision or (
                        item.document_revision == snapshot.document_revision and item.facts_revision > snapshot.facts_revision)
                        for item in current.project.renders):
                    current.project.renders = [snapshot]
                self.artifacts[(identifier, snapshot.id)] = blob
                self.finish_operation(identifier, operation.id, "completed")
                if self.persist(identifier) == "failed":
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
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
        jobs = getattr(self, "background_jobs", None)
        if jobs is not None and jobs.enabled:
            from packages.resume_core.background_assets import JobAssets
            assets, owner = JobAssets(jobs.store), command_identity("archive")
            try:
                workspace, _checksum = assets.capture(identifier, "export", owner)
                images, originals = assets.bytes_for(identifier, "export", owner)
                return self._portable(identifier, workspace, originals, images)
            except BackgroundFailure as error:
                raise ProjectFailure(error.code, 409) from None
            finally:
                assets.release(identifier, "export", owner)
        return self._portable(identifier, self.read(identifier),
            {sid: blob for (pid, sid), blob in self.originals.items() if pid == identifier},
            {aid: blob for (pid, aid), blob in self.images.items() if pid == identifier})

    def _portable(self, identifier, workspace, originals, images):
        artifacts = {rid: blob for (pid, rid), blob in self.artifacts.items() if pid == identifier}
        try:
            return export_rich_archive(workspace, originals, artifacts, images)
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
        self.ensure_loaded()
        tombstoned = any(entry.project_id == identifier and entry.tombstoned for entry in self.storage.registry().entries)
        if not tombstoned:
            try:
                self.storage._directory(identifier)
            except ProjectStoreFailure as error:
                raise ProjectFailure(error.code, 409) from None
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
            try:
                await jobs.stop_project(identifier)
            except BackgroundFailure as error:
                from packages.resume_core.gui_projects import GuiDeleteProjectResult
                return GuiDeleteProjectResult(projectId=identifier, status="cleanup_incomplete", errorCode=error.code)
        for (pid, _), session in self.image_sessions.items():
            if pid == identifier:
                session.closed = True
        result = await super().delete_project(identifier)
        if result.status == "deleted" and jobs is not None and jobs.enabled:
            try:
                jobs.store.cleanup_deleted(identifier)
            except BackgroundFailure as error:
                from packages.resume_core.gui_projects import GuiDeleteProjectResult
                return GuiDeleteProjectResult(projectId=identifier, status="cleanup_incomplete", errorCode=error.code)
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
