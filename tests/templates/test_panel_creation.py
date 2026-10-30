"""New employment items use captured configuration without rewriting existing items."""

from copy import deepcopy

import pytest

from packages.resume_core.template_inverse import semantic
from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import FieldOccurrence, PresentedText, TemplateParagraphBlock
from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.rich_fields import builtin_cell_values, field_key
from packages.resume_core.rich_mutations import apply_rich_mutation, RichMutationFailure
from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.template_authoring import copy_blocks, copy_inline
from packages.resume_core.template_capture import prepare_builtin_identities
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.template_preparation_ids import EditIdAllocator,existing_ids
from packages.resume_core.templates.compiler import canonical, compile_bytes
from packages.resume_core.templates.materialize_nodes import reference
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.pipeline_fixtures import source_draft
from tests.templates.test_materialize import admitted
from tests.templates.test_panel_preparation import prepared, restore
from tests.templates.test_template_preparation import response


def employment_workspace():
    operation,facts,package,src,raw=admitted('F02')
    return assemble_template(source_draft(operation,facts,captured=package,src=src),operation),{src.id:raw}


def empty_configure(edit):
    before,_=employment_workspace();config=before.project.template_package.definition.model_dump(by_alias=True)
    edit(config)
    before.project.template_package=compile_bytes(canonical(config),BUNDLED_TEMPLATE.parent,original_format='json')
    before.project.facts=WorkingFactsV2(schemaVersion=2,revision=1,records=[],tombstones=[],extensions=[],
        observations=[],relations=[],manualScopes=[])
    before.project.template_operations=[];before.project.import_coverage=[];before.project.import_issues=[]
    for region in before.project.document.regions:region.blocks=[]
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True))


def request(before, *, operation='add', values=None, context=None, record_id=None, identifier='create-item'):
    capture={'sessionId':'session','actionId':identifier,'actionToken':1,'dependencies':[]}
    value={'kind':'builtin_panel','opId':'new-item','command':{'operation':operation,'recordKind':'employment',
        'recordId':record_id,'periodId':None,'jobId':None,'values':values or {},
        'factsRevision':before.project.facts.revision,'documentRevision':before.document_revision,'capture':capture}}
    if context is not None:value['placementContext']=context
    return TemplateEditPreparationV1(schemaVersion=1,clientMutationId=identifier,snapshot=response(before).snapshot,
        capture=capture,operations=[value])


def owner(before):
    return next(block for block in before.project.document.blocks() if block.type=='section' and block.props.record_id is not None)


def period_block(section):
    return next(block for block in section.children if any(isinstance(span,FieldOccurrence)
        and span.field_key.startswith('period:') for span in block.content))


def context(section, block=None):
    return {'contextBlockId':(block or section).id,
        'placement':{'parentId':section.id,'afterId':section.children[-1].id if section.children else None}}


def test_new_employment_allocates_only_human_canonical_identity_and_preserves_all_old_blocks():
    before,_=employment_workspace();old={block.id:deepcopy(block) for block in before.project.document.blocks()}
    result=prepared(before,request(before,values={'employer':' New employer 😀 ','role':'New role','start':'2020',
        'end':'2024','present':'not yet sure'}))
    current=result.preview.workspace
    new=next(record for record in current.project.facts.records if record.id not in {value.id for value in before.project.facts.records})
    assert new.kind=='employment' and new.origin=='user' and not new.evidence
    assert new.employer.raw_text==' New employer 😀 ' and new.role.raw_text=='New role'
    assert new.periods[0].start.value.year==2020 and new.periods[0].start.value.month is None
    assert new.periods[0].present.value is None and new.periods[0].present.raw_text=='not yet sure'
    assert current.project.facts.builtin_identities==before.project.facts.builtin_identities
    # Import records are named by history file; an unloaded copy and a loaded one name the same (D104).
    assert current.project.current_history()==before.project.current_history()
    for block in current.project.document.blocks():
        if block.id in old:assert block==old[block.id]
    section=next(block for block in current.project.document.blocks() if block.type=='section' and block.props.record_id==new.id)
    fields=[span for block in section.children for span in block.content if isinstance(span,FieldOccurrence)]
    assert any(span.text=='not yet sure' and span.field_key.endswith(':present') for span in fields)
    assert all(span.record_id==new.id and span.cell_id==field_key(new.id,span.field_key) for span in fields)
    assert all(span.presentation.item_handle is None and not getattr(span,'citations',[]) for span in fields)
    assert all(not block.provenance for block in [section,*section.children])
    assert new.id in result.created_ids['new-item'].values() and new.periods[0].id in result.created_ids['new-item'].values()
    assert set(builtin_cell_values([new])) <= set(result.created_ids['new-item'].values())
    restore(before,result)
    with pytest.raises(ValueError,match='explicit existing period slots'):
        prepare_builtin_identities(current.project.facts,current.project.template_package,current.project.template_operations,
            id_factory=lambda _prefix:pytest.fail('unmapped periods must not receive guessed identities'))


@pytest.mark.parametrize(('start','month'),[('весна 2024',None),('03.2024',3),('2024-03',3)])
def test_new_period_uses_captured_defaults_and_keeps_existing_period_runs_unchanged(start,month):
    before,_=employment_workspace();section=owner(before);existing=period_block(section)
    existing.content[0].styles.bold=True
    existing.presentation.overrides.alignment='right';existing.props.alignment='right'
    for span in existing.content:
        if span.presentation is not None:span.presentation.overrides.alignment='right'
    result=prepared(before,request(before,operation='add_period',record_id=section.props.record_id,
        values={'start':start,'end':'2025'}))
    current=result.preview.workspace;changed=next(block for block in current.project.document.blocks() if block.id==section.id)
    assert next(block for block in changed.children if block.id==existing.id)==existing
    added=next(block for block in changed.children if block.id not in {value.id for value in section.children})
    assert ''.join(span.text for span in added.content)==start+'–2025'
    assert added.presentation.view_key==existing.presentation.view_key and added.presentation.node_index==existing.presentation.node_index
    assert added.presentation.overrides.alignment=='right' and added.props.alignment=='right'
    assert all(not span.styles.bold for span in added.content)
    assert current.project.facts.builtin_identities==before.project.facts.builtin_identities
    record=next(value for value in current.project.facts.records if value.id==section.props.record_id)
    assert len(record.periods)==2 and record.periods[0]==next(value for value in before.project.facts.records if value.id==record.id).periods[0]
    if month is None:
        assert record.periods[1].start.value is None and record.periods[1].start.status=='unresolved'
    else:
        assert record.periods[1].start.value.month==month
    assert record.periods[1].start.raw_text==start and record.periods[1].end.value.month is None
    outputs=set(result.created_ids['new-item'].values())
    assert {field_key(record.id,'period:'+record.periods[1].id+':'+key) for key in ['start','end','present']} <= outputs
    assert not set(builtin_cell_values(before.project.facts.records)) & outputs
    restore(before,result)


def test_removed_period_display_can_be_recreated_from_the_unique_captured_node():
    before,_=employment_workspace();section=owner(before);removed=period_block(section)
    section.children.remove(removed)
    for row in before.project.import_coverage:row.block_ids=[identifier for identifier in row.block_ids if identifier!=removed.id]
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True));section=owner(before)
    result=prepared(before,request(before,operation='add_period',record_id=section.props.record_id,values={'start':'2026'}))
    added=next(block for block in result.preview.workspace.project.document.blocks()
        if block.id not in {value.id for value in before.project.document.blocks()})
    assert added.presentation.node_index==removed.presentation.node_index
    assert any(isinstance(span,FieldOccurrence) and span.text=='2026' for span in added.content)


def test_formatted_period_paragraph_inherits_alignment_without_inline_context_ambiguity():
    from tests.templates.test_structural_preparation import prepare, selection
    before,_=employment_workspace()
    original=period_block(owner(before))
    before=prepare(before,'format_blocks',targets=[selection(original)],patch={'alignment':'right'}).preview.workspace
    section=owner(before);existing=period_block(section)
    assert existing.presentation.overrides.alignment=='right'
    assert any(span.presentation.overrides.alignment is None for span in existing.content)
    result=prepared(before,request(before,operation='add_period',record_id=section.props.record_id,values={'start':'2026'}))
    current=owner(result.preview.workspace)
    assert next(block for block in current.children if block.id==existing.id)==existing
    added=current.children[-1]
    assert added.presentation.overrides.alignment=='right' and added.props.alignment=='right'
    assert all(not span.styles.bold for span in added.content)
    restore(before,result)


def test_multiple_copied_sections_require_explicit_exact_owner_context():
    before,_=employment_workspace();section=owner(before)
    copied=copy_blocks(before.project,[section])[0]
    before.project.document.regions[2].blocks.append(copied)
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    with pytest.raises(ValueError,match='one authored employment section'):
        prepare_edit(response(before),request(before,operation='add_period',record_id=section.props.record_id))
    copied_period=period_block(copied)
    result=prepared(before,request(before,operation='add_period',record_id=section.props.record_id,
        context=context(copied,copied_period),values={'start':'2026'}))
    current=result.preview.workspace
    assert next(block for block in current.project.document.blocks() if block.id==section.id)==section
    target=next(block for block in current.project.document.blocks() if block.id==copied.id)
    assert len(target.children)==len(copied.children)+1 and target.props.record_id is None
    assert all(span.record_id==section.props.record_id for span in target.children[-1].content if isinstance(span,FieldOccurrence))


def test_new_employment_context_cannot_make_it_a_child_of_an_existing_employment():
    before,_=employment_workspace();section=owner(before)
    raw=canonical(before)
    with pytest.raises(ValueError,match='another item child'):
        prepare_edit(response(before),request(before,context=context(section)))
    assert canonical(before)==raw


def test_two_configured_views_require_a_context_and_never_choose_by_declaration_order():
    def edit(config):
        other=deepcopy(config['blocks'][0]);other['id']='another-employment-view';other['placement']['order']+=1
        config['blocks'].append(other)
    before=empty_configure(edit)
    with pytest.raises(ValueError,match='one captured view'):
        prepare_edit(response(before),request(before))
    package=before.project.template_package;view=package.definition.blocks[1]
    block=TemplateParagraphBlock(type='paragraph',id='explicit-view-context',revision=1,props={},children=[],provenance=[],
        presentation=reference(package,view.id,view.view.nodes[0].style,'context-instance',node_index=0),
        content=[PresentedText(type='text',text='Keep context',styles={})])
    region=before.project.document.regions[2];region.blocks=[block]
    chosen={'contextBlockId':block.id,'placement':{'parentId':region.id,'afterId':block.id}}
    result=prepared(before,request(before,context=chosen,values={'employer':'Chosen view'}))
    created=next(value for value in result.preview.workspace.project.document.blocks() if value.type=='section')
    assert created.presentation.view_key==view.id
    assert result.preview.workspace.project.document.regions[2].blocks[0]==block
    wrong=block.model_copy(update={'id':'wrong-view-parent','presentation':reference(package,
        package.definition.blocks[0].id,view.view.nodes[0].style,'wrong-context-instance',node_index=0)},deep=True)
    region.blocks.append(wrong)
    chosen['placement']={'parentId':wrong.id,'afterId':None}
    raw=canonical(before)
    with pytest.raises(ValueError,match='another item child'):
        prepare_edit(response(before),request(before,context=chosen,values={'employer':'Wrong container'}))
    assert canonical(before)==raw


def test_repeated_configured_field_allocates_independent_occurrences_in_one_join():
    def edit(config):
        config['blocks'][0]['view']['nodes']=[{'type':'join_fields','fields':['/company','/company'],
            'style':'body','separator':' | '}]
    before=empty_configure(edit)
    result=prepared(before,request(before,values={'employer':'Repeated'}))
    block=next(value for value in result.preview.workspace.project.document.blocks() if value.type=='paragraph')
    fields=[span for span in block.content if isinstance(span,FieldOccurrence)]
    assert ''.join(span.text for span in block.content)=='Repeated | Repeated'
    assert len(fields)==2 and fields[0].cell_id==fields[1].cell_id
    assert fields[0].occurrence_id!=fields[1].occurrence_id and fields[0].binding_id!=fields[1].binding_id


def test_unique_implicit_outer_item_root_uses_the_existing_captured_derivation():
    def edit(config):
        for binding in config['blocks'][0]['bindings']:
            if binding['semantic_type']=='employment':binding['item_pointer']=None
    before=empty_configure(edit)
    result=prepared(before,request(before,values={'employer':'Implicit root'}))
    assert any(span.text=='Implicit root' for block in result.preview.workspace.project.document.blocks() for span in block.content)


def test_an_unsupported_node_selecting_new_canonical_fields_rejects_instead_of_dropping_them():
    def edit(config):
        config['blocks'][0]['view']['nodes']=[{'type':'link','name_field':'/company','url_field':'/role','style':'body'}]
    before=empty_configure(edit);raw=canonical(before)
    with pytest.raises(ValueError,match='creation node is unsupported'):
        prepare_edit(response(before),request(before,values={'employer':'Keep raw','role':'https://example.test'}))
    assert canonical(before)==raw


def test_new_canonical_selector_collision_rejects_without_partial_creation():
    before=empty_configure(lambda _config:None);value=request(before,values={'employer':'Collision'})
    allocator=EditIdAllocator(before.project_id, value.client_mutation_id,'new-item',existing_ids(before))
    record=allocator.allocate('employment',['panel-employment'])
    selector=field_key(record,'employer');package=before.project.template_package
    before.project.document.regions[2].blocks.append(TemplateParagraphBlock(type='paragraph',id=selector,revision=1,
        props={},children=[],provenance=[],presentation=reference(package,'employment-view','body','collision-context'),
        content=[PresentedText(type='text',text='Retained block',styles={})]))
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True));raw=canonical(before)
    value=request(before,values={'employer':'Collision'})
    with pytest.raises(ValueError,match='derived authoring identity collides'):
        prepare_edit(response(before),value)
    assert canonical(before)==raw


def test_aliases_target_the_new_period_exactly_and_conflicts_retain_input():
    before,_=employment_workspace();section=owner(before)
    value=request(before,operation='add_period',record_id=section.props.record_id,values={'start':'2026'})
    allocator=EditIdAllocator(before.project_id, value.client_mutation_id,'new-item',existing_ids(before))
    period=allocator.allocate('period',['panel-period',section.props.record_id])
    key='period:'+period+':start'
    value.operations[0].command.values[key]='2025';raw=canonical(before)
    with pytest.raises(ValueError,match='aliases conflict'):prepare_edit(response(before),value)
    assert canonical(before)==raw
    value.operations[0].command.values[key]='2026'
    result=prepared(before,value)
    record=next(record for record in result.preview.workspace.project.facts.records if record.id==section.props.record_id)
    assert record.periods[-1].id==period and record.periods[-1].start.raw_text=='2026'


def test_copied_section_with_disagreeing_exact_employment_references_rejects_period_creation():
    before,_=employment_workspace();original=owner(before)
    added=prepared(before,request(before,values={'employer':'Second'})).preview.workspace
    other=next(block for block in added.project.document.blocks() if block.type=='section' and block.props.record_id!=original.props.record_id)
    copied=copy_blocks(added.project,[original])[0]
    reference_span=next(span for block in other.children for span in block.content
        if isinstance(span,FieldOccurrence) and span.field_key=='employer')
    copied.children[0].content+=copy_inline(added.project,[reference_span])
    added.project.document.regions[2].blocks.append(copied)
    added=WorkspaceV7.model_validate(added.model_dump(by_alias=True));raw=canonical(added)
    with pytest.raises(ValueError,match='one authored employment section'):
        prepare_edit(response(added),request(added,operation='add_period',record_id=original.props.record_id,
            context=context(copied,period_block(copied)),identifier='conflicting-copy'))
    assert canonical(added)==raw


def test_conflicting_retained_paragraph_overrides_require_one_explicit_context_block():
    before,_=employment_workspace();section=owner(before);original=period_block(section)
    copied=copy_blocks(before.project,[original])[0]
    copied.presentation.overrides.alignment='right';copied.props.alignment='right'
    section.children.append(copied)
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    with pytest.raises(ValueError,match='overrides need explicit context'):
        prepare_edit(response(before),request(before,operation='add_period',record_id=section.props.record_id))
    result=prepared(before,request(before,operation='add_period',record_id=section.props.record_id,
        context=context(section,copied),values={'start':'2026'}))
    current=next(block for block in result.preview.workspace.project.document.blocks() if block.id==section.id)
    assert current.children[-1].presentation.overrides.alignment=='right'
    assert next(block for block in current.children if block.id==original.id)==original


def test_multiple_period_nodes_require_the_explicit_captured_node_context():
    def edit(config):
        view=config['blocks'][0]['view']
        view['nodes'].append(deepcopy(next(node for node in view['nodes'] if node['type']=='period')))
    before=empty_configure(edit)
    before=prepared(before,request(before,values={'employer':'Two period views','start':'2020'})).preview.workspace
    section=owner(before)
    periods=[block for block in section.children if any(isinstance(span,FieldOccurrence)
        and span.field_key.startswith('period:') for span in block.content)]
    assert len(periods)==2 and periods[0].presentation.node_index!=periods[1].presentation.node_index
    with pytest.raises(ValueError,match='one compatible captured node'):
        prepare_edit(response(before),request(before,operation='add_period',record_id=section.props.record_id,
            identifier='period-without-node'))
    result=prepared(before,request(before,operation='add_period',record_id=section.props.record_id,
        context=context(section,periods[1]),values={'start':'2026'},identifier='period-selected-node'))
    changed=next(block for block in result.preview.workspace.project.document.blocks() if block.id==section.id)
    assert changed.children[-1].presentation.node_index==periods[1].presentation.node_index
    assert all(next(block for block in changed.children if block.id==value.id)==value for value in periods)


def test_period_context_from_another_view_rejects_even_inside_the_selected_section():
    def edit(config):
        other=deepcopy(config['blocks'][0]);other['id']='foreign-view';other['placement']['order']+=1
        config['blocks'].append(other)
    before=empty_configure(edit);package=before.project.template_package
    seed=TemplateParagraphBlock(type='paragraph',id='seed-context',revision=1,props={},children=[],provenance=[],
        presentation=reference(package,'employment-view','body','seed-instance'),content=[])
    region=before.project.document.regions[2];region.blocks.append(seed)
    selected={'contextBlockId':seed.id,'placement':{'parentId':region.id,'afterId':seed.id}}
    before=prepared(before,request(before,context=selected,values={'employer':'Selected owner'})).preview.workspace
    section=owner(before)
    foreign=seed.model_copy(update={'id':'foreign-context','presentation':reference(package,'foreign-view','body','foreign-instance')},deep=True)
    section.children.append(foreign)
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True));raw=canonical(before)
    with pytest.raises(ValueError,match='another captured view'):
        prepare_edit(response(before),request(before,operation='add_period',record_id=section.props.record_id,
            context=context(section,foreign),identifier='foreign-period'))
    assert canonical(before)==raw


def test_new_item_preserves_unrelated_import_issues_without_a_compliance_transition():
    from tests.templates.test_materialize import issue_workspace
    before,_=issue_workspace()
    result=prepared(before,request(before,values={'employer':'New independent item'}))
    assert result.preview.workspace.project.import_issues==before.project.import_issues
    assert result.preview.workspace.project.import_coverage==before.project.import_coverage
    assert not any(step.kind=='set_issue_state' for step in result.mutation.steps)


def test_new_item_uses_arbitrary_captured_region_id_and_does_not_restore_deleted_heading():
    before,_=employment_workspace();main=before.project.document.regions[2]
    main.id='arbitrary-body-region'
    main.blocks=[block for block in main.blocks if block.type!='heading']
    removed={identifier for row in before.project.import_coverage for identifier in row.block_ids}-{block.id for block in before.project.document.blocks()}
    for row in before.project.import_coverage:row.block_ids=[identifier for identifier in row.block_ids if identifier not in removed]
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    result=prepared(before,request(before,values={'employer':'New'}))
    assert result.preview.workspace.project.document.regions[2].id=='arbitrary-body-region'
    assert not any(block.type=='heading' for block in result.preview.workspace.project.document.regions[2].blocks)


@pytest.mark.parametrize('damage',['unknown','period_id','owner','placement','missing_context'])
def test_invalid_creation_retains_base_without_a_partial_record(damage):
    before,_=employment_workspace();value=request(before,values={'employer':'New'})
    operation=value.operations[0]
    if damage=='unknown':operation.command.values={'company':'Unknown alias'}
    elif damage=='period_id':operation.command.period_id='invented'
    elif damage=='owner':operation.command.job_id=owner(before).props.record_id
    elif damage=='placement':
        from packages.resume_core.models.template_authoring import PanelPlacementContext
        operation.placement_context=PanelPlacementContext(contextBlockId=owner(before).id,
            placement={'parentId':before.project.document.regions[2].id,'afterId':'missing'})
    else:
        from packages.resume_core.models.template_authoring import PanelPlacementContext
        operation.placement_context=PanelPlacementContext(contextBlockId='missing',
            placement={'parentId':before.project.document.regions[2].id,'afterId':None})
    raw=canonical(before)
    with pytest.raises((ValueError,RichMutationFailure)):prepare_edit(response(before),value)
    assert canonical(before)==raw


def test_actual_prepared_creation_save_undo_redo_reopen_and_portable_transfer(tmp_path):
    before,sources=employment_workspace();editor=TemplateEditor(tmp_path,before,sources)
    value=request(before,values={'employer':'New exact company','start':'2026'})
    value.operations[0].command.capture=value.capture.model_copy(deep=True)
    editor.edit(value)
    undo=editor.undo('undo-creation',expected='create-item').response.workspace
    assert semantic(undo.project.document)==semantic(before.project.document)
    assert semantic(undo.project.facts.records)==semantic(before.project.facts.records)
    editor.redo('redo-creation',expected='create-item')
    reopened=editor.reopen()
    assert any(record.kind=='employment' and record.employer.raw_text=='New exact company' for record in reopened.project.facts.records)
    transferred,retained,_,_=open_archive_v7(write_zip(archive_payload_v7(reopened,sources,{})),'creation-transfer')
    assert transferred.project.document==reopened.project.document and transferred.project.facts==reopened.project.facts
    assert retained==sources
