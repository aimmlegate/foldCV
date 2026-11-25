"""A block reworded on the user's request (a trial): the blocks that can be, a preview, and the user's Apply.

Two actions share the panel: «Изменить формулировку» rewords each value from its own source lines, and «Написать
заново по резюме» (F6a) writes a text block again from the CV's lines. A preview writes nothing: one model call, and
for a written text that code refused one more call with the reason, both under the one request ID. Apply takes the values the user kept and
commits them as fact updates, one undo action: a fact changes here only by the user's request."""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from packages.resume_core.repository.block_reword import (RewordChange, RewordSource, RewordValue, Target, model_written, reword_ops,
    reword_request, reword_schema, reword_source, reword_values, rewordable)
from packages.resume_core.importing.lite import prompts
from packages.resume_core.repository import block_write
from packages.resume_core.models.contracts import Id, Wire
from packages.resume_core.project_limits import REWRITE_INSTRUCTION_CHARS
from packages.resume_core.models.assistant import UpdateFactOp
from packages.resume_core.repository.assistant_compiler import CompileFailure, _hash, changed_targets, compile_ops, touched
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
    # reword: «Изменить формулировку»; write: «Написать заново по резюме».
    mode: Literal['reword', 'write'] = 'reword'


class RewordPreview(Wire):
    request_id: Id
    block_id: Id
    values: list[RewordValue]
    mode: Literal['reword', 'write'] = 'reword'
    # F6b: a list written again has the present items in `values` and the model's items in `added`.
    shape: Literal['text', 'items'] = 'text'
    added: list[block_write.WrittenItem] = Field(default_factory=list)
    # The hash of every record a value belongs to, as the preview read it: Apply refuses one that changed since.
    touched: dict[str, str]


class RewordApplyRequest(Wire):
    editor_token: str = Field(min_length=1, max_length=256)
    client_mutation_id: Id
    block_id: Id
    changes: list[RewordChange] = Field(default_factory=list, max_length=200)
    touched: dict[str, str]
    # F6b: the present items of a list that go, and the new items that come (in the reply's order).
    removed: list[Id] = Field(default_factory=list, max_length=50)
    added: list[block_write.AddedItem] = Field(default_factory=list, max_length=block_write.LIST_MOST)


def blocks(service, project_id):
    session = service.repository.open(project_id)
    with session.lock:
        found = rewordable(session.workspace)
        hidden = block_write.project_hidden(session.directory, session.workspace) if found else None
        return {'blockIds': list(found), 'rules': found, 'write': block_write.writable(session.workspace, hidden)}


def _read(service, project_id, payload):
    session = service.repository.open(project_id)
    with session.lock:
        session.require_editor(payload.editor_token)
        workspace = session.workspace
        source: block_write.WriteSource | block_write.ListSource | RewordSource | None
        targets: list[Target]
        if payload.mode == 'write':
            hidden = block_write.project_hidden(session.directory, workspace)
            source = block_write.write_source(workspace, payload.block_id, hidden)
            if source is None:
                listed = block_write.list_source(workspace, payload.block_id, hidden)
                if listed is None or not payload.instruction.strip():
                    raise ProjectFailure('V7_INPUT_REJECTED', 422)
                # The list block's hash sees a change of its structure too: a bullet typed, moved or removed.
                section = next(block for block in workspace.project.document.blocks() if block.id == payload.block_id)
                ops = [UpdateFactOp.model_validate({'op': 'update_fact', 'recordId': item.record_id, 'field': item.field,
                       'value': item.text}) for item in listed.items]
                return listed, {**touched(workspace, ops), payload.block_id: _hash(section)}
            targets = [source.target]
        else:
            source = reword_source(workspace, payload.block_id)
            targets = list(source.targets) if source is not None else []
        if source is None or not payload.instruction.strip():
            raise ProjectFailure('V7_INPUT_REJECTED', 422)
        ops = [{'op': 'update_fact', 'recordId': target.record_id, 'field': target.field, 'value': target.text}
               for target in targets]
        return source, touched(workspace, [UpdateFactOp.model_validate(op) for op in ops])


def _maker(prompt_of, schema):
    def make(provider):
        # The Claude CLI gets the schema at the root, every other provider the product's envelope (as a lite import).
        envelope = getattr(provider, 'template_adapter', 'codex_cli') != 'claude_cli'
        token = prompts.ENVELOPE.set(envelope)
        try:
            return prompt_of(), dynamic_result(schema) if envelope else root_model(schema)
        finally:
            prompts.ENVELOPE.reset(token)
    return make


def _payload(value):
    return value.payload if hasattr(value, 'payload') else value.model_dump(mode='json')


async def preview(service, project_id, payload):
    source, hashes = await asyncio.to_thread(_read, service, project_id, payload)
    started = lambda: service.tasks.update(task.id, stage='generating')
    task = service.tasks.start(project_id, 'rewrite', stage='queued', detail={'requestId': payload.request_id})
    try:
        if isinstance(source, block_write.WriteSource):
            schema = prompts.rewrite_schema()
            reply = _payload(await service.rewrite_reply(project_id, payload.request_id,
                _maker(lambda: block_write.write_request(source, payload.instruction), schema), started))
            value, told = block_write.write_value(source, reply)
            if told:
                # One more call, told what code refused; the same request ID, so one Cancel stops either call.
                reply = _payload(await service.rewrite_reply(project_id, payload.request_id,
                    _maker(lambda: block_write.write_request(source, payload.instruction, told), schema), started))
                value, _told = block_write.write_value(source, reply)
            values, added, shape = [value], [], 'text'
        elif isinstance(source, block_write.ListSource):
            listed = source
            # One call for a list: a refused item is left out alone, as the import does.
            reply = _payload(await service.rewrite_reply(project_id, payload.request_id,
                _maker(lambda: block_write.list_request(listed, payload.instruction), block_write.list_schema(listed)),
                started))
            values, added = block_write.list_values(listed, reply)
            shape = 'items'
        else:
            reword = source
            reply = _payload(await service.rewrite_reply(project_id, payload.request_id,
                _maker(lambda: reword_request(reword, payload.instruction), reword_schema(reword.targets)), started))
            values, added, shape = reword_values(reword, reply), [], 'text'
    except BaseException as error:
        code = getattr(error, 'code', 'PROCESS_FAILED')
        service.tasks.finish(task.id, 'cancelled' if code == 'CANCELLED' else 'failed', error=code)
        raise
    service.tasks.finish(task.id, 'succeeded')
    return RewordPreview(requestId=payload.request_id, blockId=payload.block_id, values=values, touched=hashes,
        mode=payload.mode, shape=shape, added=added)


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
            if payload.removed or payload.added:
                return _list_apply(session, committed, payload, action_id)
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
            after = model_written(after.model_copy(deep=True), payload.changes, action_id)
            created_blocks, changed_blocks = editing.block_changes(committed, after, 'reword')
            return after, {'created_ids': created, 'created_blocks': created_blocks, 'changed_block_ids': changed_blocks}
        outcome = repository.mutate(project_id, base_revision=session.revision, client_mutation_id=payload.client_mutation_id,
            request_sha256=digest({'reword': payload.block_id, 'changes': [change.model_dump(mode='json') for change in payload.changes],
                'removed': payload.removed, 'added': [item.model_dump(mode='json') for item in payload.added]}),
            action_id=action_id, kind='edit', build=build)
        return editing.result(service, session, outcome, payload.client_mutation_id)


def _list_apply(session, committed, payload, action_id):
    """The user's Apply of a list written again (F6b): new items come, removed items go, one action. The preview's
    hashes must name the list block and each removed record, so a list changed since is refused as stale."""
    if payload.changes or payload.block_id not in payload.touched or not set(payload.removed) <= set(payload.touched):
        raise ProjectFailure('V7_INPUT_REJECTED', 422)
    try:
        after, created = block_write.list_workspace(committed, payload.block_id, payload.removed, payload.added,
            block_write.project_hidden(session.directory, committed), action_id=action_id,
            occupied=session.occupied_ids, response_for=response_for_workspace)
    except ValueError:
        raise ProjectFailure('V7_INPUT_REJECTED', 422) from None
    except CompileFailure as error:
        raise ProjectFailure(error.code, 409, detail=error.detail) from None
    created_blocks, changed_blocks = editing.block_changes(committed, after, 'reword')
    return after, {'created_ids': created, 'created_blocks': created_blocks, 'changed_block_ids': changed_blocks}
