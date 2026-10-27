"""Block clipboard paste uses frozen selection and fresh display identities."""

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import PresentedText
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.rich_mutations import apply_rich_mutation,inline_text
from packages.resume_core.template_authoring import split_block
from packages.resume_core.template_facts import human_edit
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.editor_fixtures import TemplateEditor
from tests.templates.test_clipboard_retention import captured
from tests.templates.test_structural_preparation import intent as structure_intent
from tests.templates.test_template_preparation import response


def block_capture(before,blocks=None):
    return captured(before,blocks=[{'blockId':block.id,'beforeRevision':block.revision}
        for block in (blocks if blocks is not None else before.project.document.regions[2].blocks)])


def block_request(before,clipboard,*,parent='main',after=None,identifier='paste-blocks'):
    return TemplateEditPreparationV1(schemaVersion=1,clientMutationId=identifier,snapshot=response(before).snapshot,
        capture={'sessionId':'session','actionId':identifier,'actionToken':1,'dependencies':[]},
        operations=[{'opId':'paste','kind':'paste_blocks',
            'source':{'kind':'same_project','clipboardCaptureId':clipboard.capture.clipboard_capture_id},
            'placement':{'parentId':parent,'afterId':after}}])


def test_block_capture_paste_keeps_order_styles_provenance_and_fresh_semantic_roots():
    before,_=workspace();originals=before.project.document.regions[2].blocks
    originals[0].props.alignment='right';originals[0].content[0].styles.bold=True
    clipboard=block_capture(before,list(reversed(originals)));raw=canonical(before)
    intent=block_request(before,clipboard,after=originals[-1].id)
    prepared=prepare_edit(response(before),intent,clipboard=clipboard)
    after=prepared.preview.workspace;copied=after.project.document.regions[2].blocks[2:]
    assert [block.content[0].cell_id for block in copied]==['a-title','b-title']
    assert not {block.id for block in copied}&{block.id for block in originals}
    assert all(block.content[0].occurrence_id!=original.content[0].occurrence_id for block,original in zip(copied,originals))
    assert copied[0].props.alignment=='right' and copied[0].content[0].styles.bold
    assert copied[0].presentation==originals[0].presentation and after.project.facts==before.project.facts
    assert canonical(before)==raw and apply_rich_mutation(before,prepared.mutation)[0]==after
    assert canonical(prepare_edit(response(before),intent,clipboard=clipboard))==canonical(prepared)


def test_split_semantic_capture_keeps_one_fresh_occurrence_across_copied_blocks():
    before,_=workspace();region=before.project.document.regions[2]
    left,right=split_block(region.blocks[0],7);region.blocks[:1]=[left,right]
    clipboard=block_capture(before,[right,left])
    prepared=prepare_edit(response(before),block_request(before,clipboard,after=region.blocks[-1].id),clipboard=clipboard)
    copied=prepared.preview.workspace.project.document.regions[2].blocks[-2:]
    spans=[block.content[0] for block in copied]
    assert [span.text for span in spans]==['Shared ','title']
    assert len({span.occurrence_id for span in spans})==1 and spans[0].occurrence_id!=left.content[0].occurrence_id
    assert len({span.binding_id for span in spans})==2
    assert prepared.preview.workspace.project.facts==before.project.facts


def test_partial_block_capture_stays_cited_literal_after_former_cell_changes():
    before,_=workspace();region=before.project.document.regions[2]
    left,right=split_block(region.blocks[0],7);region.blocks[:1]=[left,right]
    clipboard=block_capture(before,[left]);assert isinstance(clipboard.payload.blocks[0].content[0],PresentedText)
    before.project.facts=human_edit(before.project.facts,'paper-a','title','Later authority')
    prepared=prepare_edit(response(before),block_request(before,clipboard,after=region.blocks[-1].id),clipboard=clipboard)
    part=prepared.preview.workspace.project.document.regions[2].blocks[-1].content[0]
    assert isinstance(part,PresentedText) and part.text=='Shared ' and part.citations
    assert prepared.preview.workspace.project.facts==before.project.facts


def test_actual_capture_source_removal_block_paste_full_history_chain_and_portable_transfer(tmp_path):
    before,sources=workspace();editor=TemplateEditor(tmp_path,before,sources)
    blocks=[{'blockId':block.id,'beforeRevision':block.revision} for block in before.project.document.regions[2].blocks]
    capture=editor.capture({'kind':'blocks','blocks':blocks},'copy-blocks')
    retained=editor.retained(capture)
    removal=structure_intent(editor.current(),'remove_occurrences',blocks=blocks)
    removal.client_mutation_id='remove-source';removal.capture.action_id='remove-source'
    editor.edit(removal)
    assert not editor.current().project.document.regions[2].blocks
    # The capture outlives its source: the paste uses the frozen payload, not the removed blocks.
    editor.edit(block_request(editor.current(),retained))
    current=editor.current();copied_ids=[block.id for block in current.project.document.regions[2].blocks]
    assert len(copied_ids)==2 and current.project.facts==before.project.facts
    moved,*_=open_archive_v7(write_zip(archive_payload_v7(current,sources,{})),'transferred')
    assert moved.project.document==current.project.document and moved.project.facts==current.project.facts
    undone=editor.undo('undo-paste',expected='paste-blocks').response.workspace
    assert not undone.project.document.regions[2].blocks
    undone_source=editor.undo('undo-source',expected='remove-source').response.workspace
    assert [block.id for block in undone_source.project.document.regions[2].blocks]==[block.id for block in before.project.document.regions[2].blocks]
    redone_source=editor.redo('redo-source',expected='remove-source').response.workspace
    assert not redone_source.project.document.regions[2].blocks
    redone=editor.redo('redo-paste',expected='paste-blocks').response.workspace
    assert [block.id for block in redone.project.document.regions[2].blocks]==copied_ids


@pytest.mark.parametrize('damage',['inline','package','cell','placement','identity'])
def test_block_paste_rejects_wrong_capture_or_current_authority_without_mutation(damage):
    before,_=workspace();clipboard=captured(before) if damage=='inline' else block_capture(before)
    parent,after='main',None
    if damage=='package':clipboard.package_fingerprint='f'*64
    elif damage=='cell':before.project.facts=human_edit(before.project.facts,'paper-a','title','Changed')
    elif damage=='placement':after='missing-sibling'
    elif damage=='identity':clipboard.capture.project_id='another-project'
    raw=canonical(before)
    with pytest.raises(ValueError):prepare_edit(response(before),block_request(before,clipboard,parent=parent,after=after),clipboard=clipboard)
    assert canonical(before)==raw
