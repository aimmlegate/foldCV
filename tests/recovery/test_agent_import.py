"""Flexible facts retain ambiguity; only technical defects reject draft batches."""

import asyncio
from io import BytesIO
from pathlib import Path
import threading
from zipfile import ZipFile

import pytest

from packages.resume_core.import_agent import ImportFailure, source_parts, update_draft, finish_draft, assemble_agent_import
from packages.resume_core.models.importing import (ImportBatch, ImportDraft, ImportFinish, ImportRead,
    ImportContent, ImportContentFinish)
from packages.resume_core.rich_presentation import authored_text
from packages.resume_core.rich_archive import open_rich_archive
from packages.resume_core.rules import RulesStore
from packages.resume_core.project_store import ProjectStoreFailure
from resume_api.rich_projects import RichProjectService
from resume_api.agent.runtime import RuntimeResult
from resume_api.importer.session import ImportCoordinator, ImportSession
from tests.recovery.candidate_fixtures import request as source_request
from tests.support.importing import importer, read_source, complete


TEXT = ("Анна Пример\nPlatform engineer\nhello@example.test\n"
    "Примерно с 2020 до весны 23: Orion, клиент или работодатель — неясно.\n"
    "Команда ускорила выпуск; моя часть — Python API.\n"
    "Должность не указана. Перерыв? Параллельно проект Delta.\n"
    "Курс: не закончен. English: B1/B2?\nНеобычная заметка: сохранить.\n")


def source_fixture():
    return source_request(TEXT).sources


def draft_fixture():
    return ImportDraft(sourceSha256="1" * 64, skillSha256="2" * 64, runId="run")


def batch(sequence=0, **overrides):
    return ImportBatch.model_validate({"batchId": "batch", "sequence": sequence,
        "facts": [{"id": "work", "text": "Вероятно Orion, около 2020–2023; связь с компанией и должность неясны. "
            "Python API; ускорение — результат команды. Параллельный проект Delta.",
            "sourceKeys": ["part_4", "part_5", "part_6"]}],
        "blocks": [{"id": "name", "sourceKeys": ["part_1"], "region": "header", "kind": "heading"},
            {"id": "contact", "sourceKeys": ["part_3"], "region": "sidebar"},
            {"id": "work", "sourceKeys": ["part_4", "part_5", "part_6"]}],
        "profile": {"name": "Анна Пример", "sourceKeys": ["part_1"]}, **overrides})


def test_ambiguous_work_and_relationships_are_preserved_without_literal_or_required_fields(tmp_path):
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: None)
    identifier = service.allocate("Example")
    workspace = service.read(identifier)
    workspace.pre_draft.sources = source_fixture()
    workspace.pre_draft.selected_source_id = workspace.pre_draft.sources[0].id
    parts = source_parts(workspace.pre_draft.sources)
    draft, _ = update_draft(draft_fixture(), batch(), parts)
    final = finish_draft(draft, ImportFinish(sequence=1, issues=["Связь Orion и Delta требует уточнения."]), parts)
    project = assemble_agent_import(workspace, final)
    claim = next(r for r in project.facts.records if r.kind == "claim")
    assert claim.value.raw_text == batch().facts[0].text
    assert claim.job_id is None and claim.subproject_id is None and claim.evidence
    visible = "".join(authored_text(b) for b in project.document.blocks())
    assert all(line in visible for line in TEXT.splitlines())
    assert project.facts.mode == "digest" and project.facts.extraction.status == "partial"
    assert project.facts.extraction.unresolved[-1].section == final.issues[0]
    assert all(region.blocks for region in project.document.regions)
    assert all(row.block_ids for row in project.import_coverage)
    assert project.sources == workspace.pre_draft.sources
    assert any(link.kind == "citation" and link.record_id == claim.id for b in project.document.blocks() for link in b.provenance)


@pytest.mark.parametrize("change,code", [
    ({"sequence": 1}, "IMPORT_STALE_BATCH"),
    ({"blocks": [{"id": "bad", "sourceKeys": ["absent"]}]}, "IMPORT_REFERENCE_INVALID"),
    ({"facts": [{"id": "same", "text": "a"}, {"id": "same", "text": "b"}]}, "IMPORT_DUPLICATE_ID"),
])
def test_invalid_batch_is_atomic(change, code):
    before = draft_fixture()
    with pytest.raises(ImportFailure, match=code):
        update_draft(before, batch(**change), source_parts(source_fixture()))
    assert before.sequence == 0 and before.facts == before.blocks == before.receipts == []


def test_checkpoint_replay_is_exact_and_revisions_move_existing_blocks_atomically():
    parts = source_parts(source_fixture())
    before, receipt = update_draft(draft_fixture(), batch(), parts)
    replay, same = update_draft(before, batch(), parts)
    assert replay == before and same == receipt
    with pytest.raises(ImportFailure, match="IMPORT_IDEMPOTENCY_CONFLICT"):
        update_draft(before, batch(facts=[]), parts)
    changed, _ = update_draft(before, ImportBatch(batchId="move", sequence=1, blocks=[
        {"id": "name", "sourceKeys": ["part_1"], "region": "main"}]), parts)
    assert changed.blocks[0].region == "main" and changed.facts == before.facts


def test_agent_block_ids_cannot_collide_with_retained_source_fragments(tmp_path):
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: None)
    workspace = service.read(service.allocate("Example"))
    workspace.pre_draft.sources = source_fixture()
    workspace.pre_draft.selected_source_id = workspace.pre_draft.sources[0].id
    parts = source_parts(workspace.pre_draft.sources)
    draft, _ = update_draft(draft_fixture(), batch(blocks=[
        {"id": "retained_part_2", "sourceKeys": ["part_1"]}]), parts)
    final = finish_draft(draft, ImportFinish(sequence=1), parts)
    project = assemble_agent_import(workspace, final)
    blocks = list(project.document.blocks())
    assert len({block.id for block in blocks}) == len(blocks)
    assert "".join(authored_text(block) for block in blocks) == TEXT


def test_redundant_titles_and_reused_source_do_not_discard_a_useful_digest(tmp_path):
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"), lambda: None)
    workspace = service.read(service.allocate("Example"))
    workspace.pre_draft.sources = source_fixture()
    workspace.pre_draft.selected_source_id = workspace.pre_draft.sources[0].id
    parts = source_parts(workspace.pre_draft.sources)
    request = batch(blocks=[
        {"id": "name", "sourceKeys": ["part_1"], "region": "header", "kind": "heading", "title": "Candidate"},
        {"id": "repeated", "sourceKeys": ["part_1"]},
        {"id": "section", "kind": "section", "title": "Experience"},
        {"id": "work", "sourceKeys": ["part_4", "part_5", "part_6"]}])
    saved, _ = update_draft(draft_fixture(), request, parts)
    project = assemble_agent_import(workspace, finish_draft(saved, ImportFinish(sequence=1), parts))
    claim = next(record for record in project.facts.records if record.kind == "claim")
    assert claim.value.value == request.facts[0].text
    assert authored_text(project.document.regions[0].blocks[0]) == parts[0].text
    assert all(line in "".join(authored_text(block) for block in project.document.blocks()) for line in TEXT.splitlines())
    assert any("повторно" in issue.section for issue in project.facts.extraction.unresolved)


async def selected_service(tmp_path, monkeypatch, script=None):
    runtime, sessions = importer(monkeypatch, script)
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"),
        lambda: (object(), "fixture"), import_runtime=runtime)
    workspace = await service.select(Path("tests/fixtures/recovery/E1.txt").read_bytes(), "pasted.txt", True)
    return service, workspace.project_id, runtime, sessions


@pytest.mark.asyncio
@pytest.mark.parametrize("with_text", [False, True])
async def test_pdf_images_stay_separate_from_text_and_do_not_trigger_ocr(tmp_path, monkeypatch, with_text):
    import json
    import pymupdf
    from resume_api.gui_projects import ProjectFailure
    runtime, _sessions = importer(monkeypatch)
    service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"),
        lambda: (object(), "fixture"), import_runtime=runtime)
    with pymupdf.open() as document:
        page = document.new_page()
        pixels = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 2, 2), False)
        pixels.clear_with(0)
        page.insert_image(pymupdf.Rect(20, 20, 40, 40), pixmap=pixels)
        if with_text:
            page.insert_text((60, 60), "Example Candidate\nPython engineer")
        pdf = document.tobytes()
    workspace = await service.select(pdf, "example.pdf", False)
    source = workspace.pre_draft.sources[0]
    assert source.parser == "pymupdf" and "IMAGE" in source.warnings
    if not with_text:
        with pytest.raises(ProjectFailure, match="NO_USABLE_TEXT"):
            service.start(workspace.project_id)
    else:
        coordinator = ImportCoordinator(service, workspace.project_id, "text", service.rules.load(), threading.Event())
        coordinator.begin()
        session = ImportSession(coordinator)
        try:
            items, _sequence = await read_source(session)
            assert "Example Candidate" in "".join(item["text"] for item in items)
            assert "base64" not in json.dumps(items) and "image" not in json.dumps(items).lower()
        finally:
            await session.close()
    assert runtime.calls == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_direct_import_publishes_once_after_durable_batches_and_exports_editable_docx(tmp_path, monkeypatch):
    service, identifier, runtime, sessions = await selected_service(tmp_path, monkeypatch)
    try:
        generation = service.start(identifier)
        await service.tasks[(identifier, generation)]
        state = service.generations[identifier]
        assert state.status == "completed", state
        workspace, _ = service.storage.read_committed(identifier)
        assert workspace.project.facts.mode == "digest" and workspace.pre_draft is None
        headers = workspace.project.document.regions[0].blocks
        assert [block.props.level for block in headers] == [1, 2]
        bindings = [span for block in headers for span in block.content if span.type == "fact_field"]
        assert {span.field_key for span in bindings} == {"name", "title"}
        assert all("\n" not in span.text for span in bindings)
        from tests.recovery.test_rich_panel import edit
        from packages.resume_core.rich_panel import panel_mutation
        from packages.resume_core.rich_mutations import apply_rich_mutation
        renamed, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
            edit(workspace, recordId="candidate", values={"name": "Мария Примерова"})))
        renamed_header = renamed.project.document.regions[0].blocks
        assert authored_text(renamed_header[0]) == "Мария Примерова, "
        assert authored_text(renamed_header[1]) == "backend-разработчик.\n"
        assert len(runtime.calls) == 1 and all(not s.token for s in sessions.values())
        _snapshot, docx = await service.export(identifier)
        with ZipFile(BytesIO(docx)) as archive:
            assert "Ирина Примерова" in archive.read("word/document.xml").decode()
        reopened = RichProjectService(tmp_path / "again", RulesStore(tmp_path / "store"), lambda: None)
        assert reopened.read(identifier) == workspace
        transferred, *_ = open_rich_archive(service.portable(identifier), "transfer")
        assert transferred.project.facts == workspace.project.facts
    finally:
        await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["no_finish", "cancel", "runtime", "source", "rules"])
async def test_failed_turn_keeps_checkpoint_and_explicit_retry_resumes_without_hidden_turns(tmp_path, monkeypatch, failure):
    entered, release = asyncio.Event(), asyncio.Event()
    async def script(session, value, cancel):
        await complete(session, finish=False)
        entered.set()
        await release.wait()
        return RuntimeResult(state="failed" if failure == "runtime" else "cancelled" if cancel.is_set() else "completed",
            error="AGENT_PROTOCOL" if failure == "runtime" else None)
    service, identifier, runtime, sessions = await selected_service(tmp_path, monkeypatch, script)
    try:
        generation = service.start(identifier)
        await asyncio.wait_for(entered.wait(), 3)
        stored, _ = service.storage.read_committed(identifier)
        assert stored.pre_draft.import_draft.sequence == 1 and stored.project is None
        if failure == "cancel":
            service.cancels[(identifier, generation)].set()
        elif failure == "source":
            service.workspaces[identifier].pre_draft.sources[0].units[0].text += "Changed source"
            service.persist(identifier)
        elif failure == "rules":
            rules = service.rules.load()
            service.rules.save(rules.markdown + "\nUpdated rules", rules.revision)
        release.set()
        await service.tasks[(identifier, generation)]
        assert service.generations[identifier].status in {"failed", "cancelled"}
        assert len(runtime.calls) == 1
        reopened = RichProjectService(tmp_path / "again", RulesStore(tmp_path / "store"), lambda: (object(), "fixture"))
        assert reopened.read(identifier).pre_draft.import_draft.facts == stored.pre_draft.import_draft.facts
        async def resume(session, value, cancel):
            _items, seq = await read_source(session)
            assert seq == (0 if failure in {"source", "rules"} else 1)
            await complete(session)
            return RuntimeResult(state="completed")
        reopened.import_runtime, _ = importer(monkeypatch, resume)
        retry = reopened.start(identifier)
        await reopened.tasks[(identifier, retry)]
        assert reopened.generations[identifier].status == "completed", reopened.generations[identifier]
        assert len(reopened.import_runtime.calls) == 1
        await reopened.shutdown()
    finally:
        release.set()
        await service.shutdown()


@pytest.mark.asyncio
async def test_tool_checkpoint_failure_cannot_be_acknowledged_or_published(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    coordinator = ImportCoordinator(service, identifier, "test", service.rules.load(), threading.Event())
    coordinator.begin()
    session = ImportSession(coordinator)
    try:
        await read_source(session)
        before, _ = service.storage.read_committed(identifier)
        def fail(*_args, **_kwargs):
            raise ProjectStoreFailure("PROJECT_SAVE_FAILED")
        monkeypatch.setattr(service.storage, "save", fail)
        result = await session.dispatcher.call("save_import", ImportContent(facts=[{"text": "Keep"}]))
        assert result == {"error": {"code": "PROJECT_SAVE_FAILED"}}
        assert service.storage.read_committed(identifier)[0] == before
        with pytest.raises(ImportFailure, match="PROJECT_SAVE_FAILED"):
            coordinator.load()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_finish_requires_full_source_read_and_invalid_calls_are_bounded(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    coordinator = ImportCoordinator(service, identifier, "test", service.rules.load(), threading.Event())
    coordinator.begin()
    session = ImportSession(coordinator)
    try:
        result = await session.dispatcher.call("finish_import", ImportContentFinish())
        assert result["error"]["code"] == "IMPORT_SOURCE_NOT_READ"
        for _ in range(63):
            assert session.dispatcher.preflight({"name": "save_import", "arguments": {"request": {}}}) == "IMPORT_ARGUMENTS_INVALID"
        assert session.dispatcher.preflight({"name": "read_import", "arguments": {"request": {}}}) == "IMPORT_TOOL_LIMIT"
        with pytest.raises(ImportFailure, match="IMPORT_TOOL_LIMIT"):
            coordinator.load()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_invalid_content_reports_the_repair_without_echoing_source_text(tmp_path, monkeypatch):
    import json
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    coordinator = ImportCoordinator(service, identifier, "test", service.rules.load(), threading.Event())
    coordinator.begin()
    session = ImportSession(coordinator)
    try:
        error = session.dispatcher.preflight({"name": "save_import", "arguments": {"request": {
            "facts": [{"text": "", "refs": ["PRIVATE_CANARY"]}]}}})
        response = session.dispatcher.preflight_failure(error)
        assert error == "IMPORT_ARGUMENTS_INVALID"
        note_error = next(issue for issue in response["argumentIssues"]
            if issue["path"] == ["facts", 0, "ContentFact", "text"])
        assert "at least 1 character" in note_error["message"]
        assert "PRIVATE_CANARY" not in json.dumps(response)
        assert coordinator.load().sequence == 0
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_advertised_import_tools_round_trip_durable_receipts_over_mcp(tmp_path, monkeypatch):
    import json
    import httpx
    from jsonschema import Draft202012Validator
    from packages.resume_core.models.importing import IMPORT_TOOLS
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    coordinator = ImportCoordinator(service, identifier, "wire", service.rules.load(), threading.Event())
    coordinator.begin()
    session = ImportSession(coordinator)
    session.application = session.sdk.streamable_http_app()
    headers = {"Authorization": "Bearer " + session.token, "Accept": "application/json, text/event-stream"}
    try:
        async with session.application.router.lifespan_context(session.application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=session), base_url="http://" + session.host, headers=headers) as client:
                async def rpc(method, params):
                    response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                    assert response.status_code == 200
                    return response.json()["result"]
                catalog = {tool["name"]: tool for tool in (await rpc("tools/list", {}))["tools"]}
                assert set(catalog) == set(IMPORT_TOOLS)
                async def call(name, request):
                    Draft202012Validator(catalog[name]["inputSchema"]).validate({"request": request})
                    result = await rpc("tools/call", {"name": name, "arguments": {"request": request}})
                    assert not result.get("isError"), result
                    return json.loads(result["content"][0]["text"])
                source = await call("read_import", {})
                assert source["nextOffset"] is None and "[p1]" in source["text"]
                request = {"facts": [{"text": "Роль не указана."}]}
                receipt = await call("save_import", request)
                assert receipt == await call("save_import", request)
                draft = await call("read_import", {"section": "draft"})
                assert draft["items"][1]["fact"]["text"] == "Роль не указана."
                result = await call("finish_import", {"issues": ["Проверьте разделы."]})
                assert result["durable"] and result["unassignedRefs"] and not result["completed"]
                denied = await rpc("tools/call", {"name": "project_action", "arguments": {"request": {}}})
                assert denied["isError"]
                response = await client.post("/mcp", headers={"Origin": "http://localhost"}, json={})
                assert response.status_code == 403
        saved, _ = service.storage.read_committed(identifier)
        assert saved.pre_draft.import_draft.finished and saved.project is None
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_unverified_runtime_cleanup_never_publishes_finished_draft(tmp_path, monkeypatch):
    service, identifier, _runtime, sessions = await selected_service(tmp_path, monkeypatch)
    failures = []
    service.cleanup_error = lambda error: failures.append(error.code)
    class UnverifiedRuntime:
        async def run(self, value, cancel, emit):
            await complete(sessions[value.url])
            return RuntimeResult(state="completed", cleanup_verified=False)
    service.import_runtime = UnverifiedRuntime()
    generation = service.start(identifier)
    await service.tasks[(identifier, generation)]
    assert service.generations[identifier].error_code == "AGENT_CLEANUP_FAILED"
    saved, _ = service.storage.read_committed(identifier)
    assert saved.project is None and saved.pre_draft.import_draft.finished
    assert failures == ["AGENT_CLEANUP_FAILED"] and all(not session.token for session in sessions.values())


@pytest.mark.asyncio
async def test_queued_retry_uses_checkpoint_and_publishes_through_the_existing_coordinator(tmp_path, monkeypatch):
    from tests.recovery.test_background_agent import environment
    from tests.recovery.test_background_fixed_jobs import source_project, fixed_request, settled
    service, factory, _workspace, _request, _connection, _old = await environment(tmp_path)
    service.projects.provider_factory = lambda: (object(), "processing-model")
    async def fail(session, value, cancel):
        await complete(session, finish=False)
        return RuntimeResult(state="failed", error="AGENT_PROTOCOL")
    first, _ = importer(monkeypatch, fail, admission=service.admission)
    service.runtime = first
    try:
        source = await source_project(service, monkeypatch)
        request = fixed_request(service, source.project_id, "first-import", {"kind": "processing"})
        reply, _ = await service.fixed.submit(source.project_id, request)
        failed = await settled(service, source.project_id, reply.job.id)
        assert failed.execution == "failed" and failed.receipt is None
        current, _ = service.projects.storage.read_committed(source.project_id)
        assert current.pre_draft.import_draft.sequence == 1 and current.pre_draft.import_draft.facts
        async def resume(session, value, cancel):
            _items, seq = await read_source(session)
            assert seq == 1
            await complete(session)
            return RuntimeResult(state="completed")
        second, _ = importer(monkeypatch, resume, admission=service.admission)
        service.runtime = second
        request = fixed_request(service, source.project_id, "retry-import", {"kind": "processing"})
        reply, _ = await service.fixed.submit(source.project_id, request)
        done = await settled(service, source.project_id, reply.job.id, publication="saved")
        assert len(done.attempts) == 1 and done.attempts[0].cleanup_verified and done.receipt
        current, _ = service.projects.storage.read_committed(source.project_id)
        assert current.project.facts.mode == "digest" and current.pre_draft is None
        assert first.calls == second.calls == ["processing-model"] and not service.admission.locked()
    finally:
        await service.shutdown()
        factory.verify()
        service.supervisor.clock.verify()
