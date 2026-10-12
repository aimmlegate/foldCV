"""Explicit zero-call DOCX export on the canonical project service."""

import asyncio
import hashlib
import threading
import uuid

from pydantic import ValidationError

from packages.resume_core.gui_exports import export_fingerprint, matching_snapshot
from packages.resume_core.gui_normalization import source_fingerprint
from packages.resume_core.gui_rendering import render_input
from packages.resume_core.models.recovery import Dependencies, GuiOperation, RenderSnapshotV4
from packages.resume_core.rendering.docx_errors import DocxFailure, failure
from packages.resume_core.rendering.template import PACKAGE_SHA256, RenderFailure, renderer_sha256, require_docx_template
from .gui_admission import AdmissionCancelled
from .gui_errors import ProjectFailure
from .lifecycle import OperationFiles, SpikeError


class GuiExportMixin:
    def start_export(self, id, request):
        try:
            self.read(id)
            fingerprint = export_fingerprint(request)
        except ValidationError:
            raise ProjectFailure("EXPORT_INVALID_DOCUMENT", 422) from None
        except UnicodeError:
            raise ProjectFailure("INVALID_CONTENT_INPUT", 422) from None
        with self.state_lock:
            workspace = self.workspaces[id]
            if workspace.project is None:
                raise ProjectFailure("DOCUMENT_UNAVAILABLE")
            previous = next((item for item in workspace.project.operations if item.id == request.client_request_id), None)
            if previous:
                if previous.kind != "render" or not previous.dependencies or previous.dependencies.dependency_fingerprint != fingerprint:
                    raise ProjectFailure("REQUEST_ID_REUSED")
                return previous.id
            if (request.project_revision, request.document_revision) != (workspace.project_revision, workspace.document_revision):
                raise ProjectFailure("EXPORT_STALE")
            if any(item.kind == "render" and (id, item.id) in self.tasks and not self.tasks[(id, item.id)].done()
                   for item in workspace.project.operations):
                raise ProjectFailure("EXPORT_ACTIVE")
            if self.persist(id) == "failed":
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            operation = GuiOperation(id=request.client_request_id, kind="render", status="queued", baseRevision=workspace.project_revision,
                usage=None, events=[], projectId=id, capturedDocumentRevision=workspace.document_revision,
                dependencies=None, rulesUsed=workspace.rules_used, targetFieldIds=[], resultFingerprint=None, errorCode=None)
            workspace.project.operations.append(operation)
            operation.dependencies = Dependencies(projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
                rulesSha256=workspace.rules_used.sha256 if workspace.rules_used else None,
                sourceFingerprint=source_fingerprint(workspace.project.sources), dependencyFingerprint=fingerprint)
            captured = self.read_memory(id)
            if self.persist(id) == "failed":
                operation.status, operation.error_code = "failed", "PROJECT_SAVE_FAILED"
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
            key = (id, operation.id)
            self.cancels[key] = threading.Event()
            self.tasks[key] = asyncio.create_task(self._run_export(captured, operation))
            return operation.id

    async def _run_export(self, captured, operation):
        id, oid = captured.project_id, operation.id
        key, cancel = (id, oid), self.cancels[(id, oid)]
        files = OperationFiles(self.temp_root)
        self.files[key] = files
        try:
            require_docx_template()
            document, anchors, fingerprint = render_input(captured)
            renderer = renderer_sha256()
            cached = next((snapshot for snapshot in reversed(captured.project.renders)
                if matching_snapshot(captured, snapshot, self.artifacts.get((id, snapshot.id)), fingerprint, renderer)), None)
            if cached is None:
                operation.status = "running"
                self._event(operation, "operation.started")
                if id in self.save_errors:
                    raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
                async with self.worker_slot(cancel):
                    with files.open():
                        content = await self.renderer.render(document, anchors, files)
            with self.state_lock:
                workspace = self.workspaces[id]
                if cancel.is_set():
                    raise AdmissionCancelled()
                if (workspace.project_revision, workspace.document_revision) != (captured.project_revision, captured.document_revision) or renderer_sha256() != renderer or render_input(workspace)[2] != fingerprint:
                    raise ProjectFailure("EXPORT_STALE")
                if cached is None:
                    rid = "render-" + uuid.uuid4().hex
                    cached = RenderSnapshotV4(id=rid, projectRevision=captured.project_revision, documentRevision=captured.document_revision,
                        renderInputFingerprint=fingerprint, templateId="generic", templateVersion="1.0.0", templateSha256=PACKAGE_SHA256,
                        rendererVersion="1.0.0", rendererSha256=renderer,
                        docx={"path": f"renders/{rid}/resume.docx", "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)},
                        pdf=None, artifactAvailable=True)
                    workspace.project.renders.append(cached)
                    self.artifacts[(id, rid)] = content
                operation.status, operation.render_snapshot_id = "completed", cached.id
                operation.result_fingerprint = fingerprint
                self._event(operation, "operation.completed", save=False)
        except (DocxFailure, RenderFailure, SpikeError, ProjectFailure, AdmissionCancelled, asyncio.TimeoutError) as error:
            if isinstance(error, SpikeError):
                self.cleanup_error(error)
            operation.status = "cancelled" if cancel.is_set() or isinstance(error, AdmissionCancelled) else "failed"
            operation.error_code = "CANCELLED" if operation.status == "cancelled" else getattr(error, "code", "DOCX_RENDER_FAILED")
            if isinstance(error, DocxFailure):
                operation.docx_error = error.error
            elif operation.status != "cancelled" and not isinstance(error, ProjectFailure):
                operation.docx_error = failure("DOCX_RENDER_FAILED").error
            self._event(operation, "cancelled" if operation.status == "cancelled" else "operation.failed", save=False)
        except Exception:
            operation.status, operation.error_code = "failed", "DOCX_RENDER_FAILED"
            operation.docx_error = failure("DOCX_RENDER_FAILED").error
            self._event(operation, "operation.failed", save=False)
        finally:
            self.files.pop(key, None)
            self.persist(id)

    def export_artifact(self, id, oid):
        try:
            self.read(id)
        except ValidationError:
            raise ProjectFailure("EXPORT_INVALID_DOCUMENT", 422) from None
        with self.state_lock:
            workspace = self.workspaces[id]
            if workspace.project is None:
                raise ProjectFailure("EXPORT_UNAVAILABLE")
            operation = next((item for item in workspace.project.operations if item.id == oid and item.kind == "render"), None)
            if operation is None or operation.status != "completed":
                raise ProjectFailure("EXPORT_UNAVAILABLE")
            snapshot = next((item for item in workspace.project.renders if item.id == operation.render_snapshot_id), None)
            content = self.artifacts.get((id, operation.render_snapshot_id))
            try:
                require_docx_template()
                fingerprint = render_input(workspace)[2]
            except (DocxFailure, RenderFailure, ValueError):
                raise ProjectFailure("EXPORT_STALE") from None
            if snapshot is None or not matching_snapshot(workspace, snapshot, content, fingerprint, renderer_sha256()):
                raise ProjectFailure("EXPORT_STALE")
            if (operation.base_revision, operation.captured_document_revision) != (workspace.project_revision, workspace.document_revision):
                raise ProjectFailure("EXPORT_STALE")
            return content
