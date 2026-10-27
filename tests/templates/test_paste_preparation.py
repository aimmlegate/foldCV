"""Inline paste keeps exact runs and uses one shared ownership transaction."""

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import BoundLink,ManualScopeSpan,PresentedHyperlink,PresentedText
from packages.resume_core.rich_mutations import apply_rich_mutation,inline_text
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.template_identity import capture_span
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_bound_links import linked_workspace
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.test_clipboard_retention import captured
from tests.templates.test_manual_scope_occurrences import shared_workspace
from tests.templates.test_template_preparation import command,response
from tests.templates.test_transactions import issue


RUNS=[{'type':'text','text':'A','styles':{'bold':True}},
    {'type':'text','text':'😀','styles':{'italic':True,'textColor':'#334455'}}]


def paste_request(before,*,content=None,clipboard=None,start=0,end=6,target=None,identifier='paste-edit'):
    intent=command(before,start=start,end=end,target=target)
    value=intent.model_dump(mode='json',by_alias=True)
    source=({'kind':'same_project','clipboardCaptureId':clipboard.capture.clipboard_capture_id}
        if clipboard is not None else {'kind':'literal','content':RUNS if content is None else content})
    value['clientMutationId']=identifier
    value['operations']=[{'opId':'paste','kind':'paste_inline','destination':value['operations'][0]['range'],'source':source}]
    return TemplateEditPreparationV1.model_validate(value)


def words(block):return ''.join(inline_text(part) for part in block.content)


def test_rich_literal_paste_updates_whole_field_with_exact_runs_and_fragment_roots():
    before,_=workspace();original=canonical(before)
    intent=paste_request(before)
    prepared=prepare_edit(response(before),intent);after=prepared.preview.workspace
    block=after.project.document.regions[2].blocks[0]
    assert words(block)=='A😀 title' and all(part.type=='fact_field' for part in block.content)
    assert {part.occurrence_id for part in block.content}=={'occurrence-paper-a'}
    assert len({part.binding_id for part in block.content})==3
    assert block.content[0].styles.bold and block.content[1].styles.italic
    assert block.content[1].styles.text_color=='#334455'
    assert after.project.facts.extensions[0].cells[0].raw_input=='A😀 title'
    assert after.project.facts.extensions[0].cells[0].typed_value is None
    assert prepared.mutation.kind=='structure' and len(prepared.created_ids['paste'])>=3
    assert apply_rich_mutation(before,prepared.mutation)[0]==after
    assert canonical(prepare_edit(response(before),intent))==canonical(prepared)
    assert canonical(before)==original


def test_partial_cited_capture_rebinds_to_destination_field_without_losing_citations():
    before,_=workspace();clipboard=captured(before,start=1,end=4)
    prepared=prepare_edit(response(before),paste_request(before,clipboard=clipboard),clipboard=clipboard)
    part=prepared.preview.workspace.project.document.regions[2].blocks[0].content[0]
    assert part.type=='fact_field' and part.text=='har'
    assert part.citations==clipboard.payload.content[0].citations
    assert prepared.preview.workspace.project.facts.extensions[0].cells[0].evidence==before.project.facts.extensions[0].cells[0].evidence


@pytest.mark.parametrize('changed_marks',[False,True])
def test_same_wording_literal_paste_preserves_admitted_authority_and_active_issue(changed_marks):
    before,_=workspace();finding=issue('same-paste-issue','a-title');finding.block_ids=['block-paper-a'];before.project.import_issues=[finding]
    content=[{'type':'text','text':'Shared','styles':{'bold':changed_marks}},
        {'type':'text','text':' title','styles':{'italic':changed_marks}}]
    prepared=prepare_edit(response(before),paste_request(before,content=content,end=12))
    after=prepared.preview.workspace;assert after.project.facts==before.project.facts
    assert after.project.import_issues==before.project.import_issues
    block=after.project.document.regions[2].blocks[0]
    assert words(block)=='Shared title' and all(part.type=='fact_field' for part in block.content)
    assert {part.occurrence_id for part in block.content}=={'occurrence-paper-a'}
    assert block.content[0].styles.bold==changed_marks and block.content[-1].styles.italic==changed_marks


@pytest.mark.parametrize('scope_text',['Exact human input',''])
def test_same_wording_mixed_scope_field_overlay_keeps_authority_and_empty_anchors(scope_text):
    before,_=shared_workspace(scope_text);first,second=before.project.document.regions[2].blocks
    anchor=first.content[0].model_copy(deep=True)
    first.content+=[PresentedText(type='text',text=' / ',styles={}),*second.content]
    before.project.document.regions[2].blocks=[first]
    text=words(first);content=[{'type':'text','text':text[:2],'styles':{'bold':True}},
        {'type':'text','text':text[2:],'styles':{'italic':True}}]
    prepared=prepare_edit(response(before),paste_request(before,content=content,end=len(text)))
    after=prepared.preview.workspace;assert after.project.facts==before.project.facts
    spans=after.project.document.regions[2].blocks[0].content
    scoped=[part for part in spans if isinstance(part,ManualScopeSpan)]
    assert ''.join(part.text for part in scoped)==scope_text
    assert {part.occurrence_id for part in scoped}=={anchor.occurrence_id}
    assert {part.scope_id for part in scoped}=={anchor.scope_id}
    if not scope_text:assert len(scoped)==1 and scoped[0].fragment_id==anchor.fragment_id
    assert all(part.occurrence_id==second.content[0].occurrence_id for part in spans if part.type=='fact_field')


def test_equal_wording_capture_overlays_exact_citations_and_presentation_without_new_cell_authority():
    before,_=workspace();part=before.project.document.regions[2].blocks[0].content[0]
    source=before.project.sources[0];part.citations=[capture_span(source,source.units[0],0,3)]
    part.presentation.overrides.size=19;part.styles.bold=True
    clipboard=captured(before,start=0,end=6)
    part.presentation.overrides.size=12;part.styles.bold=False;part.citations=[]
    prepared=prepare_edit(response(before),paste_request(before,clipboard=clipboard),clipboard=clipboard)
    after=prepared.preview.workspace;result=after.project.document.regions[2].blocks[0].content[0]
    assert result.styles.bold and result.presentation.overrides.size==19
    assert result.citations==clipboard.payload.content[0].citations
    assert after.project.facts==before.project.facts


@pytest.mark.parametrize('kind',['paste','replace_text'])
def test_changed_text_rebinding_preserves_citations_from_every_selected_fragment(kind):
    before,_=workspace();block=before.project.document.regions[2].blocks[0];first=block.content[0]
    second=first.model_copy(deep=True);first.text='Shared ';second.text='title';second.binding_id='second-fragment'
    source=before.project.sources[0];one=capture_span(source,source.units[0],0,3);two=capture_span(source,source.units[0],4,8)
    first.citations=[one];second.citations=[two];block.content=[first,second]
    intent=paste_request(before,end=12) if kind=='paste' else command(before,end=12,text='Replacement')
    prepared=prepare_edit(response(before),intent)
    after=prepared.preview.workspace
    for part in after.project.document.regions[2].blocks[0].content:assert part.citations==[one,two]
    assert after.project.facts.extensions[0].cells[0].evidence==before.project.facts.extensions[0].cells[0].evidence


@pytest.mark.parametrize('literal_children',[False,True])
def test_rich_literal_paste_into_bound_label_preserves_independent_url(literal_children):
    before,_=linked_workspace();link=before.project.document.regions[2].blocks[0].content[0]
    if literal_children:link.content=[PresentedText(type='text',text='Shared title',styles={},presentation=link.presentation)]
    prepared=prepare_edit(response(before),paste_request(before))
    result=prepared.preview.workspace.project.document.regions[2].blocks[0].content[0]
    assert result.href==link.href and result.label_binding==link.label_binding and result.url_binding==link.url_binding
    assert ''.join(part.text for part in result.content)=='A😀 title'
    assert result.content[0].styles.bold and result.content[1].styles.italic
    assert all(part.type==('text' if literal_children else 'fact_field') for part in result.content)
    assert prepared.preview.workspace.project.facts.extensions[0].cells[0].raw_input=='A😀 title'
    assert prepared.preview.workspace.project.facts.extensions[0].cells[3]==before.project.facts.extensions[0].cells[3]


@pytest.mark.parametrize('literal_children',[False,True])
def test_same_wording_bound_label_overlay_keeps_authority_and_both_link_references(literal_children):
    before,_=linked_workspace();link=before.project.document.regions[2].blocks[0].content[0]
    if literal_children:link.content=[PresentedText(type='text',text='Shared title',styles={},presentation=link.presentation)]
    content=[{'type':'text','text':'Shared','styles':{'bold':True}},
        {'type':'text','text':' title','styles':{'italic':True}}]
    prepared=prepare_edit(response(before),paste_request(before,content=content,end=12))
    result=prepared.preview.workspace.project.document.regions[2].blocks[0].content[0]
    assert result.href==link.href and result.label_binding==link.label_binding and result.url_binding==link.url_binding
    assert result.content[0].styles.bold and result.content[-1].styles.italic
    assert prepared.preview.workspace.project.facts==before.project.facts


@pytest.mark.parametrize('empty',[False,True])
def test_literal_paste_into_shared_scope_keeps_one_new_exact_authority(empty):
    before,_=shared_workspace('Exact shared input');old=before.project.facts.manual_scopes[-1]
    intent=paste_request(before,content=[] if empty else RUNS,start=0,end=len(old.raw_input))
    prepared=prepare_edit(response(before),intent);after=prepared.preview.workspace
    scope=after.project.facts.manual_scopes[-1];block=after.project.document.regions[2].blocks[0]
    assert scope.id!=old.id and scope.raw_input==('' if empty else 'A😀') and scope.cell_ids==old.cell_ids
    spans=[part for part in block.content if isinstance(part,ManualScopeSpan)]
    assert len(spans)==(1 if empty else 2) and {part.scope_id for part in spans}=={scope.id}
    assert len({part.occurrence_id for part in spans})==1
    assert all(cell.manual_scope_id==scope.id for record in after.project.facts.extensions for cell in record.cells if cell.id in scope.cell_ids)
    assert apply_rich_mutation(before,prepared.mutation)[0]==after


def test_mixed_destination_literal_paste_creates_one_scope_for_affected_cells():
    before,_=workspace();first,second=before.project.document.regions[2].blocks
    first.content+=[PresentedText(type='text',text=' / ',styles={}),*second.content]
    before.project.document.regions[2].blocks=[first]
    prepared=prepare_edit(response(before),paste_request(before,start=7,end=20))
    after=prepared.preview.workspace;scope=after.project.facts.manual_scopes[-1]
    assert scope.cell_ids==['a-title','b-title'] and scope.raw_input=='A😀'
    spans=[part for part in after.project.document.regions[2].blocks[0].content if isinstance(part,ManualScopeSpan)]
    assert [part.text for part in spans]==['A','😀'] and len({part.occurrence_id for part in spans})==1
    assert len({part.fragment_id for part in spans})==2
    assert all(record.cells[0].state=='pending_manual' for record in after.project.facts.extensions)


@pytest.mark.parametrize('kind',['field','scope','link'])
def test_semantic_capture_into_literal_destination_keeps_facts_and_fresh_display_ids(kind):
    before,_=shared_workspace() if kind=='scope' else linked_workspace() if kind=='link' else workspace()
    clipboard=captured(before,end=12 if kind=='link' else None)
    destination=before.project.document.regions[2].blocks[0]
    destination.content=[PresentedText(type='text',text='prefix suffix',styles={})]
    intent=paste_request(before,clipboard=clipboard,start=7,end=7,target={'kind':'literal'})
    prepared=prepare_edit(response(before),intent,clipboard=clipboard)
    after=prepared.preview.workspace;inserted=after.project.document.regions[2].blocks[0].content[1]
    assert after.project.facts==before.project.facts and words(after.project.document.regions[2].blocks[0])=='prefix '+''.join(inline_text(p) for p in clipboard.payload.content)+'suffix'
    if kind=='scope':assert inserted.occurrence_id!=clipboard.payload.content[0].occurrence_id
    elif kind=='link':
        assert inserted.label_binding.occurrence_id!=clipboard.payload.content[0].label_binding.occurrence_id
        assert inserted.url_binding.occurrence_id!=clipboard.payload.content[0].url_binding.occurrence_id
        assert inserted.href==clipboard.payload.content[0].href
    else:assert inserted.occurrence_id!=clipboard.payload.content[0].occurrence_id
    assert prepared.created_ids['paste'] and apply_rich_mutation(before,prepared.mutation)[0]==after
    again=paste_request(before,clipboard=clipboard,start=7,end=7,target={'kind':'literal'},identifier='second-paste')
    other=prepare_edit(response(before),again,clipboard=clipboard)
    assert set(prepared.created_ids['paste'].values()).isdisjoint(other.created_ids['paste'].values())


@pytest.mark.parametrize('point',[0,12])
def test_semantic_capture_at_explicit_literal_outer_field_boundary_does_not_rebind(point):
    before,_=workspace();clipboard=captured(before)
    intent=paste_request(before,clipboard=clipboard,start=point,end=point,target={'kind':'literal'})
    prepared=prepare_edit(response(before),intent,clipboard=clipboard)
    block=prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert words(block)=='Shared titleShared title' and len({part.occurrence_id for part in block.content})==2
    assert prepared.preview.workspace.project.facts==before.project.facts


@pytest.mark.parametrize('destination',['field','scope','mixed','targeted_field','ordinary_link','bound_link'])
def test_semantic_capture_rejects_unrepresentable_destination_before_any_mutation(destination):
    before,_=shared_workspace() if destination=='scope' else linked_workspace() if destination=='bound_link' else workspace()
    clipboard=captured(before,end=12 if destination=='bound_link' else None);block=before.project.document.regions[2].blocks[0]
    start,end,target=0,6,None
    if destination=='mixed':block.content.insert(0,PresentedText(type='text',text='X',styles={}))
    elif destination=='targeted_field':start=end=0;target={'kind':'field','bindingId':block.content[0].binding_id}
    elif destination=='ordinary_link':block.content=[PresentedHyperlink(type='link',href='https://example.test',content=[PresentedText(type='text',text='literal',styles={})])]
    raw=canonical(before)
    with pytest.raises(ValueError):prepare_edit(response(before),paste_request(before,clipboard=clipboard,start=start,end=end,target=target),clipboard=clipboard)
    assert canonical(before)==raw


@pytest.mark.parametrize('destination',['field','scope','link'])
def test_literal_hyperlink_rejects_nested_or_owned_composition(destination):
    before,_=shared_workspace() if destination=='scope' else linked_workspace() if destination=='link' else workspace()
    content=[{'type':'link','href':'https://example.test','content':[{'type':'text','text':'linked','styles':{}}]}]
    raw=canonical(before)
    with pytest.raises(ValueError):prepare_edit(response(before),paste_request(before,content=content))
    assert canonical(before)==raw


def test_literal_hyperlink_into_unbound_text_preserves_url_and_child_marks():
    before,_=workspace();before.project.document.regions[2].blocks[0].content=[PresentedText(type='text',text='prefix suffix',styles={})]
    content=[{'type':'link','href':'https://example.test/exact','content':RUNS}]
    prepared=prepare_edit(response(before),paste_request(before,content=content,start=7,end=7,target={'kind':'literal'}))
    result=prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert words(result)=='prefix A😀suffix' and isinstance(result.content[1],PresentedHyperlink)
    assert result.content[1].href=='https://example.test/exact'
    assert result.content[1].content[0].styles.bold and result.content[1].content[1].styles.italic
    assert prepared.preview.workspace.project.facts==before.project.facts


def test_empty_semantic_scope_capture_inserts_a_fresh_anchor_without_losing_authority():
    before,_=shared_workspace('');clipboard=captured(before)
    before.project.document.regions[2].blocks[0].content=[PresentedText(type='text',text='literal',styles={})]
    prepared=prepare_edit(response(before),paste_request(before,clipboard=clipboard,start=0,end=0,target={'kind':'literal'}),clipboard=clipboard)
    block=prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert isinstance(block.content[0],ManualScopeSpan) and block.content[0].text=='' and words(block)=='literal'
    assert block.content[0].scope_id==clipboard.payload.content[0].scope_id
    assert block.content[0].occurrence_id!=clipboard.payload.content[0].occurrence_id
    assert prepared.preview.workspace.project.facts==before.project.facts


def test_a_block_capture_cannot_be_pasted_inline():
    before,_=workspace();clipboard=captured(before,blocks=[{'blockId':'block-paper-a','beforeRevision':1}])
    raw=canonical(before)
    with pytest.raises(ValueError,match='matching retained capture kind'):
        prepare_edit(response(before),paste_request(before,clipboard=clipboard,start=0,end=0,target={'kind':'literal'}),clipboard=clipboard)
    assert canonical(before)==raw


def test_failed_semantic_destination_accepts_corrected_intent_without_consuming_id_or_capture(tmp_path):
    from resume_api.projects.errors import ProjectFailure
    before,sources=workspace();editor=TemplateEditor(tmp_path,before,sources)
    block=before.project.document.regions[2].blocks[0]
    capture=editor.capture({'kind':'range','range':{'blockId':block.id,'beforeRevision':block.revision,'cellId':None,
        'field':'content','start':0,'end':12}},'copy-one')
    retained=editor.retained(capture)
    raw=canonical(editor.current())
    with pytest.raises(ProjectFailure) as refused:
        editor.edit(paste_request(editor.current(),clipboard=retained))
    assert (refused.value.code,refused.value.status)==('V7_INPUT_REJECTED',422)
    assert canonical(editor.current())==raw and 'paste-edit' not in editor.session().replays
    corrected=paste_request(editor.current(),clipboard=retained,start=0,end=0,target={'kind':'literal'})
    saved=editor.edit(corrected)
    assert saved.history.undo.action_id==corrected.capture.action_id
    assert words(editor.current().project.document.regions[2].blocks[0])=='Shared titleShared title'
    assert editor.current().project.facts==before.project.facts
