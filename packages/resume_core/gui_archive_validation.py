"""Check portable references before admitting data into a local project."""

from .gui_archive_zip import ArchiveFailure,digest,safe_path,alias
from .gui_mutations import unicode_valid
from .gui_selection import field_index,normalized_text,utf16_slice
from .models.recovery import ObservationFact,authored_fields,record_slot


def validate_workspace(workspace):
    def require(ok):
        if not ok:raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID')
    def unique(items):require(len(items)==len(set(items)))
    unicode_valid(workspace.model_dump())
    owner=workspace.project or workspace.pre_draft
    facts={fact.id for fact in owner.facts};sources={source.id:source for source in owner.sources}
    unique([fact.id for fact in owner.facts]);unique([source.id for source in owner.sources])
    unique([alias(source.byte_ref) for source in owner.sources])
    unique([operation.id for operation in owner.operations]);unique([item.id for item in workspace.generations])
    require(workspace.document_revision<=workspace.project_revision)
    for source in owner.sources:
        require(safe_path(source.byte_ref) and source.byte_ref.startswith('sources/'))
        unique([unit.id for unit in source.units]);unique([overlay.id for overlay in source.overlays])
        require([unit.order for unit in source.units]==list(range(len(source.units))))
        for unit in source.units:require(set(unit.represented_fact_ids)<=facts)
        for overlay in source.overlays:require(overlay.unit_id is None or overlay.unit_id in {unit.id for unit in source.units})
    def evidence(ref):
        source=sources.get(ref.source_id)
        unit=next((unit for unit in source.units if unit.id==ref.unit_id),None) if source else None
        require(source is not None and unit is not None and source.revision==ref.source_revision and unit.revision==ref.unit_revision)
        if hasattr(ref,'text'):require(ref.text in unit.text)
    for fact in owner.facts:
        for ref in [*fact.evidence,*getattr(fact,'literal_evidence',[])]:evidence(ref)
        if fact.kind in {'source_observation','name_assessment'}:
            refs=fact.value.evidence
            for ref in refs if isinstance(refs,list) else [refs] if refs else []:evidence(ref)
    observations=[fact.value.source_observed_at for fact in owner.facts if isinstance(fact,ObservationFact)]
    if workspace.source_observed_at:require(workspace.source_observed_at in observations)
    if workspace.pre_draft:require(workspace.pre_draft.selected_source_id is None or workspace.pre_draft.selected_source_id in sources)
    def record(value,valid):
        for field in authored_fields(value):
            require(field.text==normalized_text(field.text) and set(field.fact_ids)<=valid)
            for ref in field.evidence:evidence(ref)
    if workspace.project:
        document=workspace.project.document;indexed=field_index(document)
        anchors=set(indexed)|{job.periods_field_id for job in document.jobs}|{document.skills_focus.focus_field_id}
        for item in document.records():record(item,facts)
        job_ids={job.id for job in workspace.project.employment}
        for job in workspace.project.employment:require(set(job.fact_ids)<=facts)
        for fact in owner.facts:require(fact.job_id is None or fact.job_id in job_ids or any(job.id==fact.job_id for job in document.jobs))
        if workspace.editorial_plan:
            plan=workspace.editorial_plan
            require({job.job_id for job in plan.jobs}==job_ids and plan.formatting_as_of==workspace.formatting_as_of)
            for ids in [plan.fact_ids,*(job.fact_ids for job in plan.jobs),*(item.fact_ids for item in plan.focus),*(item.fact_ids for item in plan.technology_groups)]:require(set(ids)<=facts)
        for slot,session in workspace.edit_sessions.items():
            require(record_slot(session.baseline.record)==slot and session.started_document_revision<=workspace.document_revision)
            require(all(value.field_id in {field.field_id for field in authored_fields(session.baseline.record)} and value.text==normalized_text(value.text) for value in session.buffered_fields))
        for cp in [*workspace.undo_slots.values(),*(session.baseline for session in workspace.edit_sessions.values())]:
            if cp:
                record(cp.record,facts|{fact.id for fact in cp.facts}|{stamp.fact_id for stamp in cp.fact_stamps})
                require(cp.document_revision<=workspace.document_revision and cp.project_revision<=workspace.project_revision)
                for fact in cp.facts:
                    for ref in fact.evidence:evidence(ref)
        unique([mark.id for mark in workspace.annotations]);unique([item.id for item in workspace.related_update_suggestions])
        suggestions={item.id for item in workspace.related_update_suggestions}
        for mark in workspace.annotations:
            require(set(mark.fact_ids)<=facts and (mark.update_suggestion_id is None or mark.update_suggestion_id in suggestions))
            if not mark.resolved and mark.anchor.kind=='field':require(mark.anchor.field_id in anchors)
            for ref in mark.evidence:evidence(ref)
        for item in workspace.related_update_suggestions:
            require(set(item.fact_ids)<=facts)
            for replacement in item.replacements:
                require(replacement.text==normalized_text(replacement.text))
                if item.dependencies.document_revision==workspace.document_revision:
                    require(replacement.field_id in indexed)
                    if replacement.range:utf16_slice(indexed[replacement.field_id][0].text,replacement.range.start,replacement.range.end)
        for exclusion in workspace.source_exclusions:require(set(exclusion.fact_ids)<=facts and set(exclusion.source_ids)<=sources.keys())
    for operation in owner.operations:require(operation.project_id==workspace.project_id)
    for generation in workspace.generations:require(generation.project_id==workspace.project_id and set(generation.source_ids)<=sources.keys())
    for rules in [workspace.rules_used,*(op.rules_used for op in owner.operations),*(generation.rules_used for generation in workspace.generations)]:
        if rules and digest(rules.markdown.encode('utf-8'))!=rules.sha256:raise ArchiveFailure('ARCHIVE_RULES_INVALID')
    for render in owner.renders:require(render.document_revision<=workspace.document_revision and render.project_revision<=workspace.project_revision)
    return workspace
