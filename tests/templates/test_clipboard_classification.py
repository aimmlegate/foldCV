"""Capture freezes completeness before any destination identity is allocated."""

import pytest

from packages.resume_core import template_authoring
from packages.resume_core.models.template_document import BoundLink,FieldOccurrence,ManualScopeSpan,PresentedText
from packages.resume_core.rich_mutations import RichMutationFailure
from packages.resume_core.template_authoring import (allocate_classified_blocks,classify_blocks,classify_fragment,
    classify_inline,split_block)
from packages.resume_core.template_preparation_ids import EditIdAllocator,existing_ids
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_manual_scope_occurrences import shared_workspace
from tests.templates.test_sync_preparation import link_mentions
from tests.templates.test_template_synchronization import conflicted_move


def test_capture_preserves_source_keys_without_running_destination_allocation(monkeypatch):
    before,_=workspace();block=before.project.document.regions[2].blocks[0];raw=canonical(before)
    def forbidden(*_args,**_kwargs):raise AssertionError('capture allocated a destination identity')
    monkeypatch.setattr(template_authoring,'allocate_id',forbidden)
    captured=classify_blocks(before.project,[block])[0]
    inline=classify_inline(before.project,block.content)
    assert captured==block and inline==block.content and canonical(before)==raw


@pytest.mark.parametrize('shared',[False,True])
def test_split_capture_freezes_complete_or_partial_authority_and_allocates_fresh_consistent_roots(shared):
    before,_=shared_workspace() if shared else workspace()
    region=before.project.document.regions[2]
    left,right=split_block(region.blocks[0],5);region.blocks[:1]=[left,right]
    selected=classify_blocks(before.project,[left,right]);partial=classify_blocks(before.project,[right])
    kind=ManualScopeSpan if shared else FieldOccurrence
    assert all(isinstance(block.content[0],kind) for block in selected)
    assert isinstance(partial[0].content[0],PresentedText) and partial[0].content[0].citations
    assert [block.id for block in selected]==[left.id,right.id]
    captured=canonical([block.model_dump(mode='json',by_alias=True) for block in selected])
    old_root=selected[0].content[0].occurrence_id
    before.project.document.regions[2].blocks=[]
    for record in before.project.facts.extensions:
        for cell in record.cells:cell.raw_input='Later independent wording'
    allocated=allocate_classified_blocks(selected,
        id_factory=EditIdAllocator('template-project', 'paste-captured','copy',existing_ids(before)))
    assert canonical([block.model_dump(mode='json',by_alias=True) for block in selected])==captured
    spans=[block.content[0] for block in allocated]
    assert len({part.occurrence_id for part in spans})==1 and spans[0].occurrence_id!=old_root
    assert {block.id for block in allocated}.isdisjoint({left.id,right.id})
    fragments=[part.fragment_id if shared else part.binding_id for part in spans]
    assert len(set(fragments))==2


@pytest.mark.parametrize('text',['','Exact 😀 input'])
def test_scope_fragment_capture_keeps_empty_anchor_and_literal_partial_citations(text):
    before,_=shared_workspace(text);block=before.project.document.regions[2].blocks[0]
    captured=classify_fragment(before.project,block,0,len(text.encode('utf-16-le'))//2)
    assert captured.id==block.id and captured.content==block.content
    if text:
        partial=classify_fragment(before.project,block,0,5).content[0]
        assert isinstance(partial,PresentedText) and partial.text=='Exact' and partial.citations
        assert not hasattr(partial,'scope_id')
        with pytest.raises(RichMutationFailure,match='RICH_RANGE_INVALID'):classify_fragment(before.project,block,7,8)


def test_independent_bound_link_capture_keeps_refs_until_allocation_and_partial_becomes_cited_literal():
    before,_sources,_command=conflicted_move();link_mentions(before)
    block=next(block for block in before.project.document.blocks() if block.id=='block-paper-a')
    source=block.content[0];assert isinstance(source,BoundLink)
    captured=classify_blocks(before.project,[block]);assert captured[0].content[0]==source
    partial=classify_fragment(before.project,block,0,3).content[0]
    assert partial.type=='link' and partial.href==source.href
    assert all(isinstance(child,PresentedText) for child in partial.content)
    assert partial.content[0].citations and not hasattr(partial,'label_binding')
    allocated=allocate_classified_blocks(captured,
        id_factory=EditIdAllocator('template-project', 'paste-link','copy',existing_ids(before)))[0].content[0]
    assert isinstance(allocated,BoundLink) and allocated.label_binding.cell_id==source.label_binding.cell_id
    assert allocated.label_binding.occurrence_id!=source.label_binding.occurrence_id
    assert all(isinstance(child,PresentedText) for child in allocated.content)
