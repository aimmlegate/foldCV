"""Publish the initial template tree while retaining original sources and fact history."""

from .models.template_workspace import ProjectV6, WorkspaceV7, validated_with_history
from .templates.focus import catalog_for, remembered_icon, row_name
from .templates.materialize import materialize
from .templates.presentation_plan import focus_row
from .templates.span_coverage import overlaps
from .template_capture import item_identities
from .template_proposals import relation_evidence


def remembered_rows(document, package, facts, remembered):
    """Focus rows take the icons the user chose before for their names, when the template has them (D122)."""
    if remembered is None or package.recipe.style.focus.icon_catalog is None:
        return
    catalog = catalog_for(package)
    for block in document.blocks():
        row = focus_row(block, package.recipe)
        icon = remembered_icon(catalog, remembered, row_name(package, facts, row)) if row else None
        if icon is not None:
            block.props.icon = icon


def assemble_template(workspace, operation, remembered=None):
    """`remembered`: the Focus icons the user chose before (`remembered_catalog`)."""
    if workspace.schema_version != 7 or workspace.project is not None or workspace.pre_draft is None:
        raise ValueError('template assembly requires a new captured pre-draft')
    result = workspace.model_copy(deep=True)
    data = result.pre_draft
    document, coverage = materialize(data.template_package, data.facts, data.template_operations, data.sources,
        operation_id=operation.id, revision=result.document_revision + 1, as_of=result.formatting_as_of)
    remembered_rows(document, data.template_package, data.facts, remembered)
    issues = [issue.model_copy(deep=True) for issue in operation.issues]
    identities = {identity.item_handle: identity for retained in data.template_operations for identity in item_identities(retained)}
    target_spans = {}
    for retained in data.template_operations:
        for proposal in retained.proposals:
            for field in proposal.resolved_fields:
                identifier = identities[field.item_handle].cell_ids[field.field_key]
                target_spans.setdefault(identifier, []).extend(field.evidence)
            for identifier, spans in relation_evidence(retained, proposal).items():
                target_spans.setdefault(identifier, []).extend(spans)
    # A whole-scope issue points at the fallback lines its own task shows, else at its block's view; before, it
    # named every block, so its notice showed the first block of the page and any edit anywhere retired it.
    fallback_spans, views = {}, {}
    for retained in data.template_operations:
        views.update({task.id: task.block_id for task in retained.tasks})
        for value in retained.task_results:
            if value.disposition == 'source_fallback':
                fallback_spans.setdefault(value.task_id, []).extend(value.source_spans)
    order = {block.id: index for index, block in enumerate(document.blocks())}
    gated = {}
    for declaration in data.template_package.definition.blocks:
        if declaration.when is not None:
            gated.setdefault(declaration.when.operation, set()).add(declaration.id)
    def placed(issue, value, target):
        if target.startswith('scope-'):
            return value.disposition == 'fallback' and any(overlaps(value.span, span) for span in fallback_spans.get(issue.task_id, []))
        return any(overlaps(value.span, span) for span in target_spans.get(target, []))
    for issue in issues:
        blocks = {identifier for value in coverage if value.disposition != 'source_only'
            and (not issue.target_ids or any(placed(issue, value, target) for target in issue.target_ids))
            for identifier in value.block_ids}
        if not blocks and any(target.startswith('scope-') for target in issue.target_ids):
            # A step without a view of its own (the role branch) points at the views its result selects.
            wanted = {views.get(issue.task_id)} | gated.get(views.get(issue.task_id), set())
            blocks = {block.id for block in document.blocks() if block.presentation is not None
                and block.presentation.view_key in wanted}
        if not blocks:
            blocks = {identifier for value in coverage if value.disposition != 'source_only' for identifier in value.block_ids}
        issue.block_ids = sorted(blocks, key=lambda identifier: order.get(identifier, len(order)))
    result.project = ProjectV6(schemaVersion=6, projectId=result.project_id, revision=result.project_revision,
        createdAt=result.created_at, sources=data.sources, evidenceRecords=[], facts=data.facts, document=document,
        assets=[], operations=data.operations, renders=[], templatePackage=data.template_package,
        importCoverage=coverage, importIssues=issues, templateOperations=data.template_operations, exports=[])
    result.pre_draft = None
    result.document_revision = document.revision
    return validated_with_history(result)
