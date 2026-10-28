"""Template import intake: an upload becomes a V7 pre-draft with the store's active package, and the import start
captures its package, sources, models and limits.

The runtime call cap has no default: without an explicit configured value the import is unavailable.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import threading

from packages.resume_core.dates import partial_date
from packages.resume_core.models.contracts import Source
from packages.resume_core.models.template_import import MAX_IMPORT_CONCURRENCY, ImportCapture, RuntimePolicy, StartTemplateImportV1
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.project_limits import finalization_seconds, import_seconds
from packages.resume_core.sources import canonical_source
from packages.resume_core.template_import import TemplateImportFailure, digest, identity
from packages.resume_core.templates.store import TemplateStore

from ..extracting import UploadFailure, run_extract
from ..inference_admission import AdmissionCancelled
from ..lifecycle import OperationFiles, SpikeError
from .errors import ProjectFailure

CANCEL_SECONDS = 65


def _now():
    return datetime.now(timezone.utc)


class TemplateIntake:
    def __init__(self, repository, *, temp_root, worker_slot, cleanup_error, clock=_now):
        self.repository, self.temp_root = repository, temp_root
        self.worker_slot, self.cleanup_error, self.clock = worker_slot, cleanup_error, clock
        self.call_cap, self.model, self.fallback, self.concurrency = None, None, None, 1
        # Set once the import pipeline exists; without it no upload creates a project.
        self.ready = False
        self.extractions = {}

    def configure(self, *, call_cap, model, fallback=None, concurrency=1):
        """`model(effort=None)` returns the ModelCapture for the selected import model with that effort, else its
        catalog default, or raises ProjectFailure (also for an effort the catalog does not offer). `fallback`, given
        that capture, returns the configured fallback model's capture, None when there is none, or raises.
        `concurrency` is how many independent blocks one import runs at once (CT10); 1 is sequential."""
        if call_cap is not None and (not isinstance(call_cap, int) or call_cap < 1):
            raise ValueError('template import call cap must be an explicit positive integer')
        if not isinstance(concurrency, int) or not 1 <= concurrency <= MAX_IMPORT_CONCURRENCY:
            raise ValueError('template import concurrency must be an integer from 1 to ' + str(MAX_IMPORT_CONCURRENCY))
        self.call_cap, self.model, self.fallback, self.concurrency = call_cap, model, fallback, concurrency

    def package(self):
        return TemplateStore(self.repository.root).active()

    def status(self):
        available = self.call_cap is not None and self.model is not None and self.ready
        package = self.package() if available else None
        return {'schemaVersion': 1, 'available': available, 'package': None if package is None else {
            'id': package.id, 'name': package.definition.template.name, 'revision': package.revision,
            'packageHash': package.package_hash}}

    async def create(self, data, name, pasted):
        """Extract the upload, then store one pre-draft with its source; a failed extraction keeps the bytes and
        names the failure in the pre-draft warnings."""
        if not self.status()['available']:
            raise ProjectFailure('JOB_DISABLED', 409)
        package = self.package()
        project_id, source_id = identity('project'), identity('source')
        source = Source.model_validate({'id': source_id, 'revision': 1, 'originalName': name,
            'mimeType': 'text/plain' if pasted else 'application/octet-stream',
            'byteSha256': hashlib.sha256(data).hexdigest(), 'byteRef': f'sources/{source_id}/original',
            'parser': 'pending', 'parserVersion': '1', 'units': [], 'overlays': [], 'warnings': []})
        files, cancel = OperationFiles(self.temp_root), threading.Event()
        key = (project_id, source_id)
        self.extractions[key] = (asyncio.current_task(), files, cancel)
        extracted, error = None, None
        try:
            async with self.worker_slot(cancel):
                with files.open():
                    result = await run_extract(data, name, pasted, files)
            extracted = canonical_source(result, source_id=source_id)
        except (UploadFailure, SpikeError, AdmissionCancelled) as failure:
            if isinstance(failure, SpikeError):
                self.cleanup_error(failure)
            error = getattr(failure, 'code', 'EXTRACT_INTERRUPTED')
        finally:
            self.extractions.pop(key, None)
        if extracted is not None:
            source = extracted
            warnings = extracted.warnings[:]
            if not any(unit.text.strip() for unit in extracted.units):
                warnings.append('NO_USABLE_TEXT')
        else:
            warnings = [error, 'NO_USABLE_TEXT']
        stamp = self.clock()
        workspace = WorkspaceV7.model_validate({'schemaVersion': 7, 'projectId': project_id,
            'projectRevision': 1, 'documentRevision': 1, 'title': 'Новое резюме' if pasted else name,
            'titleManuallySet': False, 'createdAt': stamp.isoformat(), 'updatedAt': stamp.isoformat(), 'project': None,
            'preDraft': {'sources': [source.model_dump(mode='json', by_alias=True)],
                'facts': {'schemaVersion': 2, 'revision': 1, 'records': [], 'tombstones': [], 'extensions': [],
                    'observations': [], 'relations': [], 'manualScopes': []},
                'selectedInput': 'text' if pasted else 'file', 'selectedSourceId': source_id, 'operations': [],
                'warnings': warnings, 'templatePackage': package.model_dump(by_alias=True), 'templateOperations': []},
            'formattingAsOf': partial_date(stamp.date().isoformat()).model_dump(by_alias=True), 'sourceObservedAt': None,
            'rulesUsed': None, 'syncRecords': [], 'mutationReplay': [], 'warnings': []})
        await asyncio.to_thread(self.repository.create, workspace,
            [('sources', source_id, bytes(data), source.byte_sha256)])
        return project_id

    def request_shutdown(self):
        for _task, _files, cancel in list(self.extractions.values()):
            cancel.set()

    async def shutdown(self):
        """Stop running extractions and wait for them; a worker that does not stop blocks new work."""
        self.request_shutdown()
        for task, files, _cancel in list(self.extractions.values()):
            try:
                files.stop_worker()
            except SpikeError as error:
                self.cleanup_error(error)
                raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503) from None
            if task is None or task is asyncio.current_task() or task.done():
                continue
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=CANCEL_SECONDS)
            except asyncio.TimeoutError:
                self.cleanup_error(SpikeError('PROCESS_CLEANUP_FAILED'))
                raise ProjectFailure('PROCESS_CLEANUP_FAILED', 503) from None
            except Exception:
                pass

    def command(self, project_id, client_request_id, allow_text_rewrite, effort=None, *, workspace):
        pre = workspace.pre_draft
        if workspace.schema_version != 7 or workspace.project is not None or pre is None or pre.template_package is None:
            raise ProjectFailure('IMPORT_PROTOCOL_MISMATCH', 409)
        if not pre.sources or not any(unit.text.strip() for source in pre.sources for unit in source.units):
            raise ProjectFailure('NO_USABLE_TEXT', 409)
        capture = self.capture(workspace, allow_text_rewrite, effort=effort)
        return StartTemplateImportV1(kind='start_new_import', protocol='template_import_v1', clientRequestId=client_request_id,
            capture=capture)

    def capture(self, workspace, allow_text_rewrite, models=None, *, effort=None):
        data = workspace.project or workspace.pre_draft
        package, sources = data.template_package, {source.id: source.byte_sha256 for source in data.sources}
        if models is not None:
            primary, fallback = models
        else:
            primary = self.model(effort=effort)
            fallback = self.fallback(primary) if self.fallback else None
        models = {'model': primary.model_dump(mode='json', by_alias=True)}
        if fallback is not None:
            models['fallback'] = fallback.model_dump(mode='json', by_alias=True)
        return ImportCapture(packageHash=package.package_hash, sourceHashes=sources,
            factRevisions={record.id: record.revision for record in [*data.facts.records, *data.facts.extensions]
                if getattr(record, 'active', True)},
            authorityHash=digest({'project': workspace.project_id, **models}),
            dependencyHash=digest({'package': package.package_hash, 'sources': sources}), allowTextRewrite=allow_text_rewrite,
            primary=primary, fallback=fallback, formattingAsOf=workspace.formatting_as_of,
            policy=RuntimePolicy(callCap=self.call_cap, concurrency=self.concurrency,
                processingSeconds=import_seconds(), cleanupSeconds=5,
                finalizationSeconds=finalization_seconds(), primaryRepairs=1, fallbackRepairs=1))

    def validate(self, operation, workspace):
        data = workspace.project or workspace.pre_draft
        if data is None or data.template_package is None or self.call_cap is None:
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
        # Facts advance through admitted proposals; the pipeline checks their captured revisions separately.
        # A stored import keeps the time limits, concurrency and models captured at its start when Settings change
        # (E07); a new one must match.
        # A published project names its records by history file (D104).
        stored = any(value.id == operation.id for value in data.template_operations) or any(
            ref.operation_id == operation.id for ref in getattr(data, 'import_history', []))
        try:
            # A new operation carries the effort its start chose; the catalog must still offer it.
            expected = self.capture(workspace, operation.capture.allow_text_rewrite,
                models=(operation.capture.primary, operation.capture.fallback) if stored else None,
                effort=None if stored else operation.capture.primary.effort)
        except ProjectFailure:
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE') from None
        ignored = {'fact_revisions': True, **({'policy': {'processing_seconds', 'finalization_seconds', 'concurrency'}} if stored else {})}
        if expected.model_dump(exclude=ignored) != operation.capture.model_dump(exclude=ignored):
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
