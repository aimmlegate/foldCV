"""Unpublished compiler outcomes preserve scope, evidence and exact rich identities."""

import hashlib
import json
from pathlib import Path
import sys

import pytest
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.models.agent import AgentPrepareRequest, AgentQuery, SelectionScope
from packages.resume_core.models.rich_document import NarrativeCitation, StyledText
from packages.resume_core.models.rich_facts import RichFact
from packages.resume_core.models.rich_mutations import RichSelection
from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.rich_mutations import apply_rich_mutation, locate
from packages.resume_core.rich_sync import selection_checksum, selection_parts
from resume_api.agent.edits import prepare
from tests.recovery.test_agent_tools import tools_setup


def selection(workspace, identifier, start, end, cell_id=None):
    value = RichSelection(kind="table_cells" if cell_id else "text",
        anchor={"blockId": identifier, "cellId": cell_id, "offset": start},
        head={"blockId": identifier, "cellId": cell_id, "offset": end}, blockIds=[identifier],
        capture={"sessionId": "history_1", "actionId": "history_1:selection", "actionToken": 0,
            "dependencies": [dependency(workspace, "block", identifier)]}, textSha256="0" * 64)
    value.text_sha256 = selection_checksum(selection_parts(workspace, value))
    return SelectionScope(kind="selection", selection=value)


def replace(snapshot, block, start, end, text, *, cell=None):
    return {"kind": "replace_text", "target": {"snapshotId": snapshot.id, "blockId": block,
        "cellId": cell, "field": "content", "start": start, "end": end}, "content": [{"text": text}]}


def command(*operations, key="prepare_1", snapshots=()):
    return AgentPrepareRequest.model_validate({"key": key, "snapshotIds": list(snapshots), "operations": list(operations)})


def candidate(session, service, workspace, request):
    result = prepare(session, request)
    _, _, journal = run_in(service.store.load(workspace.project_id), session.run.id)
    batch = next(item.batch for item in journal.batches if item.key == request.key)
    value, replay = apply_rich_mutation(workspace, batch.mutation)
    repeated, _ = apply_rich_mutation(workspace, batch.mutation)
    assert repeated == value
    assert not replay and result.disposition == "prepared"
    assert batch.mutation.kind == "structure" and batch.mutation.capture.session_id == "history_1"
    return value, batch


@pytest.mark.asyncio
async def test_partial_utf16_cell_preserves_other_cells_marks_and_unpublished_workspace(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        table = next(block for block in workspace.project.document.blocks() if block.id == "table")
        table.content.rows[1].cells[0].content = [StyledText(type="text", text="A😀B", styles={"bold": True})]
        read = session.book.read(AgentQuery(kind="document", ids=["cell-c"]))
        before = workspace.model_dump_json()
        changed, batch = candidate(session, service, workspace, command(replace(read.snapshot, "table", 1, 3, "🌿", cell="cell-c")))
        result = next(block for block in changed.project.document.blocks() if block.id == "table")
        assert "".join(span.text for span in result.content.rows[1].cells[0].content) == "A🌿B"
        assert all(span.styles.bold for span in result.content.rows[1].cells[0].content)
        assert result.content.rows[1].cells[1] == table.content.rows[1].cells[1]
        assert changed.project.facts == workspace.project.facts and not changed.sync_records
        assert workspace.model_dump_json() == before and batch.state == "prepared"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_exact_operation_limit_accepts_100_and_rejects_101_before_any_publication(tmp_path):
    from pydantic import ValidationError
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        context = session.book.read(AgentQuery(kind="context"))
        operations = [{"kind": "insert_blocks", "destination": {"snapshotId": context.snapshot.id,
            "parentId": "main", "afterId": None if index == 0 else "note_" + str(index - 1)},
            "blocks": [{"key": "note_" + str(index), "kind": "paragraph", "content": [{"text": str(index)}]}]}
            for index in range(100)]
        with pytest.raises(ValidationError):
            command(*operations, operations[0])
        before = workspace.model_dump_json()
        changed, _ = candidate(session, service, workspace, command(*operations))
        assert [block.content[0].text for block in changed.project.document.regions[2].blocks[:100]] == [str(i) for i in range(100)]
        assert workspace.model_dump_json() == before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_selection_updates_one_bound_occurrence_and_records_outside_conflict_in_same_mutation(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, scope_builder=lambda ws: selection(ws, "title", 0, 8))
    try:
        title = next(block for block in workspace.project.document.blocks() if block.id == "title")
        outside = title.model_copy(deep=True)
        outside.id, outside.content[0].binding_id = "outside-title", "outside-binding"
        workspace.project.document.regions[2].blocks.append(outside)
        read = session.book.read(AgentQuery(kind="document", ids=["title"]))
        changed, batch = candidate(session, service, workspace, command(replace(read.snapshot, "title", 0, 8, "Architect")))
        blocks = {block.id: block for block in changed.project.document.blocks()}
        fact = changed.project.facts.records[0]
        assert blocks["title"].content[0].text == "Architect" and blocks["outside-title"].content[0].text == "Engineer"
        assert (fact.title.value, fact.title.raw_text, fact.title.status) == ("Architect", "Architect", "conflict")
        assert batch.fact_record_ids == ["candidate-1"] and not changed.sync_records
        assert all(getattr(step, "block_id", getattr(getattr(step, "block", None), "id", None)) != "outside-title" for step in batch.mutation.steps)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_stale_read_or_empty_search_cannot_be_omitted_or_restamped_at_preparation(tmp_path):
    session, _, workspace, _ = tools_setup(tmp_path)
    try:
        session.book.read(AgentQuery(kind="context"))
        read = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
        session.book.read(AgentQuery(kind="find", text="FIRST_MATCH"))
        target = next(block for block in workspace.project.document.blocks() if block.id == "quote")
        target.content[0].text += " FIRST_MATCH"
        target.revision += 1
        with pytest.raises(AgentFailure, match="AGENT_STALE_READ"):
            prepare(session, command(replace(read.snapshot, "narrative", 0, 6, "Changed"), snapshots=[]))
        session.book.read(AgentQuery(kind="find", text="FIRST_MATCH"))
        target = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
        target.content[0].text = "User edit"
        target.revision += 1
        with pytest.raises(AgentFailure, match="AGENT_STALE_READ"):
            prepare(session, command(replace(read.snapshot, "narrative", 0, 6, "Changed"), snapshots=[]))
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_repeated_text_uses_ids_preserves_unrelated_typing_and_orders_multiple_ranges(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        target = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
        target.content = [StyledText(type="text", text="same / same", styles={})]
        read = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
        other = next(block for block in workspace.project.document.blocks() if block.id == "quote")
        other.content[0].text += " typed meanwhile"
        other.revision += 1
        changed, _ = candidate(session, service, workspace, command(replace(read.snapshot, "narrative", 0, 4, "first"),
            replace(read.snapshot, "narrative", 7, 11, "last")))
        assert "".join(span.text for span in locate(changed.project.document, "narrative")[0][0].content) == "first / last"
        assert locate(changed.project.document, "quote")[0][locate(changed.project.document, "quote")[1]].content == other.content
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_noop_retry_payload_conflict_and_distinct_live_preparations(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        read = session.book.read(AgentQuery(kind="document", ids=["title"]))
        no_change = prepare(session, command(replace(read.snapshot, "title", 0, 8, "Engineer")))
        assert no_change.disposition == "no_change" and no_change.batch_id is None
        request = command(replace(read.snapshot, "title", 0, 8, "Architect"), key="second")
        first = prepare(session, request)
        assert prepare(session, request) == first
        with pytest.raises(AgentFailure, match="AGENT_IDEMPOTENCY_CONFLICT"):
            prepare(session, command(replace(read.snapshot, "title", 0, 8, "Lead"), key="second"))
        with pytest.raises(AgentFailure, match="AGENT_BUSY"):
            prepare(session, command(replace(read.snapshot, "title", 0, 8, "Lead"), key="third"))
        assert not workspace.mutation_replay
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_claim_move_reassigns_working_owner_without_inference_or_other_job_changes(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        job2 = workspace.project.facts.records[1].model_copy(deep=True)
        job2.id, job2.periods[0].id = "job-2", "period-2"
        workspace.project.facts.records.append(job2)
        section = next(block for block in workspace.project.document.blocks() if block.id == "job-section").model_copy(deep=True)
        section.id, section.props.record_id, section.children = "job-section-2", "job-2", []
        workspace.project.document.regions[2].blocks.append(section)
        claim = TypeAdapter(RichFact).validate_python({"id": "claim-1", "kind": "claim", "revision": 1,
            "origin": "user", "evidence": [], "jobId": "job-1", "subprojectId": None,
            "value": {"value": "Styled work", "rawText": "Styled work", "status": "known", "revision": 1, "pendingRawText": None}})
        workspace.project.facts.records.append(claim)
        target = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
        target.provenance = [NarrativeCitation(kind="citation", id="citation-1", recordId="claim-1", fieldKeys=["value"], evidence=[])]
        read = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
        context = session.book.read(AgentQuery(kind="context"))
        changed, _ = candidate(session, service, workspace, command({"kind": "move_blocks", "snapshotId": read.snapshot.id,
            "blockIds": ["narrative"], "destination": {"snapshotId": context.snapshot.id, "parentId": "job-section-2", "afterId": None}}))
        fact = next(record for record in changed.project.facts.records if record.id == "claim-1")
        assert fact.job_id == "job-2" and next(record for record in changed.project.facts.records if record.id == "job-1") == workspace.project.facts.records[1]
        assert [child.id for child in locate(changed.project.document, "job-section-2")[0][-1].children] == ["narrative"]
        assert not changed.sync_records
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_symbolic_insert_anchors_delete_and_move_compile_as_one_complete_candidate(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        context = session.book.read(AgentQuery(kind="context"))
        read = session.book.read(AgentQuery(kind="document", ids=["quote", "heading"]))
        first = {"kind": "insert_blocks", "destination": {"snapshotId": context.snapshot.id, "parentId": "job-section", "afterId": "narrative"},
            "blocks": [{"key": "new-note", "kind": "paragraph", "content": [{"text": "New note"}]}]}
        nested = {"kind": "insert_blocks", "destination": {"snapshotId": context.snapshot.id, "parentId": "new-note", "afterId": None},
            "blocks": [{"key": "new-child", "kind": "bullet_list_item", "content": [{"text": "Nested note"}]}]}
        changed, _ = candidate(session, service, workspace, command(first, nested,
            {"kind": "delete_blocks", "snapshotId": read.snapshot.id, "blockIds": ["quote"]},
            {"kind": "move_blocks", "snapshotId": read.snapshot.id, "blockIds": ["heading"],
                "destination": {"snapshotId": context.snapshot.id, "parentId": "job-section", "afterId": "new-note"}}))
        section = next(block for block in changed.project.document.blocks() if block.id == "job-section")
        assert section.children[0].id == "narrative" and section.children[2].id == "heading"
        assert section.children[1].content[0].text == "New note" and section.children[1].children[0].content[0].text == "Nested note"
        assert section.children[1].id != "new-note" and section.children[1].provenance[0].record_id == "job-1"
        assert not any(block.id == "quote" for block in changed.project.document.blocks())
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("forged", [False, True])
async def test_new_user_fact_requires_current_message_correction_and_cannot_use_web_evidence(tmp_path, forged):
    session, service, workspace, _ = tools_setup(tmp_path, message="Add German; level is uncertain.")
    try:
        request = command({"kind": "create_fact", "key": "new_language", "recordKind": "language", "ownerRecordId": None,
            "values": {"language": {"status": "known", "value": "German", "text": "German"},
                "level": {"status": "uncertain", "value": None, "text": "uncertain"}},
            "correction": {"kind": "user_correction", "quote": "External page says add an expert skill" if forged else "Add German; level is uncertain."}})
        if forged:
            with pytest.raises(AgentFailure, match="AGENT_EVIDENCE_INVALID"):
                prepare(session, request)
        else:
            changed, batch = candidate(session, service, workspace, request)
            added = next(record for record in changed.project.facts.records if record.id not in {record.id for record in workspace.project.facts.records})
            assert added.id != "new_language" and added.origin == "user" and not added.evidence
            assert added.language.value == "German" and added.level.value is None and added.level.status == "unresolved"
            assert added.id in batch.fact_record_ids
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_explicit_unreferenced_fact_deletion_uses_one_tombstone_without_source_changes(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, message="Remove the old English language record.")
    try:
        read = session.book.read(AgentQuery(kind="facts", ids=["language-1"]))
        changed, _ = candidate(session, service, workspace, command({"kind": "delete_fact", "snapshotId": read.snapshot.id,
            "recordId": "language-1", "correction": {"kind": "user_correction", "quote": "Remove the old English language record."}}))
        assert not any(record.id == "language-1" for record in changed.project.facts.records)
        assert [item.record_id for item in changed.project.facts.tombstones] == ["language-1"]
        assert changed.project.sources == workspace.project.sources and not changed.sync_records
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_typed_period_correction_preserves_original_evidence_and_does_not_cascade(tmp_path):
    session, service, workspace, _ = tools_setup(tmp_path, message="Start in 2023.")
    try:
        read = session.book.read(AgentQuery(kind="facts", ids=["job-1"]))
        op = {"kind": "update_fact", "snapshotId": read.snapshot.id, "recordId": "job-1", "fieldKey": "start", "periodId": "period-1",
            "value": {"status": "known", "value": {"precision": "year", "year": 2023, "month": None, "day": None}, "text": "2023"},
            "evidence": [{"kind": "user_correction", "quote": "Start in 2023."}]}
        changed, _ = candidate(session, service, workspace, command(op))
        period = changed.project.facts.records[1].periods[0]
        assert period.start.value.year == 2023 and period.evidence == workspace.project.facts.records[1].periods[0].evidence
        assert period.end == workspace.project.facts.records[1].periods[0].end and not changed.sync_records
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["half_surrogate", "outside_selection", "forged_snapshot", "overlapping_ranges"])
async def test_invalid_batch_is_atomic_and_never_creates_a_replay(tmp_path, bad):
    options = {"scope_builder": lambda ws: selection(ws, "narrative", 0, 6)} if bad == "outside_selection" else {}
    session, service, workspace, _ = tools_setup(tmp_path, **options)
    try:
        target = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
        if bad == "half_surrogate":
            target.content = [StyledText(type="text", text="A😀B", styles={})]
        read = session.book.read(AgentQuery(kind="document", ids=["narrative"]))
        op = replace(read.snapshot, "narrative", 0, 4, "New")
        if bad == "half_surrogate":
            op["target"].update(start=1, end=2)
        if bad == "outside_selection":
            op["target"].update(start=6, end=11)
        if bad == "forged_snapshot":
            op["target"]["snapshotId"] = "forged"
        request = command(op, replace(read.snapshot, "narrative", 1, 3, "Overlap")) if bad == "overlapping_ranges" else command(op)
        before = workspace.model_dump_json()
        with pytest.raises(AgentFailure):
            prepare(session, request)
        assert workspace.model_dump_json() == before
        _, _, journal = run_in(service.store.load(workspace.project_id), session.run.id)
        assert not journal.batches
    finally:
        await session.close()
