"""A block reworded on the user's request (a trial): the blocks that can be, a preview, and the user's Apply.

The preview is one model call on the rewrite model and writes nothing. Apply takes the values the user kept and
commits them as fact updates, one undo action: a fact changes here only by the user's request."""

from __future__ import annotations

import asyncio

from pydantic import Field

from packages.resume_core.repository.block_reword import (RewordChange, RewordValue, reword_ops, reword_request,
    reword_schema, reword_source, reword_values, rewordable)
from packages.resume_core.importing.lite import prompts
from packages.resume_core.models.contracts import Id, Wire
from packages.resume_core.project_limits import REWRITE_INSTRUCTION_CHARS
from packages.resume_core.repository.assistant_compiler import CompileFailure, changed_targets, compile_ops, touched
from packages.resume_core.repository.assistant_store import digest, identity

from ..importer.lite_import import root_model
from ..providers.dynamic_result import dynamic_result
from . import editing
from .errors import ProjectFailure
from .service import response_for_workspace


class RewordPreviewRequest(Wire):
    editor_token: str = Field(min_length=1, max_length=128)
    request_id: Id
    block_id: Id
    # How to reword, as the user saw it in the panel: their own words or the rules a button put there.
    instruction: str = Field(min_length=1, max_length=REWRITE_INSTRUCTION_CHARS)


class RewordPreview(Wire):
    request_id: Id
    block_id: Id
    values: list[RewordValue]
    # The hash of every record a value belongs to, as the preview read it: Apply refuses one that changed since.
    touched: dict[str, str]


class RewordApplyRequest(Wire):
    editor_token: str = Field(min_length=1, max_length=256)
    client_mutation_id: Id
    block_id: Id
    changes: list[RewordChange] = Field(min_length=1, max_length=200)
    touched: dict[str, str]


def blocks(service, project_id):
    session = service.repository.open(project_id)
    with session.lock:
        found = rewordable(session.workspace)
        return {'blockIds': list(found), 'rules': found}


def _read(service, project_id, payload):
    session = service.repository.open(project_id)
    with session.lock:
        session.require_editor(payload.editor_token)
        workspace = session.workspace
        source = reword_source(workspace, payload.block_id)
        if source is None or not payload.instruction.strip():
            raise ProjectFailure('V7_INPUT_REJECTED', 422)
        ops = [{'op': 'update_fact', 'recordId': target.record_id, 'field': target.field, 'value': target.text}
               for target in source.targets]
        from packages.resume_core.models.assistant import UpdateFactOp
        return source, touched(workspace, [UpdateFactOp.model_validate(op) for op in ops])


async def preview(service, project_id, payload):
    source, hashes = await asyncio.to_thread(_read, service, project_id, payload)
    schema = reword_schema(source.targets)

    def make(provider):
        # The Claude CLI gets the schema at the root, every other provider the product's envelope (as a lite import).
        envelope = getattr(provider, 'template_adapter', 'codex_cli') != 'claude_cli'
        token = prompts.ENVELOPE.set(envelope)
        try:
            return (reword_request(source, payload.instruction),
                dynamic_result(schema) if envelope else root_model(schema))
        finally:
            prompts.ENVELOPE.reset(token)
    task = service.tasks.start(project_id, 'rewrite', stage='queued', detail={'requestId': payload.request_id})
    try:
        value = await service.rewrite_reply(project_id, payload.request_id, make,
            lambda: service.tasks.update(task.id, stage='generating'))
    except BaseException as error:
        code = getattr(error, 'code', 'PROCESS_FAILED')
        service.tasks.finish(task.id, 'cancelled' if code == 'CANCELLED' else 'failed', error=code)
        raise
    service.tasks.finish(task.id, 'succeeded')
    reply = value.payload if hasattr(value, 'payload') else value.model_dump(mode='json')
    return RewordPreview(requestId=payload.request_id, blockId=payload.block_id, values=reword_values(source, reply),
        touched=hashes)


def apply(service, project_id, payload):
    repository = service.repository
    session = repository.open(project_id)
    with session.lock:
        session.require_editor(payload.editor_token)
        service.require_writable(project_id)
        action_id = identity('reword')

        def build(committed):
            changed = changed_targets(payload.touched, committed)
            if changed:
                raise ProjectFailure('ASSISTANT_PROPOSAL_STALE', 409, targets=changed)
            try:
                ops = reword_ops(committed, payload.block_id, payload.changes)
                # The stale check above reads only the hashes the request sent: every record a change names must be
                # among them, or a request with none would write over a value changed since its preview.
                if set(touched(committed, ops)) - set(payload.touched):
                    raise ValueError('a change of a record the preview did not read')
                after, created = compile_ops(committed, ops, action_id=action_id, occupied=session.occupied_ids,
                    response_for=response_for_workspace)
            except ValueError:
                raise ProjectFailure('V7_INPUT_REJECTED', 422) from None
            except CompileFailure as error:
                raise ProjectFailure(error.code, 409, detail=error.detail) from None
            if after is committed:
                raise ProjectFailure('ASSISTANT_PROPOSAL_EMPTY', 409)
            created_blocks, changed_blocks = editing.block_changes(committed, after, 'reword')
            return after, {'created_ids': created, 'created_blocks': created_blocks, 'changed_block_ids': changed_blocks}
        outcome = repository.mutate(project_id, base_revision=session.revision, client_mutation_id=payload.client_mutation_id,
            request_sha256=digest({'reword': payload.block_id, 'changes': [change.model_dump(mode='json') for change in payload.changes]}),
            action_id=action_id, kind='edit', build=build)
        return editing.result(service, session, outcome, payload.client_mutation_id)
