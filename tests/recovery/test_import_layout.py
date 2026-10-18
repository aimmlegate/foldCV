"""Import layout keeps the reference hierarchy separate from source wording."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
import pytest

from packages.resume_core.import_agent import assemble_agent_import
from packages.resume_core.import_content import update_content
from packages.resume_core.models.importing import ImportContent
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rich_presentation import authored_text, presentation
from tests.recovery.test_agent_import import draft_fixture, selected_service
from tests.recovery.test_import_content import paragraphs_fixture


@pytest.mark.asyncio
async def test_identity_metadata_stays_out_of_header_and_job_styles_survive_export(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    texts = ["Example Candidate\n", "Platform engineer\n", "Belgrade; remote only\n",
        "EXPERIENCE\n", "2021 — 2023\n", "Orion\n", "Engineer\n", "Python, PostgreSQL\n",
        "- Built a service.\n", "Delta\n", "2024 — present\n", "Lead\n", "Go, Python\n",
        "- Delivered another service.\n", "ABOUT\n", "A short source profile.\n",
        "SKILLS\n", "Linux\n", "Docker\n", "EDUCATION\n", "University\n",
        "TOOLS\n", "An unknown list with two entries: A, B.\n"]
    sources, parts, paragraphs = paragraphs_fixture(texts)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    saved = update_content(draft_fixture(), ImportContent(
        profile={"name": "Example Candidate", "title": "Platform engineer", "refs": ["p1-p3"]},
        facts=[
            {"kind": "employment", "employer": "Orion", "role": "Engineer", "technologies": ["Python", "PostgreSQL"],
                "periods": [{"start": "2021", "end": "2023"}], "refs": ["p5-p9"]},
            {"kind": "employment", "employer": "Delta", "role": "Lead", "technologies": ["Go", "Python"],
                "periods": [{"start": "2024", "end": "present", "present": True}], "refs": ["p10-p14"]},
            {"kind": "technology", "display": "Linux\n", "refs": ["p18"]},
            {"kind": "technology", "display": "Docker\n", "refs": ["p19"]},
        ],
        sections=[{"category": "identity", "refs": ["p1-p3"]},
            {"category": "summary", "heading": "ABOUT", "refs": ["p15-p16"]},
            {"category": "experience", "heading": "EXPERIENCE", "refs": ["p4-p14"]},
            {"category": "skills", "heading": "SKILLS", "refs": ["p17-p19"]},
            {"category": "education", "heading": "EDUCATION", "refs": ["p20-p21"]},
            {"category": "skills", "heading": "TOOLS", "refs": ["p22-p23"]}]), paragraphs, parts)
    saved.finished = True
    project = assemble_agent_import(workspace, saved)
    try:
        header, sidebar, main = project.document.regions
        assert [authored_text(block) for block in header.blocks] == texts[:2]
        assert "Belgrade; remote only\n" in "".join(authored_text(b) for b in project.document.blocks())
        assert all(authored_text(b) != texts[2] for b in header.blocks)
        visible = "".join(authored_text(b) for b in project.document.blocks())
        assert all(visible.count(line.removeprefix("- ").strip()) == 1 for line in texts)
        assert project.sources == sources and all(row.block_ids for row in project.import_coverage)
        roles = presentation(project.document, project.facts).blocks
        profile = next(b for b in main.blocks if authored_text(b).strip() == "ABOUT")
        assert [authored_text(b).strip() for b in main.blocks] == ["ABOUT", "EXPERIENCE", "TOOLS"]
        assert roles[profile.id].role == "profile_heading"
        experience = next(b for b in main.blocks if authored_text(b).strip() == "EXPERIENCE")
        assert roles[experience.id].role == "section_heading"
        jobs = experience.children
        assert len(jobs) == 2 and all(job.props.record_id for job in jobs)
        assert [authored_text(job.children[0]) for job in jobs] == ["Orion\n", "Delta\n"]
        assert all(roles[job.children[0].id].role == "job_heading" for job in jobs)
        assert roles[jobs[0].children[1].id].role == "support"
        stack = jobs[0].children[3]
        assert all(span.styles.background_color == "#EFEFEF" for span in stack.content if span.type == "fact_field")
        focus = next(b for b in sidebar.blocks if authored_text(b).strip() == "SKILLS")
        assert focus.props.presentation == "focus"
        assert all(roles[b.id].role == "focus_entry" for b in focus.children)
        assert all(roles[b.id].logo for b in focus.children)
        with ZipFile(BytesIO(render_rich_docx(project.document, facts=project.facts))) as archive:
            xml = etree.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs_xml = xml.xpath("//w:p", namespaces=ns)
        def paragraph(text):
            return next(p for p in paragraphs_xml if "".join(p.xpath(".//w:t/text()", namespaces=ns)) == text)
        name = paragraph("Example Candidate")
        assert set(name.xpath(".//w:rFonts/@w:ascii", namespaces=ns)) == {"Source Sans Pro Black"}
        assert set(name.xpath(".//w:sz/@w:val", namespaces=ns)) == {"36"}
        assert set(paragraph("Orion").xpath(".//w:sz/@w:val", namespaces=ns)) == {"24"}
        assert not name.xpath(".//w:br", namespaces=ns)
        assert not paragraph("Orion").xpath(".//w:br", namespaces=ns)
        assert set(paragraph("EXPERIENCE").xpath(".//w:rFonts/@w:ascii", namespaces=ns)) == {"Source Sans Pro Black"}
        assert paragraph("ABOUT").xpath("w:pPr/w:ind/@w:left", namespaces=ns) == ["100"]
        assert xml.xpath("//w:shd[@w:fill='EFEFEF']", namespaces=ns)
        assert paragraph("Built a service.").xpath("w:pPr/w:numPr", namespaces=ns)
        assert paragraph("Built a service.").xpath("w:pPr/w:ind/@w:hanging", namespaces=ns) == ["260"]
    finally:
        await service.shutdown()
