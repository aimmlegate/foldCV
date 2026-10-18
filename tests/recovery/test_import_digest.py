"""Digest editing, linked reconciliation and existing canonical bytes."""

import json

import pytest

from packages.resume_core.models.rich_facts import ClaimRecord, WorkingFacts
from packages.resume_core.models.rich_document import NarrativeCitation, StyledText
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rich_assembly import field
from packages.resume_core.rich_panel import panel_mutation
from packages.resume_core.rich_mutations import apply_rich_mutation, locate
from packages.resume_core.background_inverse import inverse_mutation
from packages.resume_core.rich_format import format_document
from packages.resume_core.rich_sync import RichReconcileProposal
from packages.resume_core.rich_dependencies import dependencies_current
from tests.recovery.test_rich_panel import edit
from tests.recovery.test_rich_synchronization import completion, mutation
from tests.recovery.test_rich_images_service import service
from tests.recovery.test_rich_persistence import without_sources


def digest_workspace():
    workspace = without_sources()
    workspace.project.facts.mode = "digest"
    claim = ClaimRecord(id="digest", kind="claim", revision=1, origin="source", evidence=[], jobId=None,
        subprojectId=None, value=field("Вероятно Orion: Python API. Команда ускорила релизы. Роль не указана."))
    workspace.project.facts.records.append(claim)
    block = next(b for b in workspace.project.document.blocks() if b.id == "narrative")
    block.provenance = [NarrativeCitation(kind="citation", id="digest-cite", recordId=claim.id, fieldKeys=["value"], evidence=[])]
    other = block.model_copy(deep=True)
    other.id, other.provenance[0].id = "related", "related-cite"
    other.content = [StyledText(type="text", text="Команда ускорила релизы; роль не указана.", styles={})]
    workspace.project.document.regions[2].blocks.append(other)
    return workspace


def test_digest_add_edit_remove_and_undo_keep_source_text_and_mode():
    workspace = digest_workspace()
    original_document = workspace.project.document.model_copy(deep=True)
    changed, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
        edit(workspace, recordId="digest", values={"value": "Orion: Python API, роль требует уточнения."})))
    assert changed.project.facts.mode == "digest" and changed.project.document.regions == original_document.regions
    assert next(r for r in changed.project.facts.records if r.id == "digest").value.user_corrected
    added, _ = apply_rich_mutation(changed, panel_mutation(changed,
        edit(changed, operation="add", recordKind="claim", values={"value": "Нужно уточнить даты."})))
    assert added.project.document.regions == original_document.regions
    note = added.project.facts.records[-1]
    assert note.kind == "claim" and note.origin == "user" and note.evidence == []
    removed, _ = apply_rich_mutation(added, panel_mutation(added, edit(added, operation="remove", recordId="digest")))
    assert not any(link.kind == "citation" and link.record_id == "digest" for b in removed.project.document.blocks() for link in b.provenance)
    assert [b.content for b in removed.project.document.blocks()] == [b.content for b in original_document.blocks()]
    undo = inverse_mutation(added, removed, mutation_id="undo-digest", session_id="test")
    restored, _ = apply_rich_mutation(removed, undo)
    assert next(r for r in restored.project.facts.records if r.id == "digest").value.raw_text == "Orion: Python API, роль требует уточнения."
    assert any(link.kind == "citation" and link.record_id == "digest" for b in restored.project.document.blocks() for link in b.provenance)
    assert restored.project.facts.mode == "digest"


def test_reformat_retains_interpreted_regions_and_current_wording():
    workspace = digest_workspace()
    assert format_document(workspace.project.document, workspace.project.facts) == workspace.project.document


def test_assistant_reads_every_digest_entry_including_unlinked_notes():
    from resume_api.agent.context import query_value
    from packages.resume_core.models.agent import AgentQuery
    workspace = digest_workspace()
    added, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
        edit(workspace, operation="add", recordKind="claim", values={"value": "Нужно уточнить образование."})))
    result = query_value(added, AgentQuery(kind="facts"))
    assert result["records"] == added.project.facts.records
    assert result["mode"] == "digest" and result["extraction"] == added.project.facts.extraction
    assert any(record.kind == "claim" and "образование" in record.value.raw_text for record in result["records"])


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent", [False, True])
async def test_digest_reconciliation_keeps_other_linked_paragraphs_and_checks_their_versions(tmp_path, concurrent):
    api, identifier = service(tmp_path)
    workspace = digest_workspace()
    api.workspaces[identifier] = workspace
    api.persist(identifier)
    async def infer(_identifier, sync, payload, result_type):
        assert result_type is RichReconcileProposal
        assert [b["id"] for b in payload["blocks"]] == ["narrative"]
        assert [b["id"] for b in payload["relatedBlocks"]] == ["related"]
        assert "Роль не указана" in next(r for r in payload["facts"] if r["id"] == "digest")["value"]["rawText"]
        if concurrent:
            current = api.read(identifier)
            block = next(b for b in current.project.document.blocks() if b.id == "related").model_copy(deep=True)
            block.content[0].text = "Changed team context"
            siblings, index, parent = locate(current.project.document, block.id)
            request = mutation(current, [{"kind": "put_block", "parentId": parent.id,
                "afterId": siblings[index - 1].id if index else None, "beforeRevision": block.revision,
                "block": block.model_dump(by_alias=True)}])
            api.mutate(identifier, request)
        return RichReconcileProposal(updates=[{"recordId": "digest", "fieldKey": "value",
            "text": "Вероятно Orion: Rust API. Команда ускорила релизы. Роль не указана."}], records=[], uncertain=[])
    api.sync_content = infer
    reply = await api.complete_rich(identifier, completion(blockIds=["narrative"], interpret=True))
    sync = reply.workspace.sync_records[-1]
    if concurrent:
        assert sync.status == "stale" and not sync.ready
        assert not dependencies_current(api.read(identifier), sync.dependencies)
    else:
        assert sync.ready and sync.status == "pending"
        changed, _ = apply_rich_mutation(api.read(identifier), mutation(workspace, sync.proposed_steps))
        digest = next(r for r in changed.project.facts.records if r.id == "digest")
        assert "Rust" in digest.value.raw_text and "Роль не указана" in digest.value.raw_text
        assert changed.project.document.regions == workspace.project.document.regions


@pytest.mark.asyncio
async def test_mixed_exact_fields_update_the_digest_but_digest_edits_flag_protected_text(tmp_path):
    from packages.resume_core.rich_panel import RichPanelSyncRequest
    from tests.recovery.test_rich_synchronization import capture
    api, identifier = service(tmp_path)
    workspace = digest_workspace()
    title = workspace.project.document.regions[0].blocks[1]
    title.content[0].text = "Senior Engineer"
    title.provenance.append(NarrativeCitation(kind="citation", id="title-digest", recordId="digest", fieldKeys=["value"], evidence=[]))
    api.workspaces[identifier] = workspace
    api.persist(identifier)
    async def infer(_identifier, sync, payload, result_type):
        assert result_type is RichReconcileProposal
        assert [b["id"] for b in payload["blocks"]] == ["title"]
        assert {r["id"] for r in payload["facts"]} == {"digest"}
        return RichReconcileProposal(updates=[{"recordId": "digest", "fieldKey": "value",
            "text": "Senior Engineer; команда ускорила релизы."}], records=[], uncertain=[])
    api.sync_content = infer
    reply = await api.complete_rich(identifier, completion(interpret=True))
    sync = reply.workspace.sync_records[-1]
    assert sync.ready and {step.record.id for step in sync.proposed_steps} == {"candidate-1", "digest"}
    for block in workspace.project.document.blocks():
        if block.id != "title":
            block.provenance = [link for link in block.provenance if not (link.kind == "citation" and link.record_id == "digest")]
    result = await api.panel_rich(identifier, RichPanelSyncRequest(capture=capture("panel"), recordIds=["digest"]))
    assert result.workspace.sync_records[-1].status == "conflict"
    assert result.workspace.sync_records[-1].error_code == "NARRATIVE_REQUIRES_SCOPED_EDIT"


def test_structured_defaults_do_not_change_old_canonical_bytes():
    workspace = without_sources()
    raw = workspace.model_dump_json(by_alias=True)
    assert '"mode"' not in raw and '"importDraft"' not in raw
    assert WorkspaceV6.model_validate_json(raw).model_dump_json(by_alias=True) == raw
    assert WorkingFacts.model_validate(json.loads(raw)["project"]["facts"]).mode == "structured"
