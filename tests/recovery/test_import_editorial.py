"""Initial editorial permission is captured per import and preserves source evidence."""

import asyncio
from io import BytesIO
import json
from pathlib import Path
import threading
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from packages.resume_core.gui_projects import GuiStartGenerationRequest
from packages.resume_core.import_agent import ImportFailure, assemble_agent_import, finish_draft
from packages.resume_core.import_content import draft_content, update_content
from packages.resume_core.models.background import FixedProcessingCommand
from packages.resume_core.models.importing import ContentBlock, ImportContent, ImportDraft, ImportFinish
from packages.resume_core.rich_archive import open_rich_archive
from packages.resume_core.rich_presentation import authored_text
from packages.resume_core.background_limits import import_seconds
from resume_api.agent.runtime import RuntimeResult
from resume_api.importer.session import ImportCoordinator, ImportSession
from tests.recovery.test_agent_import import draft_fixture, selected_service
from tests.recovery.test_background_fixed_jobs import fixed_request, settled
from tests.recovery.test_import_content import paragraphs_fixture
from tests.recovery.test_import_model import application
from tests.recovery.test_preferences import client_session
from tests.support.importing import complete, importer, read_source


def edited_sections():
    return [{"category": "experience", "blocks": [
        {"type": "heading", "refs": ["p1"]},
        {"type": "list_item", "refs": ["p2-p3"],
            "text": "Developed the Python API; the team reduced latency by 30%."}]}]


def test_edited_blocks_reread_and_materialize_with_original_facts_and_evidence(tmp_path):
    sources, parts, paragraphs = paragraphs_fixture([
        "Orion\n", "I worked on the Python API.\n", "Our team reduced latency by 30%.\n"])
    before = draft_fixture().model_copy(update={"allow_text_rewrite": True})
    saved = update_content(before, ImportContent(facts=[{
        "kind": "employment", "employer": "Orion", "technologies": ["Python"], "refs": ["p1-p3"]}],
        sections=edited_sections()), paragraphs, parts)
    outline = next(item["section"] for item in draft_content(saved, paragraphs) if "section" in item)
    assert outline["blocks"][1] == {**edited_sections()[0]["blocks"][1], "refs": ["p2", "p3"]}
    restored = ImportDraft.model_validate_json(saved.model_dump_json(by_alias=True))
    assert restored == saved and restored.allow_text_rewrite
    from packages.resume_core.rules import RulesStore
    from resume_api.rich_projects import RichProjectService
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: None)
    workspace = service.read(service.allocate("Example"))
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    project = assemble_agent_import(workspace, finish_draft(restored, ImportFinish(sequence=1), parts))
    visible = [authored_text(block) for block in project.document.blocks()]
    assert edited_sections()[0]["blocks"][1]["text"] in visible
    assert "I worked on the Python API." not in "".join(visible)
    assert project.sources == sources
    employment = next(record for record in project.facts.records if record.kind == "employment")
    assert employment.employer.raw_text == "Orion"
    edited = next(block for block in project.document.blocks() if block.type == "bullet_list")
    source = next(link for link in edited.provenance if link.kind == "source")
    assert "".join(span.text for span in source.evidence) == paragraphs[1].text + paragraphs[2].text
    assert all(row.block_ids for row in project.import_coverage)


def test_disabled_rewriting_rejects_an_entire_batch_without_changing_saved_facts():
    _sources, parts, paragraphs = paragraphs_fixture(["Orion\n", "Original duty.\n", "Original result.\n"])
    before = draft_fixture()
    snapshot = before.model_dump_json(by_alias=True)
    with pytest.raises(ImportFailure, match="IMPORT_REWRITE_DISABLED"):
        update_content(before, ImportContent(facts=[{"text": "Keep", "refs": ["p1"]}],
            sections=edited_sections()), paragraphs, parts)
    assert before.model_dump_json(by_alias=True) == snapshot
    legacy = ImportDraft.model_validate_json(snapshot)
    assert not legacy.allow_text_rewrite
    assert legacy.model_dump_json(by_alias=True) == snapshot


@pytest.mark.asyncio
async def test_composed_profile_can_cite_visible_jobs_without_duplicate_text_warning(tmp_path, monkeypatch):
    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    try:
        coordinator = ImportCoordinator(service, identifier, "summary", service.rules.load(), threading.Event(),
            allow_text_rewrite=True)
        coordinator.begin()
        refs = [paragraph.ref for paragraph in coordinator.paragraphs]
        coordinator.update(ImportContent(facts=[{"text": "Source-backed note", "refs": [refs[0]]}],
            sections=[{"category": "summary", "blocks": [{"type": "paragraph", "refs": refs,
                "text": "Professional profile supported by the projects below."}]},
                {"category": "experience", "refs": refs}]))
        draft = coordinator.load()
        draft.finished = True
        project = assemble_agent_import(service.read(identifier), draft)
        assert not any("размещены повторно" in issue.section for issue in project.facts.extraction.unresolved)
        assert project.sources == coordinator.sources
        text = "".join(authored_text(block) for block in project.document.blocks())
        assert "Professional profile supported by the projects below." in text
        assert all(paragraph.text.strip() in text for paragraph in coordinator.paragraphs)
    finally:
        await service.shutdown()


@pytest.mark.parametrize("block", [
    {"type": "paragraph", "refs": ["p1"], "text": "  "},
    {"type": "paragraph", "refs": [], "text": "New"},
    {"type": "source_only", "refs": ["p1"], "text": "New", "reason": "Hidden"},
    {"type": "duplicate", "refs": ["p1"], "duplicateOf": ["p2"], "text": "New"},
])
def test_edited_text_requires_visible_content_and_source_references(block):
    with pytest.raises(ValidationError):
        ContentBlock.model_validate(block)


@pytest.mark.parametrize("model_type", [GuiStartGenerationRequest, FixedProcessingCommand])
def test_process_defaults_to_rewriting_and_requires_a_real_boolean(model_type):
    base = {"kind": "processing"} if model_type is FixedProcessingCommand else {}
    assert model_type.model_validate(base).allow_text_rewrite is True
    assert model_type.model_validate({**base, "allowTextRewrite": False}).allow_text_rewrite is False
    for value in ("false", 0, None):
        with pytest.raises(ValidationError):
            model_type.model_validate({**base, "allowTextRewrite": value})


@pytest.mark.asyncio
async def test_changing_mode_starts_a_fresh_draft_and_same_mode_resumes(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    def begin(run, allowed):
        coordinator = ImportCoordinator(service, identifier, run, service.rules.load(), threading.Event(),
            allow_text_rewrite=allowed)
        coordinator.begin()
        return coordinator
    try:
        enabled = begin("enabled", True)
        enabled.update(ImportContent(sections=[{"category": "summary", "blocks": [
            {"type": "paragraph", "refs": ["p1"], "text": "A professional profile."}]}]))
        same = begin("enabled_retry", True)
        assert same.load().blocks[0].text == "A professional profile."
        disabled = begin("disabled", False)
        assert disabled.source_sha256 != enabled.source_sha256
        assert disabled.load().sequence == 0 and not disabled.load().blocks
        session = ImportSession(disabled)
        try:
            await read_source(session)
            result = await session.dispatcher.call("save_import", ImportContent(sections=[{
                "blocks": [{"type": "paragraph", "refs": ["p1"], "text": "Changed"}]}]))
            assert result["error"]["code"] == "IMPORT_REWRITE_DISABLED"
            assert "Omit block text" in result["error"]["message"]
            assert disabled.load().sequence == 0
        finally:
            await session.close()
    finally:
        await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [False, True])
@pytest.mark.parametrize("allowed", [None, False, True])
async def test_processing_routes_capture_permission_and_publish_portable_wording(tmp_path, monkeypatch, queued, allowed):
    expected = allowed is not False
    edited_text = "A clearer professional profile."
    async def turn(session, value, cancel):
        prompt = json.loads(value.prompt)
        assert value.active_seconds == import_seconds()  # the Settings import time (D096)
        assert prompt["allowTextRewrite"] is expected
        assert ("formattingAsOf" in prompt) is expected
        assert session.coordinator.load().allow_text_rewrite is expected
        await complete(session, finish=False)
        if expected:
            await session.dispatcher.call("save_import", ImportContent(sections=[{
                "category": "summary", "blocks": [{"type": "paragraph", "refs": ["p1"], "text": edited_text}]}]))
        from packages.resume_core.models.importing import ImportContentFinish
        reply = await session.dispatcher.call("finish_import", ImportContentFinish())
        assert reply.get("readyForPublication"), reply
        return RuntimeResult(state="completed")
    runtime, _sessions = importer(monkeypatch, turn)
    app = application(tmp_path, runtime, queued)
    async with app.app.router.lifespan_context(app.app), client_session(app) as client:
        await client.post("/v1/host/status", json={})
        await client.post("/v1/host/select", json={"model": "model-a"})
        projects, jobs = app.app.state.rich_projects, app.app.state.jobs
        source_bytes = Path("tests/fixtures/recovery/E1.txt").read_bytes()
        source = await projects.select(source_bytes, "pasted.txt", True)
        identifier = source.project_id
        options = {} if allowed is None else {"allowTextRewrite": allowed}
        if queued:
            jobs.supervisor.dispatch_enabled = False
            reply, _created = await jobs.fixed.submit(identifier,
                fixed_request(jobs, identifier, "editorial", {"kind": "processing", **options}))
            captured = jobs.fixed.input(reply.job)
            assert captured.request.command.allow_text_rewrite is expected
            assert captured.request.command.model_dump(by_alias=True).get("allowTextRewrite", True) is expected
            jobs.supervisor.dispatch_enabled = True
            jobs.supervisor.changed.set()
            done = await settled(jobs, identifier, reply.job.id, publication="saved")
            assert done.receipt is not None
        else:
            response = await client.post(f"/v1/rich/projects/{identifier}/generation", json=options)
            assert response.status_code == 202, response.text
            generation = projects.generations[identifier]
            await asyncio.wait_for(projects.tasks[(identifier, generation.id)], 10)
            assert generation.status == "completed", generation
        result = projects.read(identifier)
        assert result.project.sources == source.pre_draft.sources
        visible = "".join(authored_text(block) for block in result.project.document.blocks())
        assert (edited_text in visible) is expected
        if not expected:
            assert all(line in visible for line in source_bytes.decode().splitlines())
        transferred, originals, *_ = open_rich_archive(projects.portable(identifier), "transfer")
        assert transferred.project.document == result.project.document
        assert transferred.project.facts == result.project.facts
        assert source_bytes in originals.values()
        _snapshot, docx = await projects.export(identifier)
        with ZipFile(BytesIO(docx)) as archive:
            assert (edited_text in archive.read("word/document.xml").decode()) is expected
        assert runtime.calls == ["model-a"]
