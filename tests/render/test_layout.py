"""Page layout of the DOCX renderer (rendering.layout) regressions from the October 19 review."""

from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from packages.resume_core.extraction import parser
from packages.resume_core.rendering.layout import _append_with_budget, render_docx


@pytest.mark.parametrize("height", [616, 660, 705])
def test_first_block_can_use_continuation_page_budget(height):
    pages = [[]]
    _append_with_budget(pages, "large block", height)
    assert pages == [[], [("large block", height)]]


def test_large_first_summary_creates_docx_with_every_source_line(tmp_path):
    lines = [f"Retained summary line {number}" for number in range(53)]
    target = tmp_path / "resume.docx"
    render_docx({"source_language": "en", "candidate": {"name": "Candidate", "title": "Engineer",
        "summary": "\n".join(lines)}}, target)
    with ZipFile(target) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    text = "\n".join(node.text or "" for node in document.iter(parser.W + "t"))
    assert all(line in text for line in lines)
    assert any(node.get(parser.W + "type") == "page" for node in document.iter(parser.W + "br"))
