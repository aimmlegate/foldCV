"""Conflict authority and row order survive only through the shared transaction and the undo journal."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from packages.resume_core.models.template_mutations import TemplateMutationV1, TemplateOwnershipConflict, TemplateSyncWrite
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.rich_dependencies import dependencies_current, dependency
from packages.resume_core.rich_mutations import apply_rich_mutation, RichMutationFailure
from packages.resume_core.template_authoring import copy_blocks, move_occurrence_steps
from packages.resume_core.template_dependencies import selector
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_synchronization import live_sync_record, occurrence_blocks, row_hash
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_relation_transactions import related_workspace, owner_sections
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.test_transactions import authorization, request


def row(command, identifier='sync-a', *, block='block-paper-a', record='paper-a'):
    return TemplateSyncWrite(schemaVersion=2,id=identifier,status='conflict',actionId=command.action_id,
        blockIds=[block],fieldKeys=[],factIds=[record],dependencies=[],errorCode=None,kind='panel',
        ready=False,proposedSteps=[],capture=command.capture,ownershipConflict=None)


def put(command, value, existing=None, predecessor=None):
    payload=value.model_dump(by_alias=True);payload.pop('lifecycleId',None);payload['dependencies']=[]
    step={'kind':'put_template_sync','beforeHash':row_hash(existing),'record':payload}
    if existing is None:step['placement']={'afterSyncId':predecessor}
    return {**command.model_dump(by_alias=True),'steps':[*command.model_dump(by_alias=True)['steps'],step]}


def add(before, identifier='sync-a', *, predecessor=None, action=None):
    command=request(before,[{'kind':'remove_template_sync','syncId':'placeholder','beforeHash':'0'*64}],action or 'create-'+identifier)
    command.steps=[]
    return TemplateMutationV1.model_validate(put(command,row(command,identifier),predecessor=predecessor))


def replay(before, after, identifier='undo', direction='undo'):
    command=inverse_template_mutation(before,after,origin_action_id='original',mutation_id=identifier,
        session_id='current-session',action_token=7,kind=direction)
    return apply_rich_mutation(after,command,history_authorization=authorization(after,command))[0]


def test_engine_derives_final_dependencies_and_new_lifecycle_then_replay_is_exact():
    before,_=workspace();command=add(before)
    after,_=apply_rich_mutation(before,command);value=after.sync_records[0]
    assert value.lifecycle_id.startswith('sync-life-') and value.capture==command.capture
    assert dependencies_current(after,value.dependencies)
    assert dependency(after,'field',selector('sync',value.id)).fingerprint==row_hash(value)
    assert ('field',selector('sync',value.id)) not in {(item.kind,item.id) for item in value.dependencies}
    repeated,duplicate=apply_rich_mutation(after,command)
    assert duplicate and repeated==after
    undone=replay(before,after)
    assert not undone.sync_records
    redone=replay(after,undone,'redo','redo');restored=redone.sync_records[0]
    assert restored.lifecycle_id!=value.lifecycle_id and restored.capture.action_id=='redo'
    assert restored.action_id==value.action_id and dependencies_current(redone,restored.dependencies)
    assert restored.capture.action_token==7
    with pytest.raises(ValueError,match='stale'):
        live_sync_record(redone,value.id,row_hash(value),value.lifecycle_id)
    assert live_sync_record(redone,restored.id,row_hash(restored),restored.lifecycle_id)==restored


@pytest.mark.parametrize('damage',['hash','capture','origin','duplicate','predecessor','own_capture','lifecycle','dependencies'])
def test_invalid_sync_candidate_preserves_original_bytes(damage):
    before,_=workspace();command=add(before);raw=canonical(before)
    value=command.model_dump(by_alias=True);step=value['steps'][0]
    if damage=='hash':step['beforeHash']='0'*64;step.pop('placement')
    elif damage=='capture':step['record']['capture']['actionToken']+=1
    elif damage=='origin':step['record']['actionId']='another'
    elif damage=='duplicate':value['steps'].append(deepcopy(step))
    elif damage=='predecessor':step['placement']['afterSyncId']='missing'
    elif damage=='own_capture':step['record']['capture']=None
    elif damage=='lifecycle':step['record']['lifecycleId']='invented-authority'
    else:step['record']['dependencies']=[dependency(before,'record','paper-a').model_dump(by_alias=True)]
    with pytest.raises((ValueError,RichMutationFailure)):
        apply_rich_mutation(before,TemplateMutationV1.model_validate(value))
    assert canonical(before)==raw


def test_proposed_sync_cannot_recursively_store_sync_steps():
    before,_=workspace();command=add(before);value=command.model_dump(by_alias=True)
    value['steps'][0]['record']['proposedSteps']=[deepcopy(value['steps'][0])]
    with pytest.raises(ValidationError):TemplateMutationV1.model_validate(value)


def conflicted_move():
    value,sources=related_workspace();before=owner_sections(value)
    first=before.project.document.regions[2].blocks[0]
    copied=copy_blocks(before.project,[first.children[0]])[0];first.children.append(copied)
    steps,conflicts=move_occurrence_steps(before,'block-paper-a','owner-b')
    command=request(before,steps,'move-with-conflict');record=row(command)
    record.kind='conflict'
    record.block_ids=['block-paper-a',copied.id]
    groups=occurrence_blocks(before.project,'paper-a')
    record.ownership_conflict=TemplateOwnershipConflict.model_validate({'recordId':'paper-a','relationId':before.project.facts.relations[0].id,
        'beforeOwnerId':'employer-a','proposedOwnerId':'employer-b',
        'movedOccurrenceIds':sorted(groups.keys()-set(conflicts)),'remainingOccurrenceIds':conflicts})
    record=TemplateSyncWrite.model_validate(record.model_dump(by_alias=True))
    return before,sources,TemplateMutationV1.model_validate(put(command,record))


def test_owner_move_and_conflict_share_one_inverse_without_rewriting_other_copy():
    before,_sources,command=conflicted_move();copy=before.project.document.regions[2].blocks[0].children[-1]
    after,_=apply_rich_mutation(before,command)
    assert after.project.facts.relations[0].target_id=='employer-b' and after.sync_records[0].status=='conflict'
    assert after.project.document.regions[2].blocks[0].children[-1]==copy
    assert dependencies_current(after,after.sync_records[0].dependencies)
    original=replay(before,after)
    assert original.project.facts.relations[0].target_id=='employer-a' and not original.sync_records
    again=replay(after,original,'redo-conflict','redo')
    assert again.project.facts.relations[0].target_id=='employer-b'
    assert again.sync_records[0].lifecycle_id!=after.sync_records[0].lifecycle_id
    assert again.project.facts.observations==before.project.facts.observations


@pytest.mark.parametrize('damage',['owner','moved','remaining','blocks','destination'])
def test_conflict_payload_must_match_actual_atomic_ownership_and_occurrences(damage):
    before,_sources,command=conflicted_move();raw=canonical(before)
    step=command.steps[-1]
    if damage=='owner':step.record.ownership_conflict.before_owner_id='employer-b'
    elif damage=='moved':step.record.ownership_conflict.moved_occurrence_ids=['invented']
    elif damage=='remaining':step.record.ownership_conflict.remaining_occurrence_ids=['invented']
    elif damage=='blocks':step.record.block_ids=['block-paper-a']
    else:command.steps[0].parent_id='owner-a'
    with pytest.raises(RichMutationFailure):apply_rich_mutation(before,command)
    assert canonical(before)==raw


def test_existing_row_update_keeps_index_and_current_dependencies_follow_final_fact_revision():
    from packages.resume_core.template_facts import human_edit
    from tests.templates.test_transactions import extension_step
    before,_=workspace()
    for identifier,previous in [('first',None),('second','first')]:
        before,_=apply_rich_mutation(before,add(before,identifier,predecessor=previous))
    original=before.sync_records[0];facts=human_edit(before.project.facts,'paper-a','title','Exact current wording')
    command=request(before,[extension_step(before,facts.extensions[0])],'resolve-current')
    replacement=original.model_copy(deep=True);replacement.capture=command.capture.model_copy(deep=True)
    replacement.status='applied'
    command=TemplateMutationV1.model_validate(put(command,replacement,original))
    after,_=apply_rich_mutation(before,command)
    assert [value.id for value in after.sync_records]==['first','second']
    assert after.sync_records[-1]==before.sync_records[-1]
    assert after.sync_records[0].lifecycle_id!=original.lifecycle_id
    assert dependencies_current(after,after.sync_records[0].dependencies)
    assert not dependencies_current(after,original.dependencies)
    restored=replay(before,after)
    assert restored.sync_records[0].status=='conflict' and restored.sync_records[0].capture.action_id=='undo'
    assert dependencies_current(restored,restored.sync_records[0].dependencies)


def test_stale_existing_dependencies_cannot_be_refreshed_into_new_authority():
    from packages.resume_core.template_facts import human_edit
    from tests.templates.test_transactions import extension_step
    before,_=workspace();before,_=apply_rich_mutation(before,add(before));original=before.sync_records[0]
    facts=human_edit(before.project.facts,'paper-a','title','Later independent wording')
    current,_=apply_rich_mutation(before,request(before,[extension_step(before,facts.extensions[0])],'later-field-edit'))
    assert not dependencies_current(current,original.dependencies)
    command=add(current,'unused',action='stale-replacement')
    command.steps=[]
    replacement=original.model_copy(deep=True);replacement.capture=command.capture.model_copy(deep=True)
    replacement.status='applied';value=TemplateMutationV1.model_validate(put(command,replacement,original))
    raw=canonical(current)
    with pytest.raises(RichMutationFailure,match='STALE_MUTATION'):apply_rich_mutation(current,value)
    assert canonical(current)==raw


def test_existing_row_cannot_invent_an_ownership_conflict_without_the_move():
    before,_sources,unexecuted=conflicted_move()
    before,_=apply_rich_mutation(before,add(before))
    original=before.sync_records[0];command=add(before,'unused',action='invented-conflict');command.steps=[]
    replacement=unexecuted.steps[-1].record.model_copy(deep=True)
    replacement.id=original.id;replacement.action_id=original.action_id
    replacement.capture=command.capture.model_copy(deep=True)
    value=TemplateMutationV1.model_validate(put(command,replacement,original));raw=canonical(before)
    with pytest.raises(RichMutationFailure,match='STALE_MUTATION'):apply_rich_mutation(before,value)
    assert canonical(before)==raw


def test_ordinary_creation_cannot_insert_before_existing_rows_but_history_can():
    before,_=workspace();before,_=apply_rich_mutation(before,add(before));raw=canonical(before)
    with pytest.raises(RichMutationFailure,match='STALE_MUTATION'):apply_rich_mutation(before,add(before,'new-first'))
    assert canonical(before)==raw


def test_grouped_removal_in_one_action_undo_redo_preserves_original_order(tmp_path):
    before,sources=workspace()
    for identifier,previous in [('a',None),('b','a'),('c','b')]:
        before,_=apply_rich_mutation(before,add(before,identifier,predecessor=previous))
    editor=TemplateEditor(tmp_path,before,sources)
    for index in [1,2]:
        current=editor.current();value=current.sync_records[0]
        command=request(current,[{'kind':'remove_template_sync','syncId':value.id,'beforeHash':row_hash(value)}],
            'grouped-remove-'+str(index))
        command.action_id=command.capture.action_id='remove-siblings'
        editor.commit(command)
    assert [action.action_id for action in editor.session().journal.undo]==['remove-siblings']
    editor.undo('undo-grouped-removal',expected='remove-siblings')
    assert editor.current().sync_records==before.sync_records
    editor.redo('redo-grouped-removal',expected='remove-siblings')
    assert [value.id for value in editor.current().sync_records]==['c']
    assert editor.current().sync_records[0]==before.sync_records[2]


def order_aba():
    before,sources=workspace()
    for identifier,previous in [('a',None),('b','a'),('c','b')]:
        before,_=apply_rich_mutation(before,add(before,identifier,predecessor=previous))
    original=before.sync_records[1]
    removed=request(before,[{'kind':'remove_template_sync','syncId':'b','beforeHash':row_hash(original)}],'remove-b')
    middle,_=apply_rich_mutation(before,removed)
    after,_=apply_rich_mutation(middle,add(middle,'b',predecessor='c',action='recreate-b'))
    return before,sources,middle,after


@pytest.mark.parametrize('damage',['ordinary','before_predecessor','destination'])
def test_history_reposition_needs_exact_authorization_and_both_predecessors(damage):
    target,_sources,_middle,after=order_aba()
    command=inverse_template_mutation(target,after,origin_action_id='group',mutation_id='undo-order-guard',
        session_id='session',action_token=3)
    moved=next(step for step in command.steps if step.kind=='put_template_sync' and step.history_placement is not None)
    if damage=='ordinary':
        command.kind='typing';command.history.kind='edit';command.history.origin_action_id=None
        for step in command.steps:
            if step.kind=='put_template_sync':
                existing=next(value for value in after.sync_records if value.id==step.record.id)
                step.record.lifecycle_id=None;step.record.dependencies=[]
                step.record.action_id=existing.action_id
                step.record.capture=command.capture.model_copy(deep=True)
    elif damage=='before_predecessor':moved.history_placement.before_after_sync_id='missing-original'
    else:moved.history_placement.after_sync_id='missing-destination'
    raw=canonical(after)
    with pytest.raises(RichMutationFailure,match='STALE_MUTATION'):
        apply_rich_mutation(after,command,history_authorization=authorization(after,command))
    assert canonical(after)==raw


def test_delete_and_recreate_in_one_action_undo_redo_restore_both_row_orders(tmp_path):
    before,sources,_middle,_after=order_aba();editor=TemplateEditor(tmp_path,before,sources)
    for index in [1,2]:
        current=editor.current()
        if index==1:
            value=current.sync_records[1]
            command=request(current,[{'kind':'remove_template_sync','syncId':'b','beforeHash':row_hash(value)}],'remove-b-for-recreate')
        else:command=add(current,'b',predecessor='c',action='recreate-b-for-group')
        command.action_id=command.capture.action_id='same-group'
        if index==2:
            command.steps[0].record.action_id=command.action_id
            command.steps[0].record.capture=command.capture.model_copy(deep=True)
        editor.commit(command)
    saved=editor.current()
    assert [value.id for value in saved.sync_records]==['a','c','b']
    editor.undo('undo-order-aba',expected='same-group')
    assert editor.current().sync_records==before.sync_records
    editor.redo('redo-order-aba',expected='same-group')
    assert editor.current().sync_records==saved.sync_records


def test_archive_import_also_clears_crafted_foreign_capture_and_pending_authority():
    from packages.resume_core.archive_zip import read_zip,write_zip,parse_json,json_bytes,digest
    before,sources=workspace();current,_=apply_rich_mutation(before,add(before))
    source=current.sync_records[0];source.status='pending';source.ready=True
    files=read_zip(write_zip(archive_payload_v7(current,sources,{})))
    wire=parse_json(files['workspace.json'])
    assert wire['syncRecords'][0]['capture'] is None and wire['syncRecords'][0]['status']=='stale'
    wire['syncRecords'][0]=source.model_dump(mode='json',by_alias=True)
    files['workspace.json']=json_bytes(wire);manifest=parse_json(files['manifest.json'])
    entry=next(value for value in manifest['entries'] if value['path']=='workspace.json')
    entry['sha256']=digest(files['workspace.json']);entry['size']=len(files['workspace.json'])
    files['manifest.json']=json_bytes(manifest)
    imported,_,_,_=open_archive_v7(write_zip(files),'crafted-sync')
    inert=imported.sync_records[0]
    assert inert.capture is None and not inert.dependencies and not inert.ready
    assert not inert.proposed_steps and inert.status=='stale' and inert.error_code=='OPERATION_INTERRUPTED'
    assert current.sync_records[0].capture is not None and current.sync_records[0].ready


def replace_sync_command(current,identifier='action-b',status='applied'):
    original=next(row for row in current.sync_records if row.id=='sync-a')
    command=add(current,'unused',action=identifier);command.steps=[]
    value=original.model_copy(deep=True);value.status=status;value.capture=command.capture.model_copy(deep=True)
    return TemplateMutationV1.model_validate(put(command,value,original))


@pytest.mark.parametrize('unrelated',[False,True])
def test_adjacent_actions_on_one_row_undo_and_redo_in_stack_order_exactly(tmp_path,unrelated):
    before,sources=workspace();editor=TemplateEditor(tmp_path,before,sources)
    editor.commit(add(editor.current(),action='action-a'));a=editor.current()
    if unrelated:
        editor.commit(add(editor.current(),'unrelated',predecessor='sync-a',action='action-u'))
    editor.commit(replace_sync_command(editor.current()));b=editor.current()
    assert b.sync_records[0].status=='applied'
    editor.undo('undo-b',expected='action-b')
    assert editor.current().sync_records[0]==a.sync_records[0]
    if unrelated:
        editor.undo('undo-u',expected='action-u')
    editor.undo('undo-a',expected='action-a')
    assert not editor.current().sync_records
    editor.redo('redo-a',expected='action-a')
    assert editor.current().sync_records==a.sync_records
    if unrelated:
        editor.redo('redo-u',expected='action-u')
    editor.redo('redo-b',expected='action-b')
    assert editor.current().sync_records==b.sync_records
    assert [row.id for row in editor.current().sync_records]==(['sync-a','unrelated'] if unrelated else ['sync-a'])


def test_conflicted_move_undo_redo_reopen_and_archive_keep_conflict_authority(tmp_path):
    before,sources,command=conflicted_move();editor=TemplateEditor(tmp_path,before,sources)
    editor.commit(command);saved=editor.current()
    editor.undo('undo-conflict',expected=command.action_id)
    undone=editor.current()
    assert not undone.sync_records and undone.project.facts.relations[0].target_id=='employer-a'
    editor.redo('redo-conflict',expected=command.action_id)
    current=editor.reopen();record=current.sync_records[0]
    assert current.sync_records==saved.sync_records and record.status=='conflict'
    assert current.project.facts.relations[0].target_id=='employer-b'
    archive=write_zip(archive_payload_v7(current,sources,{}));assert current.sync_records[0].capture is not None
    opened,retained,_,_=open_archive_v7(archive,'sync-copy')
    assert retained==sources and opened.sync_records[0].capture is None
    assert opened.sync_records[0].ownership_conflict==record.ownership_conflict
    assert opened.sync_records[0].status=='conflict' and not opened.sync_records[0].dependencies
    with pytest.raises(ValueError,match='stale'):live_sync_record(opened,record.id,row_hash(opened.sync_records[0]),record.lifecycle_id)
