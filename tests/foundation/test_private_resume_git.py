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
