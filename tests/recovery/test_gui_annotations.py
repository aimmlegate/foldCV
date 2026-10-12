"""Initial gaps use captured assessments and stable empty-section anchors."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_annotations import complete_job_dates, initial_annotations
from packages.resume_core.gui_drafting import validate_draft
from packages.resume_core.models.recovery import Dependencies, NameAssessmentFact
from tests.recovery.draft_fixtures import RULES, draft_request, draft_reply


def annotations(example="E2", removed_focus=False):
    request = draft_request(example)
    reply = draft_reply(request, example=example)
    if removed_focus:
        reply.editorial_plan.focus.append(reply.editorial_plan.focus[0].model_copy(update={"catalog_id": "unknown"}))
    draft = validate_draft(request, reply, RULES)
    dependencies = Dependencies(projectRevision=2, documentRevision=2, rulesSha256=RULES.sha256,
        sourceFingerprint=request.normalized.source_fingerprint, dependencyFingerprint="a" * 64)
    return request, draft, dependencies


def test_e2_initial_marks_locate_empty_sections_one_conflict_and_no_invented_fields():
    request, draft, deps = annotations()
    before = draft.document.model_dump()
    marks = initial_annotations(request.project_id, draft.document, request.normalized, draft.annotations, deps)
    assert draft.document.model_dump() == before
    assert draft.document.education == draft.document.languages == []
    assert {mark.code for mark in marks} == {"missing_education", "missing_languages", "missing_job_dates", "team_size_conflict"}
    for section in ("education", "languages"):
        mark = next(mark for mark in marks if mark.code == "missing_" + section)
        assert mark.anchor.kind == "section" and mark.anchor.section_id == section
    conflict = next(mark for mark in marks if mark.type == "conflicting")
    job = draft.document.jobs[0]
    assert conflict.anchor.field_id == job.context.field_id and job.context.text == ""
    assert len(conflict.fact_ids) == len(conflict.evidence) == 2
    claims = [fact for fact in request.normalized.facts if fact.id in conflict.fact_ids]
    assert {fact.value.team_size.number for fact in claims} == {5, 6}
    assert all(mark.dependencies == deps for mark in marks)
    dates = next(mark for mark in marks if mark.code == "missing_job_dates")
    assert dates.anchor.field_id == job.periods_field_id
    assert initial_annotations(request.project_id, draft.document, request.normalized, [], deps) == marks


@pytest.mark.parametrize("assessment,expected", [(True, True), (False, False), (None, False)])
def test_surname_gap_requires_explicit_assessment_and_no_other_header_gaps(assessment, expected):
    request, draft, deps = annotations()
    fact = next(fact for fact in request.normalized.facts if isinstance(fact, NameAssessmentFact))
    fact.value.missing_surname = assessment
    fact.value.evidence = request.normalized.semantic_proposal.candidate.name.evidence if assessment else []
    marks = initial_annotations(request.project_id, draft.document, request.normalized, [], deps)
    names = [mark for mark in marks if mark.code == "missing_surname"]
    assert bool(names) is expected
    if expected:
        assert names[0].fact_ids == [fact.id] and names[0].evidence == fact.value.evidence
        assert names[0].anchor.field_id == "candidate/name"
    assert not {mark.code for mark in marks} & {"missing_title", "missing_location", "missing_contacts", "missing_age", "missing_certifications"}


@pytest.mark.parametrize("start,end,present,complete", [
    ("2020", "2022", False, True), ("2020-01", "2022-02", False, True),
    ("2020-01-01", "2020-01-01", False, True), ("2020", "", True, True),
    ("2020", "", False, False), ("", "2022", False, False), ("", "", True, False),
    ("invalid", "2022", False, False), ("2020", "invalid", False, False),
    ("2020-13", "2022", False, False), ("2023", "2022", False, False),
    ("2020", "2022", True, False), ("2020", " ", True, True),
])
def test_all_declared_job_periods_must_be_complete_at_known_precision(start, end, present, complete):
    request, draft, _ = annotations()
    job = draft.document.jobs[1]
    period = job.periods[0]
    period.start_text.text, period.end_text.text, period.present = start, end, present
    assert complete_job_dates(job, request.normalized.facts) is complete
    if complete:
        incomplete = period.model_copy(deep=True)
        incomplete.id += "-incomplete"
        incomplete.start_text.text = ""
        job.periods.append(incomplete)
        assert not complete_job_dates(job, request.normalized.facts)
        job.periods.pop()
        assert complete_job_dates(job, request.normalized.facts)
    job.periods = []
    assert not complete_job_dates(job, request.normalized.facts)


def test_focus_removal_stays_warning_at_skills_and_render_input_has_no_marks():
    from packages.resume_core.gui_rendering import render_input
    from tests.recovery.generation_fixtures import render_workspace
    request, draft, deps = annotations("E1", removed_focus=True)
    marks = initial_annotations(request.project_id, draft.document, request.normalized, draft.annotations, deps)
    assert len(marks) == 1 and marks[0].type == "warning" and marks[0].code == "focus_entry_removed"
    assert marks[0].anchor.section_id == "skills-focus" and marks[0].dependencies == deps
    workspace = render_workspace()
    before = render_input(workspace)
    workspace.annotations = marks
    assert render_input(workspace) == before
