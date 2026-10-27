"""Whole-year display, quick edits, sorting and missing-duration behavior."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
import pytest

from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import panel_mutation
from packages.resume_core.rich_presentation import authored_text, presentation
from packages.resume_core.technology_experience import technology_years
from packages.resume_core.rendering.rich_docx import render_rich_docx
from tests.facts.panel_fixtures import edit, job, technology_facts, technology_workspace
from tests.support.rich import capture


@pytest.mark.parametrize("statement,expected", [("1.5", 2), ("6,5 лет", 7), ("18 месяцев", 2),
    ("1 год 6 месяцев", 2), ("0", 0), ("unknown", None)])
def test_source_duration_rounds_to_whole_years_without_changing_the_saved_statement(statement, expected):
    facts, _ = technology_facts([{"kind": "technology", "display": "Python", "experience": statement}])
    assert technology_years(facts)["python"] == expected
    assert facts.records[0].experience.raw_text == statement


def test_closed_job_months_round_instead_of_truncating_and_overlaps_count_once():
    facts, _ = technology_facts([job("2020-01", "2021-06"), job("2021-01", "2021-06")])
    assert technology_years(facts)["python"] == 2


def test_focus_sorts_known_years_descending_and_keeps_unknown_last_without_a_subtitle():
    facts, document = technology_facts([{"kind": "technology", "display": "Linux"},
        {"kind": "technology", "display": "Python", "experience": "2"},
        {"kind": "technology", "display": "Docker", "experience": "6"},
        {"kind": "technology", "display": "DevOps", "technical": True},
        {"kind": "technology", "display": "NoIconTool", "technical": True}])
    focus = document.regions[1].blocks[0]
    assert [authored_text(b) for b in focus.children] == ["Docker", "Python", "Linux"]
    view = presentation(document, facts)
    assert [(entry.display, entry.years) for entry in view.focus_entries] == [("Docker", 6), ("Python", 2), ("Linux", None)]
    assert view.blocks[focus.children[-1].id].experience is None
    with ZipFile(BytesIO(render_rich_docx(document, facts=facts))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
    text = xml.xpath("//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"})
    assert "DevOps" not in text and "NoIconTool" not in text
    assert text.index("Docker") < text.index("Python") < text.index("Linux")
    assert not any("not stated" in value or "не указан" in value or "≈" in value or "year+" in value for value in text)


def test_quick_year_edit_resorts_in_the_same_mutation_and_can_be_cleared_undone_and_reloaded():
    workspace = technology_workspace([{"kind": "technology", "display": "Linux"},
        {"kind": "technology", "display": "Python", "experience": "2"}])
    facts = workspace.project.facts
    original = workspace.model_copy(deep=True)
    linux = next(record for record in facts.records if record.kind == "technology" and record.display.raw_text == "Linux")
    mutation = panel_mutation(workspace, edit(workspace, recordId=linux.id, values={"experience": "7"}))
    assert any(step.kind == "move_block" for step in mutation.steps)
    changed, _ = apply_rich_mutation(workspace, mutation)
    assert [authored_text(b) for b in changed.project.document.regions[1].blocks[0].children] == ["Linux", "Python"]
    assert [(entry.display, entry.years) for entry in presentation(changed.project.document, changed.project.facts).focus_entries] == [("Linux", 7), ("Python", 2)]
    transferred = WorkspaceV6.model_validate_json(changed.model_dump_json(by_alias=True))
    assert transferred.project.document == changed.project.document and transferred.project.facts == changed.project.facts
    cleared, _ = apply_rich_mutation(changed, panel_mutation(changed, edit(changed, recordId=linux.id, values={"experience": ""})))
    assert [authored_text(b) for b in cleared.project.document.regions[1].blocks[0].children] == ["Python", "Linux"]
    assert presentation(cleared.project.document, cleared.project.facts).focus_entries[-1].years is None
    before_record = next(record for record in original.project.facts.records if record.id == linux.id)
    after_record = next(record for record in changed.project.facts.records if record.id == linux.id)
    old_section, new_section = original.project.document.regions[1].blocks[0], changed.project.document.regions[1].blocks[0]
    restored, _ = apply_rich_mutation(changed, RichMutation(schemaVersion=1, projectId=changed.project_id,
        clientMutationId="undo-years", actionId="undo-years", kind="undo", capture=capture(), steps=[
            {"kind": "put_record", "beforeRevision": after_record.revision, "record": before_record.model_dump(by_alias=True)},
            {"kind": "put_block", "parentId": "sidebar", "afterId": None, "beforeRevision": new_section.revision,
                "block": old_section.model_dump(by_alias=True)}]))
    assert [authored_text(b) for b in restored.project.document.regions[1].blocks[0].children] == ["Python", "Linux"]
    assert technology_years(restored.project.facts)["linux"] is None
    assert restored.project.sources == original.project.sources


def test_clearing_an_estimated_duration_hides_it_instead_of_restoring_the_estimate():
    from packages.resume_core.rich_fields import set_text
    facts, _ = technology_facts([job("2020-01", "2022-12"), {"kind": "technology", "display": "Python"}])
    assert technology_years(facts)["python"] == 3
    general = next(record for record in facts.records if record.kind == "technology" and record.job_id is None)
    set_text(general, "experience", "")
    assert technology_years(facts)["python"] is None
