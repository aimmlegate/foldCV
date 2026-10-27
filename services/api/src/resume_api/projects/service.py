"""Projects as a whole: listing, open with an editor token, reads, rename, archive flags and deletion (D109)."""

from __future__ import annotations

import threading

from packages.resume_core.models.projects import HistoryStateV1, ProjectOpenResultV1, TaskStatusV1
from packages.resume_core.project_catalog import ProjectCatalog
from packages.resume_core.project_repository import RepositoryFailure, decode_project
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.project_tasks import TaskRegistry
from packages.resume_core.rich_identity import display_identity
from packages.resume_core.template_api import TemplateProjectResponseV1, verify_response, verifying
from packages.resume_core.templates.presentation import project_presentation, snapshot_identity

from .errors import ProjectFailure


def response_for_workspace(workspace, *, generation=None):
    """The editor's view of a committed workspace: snapshot, presentation and identity; memory follows the file, so the
    response is durable."""
    return TemplateProjectResponseV1(schemaVersion=1, workspace=workspace, snapshot=snapshot_identity(workspace),
        presentation=project_presentation(workspace), durability='durable', savedProjectRevision=workspace.project_revision,
        savedDocumentRevision=workspace.document_revision, saveError=None, generation=generation,
        identity=display_identity(workspace))


def history_state(session):
    return HistoryStateV1.model_validate(session.journal.state())


class ProjectService:
    def __init__(self, repository, *, tasks=None, catalog=None):
        self.repository = repository
        self.tasks = tasks or TaskRegistry()
        self.catalog = catalog or ProjectCatalog(repository.store)
        self.lock = threading.Lock()
        # Built once per committed workspace object; a hit is verified again under FOLDCV_VERIFY (D108).
        self.responses = {}
        self.identities = {}
        # Any commit (import, assistant Apply, export record) may change the heading the listing shows.
        repository.committed_hooks.append(self._forget_identity)

    def _forget_identity(self, session):
        with self.lock:
            self.identities.pop(session.project_id, None)

    def response(self, project_id, workspace=None):
        workspace = workspace if workspace is not None else self.repository.read(project_id)
        with self.lock:
            cached = self.responses.get(project_id)
        if cached is not None and cached[0] is workspace:
            if verifying():
                verify_response(cached[1])
            return cached[1]
        response = response_for_workspace(workspace)
        with self.lock:
            self.responses[project_id] = (workspace, response)
            self.identities[project_id] = (response.identity.title, response.identity.subtitle)
        return response

    def require_writable(self, project_id):
        if self.catalog.get(project_id).read_only:
            raise RepositoryFailure('PROJECT_READ_ONLY')

    def listing(self):
        """Registry entries with catalog flags and the resume identity; unopened projects are read once for it."""
        entries, errors = [], []
        catalog = self.catalog.entries()
        for entry in self.repository.listing():
            value = entry.model_dump(mode='json', by_alias=True)
            meta = catalog.get(entry.project_id)
            value.update(lastOpenedAt=meta.last_opened_at if meta else None, archived=meta.archived if meta else False)
            identity = self.identities.get(entry.project_id)
            if identity is None:
                try:
                    identity = self._identity(entry.project_id)
                except RepositoryFailure as error:
                    errors.append({'projectId': entry.project_id, 'errorCode': error.code})
            if identity is not None:
                value.update(title=identity[0], subtitle=identity[1])
            entries.append(value)
        entries.sort(key=lambda entry: (entry['lastOpenedAt'] or entry['updatedAt'], entry['projectId']), reverse=True)
        return {'entries': entries, 'errors': errors}

    def _identity(self, project_id):
        session = self.repository.sessions.get(project_id)
        if session is not None:
            workspace = session.workspace
        else:
            directory = self.repository._directory(project_id)
            try:
                workspace = decode_project(directory, (directory / 'workspace.json').read_bytes())
            except ProjectStoreFailure as error:
                raise RepositoryFailure(error.code) from None
            except (OSError, ValueError):
                raise RepositoryFailure('PROJECT_LOAD_FAILED') from None
        identity = display_identity(workspace)
        value = (identity.title, identity.subtitle)
        with self.lock:
            self.identities[project_id] = value
        return value

    def open(self, project_id):
        """A fresh editor token (the previous page's token is replaced), the response, history and running tasks."""
        session = self.repository.open(project_id)
        token = session.open_editor()
        try:
            self.catalog.update(project_id, opened=True)
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        with session.lock:
            workspace = session.workspace
            history = history_state(session)
        return ProjectOpenResultV1(schemaVersion=1, editorToken=token, response=self.response(project_id, workspace),
            history=history, tasks=[TaskStatusV1.model_validate(value) for value in self.tasks.list(project_id)])

    def read(self, project_id):
        return self.response(project_id)

    def rename(self, project_id, request):
        session = self.repository.open(project_id)
        self.require_writable(project_id)
        with session.lock:
            if request.editor_token is not None:
                session.require_editor(request.editor_token)
            renamed = session.workspace.model_copy()
            renamed.title, renamed.title_manually_set = request.title.strip(), True
            self.repository.replace(project_id, base_revision=request.base_revision, workspace=renamed, reason='rename')
            self.repository.write_registry(project_id)
            workspace = session.workspace
        with self.lock:
            self.identities.pop(project_id, None)
        return self.response(project_id, workspace)

    def set_formatting_date(self, project_id, value, *, base_revision=None):
        """The formatting date is not an undoable key, so the commit writes no journal line."""
        from packages.resume_core.models.contracts import PartialDate
        date = value if isinstance(value, PartialDate) else PartialDate.model_validate(value)
        session = self.repository.open(project_id)
        self.require_writable(project_id)
        with session.lock:
            updated = session.workspace.model_copy()
            updated.formatting_as_of = date
            base = session.revision if base_revision is None else base_revision
            self.repository.replace(project_id, base_revision=base, workspace=updated, reason='formatting-date')
            workspace = session.workspace
        return self.response(project_id, workspace)

    def archive(self, project_id, archived):
        self.repository._directory(project_id)
        try:
            self.catalog.update(project_id, archived=archived)
        except ProjectStoreFailure as error:
            raise RepositoryFailure(error.code) from None
        return self.listing()

    def delete(self, project_id, request):
        if request.confirmed is not True:
            raise ProjectFailure('INVALID_REQUEST', 422)
        for task in self.tasks.running(project_id):
            self.tasks.cancel(task.id)
        if self.tasks.running(project_id):
            raise RepositoryFailure('REQUEST_IN_PROGRESS')
        entry = self.repository.delete(project_id)
        self.tasks.forget(project_id)
        deleted = getattr(self, 'on_deleted', None)
        if deleted is not None:
            deleted(project_id)
        with self.lock:
            self.responses.pop(project_id, None)
            self.identities.pop(project_id, None)
        return {'schemaVersion': 1, 'projectId': project_id, 'deleted': True,
            'cleanupStatus': entry.cleanup_status if entry is not None else 'complete'}
