"""Retained clipboard authority follows cells and transitive ownership only."""

import pytest

from packages.resume_core.models.template_facts import Relation
from packages.resume_core.models.rich_document import FieldBinding
from packages.resume_core.models.template_authoring import TemplateClipboardCaptureV1
from packages.resume_core.models.template_document import BoundLink,FieldRef,PresentedText
from packages.resume_core.template_authoring import split_block
from packages.resume_core.template_clipboard import capture_clipboard
from packages.resume_core.template_clipboard_witnesses import (captured_package_hash,field_witness,fingerprint,ownership_witness,scope_witness,
    source_witness,verify_witness,verify_witnesses)
from packages.resume_core.template_facts import human_edit
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.presentation import snapshot_identity
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.storage_fixtures import workspace
from tests.templates.test_manual_scope_occurrences import shared_workspace
from tests.templates.test_relation_transactions import related_workspace


def test_field_witness_survives_source_display_removal_and_unrelated_cell_changes():
    before,_=workspace();project=before.project;witness=field_witness(project,'paper-a','title','a-title')
    project.document.regions[2].blocks=[]
    project.facts=human_edit(project.facts,'paper-a','journal','Independent journal correction')
    verify_witness(project,witness)
    project.facts=human_edit(project.facts,'paper-a','title','New title')
    with pytest.raises(ValueError,match='authority changed'):verify_witness(project,witness)


@pytest.mark.parametrize('damage',['record','cell','key','inactive'])
def test_field_witness_rejects_missing_or_wrong_current_identity(damage):
    before,_=workspace();project=before.project;witness=field_witness(project,'paper-a','title','a-title')
    if damage=='record':witness.record_id='missing'
    elif damage=='cell':witness.cell_id='b-title'
    elif damage=='key':witness.field_key='journal'
    else:project.facts.extensions[0].active=False
    with pytest.raises(ValueError):verify_witness(project,witness)


def test_transitive_legacy_builtin_owner_changes_invalidate_attached_extension():
    before,_=related_workspace();project=before.project
    relation=project.facts.relations[0];relation.kind='extension_of';relation.target_id='claim'
    project.facts.extensions[0].relations[0]=relation.model_copy(deep=True)
    witness=field_witness(project,'paper-a','title','a-title')
    assert [item.record_id for item in witness.ownership.ancestors]==['claim','employer-a']
    assert [item.relation_id for item in witness.ownership.relations]==['award-owner']
    claim=next(record for record in project.facts.records if record.id=='claim')
    claim.value.raw_text='Unrelated claim wording';claim.value.value='Unrelated claim wording'
    verify_witness(project,witness)
    claim.job_id='employer-b'
    with pytest.raises(ValueError,match='authority changed'):verify_witness(project,witness)


def test_reachable_edges_are_complete_but_related_and_sibling_edges_do_not_invalidate():
    before,_=related_workspace();project=before.project;witness=field_witness(project,'paper-a','title','a-title')
    project.facts.relations[-1].target_id='employer-b'
    project.facts.extensions[-1].relations[0]=project.facts.relations[-1].model_copy(deep=True)
    verify_witness(project,witness)
    added=Relation(id='new-attachment',kind='extension_of',subjectId='paper-a',targetId='claim',revision=1,active=True)
    project.facts.relations.append(added);project.facts.extensions[0].relations.append(added.model_copy(deep=True))
    with pytest.raises(ValueError,match='authority changed'):verify_witness(project,witness)


@pytest.mark.parametrize('damage',['cycle','missing','inconsistent'])
def test_ownership_closure_rejects_invalid_targets_and_legacy_disagreement(damage):
    before,_=related_workspace();project=before.project
    relation=project.facts.relations[0]
    if damage=='cycle':relation.target_id='paper-a'
    elif damage=='missing':relation.target_id='missing'
    else:
        relation.subject_id='claim';relation.target_id='employer-b'
        project.facts.extensions[0].relations=[]
    if damage!='inconsistent':project.facts.extensions[0].relations[0]=relation.model_copy(deep=True)
    with pytest.raises(ValueError):ownership_witness(project,'paper-a')


@pytest.mark.parametrize('text',['','Exact shared input'])
def test_scope_witness_binds_exact_immutable_scope_and_current_active_cells(text):
    before,_=shared_workspace(text);project=before.project;scope=project.facts.manual_scopes[-1]
    witness=scope_witness(project,scope.id)
    assert [item.cell_id for item in witness.active_cells]==['a-title','b-title']
    project.document.regions[2].blocks=[]
    verify_witness(project,witness)
    project.facts=human_edit(project.facts,'paper-a','title','Separate input')
    with pytest.raises(ValueError,match='authority changed'):verify_witness(project,witness)


@pytest.mark.parametrize('attribute,value',[('item_handle','replacement-handle'),('semantic_type','replacement-type'),
    ('semantic_schema_hash','f'*64),('copy_of_record_id','paper-b')])
def test_scope_witness_checks_each_active_subject_record_identity(attribute,value):
    before,_=shared_workspace();project=before.project;scope=project.facts.manual_scopes[-1]
    witness=scope_witness(project,scope.id)
    setattr(project.facts.extensions[0],attribute,value)
    with pytest.raises(ValueError,match='authority changed'):verify_witness(project,witness)


def test_source_descriptor_hash_also_checks_actual_retained_text():
    before,_=workspace();project=before.project;span=project.facts.extensions[0].cells[0].evidence[0]
    witness=source_witness(project,span);verify_witness(project,witness)
    source=next(value for value in project.sources if value.id==span.source_id)
    unit=next(value for value in source.units if value.id==span.unit_id)
    unit.text='Changed retained source text'
    with pytest.raises(ValueError,match='source'):verify_witness(project,witness)


def test_builtin_field_witness_uses_canonical_cell_and_raw_typed_revision():
    before,_=related_workspace();project=before.project;witness=field_witness(project,'claim','value')
    assert witness.cell_id=='["fact","claim","value"]'
    verify_witness(project,witness)
    claim=next(record for record in project.facts.records if record.id=='claim')
    claim.value.revision+=1;claim.revision+=1
    with pytest.raises(ValueError,match='authority changed'):verify_witness(project,witness)


def test_package_guard_covers_exact_bytes_and_validates_even_matching_tampered_fingerprint():
    before,_=workspace();project=before.project;witness=field_witness(project,'paper-a','title','a-title')
    captured=captured_package_hash(project.template_package)
    verify_witnesses(project,[witness],captured)
    project.template_package.assets[0].bytes_base64='eA=='
    with pytest.raises(ValueError,match='package changed'):verify_witnesses(project,[witness],captured)
    with pytest.raises(ValueError):verify_witnesses(project,[witness],captured_package_hash(project.template_package))


def captured(before,*,start=0,end=None,blocks=None):
    block=before.project.document.regions[2].blocks[0]
    selection={'kind':'blocks','blocks':blocks} if blocks is not None else {'kind':'range','range':{
        'blockId':block.id,'beforeRevision':block.revision,'cellId':None,'field':'content','start':start,
        'end':end if end is not None else sum(len(part.text.encode('utf-16-le'))//2 for part in block.content)}}
    capture=TemplateClipboardCaptureV1(schemaVersion=1,clipboardCaptureId='captured-fragment',projectId=before.project_id,
        sourceSnapshot=snapshot_identity(before),selection=selection)
    return capture_clipboard(before,capture,'a'*64)


def test_complete_capture_is_immutable_and_survives_display_removal_without_retaining_workspace():
    before,_=workspace();retained=captured(before);raw=canonical(retained)
    assert retained.payload.kind=='inline' and retained.payload.content[0].cell_id=='a-title'
    assert [item.cell_id for item in retained.witnesses if item.kind=='field']==['a-title']
    before.project.document.regions[2].blocks=[]
    verify_witnesses(before.project,retained.witnesses,retained.package_fingerprint)
    assert canonical(retained)==raw and b'templatePackage' not in raw and b'workingFacts' not in raw
    before.project.facts=human_edit(before.project.facts,'paper-a','title','Later human value')
    with pytest.raises(ValueError,match='authority changed'):
        verify_witnesses(before.project,retained.witnesses,retained.package_fingerprint)


def test_complete_field_capture_preserves_block_field_provenance_as_exact_run_citations(tmp_path):
    before,sources=workspace();block=before.project.document.regions[2].blocks[0]
    block.provenance=[FieldBinding(kind='field_binding',id='exact-field-provenance',recordId='paper-a',fieldKey='title')]
    editor=TemplateEditor(tmp_path,before,sources)
    capture=editor.capture({'kind':'range','range':{'blockId':block.id,'beforeRevision':block.revision,'cellId':None,
        'field':'content','start':0,'end':12}},'copy-one')
    retained=editor.retained(capture)
    assert retained.payload.content[0].citations==before.project.facts.extensions[0].cells[0].evidence
    assert any(item.kind=='source_span' and item.span==retained.payload.content[0].citations[0]
        for item in retained.witnesses)
    assert editor.current().project.document.regions[2].blocks[0].content[0].citations==[]


def test_partial_literal_capture_keeps_citations_and_survives_former_cell_change():
    before,_=workspace();block=before.project.document.regions[2].blocks[0]
    block.content[0].text='Backend Engineer';block.content[0].styles.bold=True
    retained=captured(before,start=8,end=16);part=retained.payload.content[0]
    assert isinstance(part,PresentedText) and part.text=='Engineer' and part.styles.bold and part.citations
    assert all(item.kind=='source_span' for item in retained.witnesses)
    before.project.facts=human_edit(before.project.facts,'paper-a','title','Different cell value')
    verify_witnesses(before.project,retained.witnesses,retained.package_fingerprint)


def test_split_block_capture_freezes_document_order_and_deduplicates_one_cell_witness():
    before,_=workspace();region=before.project.document.regions[2]
    left,right=split_block(region.blocks[0],7);region.blocks[:1]=[left,right]
    retained=captured(before,blocks=[{'blockId':block.id,'beforeRevision':block.revision} for block in [right,left]])
    assert retained.payload.kind=='blocks' and [block.id for block in retained.payload.blocks]==[left.id,right.id]
    assert [item.cell_id for item in retained.witnesses if item.kind=='field']==['a-title']
    assert retained.payload.blocks[0].content[0].occurrence_id==retained.payload.blocks[1].content[0].occurrence_id


def test_link_label_and_url_have_independent_witnesses_and_contextual_inline_styles():
    before,_=workspace();project=before.project;block=project.document.regions[2].blocks[0]
    project.facts=human_edit(project.facts,'paper-a','journal','https://example.test/exact')
    source=block.content[0]
    block.presentation.overrides.size=17;block.presentation.overrides.alignment='right'
    block.props.text_color='#112233';block.props.background_color='#EFEFEF'
    explicit=block.presentation.model_copy(deep=True);explicit.overrides.size=19
    block.content=[BoundLink(type='bound_link',href='https://example.test/exact',presentation=None,
        labelBinding=FieldRef(recordId='paper-a',fieldKey='title',cellId='a-title',occurrenceId=source.occurrence_id),
        urlBinding=FieldRef(recordId='paper-a',fieldKey='journal',cellId='a-journal',occurrenceId='url-occurrence'),
        content=[PresentedText(type='text',text='Shared ',styles={},presentation=None),
            PresentedText(type='text',text='title',styles={'textColor':'#334455','italic':True},presentation=explicit)])]
    retained=captured(before,end=12);link=retained.payload.content[0]
    assert isinstance(link,BoundLink)
    assert {item.cell_id for item in retained.witnesses if item.kind=='field'}=={'a-title','a-journal'}
    assert link.presentation.overrides.size==17 and link.presentation.overrides.alignment is None
    assert link.content[0].presentation.overrides.size==17 and link.content[0].styles.text_color=='#112233'
    assert link.content[1].presentation.overrides.size==19 and link.content[1].presentation.overrides.alignment=='right'
    assert link.content[1].styles.text_color=='#334455' and link.content[1].styles.italic
    assert all(child.styles.background_color=='#EFEFEF' for child in link.content)
    assert block.content[0].presentation is None and block.content[0].content[0].presentation is None
    project.facts=human_edit(project.facts,'paper-a','journal','https://example.test/new')
    with pytest.raises(ValueError,match='authority changed'):
        verify_witnesses(project,retained.witnesses,retained.package_fingerprint)


@pytest.mark.parametrize('damage',['revision','nested','snapshot'])
def test_capture_rejects_stale_or_unsupported_source_without_mutating_it(damage):
    before,_=workspace();block=before.project.document.regions[2].blocks[0]
    if damage=='revision':
        with pytest.raises(ValueError):captured(before,blocks=[{'blockId':block.id,'beforeRevision':block.revision+1}])
    elif damage=='nested':
        block.children=[before.project.document.regions[2].blocks[1].model_copy(deep=True)]
        with pytest.raises(ValueError,match='unsupported'):captured(before)
    else:
        capture=TemplateClipboardCaptureV1(schemaVersion=1,clipboardCaptureId='stale-capture',projectId=before.project_id,
            sourceSnapshot=snapshot_identity(before),selection={'kind':'blocks','blocks':[{'blockId':block.id,'beforeRevision':1}]})
        before.document_revision+=1
        with pytest.raises(ValueError,match='snapshot'):capture_clipboard(before,capture,'a'*64)
