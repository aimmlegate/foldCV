"""Converter-free DOCX checks: the product's run writer keeps line breaks and tabs as Word nodes."""

from docx import Document
from docx.oxml.ns import qn

from packages.resume_core.rendering.captured_docx import native_text


def test_docx_newlines_are_real_word_breaks_without_converter():
    run = Document().add_paragraph().add_run()
    native_text(run, "Line one\n\nLine three\r\nLine four\rLine five\t  end")
    nodes = [(node.tag, node.text) for node in run._r]
    text, line_break, tab = qn("w:t"), qn("w:br"), qn("w:tab")
    assert nodes == [(text, "Line one"), (line_break, None), (line_break, None), (text, "Line three"), (line_break, None),
                     (text, "Line four"), (line_break, None), (text, "Line five"), (tab, None), (text, "  end")]
    assert all(node.get(qn("xml:space")) == "preserve" for node in run._r if node.tag == text)
