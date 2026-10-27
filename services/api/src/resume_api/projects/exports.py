"""One repository commit records a completed export. Rendering uses the existing worker."""

from __future__ import annotations

import asyncio
import hashlib
import threading
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.resume_core.models.rich_workspace import RichRenderSnapshot
from packages.resume_core.models.template_render import TemplateRenderRequestV1, TemplateSnapshotIdentity
from packages.resume_core.rich_limits import DOCX_BYTES
from packages.resume_core.template_export import capture_export
from packages.resume_core.template_import import TemplateImportFailure
from packages.resume_core.templates.compiler import sha256

from .errors import ProjectFailure


class ExportCommand(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: Literal[1] = Field(alias='schemaVersion')
    snapshot: TemplateSnapshotIdentity
    editor_token: str = Field(alias='editorToken', min_length=1)


class ExportRetry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    editor_token: str = Field(alias='editorToken', min_length=1)


@dataclass
class ExportResult:
    attempt: object
    snapshot: object
    artifact: bytes


class ExportService:
    def __init__(self, projects, render, renderer=None):
        self.projects = projects
        self.render = render
        self._renderer = renderer

    @property
    def renderer(self):
        if self._renderer is None:
            from packages.resume_core.rendering.captured_docx import renderer_identity
            self._renderer = renderer_identity()
        return self._renderer

    async def export(self, project_id, snapshot, editor_token, *, retry_attempt_id=None, trusted=False):
        """`trusted` is the assistant's server-side export: it has no page, so no editor token."""
        task = self.projects.tasks.start(project_id, 'export', stage='rendering')
        session = self.projects.repository.open(project_id)
        with session.lock:
            session.pins += 1
        try:
            prepared = await asyncio.to_thread(self._prepare, project_id, snapshot, editor_token, retry_attempt_id, trusted)
            artifact = await self.render(prepared.request)
            if not isinstance(artifact, bytes) or not 0 < len(artifact) <= DOCX_BYTES:
                raise ProjectFailure('IMPORT_EXPORT_INVALID_ARTIFACT', 422)
            result = await asyncio.to_thread(self._record, project_id, prepared, artifact)
            self.projects.tasks.finish(task.id, 'succeeded', detail={'attemptId': result.attempt.id})
            return result
        except ProjectFailure as error:
            self.projects.tasks.finish(task.id, 'failed', error=error.code)
            raise
        except TemplateImportFailure as error:
            self.projects.tasks.finish(task.id, 'failed', error=error.code)
            raise ProjectFailure(error.code, 409) from None
        except BaseException as error:
            self.projects.tasks.finish(task.id, 'failed', error=getattr(error, 'code', 'PROCESS_FAILED'))
            raise
        finally:
            with session.lock:
                session.pins -= 1

    def _prepare(self, project_id, snapshot, editor_token, retry_attempt_id, trusted=False):
        session = self.projects.repository.open(project_id)
        with session.lock:
            if not trusted:
                session.require_editor(editor_token)
            workspace = session.workspace
            project = workspace.project
            if project is None:
                raise ProjectFailure('IMPORT_PROJECT_NOT_AUTHORED', 409)
            retry = None
            if retry_attempt_id is not None:
                retry = next((value for value in project.export_inputs if value.attempt_id == retry_attempt_id), None)
                if retry is None:
                    raise ProjectFailure('IMPORT_EXPORT_ATTEMPT_UNKNOWN', 409)
            try:
                attempt, captured = capture_export(workspace, snapshot, self.renderer, retry_capture=retry)
            except TemplateImportFailure as error:
                raise ProjectFailure(error.code, 409) from None
            request = TemplateRenderRequestV1.model_validate({**captured.request.model_dump(by_alias=True),
                'package': project.template_package})
            return _Prepared(workspace.project_revision, attempt, captured, request)

    def _record(self, project_id, prepared, artifact):
        digest = sha256(artifact)
        session = self.projects.repository.open(project_id)
        with session.lock:
            if session.revision != prepared.revision:
                raise ProjectFailure('REVISION_CONFLICT', 409)
            updated = session.workspace.model_copy(deep=True)
            attempt = prepared.attempt.model_copy(update={'state': 'completed', 'artifact_hash': digest, 'error_code': None})
            render = RichRenderSnapshot(id=attempt.id, documentRevision=prepared.captured.snapshot.document_revision,
                factsRevision=prepared.captured.request.facts.revision, templateSha256=prepared.captured.request.package_hash,
                rendererVersion=prepared.captured.request.renderer.version, rendererSha256=prepared.captured.request.renderer.sha256,
                docxSha256=digest, docxSize=len(artifact), docxPath='renders/' + attempt.id + '.docx')
            updated.project.exports.append(attempt)
            updated.project.export_inputs.append(prepared.captured)
            updated.project.renders.append(render)
            if attempt.publication_intent_id is not None:
                operation = next((value for value in updated.project.template_operations
                    if value.publication.intent_id == attempt.publication_intent_id), None)
                if operation is not None:
                    operation.export_attempts.append(attempt.model_copy(deep=True))
            self.projects.repository.replace(project_id, base_revision=prepared.revision, workspace=updated, reason='export',
                blobs=[('renders', attempt.id, artifact, digest)], client_mutation_id='export-' + attempt.id,
                request_sha256=hashlib.sha256(attempt.id.encode()).hexdigest())
        return ExportResult(attempt, prepared.captured.snapshot, artifact)


@dataclass
class _Prepared:
    revision: int
    attempt: object
    captured: object
    request: object


async def production_render(owner, request):
    """The DOCX worker already used by the legacy exporter, in its own operation directory."""
    from ..inference_admission import AdmissionCancelled
    from ..lifecycle import OperationFiles, SpikeError
    files, cancel = OperationFiles(owner.temp_root), threading.Event()
    try:
        async with owner.worker_slot(cancel):
            if cancel.is_set():
                raise ProjectFailure('CANCELLED', 409)
            with files.open():
                blob = await owner.renderer.render_template(request, files)
            if cancel.is_set():
                raise ProjectFailure('CANCELLED', 409)
            return blob
    except ProjectFailure:
        raise
    except AdmissionCancelled:
        raise ProjectFailure('CANCELLED', 409) from None
    except SpikeError as error:
        raise ProjectFailure(error.code, 503) from None
