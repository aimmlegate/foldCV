"""Prepared structure retains exact cells, presentation, anchors and shared history."""

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import FieldOccurrence, PresentedText
from packages.resume_core.models.template_writer import WriterPrepareEditV2
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_fields import occurrences
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_authored_anchors import anchored
from tests.templates.test_compact_save import compact_command
from tests.templates.test_preparation_store import setup
from tests.templates.test_template_preparation import command, proof, response


def intent(before, kind, **values):
    value=command(before).model_dump(by_alias=True)
    value['clientMutationId']=kind+'-'+str(before.project_revision)
    value['capture']['actionId']=value['clientMutationId']
    value['operations']=[{'opId':'structure','kind':kind,**values}]
    return TemplateEditPreparationV1.model_validate(value)


def prepare(before, kind, **values):
    request=intent(before,kind,**values)
    raw=canonical(before)
    result=prepare_edit(response(before),request,proof())
    assert canonical(before)==raw
    assert canonical(result)==canonical(prepare_edit(response(before),request,proof()))
    if result.mutation:
        assert apply_rich_mutation(before,result.mutation)[0]==result.preview.workspace
    return result


def selection(block):
    return {'blockId':block.id,'beforeRevision':block.revision}


def place(after=None, parent='main'):
    return {'parentId':parent,'afterId':after}


def test_split_merge_preserves_one_occurrence_immutable_issues_and_authored_anchors():
    before,_=anchored();first=before.project.document.regions[2].blocks[0]
    split=prepare(before,'split_block',**selection(first),offset=7)
    current=split.preview.workspace;left,right=current.project.document.regions[2].blocks[:2]
    assert [left.content[0].text,right.content[0].text]==['Shared ','title']
    assert left.content[0].occurrence_id==right.content[0].occurrence_id=='occurrence-paper-a'
    assert left.content[0].binding_id!=right.content[0].binding_id
    assert current.project.facts==before.project.facts
    assert current.project.import_issues[0].state=='active'
    assert current.project.import_issues[0].block_ids==[left.id,right.id]
    assert all(row.block_ids==[left.id,right.id] for row in current.project.import_coverage)
    merge=prepare(current,'merge_blocks',leadingId=left.id,leadingRevision=left.revision,
        trailingId=right.id,trailingRevision=right.revision)
    assert occurrences(merge.preview.workspace.project.document)[('paper-a','title','occurrence-paper-a')].text=='Shared title'
    assert merge.preview.workspace.project.import_issues==before.project.import_issues
    assert merge.preview.workspace.project.import_coverage==before.project.import_coverage


def test_merging_distinct_fields_keeps_both_cells_and_inherits_trailing_styles():
    before,_=workspace();a,b=before.project.document.regions[2].blocks
    b.presentation.overrides.size=17;b.props.text_color='#334455';b.content[0].presentation=None
    result=prepare(before,'merge_blocks',leadingId=a.id,leadingRevision=a.revision,trailingId=b.id,trailingRevision=b.revision)
    merged=result.preview.workspace.project.document.regions[2].blocks[0]
    assert [value.cell_id for value in merged.content]==['a-title','b-title']
    assert [value.occurrence_id for value in merged.content]==['occurrence-paper-a','occurrence-paper-b']
    assert merged.content[1].presentation.overrides.size==17
    assert merged.content[1].styles.text_color=='#334455'
    assert result.preview.workspace.project.facts==before.project.facts


@pytest.mark.parametrize('complete',[False,True])
def test_fragment_copy_keeps_only_complete_field_authority(complete):
    before,_=workspace();block=before.project.document.regions[2].blocks[0]
    block.content[0].text='Backend Engineer';block.content[0].styles.bold=True
    result=prepare(before,'copy_fragment',source={**selection(block),'cellId':None,'field':'content',
        'start':0 if complete else 8,'end':16},placement=place(block.id))
    copied=result.preview.workspace.project.document.regions[2].blocks[1]
    span=copied.content[0]
    assert copied.id!=block.id and copied.presentation==block.presentation
    assert span.text==('Backend Engineer' if complete else 'Engineer') and span.styles.bold
    if complete:
        assert isinstance(span,FieldOccurrence) and span.cell_id=='a-title'
        assert span.occurrence_id!=block.content[0].occurrence_id
    else:
        assert isinstance(span,PresentedText) and span.citations==before.project.facts.extensions[0].cells[0].evidence
    assert result.preview.workspace.project.facts==before.project.facts


def test_complete_copy_of_split_occurrence_gets_one_fresh_root_and_remove_keeps_the_fact_issue():
    before,_=anchored();block=before.project.document.regions[2].blocks[0]
    split=prepare(before,'split_block',**selection(block),offset=7).preview.workspace
    left,right=split.project.document.regions[2].blocks[:2]
    copied=prepare(split,'copy_blocks',sources=[selection(left),selection(right)],placement=place(right.id)).preview.workspace
    values=copied.project.document.regions[2].blocks[2:4]
    assert values[0].content[0].occurrence_id==values[1].content[0].occurrence_id!=left.content[0].occurrence_id
    removed=prepare(copied,'remove_occurrences',blocks=[selection(value) for value in values]).preview.workspace
    assert removed.project.facts==before.project.facts
    assert removed.project.import_issues==split.project.import_issues
    assert removed.project.import_coverage==split.project.import_coverage


def test_removing_original_occurrence_clears_only_live_anchors():
    before,_=anchored();block=before.project.document.regions[2].blocks[0]
    removed=prepare(before,'remove_occurrences',blocks=[selection(block)]).preview.workspace
    assert all(value.block_ids==[] for value in removed.project.import_coverage)
    issue=removed.project.import_issues[0]
    assert issue.state=='active' and issue.block_ids==[]
    assert issue.lifecycle_id==before.project.import_issues[0].lifecycle_id
    assert removed.project.facts==before.project.facts


def test_insert_inherits_context_without_claiming_its_semantic_cell():
    before,_=workspace();block=before.project.document.regions[2].blocks[0]
    block.presentation.overrides.size=18
    inserted=prepare(before,'insert_paragraph',contextBlockId=block.id,contextRevision=block.revision,
        placement=place(block.id),text='Exact human 😀').preview.workspace.project.document.regions[2].blocks[1]
    assert inserted.presentation==block.presentation and inserted.content[0].text=='Exact human 😀'
    assert isinstance(inserted.content[0],PresentedText) and not inserted.provenance


def test_format_changes_kind_and_overrides_preserving_distinct_inline_metadata():
    before,_=anchored();block=before.project.document.regions[2].blocks[0]
    original=block.content[0].model_copy(deep=True)
    result=prepare(before,'format_blocks',targets=[selection(block)],patch={'blockKind':{'type':'heading','level':2},
        'alignment':'center','textColor':'#334455','backgroundColor':'#eeeeee'})
    changed=result.preview.workspace.project.document.regions[2].blocks[0]
    assert changed.type=='heading' and changed.props.level==2 and changed.props.alignment=='center'
    assert changed.presentation.overrides.alignment=='center' and changed.content==[original]
    assert result.preview.workspace.project.facts==before.project.facts
    assert result.preview.workspace.project.import_issues==before.project.import_issues
    unchanged=prepare(result.preview.workspace,'format_blocks',targets=[selection(changed)],
        patch={'blockKind':{'type':'heading','level':2},'alignment':'center','textColor':'#334455','backgroundColor':'#eeeeee'})
    assert unchanged.mutation is None


def test_reorder_keeps_all_bindings_and_current_position_is_a_noop():
    before,_=workspace();a,b=before.project.document.regions[2].blocks
    result=prepare(before,'move_block',**selection(b),placement=place()).preview.workspace
    assert [block.id for block in result.project.document.regions[2].blocks]==[b.id,a.id]
    assert result.project.facts==before.project.facts
    assert result.project.document.regions[2].blocks[0].content==b.content
    current=result.project.document.regions[2].blocks[0]
    assert prepare(result,'move_block',**selection(current),placement=place()).mutation is None


@pytest.mark.parametrize('damage',['stale','missing_parent','missing_sibling','self','descendant','surrogate','merge_gap'])
def test_invalid_structure_rejects_without_changing_base(damage):
    before,_=workspace();a,b=before.project.document.regions[2].blocks
    kind='move_block';values={**selection(a),'placement':place(b.id)}
    if damage=='stale': values['beforeRevision']+=1
    elif damage=='missing_parent': values['placement']=place(parent='missing')
    elif damage=='missing_sibling': values['placement']=place('missing')
    elif damage=='self': values['placement']=place(a.id)
    elif damage=='descendant': values['placement']=place(parent=a.id)
    elif damage=='surrogate':
        a.content[0].text='😀 text';kind='split_block';values={**selection(a),'offset':1}
    else:
        kind='merge_blocks';values={'leadingId':b.id,'leadingRevision':b.revision,'trailingId':a.id,'trailingRevision':a.revision}
    raw=canonical(before)
    with pytest.raises((ValueError,RichMutationFailure)):
        prepare_edit(response(before),intent(before,kind,**values),proof())
    assert canonical(before)==raw


def test_formatting_parent_and_child_keeps_both_changes_and_nested_remove_is_one_root():
    before,_=workspace();a,b=before.project.document.regions[2].blocks
    a.children=[b];before.project.document.regions[2].blocks=[a]
    result=prepare(before,'format_blocks',targets=[selection(a),selection(b)],patch={'alignment':'right'}).preview.workspace
    assert result.project.document.regions[2].blocks[0].props.alignment=='right'
    assert result.project.document.regions[2].blocks[0].children[0].props.alignment=='right'
    removed=prepare(before,'remove_occurrences',blocks=[selection(b),selection(a)])
    assert not removed.preview.workspace.project.document.regions[2].blocks
    assert len([step for step in removed.mutation.steps if step.kind=='remove_block'])==1


def test_merge_moves_trailing_children_without_dropping_their_import_anchors():
    before,_=anchored();a,b=before.project.document.regions[2].blocks
    child=b.model_copy(update={'id':'nested-child','provenance':[]},deep=True)
    child.content=[PresentedText(type='text',text='Retained child',styles={})]
    b.children=[child]
    before.project.import_coverage[0].block_ids=[child.id]
    before.project.import_issues[0].block_ids=[child.id]
    result=prepare(before,'merge_blocks',leadingId=a.id,leadingRevision=a.revision,trailingId=b.id,trailingRevision=b.revision)
    project=result.preview.workspace.project
    assert project.document.regions[2].blocks[0].children[0].id==child.id
    assert project.import_coverage[0].block_ids==[child.id] and project.import_issues[0].block_ids==[child.id]
    assert project.import_issues[0].state=='active'


def test_moving_owned_occurrence_changes_only_effective_relation_and_retires_scoped_issue():
    from tests.templates.test_relation_transactions import owner_sections,related_workspace
    from tests.templates.test_transactions import authorization,issue
    from packages.resume_core.template_inverse import inverse_template_mutation
    before,_=related_workspace();before=owner_sections(before)
    original=next(block for block in before.project.document.blocks() if block.id=='block-paper-a')
    warning=issue('owner-warning',before.project.facts.relations[0].id)
    warning.block_ids=[original.id];before.project.import_issues=[warning]
    result=prepare(before,'move_block',**selection(original),placement=place(parent='owner-b'))
    current=result.preview.workspace
    assert current.project.facts.extensions[0].relations[0].target_id=='employer-b'
    assert current.project.facts.observations==before.project.facts.observations
    assert current.project.import_issues[0].state=='retired'
    assert next(block for block in current.project.document.blocks() if block.id==original.id).content==original.content
    inverse=inverse_template_mutation(before,current,origin_action_id=result.mutation.action_id,
        mutation_id='undo-structural-move',session_id='session',action_token=2)
    restored,_=apply_rich_mutation(current,inverse,history_authorization=authorization(current,inverse))
    assert restored.project.facts.extensions[0].relations[0].target_id=='employer-a'
    assert restored.project.import_issues==before.project.import_issues


def test_manual_scope_split_and_complete_copy_retain_current_cell_union():
    from tests.templates.test_manual_scope_occurrences import shared_workspace
    from packages.resume_core.models.template_document import ManualScopeSpan
    before,_=shared_workspace();block=before.project.document.regions[2].blocks[0]
    split=prepare(before,'split_block',**selection(block),offset=6).preview.workspace
    left,right=split.project.document.regions[2].blocks[:2]
    assert left.content[0].scope_id==right.content[0].scope_id==block.content[0].scope_id
    copied=prepare(split,'copy_blocks',sources=[selection(left),selection(right)],placement=place(right.id)).preview.workspace
    copy_left,copy_right=copied.project.document.regions[2].blocks[2:4]
    assert isinstance(copy_left.content[0],ManualScopeSpan)
    assert copy_left.content[0].occurrence_id==copy_right.content[0].occurrence_id!=block.content[0].occurrence_id
    assert copied.project.facts==before.project.facts


def test_copy_source_targets_use_original_document_order_even_when_the_request_lists_them_backwards():
    before,_=workspace();block=before.project.document.regions[2].blocks[0]
    split=prepare(before,'split_block',**selection(block),offset=7).preview.workspace
    left,right=split.project.document.regions[2].blocks[:2]
    copied=prepare(split,'copy_blocks',sources=[selection(right),selection(left)],placement=place(right.id)).preview.workspace
    first,second=copied.project.document.regions[2].blocks[2:4]
    assert [span.text for value in [first,second] for span in value.content]==['Shared ','title']
    assert first.content[0].occurrence_id==second.content[0].occurrence_id


def test_ownership_move_with_an_outside_copy_creates_an_atomic_explicit_conflict():
    from tests.templates.test_relation_transactions import owner_sections,related_workspace
    from packages.resume_core.template_authoring import copy_blocks
    before,_=related_workspace();before=owner_sections(before)
    original=next(block for block in before.project.document.blocks() if block.id=='block-paper-a')
    before.project.document.regions[2].blocks[0].children.append(copy_blocks(before.project,[original])[0])
    raw=canonical(before)
    result=prepare_edit(response(before),intent(before,'move_block',**selection(original),placement=place(parent='owner-b')),proof())
    current=result.preview.workspace
    assert current.project.facts.relations[0].target_id=='employer-b'
    assert current.sync_records[0].status=='conflict'
    assert current.sync_records[0].ownership_conflict.record_id=='paper-a'
    assert current.project.document.regions[2].blocks[0].children[-1]==before.project.document.regions[2].blocks[0].children[-1]
    assert current.sync_records[0].lifecycle_id in result.created_ids['structure'].values()
    assert canonical(before)==raw


def test_real_writer_delta_split_issue_history_reopen_and_archive(tmp_path):
    fixture=setup(tmp_path);before=fixture.current();block=before.project.document.regions[2].blocks[0]
    request=intent(before,'split_block',**selection(block),offset=7)
    request.capture.session_id=fixture.proof.session_id
    wrapped=WriterPrepareEditV2(schemaVersion=2,proof=fixture.proof,preparation=request)
    prepared=fixture.writers.prepare_edit_delta(fixture.project,wrapped)
    saved=fixture.writers.save(fixture.project,compact_command(fixture,prepared),originals=fixture.originals)
    split=fixture.current()
    assert saved.local_history_ack.action_id==request.capture.action_id
    assert len(split.project.document.regions[2].blocks)==3
    from tests.templates.test_template_local_history import history_request
    undo=fixture.writers.local_history_command(fixture.project,history_request(fixture,saved.local_history_ack),originals=fixture.originals)
    assert len(fixture.current().project.document.regions[2].blocks)==2
    fixture.writers.local_history_command(fixture.project,history_request(fixture,undo.local_history_ack,'redo','local-redo'),originals=fixture.originals)
    reopened=fixture.current()
    assert reopened.project.document.regions[2].blocks[0].content[0].occurrence_id=='occurrence-paper-a'
    originals={identifier:data for (_project,identifier),data in fixture.originals.items()}
    transferred,_,_,_=open_rich_archive(export_rich_archive(reopened,originals,{},{}),'structure-transfer')
    assert transferred.project.document==reopened.project.document and transferred.project.facts==reopened.project.facts
