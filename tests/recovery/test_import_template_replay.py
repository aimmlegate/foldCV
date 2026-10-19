"""Regressions found in the six recorded native imports."""

from collections import Counter
from types import SimpleNamespace

import pytest

from packages.resume_core.import_agent import assemble_agent_import
from packages.resume_core.import_content import update_content
from packages.resume_core.import_cleanup import clean_list_text, contact_key
from packages.resume_core.import_facts import assemble_import_facts, import_date_field, record_fields
from packages.resume_core.import_layout import arrange_import
from packages.resume_core.models.importing import ImportContent
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import panel_mutation
from packages.resume_core.rich_presentation import authored_text
from tests.recovery.test_agent_import import draft_fixture, selected_service
from tests.recovery.test_import_content import paragraphs_fixture
from tests.recovery.test_rich_panel import edit


@pytest.mark.parametrize("text,expected", [
    ("•\n", ""), (" • ", ""), ("•\n• \nBuilt a service.\n", "Built a service.\n"),
    ("• - Delivered a service.\n", "• Delivered a service.\n"),
    ("-1 is a value; C++ and C# stay.\n", "-1 is a value; C++ and C# stay.\n"),
    ("A • B\n-\n", "A • B\n-\n"),
])
def test_list_cleanup_removes_only_empty_or_duplicate_markers(text, expected):
    assert clean_list_text(text) == expected


def test_contact_deduplication_keeps_qualifiers_and_distinct_addresses():
    assert contact_key("Почта: one@example.test") == contact_key("Эл. почта: one@example.test")
    assert contact_key("Telegram: @example") == contact_key("Telegram: example")
    assert contact_key("one@example.test (preferred)") != contact_key("one@example.test")
    assert contact_key("other@example.test") != contact_key("one@example.test")
    assert contact_key("Telegram: example (work)") != contact_key("Telegram: example")


@pytest.mark.asyncio
async def test_contact_rows_follow_geometry_and_exact_duplicates_keep_all_source_links(tmp_path, monkeypatch):
    from packages.resume_core.models.contracts import SourceStructure

    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    texts = ["Example Candidate\n", "Email\n", "Phone\n", "one@example.test\n", "+123\n",
        "one@example.test\n", "one@example.test (preferred)\n", "•\n", "Example Candidate\n",
        "Different Candidate\n", "• - Built a service.\n"]
    sources, parts, paragraphs = paragraphs_fixture(texts, pages=[1] * len(texts))
    for index, bounds in {1: [10, 20, 50, 30], 2: [10, 40, 50, 50],
            3: [80, 20.5, 160, 30.5], 4: [80, 40.5, 140, 50.5]}.items():
        sources[0].units[index].structure = SourceStructure(bounds=bounds)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    request = ImportContent(profile={"name": "Example Candidate", "refs": ["p1"]}, facts=[],
        sections=[{"category": "identity", "refs": ["p1"]},
            {"category": "contacts", "refs": ["p2-p7"]},
            {"category": "experience", "heading": "Work", "refs": ["p8-p11"]}])
    draft = update_content(draft_fixture(), request, paragraphs, parts)
    draft.finished = True
    try:
        project = assemble_agent_import(workspace, draft)
        visible = "\n".join(authored_text(b) for b in project.document.blocks())
        assert "Email: one@example.test" in visible and "Phone: +123" in visible
        assert visible.count("Example Candidate") == 1 and "Different Candidate" in visible
        assert "• -" not in visible and "Built a service." in visible
        assert not any(authored_text(b).strip() == "•" for b in project.document.blocks())
        assert "one@example.test (preferred)" in visible
        assert project.sources == sources
        assert "list marker" in project.import_coverage[7].reason
        assert "Repeated source name" in project.import_coverage[8].reason
        assert all(project.import_coverage[i].block_ids for i in range(1, 7))
    finally:
        await service.shutdown()


def test_contact_geometry_does_not_pair_ambiguous_rows_or_different_pages():
    from packages.resume_core.import_cleanup import compact_contacts
    from packages.resume_core.models.contracts import SourceStructure

    for pages, boxes in [([1, 2], [[10, 20, 40, 30], [80, 20, 120, 30]]),
            ([1, 1, 1], [[10, 20, 40, 30], [80, 20, 120, 30], [140, 20, 180, 30]])]:
        texts = [f"Different {index}\n" for index in range(len(pages))]
        sources, _parts, _paragraphs = paragraphs_fixture(texts, pages=pages)
        blocks, metadata = [], {}
        for index, (unit, box) in enumerate(zip(sources[0].units, boxes, strict=True)):
            unit.structure = SourceStructure(bounds=box)
            identifier = str(index)
            blocks.append({"id": identifier, "type": "paragraph", "content": [{"type": "text", "text": unit.text}],
                "provenance": [{"kind": "source", "evidence": [{"sourceId": sources[0].id, "unitId": unit.id}]}]})
            metadata[identifier] = SimpleNamespace(category="contacts", id=f"outline_0_p{index}")
        assert compact_contacts(blocks, metadata, sources) == blocks


@pytest.mark.asyncio
async def test_wrapped_identity_is_bound_once_and_name_edits_reach_the_header(tmp_path, monkeypatch):
    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    texts = ["Example\nCandidate\n", "Engineer\n", "Example Candidate\n", "Built a service.\n"]
    sources, parts, paragraphs = paragraphs_fixture(texts)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    request = ImportContent(profile={"name": "Example Candidate", "title": "Engineer", "refs": ["p1-p2"]},
        facts=[{"kind": "note", "text": "Keep a source note.", "refs": ["p4"]}],
        sections=[{"category": "identity", "refs": ["p1-p2"]}, {"category": "summary", "refs": ["p3-p4"]}])
    draft = update_content(draft_fixture(), request, paragraphs, parts)
    draft.finished = True
    try:
        project = assemble_agent_import(workspace, draft)
        assert len(project.document.regions[0].blocks) == 2
        name = project.document.regions[0].blocks[0]
        assert authored_text(name).strip() == "Example Candidate"
        assert any(span.type == "fact_field" and span.field_key == "name" for span in name.content)
        assert sum(authored_text(b).strip() == "Example Candidate" for b in project.document.blocks()) == 1
        workspace.project = project
        workspace.pre_draft = None
        workspace.project_revision, workspace.document_revision = project.revision, project.document.revision
        changed, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
            edit(workspace, recordId="candidate", values={"name": "Renamed Candidate"})))
        assert authored_text(changed.project.document.regions[0].blocks[0]).strip() == "Renamed Candidate"
        assert changed.project.sources == sources
    finally:
        await service.shutdown()


@pytest.mark.parametrize("text,value", [
    ("Июль 2021", {"precision": "month", "year": 2021, "month": 7, "day": None}),
    ("7 марта 2005", {"precision": "day", "year": 2005, "month": 3, "day": 7}),
    ("07.2021", {"precision": "month", "year": 2021, "month": 7, "day": None}),
    ("March 2025", {"precision": "month", "year": 2025, "month": 3, "day": None}),
    ("январь 2020 г.", {"precision": "month", "year": 2020, "month": 1, "day": None}),
    ("около июля 2021", None), ("31 февраля 2021", None), ("весна 2024", None),
])
def test_import_dates_decode_only_unambiguous_values_and_keep_the_raw_text(text, value):
    result = import_date_field(text)
    assert result["value"] == value and result["rawText"] == text


@pytest.mark.parametrize("kind", [None, "text", "note"])
def test_freeform_note_accepts_the_recorded_text_discriminator(kind):
    fact = {"text": "A source detail that needs review.", "refs": ["p1"]}
    if kind is not None:
        fact["kind"] = kind
    request = ImportContent(facts=[fact])
    assert request.facts[0].text == fact["text"]


def test_present_flag_does_not_discard_a_conflicting_raw_end_date():
    _sources, parts, paragraphs = paragraphs_fixture(["Orion: July 2021 — March 2025; current?\n"])
    request = ImportContent(facts=[{"kind": "employment", "employer": "Orion", "refs": ["p1"],
        "periods": [{"start": "July 2021", "end": "March 2025", "present": True}]}])
    draft = update_content(draft_fixture(), request, paragraphs, parts)
    records, _evidence, _links = assemble_import_facts(draft, lambda kind, key: f"{kind}-{key}", lambda keys: [])
    period = records[0]["periods"][0]
    assert period["start"]["value"]["month"] == 7
    assert period["end"]["rawText"] == period["present"]["rawText"] == "March 2025"
    assert period["end"]["value"]["year"] == 2025 and period["present"]["value"] is True
    anchors = dict(record_fields(records[0]))
    assert f"period:{period['id']}:end" not in anchors
    assert anchors[f"period:{period['id']}:present"] == "March 2025"


def test_focus_selection_keeps_every_underlying_technology_record():
    labels = [f"Custom skill {index}" for index in range(13)]
    _sources, parts, paragraphs = paragraphs_fixture([", ".join(labels) + "\n"])
    draft = update_content(draft_fixture(), ImportContent(facts=[
        {"kind": "technology", "technical": True, "display": label, "refs": ["p1"]} for label in labels]), paragraphs, parts)
    identify = lambda kind, key: f"{kind}-{key}"
    records, _evidence, _links = assemble_import_facts(draft, identify, lambda keys: [])
    regions = arrange_import({"header": [], "sidebar": [], "main": []},
        {"source": SimpleNamespace(category="skills")}, records, identify)
    assert regions["sidebar"] == []
    assert [record["display"]["rawText"] for record in records] == labels


def test_focus_prefers_known_tools_without_discarding_unknown_source_skills():
    labels = [f"Custom source skill {index}" for index in range(12)] + ["Linux", "Docker"]
    _sources, parts, paragraphs = paragraphs_fixture([", ".join(labels) + "\n"])
    draft = update_content(draft_fixture(), ImportContent(facts=[
        {"kind": "technology", "display": label, "refs": ["p1"]} for label in labels] + [
            {"kind": "employment", "employer": "Orion", "technologies": ["Redis"], "refs": ["p1"]}]), paragraphs, parts)
    identify = lambda kind, key: f"{kind}-{key}"
    records, *_ = assemble_import_facts(draft, identify, lambda keys: [])
    result = arrange_import({"header": [], "sidebar": [], "main": []},
        {"source": SimpleNamespace(category="skills")}, records, identify)
    focus = result["sidebar"][0]["children"]
    assert ["".join(span["text"] for span in b["content"]) for b in focus[:3]] == ["Linux", "Docker", "Redis"]
    assert len(focus) == 3 and [r["display"]["rawText"] for r in records if r["kind"] == "technology"] == labels + ["Redis"]


@pytest.mark.asyncio
@pytest.mark.parametrize("heading", ["EXPERIENCE", "Orion"])
async def test_split_job_outlines_keep_one_experience_band_and_no_empty_continuations(tmp_path, monkeypatch, heading):
    service, identifier, *_ = await selected_service(tmp_path, monkeypatch)
    texts = ["Example Candidate\n", "Orion\n", "Engineer\n", "Built service A.\n", "Continued service A.\n",
        "Delta\n", "Built service B.\n", "A unique source subheading\n"]
    sources, parts, paragraphs = paragraphs_fixture(texts)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources, workspace.pre_draft.selected_source_id = sources, sources[0].id
    request = ImportContent(profile={"name": "Example Candidate", "refs": ["p1"]}, facts=[
        {"kind": "employment", "employer": "Orion", "role": "Engineer", "refs": ["p2-p4"]},
        {"kind": "employment", "employer": "Delta", "refs": ["p6-p8"]}], sections=[
        {"category": "identity", "refs": ["p1"]},
        {"category": "experience", "heading": heading, "refs": ["p2-p4"]},
        {"category": "experience", "heading": "Orion (continued)", "refs": ["p5"]},
        {"category": "experience", "heading": "Delta", "refs": ["p6-p7"]},
        {"category": "experience", "heading": "A unique source subheading", "refs": ["p8"]}])
    draft = update_content(draft_fixture(), request, paragraphs, parts)
    draft.finished = True
    try:
        project = assemble_agent_import(workspace, draft)
        main = project.document.regions[2].blocks
        assert len(main) == 1 and authored_text(main[0]) == "EXPERIENCE"
        assert len(main[0].children) == 2
        assert [authored_text(job.children[0]).strip() for job in main[0].children] == ["Orion", "Delta"]
        assert [authored_text(b).strip() for b in main[0].children[0].children][-2:] == ["Built service A.", "Continued service A."]
        visible = "\n".join(authored_text(b) for b in project.document.blocks())
        assert "(continued)" not in visible
        assert all(text.strip() in visible for text in texts)
        assert all(row.block_ids for row in project.import_coverage)
        assert project.sources == sources
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_focus_is_an_editable_projection_while_duplicate_only_footer_groups_stay_in_source(tmp_path, monkeypatch):
    service, identifier, _runtime, _sessions = await selected_service(tmp_path, monkeypatch)
    texts = ["Example Candidate\n", "Engineer\n", "Orion\n", "Built a service without repeating the employer.\n",
        "EXPERIENCE: 5 YEARS\n", "SKILLS\n", "General: Python, Linux, Docker\n", "Example Candidate\n", "Example Candidate\n",
        "Unique footer contact: candidate@example.test\n"]
    sources, parts, paragraphs = paragraphs_fixture(texts)
    workspace = service.workspaces[identifier]
    workspace.pre_draft.sources = sources
    workspace.pre_draft.selected_source_id = sources[0].id
    request = ImportContent(profile={"name": "Example Candidate", "title": "Engineer", "refs": ["p1-p2"]},
        facts=[{"kind": "employment", "employer": "Orion", "refs": ["p3"]},
            {"kind": "technology", "display": "Python", "refs": ["p7"]},
            {"kind": "technology", "display": "Linux", "refs": ["p7"]},
            {"kind": "technology", "display": "Docker", "refs": ["p7"]},
            {"kind": "note", "text": "An uncertain source detail.", "refs": ["p4"]}],
        sections=[{"category": "identity", "refs": ["p1-p2"]},
            {"category": "experience", "heading": "experience", "refs": ["p5", "p3-p4"]},
            {"category": "skills", "heading": "skills", "refs": ["p6-p7"]},
            {"category": "other", "heading": "Page footers", "refs": ["p8-p9"]},
            {"category": "other", "refs": ["p10"]}])
    draft = update_content(draft_fixture(), request, paragraphs, parts)
    draft.finished = True
    project = assemble_agent_import(workspace, draft)
    try:
        focus = project.document.regions[1].blocks[0]
        assert focus.props.presentation == "focus"
        assert [authored_text(b) for b in focus.children] == ["Python", "Linux", "Docker"]
        visible = "\n".join(authored_text(b) for b in project.document.blocks())
        assert visible.count("Example Candidate") == 1
        assert visible.count("EXPERIENCE") == visible.count("SKILLS") == 1
        assert "Page footers" not in visible and "Unique footer contact: candidate@example.test" in visible
        assert project.sources == sources
        assert [row.disposition for row in project.import_coverage[7:9]] == ["excluded", "excluded"]
        assert all("original" in row.reason for row in project.import_coverage[7:9])
        experience = next(b for b in project.document.regions[2].blocks if authored_text(b) == "EXPERIENCE: 5 YEARS\n")
        assert len(experience.children) == 1
        assert authored_text(experience.children[0].children[-1]) == texts[3]
        assert any(link.kind == "working_owner" for link in experience.children[0].children[-1].provenance)
        record = next(r for r in project.facts.records if r.kind == "technology" and r.display.value == "Linux")
        workspace.project = project
        workspace.pre_draft = None
        workspace.project_revision = project.revision
        workspace.document_revision = project.document.revision
        changed, _ = apply_rich_mutation(workspace, panel_mutation(workspace,
            edit(workspace, recordId=record.id, values={"display": "Rust"})))
        changed_focus = changed.project.document.regions[1].blocks[0]
        assert authored_text(changed_focus.children[1]) == "Rust"
        assert "General: Python, Rust, Docker" in "".join(authored_text(b) for b in changed.project.document.blocks())
        assert Counter(r.kind for r in changed.project.facts.records) == Counter(r.kind for r in project.facts.records)
        assert changed.project.sources == project.sources
    finally:
        await service.shutdown()
