"""Synthetic editor preparation keeps explicit bindings and policy output."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import io
import hashlib
import sys
import zipfile

import pytest
from pydantic import ValidationError
import pymupdf

from packages.resume_core.rendering.preparation import PreparationFailure, PrepareRequest, prepare_document
from packages.resume_core.rendering.template import PACKAGE_SHA256, RenderFailure

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api/src"))
from resume_api.lifecycle import OperationFiles
from resume_api.rendering import DocumentRenderer


def example() -> dict:
    project = json.loads((ROOT / "contracts/examples/project.json").read_text(encoding="utf-8"))
    project["template"].update(version="1.0.0", packageSha256=PACKAGE_SHA256, assets=[])
    project["renders"] = []
    profile = project["views"][0]
    for block_id, text, fact_ids in (("work-one", "Built a team from zero to five.", ["fact_metric"]),
                                     ("work-two", "Mentored developers.", ["fact_user"])):
        block = deepcopy(profile)
        block.update(id=block_id, kind="job_prose", revision=1, previous=None, status="ready")
        block["state"].update(text=text, factIds=fact_ids,
                              factRevisions={fact_id: 2 if fact_id == "fact_metric" else 1 for fact_id in fact_ids})
        project["views"].append(block)
    education = deepcopy(profile)
    education.update(id="education", kind="education", revision=1, previous=None, status="ready")
    education["state"].update(text="Technical Institute, 2018", factIds=[], factRevisions={})
    project["views"].append(education)
    return {"project": project, "presentation": {"name": "Synthetic Person", "title": "Engineer",
            "sourceLanguage": "en", "jobProseBlocks": {"job_1": "work-one", "job_2": "work-two"}}}


def test_preparation_maps_every_job_and_education_without_translation():
    payload = PrepareRequest.model_validate(example())
    request = prepare_document(payload)
    assert request.document.candidate.name == "Synthetic Person"
    assert [item.company for item in request.document.projects] == ["Example One", "Example Two"]
    assert [item.description for item in request.document.projects] == ["Built a team from zero to five.", "Mentored developers."]
    assert request.document.projects[1].period.endswith("present")
    assert request.document.sidebar[-1].items == ["Technical Institute, 2018"]
    assert request.document.skill_groups[0].items == "Python"
    assert request.document.focus == []  # A global-only technology has no dated focus.
    assert request.snapshot.project_revision == payload.project.revision


def test_dated_technology_selects_available_icon_and_duration():
    data = example()
    technology = deepcopy(data["project"]["facts"][1])
    technology.update(id="job-tech", jobId="job_1")
    technology["value"]["scope"] = "job"
    data["project"]["facts"].append(technology)
    data["project"]["employment"][0]["factIds"].append("job-tech")
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert [(item.label, item.icon) for item in prepared.document.focus] == [("Python", "python")]
    assert prepared.document.focus[0].duration


@pytest.mark.parametrize(("language", "label"), [("en", "Dates not specified"), ("ru", "Даты не указаны")])
def test_job_without_dates_still_prepares_for_export(language, label):
    data = example()
    data["presentation"]["sourceLanguage"] = language
    data["project"]["employment"][0]["periods"] = []
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert prepared.document.projects[0].period == label
    assert prepared.document.source_language == language


@pytest.mark.parametrize(("index", "length", "code"), [
    (1, 4001, "JOB_DESCRIPTION_TOO_LONG"), (0, 12001, "PROFILE_TOO_LONG"),
    (-1, 4001, "EDUCATION_TOO_LONG"),
])
def test_visible_text_limit_reports_field_before_document_validation(index, length, code):
    data = example()
    data["project"]["views"][index]["state"]["text"] = "x" * length
    original = deepcopy(data)
    with pytest.raises(PreparationFailure, match=code):
        prepare_document(PrepareRequest.model_validate(data))
    assert data == original
    data["project"]["views"][index]["state"]["text"] = "x" * (length - 1)
    prepare_document(PrepareRequest.model_validate(data))
    data["project"]["views"][index]["visible"] = False
    data["project"]["views"][index]["state"]["text"] = "x" * length
    prepare_document(PrepareRequest.model_validate(data))


@pytest.mark.parametrize(("language", "start", "end", "precision", "duration"), [
    ("en", 2020, 2024, "year", "≈ 3 years"),
    ("ru", 2020, 2020, "month", "≈ 1 год"),
    ("ru", 2020, 2021, "month", "≈ 2 года"),
    ("ru", 2020, 2024, "month", "≈ 5 лет"),
    ("en", 2020, 2020, "month", "≈ 1 year"),
])
def test_focus_uses_conservative_duration_and_language_grammar(language, start, end, precision, duration):
    data = example()
    data["presentation"]["sourceLanguage"] = language
    data["project"]["employment"][0]["periods"] = [{
        "start": {"precision": precision, "year": start, "month": 1 if precision == "month" else None, "day": None},
        "end": {"precision": precision, "year": end, "month": 12 if precision == "month" else None, "day": None}}]
    for subproject in data["project"]["employment"][0]["subprojects"]:
        subproject["period"] = deepcopy(data["project"]["employment"][0]["periods"][0])
    technology = deepcopy(data["project"]["facts"][1])
    technology.update(id="job-tech", jobId="job_1")
    technology["value"]["scope"] = "job"
    data["project"]["facts"].append(technology)
    data["project"]["employment"][0]["factIds"].append("job-tech")
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert prepared.document.focus[0].duration == duration
    assert prepared.document.sidebar[-1].title == ("ОБРАЗОВАНИЕ" if language == "ru" else "EDUCATION")


def test_hidden_profile_and_job_are_omitted_but_skills_and_education_remain():
    data = example()
    data["project"]["views"][0]["visible"] = False
    data["project"]["views"][1]["visible"] = False
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert prepared.document.candidate.summary == ""
    assert [item.company for item in prepared.document.projects] == ["Example Two"]
    assert prepared.document.skill_groups[0].items == "Python"
    assert prepared.document.sidebar[-1].items == ["Technical Institute, 2018"]


def test_old_job_uses_compact_policy_row_and_keeps_detail_only_in_project():
    data = example()
    data["project"]["employment"].append({"id": "old-job", "employer": "Earlier Company", "role": "Developer",
        "periods": [{"start": {"precision": "year", "year": 2001, "month": None, "day": None},
                     "end": {"precision": "year", "year": 2005, "month": None, "day": None}}],
        "subprojects": [], "factIds": []})
    block = deepcopy(data["project"]["views"][1])
    block["id"] = "old-prose"
    block["visible"] = False
    block["state"].update(text="Maintained service integrations.", factIds=[], factRevisions={})
    data["project"]["views"].append(block)
    data["presentation"]["jobProseBlocks"]["old-job"] = "old-prose"
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert "Earlier Company" not in [item.company for item in prepared.document.projects]
    row = next(section for section in prepared.document.sidebar if section.title == "EARLY CAREER")
    assert row.items == ["Earlier Company — Developer (2001–2005)"]
    assert "Maintained service integrations." not in row.items[0]
    assert data["project"]["views"][-1]["state"]["text"] == "Maintained service integrations."
    early = deepcopy(block)
    early.update(id="early-career", kind="early_career", visible=False)
    early["state"].update(text="", factIds=[], factRevisions={})
    data["project"]["views"].append(early)
    hidden = prepare_document(PrepareRequest.model_validate(data))
    assert all(section.title != "EARLY CAREER" for section in hidden.document.sidebar)


@pytest.mark.parametrize(("field", "value", "section"), [
    ("job_prose", "Built a tool. Call 555-123-4567.", "JOB"),
    ("profile", "Reach me at example@example.com", "PROFILE"),
    ("profile", "Portfolio: alice.dev", "PROFILE"),
    ("profile", "Website: alice.com", "PROFILE"),
    ("profile", "LinkedIn: linkedin.com", "PROFILE"),
    ("identity", "https://example.com/profile", "IDENTITY"),
    ("employer", "Example Works. Phone: (555) 123-4567", "JOB"),
    ("role", "Engineer. Age: 29", "JOB"),
    ("education", "Technical Institute. Resume ID: 12345", "SIDEBAR"),
    ("language", "Job board: hh.ru", "SIDEBAR"),
    ("skill", "Python, contact@example.com", "SKILLS"),
])
def test_preparation_preserves_visible_candidate_content_without_changing_input(field, value, section):
    data = example()
    if field == "job_prose":
        data["project"]["views"][1]["state"]["text"] = value
    elif field == "profile":
        data["project"]["views"][0]["state"]["text"] = value
    elif field == "identity":
        data["presentation"]["name"] = value
    elif field == "employer":
        data["project"]["employment"][0]["employer"] = value
    elif field == "role":
        data["project"]["employment"][0]["role"] = value
    elif field == "education":
        data["project"]["views"][-1]["state"]["text"] = value
    elif field == "language":
        data["presentation"]["languages"] = [value]
    else:
        data["project"]["facts"][1]["value"]["display"] = value
    original = deepcopy(data)
    result = prepare_document(PrepareRequest.model_validate(data))
    assert value in result.document.model_dump_json()
    assert data == original


def test_hidden_source_private_values_do_not_block_safe_visible_document():
    data = example()
    data["project"]["sources"][0]["units"][0]["text"] = "Call 555-123-4567 for references."
    data["project"]["views"][1]["visible"] = False
    data["project"]["views"][1]["state"]["text"] = "Call 555-123-4567 for references."
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert all("555" not in item.description for item in prepared.document.projects)


def test_visible_legacy_contact_block_is_editable_render_content_and_hidden_choice_is_kept():
    data = example()
    contact = deepcopy(data['project']['views'][0])
    contact.update(id='contact-details', kind='contact')
    contact['state'].update(text='Email: contact@example.invalid\nAge: 42', factIds=[], factRevisions={})
    data['project']['views'].append(contact)
    rendered = prepare_document(PrepareRequest.model_validate(data))
    assert any(section.items == ['Email: contact@example.invalid\nAge: 42'] for section in rendered.document.sidebar)
    contact['visible'] = False
    hidden = prepare_document(PrepareRequest.model_validate(data))
    assert 'contact@example.invalid' not in hidden.document.model_dump_json()


def test_safe_metrics_and_dates_remain_renderable():
    data = example()
    data["project"]["views"][0]["state"]["text"] = "Engineer with 12 years of experience."
    data["project"]["employment"][0]["employer"] = "HeadHunter"
    data["project"]["views"][1]["state"]["text"] = "Built hh.ru integrations for 5000 jobs in 2022-2025; grew by +20 000 users."
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert "5000 jobs" in prepared.document.projects[0].description
    assert prepared.document.projects[0].company == "HeadHunter"


@pytest.mark.parametrize("change", ["missing_binding", "extra_prose", "second_profile", "wrong_template", "stale_prose"])
def test_preparation_rejects_ambiguous_or_stale_mapping(change):
    data = example()
    if change == "missing_binding":
        del data["presentation"]["jobProseBlocks"]["job_2"]
    elif change == "extra_prose":
        extra = deepcopy(data["project"]["views"][1])
        extra["id"] = "unmapped"
        data["project"]["views"].append(extra)
    elif change == "second_profile":
        extra = deepcopy(data["project"]["views"][0])
        extra["id"] = "profile-two"
        data["project"]["views"].append(extra)
    elif change == "wrong_template":
        data["project"]["template"]["packageSha256"] = "c" * 64
    else:
        data["project"]["views"][1]["status"] = "stale"
    with pytest.raises((ValidationError, ValueError)):
        prepare_document(PrepareRequest.model_validate(data))


@pytest.mark.slow
@pytest.mark.asyncio
async def test_prepared_snapshot_converts_to_matching_pdf_and_editable_docx(tmp_path):
    data = example()
    data["project"]["views"][0]["state"]["text"] = "Synthetic edited summary."
    request = prepare_document(PrepareRequest.model_validate(data))
    files = OperationFiles(tmp_path / "operations")
    with files.open():
        archive = await DocumentRenderer().render(request, files)
    with zipfile.ZipFile(io.BytesIO(archive)) as document:
        assert document.namelist() == ["resume.docx", "resume.pdf", "render.json"]
        docx = document.read("resume.docx")
        pdf = document.read("resume.pdf")
        metadata = json.loads(document.read("render.json"))
    assert metadata["snapshotSha256"] == request.snapshot.snapshot_sha256
    assert metadata["pdfSha256"] == hashlib.sha256(pdf).hexdigest()
    assert metadata["docxSha256"] == hashlib.sha256(docx).hexdigest()
    with pymupdf.open(stream=pdf, filetype="pdf") as rendered_pdf:
        text = " ".join(page.get_text() for page in rendered_pdf)
    assert "Synthetic edited summary." in text
    assert "Built a team from zero to five." in text
    assert "Technical Institute, 2018" in text
    assert all(label in text for label in ("ABOUT ME", "PROJECTS", "Role:", "EDUCATION"))
    with zipfile.ZipFile(io.BytesIO(docx)) as editable:
        assert b"Synthetic edited summary." in editable.read("word/document.xml")
    assert list((tmp_path / "operations").iterdir()) == []
