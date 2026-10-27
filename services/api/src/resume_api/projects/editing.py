"""One request per edit: prepare the authored operation on the committed workspace and commit it (D109, plan 2.3)."""

from __future__ import annotations

from packages.resume_core.models.projects import EditResultV1, digest_request
from packages.resume_core.models.template_authoring import PasteBlocks, PasteInline
from packages.resume_core.rich_mutations import RichMutationFailure
from packages.resume_core.template_preparation import prepare_edit

from .clipboard import for_paste
from .errors import ProjectFailure
from .service import history_state


def _blocks(workspace):
    return [(block.id, block.revision) for block in workspace.project.document.blocks()] if workspace.project else []


def block_changes(before, after, op_id):
    """Blocks the edit created (per operation, in document order) and every block whose revision moved."""
    old = dict(_blocks(before))
    created, changed = [], []
    for identifier, revision in _blocks(after):
        if identifier not in old:
            created.append(identifier)
            changed.append(identifier)
        elif old[identifier] != revision:
            changed.append(identifier)
    return {op_id: created} if created else {}, changed


def edit(service, project_id, request):
    repository = service.repository
    session = repository.open(project_id)
    session.require_editor(request.editor_token)
    service.require_writable(project_id)
    preparation = request.preparation
    operation = preparation.operations[0]
    if preparation.snapshot.project_id != project_id:
        raise ProjectFailure('V7_INPUT_REJECTED', 422)

    def build(committed):
        response = service.response(project_id, committed)
        clipboard = None
        if isinstance(operation, (PasteInline, PasteBlocks)) and operation.source.kind == 'same_project':
            clipboard = for_paste(session, committed, operation.source.clipboard_capture_id)
        try:
            prepared = prepare_edit(response, preparation, clipboard=clipboard, occupied=session.occupied_ids)
        except (ValueError, RichMutationFailure):
            raise ProjectFailure('V7_INPUT_REJECTED', 422) from None
        if prepared.mutation is None:
            return None
        after = prepared.preview.workspace
        created, changed = block_changes(committed, after, operation.op_id)
        return after, {'created_ids': prepared.created_ids, 'created_blocks': created, 'changed_block_ids': changed}

    outcome = repository.mutate(project_id, base_revision=request.base_revision,
        client_mutation_id=preparation.client_mutation_id, request_sha256=digest_request(preparation),
        action_id=preparation.capture.action_id, kind='edit', build=build)
    return result(service, session, outcome, preparation.client_mutation_id)


def history(service, project_id, request):
    repository = service.repository
    session = repository.open(project_id)
    session.require_editor(request.editor_token)
    service.require_writable(project_id)
    outcome = repository.history(project_id, direction=request.direction, base_revision=request.base_revision,
        client_mutation_id=request.client_mutation_id, request_sha256=digest_request(request.model_dump(mode='json',
            by_alias=True, exclude={'editor_token'})), expected_action_id=request.expected_action_id)
    return result(service, session, outcome, request.client_mutation_id)


def result(service, session, outcome, client_mutation_id):
    with session.lock:
        workspace = session.workspace
        history = history_state(session)
    details = outcome.details
    return EditResultV1(schemaVersion=1, revision=workspace.project_revision, documentRevision=workspace.document_revision,
        clientMutationId=client_mutation_id, replayed=outcome.replayed, createdIds=details.get('created_ids') or {},
        createdBlocks=details.get('created_blocks') or {}, changedBlockIds=details.get('changed_block_ids') or [],
        history=history, response=service.response(session.project_id, workspace))
