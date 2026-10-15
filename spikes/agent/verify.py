"""Verify the exact GUI export bytes and synthetic saved state without inference."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.resume_core.agent_store import AgentStore
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rendering.rich_docx import validate_export
from packages.resume_core.rich_archive import open_rich_archive
from packages.resume_core.rich_timeline import timeline_report
from spikes.agent.native_proof import CHECK, RESEARCH, TEXT, VACANCY


def semantic(value):
    if isinstance(value, list): return [semantic(item) for item in value]
    if isinstance(value, dict): return {key: semantic(item) for key, item in value.items() if key not in {"revision", "syncedFactRevision"}}
    return value


def blocks(document):
    result = {}
    def visit(items):
        for block in items:
            value = block.model_dump(mode="json", by_alias=True)
            value["children"] = [child.id for child in block.children]
            result[block.id] = value; visit(block.children)
    for region in document.regions: visit(region.blocks)
    return result


def verify_native(root, phase):
    state = AgentStore(root / "data").load("project-1")
    conversation = state.conversations[0]
    editable = phase == "research_edit"
    run = next(item for item in reversed(conversation.runs) if item.allow_edits == editable)
    journal = next(item for item in state.journals if item.run_id == run.id)
    assert journal.request.message == (RESEARCH if editable else CHECK)
    assert run.state == "completed" and run.error is None
    assert run.allow_web == editable and run.model == "gpt-6-luna"
    reports = [json.loads(path.read_text()) for path in root.glob("attempt-*-runtime.json")]
    report = next(item for item in reports if item["runId"] == run.id)
    assert report["state"] == "completed" and report["error"] is None and report["nativeStarted"]
    assert report["ownedPidsGone"] and report["mcpListenerClosed"] and report["operationRemoved"]
    assert not report["profileExclusionLost"] and not report["operationDirectories"] and not report["diagnosticErrors"]
    assert report["timings"]["cleanup"] <= 5 and report["timings"]["active"] <= 180
    assert report["timings"]["startup"] <= 15
    rows = [json.loads(line) for line in (root / "tool-diagnostics.jsonl").read_text().splitlines()]
    rows = [row for row in rows if row["runId"] == run.id and row["phase"] == "validated_call"]
    assert all(row["allowEdits"] == editable and row["allowWeb"] == editable for row in rows)
    passed = [row["name"] for row in rows if row["code"] is None]
    assert {"get_resume_context", "publish_findings", "check_resume"} <= set(passed)
    sources = [source for source in conversation.sources if source.final_url == VACANCY]
    assert sources and all(source.text for source in sources)
    source_ids = {source.id for source in sources}
    findings = [finding for finding in conversation.findings if finding.run_id == run.id]
    assert findings and all(finding.anchors for finding in findings)
    assert source_ids.intersection(identifier for finding in findings for identifier in finding.source_ids)
    answer = next(message for message in reversed(conversation.messages) if message.run_id == run.id and message.role == "assistant")
    assert source_ids.intersection(reference.id for reference in answer.sources)
    assert any(identifier in answer.text for identifier in source_ids)
    current = WorkspaceV6.model_validate(json.loads((root / "data/projects/project-1/workspace.json").read_text()))
    before_name = "before-research.json" if editable else "before-check.json"
    before = WorkspaceV6.model_validate(json.loads((root / before_name).read_text()))
    assert before.project.facts == current.project.facts and before.sync_records == current.sync_records
    if editable:
        assert report["webActions"] >= 1
        assert {"read_public_page", "prepare_edit_batch", "apply_edit_batch"} <= set(passed)
        apply_index = passed.index("apply_edit_batch")
        assert "get_resume_context" in passed[apply_index + 1:] and "check_resume" in passed[apply_index + 1:]
        assert any(source.run_id == run.id for source in sources)
        receipts = [batch.receipt for batch in journal.batches if batch.receipt is not None]
        assert len(receipts) == 1 and len(journal.batches) == 1
        receipt = receipts[0]
        assert receipt.durable and receipt.disposition == "saved" and receipt.error is None
        assert run.saved_batch_id == receipt.batch_id
        replay = next(item for item in current.mutation_replay if item.client_mutation_id == receipt.client_mutation_id)
        assert replay.request_sha256 == receipt.request_sha256 and replay.resulting_revision == receipt.project_revision
        old, new = blocks(before.project.document), blocks(current.project.document)
        assert old.keys() == new.keys()
        assert [(region.id, region.role, [block.id for block in region.blocks]) for region in before.project.document.regions] == [
            (region.id, region.role, [block.id for block in region.blocks]) for region in current.project.document.regions]
        assert all(semantic(old[key]) == semantic(new[key]) for key in old if key != "narrative")
        assert "".join(span["text"] for span in old["narrative"]["content"]) == TEXT
        assert "".join(span["text"] for span in new["narrative"]["content"]) == "Built REST APIs in Python and wrote unit tests with pytest."
        assert all(span["styles"]["bold"] for span in new["narrative"]["content"])
    else:
        assert report["webActions"] == 0 and "read_public_page" not in [row["name"] for row in rows]
        assert not journal.batches and run.saved_batch_id is None
        denials = [row for row in rows if row["name"] == "prepare_edit_batch"]
        assert len(denials) == 1 and denials[0]["code"] == "AGENT_TOOL_DENIED"
        assert any(row["name"] == "get_conversation_context" and source_ids.intersection(row.get("storedIds", [])) for row in rows)
        assert current == before
    result = {"schemaVersion": 1, "status": "passed", "phase": phase, "attempt": report["attempt"],
        "runId": run.id, "model": run.model, "allowEdits": run.allow_edits, "allowWeb": run.allow_web,
        "sourceIds": sorted(source_ids), "findingIds": [finding.id for finding in findings],
        "calls": rows, "runtime": report, "factsUnchanged": True, "unrelatedContentUnchanged": True,
        "beforeRevisions": [before.project_revision, before.document_revision, before.project.facts.revision],
        "afterRevisions": [current.project_revision, current.document_revision, current.project.facts.revision],
        "answer": answer.text, "claimInspection": "Edited text contains only the four original claims: Python, REST APIs, unit tests and pytest. Vacancy-only experience remains findings."}
    name = "research-proof.json" if editable else "check-only-proof.json"
    (root / name).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def verify(root, imported_id):
    read = lambda path: WorkspaceV6.model_validate(json.loads(path.read_text()))
    before = read(root / "before-research.json")
    current = read(root / "data/projects/project-1/workspace.json")
    imported = read(root / "data/projects" / imported_id / "workspace.json")
    assert current.project and before.project and imported.project and imported_id != current.project_id
    old, new = blocks(before.project.document), blocks(current.project.document)
    assert old.keys() == new.keys()
    assert [(region.id, region.role, [block.id for block in region.blocks]) for region in before.project.document.regions] == [
        (region.id, region.role, [block.id for block in region.blocks]) for region in current.project.document.regions]
    assert all(semantic(old[key]) == semantic(new[key]) for key in old if key != "narrative")
    expected = "Built REST APIs in Python and wrote unit tests with pytest."
    assert "".join(span["text"] for span in new["narrative"]["content"]) == expected
    assert all(part["styles"]["bold"] for part in new["narrative"]["content"])
    assert before.project.facts == current.project.facts and before.sync_records == current.sync_records
    assert semantic(current.project.document.model_dump()) == semantic(imported.project.document.model_dump())
    assert current.project.facts == imported.project.facts
    validate_export(current.project.document)
    timeline = timeline_report(current)
    docx, portable = root / "ui-resume.docx", root / "ui-project.foldcv"
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    with ZipFile(docx) as archive:
        xml = ET.fromstring(archive.read("word/document.xml"))
        paragraphs = ["".join(node.itertext()) for node in xml.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")]
        assert any(expected in text for text in paragraphs)
        assert not any("Built REST APIs in Python. Wrote unit tests with pytest." in text for text in paragraphs)
    with ZipFile(portable) as archive:
        paths = archive.namelist()
        assert not any(any(word in path.lower() for word in ("assistant", "conversation", "auth", "settings")) for path in paths)
        packaged = json.loads(archive.read("workspace.json"))
        assert packaged["mutationReplay"] == [item.model_dump(mode="json", by_alias=True) for item in current.mutation_replay]
        manifest = json.loads(archive.read("manifest.json"))
        render = next(entry for entry in manifest["entries"] if entry["role"] == "render")
        assert archive.read(render["path"]) == docx.read_bytes()
    validated, *_ = open_rich_archive(portable.read_bytes(), "project-offline-verify")
    assert validated.project.facts == current.project.facts
    assert validated.mutation_replay == [] and imported.mutation_replay == []
    sidecar = AgentStore(root / "data")
    assert not sidecar.load(imported_id).conversations
    state = sidecar.load(current.project_id)
    receipts = [item.receipt for journal in state.journals for item in journal.batches if item.receipt and item.receipt.durable]
    assert len(receipts) == 1
    receipt = receipts[0]
    replay = next(item for item in current.mutation_replay if item.client_mutation_id == receipt.client_mutation_id)
    assert replay.request_sha256 == receipt.request_sha256 and replay.resulting_revision == receipt.project_revision
    native_passed = all((root / name).exists() and json.loads((root / name).read_text())["status"] == "passed"
        for name in ("research-proof.json", "check-only-proof.json"))
    return {"schemaVersion": 1, "status": "passed_artifacts_only", "nativeAcceptance": "both mandatory outcomes passed" if native_passed else "blocked; research final native check and check-only remain unproved",
        "originId": current.project_id, "importedId": imported_id, "changedBlock": "narrative", "finalText": expected,
        "unrelatedBlocksUnchanged": True, "factsUnchanged": True, "syncRecordsUnchanged": True,
        "docx": {"sha256": digest(docx.read_bytes()), "bytes": docx.stat().st_size, "matchesEmbeddedPortableRender": True},
        "portable": {"sha256": digest(portable.read_bytes()), "bytes": portable.stat().st_size, "assistantStateIncluded": False},
        "importedConversationCount": 0, "durableReceipt": receipt.model_dump(mode="json", by_alias=True),
        "deterministicChecks": {"export": "valid", "timelineWarnings": len(timeline.warnings)},
        "manualWord": "pending"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, required=True); parser.add_argument("--imported-id")
    parser.add_argument("--native-phase", choices=("research_edit", "check_only"))
    args = parser.parse_args()
    if args.native_phase:
        result = verify_native(args.root, args.native_phase)
    else:
        if not args.imported_id: parser.error("--imported-id is required for artifact verification")
        result = verify(args.root, args.imported_id)
        (args.root / "artifact-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
