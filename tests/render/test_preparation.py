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

from packages.resume_core.rendering.preparation import PrepareRequest, prepare_document
from packages.resume_core.rendering.template import PACKAGE_SHA256

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


def test_hidden_profile_and_job_are_omitted_but_skills_and_education_remain():
    data = example()
    data["project"]["views"][0]["visible"] = False
    data["project"]["views"][1]["visible"] = False
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert prepared.document.candidate.summary == ""
    assert [item.company for item in prepared.document.projects] == ["Example Two"]
    assert prepared.document.skill_groups[0].items == "Python"
    assert prepared.document.sidebar[-1].items == ["Technical Institute, 2018"]


def test_old_job_uses_policy_row_and_preserves_accepted_prose():
    data = example()
    data["project"]["employment"].append({"id": "old-job", "employer": "Earlier Company", "role": "Developer",
        "periods": [{"start": {"precision": "year", "year": 2001, "month": None, "day": None},
                     "end": {"precision": "year", "year": 2005, "month": None, "day": None}}],
        "subprojects": [], "factIds": []})
    block = deepcopy(data["project"]["views"][1])
    block["id"] = "old-prose"
    block["state"].update(text="Maintained service integrations.", factIds=[], factRevisions={})
    data["project"]["views"].append(block)
    data["presentation"]["jobProseBlocks"]["old-job"] = "old-prose"
    prepared = prepare_document(PrepareRequest.model_validate(data))
    assert "Earlier Company" not in [item.company for item in prepared.document.projects]
    assert any("Maintained service integrations." in item for section in prepared.document.sidebar for item in section.items)


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
    with zipfile.ZipFile(io.BytesIO(docx)) as editable:
        assert b"Synthetic edited summary." in editable.read("word/document.xml")
    assert list((tmp_path / "operations").iterdir()) == []
