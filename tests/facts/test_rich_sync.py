"""Scoped exact completion and structured rewrite steps over the rich document."""

from packages.resume_core.models.rich_document import NarrativeCitation, ParagraphBlock, SectionBlock
from packages.resume_core.models.rich_facts import ClaimRecord, TechnologyRecord
from packages.resume_core.models.rich_mutations import RichSelection
from packages.resume_core.rich_fields import occurrences
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_sync import RichRewriteProposal, exact_completion, rewrite_steps, selection_parts
from tests.support.rich import capture, completion, mutation, selection, without_sources


def test_exact_styled_fragments_complete_as_one_field_and_clear_to_unknown():
    workspace = without_sources()
    block = workspace.project.document.regions[0].blocks[1]
    original = block.content[0]
    original.text, original.binding_root_id = "Senior ", "title-root"
    other = original.model_copy(deep=True); other.binding_id, other.text, other.styles.bold = "part-two", "Engineer", True
    block.content = [original, other]
    steps, conflicts = exact_completion(workspace, completion())
    assert not conflicts and len(steps) == 1
    updated, _ = apply_rich_mutation(workspace, mutation(workspace, steps))
    candidate = updated.project.facts.records[0]
    assert candidate.title.value == "Senior Engineer" and candidate.title.user_corrected and candidate.user_corrected
    assert candidate.evidence == workspace.project.facts.records[0].evidence
    assert all(span.synced_fact_revision == candidate.title.revision for span in updated.project.document.regions[0].blocks[1].content)
    block.content = []
    steps, _ = exact_completion(workspace, completion(removedFields=[{"recordId": "candidate-1", "fieldKey": "title", "rootId": "title-root"}]))
    assert steps[0].record.title.value is None and steps[0].record.title.status == "unknown"
    assert steps[0].record.title.raw_text == ""


def test_duplicate_occurrences_conflict_instead_of_concatenating_values():
    workspace = without_sources(); block = workspace.project.document.regions[0].blocks[1]
    original = block.content[0]; original.text, original.binding_root_id = "Senior Engineer", "edited"
    copy = block.model_copy(deep=True); copy.id = "copy"; copy.content[0].binding_id = "copy-binding"
    copy.content[0].binding_root_id, copy.content[0].text = "copy-root", "Engineer"
    workspace.project.document.regions[0].blocks.append(copy)
    steps, conflicts = exact_completion(workspace, completion())
    assert steps[0].record.title.value == "Senior Engineer"
    assert conflicts == [("candidate-1", "title")]
    assert len(occurrences(workspace.project.document)) == 2


def test_partial_rewrite_to_list_keeps_outside_rich_text_and_links_in_paragraphs():
    workspace = without_sources(); selected = selection(workspace, start=7, end=11)
    output = ParagraphBlock(type="paragraph", id="ignored", revision=1, props={}, content=[{"type": "text", "text": "New", "styles": {"italic": True}}], children=[], provenance=[])
    raw = output.model_dump(by_alias=True); raw["type"] = "bullet_list"
    proposal = RichRewriteProposal.model_validate({"replacements": [{"blockId": "narrative", "blocks": [raw]}]})
    steps = rewrite_steps(workspace, selected, proposal)
    updated, _ = apply_rich_mutation(workspace, mutation(workspace, steps))
    children = next(block for block in updated.project.document.blocks() if block.id == "job-section").children
    assert children[0].id == "narrative" and children[0].type == "paragraph"
    assert children[0].content[0].text == "Styled " and children[0].content[0].styles.bold
    assert children[1].type == "bullet_list" and children[1].content[0].text == "New"
    assert children[2].type == "paragraph" and children[2].content[0].type == "link"
    assert children[2].content[0].href == "https://example.com/path?q=exact"


def test_claim_move_corrects_working_owner_and_owned_job_deletion_tombstones_related_facts():
    workspace = without_sources(); job = workspace.project.facts.records[1]
    other = job.model_copy(deep=True); other.id = "job-2"; other.periods = []
    workspace.project.facts.records.append(other)
    original_evidence = job.evidence
    claim = ClaimRecord.model_validate({"id": "claim-1", "kind": "claim", "revision": 1, "origin": "source", "evidence": [span.model_dump(by_alias=True) for span in original_evidence],
        "jobId": "job-1", "subprojectId": None, "value": {"value": "Delivered", "rawText": "Delivered", "status": "known", "revision": 1, "pendingRawText": None}})
    workspace.project.facts.records.append(claim)
    technology = TechnologyRecord.model_validate({"id": "tech-1", "kind": "technology", "revision": 1, "origin": "source", "evidence": [],
        "jobId": "job-1", "subprojectId": None, "display": {"value": "Python", "rawText": "Python", "status": "known", "revision": 1, "pendingRawText": None},
        "canonicalId": {"value": "python", "rawText": "python", "status": "known", "revision": 1, "pendingRawText": None}})
    workspace.project.facts.records.append(technology)
    main = workspace.project.document.regions[2]
    section = main.blocks[0].model_copy(deep=True); section.id, section.props.record_id = "other-job", "job-2"
    narrative = section.children[0]; narrative.id = "moved-claim"; narrative.children = []
    narrative.provenance = [NarrativeCitation(kind="citation", id="cite", recordId="claim-1", fieldKeys=[], evidence=[]),
        NarrativeCitation(kind="citation", id="tech-cite", recordId="tech-1", fieldKeys=[], evidence=[])]
    section.children = [narrative]
    # Validate the constructed provenance before exercising the domain operation.
    main.blocks.append(SectionBlock.model_validate(section.model_dump(by_alias=True)))
    steps, _ = exact_completion(workspace, completion(blockIds=["moved-claim"], movedIds=["moved-claim"]))
    assert steps[0].record.job_id == "job-2" and steps[0].record.user_corrected
    assert steps[0].record.evidence == original_evidence and claim.job_id == "job-1"
    assert len(steps) == 1 and not technology.user_corrected and technology.job_id == "job-1"
    main.blocks = [block for block in main.blocks if block.id != "job-section"]
    steps, _ = exact_completion(workspace, completion(blockIds=[], removedRecordIds=["job-1"]))
    removed, _ = apply_rich_mutation(workspace, mutation(workspace, steps))
    assert {item.record_id for item in removed.project.facts.tombstones} == {"job-1", "claim-1", "tech-1"}


def test_multicell_rich_rewrite_preserves_unselected_table_text_cell_ids_and_marks():
    workspace = without_sources(); table = next(block for block in workspace.project.document.blocks() if block.type == "table")
    cells = [cell for row in table.content.rows for cell in row.cells]
    assert len(cells) >= 2
    selected = RichSelection.model_validate({"kind": "table_cells", "anchor": {"blockId": table.id, "cellId": cells[0].id, "offset": 1},
        "head": {"blockId": table.id, "cellId": cells[1].id, "offset": 2}, "blockIds": [table.id], "capture": capture(), "textSha256": "0" * 64})
    parts = selection_parts(workspace, selected)
    proposal = RichRewriteProposal.model_validate({"replacements": [{"blockId": table.id, "cellId": part[4].id, "blocks": [{"id": "ignored", "revision": 1,
        "type": "paragraph", "props": {}, "children": [], "provenance": [], "content": [{"type": "text", "text": "X", "styles": {"bold": True}}]}]} for part in parts]})
    updated, _ = apply_rich_mutation(workspace, mutation(workspace, rewrite_steps(workspace, selected, proposal)))
    actual = next(block for block in updated.project.document.blocks() if block.id == table.id)
    actual_cells = [cell for row in actual.content.rows for cell in row.cells]
    assert [cell.id for cell in actual_cells] == [cell.id for cell in cells]
    assert actual_cells[0].content[0].text == "H" and actual_cells[0].content[1].text == "X" and actual_cells[0].content[1].styles.bold
    assert actual_cells[1].content[0].text == "X"
    assert actual_cells[1].content[-1].text == cells[1].content[0].text[2:]
    assert actual_cells[2:] == cells[2:]


def test_full_block_rewrite_keeps_nested_children_exactly():
    workspace = without_sources()
    parent = next(block for block in workspace.project.document.blocks() if block.id == "bullet")
    selected = selection(workspace, "bullet", end=0).model_copy(update={"kind": "blocks"})
    output = parent.model_copy(deep=True)
    output.content[0].text = "Changed parent"
    output.children = []
    proposal = RichRewriteProposal(replacements=[{"blockId": parent.id, "blocks": [output]}])
    changed, _ = apply_rich_mutation(workspace, mutation(workspace, rewrite_steps(workspace, selected, proposal)))
    current = next(block for block in changed.project.document.blocks() if block.id == parent.id)
    assert current.content[0].text == "Changed parent"
    assert current.children == parent.children
