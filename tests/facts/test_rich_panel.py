"""Facts-panel scope, evidence, precise periods and reversible document effects."""

import pytest

from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_fields import inline_groups, occurrences
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import RichPanelProposal, narrative_steps, panel_mutation
from tests.facts.panel_fixtures import apply, edit
from tests.support.rich import capture, mutation, without_sources


def test_candidate_panel_updates_all_exact_occurrences_and_preserves_marks_and_evidence():
    workspace = without_sources()
    original = workspace.project.document.regions[0].blocks[1]
    original.content[0].styles.italic = True
    copy = original.model_copy(deep=True); copy.id = 'second-title'; copy.content[0].binding_id = 'second-title-binding'
    workspace.project.document.regions[1].blocks.append(copy)
    before = workspace.project.evidence_records.copy()
    changed = apply(workspace, values={'title': 'Senior Engineer', 'location': 'Belgrade / remote'})
    assert changed.project.facts.records[0].title.value == 'Senior Engineer'
    assert changed.project.facts.records[0].location.value == 'Belgrade / remote'
    assert changed.project.facts.records[0].evidence == workspace.project.facts.records[0].evidence
    titles = [g for g in occurrences(changed.project.document).values() if g.key == 'title']
    assert len(titles) == 2 and all(g.text == 'Senior Engineer' and g.spans[0].styles.italic for g in titles)
    assert changed.project.evidence_records == before
    assert changed.project.document.regions[2] == workspace.project.document.regions[2]


def test_panel_creation_and_precise_unknown_fields_do_not_fabricate_evidence_or_level():
    workspace = without_sources()
    changed = apply(workspace, operation='add', recordKind='technology', values={'display': 'Custom Toolkit'})
    technology = changed.project.facts.records[-1]
    assert technology.job_id is None and technology.evidence == [] and technology.origin == 'user'
    assert technology.canonical_id.value is None
    changed = apply(changed, operation='add', recordKind='education', values={'institution': 'University', 'completion': '2020-02-29'})
    education = changed.project.facts.records[-1]
    assert education.completion.value.precision == 'day' and education.completion.value.day == 29
    changed = apply(changed, recordId=education.id, values={'completion': 'around spring'})
    assert changed.project.facts.records[-1].completion.value is None
    assert changed.project.facts.records[-1].completion.raw_text == 'around spring'
    changed = apply(changed, operation='add', recordKind='language', values={'language': 'French'})
    assert changed.project.facts.records[-1].level.value is None
    assert workspace.project.facts.records[1].periods == changed.project.facts.records[1].periods


def test_job_technology_edit_and_removal_leave_other_job_and_claims_unchanged():
    workspace = without_sources()
    first = apply(workspace, operation='add', recordKind='technology', jobId='job-1', values={'display': 'Python'})
    a = first.project.facts.records[-1]
    second = apply(first, operation='add', recordKind='employment', values={'employer': 'Other'})
    job = second.project.facts.records[-1]
    second = apply(second, operation='add', recordKind='technology', jobId=job.id, values={'display': 'Python'})
    b = second.project.facts.records[-1]
    changed = apply(second, recordId=a.id, values={'display': 'Rust'})
    assert next(r for r in changed.project.facts.records if r.id == b.id).display.value == 'Python'
    assert any(g.record_id == a.id and g.text == 'Rust' for g in occurrences(changed.project.document).values())
    removed = apply(changed, operation='remove', recordId=a.id)
    assert any(t.record_id == a.id for t in removed.project.facts.tombstones)
    assert not any(g.record_id == a.id for g in occurrences(removed.project.document).values())
    assert any(g.record_id == b.id and g.text == 'Python' for g in occurrences(removed.project.document).values())
    assert next(b for b in removed.project.document.blocks() if b.id == 'narrative').content == next(b for b in workspace.project.document.blocks() if b.id == 'narrative').content


def test_job_removal_removes_owned_subtree_and_associations_and_inverse_restores_them():
    workspace = without_sources()
    workspace = apply(workspace, operation='add', recordKind='employment', values={'employer': 'New', 'start': '2021-01', 'end': '2022-03'})
    job = workspace.project.facts.records[-1]
    workspace = apply(workspace, operation='add', recordKind='technology', jobId=job.id, values={'display': 'Go'})
    tech = workspace.project.facts.records[-1]
    removed, _ = apply_rich_mutation(workspace, panel_mutation(workspace, edit(workspace, operation='remove', recordId=job.id)))
    assert not {job.id, tech.id} & {r.id for r in removed.project.facts.records}
    assert not any(getattr(b.props, 'record_id', None) == job.id for b in removed.project.document.blocks())
    owner = next(b for b in workspace.project.document.blocks() if getattr(b.props, 'record_id', None) == job.id)
    inverse = [{'kind': 'put_record', 'beforeRevision': next(t.revision for t in removed.project.facts.tombstones if t.record_id == r.id), 'record': r.model_dump(by_alias=True)} for r in [job, tech]]
    inverse.append({'kind': 'put_block', 'parentId': 'main', 'afterId': removed.project.document.regions[2].blocks[-1].id, 'beforeRevision': None, 'block': owner.model_dump(by_alias=True)})
    restored, _ = apply_rich_mutation(removed, RichMutation(schemaVersion=1, projectId=removed.project_id,
        clientMutationId='undo-panel', actionId='undo-panel', kind='undo', capture=capture(), steps=inverse))
    assert {job.id, tech.id} <= {r.id for r in restored.project.facts.records}
    assert any(g.record_id == tech.id and g.text == 'Go' for g in occurrences(restored.project.document).values())
    assert next(r for r in restored.project.facts.records if r.id == job.id).periods[0].start.value.precision == 'month'


def test_period_add_remove_preserves_original_precision_and_source_evidence():
    workspace = without_sources(); before = workspace.project.facts.records[1].periods[0].model_copy(deep=True)
    changed = apply(workspace, operation='add_period', recordId='job-1')
    job = changed.project.facts.records[1]; added = job.periods[-1]
    assert job.periods[0] == before and added.evidence == []
    changed = apply(changed, recordId=job.id, values={f'period:{added.id}:start': '2020-02-29', f'period:{added.id}:end': '2020-03-05'})
    assert changed.project.facts.records[1].periods[-1].start.value.precision == 'day'
    changed = apply(changed, operation='remove_period', recordId=job.id, periodId=added.id)
    assert changed.project.facts.records[1].periods == [before]
    assert not any(added.id in g.key for g in occurrences(changed.project.document).values())


def test_panel_rejects_stale_revision_foreign_owner_and_nonpanel_fields_without_partial_effect():
    workspace = without_sources(); snapshot = workspace.model_dump_json()
    for values in [{'factsRevision': 999}, {'values': {'evidence': 'replace'}}, {'recordId': 'missing'},
        {'operation': 'add', 'recordKind': 'technology', 'jobId': 'missing'}]:
        with pytest.raises(ValueError):
            panel_mutation(workspace, edit(workspace, **values))
        assert workspace.model_dump_json() == snapshot


def test_narrative_panel_patch_preserves_structure_styles_links_and_rejects_unrelated_scope():
    workspace = without_sources(); block = next(b for b in workspace.project.document.blocks() if b.id == 'narrative')
    block.content[0].styles.bold = True
    proposal = RichPanelProposal(updates=[{'blockId': block.id, 'text': 'Corrected narrative'}])
    steps = narrative_steps(workspace, [block], proposal)
    changed, _ = apply_rich_mutation(workspace, mutation(workspace, steps))
    result = next(b for b in changed.project.document.blocks() if b.id == block.id)
    assert result.content[0].styles.bold and result.type == block.type and result.children == block.children
    assert result.provenance == block.provenance
    with pytest.raises(ValueError, match='SCOPE'):
        narrative_steps(workspace, [], proposal)


def test_moving_user_created_exact_technology_changes_only_its_working_job():
    from packages.resume_core.rich_sync import exact_completion, RichCompletionRequest
    workspace = without_sources()
    workspace = apply(workspace, operation='add', recordKind='technology', jobId='job-1', values={'display':'Go'})
    technology = workspace.project.facts.records[-1]
    workspace = apply(workspace, operation='add', recordKind='employment', values={'employer':'New'})
    job = workspace.project.facts.records[-1]
    block = next(b for b in workspace.project.document.blocks() if any(getattr(s,'record_id',None) == technology.id for _,c in inline_groups(b) for s in c))
    owner = next(b for b in workspace.project.document.blocks() if getattr(b.props,'record_id',None) == job.id)
    moved, _ = apply_rich_mutation(workspace, mutation(workspace,[{'kind':'move_block','blockId':block.id,'beforeRevision':block.revision,'parentId':owner.id,'afterId':None}]))
    steps, _ = exact_completion(moved, RichCompletionRequest(capture=capture(), blockIds=[block.id], movedIds=[block.id], removedFields=[], interpret=False))
    assert len(steps) == 1 and steps[0].record.job_id == job.id
    assert steps[0].record.evidence == [] and steps[0].record.origin == 'user'


def test_cited_focus_label_gets_exact_technology_update_without_matching_unlinked_text():
    from packages.resume_core.models.rich_document import ParagraphBlock
    workspace = apply(without_sources(), operation='add', recordKind='technology', values={'display':'Python'})
    technology = workspace.project.facts.records[-1]
    raw = {'id':'focus-label','revision':1,'type':'paragraph','props':{},'children':[],
        'content':[{'type':'text','text':'Python','styles':{'bold':True}}],
        'provenance':[{'kind':'citation','id':'focus-ref','recordId':technology.id,'fieldKeys':[],'evidence':[]}]}
    workspace.project.document.regions[1].blocks.append(ParagraphBlock.model_validate(raw))
    other = ParagraphBlock.model_validate({**raw,'id':'unlinked-label','provenance':[]})
    workspace.project.document.regions[1].blocks.append(other)
    changed = apply(workspace, recordId=technology.id, values={'display':'Rust'})
    assert any(g.record_id == technology.id and g.text == 'Rust' and g.block_ids == ['focus-label'] for g in occurrences(changed.project.document).values())
    assert next(b for b in changed.project.document.blocks() if b.id == 'focus-label').content[0].styles.bold
    assert next(b for b in changed.project.document.blocks() if b.id == 'unlinked-label').content[0].text == 'Python'
    removed = apply(workspace, operation='remove', recordId=technology.id)
    assert next(b for b in removed.project.document.blocks() if b.id == 'focus-label').content == []
    assert next(b for b in removed.project.document.blocks() if b.id == 'unlinked-label').content[0].text == 'Python'


def test_closing_open_period_and_reopening_it_updates_the_existing_endpoint_span():
    from packages.resume_core.models.rich_document import ParagraphBlock
    workspace = without_sources(); job = workspace.project.facts.records[1]; period = job.periods[0]
    from packages.resume_core.rich_fields import set_text
    set_text(job, f'period:{period.id}:present', 'по настоящее время')
    raw={'id':'date-endpoint','revision':1,'type':'paragraph','props':{},'children':[], 'provenance':[],
        'content':[{'type':'fact_field','bindingId':'endpoint','recordId':job.id,'fieldKey':f'period:{period.id}:present','text':'по настоящее время','styles':{'italic':True},'syncedFactRevision':1}]}
    workspace.project.document.regions[2].blocks.append(ParagraphBlock.model_validate(raw))
    closed = apply(workspace, recordId=job.id, values={f'period:{period.id}:end':'2020-04',f'period:{period.id}:present':''})
    span=next(b for b in closed.project.document.blocks() if b.id=='date-endpoint').content[0]
    assert span.text=='2020-04' and span.field_key.endswith(':end') and span.styles.italic
    opened = apply(closed, recordId=job.id, values={f'period:{period.id}:present':'по настоящее время'})
    span=next(b for b in opened.project.document.blocks() if b.id=='date-endpoint').content[0]
    assert span.text=='по настоящее время' and span.field_key.endswith(':present') and span.styles.italic


def test_removing_period_retains_other_edits_in_the_same_block():
    from packages.resume_core.models.rich_document import FactFieldSpan, StyledText
    from packages.resume_core.models.rich_mutations import PutBlock
    from packages.resume_core.rich_dependencies import placements
    from packages.resume_core.rich_panel import period_blocks, put_block
    workspace = without_sources()
    project = workspace.project
    record = project.facts.records[1]
    old = record.model_copy(deep=True)
    block = next(block for block in project.document.blocks() if block.id == "narrative")
    block.content = [FactFieldSpan(type="fact_field", bindingId="remove", bindingRootId="root", recordId=record.id,
        fieldKey=f"period:{record.periods[0].id}:start", text="2020", syncedFactRevision=1, styles={}),
        StyledText(type="text", text="Old employer", styles={})]
    staged = block.model_copy(deep=True)
    staged.content[-1].text = "New employer"
    record.periods = []
    positions = placements(project.document)
    steps = period_blocks(project, record, old, [put_block(staged, positions)], positions)
    updated = next(step.block for step in steps if isinstance(step, PutBlock) and step.block.id == block.id)
    assert len(updated.content) == 1 and updated.content[0].text == "New employer"
