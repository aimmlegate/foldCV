"""Prepared ownership conflicts retain existing explicit resolution behavior."""

import pytest

from packages.resume_core.agent_edits import semantic
from packages.resume_core.models.template_document import BoundLink,FieldOccurrence,FieldRef,PresentedText
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_writer import WriterPrepareEditV2
from packages.resume_core.rich_archive import export_rich_archive,open_rich_archive
from packages.resume_core.rich_dependencies import dependencies_current
from packages.resume_core.rich_mutations import apply_rich_mutation,RichMutationFailure
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.template_synchronization import occurrence_blocks,row_hash
from packages.resume_core.templates.compiler import canonical
from tests.templates.test_compact_save import compact_command
from tests.templates.test_structural_preparation import intent,selection,place
from tests.templates.test_template_local_history import history_request
from tests.templates.test_template_preparation import proof,response
from tests.templates.test_template_synchronization import add,conflicted_move
from tests.templates.test_template_writers import TemplateWriterFixture
from tests.templates.test_transactions import issue,request as mutation_request


def move_request(before):
    block=next(value for value in before.project.document.blocks() if value.id=='block-paper-a')
    return intent(before,'move_block',**selection(block),placement=place(parent='owner-b'))


def resolve_request(before,source=None):
    source=source or before.sync_records[-1]
    return intent(before,'resolve_template_sync',syncId=source.id,beforeRecordHash=row_hash(source),
        beforeLifecycleId=source.lifecycle_id)


def moved():
    before,sources,_command=conflicted_move()
    prepared=prepare_edit(response(before),move_request(before),proof())
    return before,sources,prepared


def link_mentions(before):
    for block in before.project.document.blocks():
        for index,part in enumerate(block.content if isinstance(block.content,list) else []):
            if isinstance(part,FieldOccurrence) and part.record_id=='paper-a':
                block.content[index]=BoundLink(type='bound_link',href='https://example.com/paper',
                    content=[PresentedText(type='text',text=part.text,styles=part.styles,presentation=part.presentation)],
                    labelBinding=FieldRef(recordId=part.record_id,fieldKey=part.field_key,cellId=part.cell_id,
                        occurrenceId=part.occurrence_id),urlBinding=None,presentation=part.presentation)


def test_link_only_mentions_create_the_same_explicit_ownership_conflict():
    before,_sources,_command=conflicted_move();link_mentions(before)
    groups=occurrence_blocks(before.project,'paper-a');assert len(groups)==2
    result=prepare_edit(response(before),move_request(before),proof()).preview.workspace
    assert result.project.facts.relations[0].target_id=='employer-b'
    assert len(result.sync_records)==1
    conflict=result.sync_records[0].ownership_conflict
    assert set(conflict.moved_occurrence_ids+conflict.remaining_occurrence_ids)==groups.keys()
    assert len(conflict.moved_occurrence_ids)==len(conflict.remaining_occurrence_ids)==1
    assert set(result.sync_records[0].block_ids)==set().union(*groups.values())
    assert occurrence_blocks(result.project,'paper-a')==groups


def test_prepared_move_reports_actual_lifecycles_preserves_other_mentions_and_retires_owned_issues():
    before,_sources,_command=conflicted_move()
    relation=before.project.facts.relations[0]
    before.project.import_issues=[issue('subject-owner','paper-a'),issue('relation-owner',relation.id),issue('unrelated','paper-b')]
    before.project.import_issues[1].block_ids=['block-paper-a']
    raw=canonical(before);request=move_request(before)
    result=prepare_edit(response(before),request,proof());current=result.preview.workspace
    assert canonical(before)==raw
    assert current.project.facts.relations[0].target_id=='employer-b'
    assert [value.state for value in current.project.import_issues]==['retired','retired','active']
    assert current.project.facts.observations==before.project.facts.observations
    assert current.project.document.regions[2].blocks[0].children[-1]==before.project.document.regions[2].blocks[0].children[-1]
    source=current.sync_records[-1];outputs=result.created_ids['structure']
    assert outputs[canonical(['sync-lifecycle',source.id]).decode()]==source.lifecycle_id
    assert source.id in outputs.values() and source.ownership_conflict.record_id=='paper-a'
    assert canonical(result)==canonical(prepare_edit(response(before),request,proof()))
    assert apply_rich_mutation(before,result.mutation)[0]==current


def test_explicit_ownership_resolution_supersedes_old_row_and_retains_a_new_unresolved_result():
    _before,_sources,move=moved();before=move.preview.workspace;original=before.sync_records[-1]
    request=resolve_request(before);result=prepare_edit(response(before),request,proof());current=result.preview.workspace
    old,new=current.sync_records
    assert old.id==original.id and old.action_id==original.action_id and old.status=='stale'
    assert old.error_code=='SYNC_SUPERSEDED' and not old.ready and not old.proposed_steps
    assert new.id!=old.id and new.action_id==request.capture.action_id and new.status=='conflict'
    assert new.error_code=='NARRATIVE_REQUIRES_SCOPED_EDIT' and not new.ready and not new.proposed_steps
    assert new.ownership_conflict==original.ownership_conflict
    assert new.resolution_of.sync_id==original.id and new.resolution_of.before_record_hash==row_hash(original)
    assert old.capture==new.capture==request.capture
    assert old.lifecycle_id!=original.lifecycle_id
    assert semantic(current.project.document)==semantic(before.project.document)
    assert current.project.facts==before.project.facts and current.project.import_issues==before.project.import_issues
    outputs=result.created_ids['structure']
    assert {old.lifecycle_id,new.lifecycle_id,new.id}<=set(outputs.values())
    assert apply_rich_mutation(before,result.mutation)[0]==current


@pytest.mark.parametrize('damage',['row_hash','lifecycle','missing_subject','missing_occurrence','stale_dependency'])
def test_invalid_resolution_rejects_before_any_row_changes(damage):
    _before,_sources,move=moved();before=move.preview.workspace;request=resolve_request(before)
    operation=request.operations[0]
    if damage=='row_hash':operation.before_record_hash='0'*64
    elif damage=='lifecycle':operation.before_lifecycle_id='old-lifecycle'
    else:
        source=before.sync_records[-1]
        if damage=='missing_subject':source.ownership_conflict.record_id='missing'
        elif damage=='missing_occurrence':source.ownership_conflict.moved_occurrence_ids=['missing']
        else:source.dependencies[0].fingerprint='0'*64
        request=resolve_request(before)
    raw=canonical(before)
    with pytest.raises(ValueError):prepare_edit(response(before),request,proof())
    assert canonical(before)==raw


@pytest.mark.parametrize('damage',['missing_lineage','wrong_lineage','old_status','new_payload','new_status','new_capture','extra_write'])
def test_resolution_engine_requires_exact_lineage_and_atomic_supersession(damage):
    _before,_sources,move=moved();before=move.preview.workspace
    result=prepare_edit(response(before),resolve_request(before),proof());value=result.mutation.model_dump(by_alias=True)
    old,new=value['steps']
    if damage=='missing_lineage':new['record'].pop('resolutionOf')
    elif damage=='wrong_lineage':new['record']['resolutionOf']['beforeRecordHash']='0'*64
    elif damage=='old_status':old['record']['status']='conflict'
    elif damage=='new_payload':new['record']['ownershipConflict']['remainingOccurrenceIds']=['invented']
    elif damage=='new_status':new['record']['status']='applied'
    elif damage=='new_capture':new['record']['capture']['actionToken']+=1
    else:value['steps'].append({'kind':'remove_template_sync','syncId':old['record']['id'],'beforeHash':old['beforeHash']})
    raw=canonical(before)
    with pytest.raises(RichMutationFailure):apply_rich_mutation(before,TemplateMutationV1.model_validate(value))
    assert canonical(before)==raw


def test_inert_archive_resolution_uses_current_opening_without_reusing_foreign_capture():
    _before,sources,move=moved();before=move.preview.workspace
    imported,retained,_,_=open_rich_archive(export_rich_archive(before,sources,{},{}),'ownership-copy')
    assert retained==sources and imported.sync_records[0].capture is None
    request=resolve_request(imported);result=prepare_edit(response(imported),request,proof())
    assert all(row.capture==request.capture for row in result.preview.workspace.sync_records)
    assert result.preview.workspace.sync_records[-1].status=='conflict'
    assert result.preview.workspace.project.facts==imported.project.facts


def test_inert_resolution_preserves_historical_partition_after_current_display_movement():
    _before,sources,move=moved();before=move.preview.workspace
    imported,_,_,_=open_rich_archive(export_rich_archive(before,sources,{},{}),'ownership-return')
    block=next(value for value in imported.project.document.blocks() if value.id=='block-paper-a')
    current,_=apply_rich_mutation(imported,mutation_request(imported,[{'kind':'move_block','blockId':block.id,
        'beforeRevision':block.revision,'parentId':'owner-a','afterId':None}],'display-return-only'))
    original=current.sync_records[0]
    result=prepare_edit(response(current),resolve_request(current),proof()).preview.workspace
    assert result.sync_records[-1].ownership_conflict==original.ownership_conflict
    assert result.sync_records[-1].status=='conflict'
    assert result.sync_records[-1].error_code=='NARRATIVE_REQUIRES_SCOPED_EDIT'
    assert semantic(result.project.document)==semantic(current.project.document) and result.project.facts==current.project.facts
    assert result.project.facts.relations[0].target_id=='employer-b'
    assert all(dependencies_current(result,row.dependencies) for row in result.sync_records)


def test_move_and_resolution_preserve_unrelated_conflict_bytes():
    before,_sources,_command=conflicted_move()
    command=add(before,'unrelated')
    command.steps[0].record.fact_ids=['paper-b'];command.steps[0].record.block_ids=['block-paper-b']
    before,_=apply_rich_mutation(before,command);unrelated=canonical(before.sync_records[0])
    move=prepare_edit(response(before),move_request(before),proof())
    current=move.preview.workspace
    assert canonical(current.sync_records[0])==unrelated
    resolved=prepare_edit(response(current),resolve_request(current),proof()).preview.workspace
    assert canonical(resolved.sync_records[0])==unrelated
    assert len(resolved.sync_records)==3


def test_deleted_subject_cannot_be_resolved_from_its_retained_description():
    _before,_sources,move=moved();before=move.preview.workspace
    record=next(value for value in before.project.facts.extensions if value.id=='paper-a')
    identifiers=set().union(*occurrence_blocks(before.project,record.id).values())
    steps=[{'kind':'remove_extension','recordId':record.id,'beforeRevision':record.revision}]
    steps += [{'kind':'remove_block','blockId':block.id,'beforeRevision':block.revision}
        for block in before.project.document.blocks() if block.id in identifiers]
    current,_=apply_rich_mutation(before,mutation_request(before,steps,'delete-conflict-subject'))
    raw=canonical(current)
    with pytest.raises(ValueError):prepare_edit(response(current),resolve_request(current),proof())
    assert canonical(current)==raw and current.sync_records==before.sync_records


@pytest.mark.parametrize('operation',['move','resolution'])
@pytest.mark.parametrize('phase',['before_workspace_replaced','before_local_history_receipt'])
def test_actual_compact_conflict_publication_failure_and_receipt_retry_are_atomic(tmp_path,operation,phase):
    before,sources,_command=conflicted_move();before.project.import_issues=[issue('owner-issue','paper-a')]
    fixture=TemplateWriterFixture(tmp_path,before,sources)
    def prepare(request):
        request.capture.session_id=fixture.proof.session_id
        delta=fixture.writers.prepare_edit_delta(fixture.project,
            WriterPrepareEditV2(schemaVersion=2,proof=fixture.proof,preparation=request))
        cursor=fixture.jobs.load(fixture.project).writer.acknowledged_cursor+1
        return compact_command(fixture,delta,cursor)
    if operation=='resolution':
        fixture.writers.save(fixture.project,prepare(move_request(fixture.current())),originals=fixture.originals)
    command=prepare(move_request(fixture.current()) if operation=='move' else resolve_request(fixture.current()))
    raw=canonical(fixture.current())
    target=fixture.publisher if phase=='before_workspace_replaced' else fixture.writers
    def interrupt(name,_project):
        if name==phase:raise SystemExit('controlled ownership publication cut')
    target.observer=interrupt
    with pytest.raises(SystemExit,match='ownership publication cut'):
        fixture.writers.save(fixture.project,command,originals=fixture.originals)
    target.observer=lambda *_args:None
    if phase=='before_workspace_replaced':
        fixture.publisher.recover(fixture.project)
        assert canonical(fixture.current())==raw
    else:
        saved=fixture.writers.save(fixture.project,command,originals=fixture.originals)
        assert saved.replayed
        current=fixture.current()
        assert [row.status for row in current.sync_records]==(['conflict'] if operation=='move' else ['stale','conflict'])
        assert current.project.facts.relations[0].target_id=='employer-b'
        assert current.project.import_issues[0].state=='retired'


@pytest.mark.parametrize('linked',[False,True])
def test_actual_compact_move_resolution_full_history_chain_reopen_and_archive(tmp_path,linked):
    before,sources,_command=conflicted_move();before.project.import_issues=[issue('owner-issue','paper-a')]
    if linked:link_mentions(before)
    fixture=TemplateWriterFixture(tmp_path,before,sources)
    def save(request):
        request.capture.session_id=fixture.proof.session_id
        delta=fixture.writers.prepare_edit_delta(fixture.project,WriterPrepareEditV2(schemaVersion=2,proof=fixture.proof,preparation=request))
        cursor=fixture.jobs.load(fixture.project).writer.acknowledged_cursor+1
        return fixture.writers.save(fixture.project,compact_command(fixture,delta,cursor),originals=fixture.originals)
    move=save(move_request(fixture.current()))
    moved_state=fixture.current();assert moved_state.project.import_issues[0].state=='retired'
    resolve=save(resolve_request(moved_state));resolved=fixture.current()
    assert [row.status for row in resolved.sync_records]==['stale','conflict']
    undo_resolve=fixture.writers.local_history_command(fixture.project,history_request(fixture,resolve.local_history_ack,identifier='undo-resolution'),originals=fixture.originals)
    assert len(undo_resolve.workspace.sync_records)==1 and undo_resolve.workspace.sync_records[0].status=='conflict'
    undo_move=fixture.writers.local_history_command(fixture.project,history_request(fixture,move.local_history_ack,identifier='undo-owner-move'),originals=fixture.originals)
    assert not undo_move.workspace.sync_records and undo_move.workspace.project.facts.relations[0].target_id=='employer-a'
    assert undo_move.workspace.project.import_issues[0].state=='active'
    fixture.writers.local_history_command(fixture.project,history_request(fixture,undo_move.local_history_ack,'redo','redo-owner-move'),originals=fixture.originals)
    fixture.writers.local_history_command(fixture.project,history_request(fixture,undo_resolve.local_history_ack,'redo','redo-resolution'),originals=fixture.originals)
    reopened=fixture.current()
    assert [row.status for row in reopened.sync_records]==['stale','conflict']
    assert reopened.project.facts.relations[0].target_id=='employer-b' and reopened.project.import_issues[0].state=='retired'
    transferred,_,_,_=open_rich_archive(export_rich_archive(reopened,sources,{},{}),'ownership-transfer')
    assert transferred.project.facts==reopened.project.facts and transferred.project.document==reopened.project.document
    assert all(row.capture is None for row in transferred.sync_records)
