"""Run the existing import coordinator with repository checkpoints and the durable operation sidecar."""

from __future__ import annotations

import asyncio
import hashlib
import time

from packages.resume_core.models.template_import import PublicationOutcome
from packages.resume_core.project_repository import RepositoryFailure, decode_project, rich_snapshot_bytes, verifying
from packages.resume_core.template_finalization import capture_finalization
from packages.resume_core.template_import import (TemplateImportFailure, cancel_operation, checked, identity,
    reconcile_cleanup, recover_operation)

from ..importer.template_pipeline import TemplatePipeline, operation_in, owner
from .fold import sidecar_store
from .blobs import retained_blobs


class RepositoryPipeline(TemplatePipeline):
    def __init__(self, _publisher, transport, *, repository, originals, authority, assemble, derive,
                 artifacts=None, images=None, wall, elapsed=time.monotonic, id_factory=identity):
        self.repository, self.transport = repository, transport
        self.originals = originals
        self.artifacts = artifacts if artifacts is not None else {}
        self.images = images if images is not None else {}
        self.authority, self.assemble, self.derive = authority, assemble, derive
        self.wall, self.elapsed, self.id_factory = wall, elapsed, id_factory
        self.locks, self.cancels, self.read_cache = {}, {}, {}

    def read(self, project):
        session = self.repository.open(project)
        with session.lock:
            workspace = session.workspace
            data = owner(workspace)
            if workspace.project is not None and not data.history_loaded:
                workspace = decode_project(session.directory, rich_snapshot_bytes(workspace), history=True)
                data = owner(workspace)
            sidecar = sidecar_store(session.directory)
            key = (id(session.workspace), sidecar.keys(project, workspace))
            cached = self.read_cache.get(project)
            if cached is not None and cached[0] == key and not verifying():
                return cached[1]
            overlays = [sidecar.overlay(project, session.revision, value) for value in data.template_operations]
            facts = [value for _operation, value in overlays if value is not None]
            if len(facts) > 1:
                raise RepositoryFailure('OUTCOME_UNKNOWN')
            view = workspace.model_copy(deep=True)
            holder = owner(view)
            holder.template_operations = [operation for operation, _facts in overlays]
            if facts:
                holder.facts = facts[0]
            if cached is not None and cached[0] == key:
                if cached[1] != view:
                    raise RuntimeError('Import read cache changed')
                return cached[1]
            self.read_cache[project] = (key, view)
            return view

    def checkpoint(self, project, transition, **_options):
        session = self.repository.open(project)
        with session.lock:
            before = self.read(project)
            after = transition(before.model_copy(deep=True))
            if after == before:
                return before
            identifier = self.id_factory('metadata_template')
            self.repository.replace(project, base_revision=before.project_revision, workspace=after,
                blobs=retained_blobs(project, after, self.originals, self.artifacts, self.images), reason='import',
                client_mutation_id=identifier, request_sha256=hashlib.sha256(identifier.encode()).hexdigest())
            return self.read(project)

    def update_operation(self, project, operation_id, transition, *, copy_on_write=False):
        del copy_on_write
        session = self.repository.open(project)
        with session.lock:
            before = self.read(project)
            view = before.model_copy(deep=True)
            data = owner(view)
            prior = operation_in(view, operation_id)
            updated = checked(transition(prior, data, view))
            data.template_operations = [updated if value.id == operation_id else value for value in data.template_operations]
            if view == before:
                return before
            sidecar_store(session.directory).write(project, before.project_revision, updated, data.facts)
            self.read_cache.pop(project, None)
            return self.read(project)

    def guard(self, project, operation):
        workspace = self.read(project)
        self.authority(operation, workspace)
        data = owner(workspace)
        if (data.template_package.package_hash != operation.capture.package_hash or
                {value.id: value.byte_sha256 for value in data.sources} != operation.capture.source_hashes):
            raise TemplateImportFailure('IMPORT_CAPTURE_STALE')
        self.facts_current(operation_in(workspace, operation.id), data.facts)

    def authorize(self, project, operation):
        self.guard(project, operation)

    async def recover(self, project, identifier):
        workspace = self.read(project)
        operation = operation_in(workspace, identifier)
        if workspace.project is not None and operation.finalization is not None:
            return await asyncio.to_thread(self.record_publication, project, identifier)
        def recover(value, _data, _workspace):
            updated = recover_operation(value)
            for attempt in updated.attempts:
                if attempt.state == 'outcome_unknown' or attempt.cleanup.state != 'verified':
                    proof = self.transport.reconcile(attempt)
                    if proof is not None:
                        updated = reconcile_cleanup(updated, proof, self.wall())
            return updated
        updated = await asyncio.to_thread(self.update, project, identifier, recover)
        return operation_in(updated, identifier)

    async def cancel(self, project, identifier):
        import threading
        self.cancels.setdefault((project, identifier), threading.Event()).set()
        await asyncio.to_thread(self.update, project, identifier,
            lambda operation, _data, _workspace: cancel_operation(operation))
        return True

    async def finalize(self, project, identifier):
        workspace = self.read(project)
        operation = operation_in(workspace, identifier)
        if workspace.project is not None and operation.finalization is not None:
            return await asyncio.to_thread(self.record_publication, project, identifier)
        self.guard(project, operation)
        if any(attempt.cleanup.state != 'verified' for attempt in operation.attempts):
            return operation
        authored = await asyncio.to_thread(self.assemble, workspace, operation)
        authored.document_revision = workspace.document_revision + 1
        authored.project.document.revision = authored.document_revision
        candidate = capture_finalization(operation, authored.project, self.wall(), id_factory=self.id_factory)

        def prepare(value, _data, current):
            if current.project_revision != workspace.project_revision:
                raise RepositoryFailure('REVISION_CONFLICT', revision=current.project_revision)
            if value.finalization is not None and value.finalization != candidate:
                value.finalization_history.append(value.finalization)
            value.finalization, value.state = candidate, 'finalizing'
            return value

        before = await asyncio.to_thread(self.update, project, identifier, prepare)
        authored.project.template_operations = owner(before).template_operations
        authored.project_revision = before.project_revision + 1
        authored.project.revision = authored.project_revision
        authored.updated_at = self.wall()

        def publish():
            mutation_id = 'template_publication_' + candidate.id
            self.repository.replace(project, base_revision=before.project_revision, workspace=authored,
                blobs=retained_blobs(project, authored, self.originals, self.artifacts, self.images), reason='publication',
                client_mutation_id=mutation_id, request_sha256=hashlib.sha256(mutation_id.encode()).hexdigest())
            return self.record_publication(project, identifier)

        return await asyncio.to_thread(publish)

    def record_publication(self, project, identifier):
        session = self.repository.open(project)
        with session.lock:
            workspace = self.read(project)
            operation = operation_in(workspace, identifier)
            if operation.publication.state == 'saved':
                return operation
            # A finalizing pre-draft becomes an authored project in the publication write itself.
            # After a crash, finish its outcome metadata; never assemble over later manual edits.
            if workspace.project is None or operation.finalization is None:
                raise RepositoryFailure('OUTCOME_UNKNOWN')
            outcome = PublicationOutcome(state='saved', intentId=operation.finalization.id,
                workspaceHash=hashlib.sha256(rich_snapshot_bytes(workspace)).hexdigest(), errorCode=None)
            def recorded(value, _data, _workspace):
                value.publication, value.state = outcome, 'published'
                return value
            return operation_in(self.update(project, identifier, recorded), identifier)
