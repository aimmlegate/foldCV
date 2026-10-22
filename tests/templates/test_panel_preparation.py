"""Employment panel edits and explicit deletion share guarded authoring history."""

import pytest

from packages.resume_core.agent_edits import semantic
from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import FieldOccurrence, PresentedText, TemplateParagraphBlock
from packages.resume_core.models.rich_facts import WorkingPeriod
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.models.template_writer import WriterPrepareEditV2
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_fields import field_key, set_text
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.test_builtin_scopes import scoped_workspace
from tests.templates.test_compact_save import compact_command
from tests.templates.test_relation_transactions import related_workspace, owner_sections
from tests.templates.test_structural_preparation import intent
from tests.templates.test_template_local_history import history_request
from tests.templates.test_template_preparation import command as text_command, proof, response
from tests.templates.test_template_writers import TemplateWriterFixture
from tests.templates.test_transactions import authorization, issue


def period_workspace():
    from packages.resume_core.template_builtin_admission import unknown
    before,sources=scoped_workspace()
    record=next(value for value in before.project.facts.records if value.id=='employer-a')
    record.periods=[WorkingPeriod(id='exact-period',revision=1,start=unknown(),end=unknown(),present=unknown(),evidence=[])]
    for name,text in [('start','2020'),('end','2023'),('present','')]:
        set_text(record,'period:exact-period:'+name,text)
    presentation=before.project.document.regions[2].blocks[0].presentation
    content=[];provenance=[]
    for name in ['start','end']:
        key='period:exact-period:'+name
        if content:content.append(PresentedText(type='text',text=' — ',styles={}))
        content.append(FieldOccurrence(type='fact_field',bindingId=name+'-fragment',bindingRootId=name+'-root',
            recordId=record.id,fieldKey=key,cellId=field_key(record.id,key),occurrenceId=name+'-root',complete=True,
            presentation=presentation,text=getattr(record.periods[0],name).raw_text,styles={'bold':name=='end'},syncedFactRevision=1))
        provenance.append({'kind':'field_binding','id':'binding-'+name,'recordId':record.id,'fieldKey':key})
    before.project.document.regions[2].blocks.append(TemplateParagraphBlock(type='paragraph',id='period-block',revision=1,
        props={},children=[],content=content,provenance=provenance,presentation=presentation))
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True)),sources


def panel(before, operation='edit', *, values=None, period_id=None, identifier='panel-edit'):
    capture={'sessionId':'session','actionId':identifier,'actionToken':1,'dependencies':[]}
    return TemplateEditPreparationV1(schemaVersion=1,clientMutationId=identifier,snapshot=response(before).snapshot,
        capture=capture,operations=[{'kind':'builtin_panel','opId':'panel','command':{
            'operation':operation,'recordId':'employer-a','recordKind':'employment','jobId':None,'periodId':period_id,
            'values':values or {},'factsRevision':before.project.facts.revision,
            'documentRevision':before.document_revision,'capture':capture}}])


def prepared(before, request):
    raw=canonical(before)
    result=prepare_edit(response(before),request,proof())
    assert canonical(before)==raw
    assert canonical(result)==canonical(prepare_edit(response(before),request,proof()))
    if result.mutation:
        assert apply_rich_mutation(before,result.mutation)[0]==result.preview.workspace
    return result


def restore(before, result):
    current=result.preview.workspace
    inverse=inverse_template_mutation(before,current,origin_action_id=result.mutation.action_id,
        mutation_id='undo-panel',session_id='session',action_token=2)
    restored,_=apply_rich_mutation(current,inverse,history_authorization=authorization(current,inverse))
    assert semantic(restored.project.document)==semantic(before.project.document)
    assert semantic(restored.project.facts.records)==semantic(before.project.facts.records)
    assert semantic(restored.project.facts.extensions)==semantic(before.project.facts.extensions)
    assert restored.project.import_issues==before.project.import_issues
    return restored


def test_exact_selected_employer_panel_field_updates_its_display_only_and_retires_its_issue(monkeypatch):
    before,_=scoped_workspace();block=before.project.document.regions[2].blocks[0]
    imported=issue('company-warning',field_key('employer-a','employer'));imported.block_ids=[block.id]
    other=issue('role-warning',field_key('employer-a','role'));other.block_ids=[block.id]
    before.project.import_issues=[imported,other]
    block.content[0].styles.bold=True
    role=next(span for span in block.content if isinstance(span,FieldOccurrence) and span.field_key=='role').model_copy(deep=True)
    def forbidden(*_args,**_kwargs):pytest.fail('panel editing cannot invoke template assertions or inference')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload',forbidden)
    result=prepared(before,panel(before,values={'employer':' Exact company 😀 '}))
    current=result.preview.workspace
    changed=current.project.document.regions[2].blocks[0]
    assert changed.content[0].text==' Exact company 😀 ' and changed.content[0].styles.bold
    assert next(span for span in changed.content if isinstance(span,FieldOccurrence) and span.field_key=='role')==role
    assert [value.state for value in current.project.import_issues]==['retired','active']
    company=next(record for record in current.project.facts.records if record.id=='employer-a')
    assert company.employer.raw_text==' Exact company 😀 ' and company.employer.user_corrected
    assert current.project.facts.builtin_identities==before.project.facts.builtin_identities
    restore(before,result)


def test_unchanged_panel_input_is_a_true_noop_without_issue_retirement():
    before,_=scoped_workspace();record=next(value for value in before.project.facts.records if value.id=='employer-a')
    result=prepared(before,panel(before,values={'employer':record.employer.raw_text}))
    assert result.mutation is None and result.created_ids=={'panel':{}}
    assert result.preview.workspace==before and result.preview.durability=='durable'


def test_period_endpoint_switch_updates_every_binding_identity_and_preserves_authored_marks():
    before,_=period_workspace()
    result=prepared(before,panel(before,values={'period:exact-period:present':'present'}))
    project=result.preview.workspace.project
    changed=next(block for block in project.document.blocks() if block.id=='period-block')
    endpoint=changed.content[-1]
    assert endpoint.field_key=='period:exact-period:present'
    assert endpoint.cell_id==field_key('employer-a',endpoint.field_key)
    assert endpoint.binding_id!='end-fragment' and endpoint.occurrence_id!='end-root'
    assert endpoint.binding_root_id==endpoint.occurrence_id and endpoint.text=='present' and endpoint.styles.bold
    assert changed.provenance[-1].field_key==endpoint.field_key
    record=next(value for value in project.facts.records if value.id=='employer-a')
    assert record.periods[0].present.value is True and record.periods[0].end.raw_text=='2023'
    restore(before,result)
    switched=prepared(result.preview.workspace,panel(result.preview.workspace,values={'period:exact-period:present':''},identifier='end-again'))
    end=next(block for block in switched.preview.workspace.project.document.blocks() if block.id=='period-block').content[-1]
    assert end.field_key=='period:exact-period:end' and end.text=='2023' and end.styles.bold


@pytest.mark.parametrize('previous_present',[False,True])
def test_unresolved_human_present_endpoint_keeps_exact_visible_raw_input(previous_present):
    before,_=period_workspace()
    if previous_present:
        before=prepared(before,panel(before,values={'period:exact-period:present':'present'})).preview.workspace
    raw=' not yet sure 😀 '
    result=prepared(before,panel(before,values={'period:exact-period:present':raw},identifier='uncertain-present'))
    current=result.preview.workspace
    record=next(value for value in current.project.facts.records if value.id=='employer-a')
    assert record.periods[0].present.value is None and record.periods[0].present.status=='unresolved'
    assert record.periods[0].present.raw_text==raw and record.periods[0].end.raw_text=='2023'
    span=next(block for block in current.project.document.blocks() if block.id=='period-block').content[-1]
    assert span.field_key=='period:exact-period:present' and span.text==raw and span.styles.bold
    restore(before,result)


@pytest.mark.parametrize('binding',['label','url'])
def test_independent_link_references_reject_panel_changes_even_without_field_children(binding):
    from packages.resume_core.models.template_document import BoundLink,FieldRef
    before,_=scoped_workspace();block=before.project.document.regions[2].blocks[0];original=block.content[0]
    bound=FieldRef(recordId=original.record_id,fieldKey=original.field_key,cellId=original.cell_id,occurrenceId=original.occurrence_id)
    block.content[0]=BoundLink(type='bound_link',href='https://example.test/retained',
        content=[PresentedText(type='text',text=original.text,styles={})],
        labelBinding=bound if binding=='label' else None,urlBinding=bound if binding=='url' else None,presentation=original.presentation)
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True));raw=canonical(before)
    with pytest.raises(ValueError,match='semantic link panel editing'):
        prepare_edit(response(before),panel(before,values={'employer':'Changed company'}),proof())
    assert canonical(before)==raw
    role=prepared(before,panel(before,values={'role':'Unrelated role'}))
    assert role.preview.workspace.project.document.regions[2].blocks[0].content[0]==block.content[0]


def test_remove_period_removes_its_exact_fields_preserving_authored_literals_and_history():
    before,_=period_workspace()
    original=next(block for block in before.project.document.blocks() if block.id=='period-block')
    original.content.append(PresentedText(type='text',text=' authored suffix',styles={'italic':True}))
    result=prepared(before,panel(before,'remove_period',period_id='exact-period'))
    record=next(value for value in result.preview.workspace.project.facts.records if value.id=='employer-a')
    assert not record.periods
    changed=next(block for block in result.preview.workspace.project.document.blocks() if block.id=='period-block')
    assert ''.join(span.text for span in changed.content)==' —  authored suffix'
    assert not changed.provenance and changed.content[-1].styles.italic
    restore(before,result)


@pytest.mark.parametrize('display',['fields','link'])
def test_removing_a_period_does_not_match_another_valid_period_id_with_a_shared_colon_prefix(display):
    from packages.resume_core.models.template_document import BoundLink,FieldRef
    before,_=period_workspace();record=next(value for value in before.project.facts.records if value.id=='employer-a')
    record.periods.append(record.periods[0].model_copy(update={'id':'exact-period:later'},deep=True))
    original=next(block for block in before.project.document.blocks() if block.id=='period-block')
    later=original.model_copy(update={'id':'later-period-block'},deep=True)
    for span in later.content:
        if isinstance(span,FieldOccurrence):
            span.field_key=span.field_key.replace('period:exact-period:','period:exact-period:later:')
            span.cell_id=field_key(record.id,span.field_key)
            span.binding_id='later-'+span.binding_id
            span.binding_root_id=span.occurrence_id='later-'+span.occurrence_id
    for value in later.provenance:
        value.id='later-'+value.id
        value.field_key=value.field_key.replace('period:exact-period:','period:exact-period:later:')
    if display=='link':
        span=later.content[0]
        later.content=[BoundLink(type='bound_link',href='https://example.test/later',
            labelBinding=FieldRef(recordId=record.id,fieldKey=span.field_key,cellId=span.cell_id,occurrenceId=span.occurrence_id),
            urlBinding=None,content=[PresentedText(type='text',text=span.text,styles={})],presentation=span.presentation)]
    before.project.document.regions[2].blocks.append(later)
    before=WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    result=prepared(before,panel(before,'remove_period',period_id='exact-period'))
    record=next(value for value in result.preview.workspace.project.facts.records if value.id=='employer-a')
    assert [period.id for period in record.periods]==['exact-period:later']
    assert next(block for block in result.preview.workspace.project.document.blocks() if block.id==later.id)==later
    restore(before,result)


def test_period_deletion_detaches_unowned_human_scope_and_history_restores_its_exact_reference():
    from tests.templates.test_builtin_scopes import pending_steps
    from tests.templates.test_transactions import request as mutation_request
    from packages.resume_core.models.template_document import ManualScopeSpan
    before,_=period_workspace()
    steps,scope=pending_steps(before,names=('period:exact-period:start',),text='2020')
    block=next(value for value in before.project.document.blocks() if value.id=='period-block').model_copy(deep=True)
    block.content[0]=ManualScopeSpan(type='manual_scope',text='2020',styles={},presentation=block.presentation,
        scopeId=scope['id'],occurrenceId='period-scope-root',fragmentId='period-scope-fragment')
    steps.append({'kind':'put_block','parentId':'main','afterId':'block-paper-b','beforeRevision':block.revision,
        'block':block.model_dump(by_alias=True)})
    before,_=apply_rich_mutation(before,mutation_request(before,steps,'joined-edit'))
    result=prepared(before,panel(before,'remove_period',period_id='exact-period'))
    current=result.preview.workspace
    assert not current.project.facts.builtin_manual_scopes
    assert current.project.facts.manual_scopes==before.project.facts.manual_scopes
    changed=next(value for value in current.project.document.blocks() if value.id=='period-block')
    assert isinstance(changed.content[0],PresentedText) and changed.content[0].text=='2020'
    restored=restore(before,result)
    assert restored.project.facts.builtin_manual_scopes==before.project.facts.builtin_manual_scopes


def test_panel_edit_detaches_only_last_unowned_manual_display_and_preserves_historical_scope():
    before,_=scoped_workspace();block=before.project.document.regions[2].blocks[0]
    joined=text_command(before,start=0,end=sum(len(span.text) for span in block.content),text='Exact company and role')
    before=prepare_edit(response(before),joined,proof()).preview.workspace
    result=prepared(before,panel(before,values={'employer':'Direct company','role':'Direct role'}))
    current=result.preview.workspace
    assert current.project.facts.manual_scopes==before.project.facts.manual_scopes
    assert not current.project.facts.builtin_manual_scopes
    assert all(span.type!='manual_scope' for block in current.project.document.blocks()
        for span in block.content)
    restore(before,result)


@pytest.mark.parametrize('kind',['builtin','extension'])
def test_explicit_entity_deletion_cascades_authority_and_retains_unrelated_observations(kind):
    before,_=related_workspace();before=owner_sections(before)
    record=next(value for value in (before.project.facts.records if kind=='builtin' else before.project.facts.extensions)
        if value.id==('employer-a' if kind=='builtin' else 'paper-a'))
    result=prepared(before,intent(before,'delete_entity',recordId=record.id,beforeRevision=record.revision))
    current=result.preview.workspace
    removed={value.record_id for value in current.project.facts.tombstones}
    assert removed==({'employer-a','claim','paper-a','paper-b'} if kind=='builtin' else {'paper-a'})
    assert current.project.facts.observations==before.project.facts.observations
    assert next(value for value in current.project.facts.extensions if value.id=='reference').active
    assert not any(span.record_id in removed for block in current.project.document.blocks()
        for span in block.content if isinstance(span,FieldOccurrence))
    restore(before,result)


@pytest.mark.parametrize('damage',['facts','document','unknown_field','record','period','owner','capture','creation'])
def test_stale_or_unsupported_panel_request_retains_base(damage):
    before,_=scoped_workspace();request=panel(before,values={'employer':'Changed'})
    command=request.operations[0].command
    if damage=='facts':command.facts_revision+=1
    elif damage=='document':command.document_revision+=1
    elif damage=='unknown_field':command.values={'company':'Changed'}
    elif damage=='record':command.record_id='missing'
    elif damage=='period':command.period_id='missing'
    elif damage=='owner':command.job_id='employer-a'
    elif damage=='capture':command.capture.action_token+=1
    else:command.operation='add_period'
    raw=canonical(before)
    with pytest.raises(ValueError):prepare_edit(response(before),request,proof())
    assert canonical(before)==raw


def test_real_compact_panel_save_undo_redo_reopen_and_archive(tmp_path):
    before,sources=scoped_workspace();fixture=TemplateWriterFixture(tmp_path,before,sources)
    request=panel(before,values={'employer':'Human employer'})
    request.capture.session_id=fixture.proof.session_id
    request.operations[0].command.capture=request.capture.model_copy(deep=True)
    wrapped=WriterPrepareEditV2(schemaVersion=2,proof=fixture.proof,preparation=request)
    value=fixture.writers.prepare_edit_delta(fixture.project,wrapped)
    saved=fixture.writers.save(fixture.project,compact_command(fixture,value),originals=fixture.originals)
    undo=fixture.writers.local_history_command(fixture.project,history_request(fixture,saved.local_history_ack),originals=fixture.originals)
    assert semantic(undo.workspace.project.document)==semantic(before.project.document)
    redo=fixture.writers.local_history_command(fixture.project,history_request(fixture,undo.local_history_ack,'redo','redo-panel'),originals=fixture.originals)
    reopened=fixture.current()
    assert any(span.text=='Human employer' for block in reopened.project.document.blocks() for span in block.content)
    transferred,retained,_,_=open_rich_archive(export_rich_archive(reopened,sources,{},{}),'panel-transfer')
    assert transferred.project.document==reopened.project.document and transferred.project.facts==reopened.project.facts
    assert retained==sources and redo.workspace==reopened


@pytest.mark.parametrize('form',['full','delta'])
def test_actual_preparer_maps_tree_guard_failure_without_accepting_an_id_or_changing_input(tmp_path,form):
    from packages.resume_core.background_store import BackgroundFailure
    before,sources=scoped_workspace();fixture=TemplateWriterFixture(tmp_path,before,sources)
    block=before.project.document.regions[2].blocks[0]
    request=intent(before,'move_block',blockId=block.id,beforeRevision=block.revision,
        placement={'parentId':'missing','afterId':None})
    request.capture.session_id=fixture.proof.session_id
    wrapped=WriterPrepareEditV2(schemaVersion=2,proof=fixture.proof,preparation=request)
    method=fixture.writers.prepare_edit if form=='full' else fixture.writers.prepare_edit_delta
    raw=canonical(fixture.current())
    with pytest.raises(BackgroundFailure,match='JOB_SCOPE_INVALID'):
        method(fixture.project,wrapped)
    assert canonical(fixture.current())==raw
    opening=fixture.writers.preparations.openings.get(fixture.project)
    assert opening is None or request.client_mutation_id not in opening.entries
    request.operations[0].placement.parent_id='main'
    assert method(fixture.project,wrapped).client_mutation_id==request.client_mutation_id
