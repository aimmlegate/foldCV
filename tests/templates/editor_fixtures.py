"""One project in an in-process repository and project service: authored edits, raw mutations, clipboard captures and
undo/redo go through the v2 edit path (`projects/editing`, `repository.mutate` and the journal) without HTTP."""

import hashlib

from packages.resume_core.models.projects import ClipboardCaptureRequestV1, EditRequestV1, HistoryRequestV1
from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.project_repository import ProjectRepository, blob_path
from packages.resume_core.rich_mutations import apply_rich_mutation, mutation_sha256
from packages.resume_core.templates.presentation import snapshot_identity
from resume_api.projects import clipboard, editing
from resume_api.projects.service import ProjectService


def source_blobs(sources):
    return [('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()]


def saved_sources(repository, project_id):
    """The source bytes of a stored project, read from its folder, by source id."""
    session = repository.open(project_id)
    owner = session.workspace.project or session.workspace.pre_draft
    return {source.id: blob_path(session.directory, 'sources', source.id).read_bytes() for source in owner.sources}


class TemplateEditor:
    def __init__(self, root, workspace=None, sources=None, *, clock=None):
        if workspace is None:
            from tests.templates.test_materialize import issue_workspace
            workspace, sources = issue_workspace()
        self.root = root / 'data'
        self.repository = ProjectRepository(self.root, **({'clock': clock} if clock else {}))
        self.repository.create(workspace, blobs=source_blobs(sources or {}))
        self.service = ProjectService(self.repository)
        self.project = workspace.project_id
        self.originals = dict(sources or {})
        self.token = self.service.open(self.project).editor_token

    def current(self):
        return self.repository.read(self.project)

    def session(self):
        return self.repository.open(self.project)

    def history_state(self):
        return self.session().journal.state()

    def reopen(self):
        """The same store read by a new repository, as after a service restart."""
        self.repository.close(self.project)
        self.repository = ProjectRepository(self.root)
        self.service = ProjectService(self.repository)
        self.token = self.service.open(self.project).editor_token
        return self.current()

    def edit(self, preparation, *, base=None):
        """Prepare and commit one authored operation on the committed workspace; returns `EditResultV1`."""
        if not isinstance(preparation, TemplateEditPreparationV1):
            preparation = TemplateEditPreparationV1.model_validate(preparation)
        request = EditRequestV1(editorToken=self.token, baseRevision=self.current().project_revision if base is None else base,
            preparation=preparation)
        return editing.edit(self.service, self.project, request)

    def commit(self, mutation, *, base=None, kind='edit'):
        """Commit a raw `TemplateMutationV1` the way a domain caller does; returns the repository outcome."""
        def build(committed):
            after, replayed = apply_rich_mutation(committed, mutation)
            return None if replayed else after
        return self.repository.mutate(self.project, base_revision=self.current().project_revision if base is None else base,
            client_mutation_id=mutation.client_mutation_id, request_sha256=mutation_sha256(mutation),
            action_id=mutation.action_id, kind=kind, build=build)

    def capture(self, selection, identifier='capture'):
        """A same-project clipboard capture of the current snapshot; returns `TemplateClipboardCaptureV1`."""
        request = ClipboardCaptureRequestV1(editorToken=self.token, clientCaptureId=identifier,
            snapshot=snapshot_identity(self.current()), selection=selection)
        return clipboard.capture(self.service, self.project, request)

    def retained(self, capture):
        identifier = capture if isinstance(capture, str) else capture.clipboard_capture_id
        return self.session().clipboard[identifier]

    def step(self, direction, identifier, *, expected=None, base=None):
        request = HistoryRequestV1(editorToken=self.token, baseRevision=self.current().project_revision if base is None else base,
            direction=direction, clientMutationId=identifier, expectedActionId=expected)
        return editing.history(self.service, self.project, request)

    def undo(self, identifier='undo', **options):
        return self.step('undo', identifier, **options)

    def redo(self, identifier='redo', **options):
        return self.step('redo', identifier, **options)
