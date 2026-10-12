"""Pure annotation/derived lifecycle; semantic choices remain explicit work."""

from .gui_annotations import complete_job_dates
from .gui_derived import digest, initial_derived
from .gui_drafting import available_focus_ids
from .gui_normalization import source_fingerprint
from .gui_selection import field_index
from .models.recovery import Annotation, CandidateFact, Dependencies, NameAssessmentFact, ObservationFact, authored_fields, record_slot
from .normalization import _id
from .technologies import BY_ID


def validate_focus(workspace, explicit=False):
    available, seen, kept, removed = available_focus_ids(), set(), [], []
    for entry in workspace.project.document.skills_focus.focus:
        reason = "duplicate" if entry.catalog_id in seen else "unknown-ID" if entry.catalog_id not in BY_ID else "missing-logo" if entry.catalog_id not in available else "capacity" if len(kept) >= 8 else None
        seen.add(entry.catalog_id)
        if reason:
            removed.append({"catalogId": entry.catalog_id, "reason": reason})
        else:
            kept.append(entry)
    workspace.project.document.skills_focus.focus = kept
    if explicit or removed:
        workspace.annotations = [mark for mark in workspace.annotations if mark.code != "focus_entry_removed"]
    return removed


def refresh(workspace, changed_slots, removed_focus=None):
    document, facts = workspace.project.document, workspace.project.facts
    indexed = field_index(document)
    valid_fields = set(indexed) | {job.periods_field_id for job in document.jobs} | {document.skills_focus.focus_field_id}
    valid_sections = {"candidate", "profile", "employment", "jobs", "education", "certifications", "languages",
                      "skills-focus", "early-career", "document-sidebar"} | {record_slot(record) for record in document.records()}
    deps = Dependencies(projectRevision=workspace.project_revision, documentRevision=workspace.document_revision,
        rulesSha256=workspace.rules_used.sha256 if workspace.rules_used else None,
        sourceFingerprint=source_fingerprint(workspace.project.sources),
        dependencyFingerprint=digest({"document": document.model_dump(mode="json", by_alias=True),
                                     "facts": [fact.model_dump(mode="json", by_alias=True) for fact in facts]}))
    initial_codes = {"missing_surname", "missing_education", "missing_languages", "missing_job_dates"}
    previous = workspace.annotations
    marks = []
    for mark in previous:
        if mark.code in initial_codes:
            continue
        if mark.anchor.kind == "field" and mark.anchor.field_id not in valid_fields:
            continue
        if mark.anchor.kind == "section" and mark.anchor.section_id not in valid_sections:
            continue
        value = mark.model_copy(deep=True)
        value.dependencies = deps.model_copy(deep=True)
        if value.anchor.kind == "field" and value.anchor.range is not None:
            field = indexed.get(value.anchor.field_id)
            if not field or field[1] in changed_slots or value.anchor.range.end > len(field[0].text.encode("utf-16-le")) // 2:
                value.anchor.range = None
        marks.append(value)

    def add(code, type, anchor, reason, fact_ids=None, evidence=None, removed=None):
        old = next((mark for mark in previous if mark.code == code and mark.anchor.model_dump(by_alias=True) == anchor), None)
        marks.append(Annotation(id=old.id if old else _id("annotation", workspace.project_id, code, str(anchor)),
            type=type, code=code, anchor=anchor, dependencies=deps.model_copy(deep=True), factIds=fact_ids or [],
            reason=reason, evidence=evidence or [], resolved=False, updateSuggestionId=None, removedFocus=removed or []))

    assessment = next((fact for fact in facts if isinstance(fact, NameAssessmentFact)), None)
    supplied_name = next((fact.value.text for fact in facts if isinstance(fact, CandidateFact) and fact.value.field == "name"), None)
    if assessment and assessment.value.missing_surname is True and document.candidate.name.text.strip():
        anchor = {"kind": "field", "fieldId": document.candidate.name.field_id, "range": None}
        if document.candidate.name.text == supplied_name:
            marks = [mark for mark in marks if mark.code != "name_assessment_stale"]
            add("missing_surname", "missing", anchor, "The source explicitly says the surname is missing.", [assessment.id], assessment.value.evidence)
        elif not any(mark.code == "name_assessment_stale" for mark in marks):
            add("name_assessment_stale", "stale", anchor, "The name changed after its source assessment.", [assessment.id])
    else:
        marks = [mark for mark in marks if mark.code != "name_assessment_stale"]
    for section, rows in (("education", document.education), ("languages", document.languages)):
        if not any(any(field.text.strip() for field in authored_fields(row)) for row in rows):
            add("missing_" + section, "missing", {"kind": "section", "sectionId": section}, "No supplied content in this section.")
    for job in document.jobs:
        if job.visible and not complete_job_dates(job, facts):
            add("missing_job_dates", "missing", {"kind": "field", "fieldId": job.periods_field_id, "range": None},
                "Every declared period needs a valid start and an ordered end or an explicit present flag.")
    if changed_slots and workspace.editorial_plan and workspace.editorial_plan.origin == "model":
        marks = [mark for mark in marks if mark.code != "editorial_plan_stale"]
        add("editorial_plan_stale", "stale", {"kind": "document"}, "Authored inputs changed after the editorial plan.")
    if removed_focus:
        marks = [mark for mark in marks if mark.code != "focus_entry_removed"]
        add("focus_entry_removed", "warning", {"kind": "section", "sectionId": "skills-focus"},
            "Ineligible focus entries were removed.", removed=removed_focus)
    workspace.annotations = marks
    language = workspace.editorial_plan.source_language if workspace.editorial_plan else "ru"
    observation = next((fact.value.source_observed_at for fact in facts if isinstance(fact, ObservationFact)), None)
    workspace.derived_state = initial_derived(document, facts, workspace.project.employment,
        observation, workspace.document_revision, language)
