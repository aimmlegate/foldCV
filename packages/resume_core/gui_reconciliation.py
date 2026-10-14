"""Bounded reconciliation context and metadata-only authoritative acceptance."""

from typing import Literal
from pydantic import Field

from .gui_derived import digest
from .gui_mutations import document_content, records, unicode_valid
from .gui_normalization import public_context_facts, source_fingerprint
from .gui_legacy_context import public_workspace_facts
from .gui_projection import compatibility_views
from .gui_prompts import content_input
from .gui_refresh import refresh
from .gui_selection import field_index, selection_fingerprint, normalized_text, utf16_slice
from .models.contracts import Id, Wire
from .models.recovery import (RecoveryFact, Anchor, EditorialPlan, Annotation, Dependencies,
    FieldReplacement, RelatedUpdateSuggestion, NameAssessmentFact, authored_fields)
from .privacy import private_output_text


class GuiAnalysisRequest(Wire):
    action: Literal['invalidate', 'retry']
    field_ids: list[Id] = Field(default_factory=list, max_length=500)


class SaveAnalysisPreference(Wire):
    automatic_analysis: bool


class ReconciledField(Wire):
    field_id: Id
    fact_ids: list[Id] = Field(max_length=100)


class SemanticMark(Wire):
    id: Id
    type: Literal['missing', 'conflicting', 'warning']
    code: Id
    anchor: Anchor
    fact_ids: list[Id] = Field(max_length=100)
    reason: str = Field(max_length=2000)
    update_suggestion_id: Id | None


class SuggestedUpdate(Wire):
    id: Id
    fact_ids: list[Id] = Field(max_length=100)
    replacements: list[FieldReplacement] = Field(min_length=1, max_length=100)
    reason: str = Field(max_length=2000)


class GuiReconcileProposal(Wire):
    facts: list[RecoveryFact] = Field(max_length=500)
    field_facts: list[ReconciledField] = Field(max_length=500)
    annotations: list[SemanticMark] = Field(max_length=500)
    suggestions: list[SuggestedUpdate] = Field(max_length=100)
    editorial_plan: EditorialPlan | None
    recommendations: list[str] = Field(max_length=50)


def analysis_index(workspace):
    index = field_index(workspace.project.document)
    for job in workspace.project.document.jobs:
        index[job.periods_field_id] = (None, 'job:' + job.id)
    index[workspace.project.document.skills_focus.focus_field_id] = (None, 'skills-focus')
    return index


def relevant_ids(workspace, field_ids):
    indexed = analysis_index(workspace)
    ids = set()
    if workspace.project.document.candidate.name.field_id in field_ids:
        ids.update(fact.id for fact in workspace.project.facts if isinstance(fact, NameAssessmentFact))
    for id in field_ids:
        field, slot = indexed[id]
        if field: ids.update(field.fact_ids)
        else: ids.update(ref for value in authored_fields(records(workspace)[slot]) for ref in value.fact_ids)
        session = workspace.edit_sessions.get(slot)
        baseline = session.baseline if session else workspace.undo_slots.get(slot)
        if baseline: ids.update(fact.id for fact in baseline.facts)
        ids.update(ref for mark in workspace.annotations if mark.anchor.kind == 'field'
            and mark.anchor.field_id in indexed and indexed[mark.anchor.field_id][1] == slot for ref in mark.fact_ids)
    return ids


def assessed_fields(workspace, field_ids):
    indexed = analysis_index(workspace)
    ids = relevant_ids(workspace, field_ids)
    slots = {indexed[id][1] for id in field_ids}
    return set(field_ids) | {id for id, (field, _slot) in indexed.items() if field and set(field.fact_ids) & ids} | {
        mark.anchor.field_id for mark in workspace.annotations if mark.anchor.kind == 'field'
        and mark.anchor.field_id in indexed and indexed[mark.anchor.field_id][1] in slots}


def reconciliation_input(workspace, field_ids, rules):
    indexed = analysis_index(workspace)
    if not field_ids or not set(field_ids) <= indexed.keys(): raise ValueError('ANALYSIS_SCOPE_INVALID')
    ids = relevant_ids(workspace, field_ids)
    facts = [fact for fact in public_workspace_facts(workspace) if fact.id in ids]
    public = {fact.id for fact in facts}
    fields = []
    mentions = []
    for id, (field, slot) in indexed.items():
        if id in field_ids:
            if field:
                fields.append({'fieldId': id, 'slotId': slot, 'text': field.text, 'factIds': [ref for ref in field.fact_ids if ref in public]})
            elif slot.startswith('job:'):
                fields.append({'fieldId': id, 'slotId': slot, 'periods': [item.model_dump(mode='json', by_alias=True) for item in records(workspace)[slot].periods]})
            else:
                fields.append({'fieldId': id, 'slotId': slot, 'focus': [item.model_dump(mode='json', by_alias=True) for item in workspace.project.document.skills_focus.focus]})
        elif field and set(field.fact_ids) & public:
            mentions.append({'fieldId': id, 'text': field.text, 'factIds': [ref for ref in field.fact_ids if ref in public]})
    assessment = next((fact for fact in workspace.project.facts if isinstance(fact, NameAssessmentFact)), None)
    anchors = assessed_fields(workspace, field_ids)
    marks = [{'id': mark.id, 'type': mark.type, 'code': mark.code, 'anchor': mark.anchor.model_dump(by_alias=True),
        'factIds': [id for id in mark.fact_ids if id in public], 'reason': mark.reason}
        for mark in workspace.annotations if mark.anchor.kind == 'field' and mark.anchor.field_id in anchors]
    return content_input('reconcile_edits', {'projectId': workspace.project_id,
        'projectRevision': workspace.project_revision, 'documentRevision': workspace.document_revision,
        'changedFields': fields, 'facts': [fact.model_dump(mode='json', by_alias=True) for fact in facts],
        'otherMentions': mentions, 'nameAssessmentFactId': assessment.id if assessment and workspace.project.document.candidate.name.field_id in field_ids else None,
        'annotations': marks,
        'editorialPlan': workspace.editorial_plan.model_dump(mode='json', by_alias=True) if workspace.editorial_plan else None}, rules)


def result_dependencies(workspace, rules):
    return Dependencies(projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
        rulesSha256=rules.sha256, sourceFingerprint=source_fingerprint(workspace.project.sources),
        dependencyFingerprint=selection_fingerprint(workspace))


def validate_proposal(workspace, field_ids, proposal):
    raw = proposal.model_dump(mode='json', by_alias=True)
    unicode_valid(raw)
    indexed = analysis_index(workspace)
    allowed = relevant_ids(workspace, field_ids)
    public = {fact.id for fact in public_workspace_facts(workspace)}
    if workspace.project.document.candidate.name.field_id in field_ids:
        public.update(fact.id for fact in workspace.project.facts if isinstance(fact, NameAssessmentFact))
    fields = [entry.field_id for entry in proposal.field_facts]
    expanded = set(field_ids)
    for id in field_ids:
        field, slot = indexed[id]
        if field is None:
            record = records(workspace)[slot]
            if slot.startswith('job:'):
                expanded.update(value.field_id for period in record.periods for value in (period.start_text, period.end_text))
            else:
                expanded.update(entry.display.field_id for entry in record.focus)
    required = {id for id in field_ids if indexed[id][0] is not None}
    if len(fields) != len(set(fields)) or not required <= set(fields) <= expanded: raise ValueError('ANALYSIS_SCOPE_INVALID')
    if any(indexed[item.field_id][0] is None and item.fact_ids for item in proposal.field_facts): raise ValueError('ANALYSIS_SCOPE_INVALID')
    facts = {fact.id: fact for fact in proposal.facts}
    if len(facts) != len(proposal.facts): raise ValueError('ANALYSIS_SCOPE_INVALID')
    references = {id for entry in proposal.field_facts for id in entry.fact_ids}
    existing = {fact.id for fact in workspace.project.facts}
    if not references <= public | facts.keys(): raise ValueError('ANALYSIS_SCOPE_INVALID')
    if not facts.keys() <= references or not (facts.keys() & existing) <= allowed & public: raise ValueError('ANALYSIS_SCOPE_INVALID')
    for fact in proposal.facts:
        if isinstance(fact, NameAssessmentFact):
            if workspace.project.document.candidate.name.field_id not in field_ids or fact.value.evidence:
                raise ValueError('ANALYSIS_SCOPE_INVALID')
        elif fact.kind == 'source_observation' or fact not in public_context_facts([fact]):
            raise ValueError('ANALYSIS_SCOPE_INVALID')
        if private_output_text(str(fact.value.model_dump() if hasattr(fact.value, 'model_dump') else fact.value)):
            raise ValueError('NO_SAFE_CONTENT')
        if fact.job_id is not None and fact.job_id not in ({job.id for job in workspace.project.document.jobs} | set(workspace.project.document.early_career.represented_job_ids)):
            raise ValueError('ANALYSIS_SCOPE_INVALID')
    mention_ids = {id for id, (field, _slot) in indexed.items() if field and set(field.fact_ids) & allowed}
    anchors = expanded | mention_ids | assessed_fields(workspace, field_ids)
    sections = {'education', 'languages', 'candidate', 'profile', 'employment', 'jobs', 'skills-focus', 'early-career', 'certifications'}
    suggestions = {item.id for item in proposal.suggestions}
    if len(suggestions) != len(proposal.suggestions): raise ValueError('ANALYSIS_SCOPE_INVALID')
    if len({mark.id for mark in proposal.annotations}) != len(proposal.annotations): raise ValueError('ANALYSIS_SCOPE_INVALID')
    for mark in proposal.annotations:
        if private_output_text(mark.reason): raise ValueError('NO_SAFE_CONTENT')
        if not set(mark.fact_ids) <= public | facts.keys() or mark.update_suggestion_id not in suggestions | {None}:
            raise ValueError('ANALYSIS_SCOPE_INVALID')
        if mark.anchor.kind == 'field':
            if mark.anchor.field_id not in anchors: raise ValueError('ANALYSIS_SCOPE_INVALID')
            field = indexed[mark.anchor.field_id][0]
            if mark.anchor.range:
                if not field: raise ValueError('ANALYSIS_SCOPE_INVALID')
                utf16_slice(field.text, mark.anchor.range.start, mark.anchor.range.end)
        elif mark.anchor.kind == 'section' and mark.anchor.section_id not in sections:
            raise ValueError('ANALYSIS_SCOPE_INVALID')
    for item in proposal.suggestions:
        if private_output_text(item.reason): raise ValueError('NO_SAFE_CONTENT')
        if not set(item.fact_ids) <= public | facts.keys(): raise ValueError('ANALYSIS_SCOPE_INVALID')
        if len({replacement.field_id for replacement in item.replacements}) != len(item.replacements): raise ValueError('ANALYSIS_SCOPE_INVALID')
        for replacement in item.replacements:
            if replacement.field_id not in anchors or not indexed[replacement.field_id][0]: raise ValueError('ANALYSIS_SCOPE_INVALID')
            field = indexed[replacement.field_id][0]
            if replacement.range: utf16_slice(field.text, replacement.range.start, replacement.range.end)
            replacement.text = normalized_text(replacement.text)
            if len(replacement.text) > 12000 or private_output_text(replacement.text): raise ValueError('NO_SAFE_CONTENT')
    if proposal.editorial_plan:
        plan_ids = [job.job_id for job in proposal.editorial_plan.jobs]
        if len(plan_ids) != len(set(plan_ids)) or set(plan_ids) != ({job.id for job in workspace.project.document.jobs} | set(workspace.project.document.early_career.represented_job_ids)):
            raise ValueError('ANALYSIS_SCOPE_INVALID')
        plan = proposal.editorial_plan
        if not set(plan.fact_ids) <= public | facts.keys() or any(not set(item.fact_ids) <= public | facts.keys() for item in [*plan.focus, *plan.technology_groups]):
            raise ValueError('ANALYSIS_SCOPE_INVALID')
        if any(private_output_text(text) for text in [*(item.display for item in plan.focus), *(item.title for item in plan.technology_groups)]):
            raise ValueError('NO_SAFE_CONTENT')
    if any(len(text) > 2000 or private_output_text(text) for text in proposal.recommendations): raise ValueError('NO_SAFE_CONTENT')
    return proposal


def apply_reconciliation(workspace, field_ids, proposal, dependencies, rules, updated_at):
    if dependencies != result_dependencies(workspace, rules): raise ValueError('ANALYSIS_STALE')
    proposal = validate_proposal(workspace, field_ids, proposal)
    if proposal.editorial_plan and (proposal.editorial_plan.rules_revision != rules.revision or proposal.editorial_plan.formatting_as_of != workspace.formatting_as_of):
        raise ValueError('ANALYSIS_SCOPE_INVALID')
    candidate = workspace.model_copy(deep=True)
    indexed = analysis_index(candidate)
    current = {fact.id: fact for fact in candidate.project.facts}
    for incoming in proposal.facts:
        value = incoming.model_copy(deep=True)
        value.origin, value.evidence = 'user', []
        if hasattr(value, 'literal_evidence'): value.literal_evidence = []
        previous = current.get(value.id)
        value.revision = previous.revision if previous else 1
        if previous and value.model_dump(exclude={'revision'}) != previous.model_dump(exclude={'revision'}): value.revision += 1
        current[value.id] = value
    candidate.project.facts = list(current.values())
    for item in proposal.field_facts:
        field, slot = indexed[item.field_id]
        if field: field.fact_ids = item.fact_ids[:];field.evidence = []
    if proposal.editorial_plan:
        candidate.editorial_plan = proposal.editorial_plan.model_copy(deep=True)
        candidate.annotations = [mark for mark in candidate.annotations if mark.code != 'editorial_plan_stale']
    # Replace only semantic assessments in the supplied context; pure gaps refresh below.
    relevant = assessed_fields(workspace, field_ids)
    assessed_fact_ids = relevant_ids(workspace, field_ids)
    pure = {'missing_surname', 'missing_education', 'missing_languages', 'missing_job_dates',
        'name_assessment_stale', 'focus_entry_removed', 'editorial_plan_stale'}
    candidate.annotations = [mark for mark in candidate.annotations if mark.code in pure or not
        (mark.anchor.kind == 'field' and mark.anchor.field_id in relevant or set(mark.fact_ids) & assessed_fact_ids)]
    retained = [item for item in candidate.related_update_suggestions if not
        (set(item.fact_ids) & assessed_fact_ids or any(value.field_id in relevant for value in item.replacements))]
    retained_ids = {item.id for item in retained}
    if retained_ids & {item.id for item in proposal.suggestions}: raise ValueError('ANALYSIS_SCOPE_INVALID')
    removed_ids = {item.id for item in candidate.related_update_suggestions} - retained_ids
    candidate.annotations = [mark for mark in candidate.annotations if mark.update_suggestion_id not in removed_ids]
    provisional = result_dependencies(candidate, rules)
    candidate.annotations += [Annotation(id=mark.id, type=mark.type, code='reconcile_' + mark.code,
        anchor=mark.anchor, dependencies=provisional, factIds=mark.fact_ids, reason=mark.reason,
        evidence=[], resolved=False, updateSuggestionId=mark.update_suggestion_id, removedFocus=[]) for mark in proposal.annotations]
    refresh(candidate, [])
    candidate.related_update_suggestions = retained + [RelatedUpdateSuggestion(id=item.id, dependencies=provisional,
        factIds=item.fact_ids, replacements=item.replacements, reason=item.reason) for item in proposal.suggestions]
    names = ('facts', 'document', 'views')
    def semantic(values): return [value.model_dump(exclude={'dependencies'}) for value in values]
    changed = (candidate.project.facts != workspace.project.facts or candidate.project.document != workspace.project.document
        or semantic(candidate.annotations) != semantic(workspace.annotations) or candidate.editorial_plan != workspace.editorial_plan
        or semantic(candidate.related_update_suggestions) != semantic(workspace.related_update_suggestions))
    if document_content(candidate.project.document) != document_content(workspace.project.document): raise ValueError('ANALYSIS_SCOPE_INVALID')
    if changed:
        candidate.project_revision += 1;candidate.project.revision = candidate.project_revision;candidate.updated_at = updated_at
        candidate.project.views = compatibility_views(candidate.project.document, candidate.project.facts)
        refresh(candidate, [])
        deps = result_dependencies(candidate, rules)
        for mark in candidate.annotations: mark.dependencies = deps.model_copy(deep=True)
        for suggestion in candidate.related_update_suggestions:
            if suggestion.id not in retained_ids: suggestion.dependencies = deps.model_copy(deep=True)
        for name in names: setattr(workspace.project, name, getattr(candidate.project, name))
        workspace.project.revision = candidate.project_revision
        for name in ('project_revision', 'updated_at', 'annotations', 'derived_state', 'related_update_suggestions', 'editorial_plan'):
            setattr(workspace, name, getattr(candidate, name))
    return changed


GUI_RECONCILE_CONTRACTS = {'gui_analysis_request': GuiAnalysisRequest, 'save_analysis_preference': SaveAnalysisPreference,
    'gui_reconcile_proposal': GuiReconcileProposal}
