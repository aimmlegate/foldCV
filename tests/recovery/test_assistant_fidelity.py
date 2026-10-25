"""Model-only rewrites preserve authored meaning carriers and actual rich data."""

import json
import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest

from packages.resume_core.assistant_proposals import content_digest
from packages.resume_core.assistant_coverage import Unit, comparison
from packages.resume_core.agent_store import digest
from packages.resume_core.models.agent import AgentQuery
from packages.resume_core.models.assistant_capabilities import AssistantTaskRequestV1
from packages.resume_core.models.assistant_proposals import AssistantAssemblyRequestV1
from packages.resume_core.models.rich_document import FactFieldSpan, Hyperlink
from packages.resume_core.rich_fields import inline_groups
from tests.recovery.test_assistant_proposals import complete, read_document
from tests.support.assistant_fidelity import environment


def test_comparison_cannot_hide_precision_or_metadata_behind_identical_display_text():
    before = Unit("record", "fact", {"rawText": "2024", "status": "known", "value": {"precision": "year", "year": 2024}})
    after = Unit("record", "fact", {"rawText": "2024", "status": "known", "value": {"precision": "month", "year": 2024, "month": 1}})
    change = comparison({"fact:record": before}, {"fact:record": after})[0]
    assert '"precision": "year"' in change.before and '"precision": "month"' in change.after
    old = Unit("block", "structure", {"provenance": []}, "Абзац")
    new = Unit("block", "structure", {"provenance": [{"recordId": "record"}]}, "Абзац")
    change = comparison({"block:one": old}, {"block:one": new})[0]
    assert change.before != change.after and "record" in change.after


def spans(workspace, kind):
    return [span.model_dump(mode="json", by_alias=True) for block in workspace.project.document.blocks()
        for _, content in inline_groups(block) for span in content if isinstance(span, kind)]


async def replacement(session, snapshot, old, new, block_id, *, cell=None, field="content"):
    found = await session.call("find_resume_content", AgentQuery(kind="find", text=old))
    matches = json.loads(found["content"])["matches"]
    match = next(item for item in matches if item["blockId"] == block_id and item["cellId"] == cell)
    return {"kind": "replace_text", "target": {"snapshotId": snapshot.id, "blockId": block_id,
        "cellId": cell, "field": field, "start": match["start"], "end": match["end"]}, "content": [{"text": new}]}


@pytest.mark.asyncio
async def test_whole_cyrillic_rewrite_accounts_for_tables_images_captions_contacts_and_human_facts(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path)
    before = workspace.model_copy(deep=True)
    try:
        snapshot = await read_document(session)
        table = next(block for block in workspace.project.document.blocks() if block.type == "table")
        operations = [await replacement(session, snapshot, "Разрабатывал", "Создавал", "narrative"),
            await replacement(session, snapshot, "Создавал сервисы", "Развивал сервисы", table.id, cell=table.content.rows[1].cells[0].id),
            await replacement(session, snapshot, "Схема проекта", "Архитектура проекта", "test-image", field="caption")]
        request = AssistantAssemblyRequestV1(protocolVersion=1, key="rich_1", taskId="rewrite_resume", phase="append",
            snapshotIds=[snapshot.id], operations=operations)
        draft = await session.call("prepare_edit_batch", request)
        assert "error" not in draft, draft
        ready = await complete(session, draft)
        assert ready["disposition"] == "draft_ready"
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        candidate = value.candidate
        assert candidate.project.facts.model_dump_json() == before.project.facts.model_dump_json()
        assert spans(candidate, FactFieldSpan) == spans(before, FactFieldSpan)
        assert spans(candidate, Hyperlink) == spans(before, Hyperlink)
        assert candidate.project.assets == before.project.assets and candidate.project.template == before.project.template
        assert candidate.project.sources == before.project.sources
        assert [block.id for block in candidate.project.document.blocks()] == [block.id for block in before.project.document.blocks()]
        after_table = next(block for block in candidate.project.document.blocks() if block.id == table.id)
        assert [[cell.id for cell in row.cells] for row in after_table.content.rows] == [[cell.id for cell in row.cells] for row in table.content.rows]
        assert after_table.content.rows[1].cells[0].content[0].styles.italic
        after_image = next(block for block in candidate.project.document.blocks() if block.id == "test-image")
        assert after_image.props.asset_id == before.project.assets[0].id and after_image.props.caption[0].styles.italic
        assert "😀" in candidate.model_dump_json() and "Скрытая строка" not in candidate.model_dump_json()
        assert all(unit.read and unit.state != "unresolved" for unit in value.proposal.coverage)
        assert any(unit.unit_id.startswith("region:") for unit in value.proposal.coverage)
        assert any(unit.unit_id.startswith("cell:") for unit in value.proposal.coverage)
        assert any(unit.unit_id == "facts:collection" for unit in value.proposal.coverage)
        assert [change.effect for change in value.proposal.changes] == ["wording"] * 3
        assert "пропуски извлечения" in value.proposal.reason
        from packages.resume_core.rendering.rich_docx import render_rich_docx
        rendered = render_rich_docx(candidate.project.document,
            {asset.id: projects.images[(workspace.project_id, asset.id)] for asset in candidate.project.assets}, candidate.project.facts)
        with ZipFile(BytesIO(rendered)) as document:
            xml = document.read("word/document.xml").decode()
            assert "Создавал" in xml and "Архитектура проекта" in xml
            relationships = document.read("word/_rels/document.xml.rels").decode()
            assert "mailto:hello@example.invalid" in relationships and "https://example.invalid/portfolio" in relationships
            assert any(hashlib.sha256(document.read(name)).hexdigest() == before.project.assets[0].sha256
                for name in document.namelist() if name.startswith("word/media/"))
        assert projects.storage.read_committed(workspace.project_id)[0] == before
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_mixed_rich_or_fact_replacement_is_rejected_without_dropping_the_draft(tmp_path):
    service, _, _, workspace, session = environment(tmp_path)
    try:
        snapshot = await read_document(session)
        narrative = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
        length = len("".join(span.text if not isinstance(span, Hyperlink) else "".join(child.text for child in span.content) for span in narrative.content).encode("utf-16-le")) // 2
        mixed = {"kind": "replace_text", "target": {"snapshotId": snapshot.id, "blockId": narrative.id,
            "cellId": None, "field": "content", "start": 0, "end": length}, "content": [{"text": "One flat replacement"}]}
        rejected = await session.call("prepare_edit_batch", AssistantAssemblyRequestV1(protocolVersion=1,
            taskId="rewrite_resume", key="mixed", phase="append", operations=[mixed], snapshotIds=[snapshot.id]))
        assert rejected["error"]["code"] == "AGENT_EDIT_INVALID" and "стили" in rejected["reason"]
        factual = await replacement(session, snapshot, "Engineer", "Architect", "title")
        rejected = await session.call("prepare_edit_batch", AssistantAssemblyRequestV1(protocolVersion=1,
            taskId="rewrite_resume", key="fact", phase="append", operations=[factual], snapshotIds=[snapshot.id]))
        assert rejected["error"]["code"] == "AGENT_EDIT_INVALID" and "факты" in rejected["reason"]
        assert service.proposals.list(workspace.project_id) == []
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_source_instructions_cannot_switch_the_frozen_task_or_grant_model_apply(tmp_path):
    _, runtime, projects, workspace, session = environment(tmp_path)
    before = content_digest(workspace)
    try:
        await read_document(session)
        source = await session.call("read_public_page", "https://example.org/vacancy")
        assert source["source"]["id"]
        switched = await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId="correct_facts"))
        assert switched["error"]["code"] == "AGENT_TOOL_DENIED" and "полномочия" in switched["reason"]
        rearmed = await session.call("get_project_resources", AssistantTaskRequestV1(protocolVersion=1, taskId="rewrite_resume"))
        assert rearmed["error"]["code"] == "AGENT_TOOL_DENIED"
        assert (await session.call("apply_edit_batch", {}))["error"]["code"] == "AGENT_TOOL_DENIED"
        assert content_digest(projects.storage.read_committed(workspace.project_id)[0]) == before and not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_explicit_fact_correction_shows_support_and_all_linked_mentions(tmp_path):
    service, _, projects, workspace, session = environment(tmp_path, task_message="Исправь профессию на Architect.")
    try:
        await read_document(session, task_id="correct_facts")
        read = await session.call("get_working_facts", AgentQuery(kind="facts", ids=["candidate-1"]))
        operation = {"kind": "update_fact", "snapshotId": read["snapshot"]["id"], "recordId": "candidate-1", "fieldKey": "title",
            "periodId": None, "value": {"status": "known", "value": "Architect", "text": "Architect"},
            "evidence": [{"kind": "user_correction", "quote": "Исправь профессию на Architect."}]}
        draft = await session.call("prepare_edit_batch", AssistantAssemblyRequestV1(protocolVersion=1,
            taskId="correct_facts", key="correction", phase="append", operations=[operation], snapshotIds=[read["snapshot"]["id"]]))
        assert "error" not in draft, draft
        ready = await complete(session, draft, task_id="correct_facts")
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        assert value.candidate.project.facts.records[0].title.raw_text == "Architect"
        assert any(change.effect == "fact" and "Architect" in change.after for change in value.proposal.changes)
        assert any(change.effect == "wording" and change.before == "Engineer" and change.after == "Architect" for change in value.proposal.changes)
        assert any(change.unit_id.startswith("support:") and "не подтверждают достоверность" in change.after for change in value.proposal.changes)
        assert projects.storage.read_committed(workspace.project_id)[0].project.facts.records[0].title.raw_text == "Engineer"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_one_character_wording_change_keeps_a_small_range_mutation_for_a_large_document(tmp_path):
    service, _, _, workspace, session = environment(tmp_path, large=True)
    try:
        snapshot = await read_document(session)
        operation = await replacement(session, snapshot, "А" * 8, "Б" + "А" * 7, "narrative")
        draft = await session.call("prepare_edit_batch", AssistantAssemblyRequestV1(protocolVersion=1,
            taskId="rewrite_resume", key="one_character", phase="append", operations=[operation], snapshotIds=[snapshot.id]))
        assert "error" not in draft, draft
        ready = await complete(session, draft)
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        assert [step.kind for step in value.batch.mutation.steps] == ["replace_inline_range"]
        assert len(value.batch.mutation.model_dump_json().encode()) < len(workspace.model_dump_json().encode()) // 10
        assert value.candidate.project.facts == workspace.project.facts
        assert len([change for change in value.proposal.changes if change.effect == "wording"]) == 1
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_compound_format_and_rewrite_is_not_staged_or_applied_in_parts(tmp_path):
    service, _, projects, workspace, session = environment(tmp_path)
    before = content_digest(workspace)
    try:
        snapshot = await read_document(session)
        operation = await replacement(session, snapshot, "Разрабатывал", "Создавал", "narrative")
        denied = await session.call("prepare_edit_batch", AssistantAssemblyRequestV1(protocolVersion=1,
            taskId="rewrite_resume", key="compound", phase="finalize", snapshotIds=[snapshot.id],
            operations=[operation, {"kind": "format_template", "snapshotId": snapshot.id}]))
        assert denied["error"]["code"] == "AGENT_EDIT_INVALID" and "отдельных" in denied["reason"]
        assert service.proposals.list(workspace.project_id) == []
        assert content_digest(projects.storage.read_committed(workspace.project_id)[0]) == before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_format_changes_existing_heading_roles_without_rebuilding_authored_content(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path, task_message="Оформи текущее резюме.")
    try:
        assert next(block for block in workspace.project.document.blocks() if block.id == "title").props.level == 1
        snapshot = await read_document(session, task_id="format_document")
        draft = await session.call("prepare_edit_batch", AssistantAssemblyRequestV1(protocolVersion=1,
            taskId="format_document", key="format_only", phase="append", snapshotIds=[snapshot.id],
            operations=[{"kind": "format_template", "snapshotId": snapshot.id}]))
        assert "error" not in draft, draft
        ready = await complete(session, draft, task_id="format_document")
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        candidate = value.candidate
        assert next(block for block in candidate.project.document.blocks() if block.id == "title").props.level == 2
        assert [(block.id, block.content, list(inline_groups(block))) for block in candidate.project.document.blocks()] == [
            (block.id, block.content, list(inline_groups(block))) for block in workspace.project.document.blocks()]
        assert candidate.project.facts == workspace.project.facts
        assert candidate.project.assets == workspace.project.assets and candidate.project.sources == workspace.project.sources
        assert all(change.effect == "structure" for change in value.proposal.changes)
        assert projects.storage.read_committed(workspace.project_id)[0] == workspace and not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_source_reference_requires_a_full_read_and_remains_visible_as_support_not_truth(tmp_path):
    service, _, projects, workspace, session = environment(tmp_path, task_message="Исправь профессию согласно исходнику.", supported_source=True)
    source = workspace.project.sources[0]
    blob = projects.originals[(workspace.project_id, source.id)]
    try:
        await read_document(session, task_id="correct_facts")
        read = await session.call("get_working_facts", AgentQuery(kind="facts", ids=["candidate-1"]))
        operation = {"kind": "update_fact", "snapshotId": read["snapshot"]["id"], "recordId": "candidate-1", "fieldKey": "title",
            "periodId": None, "value": {"status": "known", "value": "Architect", "text": "Architect"},
            "evidence": [{"kind": "source", "sourceId": source.id, "unitId": "cap-u1"}]}
        request = AssistantAssemblyRequestV1(protocolVersion=1, taskId="correct_facts", key="source_fix", phase="append",
            snapshotIds=[read["snapshot"]["id"]], operations=[operation])
        rejected = await session.call("prepare_edit_batch", request)
        assert rejected["error"]["code"] == "AGENT_EVIDENCE_INVALID" and "Перечитайте" in rejected["reason"]
        read_source = await session.call("get_original_source", AgentQuery(kind="source", ids=[source.id]))
        assert read_source["snapshot"]["nextCursor"] is None
        draft = await session.call("prepare_edit_batch", request)
        assert "error" not in draft, draft
        ready = await complete(session, draft, task_id="correct_facts")
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        support = next(change.after for change in value.proposal.changes if change.unit_id.startswith("support:"))
        assert source.original_name in support and blob.decode() in support and "не подтверждают достоверность" in support
        assert projects.storage.read_committed(workspace.project_id)[0].project.facts.records[0].title.raw_text == "Engineer"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_ready_draft_from_an_earlier_scope_policy_is_retained_stale_for_review(tmp_path):
    service, _, _, workspace, session = environment(tmp_path)
    try:
        snapshot = await read_document(session)
        operation = await replacement(session, snapshot, "Разрабатывал", "Создавал", "narrative")
        draft = await session.call("prepare_edit_batch", AssistantAssemblyRequestV1(protocolVersion=1,
            taskId="rewrite_resume", key="old_policy", phase="append", snapshotIds=[snapshot.id], operations=[operation]))
        ready = await complete(session, draft)
        value = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        path = service.proposals.directory(workspace.project_id) / service.proposals.filename(value)
        envelope = json.loads(path.read_text()); envelope["payload"].pop("policyRevision")
        envelope["sha256"] = digest(envelope["payload"])
        path.write_text(json.dumps(envelope))
        old = service.proposals.get(workspace.project_id, ready["proposalId"], 1)
        assert old.proposal.state == "stale" and old.candidate is not None and old.proposal.changes
        assert "новую версию" in old.proposal.reason
        assert old.proposal.content_sha256 == ready["contentSha256"]
    finally:
        await session.close()
