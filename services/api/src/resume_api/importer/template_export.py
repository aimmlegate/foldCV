"""Captured export outcomes persist independently of import and inference."""

import asyncio
from dataclasses import dataclass
import inspect

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.rich_workspace import RichRenderSnapshot
from packages.resume_core.models.template_render import TemplateRenderRequestV1
from packages.resume_core.rich_limits import DOCX_BYTES
from packages.resume_core.template_export import capture_export, snapshot_identity
from packages.resume_core.template_import import TemplateImportFailure
from packages.resume_core.templates.compiler import sha256


@dataclass(frozen=True)
class TemplateExportResult:
    attempt: object
    snapshot: object
    artifact: bytes | None


class TemplateExporter:
    def __init__(self, pipeline, renderer, render=None, *, render_async=None):
        if (render is None) == (render_async is None) or render is not None and inspect.iscoroutinefunction(render):
            raise ValueError('Provide exactly one synchronous or asynchronous renderer')
        self.pipeline, self.renderer = pipeline, renderer
        self.render, self.render_async = render, render_async
        self.tasks = pipeline.publisher.template_export_tasks

    def _retain(self, key, coroutine, *, retain_failure=False):
        task = asyncio.create_task(coroutine)
        self.tasks[key] = task
        def finished(result):
            error = result.exception() if not result.cancelled() else True
            if retain_failure and error:
                return
            if self.tasks.get(key) is result:
                self.tasks.pop(key)
        task.add_done_callback(finished)
        return task

    @staticmethod
    def _state(workspace, captured, status, artifact=None, error=None):
        attempt = next(value for value in workspace.project.exports if value.id == captured.attempt_id)
        if attempt.state in {'completed', 'failed'}:
            return workspace
        attempt.state, attempt.error_code = status, error
        attempt.artifact_hash = sha256(artifact) if artifact is not None else None
        if artifact is not None:
            workspace.project.renders.append(RichRenderSnapshot(id=attempt.id,
                documentRevision=captured.snapshot.document_revision, factsRevision=captured.request.facts.revision,
                templateSha256=captured.request.package_hash, rendererVersion=captured.request.renderer.version,
                rendererSha256=captured.request.renderer.sha256, docxSha256=attempt.artifact_hash,
                docxSize=len(artifact), docxPath='renders/' + attempt.id + '.docx'))
        for operation in workspace.project.template_operations:
            for index, prior in enumerate(operation.export_attempts):
                if prior.id == attempt.id:
                    operation.export_attempts[index] = attempt.model_copy(deep=True)
        return workspace

    async def _cancel(self, project, captured, render_task):
        if render_task is not None:
            try:
                await asyncio.shield(render_task)
            except Exception:
                pass
        if self.pipeline.checkpoint_owners.get(project) == captured.attempt_id or (
                project in self.pipeline.checkpoint_fences and self.pipeline.checkpoint_fences[project] == captured.attempt_id):
            current = await self.pipeline.reconcile_checkpoint(project, operation_id=captured.attempt_id)
        else:
            current = self.pipeline.read(project)
        if not any(value.id == captured.attempt_id for value in current.project.exports):
            return
        saved = await self.pipeline.checkpoint_async(project,
            lambda workspace: self._state(workspace, captured, 'failed', error='CANCELLED'), operation_id=captured.attempt_id)
        actual = next(value for value in saved.project.exports if value.id == captured.attempt_id)
        artifact = self.pipeline.artifacts.get((project, actual.id)) if actual.state == 'completed' else None
        return TemplateExportResult(actual, captured.snapshot, artifact)

    async def export(self, project, expected, *, retry_attempt_id=None, publication_intent_id=None):
        initial = self.pipeline.read(project)
        if initial.project is None:
            raise TemplateImportFailure('IMPORT_PROJECT_NOT_AUTHORED')
        retry = next((value for value in initial.project.export_inputs if value.attempt_id == retry_attempt_id), None)
        if retry_attempt_id is not None and retry is None:
            raise TemplateImportFailure('IMPORT_EXPORT_ATTEMPT_UNKNOWN')
        if retry is not None:
            previous = next(value for value in initial.project.exports if value.id == retry_attempt_id)
            if publication_intent_id is not None and publication_intent_id != previous.publication_intent_id:
                raise TemplateImportFailure('IMPORT_EXPORT_PUBLICATION_UNKNOWN')
            publication_intent_id = previous.publication_intent_id
        attempt, captured = capture_export(initial, expected, self.renderer, retry_capture=retry,
            publication_intent_id=publication_intent_id, id_factory=self.pipeline.id_factory)

        def capture(workspace):
            if workspace.project is None:
                raise TemplateImportFailure('IMPORT_PROJECT_NOT_AUTHORED')
            if retry is None and snapshot_identity(workspace) != expected:
                raise TemplateImportFailure('IMPORT_EXPORT_SNAPSHOT_STALE')
            if retry is not None and retry not in workspace.project.export_inputs:
                raise TemplateImportFailure('IMPORT_EXPORT_ATTEMPT_UNKNOWN')
            workspace.project.exports.append(attempt.model_copy(deep=True))
            workspace.project.export_inputs.append(captured.model_copy(deep=True))
            if publication_intent_id is not None:
                operation = next((value for value in workspace.project.template_operations
                    if value.publication.intent_id == publication_intent_id), None)
                if operation is None:
                    raise TemplateImportFailure('IMPORT_EXPORT_PUBLICATION_UNKNOWN')
                operation.export_attempts.append(attempt.model_copy(deep=True))
            return workspace

        render_task = None
        try:
            await self.pipeline.checkpoint_async(project, capture, operation_id=attempt.id)
            await self.pipeline.checkpoint_async(project, lambda workspace: self._state(workspace, captured, 'running'), operation_id=attempt.id)
            artifact, code = None, None
            try:
                render_request = TemplateRenderRequestV1.model_validate({**captured.request.model_dump(by_alias=True),
                    'package': self.pipeline.read(project).project.template_package})
                if self.render_async is not None:
                    artifact = await self.render_async(render_request)
                else:
                    render_task = self._retain((project, attempt.id, 'render'), asyncio.to_thread(self.render, render_request))
                    artifact = await asyncio.shield(render_task)
                if not isinstance(artifact, bytes) or not 0 < len(artifact) <= DOCX_BYTES:
                    raise TemplateImportFailure('IMPORT_EXPORT_INVALID_ARTIFACT')
            except Exception as error:
                code = getattr(error, 'code', 'RENDER_FAILED')
                artifact = None
            if artifact is not None:
                self.pipeline.artifacts[(project, attempt.id)] = artifact
            saved = await self.pipeline.checkpoint_async(project,
                lambda workspace: self._state(workspace, captured, 'failed' if code else 'completed', artifact, code), operation_id=attempt.id)
            actual = next(value for value in saved.project.exports if value.id == attempt.id)
            if actual.state != 'completed':
                self.pipeline.artifacts.pop((project, attempt.id), None)
            return TemplateExportResult(actual, captured.snapshot, artifact if actual.state == 'completed' else None)
        except asyncio.CancelledError:
            cleanup = self._retain((project, attempt.id, 'cleanup'), self._cancel(project, captured, render_task), retain_failure=True)
            try:
                result = await asyncio.wait_for(asyncio.shield(cleanup), self.pipeline.cleanup_seconds)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.pipeline.fence_checkpoint(project, attempt.id)
                raise BackgroundFailure('OUTCOME_UNKNOWN') from None
            except Exception:
                self.pipeline.fence_checkpoint(project, attempt.id)
                raise
            if result is not None and result.attempt.state == 'completed':
                return result
            raise
