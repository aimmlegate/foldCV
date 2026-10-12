"""Pure typed recalculation and annotation lifecycle without editorial inference."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/api/src'))

from packages.resume_core.dates import partial_date
from packages.resume_core.gui_derived import aliases, initial_derived
from packages.resume_core.gui_refresh import refresh
from packages.resume_core.gui_rendering import render_input
from packages.resume_core.models.recovery import Annotation, NameAssessmentFact, ObservationFact, Range, EvidenceSpan, authored_fields, record_slot
from tests.recovery.generation_fixtures import render_workspace
from tests.recovery.test_gui_annotations import annotations
from packages.resume_core.gui_annotations import initial_annotations
from tests.recovery.test_gui_mutations import apply, edit, new_record, restore


def workspace(example='E2'):
    result = render_workspace(example)
    request, draft, deps = annotations(example)
    result.annotations = initial_annotations(result.project_id, draft.document, request.normalized, draft.annotations, deps)
    return result


def value(workspace, id):
    return next(value for value in workspace.derived_state.values if value.field_id == id)


def set_periods(workspace, job, periods, session='periods', completion='none'):
    return apply(workspace, 'edit-field', {'fieldId': job.periods_field_id, 'text': None,
        'periods': [period.model_dump(by_alias=True) for period in periods], 'focus': None, 'sessionId': session, 'completion': completion})


def test_closed_typed_dates_update_duration_and_invalid_text_clears_obsolete_badge():
    result = workspace('E1')
    job = result.project.document.jobs[0]
    period = job.periods[0].model_copy(deep=True)
    period.end_text.text, period.present = '2024', False
    assert set_periods(result, job, [period]).status == 'applied'
    focus = result.project.document.skills_focus.focus[0]
    before = value(result, focus.display.field_id)
    assert before.complete_exposure and before.display and before.months_min is not None
    assert result.source_observed_at is None
    edit(result, period.end_text.field_id, 'invalid typed date', session='periods')
    assert result.project.document.jobs[0].periods[0].end_text.text == 'invalid typed date'
    assert not value(result, period.end_text.field_id).valid
    assert value(result, focus.display.field_id).display is None
    assert len([mark for mark in result.annotations if mark.code == 'missing_job_dates']) == 1
    assert render_input(result)[0].focus[0].duration == ''
    restore(result, record_slot(job), 'periods')
    assert result.project.document.jobs[0].periods[0].present
    assert value(result, focus.display.field_id).display is None
    assert not any(mark.code == 'missing_job_dates' for mark in result.annotations)


@pytest.mark.parametrize('start,end,present,gap', [('2020', '2022', False, False), ('2020-01', '2022-02', False, False),
    ('2020-01-01', '2020-01-01', False, False), ('2020', '', True, False), ('2020', '', False, True),
    ('', '2022', False, True), ('2023', '2022', False, True), ('bad', '', True, True), ('2020', '2022', True, True)])
def test_date_gap_uses_every_declared_period_and_not_missing_observation(start, end, present, gap):
    result = workspace()
    job = result.project.document.jobs[1]
    period = job.periods[0].model_copy(deep=True)
    period.start_text.text, period.end_text.text, period.present = start, end, present
    set_periods(result, job, [period])
    marks = [mark for mark in result.annotations if mark.code == 'missing_job_dates' and mark.anchor.field_id == job.periods_field_id]
    assert bool(marks) is gap and result.source_observed_at is None
    assert result.derived_state.document_revision == result.document_revision
    if not gap:
        bad = period.model_copy(deep=True);bad.id = 'incomplete'
        for key, field in [('startText', bad.start_text), ('endText', bad.end_text)]:field.field_id = f'{record_slot(job)}/period:incomplete/{key}'
        bad.start_text.text = ''
        set_periods(result, job, [period, bad])
        assert any(mark.code == 'missing_job_dates' and mark.anchor.field_id == job.periods_field_id for mark in result.annotations)
        set_periods(result, job, [period])
        assert not any(mark.code == 'missing_job_dates' and mark.anchor.field_id == job.periods_field_id for mark in result.annotations)


@pytest.mark.parametrize('section', ['education', 'languages'])
def test_empty_section_gap_fills_returns_on_delete_and_hidden_content_is_intentional(section):
    result = workspace()
    example = workspace('E1')
    record = new_record(example, section, 'new')
    apply(result, 'add', {'sectionId': section, 'record': record.model_dump(by_alias=True), 'afterRecordId': None})
    assert any(mark.code == 'missing_' + section for mark in result.annotations)
    first = authored_fields(record)[0]
    edit(result, first.field_id, 'User supplied content', session='row', completion='slot')
    assert not any(mark.code == 'missing_' + section for mark in result.annotations)
    apply(result, 'hide', {'slotId': record_slot(record), 'visible': False})
    assert not any(mark.code == 'missing_' + section for mark in result.annotations)
    restore(result, record_slot(record))
    assert any(mark.code == 'missing_' + section for mark in result.annotations)
    apply(result, 'delete', {'sectionId': section, 'recordId': record.id})
    mark = next(mark for mark in result.annotations if mark.code == 'missing_' + section)
    assert mark.anchor.kind == 'section' and mark.anchor.section_id == section


def test_removed_targets_have_no_orphan_fields_or_row_sections_and_ranges_reanchor():
    result = workspace()
    job = result.project.document.jobs[0]
    mark = next(mark for mark in result.annotations if mark.type == 'conflicting')
    mark.anchor.range = Range(start=0, end=100)
    edit(result, job.context.field_id, 'Current context', session='job')
    assert next(mark for mark in result.annotations if mark.type == 'conflicting').anchor.range is None
    row_mark = result.annotations[0].model_copy(deep=True)
    row_mark.id, row_mark.code, row_mark.type = 'row-mark', 'row_warning', 'warning'
    from packages.resume_core.models.recovery import SectionAnchor
    row_mark.anchor = SectionAnchor(kind='section', sectionId=record_slot(job))
    result.annotations.append(row_mark)
    apply(result, 'delete', {'sectionId': 'jobs', 'recordId': job.id})
    assert not any(mark.anchor.kind == 'field' and mark.anchor.field_id.startswith(record_slot(job) + '/') for mark in result.annotations)
    assert not any(mark.id == 'row-mark' for mark in result.annotations)
    assert any(mark.code == 'missing_education' for mark in result.annotations)


def test_exact_aliases_change_without_semantic_regrouping_or_authored_text_changes():
    result = workspace('E1')
    job = result.project.document.jobs[0]
    edit(result, job.stack.field_id, 'Postgres; Golang / Python 3.11; ExampleDB-X', session='stack')
    field = result.project.document.jobs[0].stack
    assert field.text == 'Postgres; Golang / Python 3.11; ExampleDB-X'
    assert set(value(result, field.field_id).canonical_aliases) == {'postgresql', 'golang', 'python'}
    assert aliases('Go, Node, DRF, R, ExampleDB-X') == []
    assert any(mark.code == 'editorial_plan_stale' for mark in result.annotations)
    assert result.editorial_plan.origin == 'model'
    assert result.editorial_plan.jobs == workspace('E1').editorial_plan.jobs


def test_deleted_job_and_removed_typed_stack_do_not_supply_obsolete_exposure():
    result = workspace('E1')
    job = result.project.document.jobs[0]
    period = job.periods[0].model_copy(deep=True);period.end_text.text, period.present = '2024', False
    set_periods(result, job, [period])
    focus = result.project.document.skills_focus.focus[0]
    assert value(result, focus.display.field_id).display
    edit(result, job.stack.field_id, 'JavaScript', session='periods')
    assert value(result, focus.display.field_id).display is None
    restore(result, record_slot(job), 'periods')
    apply(result, 'delete', {'sectionId': 'jobs', 'recordId': job.id})
    assert value(result, focus.display.field_id).months_min is None
    assert all(not value.field_id.startswith(record_slot(job) + '/') for value in result.derived_state.values)


def test_effective_observation_stays_unchanged_and_present_with_end_is_invalid_even_when_observed():
    result = workspace('E1')
    result.source_observed_at = partial_date('2026-10-11')
    observation = next(fact for fact in result.project.facts if isinstance(fact, ObservationFact))
    source = result.project.sources[0]
    unit = source.units[0].model_copy(deep=True);unit.id = 'observation';unit.text = 'Сведения актуальны на 2026-10-11.'
    source.units.append(unit)
    observation.value.source_observed_at = result.source_observed_at
    observation.value.evidence = EvidenceSpan(sourceId=source.id, sourceRevision=source.revision,
        unitId=unit.id, unitRevision=unit.revision, text=unit.text)
    refresh(result, [])
    focus = result.project.document.skills_focus.focus[0]
    assert value(result, focus.display.field_id).display
    job = result.project.document.jobs[0]
    period = job.periods[0].model_copy(deep=True);period.end_text.text = '2024'
    set_periods(result, job, [period])
    assert result.source_observed_at == partial_date('2026-10-11')
    assert not value(result, period.end_text.field_id).valid
    assert value(result, focus.display.field_id).display is None
    assert any(mark.code == 'missing_job_dates' for mark in result.annotations)


def test_unknown_surname_stays_unmarked_and_changed_explicit_assessment_is_stale_not_guessed():
    result = workspace()
    edit(result, 'candidate/name', 'User name', session='candidate')
    assert not any(mark.code == 'missing_surname' for mark in result.annotations)
    known = workspace('E1')
    assessment = next(fact for fact in known.project.facts if isinstance(fact, NameAssessmentFact));assessment.value.missing_surname = True
    original = known.project.document.candidate.name.text
    refresh(known, [])
    assert any(mark.code == 'missing_surname' for mark in known.annotations)
    edit(known, 'candidate/name', 'Changed supplied name', session='candidate')
    assert not any(mark.code == 'missing_surname' for mark in known.annotations)
    assert any(mark.code == 'name_assessment_stale' for mark in known.annotations)
    edit(known, 'candidate/name', original, session='candidate')
    assert any(mark.code == 'missing_surname' for mark in known.annotations)
    assert not any(mark.code == 'name_assessment_stale' for mark in known.annotations)


def test_focus_validation_replaces_warning_without_exporting_marks_or_changing_skills_text():
    result = workspace('E1')
    focus = result.project.document.skills_focus.focus[0].model_copy(deep=True)
    bad = focus.model_copy(deep=True);bad.id = 'bad';bad.catalog_id = 'unknown';bad.display.field_id = 'skills-focus/focus:bad/display'
    skills = result.project.document.skills_focus.skills_text.text
    apply(result, 'edit-field', {'fieldId': result.project.document.skills_focus.focus_field_id, 'text': None,
        'periods': None, 'focus': [focus.model_dump(by_alias=True), bad.model_dump(by_alias=True)], 'sessionId': 'focus', 'completion': 'field'})
    warnings = [mark for mark in result.annotations if mark.code == 'focus_entry_removed']
    assert len(warnings) == 1 and warnings[0].type == 'warning' and warnings[0].anchor.section_id == 'skills-focus'
    assert warnings[0].removed_focus[0].reason == 'unknown-ID'
    assert result.project.document.skills_focus.skills_text.text == skills
    assert [entry.catalog_id for entry in result.project.document.skills_focus.focus] == ['python']
    prepared = render_input(result)[0]
    assert warnings[0].reason not in prepared.model_dump_json()
    apply(result, 'edit-field', {'fieldId': result.project.document.skills_focus.focus_field_id, 'text': None,
        'periods': None, 'focus': [focus.model_dump(by_alias=True)], 'sessionId': 'focus', 'completion': 'field'})
    assert not any(mark.code == 'focus_entry_removed' for mark in result.annotations)
