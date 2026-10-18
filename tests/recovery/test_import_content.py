"""Content-only imports preserve source context and leave layout to Python."""

import json
import threading

import pytest

from packages.resume_core.import_agent import ImportFailure, source_parts, assemble_agent_import
from packages.resume_core.import_content import source_paragraphs, resolve_refs, update_content, draft_content
from packages.resume_core.models.importing import ImportContent, ImportContentFinish, ImportRead
from packages.resume_core.rich_presentation import authored_text
from resume_api.importer.session import ImportCoordinator, ImportSession
from tests.recovery.test_agent_import import source_fixture, draft_fixture, selected_service


def paragraphs_fixture(texts, *, pages=None):
    sources = source_fixture()
    first = sources[0].units[0]
    sources[0].units = [first.model_copy(update={"id": f"unit_{i}", "order": i, "text": text,
        "location": first.location.model_copy(update={"kind": "page", "index": pages[i] - 1})
            if pages else first.location}) for i, text in enumerate(texts)]
    parts = source_parts(sources)
    return sources, parts, source_paragraphs(sources, parts)


def test_paragraph_view_preserves_wrapped_text_trailing_years_and_page_boundaries():
    texts = ["Example Candidate\n", "Language certificate\nOverall: 6.5\n2013\n",
        "Technical university\nSoftware engineering\n2009\n", "Humanities academy\nManagement\n2005\n"]
    _sources, parts, paragraphs = paragraphs_fixture(texts, pages=[1, 2, 2, 3])
    assert [p.text for p in paragraphs] == texts
    assert [p.page for p in paragraphs] == [1, 2, 2, 3]
    assert [p.ref for p in paragraphs] == ["p1", "p2", "p3", "p4"]
    assert [key for p in paragraphs for key in p.keys] == [p.key for p in parts]
    assert len(paragraphs) < len(parts)
    saved = update_content(draft_fixture(), ImportContent(facts=[
        {"text": "Language certificate, 2013.", "refs": ["p2"]},
        {"text": "Technical university, 2009.", "refs": ["p3"]},
        {"text": "Humanities academy, 2005.", "refs": ["p4"]}]), paragraphs, parts)
    for fact, expected in zip(saved.facts, texts[1:]):
        assert "".join(p.text for p in parts if p.key in fact.source_keys) == expected


def test_long_paragraph_is_bounded_without_losing_characters_or_evidence():
    original = "Начало\n" + "я" * 10001 + "\nКонец\n"
    _sources, parts, paragraphs = paragraphs_fixture([original])
    assert "".join(p.text for p in paragraphs) == original
    assert max(len(p.text) for p in paragraphs) <= 4000
    assert [key for p in paragraphs for key in p.keys] == [p.key for p in parts]


@pytest.mark.parametrize("ref", ["p0", "p5", "p3-p2", "p2-p7", "part_1", "p1,p2"])
def test_invalid_short_reference_leaves_the_saved_digest_unchanged(ref):
    _sources, parts, paragraphs = paragraphs_fixture(["Name\n", "Company\n", "Role unknown\n", "Other\n"])
    saved = update_content(draft_fixture(), ImportContent(facts=[{"text": "Keep this uncertainty."}]), paragraphs, parts)
    before = saved.model_dump_json()
    with pytest.raises(ImportFailure, match="IMPORT_REFERENCE_INVALID"):
        update_content(saved, ImportContent(facts=[{"text": "New", "refs": ["p1"]}],
            sections=[{"refs": [ref]}]), paragraphs, parts)
    assert saved.model_dump_json() == before


def test_ranges_and_repeated_references_keep_order_without_duplicating_a_paragraph():
    _sources, _parts, paragraphs = paragraphs_fixture(["a\n", "b\n", "c\n", "d\n"])
    assert [p.ref for p in resolve_refs(["p3", "p1–p3", "p4"], paragraphs)] == ["p3", "p1", "p2", "p4"]


@pytest.mark.parametrize("field,code", [("facts", "IMPORT_EVIDENCE_TOO_LARGE"), ("sections", "IMPORT_DRAFT_TOO_LARGE")])
def test_storage_bounds_reject_oversized_content_atomically(field, code):
    _sources, parts, paragraphs = paragraphs_fixture([f"Text {i}\n" for i in range(1700)])
    request = (ImportContent(facts=[{"text": "Too broad", "refs": ["p1-p1700"]}]) if field == "facts" else
        ImportContent(sections=[{"refs": ["p1-p1700"]}] * 3))
    before = draft_fixture()
    with pytest.raises(ImportFailure, match=code):
        update_content(before, request, paragraphs, parts)
    assert not before.blocks and not before.facts and before.sequence == 0


def test_content_snapshots_are_idempotent_independent_and_can_reorder_existing_paragraphs():
    _sources, parts, paragraphs = paragraphs_fixture(["Name\n", "Company\n", "Dates unclear\n"])
    facts = ImportContent(facts=[{"text": "Likely Company; dates unclear.", "refs": ["p2-p3"]}])
    saved = update_content(draft_fixture(), facts, paragraphs, parts)
    assert saved.sequence == 1 and saved.blocks == []
    outline = ImportContent(sections=[{"category": "identity", "refs": ["p1"]},
        {"category": "experience", "heading": "Work", "refs": ["p2-p3"]}])
    arranged = update_content(saved, outline, paragraphs, parts)
    assert arranged.facts == saved.facts and arranged.sequence == 2
    assert update_content(arranged, outline, paragraphs, parts) == arranged
    assert update_content(arranged, facts, paragraphs, parts) == arranged
    outline.sections[1].refs = ["p3", "p2"]
    reordered = update_content(arranged, outline, paragraphs, parts)
    assert [b.source_keys for b in reordered.blocks[-2:]] == [paragraphs[2].keys, paragraphs[1].keys]
    readable = draft_content(reordered, paragraphs)
    assert readable[1]["fact"]["text"] == facts.facts[0].text
    assert readable[-1]["section"]["refs"] == ["p3", "p2"]
    assert "sourceKeys" not in json.dumps(readable) and "content_fact_" not in json.dumps(readable)
    cleared = update_content(reordered, ImportContent(sections=[]), paragraphs, parts)
    assert cleared.blocks == [] and cleared.facts == saved.facts


@pytest.mark.asyncio
async def test_python_formats_over_two_hundred_paragraphs_without_an_agent_block_plan(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    texts = ["Example Candidate\n", "Engineer\n", "Work\n", *[f"Work detail {i}\n" for i in range(205)],
        "Education\n", "University\n2009\n", "Unusual appendix\n"]
    sources, parts, paragraphs = paragraphs_fixture(texts)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    sources[0].warnings = ["IMAGE"]
    request = ImportContent(profile={"name": "Example Candidate", "title": "Engineer", "refs": ["p1-p2"]},
        facts=[{"text": "University, 2009; qualification not stated.", "refs": ["p210"]}],
        sections=[{"category": "identity", "refs": ["p1-p2"]},
            {"category": "experience", "heading": "Work", "refs": ["p3-p208"]},
            {"category": "education", "heading": "Education", "refs": ["p209-p210"]}])
    saved = update_content(draft_fixture(), request, paragraphs, parts)
    saved.finished = True
    project = assemble_agent_import(workspace, saved)
    header, sidebar, main = project.document.regions
    assert [authored_text(b) for b in header.blocks] == texts[:2]
    assert header.blocks[0].props.level == 1
    def flatten(blocks):
        return "".join(authored_text(b) + flatten(b.children) for b in blocks)
    assert flatten(sidebar.blocks) == "".join(texts[208:210])
    assert flatten(main.blocks) == "".join(texts[2:208] + texts[210:])
    assert sidebar.blocks[0].type == main.blocks[0].type == "section"
    assert len([b for b in project.document.blocks() if authored_text(b)]) == len(texts)
    assert all(row.block_ids for row in project.import_coverage)
    assert any("Изображения" in issue.section for issue in project.facts.extraction.unresolved)
    assert any(issue.unit_id for issue in project.facts.extraction.unresolved)
    await service.shutdown()


@pytest.mark.asyncio
async def test_source_reads_hide_internal_ids_and_image_warnings_and_paginate_losslessly(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    raw = "".join(f"Entry {i}: " + "x" * 1800 + "\n" for i in range(50)).encode()
    workspace = await service.select(raw, "long.txt", True)
    identifier = workspace.project_id
    workspace = service.workspaces[identifier]
    sources = workspace.pre_draft.sources
    for index, unit in enumerate(sources[0].units):
        unit.location = unit.location.model_copy(update={"kind": "page", "index": index // 25})
    sources[0].warnings = ["IMAGE"]
    service.persist(identifier)
    rules = service.rules.load()
    service.rules.save(rules.markdown + "\nRULES_CANARY: rewrite the source", rules.revision)
    coordinator = ImportCoordinator(service, identifier, "read", service.rules.load(), threading.Event())
    coordinator.begin()
    session = ImportSession(coordinator)
    try:
        assert sources[0].id not in session.prompt and "IMAGE" not in session.prompt
        assert "RULES_CANARY" not in session.prompt and "formattingAsOf" not in session.prompt
        first = await session.dispatcher.call("read_import", ImportRead())
        assert first["nextOffset"] is not None
        assert (await session.dispatcher.call("finish_import", ImportContentFinish()))["error"]["code"] == "IMPORT_SOURCE_NOT_READ"
        text, offset = first["text"], first["nextOffset"]
        while offset is not None:
            result = await session.dispatcher.call("read_import", ImportRead(offset=offset))
            assert len(json.dumps(result).encode()) < 64 * 1024
            text += result["text"]
            offset = result["nextOffset"]
        assert all(text.count(p.text) == 1 for p in coordinator.paragraphs)
        assert "Page 1" in text and "Page 2" in text and sources[0].id not in text
        assert len(session.dispatcher.read_keys) == 50
        assert (await session.dispatcher.call("finish_import", ImportContentFinish()))["readyForPublication"]
    finally:
        await session.close()
        await service.shutdown()


@pytest.mark.asyncio
async def test_unknown_reference_reports_the_repair_and_does_not_erase_saved_facts(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    coordinator = ImportCoordinator(service, identifier, "reference", service.rules.load(), threading.Event())
    coordinator.begin()
    session = ImportSession(coordinator)
    try:
        await session.dispatcher.call("save_import", ImportContent(facts=[{"text": "Keep"}]))
        before = coordinator.load()
        result = await session.dispatcher.call("save_import", ImportContent(facts=[{"text": "Changed", "refs": ["PRIVATE_CANARY"]}]))
        assert result["error"]["code"] == "IMPORT_REFERENCE_INVALID"
        assert "p1 through p12" in result["error"]["message"] and "PRIVATE_CANARY" not in json.dumps(result)
        assert coordinator.load() == before
    finally:
        await session.close()
        await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [False, True])
@pytest.mark.parametrize("kind", ["pdf", "docx", "markdown"])
async def test_source_structure_reaches_tools_and_survives_publication_reopen_and_transfer(tmp_path, monkeypatch, queued, kind):
    from packages.resume_core.rich_archive import open_rich_archive
    from packages.resume_core.rules import RulesStore
    from resume_api.agent.runtime import RuntimeResult
    from resume_api.rich_projects import RichProjectService
    from tests.extract.test_structure import pdf, structured_docx
    from tests.support.importing import importer
    inputs = {
        "pdf": (pdf([(0, 40, 100, "Qualification", False), (0, 40, 118, "2009", False),
                     (0, 40, 40, "Candidate", True)]), "source.pdf", "visual group"),
        "docx": (structured_docx(), "source.docx", "table 1, row 1, cell 3"),
        "markdown": (b"# Candidate\n\n  Experience\n2024\n", "source.md", "1 blank lines before"),
    }
    raw, filename, hint = inputs[kind]
    reads = []

    async def parse(session, _value, _cancel):
        offset = 0
        while offset is not None:
            reply = await session.dispatcher.call("read_import", ImportRead(offset=offset))
            reads.append(reply["text"])
            offset = reply["nextOffset"]
        assert hint in "".join(reads)
        count = len(session.coordinator.paragraphs)
        saved = await session.dispatcher.call("save_import", ImportContent(
            facts=[{"text": "Dates require review.", "refs": ["p1"]}],
            sections=[{"category": "other", "refs": [f"p1-p{count}"]}]))
        assert saved["durable"]
        assert (await session.dispatcher.call("finish_import", ImportContentFinish()))["readyForPublication"]
        return RuntimeResult(state="completed")

    if queued:
        from tests.recovery.test_background_agent import environment
        from tests.recovery.test_background_fixed_jobs import fixed_request, settled
        jobs, factory, *_ = await environment(tmp_path)
        projects = jobs.projects
        projects.provider_factory = lambda: (object(), "processing-model")
        runtime, _sessions = importer(monkeypatch, parse, admission=jobs.admission)
        jobs.runtime = runtime
    else:
        runtime, _sessions = importer(monkeypatch, parse)
        projects = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"),
            lambda: (object(), "fixture"), import_runtime=runtime)
    try:
        selected = await projects.select(raw, filename, False)
        identifier = selected.project_id
        original = selected.pre_draft.sources[0].model_copy(deep=True)
        stored, _ = projects.storage.read_committed(identifier)
        assert stored.pre_draft.sources[0] == original
        assert all(unit.structure for unit in original.units)
        if queued:
            reply, _ = await jobs.fixed.submit(identifier, fixed_request(jobs, identifier, "structure", {"kind": "processing"}))
            await settled(jobs, identifier, reply.job.id, publication="saved")
        else:
            generation = projects.start(identifier)
            await projects.tasks[(identifier, generation)]
            assert projects.generations[identifier].status == "completed"
        saved, _ = projects.storage.read_committed(identifier)
        assert saved.project.sources[0] == original
        visible = "".join(authored_text(block) for block in saved.project.document.blocks())
        assert hint not in visible and "layout:" not in visible
        assert all(unit.text in visible for unit in original.units if unit.text.strip())
        transferred, *_ = open_rich_archive(projects.portable(identifier), "transfer")
        assert transferred.project.sources[0] == original
        assert len(runtime.calls) == 1
        reopened = RichProjectService(tmp_path / "reopened", projects.rules, lambda: None)
        assert reopened.read(identifier).project.sources[0] == original
        await reopened.shutdown()
    finally:
        if queued:
            await jobs.shutdown()
            factory.verify()
            jobs.supervisor.clock.verify()
        else:
            await projects.shutdown()
