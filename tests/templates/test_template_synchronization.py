"""Conflict authority and row order survive only through the shared transaction."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_document import PresentedText, TemplateParagraphBlock
from packages.resume_core.models.template_mutations import TemplateMutationV1, TemplateOwnershipConflict, TemplateSyncWrite
from packages.resume_core.models.template_writer import WriterMutationV2
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_dependencies import dependencies_current, dependency
from packages.resume_core.rich_mutations import apply_rich_mutation, RichMutationFailure
from packages.resume_core.template_authoring import copy_blocks, move_occurrence_steps
from packages.resume_core.template_dependencies import selector
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_local_history import TemplateLocalHistory, changes, merge_changes, restore
from packages.resume_core.template_synchronization import live_sync_record, occurrence_blocks, row_hash
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_relation_transactions import related_workspace, owner_sections
from tests.templates.test_template_local_history import history_request
from tests.templates.test_template_writers import TemplateWriterFixture
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


def test_scoped_row_removal_restores_predecessors_before_unrelated_later_rows():
    before,_=workspace()
    for identifier,previous in [('z-first',None),('a-second','z-first'),('m-third','a-second')]:
        before,_=apply_rich_mutation(before,add(before,identifier,predecessor=previous))
    command=request(before,[{'kind':'remove_template_sync','syncId':value.id,'beforeHash':row_hash(value)}
        for value in before.sync_records[1:]],'remove-two')
    after,_=apply_rich_mutation(before,command);delta=changes(before,after)
    assert {key for key in delta if key[0]=='sync_placement'}=={('sync_placement','a-second'),('sync_placement','m-third')}
    later,_=apply_rich_mutation(after,add(after,'unrelated',predecessor='z-first'))
    target=restore(later,delta)
    restored=replay(target,later)
    assert [value.id for value in restored.sync_records]==['z-first','a-second','m-third','unrelated']
    assert restored.sync_records[-1]==later.sync_records[-1]
    assert restored.sync_records[1].lifecycle_id!=before.sync_records[1].lifecycle_id
    removed,_=apply_rich_mutation(later,request(later,[{'kind':'remove_template_sync','syncId':'z-first',
        'beforeHash':row_hash(later.sync_records[0])}],'remove-predecessor'))
    with pytest.raises(BackgroundFailure,match='DEPENDENCY_CHANGED'):restore(removed,delta)


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


def test_grouped_removals_keep_the_earliest_predecessor_chain():
    before,_=workspace()
    for identifier,previous in [('a',None),('b','a'),('c','b')]:
        before,_=apply_rich_mutation(before,add(before,identifier,predecessor=previous))
    def remove_first(current,identifier):
        value=current.sync_records[0]
        return apply_rich_mutation(current,request(current,[{'kind':'remove_template_sync',
            'syncId':value.id,'beforeHash':row_hash(value)}],identifier))[0]
    middle=remove_first(before,'remove-a');after=remove_first(middle,'remove-b')
    composed=merge_changes(changes(before,middle),changes(middle,after),middle,after)
    assert [value.id for value in restore(after,composed).sync_records]==['a','b','c']
    later,_=apply_rich_mutation(after,add(after,'unrelated',predecessor='c'))
    assert [value.id for value in restore(later,composed).sync_records]==['a','b','c','unrelated']


def test_actual_writer_grouped_removal_undo_redo_preserves_original_order(tmp_path):
    before,sources=workspace()
    for identifier,previous in [('a',None),('b','a'),('c','b')]:
        before,_=apply_rich_mutation(before,add(before,identifier,predecessor=previous))
    fixture=TemplateWriterFixture(tmp_path,before,sources)
    for cursor in [1,2]:
        current=fixture.current();value=current.sync_records[0]
        command=request(current,[{'kind':'remove_template_sync','syncId':value.id,'beforeHash':row_hash(value)}],
            'grouped-remove-'+str(cursor))
        command.action_id=command.capture.action_id='remove-siblings'
        command.capture.session_id=fixture.proof.session_id;command.capture.action_token=cursor
        wrapped=WriterMutationV2(**fixture.advance_request(cursor,[{'cursor':cursor,'mutation':command}]).model_dump(by_alias=True),mutation=command)
        saved=fixture.writers.save(fixture.project,wrapped,originals=fixture.originals)
    assert saved.local_history_ack.action_id=='remove-siblings' and saved.local_history_ack.generation==2
    undone=fixture.writers.local_history_command(fixture.project,history_request(fixture,saved.local_history_ack),originals=fixture.originals)
    assert [value.id for value in undone.workspace.sync_records]==['a','b','c']
    redone=fixture.writers.local_history_command(fixture.project,history_request(fixture,undone.local_history_ack,'redo','redo-ordered-removal'),originals=fixture.originals)
    assert [value.id for value in redone.workspace.sync_records]==['c']
    assert redone.workspace.sync_records[0]==before.sync_records[2]


def order_aba():
    before,sources=workspace()
    for identifier,previous in [('a',None),('b','a'),('c','b')]:
        before,_=apply_rich_mutation(before,add(before,identifier,predecessor=previous))
    original=before.sync_records[1]
    removed=request(before,[{'kind':'remove_template_sync','syncId':'b','beforeHash':row_hash(original)}],'remove-b')
    middle,_=apply_rich_mutation(before,removed)
    after,_=apply_rich_mutation(middle,add(middle,'b',predecessor='c',action='recreate-b'))
    delta=merge_changes(changes(before,middle),changes(middle,after),middle,after)
    return before,sources,middle,after,delta


def test_reintroduced_existing_id_restores_position_and_preserves_unrelated_later_rows():
    before,_sources,_middle,after,delta=order_aba()
    later,_=apply_rich_mutation(after,add(after,'unrelated',predecessor='b'))
    target=restore(later,delta)
    assert [value.id for value in target.sync_records]==['a','b','c','unrelated']
    restored=replay(target,later)
    assert [value.id for value in restored.sync_records]==['a','b','c','unrelated']
    assert restored.sync_records[-1]==later.sync_records[-1]
    assert restored.sync_records[1].action_id==before.sync_records[1].action_id
    redone=replay(later,restored,'redo-order-aba','redo')
    assert [value.id for value in redone.sync_records]==['a','c','b','unrelated']
    assert redone.sync_records[-1]==later.sync_records[-1]
    assert redone.sync_records[1]==before.sync_records[2]
    assert redone.sync_records[2].lifecycle_id!=after.sync_records[-1].lifecycle_id


@pytest.mark.parametrize('damage',['ordinary','before_predecessor','destination'])
def test_history_reposition_needs_exact_authorization_and_both_predecessors(damage):
    _before,_sources,_middle,after,delta=order_aba();target=restore(after,delta)
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


@pytest.mark.parametrize('cut',[False,True])
def test_actual_writer_delete_recreate_order_undo_redo_and_failed_save_are_atomic(tmp_path,cut):
    before,sources,_middle,_after,_delta=order_aba();fixture=TemplateWriterFixture(tmp_path,before,sources)
    for cursor in [1,2]:
        current=fixture.current()
        if cursor==1:
            value=current.sync_records[1]
            command=request(current,[{'kind':'remove_template_sync','syncId':'b','beforeHash':row_hash(value)}],'remove-b-for-recreate')
        else:command=add(current,'b',predecessor='c',action='recreate-b-for-group')
        command.action_id=command.capture.action_id='same-group'
        command.capture.session_id=fixture.proof.session_id;command.capture.action_token=cursor
        if cursor==2:
            command.steps[0].record.action_id=command.action_id
            command.steps[0].record.capture=command.capture.model_copy(deep=True)
        wrapped=WriterMutationV2(**fixture.advance_request(cursor,[{'cursor':cursor,'mutation':command}]).model_dump(by_alias=True),mutation=command)
        saved=fixture.writers.save(fixture.project,wrapped,originals=fixture.originals)
    assert [value.id for value in saved.workspace.sync_records]==['a','c','b']
    command=history_request(fixture,saved.local_history_ack,identifier='undo-order-aba')
    if cut:
        def interrupt(name,_project):
            if name=='before_workspace_replaced':raise SystemExit('controlled history position cut')
        fixture.publisher.observer=interrupt;raw=canonical(fixture.current())
        with pytest.raises(SystemExit,match='position cut'):
            fixture.writers.local_history_command(fixture.project,command,originals=fixture.originals)
        fixture.publisher.observer=lambda *_args:None;fixture.publisher.recover(fixture.project)
        assert canonical(fixture.current())==raw
        command=history_request(fixture,saved.local_history_ack,identifier='undo-order-after-cut')
    undone=fixture.writers.local_history_command(fixture.project,command,originals=fixture.originals)
    assert [value.id for value in undone.workspace.sync_records]==['a','b','c']
    redone=fixture.writers.local_history_command(fixture.project,
        history_request(fixture,undone.local_history_ack,'redo','redo-order-aba'),originals=fixture.originals)
    assert [value.id for value in redone.workspace.sync_records]==['a','c','b']
    assert redone.workspace.sync_records[-1].lifecycle_id!=saved.workspace.sync_records[-1].lifecycle_id


def test_archive_import_also_clears_crafted_foreign_capture_and_pending_authority():
    from packages.resume_core.gui_archive_zip import read_zip,write_zip,parse_json,json_bytes,digest
    before,sources=workspace();current,_=apply_rich_mutation(before,add(before))
    source=current.sync_records[0];source.status='pending';source.ready=True
    files=read_zip(export_rich_archive(current,sources,{},{}))
    wire=parse_json(files['workspace.json'])
    assert wire['syncRecords'][0]['capture'] is None and wire['syncRecords'][0]['status']=='stale'
    wire['syncRecords'][0]=source.model_dump(mode='json',by_alias=True)
    files['workspace.json']=json_bytes(wire);manifest=parse_json(files['manifest.json'])
    entry=next(value for value in manifest['entries'] if value['path']=='workspace.json')
    entry['sha256']=digest(files['workspace.json']);entry['size']=len(files['workspace.json'])
    files['manifest.json']=json_bytes(manifest)
    imported,_,_,_=open_rich_archive(write_zip(files),'crafted-sync')
    inert=imported.sync_records[0]
    assert inert.capture is None and not inert.dependencies and not inert.ready
    assert not inert.proposed_steps and inert.status=='stale' and inert.error_code=='OPERATION_INTERRUPTED'
    assert current.sync_records[0].capture is not None and current.sync_records[0].ready


def save_sync_command(fixture,command):
    command.capture.session_id=fixture.proof.session_id
    for step in command.steps:
        if step.kind=='put_template_sync':step.record.capture=command.capture.model_copy(deep=True)
    cursor=fixture.jobs.load(fixture.project).writer.acknowledged_cursor+1
    wrapped=WriterMutationV2(**fixture.advance_request(cursor,[{'cursor':cursor,'mutation':command}]).model_dump(by_alias=True),mutation=command)
    return fixture.writers.save(fixture.project,wrapped,originals=fixture.originals)


def replace_sync_command(current,identifier='action-b',status='applied'):
    original=next(row for row in current.sync_records if row.id=='sync-a')
    command=add(current,'unused',action=identifier);command.steps=[]
    value=original.model_copy(deep=True);value.status=status;value.capture=command.capture.model_copy(deep=True)
    return TemplateMutationV1.model_validate(put(command,value,original))


@pytest.mark.parametrize('unrelated',[False,True])
def test_adjacent_action_undo_redo_chain_rebinds_only_own_replayed_authority(tmp_path,unrelated):
    before,sources=workspace();fixture=TemplateWriterFixture(tmp_path,before,sources)
    a=save_sync_command(fixture,add(fixture.current(),action='action-a'))
    if unrelated:
        u=save_sync_command(fixture,add(fixture.current(),'unrelated',predecessor='sync-a',action='action-u'))
    b=save_sync_command(fixture,replace_sync_command(fixture.current()))
    command=history_request(fixture,b.local_history_ack,identifier='undo-b')
    undone_b=fixture.writers.local_history_command(fixture.project,command,originals=fixture.originals)
    normalized=fixture.current().sync_records[0]
    opening=fixture.writers.local_history.openings[fixture.project]
    prior=next(action for action in opening.actions if action.identifier=='action-a')
    assert prior.delta[('sync','sync-a')][1]==normalized.model_dump(mode='json',by_alias=True)
    if unrelated:
        undone_u=fixture.writers.local_history_command(fixture.project,history_request(fixture,u.local_history_ack,identifier='undo-u'),originals=fixture.originals)
    undone_a=fixture.writers.local_history_command(fixture.project,history_request(fixture,a.local_history_ack,identifier='undo-a'),originals=fixture.originals)
    assert not undone_a.workspace.sync_records
    redone_a=fixture.writers.local_history_command(fixture.project,history_request(fixture,undone_a.local_history_ack,'redo','redo-a'),originals=fixture.originals)
    if unrelated:
        fixture.writers.local_history_command(fixture.project,history_request(fixture,undone_u.local_history_ack,'redo','redo-u'),originals=fixture.originals)
    redone_b=fixture.writers.local_history_command(fixture.project,history_request(fixture,undone_b.local_history_ack,'redo','redo-b'),originals=fixture.originals)
    assert redone_b.workspace.sync_records[0].status=='applied'
    assert redone_b.workspace.sync_records[0].capture.action_id=='redo-b'
    assert redone_b.workspace.sync_records[0].lifecycle_id not in {
        a.workspace.sync_records[0].lifecycle_id,b.workspace.sync_records[0].lifecycle_id,normalized.lifecycle_id,
        redone_a.workspace.sync_records[0].lifecycle_id}
    assert [row.id for row in redone_b.workspace.sync_records]==(['sync-a','unrelated'] if unrelated else ['sync-a'])


@pytest.mark.parametrize('status',['conflict','failed'])
def test_external_equal_or_changed_payload_authority_never_rebases_history(tmp_path,status):
    before,sources=workspace();fixture=TemplateWriterFixture(tmp_path,before,sources)
    a=save_sync_command(fixture,add(fixture.current(),action='action-a'))
    b=save_sync_command(fixture,replace_sync_command(fixture.current()))
    fixture.writers.local_history_command(fixture.project,history_request(fixture,b.local_history_ack,identifier='undo-b'),originals=fixture.originals)
    opening=fixture.writers.local_history.openings[fixture.project]
    expected=deepcopy(next(action for action in opening.actions if action.identifier=='action-a').delta[('sync','sync-a')][1])
    external=replace_sync_command(fixture.current(),'external',status)
    fixture.publisher.manual(fixture.project,external,originals=fixture.originals)
    raw=canonical(fixture.current())
    with pytest.raises(BackgroundFailure,match='DEPENDENCY_CHANGED'):
        fixture.writers.local_history_command(fixture.project,history_request(fixture,a.local_history_ack,identifier='stale-undo-a'),originals=fixture.originals)
    assert canonical(fixture.current())==raw
    assert next(action for action in opening.actions if action.identifier=='action-a').delta[('sync','sync-a')][1]==expected


def test_receipt_interruption_reconciles_authority_rebase_before_the_next_undo(tmp_path):
    before,sources=workspace();fixture=TemplateWriterFixture(tmp_path,before,sources)
    a=save_sync_command(fixture,add(fixture.current(),action='action-a'))
    b=save_sync_command(fixture,replace_sync_command(fixture.current()))
    command=history_request(fixture,b.local_history_ack,identifier='undo-b-cut')
    def interrupt(name,_project):
        if name=='before_local_history_receipt':raise SystemExit('controlled registry receipt cut')
    fixture.writers.observer=interrupt
    with pytest.raises(SystemExit,match='registry receipt cut'):
        fixture.writers.local_history_command(fixture.project,command,originals=fixture.originals)
    fixture.writers.observer=lambda *_args:None
    replayed=fixture.writers.local_history_command(fixture.project,command,originals=fixture.originals)
    assert replayed.replayed and replayed.workspace.sync_records[0].status=='conflict'
    undone_a=fixture.writers.local_history_command(fixture.project,history_request(fixture,a.local_history_ack,identifier='undo-a-after-cut'),originals=fixture.originals)
    assert not undone_a.workspace.sync_records


def test_coalesced_inverse_envelope_rejects_before_intent_and_preserves_last_replayable_action(tmp_path):
    before,sources=workspace();fixture=TemplateWriterFixture(tmp_path,before,sources)
    def insert(value,identifier):
        region=fixture.current().project.document.regions[2]
        block=TemplateParagraphBlock(type='paragraph',id=identifier,revision=1,props={},children=[],provenance=[],
            presentation=region.blocks[0].presentation.model_copy(deep=True),
            content=[PresentedText(type='text',text=value,styles={})])
        return {'kind':'put_block','parentId':region.id,'afterId':region.blocks[-1].id,'beforeRevision':None,
            'block':block.model_dump(by_alias=True),'keepChildren':False}
    command=add(fixture.current(),action='a').model_dump(by_alias=True)
    command['steps'].append(insert('x'*4000,'first-payload-block'))
    first=save_sync_command(fixture,TemplateMutationV1.model_validate(command))
    current=fixture.current()
    command=request(current,[insert('','second-payload-block')],'continue-a')
    command.action_id=command.capture.action_id='a';command.capture.action_token=2
    command.capture.session_id=fixture.proof.session_id
    virtual,_=apply_rich_mutation(current,command)
    registry=fixture.writers.local_history;opening=registry.openings[fixture.project]
    hypothetical=merge_changes(opening.actions[0].delta,changes(current,virtual),current,virtual)
    target=LIMITS.inverse_bytes-10
    command.steps[0].block.content[0].text='x'*(target-len(canonical(registry.delta_wire(hypothetical))))
    cursor=fixture.jobs.load(fixture.project).writer.acknowledged_cursor+1
    wrapped=WriterMutationV2(**fixture.advance_request(cursor,[{'cursor':cursor,'mutation':command}]).model_dump(by_alias=True),mutation=command)
    fixture.writers.flush(fixture.project,wrapped)
    retained=deepcopy(opening);raw=canonical(fixture.current())
    intent_ids={intent.id for intent in fixture.jobs.load(fixture.project).manual_intents}
    with pytest.raises(BackgroundFailure,match='JOB_STORAGE_FULL'):
        fixture.writers.save(fixture.project,wrapped,originals=fixture.originals)
    assert canonical(fixture.current())==raw
    assert registry.openings[fixture.project]==retained
    intents=fixture.jobs.load(fixture.project).manual_intents
    assert {intent.id for intent in intents}<=intent_ids
    assert all(intent.client_mutation_id!=command.client_mutation_id for intent in intents)
    undone=fixture.writers.local_history_command(fixture.project,
        history_request(fixture,first.local_history_ack,identifier='undo-last-accepted'),originals=fixture.originals)
    assert not undone.workspace.sync_records
    assert not {'first-payload-block','second-payload-block'} & {block.id for block in undone.workspace.project.document.blocks()}
    redone=fixture.writers.local_history_command(fixture.project,
        history_request(fixture,undone.local_history_ack,'redo','redo-last-accepted'),originals=fixture.originals)
    assert 'first-payload-block' in {block.id for block in redone.workspace.project.document.blocks()}
    assert 'second-payload-block' not in {block.id for block in redone.workspace.project.document.blocks()}


def test_rebased_inverse_budget_rejects_before_intent_and_preserves_prior_history(tmp_path):
    before,sources=workspace();block=before.project.document.regions[2].blocks[0]
    block.content=[PresentedText(type='text',text='x'*250000,styles={})]
    fixture=TemplateWriterFixture(tmp_path,before,sources)
    command=add(fixture.current(),action='a').model_dump(by_alias=True)
    command['steps'].append({'kind':'replace_inline_range','blockId':block.id,'beforeRevision':block.revision,
        'cellId':None,'field':'content','start':0,'end':250000,'content':[{'type':'text','text':'','styles':{}}]})
    command=TemplateMutationV1.model_validate(command)
    command.capture.session_id=fixture.proof.session_id
    command.steps[0].record.capture=command.capture.model_copy(deep=True)
    virtual,_=apply_rich_mutation(before,command)
    registry=fixture.writers.local_history;target=LIMITS.inverse_bytes-10
    command.steps[1].content[0].text='y'*(target-len(canonical(registry.delta_wire(changes(before,virtual)))))
    virtual,_=apply_rich_mutation(before,command)
    measured=len(canonical(registry.delta_wire(changes(before,virtual))))
    command.steps[1].content[0].text+='y'*(target-measured) if measured<target else ''
    if measured>target:command.steps[1].content[0].text=command.steps[1].content[0].text[:target-measured]
    a=save_sync_command(fixture,command)
    b=save_sync_command(fixture,replace_sync_command(fixture.current(),'b'))
    opening=registry.openings[fixture.project]
    assert len(canonical(registry.delta_wire(opening.actions[0].delta)))==target
    retained=deepcopy(opening);raw=canonical(fixture.current())
    intent_ids={intent.id for intent in fixture.jobs.load(fixture.project).manual_intents}
    command=history_request(fixture,b.local_history_ack,identifier='u'*200)
    with pytest.raises(BackgroundFailure,match='JOB_STORAGE_FULL'):
        fixture.writers.local_history_command(fixture.project,command,originals=fixture.originals)
    assert canonical(fixture.current())==raw and registry.openings[fixture.project]==retained
    intents=fixture.jobs.load(fixture.project).manual_intents
    assert {intent.id for intent in intents}<=intent_ids
    assert all(intent.client_mutation_id!=command.client_mutation_id for intent in intents)
    fixture.writers.local_history_command(fixture.project,
        history_request(fixture,b.local_history_ack,identifier='u'),originals=fixture.originals)
    undone=fixture.writers.local_history_command(fixture.project,
        history_request(fixture,a.local_history_ack,identifier='undo-a-budget'),originals=fixture.originals)
    assert not undone.workspace.sync_records
    assert undone.workspace.project.document.regions[2].blocks[0].content[0].text=='x'*250000


def test_actual_writer_save_failure_undo_redo_reopen_and_archive_authority(tmp_path):
    before,sources,command=conflicted_move();fixture=TemplateWriterFixture(tmp_path,before,sources)
    command.capture.session_id=fixture.proof.session_id;command.steps[-1].record.capture=command.capture.model_copy(deep=True)
    wrapped=WriterMutationV2(**fixture.advance_request(1,[{'cursor':1,'mutation':command}]).model_dump(by_alias=True),mutation=command)
    def interrupt(name,_project):
        if name=='before_workspace_replaced':raise SystemExit('controlled sync save failure')
    fixture.publisher.observer=interrupt
    with pytest.raises(SystemExit,match='controlled sync'):fixture.writers.save(fixture.project,wrapped,originals=fixture.originals)
    fixture.publisher.observer=lambda *_args:None;fixture.publisher.recover(fixture.project)
    assert canonical(fixture.current())==canonical(before)
    # Recovery retains the failed request outcome; retry the user action with a new mutation ID.
    command.client_mutation_id='retry-conflict-save'
    cursor=fixture.jobs.load(fixture.project).writer.acknowledged_cursor+1
    wrapped=WriterMutationV2(**fixture.advance_request(cursor,[{'cursor':cursor,'mutation':command}]).model_dump(by_alias=True),mutation=command)
    saved=fixture.writers.save(fixture.project,wrapped,originals=fixture.originals)
    undone=fixture.writers.local_history_command(fixture.project,history_request(fixture,saved.local_history_ack),originals=fixture.originals)
    assert not undone.workspace.sync_records and undone.workspace.project.facts.relations[0].target_id=='employer-a'
    redone=fixture.writers.local_history_command(fixture.project,history_request(fixture,undone.local_history_ack,'redo','redo-conflict'),originals=fixture.originals)
    current=fixture.current();record=current.sync_records[0]
    assert current==redone.workspace and record.capture.action_id=='redo-conflict'
    assert record.lifecycle_id!=saved.workspace.sync_records[0].lifecycle_id and record.status=='conflict'
    archive=export_rich_archive(current,sources,{},{});assert current.sync_records[0].capture is not None
    opened,retained,_,_=open_rich_archive(archive,'sync-copy')
    assert retained==sources and opened.sync_records[0].capture is None
    assert opened.sync_records[0].ownership_conflict==record.ownership_conflict
    assert opened.sync_records[0].status=='conflict' and not opened.sync_records[0].dependencies
    with pytest.raises(ValueError,match='stale'):live_sync_record(opened,record.id,row_hash(opened.sync_records[0]),record.lifecycle_id)
