"""Authored field citations survive edits without becoming cell evidence."""

import pytest

from packages.resume_core.gui_archive_zip import write_zip
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_mutations import cut_inline
from packages.resume_core.template_archive import archive_payload_v7,open_archive_v7
from packages.resume_core.template_authoring import allocate_classified_inline,classify_fragment
from packages.resume_core.template_identity import capture_span
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_bound_links import linked_workspace
from tests.templates.test_clipboard_retention import captured
from tests.templates.test_template_preparation import command,proof,response
from packages.resume_core.template_preparation import prepare_text_edit


def test_empty_authored_citations_preserve_existing_canonical_node_bytes():
    before,_=workspace();part=before.project.document.regions[2].blocks[0].content[0]
    old=part.model_dump(mode='json',by_alias=True)
    assert 'citations' not in old and part.citations==[]
    assert type(part).model_validate(old).model_dump_json(by_alias=True)==part.model_dump_json(by_alias=True)
    assert canonical(before)==canonical(WorkspaceV7.model_validate_json(before.model_dump_json(by_alias=True)))


def test_exact_run_citations_survive_cut_allocation_marks_and_partial_literal_copy():
    before,_=workspace();block=before.project.document.regions[2].blocks[0]
    source=before.project.sources[0];extra=capture_span(source,source.units[0],0,5)
    block.content[0].citations=[extra]
    fragment=cut_inline(block.content,1,4)[0]
    assert fragment.citations==[extra]
    allocated=allocate_classified_inline([fragment])[0]
    assert allocated.citations==[extra] and allocated.binding_id!=fragment.binding_id
    prepared=prepare_text_edit(response(before),command(before,kind='set_marks',styles={'bold':True}),proof())
    assert all(part.citations==[extra] for part in prepared.preview.workspace.project.document.regions[2].blocks[0].content)
    literal=classify_fragment(before.project,block,1,4).content[0]
    assert literal.type=='text' and literal.citations==[extra,*before.project.facts.extensions[0].cells[0].evidence]
    retained=captured(before)
    assert any(item.kind=='source_span' and item.span==extra for item in retained.witnesses)
    assert before.project.facts.extensions[0].cells[0].evidence!=[extra]


@pytest.mark.parametrize('linked',[False,True])
def test_field_citation_integrity_and_archive_round_trip_include_link_children(linked):
    before,sources=linked_workspace() if linked else workspace()
    block=before.project.document.regions[2].blocks[0]
    part=block.content[0].content[0] if linked else block.content[0]
    source=before.project.sources[0];part.citations=[capture_span(source,source.units[0],0,5)]
    before=WorkspaceV7.model_validate(before.model_dump(mode='json',by_alias=True))
    block=before.project.document.regions[2].blocks[0]
    part=block.content[0].content[0] if linked else block.content[0]
    restored,*_=open_archive_v7(write_zip(archive_payload_v7(before,sources,{})),'restored-project')
    assert canonical(restored.project.document)==canonical(before.project.document)
    assert restored.project.facts==before.project.facts
    part.citations[0].slice_hash='f'*64
    with pytest.raises(ValueError):WorkspaceV7.model_validate(before.model_dump(mode='json',by_alias=True))
    with pytest.raises(ValueError):archive_payload_v7(before,sources,{})
