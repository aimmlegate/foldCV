"""One explicit guarded related update, independent undo and durable replay."""

import asyncio
import sys
from pathlib import Path

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api/src'))
from packages.resume_core.gui_reconciliation import apply_reconciliation,result_dependencies
from packages.resume_core.gui_mutations import document_content
from packages.resume_core.gui_selection import field_index
from packages.resume_core.models.recovery import RelatedUpdateSuggestion
from tests.recovery.test_gui_reconciliation import shared_claim,claim_reply,setup,change,settled
from tests.recovery.test_gui_mutations import edit,restore,apply,mutation
from tests.recovery.draft_fixtures import RULES
from tests.recovery.generation_fixtures import frozen_now,CreationProvider
from tests.recovery.test_project_store import service as reopened_service


def corrected():
    w,job,fact=shared_claim();w.rules_used=RULES
    edit(w,job.tasks.field_id,'Mentored three trainees',completion='slot')
    apply_reconciliation(w,[job.tasks.field_id],claim_reply(w,job.tasks.field_id,fact),result_dependencies(w,RULES),RULES,'')
    return w,job,fact


def related(w,*,id=None,suggestion=None,deps=None):
    suggestion=suggestion or w.related_update_suggestions[0]
    return mutation(w,'apply-related-update',{'suggestionId':suggestion.id,'dependencies':(deps or suggestion.dependencies).model_dump(by_alias=True)},id=id)


def invoke(w,request):
    from packages.resume_core.gui_mutations import apply_mutation
    return apply_mutation(w,request,frozen_now().isoformat(),rules_sha256=RULES.sha256)


def test_explicit_profile_update_then_job_restore_keeps_newer_profile_fact_and_job_conflict():
    w,job,fact=corrected();profile_before=w.project.document.profile.text.text;job_pointer=w.undo_slots['job:'+job.id].model_copy(deep=True)
    before=w.project_revision,w.document_revision
    result=invoke(w,related(w))
    assert result.changed_slot_ids==['profile'] and (w.project_revision,w.document_revision)==(before[0]+1,before[1]+1)
    assert w.project.document.profile.text.text=='Mentored three trainees' and w.project.document.profile.text.origin=='user'
    assert w.project.document.profile.text.fact_ids==[fact.id] and w.undo_slots['profile'].record.text.text==profile_before
    assert w.undo_slots['job:'+job.id]==job_pointer and not w.related_update_suggestions and not any(mark.type=='conflicting' for mark in w.annotations)
    restore(w,'job:'+job.id)
    assert w.project.document.jobs[0].tasks.text=='Mentored two trainees' and w.project.document.profile.text.text=='Mentored three trainees'
    assert next(item for item in w.project.facts if item.id==fact.id).value.text=='Mentored three trainees'
    assert any(mark.code=='restore_shared_fact_conflict' and mark.anchor.field_id.startswith('job:') for mark in w.annotations)
    assert w.undo_slots['job:'+job.id] is None


def test_restore_job_before_update_clears_related_conflict_and_rejects_consumed_suggestion():
    w,job,fact=corrected();intent=related(w);restore(w,'job:'+job.id)
    assert w.project.document.profile.text.text=='Mentored two trainees' and not any(mark.type=='conflicting' for mark in w.annotations)
    before=w.project_revision,w.document_revision
    assert invoke(w,intent).status=='stale' and (w.project_revision,w.document_revision)==before
    assert next(item for item in w.project.facts if item.id==fact.id).value.text=='Mentored two trainees'


@pytest.mark.parametrize('changed',['document','metadata','fact','source','rules','dependencies'])
def test_stale_related_dependencies_cannot_overwrite_current_content(changed):
    w,job,fact=corrected();intent=related(w)
    if changed=='document':edit(w,'profile/text','Newer authoritative typing',completion='field')
    elif changed=='metadata':w.project_revision+=1;w.project.revision=w.project_revision
    elif changed=='fact':w.project.facts[0].revision+=1
    elif changed=='source':w.project.sources[0].revision+=1
    elif changed=='dependencies':intent.root.payload.dependencies.dependency_fingerprint='a'*64
    before=document_content(w.project.document);counters=w.project_revision,w.document_revision
    if changed=='rules':
        from packages.resume_core.gui_mutations import apply_mutation
        result=apply_mutation(w,intent,'',rules_sha256='a'*64)
    else:result=invoke(w,intent)
    assert result.status in {'stale','rejected'} and document_content(w.project.document)==before and (w.project_revision,w.document_revision)==counters


def test_related_update_completes_target_session_and_checkpoints_immediately_preceding_text():
    w,job,fact=corrected();edit(w,'profile/text','Manual older mention',completion='paragraph')
    suggestion=w.related_update_suggestions[0];suggestion.dependencies=result_dependencies(w,RULES)
    before=w.edit_sessions['profile'].baseline.model_copy(deep=True)
    result=invoke(w,related(w));assert result.status=='applied' and 'profile' not in w.edit_sessions
    assert w.undo_slots['profile'].record.text.text=='Manual older mention' and w.undo_slots['profile']!=before
    restore(w,'profile');assert w.project.document.profile.text.text=='Manual older mention' and w.undo_slots['profile'] is None
    restore(w,'profile');assert w.project.document.profile.text.text=='Manual older mention'


def test_multi_slot_partial_utf16_related_update_is_atomic_and_preserves_boundaries():
    w,job,fact=shared_claim();w.rules_used=RULES
    edit(w,'profile/text','A 😀é B',completion='slot');edit(w,job.tasks.field_id,'Prefix OLD suffix',completion='slot')
    w.related_update_suggestions=[RelatedUpdateSuggestion(id='multiple',dependencies=result_dependencies(w,RULES),factIds=[fact.id],reason='Explicit update.',
        replacements=[{'fieldId':'profile/text','range':{'start':2,'end':6},'text':'🧩\r\n'},
            {'fieldId':job.tasks.field_id,'range':{'start':7,'end':10},'text':'NEW'}])]
    membership=[row.id for row in w.project.document.records()];before=w.project_revision,w.document_revision
    result=invoke(w,related(w))
    assert result.status=='applied' and result.changed_slot_ids==['profile','job:'+job.id]
    assert w.project.document.profile.text.text=='A 🧩\n B' and w.project.document.jobs[0].tasks.text=='Prefix NEW suffix'
    assert [row.id for row in w.project.document.records()]==membership and (w.project_revision,w.document_revision)==(before[0]+1,before[1]+1)
    restore(w,'profile');assert w.project.document.profile.text.text=='A 😀é B' and w.project.document.jobs[0].tasks.text=='Prefix NEW suffix'
    restore(w,'job:'+job.id);assert w.project.document.jobs[0].tasks.text=='Prefix OLD suffix'


@pytest.mark.parametrize('invalid',['foreign','surrogate','duplicate','missing_fact'])
def test_invalid_stored_replacement_rejects_whole_atomic_update_without_pointer_changes(invalid):
    w,job,fact=corrected();suggestion=w.related_update_suggestions[0]
    if invalid=='foreign':suggestion.replacements.append(suggestion.replacements[0].model_copy(update={'field_id':'unknown'}))
    elif invalid=='surrogate':
        edit(w,'profile/text','😀 older',completion='slot');suggestion=w.related_update_suggestions[0];suggestion.dependencies=result_dependencies(w,RULES)
        from packages.resume_core.models.recovery import Range
        suggestion.replacements[0].range=Range(start=1,end=2)
    elif invalid=='duplicate':suggestion.replacements.append(suggestion.replacements[0].model_copy(deep=True))
    else:suggestion.fact_ids=['unknown']
    before=document_content(w.project.document);pointers=w.undo_slots.copy();counters=w.project_revision,w.document_revision
    result=invoke(w,related(w))
    assert result.status=='rejected' and result.rejection_reason=='RELATED_UPDATE_INVALID'
    assert document_content(w.project.document)==before and w.undo_slots==pointers and (w.project_revision,w.document_revision)==counters


def test_noop_related_update_does_not_move_pointer_counters_or_active_session():
    w,job,fact=corrected();suggestion=w.related_update_suggestions[0]
    suggestion.replacements[0].text=w.project.document.profile.text.text
    before=w.model_copy(deep=True)
    assert invoke(w,related(w)).changed_slot_ids==[]
    assert document_content(w.project.document)==document_content(before.project.document)
    assert (w.project_revision,w.document_revision)==(before.project_revision,before.document_revision)
    assert w.undo_slots==before.undo_slots and w.edit_sessions==before.edit_sessions


@pytest.mark.asyncio
async def test_durable_related_update_replays_after_restart_with_zero_calls_and_keeps_newer_shared_fact(tmp_path):
    store,w,p=setup(tmp_path,durable=True)
    shared,job,fact=corrected();w.project.document=shared.project.document;w.project.facts=shared.project.facts
    w.annotations=shared.annotations;w.undo_slots=shared.undo_slots;w.edit_sessions=shared.edit_sessions
    w.project_revision,w.document_revision=shared.project_revision,shared.document_revision;w.project.revision=w.project_revision
    w.related_update_suggestions=shared.related_update_suggestions
    w.related_update_suggestions[0].dependencies=result_dependencies(w,store.rules.load())
    intent=related(w,id='related-durable');result=store.mutate(w.project_id,intent);assert result.persistence=='durable'
    await asyncio.sleep(.05);assert p.calls==[]
    replay=store.mutate(w.project_id,intent);assert replay.status=='replayed' and w.project_revision==result.project_revision
    provider=CreationProvider();reopened=reopened_service(tmp_path,provider);current=reopened.read(w.project_id)
    assert reopened.mutate(w.project_id,intent).status=='replayed' and provider.calls==[]
    restored=reopened.mutate(w.project_id,mutation(current,'restore-previous-block',{'slotId':'job:'+job.id,'sessionId':None}))
    current=reopened.read(w.project_id);assert restored.status=='applied' and current.project.document.profile.text.text=='Mentored three trainees'
    assert next(item for item in current.project.facts if item.id==fact.id).value.text=='Mentored three trainees'
    changed=intent.model_copy(deep=True);changed.root.payload.suggestion_id='different'
    assert reopened.mutate(w.project_id,changed).rejection_reason=='MUTATION_ID_REUSED'


@pytest.mark.asyncio
async def test_related_save_failure_retries_exact_action_without_double_replacement(tmp_path,monkeypatch):
    from packages.resume_core.project_store import ProjectStoreFailure
    store,w,p=setup(tmp_path,durable=True);shared,job,fact=corrected()
    for name in ('document','facts'):setattr(w.project,name,getattr(shared.project,name))
    for name in ('annotations','undo_slots','edit_sessions','project_revision','document_revision','related_update_suggestions'):setattr(w,name,getattr(shared,name))
    w.project.revision=w.project_revision;w.related_update_suggestions[0].dependencies=result_dependencies(w,store.rules.load())
    original=store.storage.save
    def failed(*args):raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    monkeypatch.setattr(store.storage,'save',failed);intent=related(w,id='lost-related-save')
    result=store.mutate(w.project_id,intent);assert result.persistence=='failed' and result.status=='applied'
    pointer=w.undo_slots['profile'].model_copy(deep=True);counters=w.project_revision,w.document_revision
    monkeypatch.setattr(store.storage,'save',original)
    retried=store.mutate(w.project_id,intent)
    assert retried.status=='replayed' and retried.persistence=='durable' and (w.project_revision,w.document_revision)==counters
    assert w.undo_slots['profile']==pointer and p.calls==[]


@pytest.mark.asyncio
async def test_service_checks_current_rules_but_completed_action_replay_needs_no_rules_read(tmp_path,monkeypatch):
    store,w,p=setup(tmp_path);shared,job,fact=corrected()
    for name in ('document','facts'):setattr(w.project,name,getattr(shared.project,name))
    for name in ('annotations','undo_slots','edit_sessions','project_revision','document_revision','related_update_suggestions'):setattr(w,name,getattr(shared,name))
    w.project.revision=w.project_revision;w.related_update_suggestions[0].dependencies=result_dependencies(w,store.rules.load())
    intent=related(w);store.rules.save(store.rules.load().markdown+'\nChanged policy.',store.rules.load().revision)
    assert store.mutate(w.project_id,intent).rejection_reason=='RELATED_UPDATE_STALE'
    w.related_update_suggestions[0].dependencies=result_dependencies(w,store.rules.load());intent=related(w)
    assert store.mutate(w.project_id,intent).status=='applied'
    def unavailable():raise AssertionError('Replay must not read Rules')
    monkeypatch.setattr(store.rules,'load',unavailable)
    assert store.mutate(w.project_id,intent).status=='replayed' and p.calls==[]


def test_valid_assessment_clears_resolved_original_or_restore_conflicts_but_keeps_unrelated_marks():
    from packages.resume_core.models.recovery import Annotation
    from packages.resume_core.gui_reconciliation import GuiReconcileProposal,reconciliation_input
    import json
    w,job,fact=shared_claim();w.rules_used=RULES
    deps=result_dependencies(w,RULES)
    def mark(id,field):return Annotation(id=id,type='conflicting',code='restore_shared_fact_conflict',anchor={'kind':'field','fieldId':field,'range':None},
        dependencies=deps,factIds=[fact.id] if field==job.tasks.field_id else [],reason='An older mention remains.',evidence=[],resolved=False,updateSuggestionId=None,removedFocus=[])
    w.annotations=[mark('assessed',job.tasks.field_id),mark('unrelated','candidate/title')]
    edit(w,job.tasks.field_id,'Mentored three trainees',completion='field')
    payload=json.loads(reconciliation_input(w,[job.tasks.field_id],RULES))
    assert any(item['id']=='assessed' for item in payload['input']['annotations'])
    reply=GuiReconcileProposal(facts=[],fieldFacts=[{'fieldId':job.tasks.field_id,'factIds':[fact.id]}],annotations=[],suggestions=[],editorialPlan=None,recommendations=[])
    apply_reconciliation(w,[job.tasks.field_id],reply,result_dependencies(w,RULES),RULES,'')
    assert not any(item.id=='assessed' for item in w.annotations) and any(item.id=='unrelated' for item in w.annotations)


def test_original_source_conflict_fact_ids_reach_the_same_scoped_assessment_without_authored_claims():
    from tests.recovery.generation_fixtures import render_workspace
    from packages.resume_core.models.recovery import Annotation,GuiLeadershipFact
    from packages.resume_core.gui_reconciliation import reconciliation_input
    import json
    w=render_workspace('E2');w.rules_used=RULES;job=w.project.document.jobs[0]
    facts=[fact for fact in w.project.facts if isinstance(fact,GuiLeadershipFact)]
    w.annotations=[Annotation(id='source-conflict',type='conflicting',code='team_size_conflict',anchor={'kind':'field','fieldId':job.context.field_id,'range':None},
        dependencies=result_dependencies(w,RULES),factIds=[fact.id for fact in facts],reason='Two source claims remain.',evidence=[],resolved=False,updateSuggestionId=None,removedFocus=[])]
    edit(w,job.tasks.field_id,'Explicit team correction.',completion='field')
    payload=json.loads(reconciliation_input(w,[job.tasks.field_id],RULES))
    assert {fact.id for fact in facts} <= {fact['id'] for fact in payload['input']['facts']}
    assert payload['input']['annotations'][0]['id']=='source-conflict' and 'sources' not in payload['input']


def test_related_name_recipe_accepts_assessment_reference_without_changing_source_observation():
    from packages.resume_core.models.recovery import NameAssessmentFact
    w,job,fact=corrected();assessment=next(item for item in w.project.facts if isinstance(item,NameAssessmentFact))
    suggestion=w.related_update_suggestions[0]
    suggestion.replacements[0].field_id='candidate/name';suggestion.replacements[0].text='Supplied Fullname'
    suggestion.fact_ids=[assessment.id];observed=w.source_observed_at
    assert invoke(w,related(w)).status=='applied'
    assert w.project.document.candidate.name.fact_ids==[assessment.id] and w.source_observed_at==observed


def test_related_contact_replacement_keeps_other_text_and_normal_scope_guards():
    w,job,fact=corrected();suggestion=w.related_update_suggestions[0]
    before=w.project.document.jobs[0].tasks.text
    suggestion.replacements[0].text='Call 555-123-4567'
    result=invoke(w,related(w))
    assert result.status=='applied'
    assert w.project.document.profile.text.text=='Call 555-123-4567'
    assert w.project.document.jobs[0].tasks.text==before
