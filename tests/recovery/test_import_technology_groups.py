"""Skill-owned tool groups and readable courses survive import and export."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
import pytest

from packages.resume_core.import_agent import ImportFailure, assemble_agent_import
from packages.resume_core.import_content import draft_content, update_content
from packages.resume_core.models.importing import ImportContent
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rich_archive import open_rich_archive
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import panel_mutation
from packages.resume_core.rich_presentation import authored_text, presentation
from tests.recovery.test_agent_import import draft_fixture, selected_service
from tests.recovery.test_import_content import paragraphs_fixture
from tests.recovery.test_rich_panel import edit


HEADINGS = ["ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ", "ЯП, СУБД, ФРЕЙМВОРКИ, БИБЛИОТЕКИ", "ОС"]
COURSES = ["2019 — Provider AN14,AN51,AN30G,AN61,LX071G,LX072G,SSF0G",
    "2018 — Academy Long qualification (certificate), advanced systems course"]
TEXTS = ["Candidate", "Technical skills", "Docker, Jira, Python, PostgreSQL, Linux",
    "Leadership and communication", "ПОВЫШЕНИЕ КВАЛИФИКАЦИИ И КУРСЫ", *COURSES,
    "Company: Python, 2020–2022"]


def request():
    return ImportContent(profile={"name": "Candidate", "refs": ["p1"]},
        facts=[{"kind": "technology", "display": name, "technical": True, "refs": ["p3"]}
            for name in ["Docker", "Jira", "Python", "PostgreSQL", "Linux"]] + [
                {"kind": "employment", "employer": "Company", "technologies": ["Python"], "refs": ["p8"]}],
        sections=[{"category": "identity", "blocks": [{"type": "heading", "refs": ["p1"]}]},
            {"category": "skills", "blocks": [{"type": "section", "refs": ["p2"]},
                {"type": "paragraph", "refs": ["p3"]}]},
            {"category": "other", "blocks": [{"type": "paragraph", "refs": ["p4"]}]},
            {"category": "education", "region": "sidebar", "blocks": [{"type": "section", "refs": ["p5"]},
                {"type": "list_item", "refs": ["p6"]}, {"type": "list_item", "refs": ["p7"]}]},
            {"category": "experience", "refs": ["p8"]}],
        technologyGroups=[{"heading": heading, "technologies": tools, "refs": ["p2-p3"]}
            for heading, tools in zip(HEADINGS, [["Docker", "Jira"], ["Python", "PostgreSQL"], ["Linux"]])])


@pytest.mark.asyncio
async def test_groups_replace_standalone_technical_sections_and_keep_jobs_soft_skills_courses_and_facts(tmp_path, monkeypatch):
    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    sources, parts, paragraphs = paragraphs_fixture(TEXTS)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources, workspace.pre_draft.selected_source_id = sources, sources[0].id
    saved = update_content(draft_fixture(), request(), paragraphs, parts)
    saved.finished = True
    try:
        project = assemble_agent_import(workspace, saved)
        old = saved.model_copy(deep=True)
        old.technology_groups = []
        baseline = assemble_agent_import(workspace, old)
        assert project.facts == baseline.facts and project.evidence_records == baseline.evidence_records
        assert project.sources == sources
        assert [authored_text(b) for b in project.document.regions[2].blocks if b.id.startswith("technology_group_")] == HEADINGS
        for heading, expected in zip(HEADINGS, ["Docker, Jira", "Python, PostgreSQL", "Linux"]):
            group = next(b for b in project.document.blocks() if authored_text(b) == heading)
            assert len(group.children) == 1 and group.children[0].type == "paragraph"
            assert authored_text(group.children[0]) == expected
            assert presentation(project.document, project.facts).blocks[group.children[0].id].role == "body"
        assert not any(authored_text(b) in {"Technical skills", TEXTS[2]} for b in project.document.blocks())
        assert any(authored_text(b) == TEXTS[3] for b in project.document.blocks())
        assert any(authored_text(b) == TEXTS[7] for b in project.document.blocks())
        assert project.import_coverage[1].disposition == project.import_coverage[2].disposition == "placed"
        assert all(row.block_ids for row in project.import_coverage)
        courses = next(b for b in project.document.regions[1].blocks if authored_text(b) == TEXTS[4])
        assert [authored_text(b) for b in courses.children] == COURSES
        assert all(b.type == "bullet_list" for b in courses.children)
        with ZipFile(BytesIO(render_rich_docx(project.document, facts=project.facts))) as archive:
            xml = etree.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = xml.xpath("//w:p", namespaces=ns)
        text = ["".join(p.xpath(".//w:t/text()", namespaces=ns)) for p in paragraphs]
        assert all(text.count(heading) == 1 for heading in HEADINGS)
        assert "Technical skills" not in text
        for value in ["Docker, Jira", "Python, PostgreSQL", "Linux"]:
            paragraph = next(p for p, text_value in zip(paragraphs, text) if text_value == value)
            assert not paragraph.xpath("./w:pPr/w:numPr", namespaces=ns)
        for course in COURSES:
            paragraph = next(p for p, value in zip(paragraphs, text) if value == course)
            assert paragraph.xpath("./w:pPr/w:numPr", namespaces=ns)
            widths = paragraph.xpath("ancestor::w:tc[1]/w:tcPr/w:tcW/@w:w", namespaces=ns)
            assert widths and int(widths[0]) < 3000
            assert paragraph.xpath("./w:pPr/w:spacing/@w:after", namespaces=ns) == ["120"]
        workspace.project, workspace.pre_draft = project, None
        workspace.project_revision, workspace.document_revision = project.revision, project.document.revision
        technology = next(r for r in project.facts.records if r.kind == "technology" and r.display.raw_text == "Python" and r.job_id is None)
        changed, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
            edit(workspace, recordId=technology.id, values={"display": "Python 3"})))
        python_group = next(b for b in changed.project.document.blocks() if authored_text(b) == HEADINGS[1])
        assert [authored_text(b) for b in python_group.children] == ["Python 3, PostgreSQL"]
        assert changed.project.sources == sources
        removed, _ = apply_rich_mutation(changed, panel_mutation(changed,
            edit(changed, operation="remove", recordId=technology.id, values={})))
        python_group = next(b for b in removed.project.document.blocks() if authored_text(b) == HEADINGS[1])
        assert [authored_text(b) for b in python_group.children] == ["PostgreSQL"]
        assert removed.project.sources == sources
    finally:
        await service.shutdown()


def test_group_names_count_order_membership_and_column_are_open_and_saved_independently():
    _sources, parts, paragraphs = paragraphs_fixture(["One Two Three Four"])
    groups = [{"heading": label, "region": "sidebar" if index == 2 else "main",
        "technologies": [tool], "refs": ["p1"]} for index, (label, tool) in enumerate(
            [("New group D", "Four"), ("Custom B", "Two"), ("Category X", "One"), ("Later C", "Three")])]
    saved = update_content(draft_fixture(), ImportContent(technologyGroups=groups), paragraphs, parts)
    readable = next(item["technologyGroups"] for item in draft_content(saved, paragraphs) if "technologyGroups" in item)
    assert readable == groups
    assert update_content(saved, ImportContent(technologyGroups=readable), paragraphs, parts) == saved
    updated = update_content(saved, ImportContent(facts=[{"text": "Keep source uncertainty.", "refs": ["p1"]}]), paragraphs, parts)
    assert updated.technology_groups == saved.technology_groups
    cleared = update_content(updated, ImportContent(technologyGroups=[]), paragraphs, parts)
    assert not cleared.technology_groups and cleared.facts == updated.facts
    before = saved.model_dump_json()
    with pytest.raises(ImportFailure, match="IMPORT_REFERENCE_INVALID"):
        update_content(saved, ImportContent(technologyGroups=[dict(groups[0], refs=["p99"])]), paragraphs, parts)
    assert saved.model_dump_json() == before


@pytest.mark.asyncio
async def test_a_main_summary_bound_only_to_job_tools_uses_body_typography(tmp_path, monkeypatch):
    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    sources, parts, paragraphs = paragraphs_fixture(["Company: Python, PostgreSQL"])
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources, workspace.pre_draft.selected_source_id = sources, sources[0].id
    saved = update_content(draft_fixture(), ImportContent(
        facts=[{"kind": "employment", "employer": "Company", "technologies": ["Python", "PostgreSQL"], "refs": ["p1"]}],
        sections=[{"category": "experience", "refs": ["p1"]}],
        technologyGroups=[{"heading": "Tools", "technologies": ["Python", "PostgreSQL"], "refs": ["p1"]}]), paragraphs, parts)
    saved.finished = True
    try:
        project = assemble_agent_import(workspace, saved)
        group = next(b for b in project.document.blocks() if authored_text(b) == "Tools")
        assert authored_text(group.children[0]) == "Python, PostgreSQL"
        assert presentation(project.document, project.facts).blocks[group.children[0].id].role == "body"
        assert all(record.job_id is not None for record in project.facts.records if record.kind == "technology")
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_partial_group_coverage_keeps_unique_source_and_has_no_ten_tool_cutoff(tmp_path, monkeypatch):
    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    tools = [f"SourceTool{index}" for index in range(12)]
    sources, parts, paragraphs = paragraphs_fixture(["Skills", ", ".join(tools), "Unique source qualification"])
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources, workspace.pre_draft.selected_source_id = sources, sources[0].id
    saved = update_content(draft_fixture(), ImportContent(sections=[{"category": "skills", "refs": ["p1-p3"]}],
        technologyGroups=[{"heading": "Custom tools", "technologies": tools, "refs": ["p2"]}]), paragraphs, parts)
    saved.finished = True
    try:
        project = assemble_agent_import(workspace, saved)
        group = next(b for b in project.document.blocks() if authored_text(b) == "Custom tools")
        assert [authored_text(b) for b in group.children] == [", ".join(tools)]
        assert any(authored_text(b).strip() == "Unique source qualification" for b in project.document.blocks())
        assert all(row.block_ids for row in project.import_coverage)
    finally:
        await service.shutdown()


@pytest.mark.parametrize("region", ["sidebar", "main"])
def test_course_column_and_item_boundaries_survive_a_saved_outline_reread(region):
    _sources, parts, paragraphs = paragraphs_fixture(TEXTS)
    content = request()
    next(section for section in content.sections if section.category == "education").region = region
    saved = update_content(draft_fixture(), content, paragraphs, parts)
    outlines = [item["section"] for item in draft_content(saved, paragraphs) if "section" in item]
    courses = next(section for section in outlines if section["category"] == "education")
    assert courses.get("region", "sidebar") == region
    assert [block["refs"] for block in courses["blocks"]] == [["p5"], ["p6"], ["p7"]]
    assert update_content(saved, ImportContent(sections=outlines), paragraphs, parts) == saved


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [False, True])
async def test_groups_survive_tool_checkpoint_publication_and_portable_transfer(tmp_path, monkeypatch, queued):
    from packages.resume_core.models.importing import ImportContentFinish, ImportRead
    from packages.resume_core.rules import RulesStore
    from resume_api.agent.runtime import RuntimeResult
    from resume_api.rich_projects import RichProjectService
    from tests.support.importing import importer, read_source

    async def parse(session, _value, _cancel):
        await read_source(session)
        assert (await session.dispatcher.call("save_import", request()))["durable"]
        read = await session.dispatcher.call("read_import", ImportRead(section="draft"))
        assert next(item["technologyGroups"] for item in read["items"] if "technologyGroups" in item)[0]["heading"] == HEADINGS[0]
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
        raw = ("\n".join(TEXTS) + "\n").encode()
        selected = await projects.select(raw, "groups.txt", False)
        identifier = selected.project_id
        if queued:
            reply, _ = await jobs.fixed.submit(identifier, fixed_request(jobs, identifier, "groups", {"kind": "processing"}))
            await settled(jobs, identifier, reply.job.id, publication="saved")
        else:
            generation = projects.start(identifier)
            await projects.tasks[(identifier, generation)]
            assert projects.generations[identifier].status == "completed"
        saved, _ = projects.storage.read_committed(identifier)
        transfer, originals, *_ = open_rich_archive(projects.portable(identifier), "group-transfer")
        assert transfer.project.document == saved.project.document and transfer.project.facts == saved.project.facts
        assert list(originals.values()) == [raw]
        assert [authored_text(b) for b in saved.project.document.regions[2].blocks if b.id.startswith("technology_group_")] == HEADINGS
        assert len(runtime.calls) == 1
    finally:
        if queued:
            await jobs.shutdown()
            factory.verify()
            jobs.supervisor.clock.verify()
        else:
            await projects.shutdown()
