"""Keep private resume state and images out of Git, including old blobs."""

from io import BytesIO
import json
from time import monotonic
from zipfile import ZipFile

import pytest

from tools.check_private_resume_data import inspect, private_path


@pytest.mark.parametrize("path", ["experiments/import/result.json", ".private/resume/file.txt",
    "docs/gui/handoffs/IMPORT/editor.png", "docs/gui/handoffs/IMPORT/project.foldcv", "candidate.docx",
    "docs/gui/handoffs/IMPORT/gui-fixture/preview.json"])
def test_private_resume_paths_are_blocked(path):
    assert private_path(path)


@pytest.mark.parametrize("path", ["tests/fixtures/synthetic/import/rich.docx",
    "research_notes/tool/synthetic/test.pdf", "assets/branding/logo.png",
    "docs/gui/handoffs/IMPORT/after/assets/technology-library/python.png"])
def test_synthetic_fixtures_and_logo_assets_remain_allowed(path):
    assert not private_path(path)


def test_workspace_dump_is_blocked_even_after_renaming_or_nested_wire_encoding():
    workspace = {"project": {"sources": [{"units": [{"text": "Candidate"}]}], "facts": {"records": []}}}
    for value in [workspace, {"response": {"workspaceWire": json.dumps(workspace)}}]:
        assert "resume workspace or source dump" in inspect("docs/result.json", json.dumps(value).encode(), {})


def test_schema_definitions_and_explicit_synthetic_contracts_are_allowed():
    assert not inspect("contracts/schema.json", b'{"properties":{"sources":{"type":"array"},"facts":{"type":"object"}}}', {})
    assert not inspect("contracts/examples/fixture.json", b'{"sources":[],"facts":{"records":[]}}', {})


def test_known_private_indicators_are_found_in_unicode_json_and_word_xml_without_printing_values():
    indicators = {"names": ["ТестовыйКандидат"], "emails": ["resume@candidate.invalid"]}
    content = json.dumps({"name": "ТестовыйКандидат", "contact": "resume@candidate.invalid"}).encode()
    assert set(inspect("docs/check.json", content, indicators)) == {"known candidate identity", "known candidate contact"}
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", "<w:t>ТестовыйКандидат</w:t>")
    assert "known candidate identity" in inspect("tests/fixtures/synthetic/resume.docx", stream.getvalue(), indicators)


def test_source_pdf_inside_an_unexpected_archive_is_blocked():
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("sources/input.pdf", b"%PDF-1.7 private source")
    assert "embedded source PDF" in inspect("docs/snapshot.zip", stream.getvalue(), {})


WORKSPACE = {"project": {"sources": [{"units": [{"text": "Candidate"}]}], "facts": {"records": []}}}
RESUME = "Candidate\nprivate-contact@resume.local\nExperience\nEducation\n"


def zipped(members):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)
    return stream.getvalue()


@pytest.mark.parametrize("path", ["docs/backup.foldcv.bak", "docs/gui/handoffs/X/export.bin"])
def test_a_workspace_inside_an_archive_of_any_name_is_blocked(path):
    assert "resume workspace or source dump" in inspect(path, zipped({"workspace.json": json.dumps(WORKSPACE)}), {})


def test_a_source_document_inside_an_archive_of_any_name_is_blocked():
    assert "embedded source document" in inspect("docs/backup.bak", zipped({"sources/cv.docx": "content"}), {})


def test_synthetic_archives_keep_their_workspaces():
    assert not inspect("tests/fixtures/synthetic/archive.zip", zipped({"workspace.json": json.dumps(WORKSPACE)}), {})


def test_workspace_lines_are_blocked_in_any_text_file():
    lines = (json.dumps({"event": "start"}) + "\n" + json.dumps(WORKSPACE) + "\n").encode()
    for path in ["docs/gui/handoffs/X/run.jsonl", "docs/gui/handoffs/X/service.log", "docs/dump"]:
        assert "resume workspace or source dump" in inspect(path, lines, {})


def test_a_workspace_without_sources_is_not_a_source_dump():
    lines = json.dumps({"sources": [], "facts": {"records": []}}).encode()
    assert not inspect("docs/gui/handoffs/X/tools.jsonl", lines, {})


@pytest.mark.parametrize("path", ["docs/gui/handoffs/X/dump.yaml", "docs/preview.html", "docs/export.csv", "docs/notes"])
def test_contact_resume_text_is_blocked_in_any_text_file(path):
    assert "resume text with contact details" in inspect(path, RESUME.encode(), {})


@pytest.mark.parametrize("number", ["+7 (916) 765-43-21", "+44 20 7946 0958", "8 (916) 765-43-21"])
def test_resume_text_with_only_a_phone_number_is_blocked(number):
    text = f"Candidate\n{number}\nExperience\nEducation\n".encode()
    assert "resume text with contact details" in inspect("docs/notes/import.txt", text, {})


@pytest.mark.parametrize("value", ["+7 (999) 123-45-67", "+1 555 0100 1234", "+7 (999) 111", "id 89161234098",
                                   "+@pytest.mark.asyncio"])
def test_sample_numbers_ids_and_diff_decorators_are_not_contacts(value):
    assert not inspect("docs/change.patch", f"Experience\nEducation\n{value}\n".encode(), {})


def test_source_files_keep_their_sample_contacts_but_not_known_identities():
    assert not inspect("docs/check.py", RESUME.encode(), {})
    assert "known candidate contact" in inspect("docs/check.py", RESUME.encode(),
                                                {"emails": ["private-contact@resume.local"]})


@pytest.mark.parametrize("path", ["docs/notes.bin", "docs/page", "docs/scan.txt"])
def test_a_pdf_is_blocked_by_its_content_under_any_name(path):
    assert "source PDF" in inspect(path, b"%PDF-1.7 private source", {})
    assert not inspect("tests/fixtures/synthetic/" + path, b"%PDF-1.7 synthetic source", {})


@pytest.mark.parametrize("path", ["docs/candidate.odt", "docs/originals.tar", "docs/originals.tar.gz", "docs/originals.tgz",
                                  "docs/originals.tar.bz2", "docs/originals.tar.xz", "docs/log.gz", "docs/originals.7z"])
def test_document_and_archive_formats_the_guard_cannot_read_are_blocked(path):
    assert private_path(path)
    assert not private_path("tests/fixtures/synthetic/" + path)


def test_contact_resume_text_is_blocked_without_any_local_candidate_list():
    text = b"Candidate\nprivate-contact@resume.local\nExperience\nEducation\n"
    assert "resume text with contact details" in inspect("notes/import.txt", text, {})
    assert not inspect("tests/fixtures/synthetic/import.txt", text, {})


def test_large_encoded_data_does_not_make_contact_detection_quadratic():
    text = ("Experience Education " + "A" * 200000 + " mail@example.com").encode()
    started = monotonic()
    assert not inspect("docs/check.md", text, {})
    assert monotonic() - started < 3


def test_source_overlays_do_not_treat_decorators_after_escaped_newlines_as_contacts():
    source = json.dumps({"code": "Experience Education\n@pytest.mark.asyncio\nmail@example.com"}).encode()
    assert not inspect("docs/source-overlays.json", source, {})
