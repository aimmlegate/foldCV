"""Publish the initial template tree while retaining original sources and fact history."""

from ..models.template_workspace import ProjectV6, validated_with_history
from ..templates.focus import catalog_for, remembered_icon, row_name
from ..templates.materialize import materialize
from ..templates.materialize_nodes import focus_row
from ..templates.span_coverage import overlaps
from ..template_capture import item_identities
from ..editing.template_effective import effective_cells
from ..templates.source_spans import payload_value
from .template_proposals import relation_evidence


def shown_cells(document, cells):
    """Each fact cell the document shows: its text and the blocks showing it, by cell ID. `cells`: the effective cells,
    whose text a field occurrence shows (the occurrence stores none of its own)."""
    found = {}
    def visit(spans, block):
        for span in spans:
            content = getattr(span, 'content', None)
            shown = [getattr(span, 'cell_id', None)] + [binding.cell_id for binding in
                (getattr(span, 'label_binding', None), getattr(span, 'url_binding', None)) if binding is not None]
            for cell in filter(None, shown):
                value = cells.get(cell)
                text = value.raw_input or (value.typed_value if isinstance(value.typed_value, str) else '') if value else ''
                found.setdefault(cell, (text, set()))[1].add(block)
            if isinstance(content, list) and not getattr(span, 'cell_id', None):
                visit(content, block)
    for block in document.blocks():
        if isinstance(getattr(block, 'content', None), list):
            visit(block.content, block.id)
    return found


def fold(text):
    return ' '.join(text.split()).casefold() if isinstance(text, str) else ''


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
    # A technology list cites lines of the whole CV, so a technology name's evidence places nothing (D145); its value finds
    # the same name where the document shows it.
    kinds = {value.id: value.builtin_kind for value in data.template_package.definition.fact_types}
    target_spans, target_values = {}, {}
    for retained in data.template_operations:
        for proposal in retained.proposals:
            for field in proposal.resolved_fields:
                identity = identities[field.item_handle]
                identifier = identity.cell_ids[field.field_key]
                target_spans.setdefault(identifier, []).extend(field.evidence)
                if kinds.get(identity.semantic_type) != 'technology':
                    continue
                try:
                    value = payload_value(proposal.reply.payload, field.pointer) if proposal.reply is not None else None
                except ValueError:
                    value = None
                if isinstance(value, str) and value.strip():
                    target_values.setdefault(identifier, value)
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
    joined = {value.id: value.parameters.uncertain_group for value in data.template_package.definition.operations
        if value.kind == 'assign_skills'}
    shown = shown_cells(document, {cell.id: cell for cell in effective_cells(data.facts, data.template_operations)})
    by_text = {}
    for cell, (text, _blocks) in shown.items():
        by_text.setdefault(fold(text), []).append(cell)
    def placed(issue, value, target):
        if target.startswith('scope-'):
            return value.disposition == 'fallback' and any(overlaps(value.span, span) for span in fallback_spans.get(issue.task_id, []))
        # A technology name the document does not show (the check rejected it) places nothing by its evidence: those are
        # the lines it was cited from, which other blocks show.
        if target in target_values and target not in shown:
            return False
        return any(overlaps(value.span, span) for span in target_spans.get(target, []))
    for issue in issues:
        # A rejected value names the shown fields with the same text, as a «Kafka 4.0» chip another block admitted: the
        # remark marks them, and changing them retires it.
        alike = [cell for target in issue.target_ids if target in target_values and target not in shown
            for cell in by_text.get(fold(target_values[target]), [])]
        if alike:
            issue.target_ids = list(dict.fromkeys([*issue.target_ids, *alike]))
        # A skills remark asks to check the group its technology joined, so it points at that group, not at the jobs
        # naming the technology; their lines share its source text.
        group = joined.get(views.get(issue.task_id))
        blocks = {block for cell in alike for block in shown[cell][1]} or {block.id for block in document.blocks()
            if group is not None and block.presentation is not None and block.presentation.view_key == group}
        if not blocks:
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
