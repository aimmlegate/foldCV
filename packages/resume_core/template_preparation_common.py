"""Shared exact-base guards and atomic preparation completion."""

from .models.template_authoring import TemplatePreparedEditV1
from .models.template_mutations import TemplateMutationV1
from .rich_dependencies import dependencies_current
from .rich_identity import resume_identity
from .rich_mutations import apply_rich_mutation
from .template_api import TemplateProjectResponseV1
from .template_issue_impacts import issue_impacts
from .template_mutations import apply_fact_steps
from .templates.compiler import canonical, sha256
from .templates.presentation import project_presentation, snapshot_identity


def preparation_hash(request):
    return sha256(canonical(request))


def validate_preparation(response, request, proof):
    workspace = response.workspace
    if (response.durability != 'durable' or workspace.project is None or response.snapshot != request.snapshot
            or snapshot_identity(workspace) != request.snapshot
            or request.capture.session_id != proof.session_id or not dependencies_current(workspace, request.capture.dependencies)):
        raise ValueError('preparation requires its exact durable base and capture')
    if any(value.client_mutation_id == request.client_mutation_id for value in workspace.mutation_replay):
        raise ValueError('preparation request ID is already committed')


def prepared_response(response, request, allocator, mutation, preview):
    return TemplatePreparedEditV1(schemaVersion=1, clientMutationId=request.client_mutation_id,
        baseSnapshot=request.snapshot.model_copy(deep=True), capture=request.capture.model_copy(deep=True),
        requestHash=preparation_hash(request), createdIds=allocator.created_ids, mutation=mutation, preview=preview)


def finish_preparation(response, request, allocator, steps, candidate, *, kind='structure'):
    workspace = response.workspace
    def mutation(values):
        return TemplateMutationV1(schemaVersion=1, projectId=workspace.project_id, clientMutationId=request.client_mutation_id,
            actionId=request.capture.action_id, kind=kind,
            capture=request.capture.model_copy(deep=True), steps=values, history={'kind': 'edit', 'originActionId': None})
    initial = mutation(steps)
    candidate.facts = apply_fact_steps(workspace.project.facts, initial)
    from .template_scope_displays import apply_scope_displays
    apply_scope_displays(candidate, initial)
    from .template_preparation_scopes import detach_unowned_displays
    detached = detach_unowned_displays(workspace.project, candidate)
    if detached is not None:
        apply_scope_displays(candidate, mutation([detached]))
        steps.append(detached)
        initial = mutation(steps)
    from .template_anchors import apply_anchor_steps
    apply_anchor_steps(candidate, initial, workspace.project)
    affected, known = issue_impacts(workspace.project, candidate, initial)
    for issue in workspace.project.import_issues:
        targets = set(issue.target_ids) if issue.target_ids else set(issue.block_ids)
        if not targets & known:
            targets.update(issue.block_ids)
        if issue.state == 'active' and targets & affected:
            steps.append({'kind': 'set_issue_state', 'issueId': issue.id, 'beforeLifecycleId': issue.lifecycle_id,
                'beforeState': issue.state, 'afterLifecycleId': allocator.allocate('lifecycle', ['issue-lifecycle', issue.id, 'retired']),
                'afterState': 'retired', 'actionId': request.capture.action_id, 'importedFingerprint': issue.imported_fingerprint})
    command = mutation(steps)
    result, replayed = apply_rich_mutation(workspace, command)
    if replayed:
        raise ValueError('preparation request ID is already committed')
    sync_ids = {step.record.id for step in command.steps if step.kind == 'put_template_sync'}
    for record in result.sync_records:
        if record.id in sync_ids:
            allocator.derived('sync-lifecycle', ['sync-lifecycle', record.id], record.lifecycle_id)
    preview = TemplateProjectResponseV1(schemaVersion=1, workspace=result, snapshot=snapshot_identity(result),
        presentation=project_presentation(result), durability='pending', savedProjectRevision=response.saved_project_revision,
        savedDocumentRevision=response.saved_document_revision, saveError=None, generation=response.generation,
        identity=resume_identity(result))
    return prepared_response(response, request, allocator, command, preview)
