"""Literal first-run text, conservative bindings and preserved source ownership."""

from types import SimpleNamespace

from packages.resume_core.rich_import import assemble_import, literal_content
from packages.resume_core.rich_presentation import authored_text
from tests.recovery.draft_fixtures import draft_request


def test_original_units_keep_order_blank_lines_contacts_and_unsupported_text():
    normalized = draft_request().normalized
    source = normalized.sources[0]
    texts = ["  Original wording.\n", "\n", "Phone: +1 555 0100\n", "Unknown detail: preserve exactly.  "]
    units = [source.units[0].model_copy(update={"id": f"literal-{index}", "order": index, "text": text}, deep=True)
        for index, text in enumerate(texts)]
    source.units = list(reversed(units))
    workspace = SimpleNamespace(project_id="literal-import", project_revision=1, document_revision=1,
        created_at="2026-10-15T00:00:00Z", pre_draft=SimpleNamespace(operations=[]))
    before = normalized.model_dump(by_alias=True)
    project = assemble_import(workspace, normalized)
    assert [authored_text(block) for block in project.document.regions[2].blocks] == texts
    assert not project.document.regions[0].blocks and not project.document.regions[1].blocks
    assert [block.provenance[0].evidence[0].unit_id for block in project.document.regions[2].blocks] == [unit.id for unit in units]
    assert normalized.model_dump(by_alias=True) == before
    assert project.sources == normalized.sources
    assert any(record.kind == "employment" for record in project.facts.records)


def record(identifier, text, unit="unit", key="employer"):
    return {"id": identifier, key: {"value": text, "rawText": text}, "evidence": [
        {"sourceId": "source", "unitId": unit, "text": text}]}


def test_exact_bindings_require_unambiguous_source_occurrence_and_do_not_rewrite_literals():
    text = "Company A — Engineer; Python / Python. C++"
    records = [record("job-a", "Company A"), record("job-b", "Engineer", "other"),
        record("tech", "Python", key="display"), record("cpp", "C++", key="display")]
    content = literal_content(text, SimpleNamespace(id="source"), SimpleNamespace(id="unit"), records)
    assert "".join(span["text"] for span in content) == text
    assert [(span["recordId"], span["fieldKey"]) for span in content if span["type"] == "fact_field"] == [
        ("job-a", "employer"), ("cpp", "display")]


def test_competing_fields_and_substrings_stay_literal_without_wrong_fact_links():
    for text, records in [
        ("Company A", [record("a", "Company A"), record("b", "Company A")]),
        ("Senior Engineer", [record("a", "Senior Engineer"), record("b", "Engineer")]),
        ("JavaScript", [record("java", "Java")]),
    ]:
        content = literal_content(text, SimpleNamespace(id="source"), SimpleNamespace(id="unit"), records)
        assert content == [{"type": "text", "text": text, "styles": {}}]


def test_original_date_endpoints_keep_period_ownership_without_binding_other_jobs():
    job = record("job-a", "Company A")
    job["evidence"][0]["text"] = "Company A 2020–2022"
    job["periods"] = [{"id": "p", "start": {"rawText": "2020"}, "end": {"rawText": "2022"},
        "present": {"value": False, "rawText": ""}}]
    content = literal_content("Company A 2020–2022", SimpleNamespace(id="source"), SimpleNamespace(id="unit"), [job])
    assert [(span["recordId"], span["fieldKey"], span["text"]) for span in content if span["type"] == "fact_field"] == [
        ("job-a", "employer", "Company A"), ("job-a", "period:p:start", "2020"), ("job-a", "period:p:end", "2022")]
