"""Scoped completion, identity, immutable evidence and delayed rich proposals."""

import asyncio
import json
import threading

import pytest

from packages.resume_core.models.rich_document import FactFieldSpan, ParagraphBlock
from packages.resume_core.models.rich_facts import ClaimRecord, TechnologyRecord
from packages.resume_core.models.rich_mutations import RichMutation, RichSelection
from packages.resume_core.rich_dependencies import dependency, dependencies_current
from packages.resume_core.rich_fields import field_key, occurrences
from packages.resume_core.rich_mutations import apply_rich_mutation, RichMutationFailure
from packages.resume_core.rich_sync import (RichCompletionRequest, RichRewriteRequest, RichRewriteProposal,
    exact_completion, rewrite_steps, selection_parts, selection_checksum)
from tests.recovery.test_rich_images_service import service
from tests.recovery.test_rich_persistence import without_sources, patch
from tests.recovery.generation_fixtures import CreationProvider


def capture(action="edit"):
    return {"sessionId": "session", "actionId": action, "actionToken": 0, "dependencies": []}


def completion(**values):
    return RichCompletionRequest.model_validate({"capture": capture(), "blockIds": ["title"], "movedIds": [], "removedFields": [], "interpret": False, **values})


def mutation(workspace, steps, stamps=(), id="apply"):
    return RichMutation.model_validate({"schemaVersion": 1, "projectId": workspace.project_id,
        "clientMutationId": id, "actionId": id, "kind": "reconciliation", "capture": {**capture(id), "dependencies": list(stamps)}, "steps": steps})


def selection(workspace, id="narrative", start=0, end=6):
    value = RichSelection.model_validate({"kind": "text", "anchor": {"blockId": id, "cellId": None, "offset": start},
        "head": {"blockId": id, "cellId": None, "offset": end}, "blockIds": [id], "capture": capture(), "textSha256": "0" * 64})
    value.text_sha256 = selection_checksum(selection_parts(workspace, value))
    return value


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


def test_dependencies_reject_missing_unknown_field_and_equal_text_replacement_but_allow_unrelated_typing():
    workspace = without_sources()
    stamps = [dependency(workspace, "block", "title"), dependency(workspace, "field", field_key("candidate-1", "title")),
        dependency(workspace, "ownership", "title")]
    edited, _ = apply_rich_mutation(workspace, patch(workspace, "Unrelated"))
    assert dependencies_current(edited, stamps)
    block = workspace.project.document.regions[0].blocks[1]
    replace = {"kind": "put_block", "parentId": "header", "afterId": "name", "beforeRevision": block.revision, "block": block.model_dump(by_alias=True)}
    replaced, _ = apply_rich_mutation(workspace, mutation(workspace, [replace]))
    assert not dependencies_current(replaced, stamps)
    missing = {"kind": "field", "id": '["fact","candidate-1","missing"]', "revision": 1, "fingerprint": None}
    with pytest.raises(RichMutationFailure, match="STALE_MUTATION"):
        apply_rich_mutation(workspace, mutation(workspace, [replace], [missing]))


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


@pytest.mark.asyncio
async def test_rewrite_proposal_is_durable_but_never_publishes_until_validated_session_apply(tmp_path):
    instance, identifier = service(tmp_path); provider = CreationProvider()
    instance.provider_factory = lambda: (provider, "fixture")
    before = instance.read(identifier)
    request = RichRewriteRequest(selection=selection(before), instruction="Clarify")
    reply = await instance.rewrite_rich(identifier, request)
    sync = reply.workspace.sync_records[-1]
    assert sync.ready and sync.status == "pending"
    assert reply.workspace.project.document == before.project.document
    assert len(provider.calls) == 1
    preview = instance.preview(identifier, mutation(before, sync.proposed_steps, [stamp.model_dump(by_alias=True) for stamp in sync.dependencies]))
    assert preview.workspace.project.document != before.project.document
    assert instance.read(identifier).project.document == before.project.document
    restarted = type(instance)(tmp_path / "restart", instance.rules, lambda: pytest.fail("Reopen must not infer"))
    persisted = restarted.read(identifier).sync_records[-1]
    assert persisted.error_code == "OPERATION_INTERRUPTED" and not persisted.ready
    assert restarted.read(identifier).project.document == before.project.document


@pytest.mark.asyncio
async def test_late_rewrite_is_stale_after_depended_edit_and_failure_preserves_authored_content(tmp_path):
    instance, identifier = service(tmp_path)
    started, finish = threading.Event(), threading.Event()
    class Held(CreationProvider):
        def generate(self, request, files, cancel):
            started.set(); finish.wait(5)
            return super().generate(request, files, cancel)
    provider = Held(); instance.provider_factory = lambda: (provider, "fixture")
    workspace = instance.read(identifier); selected = selection(workspace)
    task = asyncio.create_task(instance.rewrite_rich(identifier, RichRewriteRequest(selection=selected, instruction="Clarify")))
    assert await asyncio.to_thread(started.wait, 2)
    block = next(block for block in workspace.project.document.blocks() if block.id == "narrative").model_copy(deep=True)
    block.content[0].text = "Newer typing"
    step = {"kind": "put_block", "parentId": "job-section", "afterId": None, "beforeRevision": block.revision, "block": block.model_dump(by_alias=True), "keepChildren": True}
    instance.mutate(identifier, mutation(workspace, [step], id="newer")); finish.set()
    response = await task
    assert response.workspace.sync_records[-1].status == "stale" and not response.workspace.sync_records[-1].ready
    assert next(block for block in response.workspace.project.document.blocks() if block.id == "narrative").content[0].text == "Newer typing"
    failed = await instance.rewrite_rich(identifier, RichRewriteRequest(selection=selection(instance.read(identifier)), instruction="TEST_ERROR"))
    assert failed.workspace.sync_records[-1].status == "failed"
    assert failed.workspace.sync_records[-1].error_code == "MODEL_DENIED"


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
    from packages.resume_core.models.rich_document import NarrativeCitation
    narrative.provenance = [NarrativeCitation(kind="citation", id="cite", recordId="claim-1", fieldKeys=[], evidence=[]),
        NarrativeCitation(kind="citation", id="tech-cite", recordId="tech-1", fieldKeys=[], evidence=[])]
    section.children = [narrative]
    # Validate the constructed provenance before exercising the domain operation.
    from packages.resume_core.models.rich_document import SectionBlock
    main.blocks.append(SectionBlock.model_validate(section.model_dump(by_alias=True)))
    steps, _ = exact_completion(workspace, completion(blockIds=["moved-claim"], movedIds=["moved-claim"]))
    assert steps[0].record.job_id == "job-2" and steps[0].record.user_corrected
    assert steps[0].record.evidence == original_evidence and claim.job_id == "job-1"
    assert len(steps) == 1 and not technology.user_corrected and technology.job_id == "job-1"
    main.blocks = [block for block in main.blocks if block.id != "job-section"]
    steps, _ = exact_completion(workspace, completion(blockIds=[], removedRecordIds=["job-1"]))
    removed, _ = apply_rich_mutation(workspace, mutation(workspace, steps))
    assert {item.record_id for item in removed.project.facts.tombstones} == {"job-1", "claim-1", "tech-1"}


def test_initial_assembly_retains_job_aliases_exact_scoped_technologies_and_subproject_periods():
    from types import SimpleNamespace
    from packages.resume_core.rich_assembly import assemble_rich
    from packages.resume_core.dates import partial_date
    from packages.resume_core.models.contracts import Subproject, Period
    from packages.resume_core.gui_drafting import validate_draft
    from tests.recovery.draft_fixtures import draft_request, draft_reply, RULES
    request = draft_request(); draft = validate_draft(request, draft_reply(request), RULES)
    normalized = request.normalized
    job = normalized.employment[0]
    claim = next(fact for fact in normalized.facts if fact.kind == "text" and fact.job_id == job.id)
    sub = Subproject(id="subproject-retained", name="Source subproject", factIds=[claim.id],
        period=Period(start=partial_date("2020-02"), end=partial_date("2020-04")))
    job.subprojects.append(sub); claim.subproject_id = sub.id
    before = without_sources()
    workspace = SimpleNamespace(project_id=before.project_id, project_revision=1, document_revision=1,
        created_at=before.created_at, pre_draft=SimpleNamespace(operations=[]))
    project = assemble_rich(workspace, normalized, draft, RULES)
    assert {record.id for record in project.evidence_records} == {fact.id for fact in normalized.facts}
    employment_facts = {fact.id: fact.value.job_id for fact in normalized.facts if fact.kind == "employment"}
    assert employment_facts
    citations = [link for block in project.document.blocks() for link in block.provenance if link.kind == "citation"]
    assert set(employment_facts.values()) <= {link.record_id for link in citations}
    technologies = {record.id: record for record in project.facts.records if record.kind == "technology"}
    stacks = [block for block in project.document.blocks() if block.id.endswith("/stack")]
    assert any(isinstance(span, FactFieldSpan) for block in stacks for span in block.content)
    for block in stacks:
        for span in block.content:
            if isinstance(span, FactFieldSpan):
                assert span.field_key == "display" and technologies[span.record_id].job_id in block.id
    owned = next(block for block in project.document.blocks() if block.type == "section" and block.props.record_id == sub.id)
    assert any("2020-02" in group.text for group in occurrences(project.document).values() if group.record_id == sub.id)
    assert claim.id in {link.record_id for block in owned.children for link in block.provenance if link.kind == "citation"}
    working = next(record for record in project.facts.records if record.id == sub.id)
    assert working.periods[0].start.value.precision == "month" and working.periods[0].end.value.month == 4


@pytest.mark.asyncio
async def test_exact_conflicts_need_explicit_link_update_and_stale_retry_never_infers(tmp_path):
    instance, identifier = service(tmp_path); workspace = instance.workspaces[identifier]
    block = workspace.project.document.regions[0].blocks[1]
    block.content[0].text, block.content[0].binding_root_id = "Senior Engineer", "new-title"
    duplicate = block.model_copy(deep=True); duplicate.id = "old-title"
    duplicate.content[0].text, duplicate.content[0].binding_id, duplicate.content[0].binding_root_id = "Engineer", "other-binding", "other-root"
    workspace.project.document.regions[0].blocks.append(duplicate)
    instance.provider_factory = lambda: pytest.fail("Exact edits must not infer")
    result = await instance.complete_rich(identifier, completion())
    sync = result.workspace.sync_records[-1]
    assert sync.status == "conflict" and sync.ready
    instance.mutate(identifier, mutation(instance.read(identifier), sync.proposed_steps))
    instance.disposition(identifier, sync.id, "applied")
    untouched = next(block for block in instance.read(identifier).project.document.blocks() if block.id == "old-title")
    assert untouched.content[0].text == "Engineer"
    from packages.resume_core.models.rich_mutations import ActionCapture
    resolved = instance.resolve_conflict(identifier, sync.id, ActionCapture.model_validate(capture("resolve")))
    proposal = resolved.workspace.sync_records[-1]
    assert proposal.ready and len(proposal.proposed_steps) == 1
    applied = instance.mutate(identifier, mutation(instance.read(identifier), proposal.proposed_steps, id="resolve"))
    assert next(block for block in applied.workspace.project.document.blocks() if block.id == "old-title").content[0].text == "Senior Engineer"
    assert block.content[0].styles == untouched.content[0].styles
    instance.provider_factory = lambda: (CreationProvider(), "fixture")
    reply = await instance.rewrite_rich(identifier, RichRewriteRequest(selection=selection(instance.read(identifier)), instruction="TEST_ERROR"))
    failed = reply.workspace.sync_records[-1]
    target = next(block for block in instance.read(identifier).project.document.blocks() if block.id == "narrative").model_copy(deep=True)
    target.content[0].text = "Newer words"
    instance.mutate(identifier, mutation(instance.read(identifier), [{"kind": "put_block", "parentId": "job-section", "afterId": None,
        "beforeRevision": target.revision, "block": target.model_dump(by_alias=True), "keepChildren": True}], id="change-scope"))
    instance.provider_factory = lambda: pytest.fail("Stale retry must not infer")
    from resume_api.gui_projects import ProjectFailure
    with pytest.raises(ProjectFailure, match="STALE_SELECTION"):
        await instance.retry_rewrite(identifier, failed.id, ActionCapture.model_validate(capture("retry")))


@pytest.mark.asyncio
async def test_uncertain_narrative_retains_known_value_and_pending_input_in_one_bounded_proposal(tmp_path):
    from packages.resume_core.models.rich_document import NarrativeCitation
    from packages.resume_core.rich_sync import RichReconcileProposal
    from resume_api.providers.content import ContentResult, ReportedUsage
    from packages.resume_core.rich_archive import open_rich_archive
    instance, identifier = service(tmp_path)
    block = next(block for block in instance.workspaces[identifier].project.document.blocks() if block.id == "narrative")
    block.provenance = [NarrativeCitation(kind="citation", id="title-cite", recordId="candidate-1", fieldKeys=["title"], evidence=[])]
    class Uncertain:
        calls = 0
        def generate(self, request, _files, _cancel):
            self.calls += 1
            assert request.policy.timeout_seconds == 180 and not request.policy.allow_repair
            reply = RichReconcileProposal(updates=[], uncertain=[{"recordId": "candidate-1", "fieldKey": "title", "text": "Unclear new role"}])
            return ContentResult(reply, ReportedUsage(), "fixture", request.policy.model, .01, 1)
    provider = Uncertain(); instance.provider_factory = lambda: (provider, "fixture")
    response = await instance.complete_rich(identifier, completion(blockIds=["narrative"], interpret=True))
    sync = response.workspace.sync_records[-1]
    assert provider.calls == 1 and sync.ready and sync.status == "conflict"
    instance.mutate(identifier, mutation(instance.read(identifier), sync.proposed_steps))
    candidate = instance.read(identifier).project.facts.records[0]
    assert candidate.title.value == "Engineer" and candidate.title.raw_text == "Engineer"
    assert candidate.title.status == "pending" and candidate.title.pending_raw_text == "Unclear new role"
    transferred, *_ = open_rich_archive(instance.portable(identifier), "other-store")
    assert transferred.project.facts == instance.read(identifier).project.facts
    assert transferred.sync_records[-1].status == "conflict"


@pytest.mark.asyncio
async def test_cancelled_scoped_attempt_preserves_document_and_cleans_owned_work(tmp_path):
    from packages.resume_core.models.rich_mutations import ActionCapture
    from resume_api.providers.content import ContentFailure
    instance, identifier = service(tmp_path); started = threading.Event()
    class CancelledProvider:
        calls = 0
        def generate(self, _request, _files, cancel):
            self.calls += 1; started.set()
            assert cancel.wait(5)
            raise ContentFailure("CANCELLED")
    provider = CancelledProvider(); instance.provider_factory = lambda: (provider, "fixture")
    before = instance.read(identifier).project.document
    task = asyncio.create_task(instance.rewrite_rich(identifier, RichRewriteRequest(selection=selection(instance.read(identifier)), instruction="Clarify")))
    assert await asyncio.to_thread(started.wait, 2)
    await instance.cancel_sync_action(identifier, ActionCapture.model_validate(capture()))
    result = await task
    assert provider.calls == 1 and result.workspace.project.document == before
    assert result.workspace.sync_records[-1].status == "failed" and result.workspace.sync_records[-1].error_code == "CANCELLED"
    assert not instance.tasks and not instance.files and not instance.cancels
    assert not list((tmp_path / "operations").glob("**/input.json"))


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
