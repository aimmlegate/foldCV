"""Proposals: built from the run's pinned read, applied only by the user through the repository (D093, plan 2.8).

`propose` compiles the ops against the pinned workspace to check them and to show a preview; it never writes the
project. `apply` runs inside one `repository.mutate`: under the project lock it compares the hash of every touched
block and record with the current workspace, refuses a changed one as stale, and otherwise compiles the ops against
the current workspace and commits them with the proposal id as the action id, so Undo reverts the whole proposal.
"""

from __future__ import annotations

from packages.resume_core.assistant_compiler import CompileFailure, changed_targets, compile_ops, preview, touched
from packages.resume_core.assistant_store import AgentFailure, digest, identity, timestamp
from packages.resume_core.models.assistant import (AssistantActionResultV1, AssistantApplyResultV1,
    AssistantChangeProposalV1)
from packages.resume_core.models.contracts import PartialDate
from packages.resume_core.models.projects import DeleteRequestV1, RenameRequestV1
from packages.resume_core.project_repository import RepositoryFailure

from resume_api.projects import editing
from resume_api.projects.errors import ProjectFailure
from resume_api.projects.service import response_for_workspace


def refused(error):
    return ProjectFailure(error.code, 409, detail=error.detail)


def formatting_date(value):
    parts = (value or '').split('-')
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        raise CompileFailure('ASSISTANT_OP_INVALID', 'formatting_date') from None
    precision = {1: 'year', 2: 'month', 3: 'day'}.get(len(numbers))
    if precision is None:
        raise CompileFailure('ASSISTANT_OP_INVALID', 'formatting_date')
    try:
        return PartialDate(precision=precision, year=numbers[0], month=numbers[1] if len(numbers) > 1 else None,
            day=numbers[2] if len(numbers) > 2 else None)
    except ValueError:
        raise CompileFailure('ASSISTANT_OP_INVALID', 'formatting_date') from None


def action_preview(workspace, op):
    if op.action == 'rename':
        if not (op.value or '').strip():
            raise CompileFailure('ASSISTANT_OP_INVALID', 'rename')
        return [{'target': workspace.project_id, 'label': 'rename', 'before': workspace.title, 'after': op.value.strip()}]
    if op.action == 'formatting_date':
        date = formatting_date(op.value)
        return [{'target': workspace.project_id, 'label': 'formatting_date', 'before': workspace.formatting_as_of.model_dump_json(
            by_alias=True), 'after': date.model_dump_json(by_alias=True)}]
    if op.action == 'delete' and op.target_id != workspace.project_id:
        raise CompileFailure('ASSISTANT_OP_INVALID', 'delete needs targetId equal to the project id')
    return [{'target': workspace.project_id, 'label': op.action, 'before': workspace.title, 'after': workspace.title}]


def propose(service, run, pinned, request):
    """A draft proposal from the pinned read; edits off still allows a draft (G8). The tool stores it once the run's
    reply limits admit its reply. Blocking: it may wait for the project lock."""
    project_id, first = run.project_id, request.ops[0]
    proposal_id = identity('proposal')
    expected = None
    if first.op == 'history':
        session = service.projects.repository.open(project_id)
        with session.lock:
            top = session.journal.top(first.direction)
        if top is None:
            raise CompileFailure('ASSISTANT_HISTORY_EMPTY', first.direction)
        kind, hashes, expected = 'history', {}, top.action_id
        shown = [{'target': top.action_id, 'label': first.direction, 'before': '', 'after': ''}]
    elif first.op == 'action':
        kind, hashes, shown = 'action', {}, action_preview(pinned, first)
    else:
        kind, hashes = 'edit', touched(pinned, request.ops)
        session = service.projects.repository.open(project_id)
        with session.lock:
            occupied = set(session.occupied_ids)
        after, _created = compile_ops(pinned, request.ops, action_id=proposal_id, occupied=occupied,
            response_for=response_for_workspace)
        if after is pinned:
            raise CompileFailure('ASSISTANT_PROPOSAL_EMPTY')
        shown = preview(pinned, after, request.ops)
    now = timestamp()
    return AssistantChangeProposalV1(schemaVersion=1, id=proposal_id, projectId=project_id,
        conversationId=run.conversation_id, runId=run.id, kind=kind, summary=request.summary,
        baseRevision=pinned.project_revision, touched=hashes, expectedActionId=expected, ops=request.ops,
        preview=shown, state='draft', appliedRevision=None, createdAt=now, updatedAt=now)


def apply(service, project_id, proposal_id, request):
    projects, store = service.projects, service.store
    repository = projects.repository
    session = repository.open(project_id)
    with session.lock:
        # The state is read and settled under the project lock: a second Apply or a Discard waits for this one.
        proposal = store.proposal(project_id, proposal_id)
        request_sha256 = digest({'proposal': proposal.id, 'kind': proposal.kind})
        session.require_editor(request.editor_token)
        if request.client_mutation_id in session.replays:
            # A retried Apply: the repository returns its stored outcome and applies nothing. A crash after the commit
            # and before the proposal file left the proposal a draft; the replay marks it applied.
            outcome = repository.mutate(project_id, base_revision=session.revision,
                client_mutation_id=request.client_mutation_id, request_sha256=request_sha256, action_id=proposal.id,
                kind='edit', build=lambda _workspace: None)
            if proposal.state != 'applied':
                proposal = proposal.model_copy(update={'state': 'applied', 'applied_revision': outcome.revision,
                    'updated_at': timestamp()})
                store.save_proposal(proposal)
            return AssistantApplyResultV1(proposal=proposal, edit=editing.result(projects, session, outcome,
                request.client_mutation_id), action=None)
        if proposal.state != 'draft':
            raise ProjectFailure('ASSISTANT_PROPOSAL_CLOSED', 409)
        if not request.allow_edits:
            raise ProjectFailure('ASSISTANT_EDITS_OFF', 409)
        projects.require_writable(project_id)
        edit = action = None
        if proposal.kind == 'edit':
            def build(committed):
                changed = changed_targets(proposal.touched, committed)
                if changed:
                    raise ProjectFailure('ASSISTANT_PROPOSAL_STALE', 409, targets=changed)
                try:
                    after, created = compile_ops(committed, proposal.ops, action_id=proposal.id,
                        occupied=session.occupied_ids, response_for=response_for_workspace)
                except CompileFailure as error:
                    raise refused(error) from None
                if after is committed:
                    raise ProjectFailure('ASSISTANT_PROPOSAL_EMPTY', 409)
                blocks, changed_blocks = editing.block_changes(committed, after, 'assistant')
                return after, {'created_ids': created, 'created_blocks': blocks, 'changed_block_ids': changed_blocks}
            outcome = repository.mutate(project_id, base_revision=session.revision,
                client_mutation_id=request.client_mutation_id, request_sha256=request_sha256, action_id=proposal.id,
                kind='edit', build=build)
            edit = editing.result(projects, session, outcome, request.client_mutation_id)
        elif proposal.kind == 'history':
            direction = proposal.ops[0].direction
            try:
                outcome = repository.history(project_id, direction=direction, base_revision=session.revision,
                    client_mutation_id=request.client_mutation_id, request_sha256=request_sha256,
                    expected_action_id=proposal.expected_action_id)
            except RepositoryFailure as error:
                if error.code == 'HISTORY_STALE':
                    raise ProjectFailure('ASSISTANT_PROPOSAL_STALE', 409, targets=[proposal.expected_action_id]) from None
                raise
            edit = editing.result(projects, session, outcome, request.client_mutation_id)
        elif proposal.ops[0].action != 'delete':
            action = run_action(service, project_id, proposal.ops[0], request)
        if proposal.kind != 'action' or action is not None:
            proposal = proposal.model_copy(update={'state': 'applied', 'applied_revision': session.revision,
                'updated_at': timestamp()})
            store.save_proposal(proposal)
    if proposal.kind == 'action' and action is None:
        # A deletion waits for the project's running work to stop, and that work needs the project lock to finish.
        action = run_action(service, project_id, proposal.ops[0], request)
    return AssistantApplyResultV1(proposal=proposal, edit=edit, action=action)


def run_action(service, project_id, op, request):
    """The same service calls the project buttons use; one action per proposal."""
    projects = service.projects
    try:
        if op.action == 'rename':
            response = projects.rename(project_id, RenameRequestV1(editorToken=request.editor_token,
                baseRevision=projects.repository.read(project_id).project_revision, title=(op.value or '').strip()))
            return AssistantActionResultV1(action='rename', title=response.workspace.title, archived=None, deleted=False)
        if op.action == 'formatting_date':
            projects.set_formatting_date(project_id, formatting_date(op.value))
            return AssistantActionResultV1(action='formatting_date', title=None, archived=None, deleted=False)
        if op.action in {'archive', 'restore'}:
            projects.archive(project_id, op.action == 'archive')
            return AssistantActionResultV1(action=op.action, title=None, archived=op.action == 'archive', deleted=False)
    except CompileFailure as error:
        raise refused(error) from None
    if op.target_id != project_id:
        raise ProjectFailure('ASSISTANT_OP_INVALID', 409)
    service.stop_project(project_id)
    projects.delete(project_id, DeleteRequestV1(confirmed=True))
    store_cleanup(service, project_id)
    return AssistantActionResultV1(action='delete', title=None, archived=None, deleted=True)


def store_cleanup(service, project_id):
    try:
        service.store.delete_project(project_id)
    except AgentFailure:
        pass


def discard(service, project_id, proposal_id):
    session = service.projects.repository.open(project_id)
    with session.lock:
        proposal = service.store.proposal(project_id, proposal_id)
        if proposal.state == 'applied':
            raise ProjectFailure('ASSISTANT_PROPOSAL_CLOSED', 409)
        if proposal.state == 'draft':
            proposal = proposal.model_copy(update={'state': 'discarded', 'updated_at': timestamp()})
            service.store.save_proposal(proposal)
    return proposal
