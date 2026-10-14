"""Independent frozen timeline examples, ambiguity and stale atomic cascades."""

import pytest

from packages.resume_core.dates import partial_date
from packages.resume_core.models.rich_facts import EmploymentRecord
from packages.resume_core.rich_assembly import field
from packages.resume_core.rich_fields import set_text
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_timeline import CascadeRequest, CascadeApplyRequest, cascade_proposal, cascade_mutation, timeline_report
from tests.recovery.test_rich_persistence import without_sources, patch
from tests.recovery.test_rich_synchronization import capture, mutation


def timeline(rows, as_of='2026-10-14'):
    workspace = without_sources(); workspace.project.document.regions[2].blocks=[]
    workspace.project.facts.records=[r for r in workspace.project.facts.records if r.kind!='employment']
    workspace.formatting_as_of=partial_date(as_of);workspace.source_observed_at=None
    for job_id,period_id,start,end in rows:
        job=next((r for r in workspace.project.facts.records if r.id==job_id),None)
        if job is None:
            job=EmploymentRecord(kind='employment',id=job_id,revision=1,origin='user',evidence=[],employer=field(job_id),role=field(None),periods=[])
            workspace.project.facts.records.append(job)
        from packages.resume_core.models.rich_facts import WorkingPeriod
        job.periods.append(WorkingPeriod(id=period_id,revision=1,start=field(None),end=field(None),present=field(False,''),evidence=[]))
        set_text(job,f'period:{period_id}:start',start or '')
        set_text(job,f'period:{period_id}:end',end if end and end!='present' else '')
        set_text(job,f'period:{period_id}:present','present' if end=='present' else '')
    return workspace


def proposal(workspace,job='A',period='a'):
    return cascade_proposal(workspace,CascadeRequest(anchorJobId=job,anchorPeriodId=period,capture=capture('date-edit')))


def dates(value):
    from packages.resume_core.rich_timeline import date_text
    return [(s.job_id,date_text(s.after.start.value),date_text(s.after.end.value),s.inclusive_span,s.unit) for s in value.shifts]


@pytest.mark.parametrize('rows,expected',[
 ([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06')],[('B','2020-05','2020-07',3,'month')]),
 ([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06'),('C','c','2020-07','2020-08'),('D','d','2021-01','2021-02')],[('B','2020-05','2020-07',3,'month'),('C','2020-08','2020-09',2,'month')]),
 ([('A','a','2024-02-01','2024-02-29'),('B','b','2024-02-29','2024-03-02')],[('B','2024-03-01','2024-03-03',3,'day')]),
 ([('A','a','2020-01','2020-03'),('B','b','2020-01','2020-02')],[('B','2020-04','2020-05',2,'month')]),
 ([('A','a','2020-01','2020-04'),('A','b','2020-04','2020-06')],[('A','2020-05','2020-07',3,'month')]),
])
def test_frozen_forward_examples_preserve_units_and_inclusive_duration(rows,expected):
    workspace=timeline(rows);original=workspace.model_dump_json();value=proposal(workspace)
    assert value.status=='available' and dates(value)==expected
    assert workspace.model_dump_json()==original
    assert value.period_order[0]=='a'


@pytest.mark.parametrize('rows,anchor,reason',[
 ([('A','a','2020','2022'),('B','b','2022','2024')],('A','a'),'EXACT_CLOSED_PERIOD_REQUIRED'),
 ([('A','a','2020-01','present'),('B','b','2020-06','2020-08')],('A','a'),'EXACT_CLOSED_PERIOD_REQUIRED'),
 ([('A','a','2020-01-01','2020-04-30'),('B','b','2020-04','2020-06')],('A','a'),'CHAIN_PRECISION_OR_OPEN_BOUNDARY'),
 ([('A','a','2020-01','2020-06'),('B','b','2020-05','2020-08')],('B','b'),'EARLIER_OR_UNCERTAIN_OVERLAP'),
 ([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06'),('C','c','2020-07','present')],('A','a'),'CHAIN_PRECISION_OR_OPEN_BOUNDARY'),
 ([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06'),('C','c','2020-07','2019-01')],('A','a'),'CHAIN_PRECISION_OR_OPEN_BOUNDARY'),
])
def test_ambiguous_or_earlier_boundaries_expose_no_computable_prefix(rows,anchor,reason):
    value=proposal(timeline(rows),*anchor)
    assert value.status=='unavailable' and value.reason==reason and value.shifts==[]


def test_future_boundary_keeps_manual_dates_and_suppresses_unreliable_exposure():
    workspace=timeline([('A','a','2020-01','2020-08'),('B','b','2020-08','2020-09')],as_of='2020-09-30')
    value=proposal(workspace);assert value.status=='unavailable' and value.reason=='FUTURE_BOUNDARY'
    future=timeline([('A','a','2030-01','2030-02')])
    report=timeline_report(future)
    assert any(w.kind=='future' for w in report.warnings)
    assert report.estimates[0].months_min is None and report.estimates[0].reason=='FUTURE_OR_INVALID_PERIOD'


def test_inclusive_possible_certain_and_adjacent_ranges_are_distinct_for_all_pairs():
    monthly=timeline([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06'),('C','c','2020-05','2020-06')])
    report=timeline_report(monthly)
    overlap=[w for w in report.warnings if w.kind=='overlap']
    assert [(w.period_ids,w.certainty) for w in overlap]==[(['a','b'],'possible'),(['b','c'],'certain')]
    exact=timeline([('A','a','2024-02-28','2024-02-29'),('B','b','2024-03-01','2024-03-03')])
    assert not [w for w in timeline_report(exact).warnings if w.kind=='overlap']
    assert proposal(exact).reason=='NO_FORWARD_OVERLAP'


def test_open_unknown_and_invalid_dates_warn_without_invented_bounds_or_estimates():
    workspace=timeline([('A','a','2020-01','present'),('B','b','2021-01','2021-02'),('C','c','unknown','2022-01')])
    report=timeline_report(workspace)
    assert all(w.certainty=='possible' for w in report.warnings if w.kind=='overlap')
    assert report.estimates[0].months_min is None
    invalid=timeline([('A','a','2022-01','2020-01')])
    assert timeline_report(invalid).warnings[0].code=='DATE_ORDER_INVALID'
    assert proposal(invalid).shifts==[]
    observed=timeline([('A','a','2020-01','present')]);observed.source_observed_at=partial_date('2020-03-15')
    estimate=timeline_report(observed).estimates[0]
    assert (estimate.months_min,estimate.months_max)==(3,3)
    assert timeline_report(timeline([('A','a','2020-01','present')])).estimates[0].reason=='SOURCE_OBSERVATION_REQUIRED'


def test_parallel_experience_counts_once_and_unrelated_overlaps_remain_after_chain():
    workspace=timeline([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06'),('C','c','2023-01','2023-05'),('D','d','2023-03','2023-06')])
    report=timeline_report(workspace);assert (report.estimates[0].months_min,report.estimates[0].months_max)==(12,12)
    value=proposal(workspace);assert [s.job_id for s in value.shifts]==['B']
    assert next(w.id for w in report.warnings if w.period_ids==['c','d']) in value.warnings


def test_multiple_tied_starts_are_all_shifted_and_ties_ignore_record_display_order():
    workspace=timeline([('C','c','2020-01','2020-02'),('B','b','2020-01','2020-02'),('A','a','2020-01','2020-03')])
    value=proposal(workspace)
    assert value.period_order==['a','b','c']
    assert dates(value)==[('B','2020-04','2020-05',2,'month'),('C','2020-06','2020-07',2,'month')]


def test_cascade_rejects_changed_and_equal_text_restored_dates_but_allows_unrelated_prose():
    workspace=timeline([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06')]);value=proposal(workspace)
    request=CascadeApplyRequest(proposal=value,capture=capture('apply'))
    prose,_=apply_rich_mutation(workspace,patch(workspace,'Unrelated'))
    result,_=apply_rich_mutation(prose,cascade_mutation(prose,request))
    assert next(r for r in result.project.facts.records if r.id=='B').periods[0].start.raw_text=='2020-05'
    b=next(r for r in workspace.project.facts.records if r.id=='B').model_copy(deep=True)
    set_text(b,'period:b:start','2020-03')
    changed,_=apply_rich_mutation(workspace,mutation(workspace,[{'kind':'put_record','beforeRevision':b.revision,'record':b.model_dump(by_alias=True)}],id='new-date'))
    with pytest.raises(ValueError,match='STALE_CASCADE'):cascade_mutation(changed,request)
    set_text(b,'period:b:start','2020-04')
    restored,_=apply_rich_mutation(changed,mutation(changed,[{'kind':'put_record','beforeRevision':next(r for r in changed.project.facts.records if r.id=='B').revision,'record':b.model_dump(by_alias=True)}],id='same-date'))
    with pytest.raises(ValueError,match='STALE_CASCADE'):cascade_mutation(restored,request)


def test_nested_subproject_periods_do_not_enter_employment_warnings_or_cascades():
    from packages.resume_core.models.rich_facts import SubprojectRecord
    workspace=timeline([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06')])
    period=next(r for r in workspace.project.facts.records if r.id=='A').periods[0].model_copy(deep=True)
    period.id='nested';period.end.value=partial_date('2030-01');period.end.raw_text='2030-01'
    workspace.project.facts.records.append(SubprojectRecord(kind='subproject',id='sub',jobId='A',revision=1,origin='user',evidence=[],name=field('Project'),role=field(None),periods=[period]))
    assert not any('nested' in warning.period_ids for warning in timeline_report(workspace).warnings)
    assert proposal(workspace).period_order==['a','b']


def test_cascade_dates_and_estimate_survive_owned_store_restart_without_inference(tmp_path):
    from tests.recovery.test_rich_images_service import service
    api,identifier=service(tmp_path)
    workspace=timeline([('A','a','2020-01','2020-04'),('B','b','2020-04','2020-06')])
    api.workspaces[identifier]=workspace;api.persist(identifier)
    value=proposal(workspace)
    api.mutate(identifier,cascade_mutation(workspace,CascadeApplyRequest(proposal=value,capture=capture('cascade'))))
    before=timeline_report(api.read(identifier))
    reopened=type(api)(tmp_path/'restart',api.rules,lambda:pytest.fail('Reopen must not infer'))
    assert timeline_report(reopened.read(identifier))==before
    job=next(r for r in reopened.read(identifier).project.facts.records if r.id=='B')
    assert (job.periods[0].start.raw_text,job.periods[0].end.raw_text)==('2020-05','2020-07')
    assert not [w for w in before.warnings if w.kind=='overlap']


def test_timeline_and_cascade_require_a_document_instead_of_crashing_on_predraft():
    workspace=without_sources();workspace.project=None
    request=CascadeRequest(anchorJobId='A',anchorPeriodId='a',capture=capture())
    with pytest.raises(ValueError,match='DOCUMENT_REQUIRED'):timeline_report(workspace)
    with pytest.raises(ValueError,match='DOCUMENT_REQUIRED'):cascade_proposal(workspace,request)
