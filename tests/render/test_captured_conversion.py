"""The captured DOCX export converts through the pinned LibreOffice, and the pages carry its text."""

import pymupdf
import pytest

from packages.resume_core.rendering.captured_docx import render_captured_docx
from tests.support.convert import ConverterUnavailable, convert, normalize, require_converter, words_in_order
from tests.templates.test_captured_docx import captured_request, emitted, xml

pytestmark = pytest.mark.slow
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def test_the_captured_export_converts_and_keeps_every_paragraph(captured_request, tmp_path):
    try:
        require_converter()
    except ConverterUnavailable as error:
        pytest.fail(str(error))
    content = render_captured_docx(captured_request, tmp_path)
    docx = tmp_path / 'resume.docx'
    docx.write_bytes(content)
    with pymupdf.open(convert(docx, tmp_path)) as pdf:
        assert 0 < len(pdf) <= 30
        text = normalize(' '.join(page.get_text() for page in pdf))
    lines = [normalize(emitted(paragraph)) for paragraph in xml(content).iterfind('.//w:body//w:p', NS)]
    lines = [line for line in lines if line]
    assert 'Example Labs' in text and lines
    assert [line for line in lines if line not in text and not words_in_order(text, line)] == []
