"""Metadata changes preserve authored values and guard current shared authority."""

import pytest

from packages.resume_core.models.template_document import ManualScopeSpan, PresentedText
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_authoring import copy_blocks, split_block
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_mutations import HistoryAuthorization
from packages.resume_core.template_preparation_cells import human_cell_steps
from packages.resume_core.template_preparation_ids import EditIdAllocator, existing_ids
from packages.resume_core.template_scope_displays import capture_source, inline_addresses, node_hash
from packages.resume_core.templates.compiler import canonical
from tests.templates.test_manual_scope_occurrences import shared_workspace


def copied_workspace():
    value, sources = shared_workspace()
    original = value.project.document.regions[2].blocks[0]
    allocator = EditIdAllocator('template-project', 'copy', 'copy', existing_ids(value))
    copied = copy_blocks(value.project, [original], id_factory=allocator)[0]
    value.project.document.regions[2].blocks.append(copied)
    return WorkspaceV7.model_validate(value.model_dump(by_alias=True)), sources, copied.id


def command(value, steps, *, identifier='display-metadata'):
    return TemplateMutationV1(schemaVersion=1, projectId=value.project_id, clientMutationId=identifier,
        actionId='display-action', kind='structure', capture={'sessionId':'session','actionId':'display-action',
            'actionToken':2,'dependencies':[]}, history={'kind':'edit','originActionId':None}, steps=steps)


def metadata(value, bindings):
    sources, assignments = {}, []
    for address, _block, _content, span in inline_addresses(value.project.document):
        if isinstance(span, ManualScopeSpan) and span.occurrence_id in bindings:
            key = span.scope_id, span.occurrence_id
            sources.setdefault(key, capture_source(value.project, *key).model_dump(by_alias=True))
            after = bindings[span.occurrence_id]
            assignments.append({'address':dict(zip(['blockId','cellId','field','inlineIndex'],address)),
                'beforeHash':node_hash(span),'after':{'kind':'literal'} if after is None else {
                    'kind':'manual_scope','scopeId':after,'occurrenceId':span.occurrence_id,'fragmentId':span.fragment_id}})
    return {'kind':'set_manual_scope_displays','sources':list(sources.values()),'assignments':assignments}


def test_detaching_a_copy_preserves_exact_values_cells_and_issues_and_has_guarded_inverse():
    before, _sources, copied_id = copied_workspace()
    copied = next(block for block in before.project.document.blocks() if block.id == copied_id)
    scope_span = copied.content[0]
    mutation = command(before, [metadata(before, {scope_span.occurrence_id:None})])
    result, _ = apply_rich_mutation(before,mutation)
    literal = next(block for block in result.project.document.blocks() if block.id == copied_id).content[0]
    assert isinstance(literal,PresentedText) and literal.text == scope_span.text
    assert literal.styles == scope_span.styles and literal.presentation == scope_span.presentation and literal.citations == scope_span.citations
    assert result.project.facts == before.project.facts and result.project.import_issues == before.project.import_issues
    inverse = inverse_template_mutation(before,result,origin_action_id=mutation.action_id,mutation_id='undo-display',
        session_id='session',action_token=3)
    from packages.resume_core.rich_mutations import mutation_sha256
    authority = HistoryAuthorization(result.project_id,result.document_revision,'session',3,mutation.action_id,mutation_sha256(inverse))
    restored,_ = apply_rich_mutation(result,inverse,history_authorization=authority)
    restored_span = next(block for block in restored.project.document.blocks() if block.id == copied_id).content[0]
    assert restored_span == scope_span
    with pytest.raises(RichMutationFailure): apply_rich_mutation(result,inverse)


def test_repointing_all_cells_and_original_fragments_detaches_other_occurrences_atomically():
    before,_sources,copied_id = copied_workspace()
    first = before.project.document.regions[2].blocks[0].content[0]
    copied = next(block for block in before.project.document.blocks() if block.id == copied_id).content[0]
    allocator = EditIdAllocator('template-project', 'repoint','scope',existing_ids(before))
    steps = human_cell_steps(before,['a-title','b-title'],first.text,'display-action',['block-paper-a'],allocator,ambiguous=True)
    new_scope = steps[0]['scope']['id']
    steps.append(metadata(before,{first.occurrence_id:new_scope,copied.occurrence_id:None}))
    result,_ = apply_rich_mutation(before,command(before,steps))
    assert result.project.document.regions[2].blocks[0].content[0].scope_id == new_scope
    assert next(block for block in result.project.document.blocks() if block.id == copied_id).content[0].text == copied.text
    assert all(cell.manual_scope_id == new_scope for record in result.project.facts.extensions for cell in record.cells
        if cell.id in {'a-title','b-title'})
    assert len(result.project.facts.manual_scopes) == len(before.project.facts.manual_scopes)+1


@pytest.mark.parametrize('damage',['scope_hash','fragment_hash','active_cells','assignment_hash','address','duplicate_step'])
def test_stale_or_duplicate_metadata_rejects_without_changing_input(damage):
    before,_sources,copied_id = copied_workspace()
    copied = next(block for block in before.project.document.blocks() if block.id == copied_id).content[0]
    step = metadata(before,{copied.occurrence_id:None})
    if damage == 'scope_hash': step['sources'][0]['scopeHash']='0'*64
    elif damage == 'fragment_hash': step['sources'][0]['fragments'][0]['fragmentHash']='0'*64
    elif damage == 'active_cells': step['sources'][0]['activeCellIds']=['a-title']
    elif damage == 'assignment_hash': step['assignments'][0]['beforeHash']='0'*64
    elif damage == 'address': step['assignments'][0]['address']['inlineIndex']=99
    mutation = command(before,[step,step] if damage == 'duplicate_step' else [step])
    raw = canonical(before)
    with pytest.raises(RichMutationFailure): apply_rich_mutation(before,mutation)
    assert canonical(before)==raw


def test_fragment_membership_is_complete_across_blocks_and_historical_cells_are_excluded():
    before,_ = shared_workspace()
    original = before.project.document.regions[2].blocks[0]
    before.project.document.regions[2].blocks[:1]=list(split_block(original,5))
    historical = before.project.facts.extensions[1].cells[0]
    historical.state,historical.manual_scope_id,historical.raw_input='human_raw',None,'Historical value'
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    source = capture_source(before.project,original.content[0].scope_id,original.content[0].occurrence_id)
    assert source.active_cell_ids==['a-title'] and len(source.fragments)==2
    step = metadata(before,{source.occurrence_id:None})
    step['sources'][0]['fragments'].pop()
    with pytest.raises(RichMutationFailure): apply_rich_mutation(before,command(before,[step]))


def test_ordinary_literal_to_scope_conversion_rejects_even_with_a_valid_scope_source():
    before,_sources,copied_id = copied_workspace()
    copied = next(block for block in before.project.document.blocks() if block.id == copied_id)
    span = copied.content[0]; copied.content=[PresentedText(type='text',text=span.text,styles={},presentation=span.presentation)]
    step = metadata(before,{'shared-occurrence':None})
    step['assignments']=[{'address':{'blockId':copied_id,'cellId':None,'field':'content','inlineIndex':0},
        'beforeHash':node_hash(copied.content[0]),'after':{'kind':'manual_scope','scopeId':span.scope_id,
            'occurrenceId':span.occurrence_id,'fragmentId':span.fragment_id}}]
    with pytest.raises(RichMutationFailure,match='STALE_MUTATION'): apply_rich_mutation(before,command(before,[step]))


@pytest.mark.parametrize('cell_id',['content','caption'])
def test_table_cells_named_like_plain_containers_keep_their_explicit_cell_address(cell_id):
    from packages.resume_core.models.template_document import TemplateTableBlock
    before,_=shared_workspace();old=before.project.document.regions[2].blocks[0]
    table=TemplateTableBlock(type='table',id=old.id,revision=old.revision,props={},children=[],provenance=[],
        presentation=old.presentation,content={'rows':[{'id':'row','cells':[{'id':cell_id,'revision':1,'content':old.content}]}],
            'columnWidths':[None],'headerRows':0,'headerCols':0})
    before.project.document.regions[2].blocks[0]=table
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    step=metadata(before,{'shared-occurrence':None})
    assert step['sources'][0]['fragments'][0]['cellId']==cell_id
    assert step['assignments'][0]['address']['cellId']==cell_id
    after,_=apply_rich_mutation(before,command(before,[step]))
    assert isinstance(after.project.document.regions[2].blocks[0].content.rows[0].cells[0].content[0],PresentedText)


@pytest.mark.parametrize('include_metadata', [False, True])
def test_surviving_original_fragment_cannot_be_retargeted_by_tree_change_without_assignment(include_metadata):
    before,_=shared_workspace();block=before.project.document.regions[2].blocks[0]
    span=block.content[0]
    allocator=EditIdAllocator('template-project', 'retarget','scope',existing_ids(before))
    steps=human_cell_steps(before,['a-title','b-title'],span.text,'display-action',[block.id],allocator,ambiguous=True)
    copied=span.model_copy(update={'scope_id':steps[0]['scope']['id']},deep=True)
    steps.append({'kind':'replace_inline_range','blockId':block.id,'beforeRevision':block.revision,
        'cellId':None,'field':'content','start':0,'end':17,'content':[copied.model_dump(by_alias=True)],'flankBindings':[]})
    if include_metadata:
        steps.append({'kind':'set_manual_scope_displays','sources':[capture_source(before.project,span.scope_id,span.occurrence_id).model_dump(by_alias=True)],'assignments':[]})
    with pytest.raises(RichMutationFailure,match='STALE_MUTATION'):apply_rich_mutation(before,command(before,steps))


@pytest.mark.parametrize('include_original_source', [False, True])
def test_retained_retarget_assignment_must_guard_its_original_source(include_original_source):
    before,_=shared_workspace();first,second=before.project.document.regions[2].blocks[:2]
    original=first.content[0]
    allocator=EditIdAllocator('template-project', 'second-scope','scope',existing_ids(before))
    steps=human_cell_steps(before,['b-title'],original.text,'display-action',[second.id],allocator,ambiguous=True)
    other=original.model_copy(update={'scope_id':steps[0]['scope']['id'],
        'occurrence_id':'other-root','fragment_id':'other-fragment'},deep=True)
    changed=second.model_copy(deep=True);changed.content=[other]
    steps.append({'kind':'put_block','parentId':'main','afterId':first.id,'beforeRevision':second.revision,
        'block':changed.model_dump(by_alias=True)})
    before,_=apply_rich_mutation(before,command(before,steps,identifier='second-scope'))
    first,second=before.project.document.regions[2].blocks[:2]
    retarget=first.content[0].model_copy(update={'scope_id':other.scope_id,'occurrence_id':other.occurrence_id},deep=True)
    changed=second.model_copy(deep=True)
    changed.content=[PresentedText(type='text',text=other.text,styles=other.styles,presentation=other.presentation)]
    sources=[capture_source(before.project,other.scope_id,other.occurrence_id).model_dump(by_alias=True)]
    if include_original_source:
        sources.append(capture_source(before.project,original.scope_id,original.occurrence_id).model_dump(by_alias=True))
    steps=[{'kind':'replace_inline_range','blockId':first.id,'beforeRevision':first.revision,
        'cellId':None,'field':'content','start':0,'end':17,'content':[retarget.model_dump(by_alias=True)],'flankBindings':[]},
        {'kind':'put_block','parentId':'main','afterId':first.id,'beforeRevision':second.revision,
            'block':changed.model_dump(by_alias=True)},
        {'kind':'set_manual_scope_displays','sources':sources,'assignments':[{
            'address':{'blockId':first.id,'cellId':None,'field':'content','inlineIndex':0},
            'beforeHash':node_hash(retarget),'after':{'kind':'manual_scope','scopeId':retarget.scope_id,
                'occurrenceId':retarget.occurrence_id,'fragmentId':retarget.fragment_id}}]}]
    raw=canonical(before)
    if include_original_source:
        after,_=apply_rich_mutation(before,command(before,steps))
        assert after.project.document.regions[2].blocks[0].content[0]==retarget
    else:
        with pytest.raises(RichMutationFailure,match='STALE_MUTATION'):
            apply_rich_mutation(before,command(before,steps))
    assert canonical(before)==raw
