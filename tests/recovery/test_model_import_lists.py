"""Model list boundaries override damaged source layout without rewriting words."""

from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile
import threading

from lxml import etree
import pytest

from packages.resume_core.import_agent import ImportFailure, assemble_agent_import
from packages.resume_core.import_content import draft_content, update_content
from packages.resume_core.import_lists import format_import_lists
from packages.resume_core.models.importing import ImportContent
from packages.resume_core.models.importing import ImportRead
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rich_presentation import authored_text
from tests.recovery.test_agent_import import draft_fixture, selected_service
from tests.recovery.test_import_content import paragraphs_fixture
from tests.recovery.test_import_lists import fixture as list_fixture
from resume_api.importer.session import ImportCoordinator, ImportSession
from resume_api.rich_projects import RichProjectService
from packages.resume_core.rules import RulesStore


@pytest.mark.asyncio
async def test_model_joins_detached_list_continuations_across_pages_and_keeps_editable_export(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    texts = ["Example Candidate\n", "Technical skills\n", "• Queues: RabbitMQ, Kafka, ActiveMQ,\n", "Gearman\n",
        "• - Built an API for\n", "multiple customers.\n"]
    sources, parts, paragraphs = paragraphs_fixture(texts, pages=[1, 1, 1, 2, 2, 3])
    before = deepcopy(sources)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    request = ImportContent(profile={"name": "Example Candidate", "refs": ["p1"]},
        facts=[{"text": "Likely API work; employer unclear.", "refs": ["p5-p6"]}],
        sections=[{"category": "identity", "refs": ["p1"]},
            {"category": "skills", "refs": ["p2-p4"], "listItems": [["p3-p4"]]},
            {"category": "experience", "refs": ["p5-p6"], "listItems": [["p5-p6"]]}])
    draft = update_content(draft_fixture(), request, paragraphs, parts)
    draft.finished = True
    project = assemble_agent_import(workspace, draft)
    bullets = [b for b in project.document.blocks() if b.type == "bullet_list"]
    assert {authored_text(b) for b in bullets} == {"Queues: RabbitMQ, Kafka, ActiveMQ, Gearman", "Built an API for multiple customers."}
    assert project.sources == before and draft.facts[0].text == request.facts[0].text
    assert all(b.provenance for b in bullets)
    with ZipFile(BytesIO(render_rich_docx(project.document, facts=project.facts))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs_xml = xml.xpath("//w:p[w:pPr/w:numPr]", namespaces=ns)
    assert any("Gearman" in "".join(p.xpath(".//w:t/text()", namespaces=ns)) for p in paragraphs_xml)
    assert not any("•" in "".join(p.xpath(".//w:t/text()", namespaces=ns)) for p in paragraphs_xml)
    await service.shutdown()


@pytest.mark.asyncio
async def test_model_items_keep_word_boundaries_between_word_or_text_paragraphs(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    sources, parts, paragraphs = paragraphs_fixture(["Built an API for", "multiple customers."])
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    draft = update_content(draft_fixture(), ImportContent(sections=[{"category": "experience", "refs": ["p1-p2"],
        "listItems": [["p1-p2"]]}]), paragraphs, parts)
    draft.finished = True
    project = assemble_agent_import(workspace, draft)
    assert any(authored_text(b) == "Built an API for multiple customers." for b in project.document.blocks())
    assert project.sources == sources
    await service.shutdown()


def test_model_boundaries_survive_checkpoint_reread_replacement_and_independent_fact_saves():
    _sources, parts, paragraphs = paragraphs_fixture(["First item\n", "Continuation\n", "Independent item\n"])
    request = ImportContent(sections=[{"category": "experience", "refs": ["p1-p3"],
        "listItems": [["p1-p2"], ["p3"]]}])
    saved = update_content(draft_fixture(), request, paragraphs, parts)
    assert [block.list_item for block in saved.blocks] == [True, True]
    assert update_content(saved, request, paragraphs, parts) == saved
    readable = [item["section"] for item in draft_content(saved, paragraphs) if "section" in item]
    assert readable[0]["listItems"] == [["p1", "p2"], ["p3"]]
    assert readable[0]["category"] == "experience"
    assert update_content(saved, ImportContent(sections=readable), paragraphs, parts) == saved
    changed = update_content(saved, ImportContent(facts=[{"text": "Retain an uncertain date."}]), paragraphs, parts)
    assert changed.blocks == saved.blocks
    cleared = update_content(changed, ImportContent(sections=[{"category": "experience", "refs": ["p1-p3"]}]), paragraphs, parts)
    assert not any(block.list_item for block in cleared.blocks) and cleared.facts == changed.facts


@pytest.mark.asyncio
async def test_import_tool_durably_saves_and_rereads_model_list_groups_without_another_turn(tmp_path, monkeypatch):
    service, identifier, runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    workspace = await service.select(b"Queues: ActiveMQ,\n\nGearman\n", "lists.txt", True)
    identifier = workspace.project_id
    coordinator = ImportCoordinator(service, identifier, "model-list-test", service.rules.load(), threading.Event())
    coordinator.begin()
    session = ImportSession(coordinator)
    try:
        reply = await session.dispatcher.call("save_import", ImportContent(sections=[{"category": "skills",
            "refs": ["p1-p2"], "listItems": [["p1-p2"]]}]))
        assert reply["durable"]
        read = await session.dispatcher.call("read_import", ImportRead(section="draft"))
        assert any(item.get("section", {}).get("listItems") == [["p1", "p2"]] for item in read["items"])
        reopened = RichProjectService(tmp_path / "reopened", RulesStore(tmp_path / "store"), lambda: None)
        assert reopened.read(identifier).pre_draft.import_draft.blocks[0].list_item
        assert runtime.calls == []
    finally:
        await session.close()
        await service.shutdown()


def test_model_list_refs_are_saved_even_when_the_section_ref_list_is_incomplete():
    _sources, parts, paragraphs = paragraphs_fixture(["First item\n", "Continuation\n"])
    saved = update_content(draft_fixture(), ImportContent(sections=[{"category": "experience", "refs": ["p1"],
        "listItems": [["p1-p2"]]}]), paragraphs, parts)
    assert saved.blocks[0].source_keys == paragraphs[0].keys + paragraphs[1].keys
    before = saved.model_dump_json()
    with pytest.raises(ImportFailure, match="IMPORT_REFERENCE_INVALID"):
        update_content(saved, ImportContent(sections=[{"listItems": [["p3"]]}]), paragraphs, parts)
    assert saved.model_dump_json() == before


def test_an_explicit_model_item_is_not_extended_by_later_geometry_guesses():
    sources, blocks = list_fixture(["• First complete duty\n", "Independent unmarked duty\n"])
    blocks[0]["type"] = "bullet_list"
    result = format_import_lists({"main": blocks}, sources, lambda _kind, key: str(key), model_items={"b0"})["main"]
    assert len(result) == 2
    assert "".join(s["text"] for s in result[0]["content"]) == "First complete duty"
    assert result[1]["type"] == "paragraph"


@pytest.mark.parametrize("value", ["-X --option\n", "-20 percent\n", "2020. Employment\n", "0. code index\n"])
def test_model_marker_cleanup_preserves_commands_dates_and_negative_values(value):
    sources, blocks = list_fixture(["• - " + value])
    blocks[0]["type"] = "bullet_list"
    result = format_import_lists({"main": blocks}, sources, lambda _kind, key: str(key), model_items={"b0"})["main"]
    assert "".join(s["text"] for s in result[0]["content"]) == value.strip()


def test_model_marker_cleanup_keeps_bound_numbers_and_source_evidence():
    sources, blocks = list_fixture(["5. Result\n"])
    blocks[0]["type"] = "bullet_list"
    blocks[0]["content"] = [{"type": "fact_field", "text": "5", "recordId": "claim", "fieldKey": "value",
        "bindingId": "number", "syncedFactRevision": 1, "styles": {}}, {"type": "text", "text": ". Result\n", "styles": {}}]
    original = deepcopy(blocks[0]["provenance"])
    result = format_import_lists({"main": blocks}, sources, lambda _kind, key: str(key), model_items={"b0"})["main"][0]
    assert result["content"][0]["text"] == "5" and result["content"][0]["bindingId"] == "number"
    assert result["type"] == "bullet_list" and result["provenance"] == original


def test_model_item_retains_an_explicit_numbered_list_start():
    sources, blocks = list_fixture(["5. First item\nwrapped continuation\n"])
    blocks[0]["type"] = "bullet_list"
    result = format_import_lists({"main": blocks}, sources, lambda _kind, key: str(key), model_items={"b0"})["main"][0]
    assert result["type"] == "numbered_list" and result["props"]["start"] == 5
    assert "".join(s["text"] for s in result["content"]) == "First item wrapped continuation"


def test_model_item_removes_empty_and_doubled_markers_without_splitting_its_source_group():
    sources, blocks = list_fixture(["•\n• - Built the service\n•\nfor multiple customers.\n"])
    blocks[0]["type"] = "bullet_list"
    result = format_import_lists({"main": blocks}, sources, lambda _kind, key: str(key), model_items={"b0"})["main"]
    assert len(result) == 1
    assert " ".join("".join(s["text"] for s in result[0]["content"]).split()) == "Built the service for multiple customers."
