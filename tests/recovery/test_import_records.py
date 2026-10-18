"""Structured import records preserve uncertain text and reuse panel history."""

from io import BytesIO
import json
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pytest

from packages.resume_core.background_inverse import inverse_mutation
from packages.resume_core.import_content import draft_content, update_content
from packages.resume_core.models.importing import ImportContent, ImportContentFinish
from packages.resume_core.rich_archive import open_rich_archive
from packages.resume_core.rich_format import format_document
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import panel_mutation
from packages.resume_core.rich_presentation import authored_text
from packages.resume_core.rules import RulesStore
from resume_api.agent.runtime import RuntimeResult
from resume_api.rich_projects import RichProjectService
from tests.recovery.test_agent_import import draft_fixture
from tests.recovery.test_import_content import paragraphs_fixture
from tests.recovery.test_rich_panel import edit
from tests.support.importing import importer, read_source


TEXT = ("Example Candidate\nPlatform engineer\nBelgrade\nOrion\nEngineer\n2021 — 2023\n"
    "Python, PostgreSQL\nDelta\nLead\nAbout 2022 — spring 2024\nPython, Go\nGeneral: Linux\n"
    "Technical university\nIncomplete course\nAround 2010\nEnglish: B1/B2?\n"
    "Undated project for an unnamed client\nThe team reduced latency by at least 20%.\n")
FACTS = [
    {"kind": "employment", "employer": "Orion", "role": "Engineer",
        "periods": [{"start": "2021", "end": "2023"}], "technologies": ["Python", "PostgreSQL"], "refs": ["p4-p7"]},
    {"kind": "employment", "employer": "Delta", "role": "Lead",
        "periods": [{"start": "About 2022", "end": "spring 2024"}], "technologies": ["Python", "Go"], "refs": ["p8-p11"]},
    {"kind": "technology", "display": "Linux", "refs": ["p12"]},
    {"kind": "education", "institution": "Technical university", "qualification": "Incomplete course",
        "completion": "Around 2010", "refs": ["p13-p15"]},
    {"kind": "language", "language": "English", "level": "B1/B2?", "refs": ["p16"]},
    {"kind": "employment", "employer": "Unnamed client; employer relationship unclear", "refs": ["p17"]},
    {"text": "At least 20% lower latency is a team result.", "refs": ["p18"]},
]


async def save_records(session, _value, _cancel):
    await read_source(session)
    facts = ImportContent(facts=FACTS, profile={"name": "Example Candidate", "title": "Platform engineer",
        "location": "Belgrade", "refs": ["p1-p3"]})
    assert session.dispatcher.preflight({"name": "save_import", "arguments": {"request": facts.model_dump(by_alias=True)}}) is None
    assert (await session.dispatcher.call("save_import", facts))["durable"]
    saved = session.coordinator.load()
    assert draft_content(saved, session.coordinator.paragraphs)[1]["fact"]["kind"] == "employment"
    assert saved.model_validate_json(saved.model_dump_json(by_alias=True)) == saved
    assert (await session.dispatcher.call("save_import", ImportContent(sections=[
        {"category": "identity", "refs": ["p1-p2"]}, {"category": "contacts", "refs": ["p3"]},
        {"category": "experience", "refs": ["p4-p11", "p17-p18"]},
        {"category": "skills", "refs": ["p12"]}, {"category": "education", "refs": ["p13-p15"]},
        {"category": "languages", "refs": ["p16"]}])))["durable"]
    assert (await session.dispatcher.call("finish_import", ImportContentFinish()))["readyForPublication"]
    return RuntimeResult(state="completed")


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [False, True])
async def test_record_import_publishes_edits_undoes_exports_and_transfers_without_losing_source(tmp_path, monkeypatch, queued):
    if queued:
        from tests.recovery.test_background_agent import environment
        from tests.recovery.test_background_fixed_jobs import fixed_request, settled
        jobs, factory, *_ = await environment(tmp_path)
        service = jobs.projects
        service.provider_factory = lambda: (object(), "processing-model")
        runtime, _sessions = importer(monkeypatch, save_records, admission=jobs.admission)
        jobs.runtime = runtime
    else:
        runtime, _sessions = importer(monkeypatch, save_records)
        service = RichProjectService(tmp_path / "operations", RulesStore(tmp_path / "store"),
            lambda: (object(), "fixture"), import_runtime=runtime)
    try:
        selected = await service.select(TEXT.encode(), "records.txt", True)
        identifier = selected.project_id
        original = selected.pre_draft.sources[0].model_copy(deep=True)
        if queued:
            reply, _ = await jobs.fixed.submit(identifier, fixed_request(jobs, identifier, "records", {"kind": "processing"}))
            await settled(jobs, identifier, reply.job.id, publication="saved")
        else:
            generation = service.start(identifier)
            await service.tasks[(identifier, generation)]
            assert service.generations[identifier].status == "completed", service.generations[identifier]
        workspace = service.read(identifier)
        project = workspace.project
        assert project.facts.mode == "imported"
        assert {r.kind for r in project.facts.records} == {"candidate", "employment", "technology", "education", "language", "claim"}
        employment = [r for r in project.facts.records if r.kind == "employment"]
        assert len(employment) == 3 and not employment[2].periods and employment[2].role.value is None
        assert employment[0].periods[0].start.value.year == 2021
        assert employment[1].periods[0].start.raw_text == "About 2022"
        assert employment[1].periods[0].start.value is None
        education = next(r for r in project.facts.records if r.kind == "education")
        assert education.completion.raw_text == "Around 2010" and education.completion.value is None
        assert next(r for r in project.facts.records if r.kind == "language").level.raw_text == "B1/B2?"
        assert format_document(project.document, project.facts) == project.document
        visible = "".join(authored_text(b) for b in project.document.blocks())
        assert all(visible.count(line) == TEXT.count(line) for line in TEXT.splitlines(True))
        assert project.sources == [original] and all(row.block_ids for row in project.import_coverage)
        technologies = [r for r in project.facts.records if r.kind == "technology"]
        first = next(r for r in technologies if r.job_id == employment[0].id and r.display.value == "Python")
        second = next(r for r in technologies if r.job_id == employment[1].id and r.display.value == "Python")
        assert next(r for r in technologies if r.display.value == "Linux").job_id is None
        changed, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
            edit(workspace, recordId=first.id, values={"display": "Rust"})))
        assert next(r for r in changed.project.facts.records if r.id == second.id) == second
        changed_text = "".join(authored_text(b) for b in changed.project.document.blocks())
        assert "Rust, PostgreSQL" in changed_text and "Python, Go" in changed_text
        assert changed.project.sources == project.sources and changed.project.evidence_records == project.evidence_records
        inverse = inverse_mutation(workspace, changed, mutation_id="undo-record", session_id="test")
        restored, _ = apply_rich_mutation(changed, inverse)
        assert "".join(authored_text(b) for b in restored.project.document.blocks()) == visible
        assert restored.project.facts.mode == "imported"
        note = next(r for r in project.facts.records if r.kind == "claim")
        removed, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
            edit(workspace, operation="remove", recordId=note.id)))
        assert "".join(authored_text(b) for b in removed.project.document.blocks()) == visible
        _snapshot, raw = await service.export(identifier)
        with ZipFile(BytesIO(raw)) as archive:
            xml = ET.fromstring(archive.read("word/document.xml"))
        exported = "".join(xml.itertext())
        assert all("".join(line.split()) in "".join(exported.split()) for line in TEXT.splitlines())
        transferred, *_ = open_rich_archive(service.portable(identifier), "transfer")
        assert transferred.project.facts == project.facts
        assert transferred.project.document == project.document
        reopened = RichProjectService(tmp_path / "reopened", service.rules, lambda: None)
        assert reopened.read(identifier).project.facts == project.facts
        await reopened.shutdown()
        assert len(runtime.calls) == 1
    finally:
        if queued:
            await jobs.shutdown()
            factory.verify()
            jobs.supervisor.clock.verify()
        else:
            await service.shutdown()


def test_partial_records_keep_raw_dates_and_checkpoint_replacement_is_exact():
    _sources, parts, paragraphs = paragraphs_fixture(["Ambiguous employer\n", "2030 — 2029\n", "Custom skill\n"])
    request = ImportContent(facts=[{"kind": "employment", "periods": [{"start": "2030", "end": "2029"}],
        "refs": ["p1-p2"]}, {"kind": "technology", "display": "Custom skill", "refs": ["p3"]}])
    saved = update_content(draft_fixture(), request, paragraphs, parts)
    assert saved.facts[0].record.employer == "" and saved.facts[0].record.periods[0].end == "2029"
    resumed = saved.model_validate_json(saved.model_dump_json(by_alias=True))
    assert update_content(resumed, request, paragraphs, parts) == saved
    view = draft_content(saved, paragraphs)
    assert view[1]["fact"]["periods"][0]["start"] == "2030" and "sourceKeys" not in json.dumps(view)
    request.facts.reverse()
    reordered = update_content(saved, request, paragraphs, parts)
    assert [f.record.kind for f in reordered.facts] == ["technology", "employment"]
    assert reordered.sequence == saved.sequence + 1
