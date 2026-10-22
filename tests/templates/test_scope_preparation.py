"""Shared text repeats atomically without assigning wording to a guessed field."""

import pytest

from packages.resume_core.models.template_document import ManualScopeSpan, PresentedText
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_archive import export_rich_archive,open_rich_archive
from packages.resume_core.rich_mutations import RichMutationFailure,apply_rich_mutation,mutation_sha256
from packages.resume_core.template_authoring import copy_blocks,split_block
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_mutations import HistoryAuthorization
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.template_scope_occurrences import active_scope_cells,scope_occurrences
from packages.resume_core.templates.compiler import canonical
from tests.templates.test_manual_scope_occurrences import shared_workspace
from tests.templates.test_scope_displays import copied_workspace
from tests.templates.test_template_preparation import command,proof,response


def prepared(value,*,identifier='scope-edit',block_id=None,**kwargs):
    request=command(value,**kwargs);request.client_mutation_id=identifier
    request.capture.action_id='action-'+identifier
    if block_id is not None:
        block=next(value for value in value.project.document.blocks() if value.id==block_id)
        request.operations[0].range.block_id=block.id;request.operations[0].range.before_revision=block.revision
    return prepare_text_edit(response(value),request,proof())


@pytest.mark.parametrize('start,end,text,expected',[(1,4,'!','E!t human input'),(0,17,'',''),(2,6,'😀','Ex😀human input')])
def test_repeat_repoints_all_current_cells_and_preserves_other_copies(start,end,text,expected):
    before,_sources,copied_id=copied_workspace();raw=canonical(before)
    copied=next(block for block in before.project.document.blocks() if block.id==copied_id).content[0]
    result=prepared(before,start=start,end=end,text=text)
    after=result.preview.workspace;scope=after.project.facts.manual_scopes[-1]
    assert scope.raw_input==expected and scope.cell_ids==['a-title','b-title']
    assert active_scope_cells(after.project.facts)[scope.id]=={'a-title','b-title'}
    assert len(scope_occurrences(after.project.document))==1
    group=next(iter(scope_occurrences(after.project.document).values()));assert group.text==expected
    literal=next(block for block in after.project.document.blocks() if block.id==copied_id).content[0]
    assert isinstance(literal,PresentedText) and literal.text==copied.text
    assert literal.styles==copied.styles and literal.presentation==copied.presentation and literal.citations==copied.citations
    assert canonical(before)==raw
    retry=prepared(before,start=start,end=end,text=text)
    assert canonical(result)==canonical(retry)


def test_fragmented_occurrence_repoints_untouched_fragments_across_blocks():
    before,_=shared_workspace();region=before.project.document.regions[2]
    region.blocks[:1]=list(split_block(region.blocks[0],5))
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    after=prepared(before,start=1,end=4,text='!').preview.workspace
    scope=after.project.facts.manual_scopes[-1];group=next(iter(scope_occurrences(after.project.document).values()))
    assert group.text==scope.raw_input=='E!t human input' and len(group.block_ids)==2
    assert all(span.scope_id==scope.id for span in group.spans)


@pytest.mark.parametrize('shared',[False,True])
def test_same_wording_with_new_marks_preserves_raw_cells_scope_and_issue_authority(shared):
    from tests.templates.storage_fixtures import workspace
    from tests.templates.test_transactions import issue
    before,_=shared_workspace() if shared else workspace()
    block=before.project.document.regions[2].blocks[0]
    finding=issue('unchanged-wording','a-title');finding.block_ids=[block.id]
    before.project.import_issues=[finding]
    changed=prepared(before,start=0,end=6,text=block.content[0].text[:6],styles={'italic':True}).preview.workspace
    assert changed.project.facts==before.project.facts
    assert changed.project.import_issues==before.project.import_issues
    assert ''.join(span.text for span in changed.project.document.regions[2].blocks[0].content)==block.content[0].text


def test_empty_insertion_then_full_deletion_keeps_exactly_one_empty_scope_anchor():
    before,_=shared_workspace('');span=before.project.document.regions[2].blocks[0].content[0]
    inserted=prepared(before,start=0,end=0,text='New',target={'kind':'manual_scope','fragmentId':span.fragment_id}).preview.workspace
    assert inserted.project.facts.manual_scopes[-1].raw_input=='New'
    deleted=prepared(inserted,identifier='delete-empty',start=0,end=3,text='').preview.workspace
    groups=list(scope_occurrences(deleted.project.document).values())
    assert len(groups)==1 and groups[0].text=='' and len(groups[0].spans)==1
    span=groups[0].spans[0]
    repeated=prepared(deleted,identifier='insert-again',start=0,end=0,text='Again',target={'kind':'manual_scope','fragmentId':span.fragment_id})
    assert repeated.preview.workspace.project.facts.manual_scopes[-1].raw_input=='Again'


def test_repeat_excludes_historical_cells_and_later_literal_edits_leave_pending_scope_unchanged():
    before,_=shared_workspace();historical=before.project.facts.extensions[1].cells[0]
    historical.state,historical.manual_scope_id,historical.raw_input='human_raw',None,'Independent value'
    block=before.project.document.regions[2].blocks[0];block.content.append(PresentedText(type='text',text='!',styles={}))
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    after=prepared(before,start=1,end=4,text='!').preview.workspace
    scope=after.project.facts.manual_scopes[-1];assert scope.cell_ids==['a-title']
    assert after.project.facts.extensions[1].cells[0]==historical
    literal=prepared(after,identifier='literal-only',start=15,end=16,text='?').preview.workspace
    assert literal.project.facts==after.project.facts


def test_direct_field_edit_detaches_displays_only_when_their_last_current_scope_cell_leaves():
    before,_=shared_workspace()
    # The second field display remains independently editable while its cell is pending.
    first=prepared(before,block_id='block-paper-b',start=0,end=6,text='Independent').preview.workspace
    assert len(scope_occurrences(first.project.document))==1
    assert list(active_scope_cells(first.project.facts).values())==[{'a-title'}]
    original=first.project.document.regions[2].blocks[0].content[0]
    independent=first.project.document.regions[2].blocks[1].content[0].model_copy(deep=True)
    independent.record_id='paper-a';independent.cell_id='a-title';independent.binding_id='last-field-fragment'
    independent.binding_root_id=independent.occurrence_id='last-field-root';independent.text='Original field display'
    first.project.document.regions[2].blocks[1].content=[independent]
    first=WorkspaceV7.model_validate(first.model_dump(by_alias=True))
    last=prepared(first,identifier='last-field',block_id='block-paper-b',start=0,end=8,text='Exact').preview.workspace
    assert not active_scope_cells(last.project.facts) and not scope_occurrences(last.project.document)
    literal=last.project.document.regions[2].blocks[0].content[0]
    assert isinstance(literal,PresentedText) and literal.text==original.text and literal.citations==original.citations


def test_scope_plus_literal_and_field_uses_current_union_and_only_replacement_input():
    before,_=shared_workspace();block=before.project.document.regions[2].blocks[0]
    field=before.project.document.regions[2].blocks[1].content[0].model_copy(deep=True)
    field.field_key='journal';field.cell_id='b-journal';field.text='Journal South';field.binding_id='journal-fragment'
    field.binding_root_id=field.occurrence_id='journal-occurrence'
    block.content.extend([PresentedText(type='text',text=' / ',styles={}),field])
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    after=prepared(before,start=5,end=24,text='Exact union').preview.workspace
    scope=after.project.facts.manual_scopes[-1]
    assert scope.raw_input=='Exact union' and scope.cell_ids==['a-title','b-journal','b-title']
    group=next(iter(scope_occurrences(after.project.document).values()));assert group.text=='Exact union'
    assert any(isinstance(span,PresentedText) and span.text=='Exact' for span in after.project.document.regions[2].blocks[0].content)


def test_scope_insertion_after_an_unrelated_bound_link_preserves_link_authority():
    from packages.resume_core.models.template_document import BoundLink,FieldRef
    before,_=shared_workspace();block=before.project.document.regions[2].blocks[0]
    span=block.content[0];field=before.project.document.regions[2].blocks[1].content[0].model_copy(deep=True)
    field.binding_id='prefix-fragment';field.binding_root_id=field.occurrence_id='prefix-root'
    link=BoundLink(type='bound_link',href='https://example.test/untouched',content=[field],
        labelBinding=FieldRef(recordId=field.record_id,fieldKey=field.field_key,cellId=field.cell_id,occurrenceId=field.occurrence_id),
        urlBinding=None,presentation=field.presentation)
    block.content.insert(0,link)
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    point=len(field.text)+2
    after=prepared(before,start=point,end=point,text='!',target={'kind':'manual_scope','fragmentId':span.fragment_id}).preview.workspace
    assert after.project.facts.manual_scopes[-1].raw_input=='Ex!act human input'
    retained=after.project.document.regions[2].blocks[0].content[0]
    assert isinstance(retained,BoundLink) and retained.href==link.href and retained.label_binding==link.label_binding
    assert retained.content[0].text==field.text


def test_two_selected_scopes_share_only_current_cell_union_and_replacement_text():
    from packages.resume_core.template_preparation_cells import human_cell_steps
    from packages.resume_core.template_preparation_ids import EditIdAllocator,existing_ids
    from tests.templates.test_scope_displays import command as mutation
    before,_=shared_workspace();block=before.project.document.regions[2].blocks[0].model_copy(deep=True)
    allocator=EditIdAllocator(proof(),'separate-scopes','scope',existing_ids(before));steps=[];parts=[]
    for index,(cell,text) in enumerate([('a-title','Alpha'),('b-title','Beta')]):
        changes=human_cell_steps(before,[cell],text,'display-action',[block.id],allocator,ambiguous=True)
        steps.extend(changes)
        if parts:parts.append(PresentedText(type='text',text=' / ',styles={}))
        parts.append(ManualScopeSpan(type='manual_scope',scopeId=changes[0]['scope']['id'],occurrenceId='root-'+str(index),
            fragmentId='fragment-'+str(index),text=text,styles={},presentation=block.presentation))
    block.content=parts
    steps.append({'kind':'put_block','parentId':'main','afterId':None,'beforeRevision':block.revision,
        'block':block.model_dump(by_alias=True),'keepChildren':True})
    before=apply_rich_mutation(before,mutation(before,steps,identifier='two-scopes'))[0]
    after=prepared(before,start=2,end=9,text='Exact').preview.workspace
    scope=after.project.facts.manual_scopes[-1]
    assert scope.cell_ids==['a-title','b-title'] and scope.raw_input=='Exact'
    assert [group.text for group in scope_occurrences(after.project.document).values()]==['Exact']


def test_repeat_undo_redo_archive_and_stale_result_have_exact_retained_authority():
    before,sources,_copied_id=copied_workspace();result=prepared(before,start=1,end=4,text='!');after=result.preview.workspace
    inverse=inverse_template_mutation(before,after,origin_action_id=result.mutation.action_id,mutation_id='scope-undo',
        session_id='session',action_token=3)
    authority=HistoryAuthorization(after.project_id,after.document_revision,'session',3,result.mutation.action_id,mutation_sha256(inverse))
    restored,_=apply_rich_mutation(after,inverse,history_authorization=authority)
    assert [group.text for group in scope_occurrences(restored.project.document).values()]==['Exact human input']*2
    assert active_scope_cells(restored.project.facts)==active_scope_cells(before.project.facts)
    redo=inverse_template_mutation(after,restored,origin_action_id=result.mutation.action_id,mutation_id='scope-redo',
        session_id='session',action_token=4,kind='redo')
    auth=HistoryAuthorization(restored.project_id,restored.document_revision,'session',4,result.mutation.action_id,mutation_sha256(redo))
    redone,_=apply_rich_mutation(restored,redo,history_authorization=auth)
    assert [group.text for group in scope_occurrences(redone.project.document).values()]==['E!t human input']
    portable,_,_,_=open_rich_archive(export_rich_archive(redone,sources,{},{}),'repeat-transfer')
    assert portable.project.facts==redone.project.facts and portable.project.document==redone.project.document
    stale=result.mutation.model_copy(update={'client_mutation_id':'stale-repeat'},deep=True)
    with pytest.raises(RichMutationFailure):apply_rich_mutation(redone,stale)


def test_builtin_shared_repeat_keeps_null_values_and_exact_pending_input_without_reassignment():
    from packages.resume_core.rich_fields import field_key,inline_groups
    from tests.templates.test_builtin_scopes import scoped_workspace
    before,_=scoped_workspace();block=before.project.document.regions[2].blocks[0]
    length=sum(len(span.text.encode('utf-16-le'))//2 for _name,content in inline_groups(block) for span in content)
    first=prepared(before,start=0,end=length,text='Exact company and role').preview.workspace
    assert first.project.facts.manual_scopes[-1].cell_ids==sorted([field_key('employer-a','employer'),field_key('employer-a','role')])
    next_value=prepared(first,identifier='builtin-repeat',start=1,end=4,text='!').preview.workspace
    scope=next_value.project.facts.manual_scopes[-1]
    company=next(record for record in next_value.project.facts.records if record.id=='employer-a')
    for name in ['employer','role']:
        field=getattr(company,name)
        assert field.value is None and field.status=='pending' and field.raw_text=='' and field.pending_raw_text==scope.raw_input
        assert next_value.project.facts.builtin_manual_scopes[field_key(company.id,name)]==scope.id


def test_real_delta_save_shared_issue_undo_redo_and_reopen_use_one_retained_history(tmp_path):
    from tests.templates.test_compact_save import compact_command
    from tests.templates.test_preparation_store import request
    from tests.templates.test_template_local_history import history_request
    from tests.templates.test_template_writers import TemplateWriterFixture
    from tests.templates.test_transactions import issue
    before,sources,copied_id=copied_workspace()
    changed_issue=issue('scope-cell-issue','a-title');changed_issue.block_ids=['block-paper-a']
    detached_issue=issue('copy-wording-issue',copied_id);detached_issue.block_ids=[copied_id]
    before.project.import_issues=[changed_issue,detached_issue]
    fixture=TemplateWriterFixture(tmp_path,before,sources)
    intent=request(fixture,start=1,end=4,text='!')
    delta=fixture.writers.prepare_edit_delta(fixture.project,intent)
    assert len(canonical(delta))<32*1024
    saved=fixture.writers.save(fixture.project,compact_command(fixture,delta),originals=fixture.originals)
    assert saved.local_history_ack is not None
    assert [value.state for value in fixture.current().project.import_issues]==['retired','active']
    undo=fixture.writers.local_history_command(fixture.project,history_request(fixture,saved.local_history_ack),originals=fixture.originals)
    assert [value.state for value in undo.workspace.project.import_issues]==['active','active']
    assert [group.text for group in scope_occurrences(undo.workspace.project.document).values()]==['Exact human input']*2
    redo=fixture.writers.local_history_command(fixture.project,history_request(fixture,undo.local_history_ack,'redo','scope-redo'),originals=fixture.originals)
    assert [value.state for value in redo.workspace.project.import_issues]==['retired','active']
    assert [group.text for group in scope_occurrences(redo.workspace.project.document).values()]==['E!t human input']
    reopened=fixture.canonical.read_committed(fixture.project)[0]
    assert reopened==redo.workspace
