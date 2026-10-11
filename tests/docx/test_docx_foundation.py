"""Converter-free DOCX checks retain the existing newline writer behavior."""

from docx import Document
from lxml import etree


def test_docx_newlines_are_real_word_breaks_without_converter():
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Line one\n\nLine three")
    nodes = etree.fromstring(paragraph._p.xml.encode())
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    assert len(nodes.findall(".//w:br", namespace)) == 2
    assert paragraph.text == "Line one\n\nLine three"
