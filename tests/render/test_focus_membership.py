"""Focus membership is a reversible document choice, independent of facts."""

from io import BytesIO
from zipfile import ZipFile

from jsonschema import Draft202012Validator
from lxml import etree
import pytest

from packages.resume_core.models.rich_document import ParagraphBlock
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import RichPanelRequest, field_block, panel_mutation
from packages.resume_core.rich_presentation import presentation
from packages.resume_core.rendering.rich_docx import render_rich_docx
from tests.facts.panel_fixtures import edit, job, technology_workspace


def workspace(rows=None):
    return technology_workspace(rows if rows is not None else [
        {"kind": "technology", "display": "Docker", "experience": "6"},
        {"kind": "technology", "display": "Python", "experience": "2"},
        {"kind": "technology", "display": "Linux"}])


def technology(value, name):
    return next(r for r in value.project.facts.records if r.kind == "technology" and r.display.raw_text == name)


def change(value, name, include):
    request = edit(value, operation="add_to_focus" if include else "remove_from_focus", recordId=technology(value, name).id)
    mutation = panel_mutation(value, request)
    return apply_rich_mutation(value, mutation)[0] if mutation else value


def view(value):
    return presentation(value.project.document, value.project.facts)


def test_remove_preserves_facts_evidence_and_other_mentions_and_readd_sorts_without_duplicates():
    original = workspace()
    mention = ParagraphBlock.model_validate(field_block(technology(original, "Docker"), "display"))
    original.project.document.regions[2].blocks.append(mention)
    removed = change(original, "Docker", False)
    assert removed.project.facts == original.project.facts
    assert removed.project.sources == original.project.sources
    assert removed.project.evidence_records == original.project.evidence_records
    assert removed.project.document.regions[2] == original.project.document.regions[2]
    assert [e.display for e in view(removed).focus_entries] == ["Python", "Linux"]
    assert [e.display for e in view(removed).focus_options] == ["Docker"]
    added = change(removed, "Docker", True)
    assert [(e.display, e.years) for e in view(added).focus_entries] == [("Docker", 6), ("Python", 2), ("Linux", None)]
    assert added.project.facts == original.project.facts
    assert change(added, "Docker", True) is added
    assert change(removed, "Docker", False) is removed


def test_remove_last_hides_heading_and_restore_survives_reload_and_docx():
    original = workspace([{"kind": "technology", "display": "Python", "experience": "2"}])
    removed = change(original, "Python", False)
    assert removed.project.document.regions[1].blocks == []
    assert [e.display for e in view(removed).focus_options] == ["Python"]
    transferred = WorkspaceV6.model_validate_json(removed.model_dump_json(by_alias=True))
    assert not view(transferred).focus_entries
    restored = change(transferred, "Python", True)
    assert len(restored.project.document.regions[1].blocks) == 1
    assert [e.display for e in view(restored).focus_entries] == ["Python"]
    assert restored.project.facts == original.project.facts
    for value, expected in [(removed, False), (restored, True)]:
        with ZipFile(BytesIO(render_rich_docx(value.project.document, facts=value.project.facts))) as archive:
            xml = etree.fromstring(archive.read("word/document.xml"))
        text = xml.xpath("//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"})
        assert ("ФОКУС" in text) == expected
        assert ("Python" in text) == expected


def test_aliases_share_membership_and_options_prefer_the_general_fact():
    original = workspace([job("2020-01", "2022-12", "Postgres"),
        {"kind": "technology", "display": "PostgreSQL"}])
    assert len(view(original).focus_entries) == 1
    removed = change(original, "Postgres", False)
    assert not view(removed).focus_entries
    assert [(e.record_id, e.display) for e in view(removed).focus_options] == [(technology(original, "PostgreSQL").id, "PostgreSQL")]
    restored = change(removed, "PostgreSQL", True)
    assert change(restored, "Postgres", True) is restored
    assert restored.project.facts == original.project.facts


def test_a_renamed_focus_label_stays_removable_without_creating_a_duplicate_option():
    original = workspace([{"kind": "technology", "display": "Python"}])
    original.project.document.regions[1].blocks[0].children[0].content[0].text = "Python (primary)"
    assert [e.display for e in view(original).focus_entries] == ["Python"]
    assert not view(original).focus_options
    assert not view(change(original, "Python", False)).focus_entries


def test_unknown_and_nontechnical_tools_are_not_offered_and_stale_commands_cannot_write():
    original = workspace([{"kind": "technology", "display": "NoIconTool", "technical": True},
        {"kind": "technology", "display": "Python", "technical": False}])
    assert not view(original).focus_options
    for name in ["NoIconTool", "Python"]:
        with pytest.raises(ValueError, match="FOCUS_TECHNOLOGY_INVALID"):
            change(original, name, True)
    with pytest.raises(ValueError, match="FOCUS_TECHNOLOGY_INVALID"):
        panel_mutation(original, edit(original, operation="add_to_focus", recordId="missing"))
    original = workspace()
    stale = edit(original, operation="remove_from_focus", recordId=technology(original, "Docker").id)
    changed = change(original, "Python", False)
    with pytest.raises(ValueError, match="STALE_PANEL_EDIT"):
        panel_mutation(changed, stale)
    assert [e.display for e in view(changed).focus_entries] == ["Docker", "Linux"]


@pytest.mark.parametrize("values", [{"recordId": None}, {"recordKind": "candidate"}, {"jobId": "job"},
    {"periodId": "period"}, {"values": {"display": "Other"}}])
def test_focus_command_rejects_fact_edits_and_ambiguous_scope(values):
    original = workspace()
    payload = edit(original, operation="add_to_focus", recordId=technology(original, "Docker").id).model_dump(by_alias=True)
    validator = Draft202012Validator(RichPanelRequest.model_json_schema())
    assert validator.is_valid(payload)
    assert not validator.is_valid({**payload, **values})
    with pytest.raises(ValueError, match="FOCUS_SCOPE_INVALID"):
        edit(original, **{"operation": "add_to_focus", "recordId": technology(original, "Docker").id, **values})
