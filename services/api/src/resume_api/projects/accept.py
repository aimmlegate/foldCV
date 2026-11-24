"""«Принять» in the tip of a green mark (D179): the value or the written block becomes the user's, one undo action."""

from __future__ import annotations

from pydantic import Field

from packages.resume_core.models.contracts import Id, Wire
from packages.resume_core.repository.accept import accept as accepted
from packages.resume_core.repository.assistant_store import digest, identity

from . import editing
from .errors import ProjectFailure


class AcceptRequest(Wire):
    editor_token: str = Field(min_length=1, max_length=256)
    client_mutation_id: Id
    # One of the two: the cell of a word mark, or a line of a block mark.
    cell_id: Id | None = None
    block_id: Id | None = None


def apply(service, project_id, payload):
    repository = service.repository
    session = repository.open(project_id)
    with session.lock:
        session.require_editor(payload.editor_token)
        service.require_writable(project_id)
        action_id = identity('accept')

        def build(committed):
            try:
                after = accepted(committed, cell_id=payload.cell_id, block_id=payload.block_id, action_id=action_id,
                    client_mutation_id=payload.client_mutation_id)
            except ValueError:
                raise ProjectFailure('V7_INPUT_REJECTED', 422) from None
            if after is None:
                return None, {}
            created_blocks, changed_blocks = editing.block_changes(committed, after, 'accept')
            return after, {'created_ids': {}, 'created_blocks': created_blocks, 'changed_block_ids': changed_blocks}
        outcome = repository.mutate(project_id, base_revision=session.revision, client_mutation_id=payload.client_mutation_id,
            request_sha256=digest({'accept': [payload.cell_id, payload.block_id]}), action_id=action_id, kind='edit', build=build)
        return editing.result(service, session, outcome, payload.client_mutation_id)
