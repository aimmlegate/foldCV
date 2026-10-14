"""Completion, authoritative facts, background races and durable analysis recovery."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import threading
import sys

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/api/src'))

from packages.resume_core.gui_reconciliation import (GuiAnalysisRequest, GuiReconcileProposal,
    apply_reconciliation, reconciliation_input, result_dependencies, validate_proposal)
from packages.resume_core.gui_mutations import document_content
from packages.resume_core.gui_selection import field_index
from packages.resume_core.models.recovery import GuiTextFact
from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.project_store import ProjectStore, ProjectStoreFailure
from packages.resume_core.gui_projects import GuiRenameProjectRequest
from packages.resume_core.storage import StorageFailure
from resume_api.gui_projects import GuiProjectService, ProjectFailure
from resume_api.gui_admission import QueuedProvider
from resume_api.lifecycle import SpikeError
from resume_api.providers.content import ContentFailure
from tests.recovery.generation_fixtures import CreationProvider, render_workspace, frozen_now
from tests.recovery.test_gui_mutations import mutation, edit, restore, new_record, apply
from tests.recovery.test_gui_rewriting import request
from tests.recovery.test_gui_projects import service


def empty_reply(payload):
    return GuiReconcileProposal(facts=[], fieldFacts=[{'fieldId': field['fieldId'], 'factIds':field.get('factIds',[])}
        for field in payload['input']['changedFields']], annotations=[], suggestions=[], editorialPlan=None, recommendations=[])


class AnalysisProvider(CreationProvider):
    def __init__(self, *, delayed=False, fail=None):
        super().__init__();self.started=threading.Event();self.release=threading.Event();self.delayed=delayed;self.fail=fail
        self.active=0;self.maximum=0;self.order=[]
    def generate(self, request, files, cancel):
        payload=json.loads(request.text)
        if request.result_type is GuiReconcileProposal:
            self.calls.append(payload);self.order.append('analysis-start');self.active+=1;self.maximum=max(self.active,self.maximum);self.started.set()
            try:
                if self.delayed:self.release.wait(5)
                if self.fail:raise ContentFailure(self.fail, logical_attempts=1)
                from resume_api.providers.content import ContentResult, ReportedUsage
                return ContentResult(empty_reply(payload), ReportedUsage(input_tokens=3,output_tokens=2),'fixture',request.policy.model,.01,1)
            finally:self.active-=1;self.order.append('analysis-release')
        self.order.append('rewrite-start');return super().generate(request,files,cancel)


def setup(tmp_path, provider=None, *, durable=False, delay=.01):
    provider=provider or AnalysisProvider();store=service(tmp_path,provider);store.analysis_delay=delay
    workspace=render_workspace();workspace.rules_used=store.rules.load();store.workspaces[workspace.project_id]=workspace
    if durable:
        store.storage=ProjectStore(store.rules.root)
        # This seam uses the existing source ownership contract.
        for source in workspace.project.sources:
            store.originals[(workspace.project_id,source.id)]=b''
            source.byte_sha256=__import__('hashlib').sha256(b'').hexdigest()
        assert store.persist(workspace.project_id)=='durable'
    return store,workspace,provider


def change(store, workspace, text, *, field='profile/text', completion='none', session='typing'):
    return store.mutate(workspace.project_id,mutation(workspace,'edit-field',{'fieldId':field,'text':text,'periods':None,'focus':None,
        'sessionId':session,'completion':completion}))


async def settled(store, workspace):
    async def wait():
        while workspace.project_id in store.analysis_timers:await asyncio.sleep(.01)
        tasks=[task for (id,_),task in store.tasks.items() if id==workspace.project_id]
        if tasks:await asyncio.gather(*tasks)
    await asyncio.wait_for(wait(),7)


async def started(provider):
    async def wait():
        while not provider.started.is_set():await asyncio.sleep(.005)
    await asyncio.wait_for(wait(),5)


@pytest.mark.asyncio
async def test_typing_save_ticks_unchanged_focus_and_restore_never_infer(tmp_path):
    store,w,p=setup(tmp_path)
    change(store,w,'First');await asyncio.sleep(.04)
    change(store,w,'Second');await asyncio.sleep(.04)
    assert p.calls==[] and store.pending_analysis(w.project_id).analysis_batch.completed_field_ids==[]
    change(store,w,'Second',completion='none');assert p.calls==[]
    store.mutate(w.project_id,mutation(w,'restore-previous-block',{'slotId':'profile','sessionId':'typing'}))
    await asyncio.sleep(.04);assert p.calls==[] and store.pending_analysis(w.project_id) is None
    change(store,w,w.project.document.profile.text.text,completion='field')
    await asyncio.sleep(.04);assert p.calls==[]
    await store.shutdown()


@pytest.mark.asyncio
async def test_completion_waits_500ms_coalesces_and_keeps_open_undo_session(tmp_path):
    store,w,p=setup(tmp_path,delay=.5)
    change(store,w,'First completed',completion='paragraph')
    await asyncio.sleep(.2);assert p.calls==[] and 'profile' in w.edit_sessions and w.undo_slots['profile'] is None
    change(store,w,'Latest completed',completion='field')
    await asyncio.sleep(.3);assert p.calls==[]
    await settled(store,w)
    assert len(p.calls)==1 and p.calls[0]['input']['changedFields'][0]['text']=='Latest completed'
    assert 'profile' in w.edit_sessions and w.undo_slots['profile'] is None
    assert w.project.operations[-1].usage.logical_attempts==1


@pytest.mark.asyncio
async def test_new_edit_removes_completion_eligibility_until_next_completion(tmp_path):
    store,w,p=setup(tmp_path,delay=.06)
    change(store,w,'Completed',completion='paragraph');change(store,w,'New incomplete')
    await settled(store,w);assert p.calls==[]
    change(store,w,'New incomplete',completion='field');await settled(store,w)
    assert len(p.calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('change_kind',['flush','rename','rules','unsaved'])
async def test_late_result_rejects_both_counters_rules_or_new_unsaved_input_and_retains_pending(tmp_path,change_kind):
    store,w,p=setup(tmp_path,AnalysisProvider(delayed=True))
    change(store,w,'Completed',completion='paragraph');await started(p)
    if change_kind=='flush':change(store,w,'Newer 1000 ms flush')
    elif change_kind=='rename':store.rename(w.project_id,GuiRenameProjectRequest(title='New name',baseRevision=w.project_revision))
    elif change_kind=='rules':store.rules.save(store.rules.load().markdown+'\nNew policy.',store.rules.load().revision)
    else:await store.analysis_action(w.project_id,GuiAnalysisRequest(action='invalidate',fieldIds=['profile/text']))
    revisions=w.project_revision,w.document_revision;p.release.set();await settled(store,w)
    assert (w.project_revision,w.document_revision)==revisions
    assert w.project.operations[0].status in {'failed','cancelled'} and store.pending_analysis(w.project_id)
    assert len(p.calls)==1


@pytest.mark.asyncio
async def test_pause_persists_accumulates_and_resume_sends_one_current_batch(tmp_path):
    store,w,p=setup(tmp_path);store.preferences=PreferencesStore(store.rules.root)
    store.preferences.select_model('fixture-model');store.preferences.save_analysis(False)
    change(store,w,'Paused first',completion='paragraph');await settled(store,w)
    change(store,w,'Paused current',completion='field');await settled(store,w);assert p.calls==[]
    reopened=PreferencesStore(store.rules.root);assert reopened.load().automatic_analysis is False and reopened.load().selected_model=='fixture-model'
    reopened.save_analysis(True);await store.set_analysis_preference(True);await settled(store,w)
    assert len(p.calls)==1 and p.calls[0]['input']['changedFields'][0]['text']=='Paused current'


@pytest.mark.asyncio
@pytest.mark.parametrize('code',['MODEL_DENIED','QUOTA_EXHAUSTED','INVALID_RESULT'])
async def test_failure_has_one_attempt_no_loop_explicit_retry_and_later_completion(tmp_path,code):
    store,w,p=setup(tmp_path,AnalysisProvider(fail=code))
    change(store,w,'Completed',completion='field');await settled(store,w);await asyncio.sleep(.04)
    assert len(p.calls)==1 and w.project.operations[0].usage.logical_attempts==1
    assert not store.pending_analysis(w.project_id).analysis_batch.enabled
    p.fail=None;await store.analysis_action(w.project_id,GuiAnalysisRequest(action='retry'));await settled(store,w);assert len(p.calls)==2
    p.fail=code;change(store,w,'Another',completion='field');await settled(store,w);assert len(p.calls)==3
    p.fail=None;change(store,w,'Newest',completion='paragraph');await settled(store,w);assert len(p.calls)==4


@pytest.mark.asyncio
async def test_failed_durable_write_starts_no_model_and_requires_explicit_retry(tmp_path,monkeypatch):
    store,w,p=setup(tmp_path,durable=True)
    original=store.storage.save
    def denied(*args):raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    monkeypatch.setattr(store.storage,'save',denied)
    result=change(store,w,'Completed but unsaved',completion='paragraph');await settled(store,w)
    assert result.persistence=='failed' and p.calls==[]
    monkeypatch.setattr(store.storage,'save',original);store.persist(w.project_id)
    await asyncio.sleep(.04);assert p.calls==[]
    await store.analysis_action(w.project_id,GuiAnalysisRequest(action='retry'));await settled(store,w)
    assert len(p.calls)==1


@pytest.mark.asyncio
async def test_restart_preserves_pending_fields_and_completion_without_resuming_inference(tmp_path):
    store,w,p=setup(tmp_path,durable=True,delay=1)
    change(store,w,'Completed',completion='paragraph');store.stop_analysis_timer(w.project_id)
    reopened=GuiProjectService(tmp_path/'reopened',store.rules,lambda:(p,'fixture'),storage=ProjectStore(store.rules.root),clock=frozen_now,analysis_delay=.01)
    current=reopened.read(w.project_id);pending=reopened.pending_analysis(w.project_id)
    assert pending.target_field_ids==['profile/text'] and pending.analysis_batch.completed_field_ids==['profile/text']
    assert not pending.analysis_batch.enabled and pending.error_code=='INTERRUPTED'
    await asyncio.sleep(.04);assert p.calls==[] and current.edit_sessions['profile'].baseline==w.edit_sessions['profile'].baseline
    await reopened.analysis_action(w.project_id,GuiAnalysisRequest(action='retry'));await settled(reopened,current);assert len(p.calls)==1


def shared_claim():
    w=render_workspace();job=w.project.document.jobs[0]
    fact=GuiTextFact(id='trainee-fact',revision=1,kind='text',value={'text':'Mentored two trainees'},origin='source',importance='normal',jobId=job.id,subprojectId=None,evidence=[],literalEvidence=[])
    w.project.facts.append(fact)
    for field in (w.project.document.profile.text,job.tasks):field.text='Mentored two trainees';field.fact_ids=[fact.id]
    return w,job,fact


def claim_reply(w,field,fact):
    changed=fact.model_copy(deep=True);changed.value.text='Mentored three trainees'
    return GuiReconcileProposal(facts=[changed],fieldFacts=[{'fieldId':field,'factIds':[fact.id]}],
        annotations=[{'id':'profile-conflict','type':'conflicting','code':'trainee_conflict','anchor':{'kind':'field','fieldId':'profile/text','range':None},
        'factIds':[fact.id],'reason':'The job correction is authoritative.','updateSuggestionId':'profile-update'}],
        suggestions=[{'id':'profile-update','factIds':[fact.id],'replacements':[{'fieldId':'profile/text','range':None,'text':'Mentored three trainees'}],
        'reason':'Update the older mention.'}],editorialPlan=None,recommendations=['Keep the current user correction.'])


def test_authoritative_job_correction_keeps_profile_text_and_first_restore_branch():
    w,job,fact=shared_claim();rules=w.rules_used=__import__('tests.recovery.draft_fixtures',fromlist=['RULES']).RULES
    edit(w,job.tasks.field_id,'Mentored three trainees',completion='slot')
    baseline=w.undo_slots['job:'+job.id].model_copy(deep=True);authored=document_content(w.project.document);before=w.project_revision,w.document_revision
    reply=claim_reply(w,job.tasks.field_id,fact)
    apply_reconciliation(w,[job.tasks.field_id],reply,result_dependencies(w,rules),rules,frozen_now().isoformat())
    assert document_content(w.project.document)==authored and w.project.document.profile.text.text=='Mentored two trainees'
    assert (w.project_revision,w.document_revision)==(before[0]+1,before[1])
    effective=next(f for f in w.project.facts if f.id==fact.id);assert effective.origin=='user' and effective.value.text=='Mentored three trainees'
    assert w.undo_slots['job:'+job.id]==baseline and w.related_update_suggestions[0].dependencies==result_dependencies(w,rules)
    restore(w,'job:'+job.id)
    assert next(f for f in w.project.facts if f.id==fact.id).value.text=='Mentored two trainees'
    assert not any(mark.type=='conflicting' for mark in w.annotations)


def test_unrelated_title_reconciliation_retains_profile_recipe_without_revalidating_it():
    from tests.recovery.test_gui_related import corrected
    from tests.recovery.draft_fixtures import RULES
    w, _job, _fact = corrected()
    recipe = w.related_update_suggestions[0].model_copy(deep=True)
    edit(w, 'candidate/title', 'Updated candidate title', completion='field')
    field = w.project.document.candidate.title
    reply = GuiReconcileProposal(facts=[], fieldFacts=[{'fieldId': field.field_id, 'factIds': field.fact_ids}],
        annotations=[], suggestions=[], editorialPlan=None, recommendations=[])
    apply_reconciliation(w, [field.field_id], reply, result_dependencies(w, RULES), RULES, '')
    assert w.related_update_suggestions == [recipe]
    assert any(mark.update_suggestion_id == recipe.id for mark in w.annotations)
    assert recipe.dependencies != result_dependencies(w, RULES)


def test_reconciliation_inside_session_preserves_baseline_and_user_addition_origin():
    w,job,fact=shared_claim();rules=__import__('tests.recovery.draft_fixtures',fromlist=['RULES']).RULES;w.rules_used=rules
    edit(w,job.tasks.field_id,'Mentored three trainees',completion='paragraph');baseline=w.edit_sessions['job:'+job.id].baseline.model_copy(deep=True)
    apply_reconciliation(w,[job.tasks.field_id],claim_reply(w,job.tasks.field_id,fact),result_dependencies(w,rules),rules,'')
    assert w.edit_sessions['job:'+job.id].baseline==baseline and w.undo_slots['job:'+job.id] is None
    restore(w,'job:'+job.id);assert next(f for f in w.project.facts if f.id==fact.id).value.text=='Mentored two trainees'
    row=new_record(w,'education','added');apply(w,'add',{'sectionId':'education','record':row.model_dump(by_alias=True),'afterRecordId':None})
    edit(w,row.institution.field_id,'User university',completion='field')
    new=fact.model_copy(deep=True);new.id='user-added';new.job_id=None;new.value.text='User university'
    reply=GuiReconcileProposal(facts=[new],fieldFacts=[{'fieldId':row.institution.field_id,'factIds':[new.id]}],annotations=[],suggestions=[],editorialPlan=None,recommendations=[])
    apply_reconciliation(w,[row.institution.field_id],reply,result_dependencies(w,rules),rules,'')
    assert next(f for f in w.project.facts if f.id==new.id).origin=='user'


def test_scoped_input_immutable_sources_observation_and_foreign_result_rejection():
    w,job,fact=shared_claim();rules=__import__('tests.recovery.draft_fixtures',fromlist=['RULES']).RULES;w.rules_used=rules
    originals=[source.model_dump() for source in w.project.sources];observed=w.source_observed_at
    edit(w,job.tasks.field_id,'Mentored three trainees',completion='field')
    payload=json.loads(reconciliation_input(w,[job.tasks.field_id],rules))
    assert set(payload['input'])=={'projectId','projectRevision','documentRevision','changedFields','facts','otherMentions','nameAssessmentFactId','annotations','editorialPlan'}
    assert 'sources' not in payload['input'] and any(mention['fieldId']=='profile/text' for mention in payload['input']['otherMentions'])
    reply=claim_reply(w,job.tasks.field_id,fact);reply.field_facts[0].field_id='candidate/name'
    with pytest.raises(ValueError,match='ANALYSIS_SCOPE_INVALID'):validate_proposal(w,[job.tasks.field_id],reply)
    assert [source.model_dump() for source in w.project.sources]==originals and w.source_observed_at==observed


@pytest.mark.asyncio
async def test_rewrite_waits_for_obsolete_analysis_cleanup_then_coalesces_once(tmp_path):
    store,w,p=setup(tmp_path,AnalysisProvider(delayed=True));change(store,w,'Completed',completion='field');await started(p)
    captured=request(w,rules=store.rules.load());task=asyncio.create_task(store.rewrite(w.project_id,captured))
    await asyncio.sleep(.03);assert not task.done() and 'rewrite-start' not in p.order
    p.release.set();result=await task;assert result.status=='applied'
    p.delayed=False;await settled(store,w)
    assert p.order[:3]==['analysis-start','analysis-release','rewrite-start'] and p.maximum==1
    assert len([call for call in p.calls if call['task']=='reconcile_edits'])==2
    assert w.project.operations[0].status=='cancelled'
    assert p.calls[-1]['input']['changedFields'][0]['text']==w.project.document.profile.text.text


@pytest.mark.asyncio
async def test_rewrite_cleanup_failure_preserves_text_and_never_admits_rewrite(tmp_path):
    store,w,p=setup(tmp_path,AnalysisProvider(delayed=True));change(store,w,'Completed',completion='field');await started(p)
    key=next(key for key in store.files)
    def failed():raise SpikeError('PROCESS_CLEANUP_FAILED')
    store.files[key].stop_worker=failed
    with pytest.raises(ProjectFailure,match='PROCESS_CLEANUP_FAILED'):await store.rewrite(w.project_id,request(w,rules=store.rules.load()))
    assert w.project.document.profile.text.text=='Completed' and 'rewrite-start' not in p.order
    p.release.set();await settled(store,w)


@pytest.mark.asyncio
async def test_more_than_twenty_batches_have_one_attempt_each_and_no_lifetime_cap(tmp_path):
    store,w,p=setup(tmp_path)
    for index in range(21):
        change(store,w,'Batch '+str(index),completion='paragraph');await settled(store,w)
    assert len(p.calls)==21 and p.maximum==1 and all(op.usage.logical_attempts==1 for op in w.project.operations)


@pytest.mark.asyncio
async def test_queued_global_lock_wait_counts_zero_until_admission_and_cancels_without_busy(tmp_path):
    class Busy:
        def __init__(self):self.inner=AnalysisProvider();self.release=threading.Event();self.waiting=threading.Event()
        def generate(self,request,files,cancel):
            self.waiting.set()
            if not self.release.is_set():raise ContentFailure('BUSY')
            return self.inner.generate(request,files,cancel)
    provider=Busy();store,w,_=setup(tmp_path,provider)
    change(store,w,'Completed',completion='field')
    async def wait():
        while not provider.waiting.is_set():await asyncio.sleep(.005)
    await asyncio.wait_for(wait(),5)
    operation=w.project.operations[0];assert operation.status=='queued' and operation.usage is None
    await store.cancel(w.project_id,operation.id);assert operation.status=='cancelled' and operation.usage.logical_attempts==0
    assert provider.inner.calls==[]
    provider.release.set();await store.analysis_action(w.project_id,GuiAnalysisRequest(action='retry'));await settled(store,w)
    assert len(provider.inner.calls)==1 and w.project.operations[-1].usage.logical_attempts==1


@pytest.mark.asyncio
async def test_other_project_analysis_is_not_cancelled_by_a_rewrite(tmp_path):
    store,w,p=setup(tmp_path,AnalysisProvider(delayed=True));other=w.model_copy(deep=True)
    other.project_id=other.project.project_id='other-project';store.workspaces[other.project_id]=other
    change(store,other,'Other completed',completion='field');await started(p)
    task=asyncio.create_task(store.rewrite(w.project_id,request(w,rules=store.rules.load())))
    await asyncio.sleep(.03)
    assert not store.cancels[(other.project_id,other.project.operations[0].id)].is_set()
    p.release.set();assert (await task).status=='applied';p.delayed=False
    await settled(store,other);await settled(store,w)
    assert other.project.operations[0].status=='completed'


def test_repeat_metadata_result_is_noop_and_forbidden_observation_never_changes_source_date():
    w,job,fact=shared_claim();rules=__import__('tests.recovery.draft_fixtures',fromlist=['RULES']).RULES;w.rules_used=rules
    edit(w,job.tasks.field_id,'Mentored three trainees',completion='slot')
    reply=claim_reply(w,job.tasks.field_id,fact)
    apply_reconciliation(w,[job.tasks.field_id],reply,result_dependencies(w,rules),rules,'')
    counters=w.project_revision,w.document_revision
    assert not apply_reconciliation(w,[job.tasks.field_id],reply,result_dependencies(w,rules),rules,'')
    assert (w.project_revision,w.document_revision)==counters
    from packages.resume_core.models.recovery import ObservationFact
    observed=ObservationFact(id='observation',revision=1,kind='source_observation',value={'sourceObservedAt':None,'evidence':None,'revision':1},
        evidence=[],origin='source',importance='normal',jobId=None,subprojectId=None)
    reply.facts=[observed];reply.field_facts[0].fact_ids=['observation']
    with pytest.raises(ValueError,match='ANALYSIS_SCOPE_INVALID'):apply_reconciliation(w,[job.tasks.field_id],reply,result_dependencies(w,rules),rules,'')
    assert w.source_observed_at is None


def test_failed_analysis_preference_write_keeps_prior_choice_model_and_theme(tmp_path,monkeypatch):
    prefs=PreferencesStore(tmp_path/'FoldCV');from packages.resume_core.rules import RulesStore
    RulesStore(prefs.root).load();prefs.select_model('fixture-model');before=prefs.load()
    def denied(*args):raise StorageFailure('denied')
    monkeypatch.setattr(prefs,'_write',denied)
    from packages.resume_core.preferences import PreferencesFailure
    with pytest.raises(PreferencesFailure,match='PREFERENCES_SAVE_FAILED'):prefs.save_analysis(False)
    assert prefs.load()==before


@pytest.mark.asyncio
async def test_protected_preferences_and_analysis_api_keep_counters_and_require_explicit_resume(tmp_path):
    from tests.recovery.test_preferences import application, MetadataAdapter, client_session
    provider=AnalysisProvider();app=application(tmp_path,MetadataAdapter(),provider);store=app.app.state.gui_projects
    store.rules.load();store.ensure_loaded();w=render_workspace();w.rules_used=store.rules.load()
    for source in w.project.sources:
        source.byte_sha256=__import__('hashlib').sha256(b'').hexdigest();store.originals[(w.project_id,source.id)]=b''
    store.workspaces[w.project_id]=w;store.persist(w.project_id)
    async with client_session(app) as client:
        counters=w.project_revision,w.document_revision
        assert (await client.put('/v1/settings/preferences',headers={'Origin':'http://evil.invalid'},json={'automaticAnalysis':False})).status_code==403
        assert (await client.put('/v1/settings/preferences',json={'automaticAnalysis':False,'selectedModel':'foreign'})).status_code==422
        assert (await client.put('/v1/settings/preferences',json={'automaticAnalysis':False})).json()['automaticAnalysis'] is False
        assert (w.project_revision,w.document_revision)==counters and provider.calls==[]
        change(store,w,'Paused HTTP correction',completion='field');await settled(store,w);assert provider.calls==[]
        assert (await client.post('/v1/projects/'+w.project_id+'/analysis',json={'action':'invalidate','fieldIds':['foreign']})).status_code==422
        assert (await client.get('/v1/projects/'+w.project_id)).status_code==200 and provider.calls==[]
        assert (await client.put('/v1/settings/preferences',json={'automaticAnalysis':True})).status_code==200
        await settled(store,w);assert len(provider.calls)==1
    await store.shutdown()


@pytest.mark.asyncio
async def test_pausing_running_analysis_cancels_only_owned_work_and_retains_current_batch(tmp_path):
    store,w,p=setup(tmp_path,AnalysisProvider(delayed=True));store.preferences=PreferencesStore(store.rules.root)
    store.preferences.load();change(store,w,'Current completion',completion='field');await started(p)
    store.preferences.save_analysis(False);task=asyncio.create_task(store.set_analysis_preference(False))
    await asyncio.sleep(.02);assert not task.done();p.release.set();await task
    assert w.project.operations[0].status=='cancelled' and store.pending_analysis(w.project_id).target_field_ids==['profile/text']
    assert len(p.calls)==1;store.preferences.save_analysis(True);p.delayed=False;await store.set_analysis_preference(True);await settled(store,w)
    assert len(p.calls)==2 and w.project.operations[-1].status=='completed'


def test_completed_name_assessment_clears_old_gap_and_restore_recovers_source_assessment():
    from packages.resume_core.models.recovery import NameAssessmentFact, CandidateFact
    from tests.recovery.draft_fixtures import RULES
    w=render_workspace('E2');w.rules_used=RULES
    assessment=next(fact for fact in w.project.facts if isinstance(fact,NameAssessmentFact))
    name=next(fact for fact in w.project.facts if isinstance(fact,CandidateFact) and fact.value.field=='name')
    assessment.value.missing_surname=True
    original=assessment.model_copy(deep=True)
    edit(w,'candidate/name','Supplied Fullname',completion='slot')
    updated_name=name.model_copy(deep=True);updated_name.value.text='Supplied Fullname'
    updated=assessment.model_copy(deep=True);updated.value.missing_surname=False;updated.value.evidence=[]
    reply=GuiReconcileProposal(facts=[updated_name,updated],fieldFacts=[{'fieldId':'candidate/name','factIds':[name.id,assessment.id]}],
        annotations=[],suggestions=[],editorialPlan=None,recommendations=[])
    apply_reconciliation(w,['candidate/name'],reply,result_dependencies(w,RULES),RULES,'')
    assert not any(mark.code in {'missing_surname','name_assessment_stale'} for mark in w.annotations)
    restore(w,'candidate');restored=next(fact for fact in w.project.facts if isinstance(fact,NameAssessmentFact))
    assert restored.value==original.value and any(mark.code=='missing_surname' for mark in w.annotations)


def test_contact_text_in_assessment_reason_is_retained_without_rejection():
    w,job,fact=shared_claim();from tests.recovery.draft_fixtures import RULES
    w.rules_used=RULES;edit(w,job.tasks.field_id,'Mentored three trainees',completion='field')
    reply=claim_reply(w,job.tasks.field_id,fact);reply.annotations[0].reason='Call 555-123-4567'
    apply_reconciliation(w,[job.tasks.field_id],reply,result_dependencies(w,RULES),RULES,'')
    assert any(mark.reason == 'Call 555-123-4567' for mark in w.annotations)


def test_period_batch_assigns_facts_only_to_addressed_endpoints_without_other_job_fields():
    from tests.recovery.draft_fixtures import RULES
    w=render_workspace();w.rules_used=RULES;job=w.project.document.jobs[0];period=job.periods[0]
    old_tasks=job.tasks.model_copy(deep=True)
    edit(w,period.start_text.field_id,'2020',completion='field')
    fact=GuiTextFact(id='endpoint',revision=1,kind='text',value={'text':'2020'},origin='user',importance='normal',jobId=job.id,subprojectId=None,evidence=[],literalEvidence=[])
    reply=GuiReconcileProposal(facts=[fact],fieldFacts=[{'fieldId':period.start_text.field_id,'factIds':[fact.id]}],
        annotations=[],suggestions=[],editorialPlan=None,recommendations=[])
    apply_reconciliation(w,[job.periods_field_id],reply,result_dependencies(w,RULES),RULES,'')
    assert w.project.document.jobs[0].periods[0].start_text.fact_ids==[fact.id]
    assert w.project.document.jobs[0].tasks==old_tasks


@pytest.mark.asyncio
async def test_rules_read_failure_pauses_pending_batch_without_provider_or_automatic_retry(tmp_path,monkeypatch):
    from packages.resume_core.rules import RulesFailure
    store,w,p=setup(tmp_path)
    def unavailable():raise RulesFailure('RULES_CORRUPT')
    monkeypatch.setattr(store.rules,'load',unavailable)
    change(store,w,'Completed',completion='field');await settled(store,w)
    pending=store.pending_analysis(w.project_id)
    assert pending.error_code=='RULES_CORRUPT' and not pending.analysis_batch.enabled and p.calls==[]
    await asyncio.sleep(.04);assert p.calls==[]
