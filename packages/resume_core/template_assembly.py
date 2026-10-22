"""Publish the initial template tree while retaining original sources and fact history."""

from .models.template_workspace import ProjectV6, WorkspaceV7
from .templates.materialize import materialize
from .templates.span_coverage import overlaps
from .template_capture import item_identities
from .template_proposals import relation_evidence


def assemble_template(workspace, operation):
    if workspace.schema_version != 7 or workspace.project is not None or workspace.pre_draft is None:
        raise ValueError('template assembly requires a new captured pre-draft')
    result = workspace.model_copy(deep=True)
    data = result.pre_draft
    document, coverage = materialize(data.template_package, data.facts, data.template_operations, data.sources,
        operation_id=operation.id, revision=result.document_revision + 1)
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
    for issue in issues:
        issue.block_ids = sorted({identifier for value in coverage
            if value.disposition != 'source_only' and (not issue.target_ids or any(
                target.startswith('scope-') or any(overlaps(value.span, span) for span in target_spans.get(target, []))
                for target in issue.target_ids)) for identifier in value.block_ids})
    result.project = ProjectV6(schemaVersion=6, projectId=result.project_id, revision=result.project_revision,
        createdAt=result.created_at, sources=data.sources, evidenceRecords=[], facts=data.facts, document=document,
        assets=[], operations=data.operations, renders=[], templatePackage=data.template_package,
        importCoverage=coverage, importIssues=issues, templateOperations=data.template_operations, exports=[])
    result.pre_draft = None
    result.document_revision = document.revision
    return WorkspaceV7.model_validate(result.model_dump(by_alias=True))
