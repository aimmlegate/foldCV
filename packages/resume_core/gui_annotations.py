"""Located initial uncertainty, separate from authored text and render input."""

from __future__ import annotations

from .gui_derived import complete_period
from .gui_normalization import GuiNormalizedResult
from .models.recovery import Annotation, Dependencies, Document, JobRecord, NameAssessmentFact, authored_fields
from .normalization import _id


def complete_job_dates(job: JobRecord, facts) -> bool:
    if not job.periods:
        return False
    return all(complete_period(period, facts) for period in job.periods)


def filled_section(rows) -> bool:
    return any(row.visible and any(field.text.strip() for field in authored_fields(row)) for row in rows)


def unresolved_source_units(normalized):
    assessments = {fact.id for fact in normalized.facts if fact.kind == "name_assessment"
        or fact.kind == "source_observation" and fact.value.source_observed_at is None}
    return [(source, unit) for source in normalized.sources for unit in source.units
        if unit.text.strip() and unit.disposition == "unresolved" and not set(unit.represented_fact_ids) - assessments]


def initial_annotations(project_id: str, document: Document, normalized: GuiNormalizedResult,
                        warnings: list[Annotation], dependencies: Dependencies) -> list[Annotation]:
    marks = [mark.model_copy(update={"dependencies": dependencies.model_copy(deep=True)}, deep=True)
             for mark in warnings]

    def add(code, type, anchor, reason, fact_ids=None, evidence=None):
        marks.append(Annotation(id=_id("annotation", project_id, code, str(anchor)), type=type,
            code=code, anchor=anchor, dependencies=dependencies.model_copy(deep=True),
            factIds=fact_ids or [], reason=reason, evidence=evidence or [], resolved=False,
            updateSuggestionId=None, removedFocus=[]))

    if normalized._native_recovery_count or unresolved_source_units(normalized):
        add("source_details_unresolved", "warning", {"kind": "document"},
            "Some source details could not be structured. Review the saved source.")

    assessment = next(fact for fact in normalized.facts if isinstance(fact, NameAssessmentFact))
    if document.candidate.visible and document.candidate.name.text.strip() and assessment.value.missing_surname is True:
        add("missing_surname", "missing", {"kind": "field", "fieldId": document.candidate.name.field_id, "range": None},
            "The source explicitly says the surname is missing.", [assessment.id], assessment.value.evidence)
    for section, rows in (("education", document.education), ("languages", document.languages)):
        if not filled_section(rows):
            add("missing_" + section, "missing", {"kind": "section", "sectionId": section},
                "No supplied content in this section.")
    jobs = {job.id: job for job in document.jobs}
    for job in document.jobs:
        if job.visible and not complete_job_dates(job, normalized.facts):
            add("missing_job_dates", "missing", {"kind": "field", "fieldId": job.periods_field_id, "range": None},
                "Every declared period needs a valid start and an ordered end or an explicit present flag.")
    for conflict in normalized.conflicts:
        job = jobs.get(conflict.job_id)
        if job and job.visible:
            add(conflict.code, "conflicting", {"kind": "field", "fieldId": job.context.field_id, "range": None},
                "The source gives conflicting team sizes.", conflict.fact_ids, conflict.evidence)
    return marks
