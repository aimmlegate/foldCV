"""Real DOCX mapping, line breaks and every safe writer/schema error family."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from lxml import etree
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_rendering import render_input
from packages.resume_core.gui_derived import initial_derived
from packages.resume_core.models.recovery import FieldAnchor
from packages.resume_core.rendering.docx_errors import DocxFailure, validate_document, writer_failure
from packages.resume_core.rendering.template import RenderFailure, require_docx_template, require_template, renderer_sha256
from packages.resume_core.rendering.worker import render_docx_only
from tests.recovery.generation_fixtures import render_workspace

W = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def write(workspace, directory):
    document, anchors, fingerprint = render_input(workspace)
    directory.mkdir(exist_ok=True)
    (directory / "docx-input.json").write_text(json.dumps({"document": document.model_dump(mode="json", by_alias=True),
        "anchors": {path: anchor.model_dump(by_alias=True) for path, anchor in anchors.items()}, "rendererSha256": renderer_sha256()}))
    render_docx_only(directory)
    with ZipFile(directory / "resume.docx") as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
    return document, xml, fingerprint


def test_docx_without_converter_or_font_copies_keeps_actual_multiline_breaks(tmp_path, monkeypatch):
    from packages.resume_core.rendering import template, worker
    monkeypatch.setattr(template, "SOFFICE", tmp_path / "missing-converter")
    monkeypatch.setattr(template, "APP_FONTS", tmp_path / "missing-font-copies")
    monkeypatch.setattr(worker, "_convert", lambda *_args: pytest.fail("converter invoked"))
    assert require_docx_template()["id"] == "generic"
    with pytest.raises(RenderFailure, match="CONVERTER_UNAVAILABLE"):
        require_template()
    workspace = render_workspace()
    document = workspace.project.document
    document.education[0].institution.text = "University\n\nFaculty"
    from packages.resume_core.models.recovery import CertificationRecord
    def field(key):
        return {"fieldId": "certification:certificate/" + key, "text": "", "factIds": [], "evidence": [], "origin": "user"}
    row = CertificationRecord.model_validate({"id": "certificate", "kind": "certification", "revision": 1,
        "visible": True, "name": field("name"), "issuer": field("issuer"), "dateText": field("dateText"), "legacyText": None})
    row.name.text, row.issuer.text, row.date_text.text = "Certificate\n\nCourse", "Institute", "2020"
    document.certifications.append(row)
    workspace.undo_slots["certification:" + row.id] = None
    document.skills_focus.skills_text.text = "Docker\n\nKubernetes"
    document.early_career.text.text = "Early\n\nCareer"
    document.jobs[0].tasks.text = "Task one\n\nTask two"
    rendered, xml, _ = write(workspace, tmp_path / "render")
    assert rendered.projects[0].tasks == ["Task one", "Task two"]
    for expected in ["University\n\nFaculty", "Certificate\n\nCourse", "Docker\n\nKubernetes", "Early\n\nCareer"]:
        paragraphs = xml.findall(".//w:p", W)
        matching = [p for p in paragraphs if expected.replace("\n", "") in "".join(p.itertext())]
        assert matching and any(len(p.findall(".//w:br", W)) >= 2 for p in matching)
    assert rendered.footer == "" and rendered.achievements == []
    assert not (tmp_path / "render/resume.pdf").exists()


def test_fallback_role_date_precision_visibility_and_language_mapping(tmp_path):
    workspace = render_workspace("E2")
    doc = workspace.project.document
    doc.candidate.name.text = doc.candidate.title.text = ""
    doc.jobs[0].role.text = doc.jobs[0].employer.text = ""
    doc.profile.visible = False
    doc.skills_focus.visible = False
    rendered, xml, _ = write(workspace, tmp_path / "render")
    assert rendered.source_language == "mixed" and rendered.candidate.summary == ""
    assert rendered.candidate.name == "Name not specified" and rendered.candidate.title == "Title not specified"
    assert rendered.projects[0].company == "Company not specified"
    assert rendered.projects[0].role == "not specified" and rendered.projects[0].period == "Dates not specified"
    assert rendered.focus == rendered.skill_groups == []
    text = " ".join(xml.itertext())
    assert "Role: not specified" in text and "Role: Role:" not in text
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    job.periods[0].start_text.text = "2017-03"
    job.periods[0].end_text.text, job.periods[0].present = "2020-02", False
    rendered, _, _ = render_input(workspace)
    assert rendered.projects[0].period == "2017-03–2020-02"
    job.periods[0].end_text.text = "unknown"
    assert render_input(workspace)[0].projects[0].period == "2017-03–unknown"
    job.periods[0].end_text.text = ""
    assert render_input(workspace)[0].projects[0].period == "2017-03–?"
    job.periods[0].end_text.text = "  "
    assert render_input(workspace)[0].projects[0].period == "2017-03–?"
    job.periods[0].present = True
    assert render_input(workspace)[0].projects[0].period == "2017-03–н. в."


def test_closed_subtotals_remain_but_open_without_observation_has_no_badge():
    workspace = render_workspace()
    # Use one explicit synthetic technology association spanning closed and open jobs.
    from packages.resume_core.models.recovery import GuiTechnologyFact
    python = next(fact for fact in workspace.project.facts if isinstance(fact, GuiTechnologyFact) and fact.value.canonical_id == "python")
    closed = python.model_copy(deep=True)
    closed.id, closed.job_id = "closed-python", workspace.project.employment[1].id
    workspace.project.facts.append(closed)
    workspace.project.document.skills_focus.focus[0].fact_ids.append(closed.id)
    workspace.derived_state = initial_derived(workspace.project.document, workspace.project.facts,
        workspace.project.employment, None, 2, "ru")
    value = workspace.derived_state.values[-1]
    assert value.months_min is not None and value.months_max is not None
    assert value.complete_exposure is False and value.display is None
    assert render_input(workspace)[0].focus[0].duration == ""
    from packages.resume_core.dates import partial_date
    workspace.derived_state = initial_derived(workspace.project.document, workspace.project.facts,
        workspace.project.employment, partial_date("2025-10"), 2, "ru")
    value = workspace.derived_state.values[-1]
    assert value.complete_exposure and value.display.startswith("≈ ")
    assert render_input(workspace)[0].focus[0].duration == value.display


STRING_LIMITS = [
    ("candidate.name", 160), ("candidate.title", 240), ("candidate.summary", 12000),
    ("projects[0].company", 200), ("projects[0].role", 300), ("projects[0].period", 100),
    ("projects[0].stack", 1000), ("projects[0].description", 4000),
    ("focus[0].label", 100), ("focus[0].duration", 100), ("focus[0].icon", 60),
    ("sidebar[0].title", 100), ("sidebar[0].items[0]", 4000), ("projects[0].tasks[0]", 4000),
    ("projects[0].results[0]", 4000), ("achievements[0]", 4000),
    ("skillGroups[0].title", 100), ("skillGroups[0].items", 4000), ("footer", 200)]
LIST_LIMITS = [("focus", 8), ("sidebar", 40), ("projects", 60), ("achievements", 100), ("skillGroups", 40),
               ("sidebar[0].items", 100), ("projects[0].tasks", 100), ("projects[0].results", 100)]


def replace(data, path, value):
    import re
    keys = re.findall(r"[A-Za-z]+|\d+", path)
    current = data
    for key in keys[:-1]:
        current = current[int(key)] if key.isdigit() else current[key]
    key = keys[-1]
    current[int(key) if key.isdigit() else key] = value


@pytest.mark.parametrize("path,limit", STRING_LIMITS)
def test_all_string_limit_paths_are_safe_and_field_mapped(path, limit):
    rendered, anchors, _ = render_input(render_workspace())
    data = rendered.model_dump(mode="json", by_alias=True)
    data["achievements"] = ["a"]
    replace(data, path, "x" * (limit + 1))
    anchor = FieldAnchor(kind="field", fieldId="safe/field", range=None)
    anchors[path] = anchor
    with pytest.raises(DocxFailure) as caught:
        validate_document(data, anchors)
    error = caught.value.error
    assert error.code == "DOCX_TEXT_LIMIT" and error.path == path and error.anchor == anchor
    assert "xxxx" not in error.model_dump_json()


@pytest.mark.parametrize("path,limit", LIST_LIMITS)
def test_all_list_limit_paths_are_retained(path, limit):
    rendered, _, _ = render_input(render_workspace())
    data = rendered.model_dump(mode="json", by_alias=True)
    data["achievements"] = ["a"]
    import re
    current = data
    for key in re.findall(r"[A-Za-z]+|\d+", path):
        current = current[int(key)] if key.isdigit() else current[key]
    replace(data, path, [deepcopy(current[0]) for _ in range(limit + 1)])
    with pytest.raises(DocxFailure) as caught:
        validate_document(data)
    assert caught.value.error.code == "DOCX_LIST_LIMIT" and caught.value.error.path == path


@pytest.mark.parametrize("change,code,path", [("control", "DOCX_INVALID_CHARACTER", "projects[0].description"),
    ("total", "DOCX_TOTAL_TEXT_LIMIT", None), ("unknown", "DOCX_INVALID_RENDER_INPUT", None),
    ("missing", "DOCX_INVALID_RENDER_INPUT", "candidate.name")])
def test_aggregate_and_unknown_schema_errors_never_echo_values(change, code, path):
    data = render_input(render_workspace())[0].model_dump(mode="json", by_alias=True)
    if change == "control": data["projects"][0]["description"] = "private\x01marker"
    elif change == "total": data["sidebar"][0]["items"] = ["x" * 4000] * 26
    elif change == "unknown": data["private-marker"] = "candidate-content"
    else: del data["candidate"]["name"]
    with pytest.raises(DocxFailure) as caught:
        validate_document(data)
    error = caught.value.error
    assert error.code == code and error.path == path
    assert "private" not in error.model_dump_json() and "candidate-content" not in error.model_dump_json()


@pytest.mark.parametrize("message,code,path", [
    ("Candidate display name exceeds one header line", "DOCX_NAME_LINE_LIMIT", "candidate.name"),
    ("Candidate title exceeds two header lines", "DOCX_TITLE_LINE_LIMIT", "candidate.title"),
    ("Unbreakable text exceeds the column width", "DOCX_UNBREAKABLE_TEXT", None),
    ("One resume block exceeds the page budget", "DOCX_BLOCK_PAGE_BUDGET", None),
    ("Resume block cannot fit on its planned page", "DOCX_BLOCK_PLANNED_PAGE", None),
    ("Unknown focus icon: private-marker", "DOCX_UNKNOWN_FOCUS_ICON", None),
    ("private failure", "DOCX_RENDER_FAILED", None)])
def test_each_known_writer_reason_maps_without_raw_exception(message, code, path):
    error = writer_failure(ValueError(message)).error
    assert error.code == code and error.path == path
    assert "private" not in error.model_dump_json()


def test_real_worker_header_and_unknown_icon_errors_preserve_identity(tmp_path):
    workspace = render_workspace()
    workspace.project.document.candidate.name.text = "Wide name " * 15
    write(workspace, tmp_path / "name")
    rendered, anchors, _ = render_input(render_workspace())
    data = rendered.model_dump(mode="json", by_alias=True)
    data["focus"][0]["icon"] = "missing"
    (tmp_path / "docx-input.json").write_text(json.dumps({"document": data, "anchors": {p: a.model_dump(by_alias=True) for p, a in anchors.items()}, "rendererSha256": renderer_sha256()}))
    with pytest.raises(DocxFailure) as caught:
        render_docx_only(tmp_path)
    assert caught.value.error.code == "DOCX_UNKNOWN_FOCUS_ICON" and caught.value.error.path == "focus[0].icon"


@pytest.mark.asyncio
async def test_gui_renderer_preserves_contact_text_in_actual_docx(tmp_path):
    from resume_api.gui_rendering import GuiDocxRenderer
    from resume_api.lifecycle import OperationFiles
    workspace = render_workspace()
    workspace.project.document.profile.text.text = "Contact fictional@example.invalid"
    rendered, anchors, _ = render_input(workspace)
    from io import BytesIO
    from zipfile import ZipFile
    with OperationFiles(tmp_path).open() as files:
        result = await GuiDocxRenderer().render(rendered, anchors, files)
    with ZipFile(BytesIO(result)) as archive:
        assert b"fictional@example.invalid" in archive.read("word/document.xml")


def test_unclassified_writer_failure_uses_typed_docx_error(tmp_path, monkeypatch):
    from packages.resume_core.rendering import worker
    def broken(*_args):
        raise RuntimeError("private writer failure")
    monkeypatch.setattr(worker.layout, "render_docx", broken)
    with pytest.raises(DocxFailure) as caught:
        write(render_workspace(), tmp_path)
    assert caught.value.error.code == "DOCX_RENDER_FAILED"
    assert caught.value.error.anchor.kind == "document" and "private" not in caught.value.error.model_dump_json()


def test_long_name_email_url_and_unbroken_tokens_wrap_without_character_loss(tmp_path):
    from packages.resume_core.models.recovery import AuthoredField
    workspace = render_workspace()
    name = "Александрович" * 9
    email = "long" * 35 + "@example.invalid"
    url = "https://example.invalid/" + "path" * 70 + "?exact=1&case=Mixed"
    token = "token" * 100
    workspace.project.document.candidate.name.text = name
    workspace.project.document.candidate.details = [AuthoredField(fieldId="detail/" + str(i), text=text,
        factIds=[], evidence=[], origin="user") for i, text in enumerate((email, url, token))]
    _, xml, _ = write(workspace, tmp_path / "long")
    text = "".join(xml.xpath(".//w:t/text()", namespaces=W))
    for value in (name, email, url, token):
        assert value in text
    with ZipFile(tmp_path / "long/resume.docx") as archive:
        styles = etree.fromstring(archive.read("word/styles.xml"))
    assert styles.xpath(".//w:style[@w:styleId='Normal']/w:pPr/w:wordWrap[@w:val='off']", namespaces=W)
