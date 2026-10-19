"""Template omissions retain exact source text, facts and an explicit reason."""

from io import BytesIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from packages.resume_core.import_agent import ImportFailure, assemble_agent_import
from packages.resume_core.import_content import draft_content, update_content
from packages.resume_core.models.importing import ImportContent
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_presentation import authored_text
from tests.recovery.test_agent_import import draft_fixture, selected_service
from tests.recovery.test_import_content import paragraphs_fixture


@pytest.mark.asyncio
async def test_source_only_sections_preserve_facts_evidence_and_portable_source_but_do_not_render(tmp_path, monkeypatch):
    texts = ["Candidate", "Project result stays visible.", "Опыт вождения", "Права категории B",
        "Дополнительно", "Разрешение на работу: Россия", "Сфера работы", "Информационные технологии",
        "Дата обновления резюме кандидатом", "20 июня 2025"]
    sources, parts, paragraphs = paragraphs_fixture(texts)
    content = ImportContent(facts=[{"text": text, "refs": [f"p{i+1}"]} for i, text in enumerate(texts) if i >= 2],
        sections=[{"category": "identity", "blocks": [{"type": "heading", "refs": ["p1"]}]},
            {"category": "experience", "blocks": [{"type": "paragraph", "refs": ["p2"]}]},
            {"category": "other", "blocks": [{"type": "source_only", "refs": [f"p{i}-p{i+1}"],
                "reason": "Не входит в выбранный шаблон."} for i in [3, 5, 7, 9]]}])
    saved = update_content(draft_fixture(), content, paragraphs, parts)
    outlines = [item["section"] for item in draft_content(saved, paragraphs) if "section" in item]
    assert update_content(saved, ImportContent(sections=outlines), paragraphs, parts) == saved
    saved.finished = True
    baseline = saved.model_copy(deep=True)
    for block in baseline.blocks:
        if block.kind == "source_only":
            block.kind, block.reason = "paragraph", None
    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    try:
        workspace = service.workspaces[identifier]
        workspace.pre_draft.sources, workspace.pre_draft.selected_source_id = sources, sources[0].id
        project = assemble_agent_import(workspace, saved)
        original = assemble_agent_import(workspace, baseline)
        assert project.facts == original.facts and project.evidence_records == original.evidence_records
        assert project.sources == original.sources == sources
        assert all(text not in [authored_text(block) for block in project.document.blocks()] for text in texts[2:])
        assert any(authored_text(block) == texts[1] for block in project.document.blocks())
        assert all(row.disposition == "excluded" and not row.block_ids and row.reason == "Не входит в выбранный шаблон."
            for row in project.import_coverage[2:])
        assert not project.facts.extraction.unresolved
        with ZipFile(BytesIO(render_rich_docx(project.document, facts=project.facts))) as archive:
            xml = archive.read("word/document.xml").decode()
        assert texts[1] in xml and all(text not in xml for text in texts[2:])
        workspace.project, workspace.pre_draft = project, None
        workspace.project_revision, workspace.document_revision = project.revision, project.document.revision
        source_bytes = {sources[0].id: b"source"}
        from hashlib import sha256
        project.sources[0].byte_sha256 = sha256(b"source").hexdigest()
        opened, originals, *_ = open_rich_archive(export_rich_archive(workspace, source_bytes, {}, {}), "source-only-transfer")
        assert opened.project.document == project.document and opened.project.facts == project.facts
        assert opened.project.sources == project.sources and opened.project.import_coverage == project.import_coverage
        assert originals == source_bytes
    finally:
        await service.shutdown()


@pytest.mark.parametrize("block", [
    {"type": "source_only", "refs": ["p1"]},
    {"type": "source_only", "refs": ["p1"], "reason": " "},
    {"type": "paragraph", "refs": ["p1"], "reason": "Not a visible-block field."},
])
def test_omissions_require_a_reason_and_visible_blocks_cannot_carry_one(block):
    with pytest.raises(ValidationError):
        ImportContent(sections=[{"blocks": [block]}])


def test_a_duplicate_cannot_use_an_omitted_block_as_its_visible_target():
    _sources, parts, paragraphs = paragraphs_fixture(["Repeated text", "Repeated text"])
    draft = draft_fixture()
    before = draft.model_dump_json()
    with pytest.raises(ImportFailure, match="IMPORT_REFERENCE_INVALID"):
        update_content(draft, ImportContent(sections=[{"blocks": [
            {"type": "source_only", "refs": ["p1"], "reason": "Template omission."},
            {"type": "duplicate", "refs": ["p2"], "duplicateOf": ["p1"]}]}]), paragraphs, parts)
    assert draft.model_dump_json() == before
