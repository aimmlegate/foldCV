"""DOCX extraction (extraction.parser) regressions from the October 19 review: inert relationships, hidden runs,
wrapped table rows."""

from xml.etree import ElementTree as ET

import pytest

from packages.resume_core.extraction import parser
from packages.resume_core.extraction.docx_structure import ParagraphStyles
from tests.extract.test_parser import rebuild


@pytest.mark.parametrize("target,kind", [("tel:+1234567", "hyperlink"), ("file:///local/image.png", "image"),
                                         ("https://example.invalid/template", "attachedTemplate")])
def test_inert_external_relationship_does_not_reject_visible_docx(target, kind):
    rels = (f'<Relationships xmlns="{parser.R[1:-1]}"><Relationship Id="extra" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}" '
        f'Target="{target}" TargetMode="External"/></Relationships>').encode()
    result = parser.extract(rebuild(extra=("word/_rels/extra.xml.rels", rels)), "source.docx")
    assert any(unit.text == "Привет résumé" for unit in result.units)
    assert all(link.relationship_id != "extra" for link in result.links)


def test_hidden_runs_inherited_styles_and_explicit_visibility():
    styles = ParagraphStyles(ET.fromstring(f'<w:styles xmlns:w="{parser.W[1:-1]}">'
        '<w:style w:styleId="Hidden"><w:rPr><w:vanish/></w:rPr></w:style></w:styles>'))
    paragraph = ET.fromstring(f'<w:p xmlns:w="{parser.W[1:-1]}"><w:pPr><w:pStyle w:val="Hidden"/></w:pPr>'
        '<w:r><w:t>Inherited secret</w:t></w:r>'
        '<w:r><w:rPr><w:vanish w:val="0"/></w:rPr><w:t>Visible</w:t></w:r></w:p>')
    assert parser._paragraph_text(paragraph, styles) == "Visible"
    xml = (f'<w:document xmlns:w="{parser.W[1:-1]}"><w:body><w:p>'
        '<w:r><w:t>Visible</w:t></w:r><w:r><w:rPr><w:vanish/></w:rPr><w:t>Secret</w:t></w:r>'
        '</w:p></w:body></w:document>').encode()
    result = parser.extract(rebuild({"word/document.xml": xml}), "source.docx")
    assert result.units[0].text == "Visible"


def test_unsupported_wrapped_table_row_keeps_later_row_location():
    xml = (f'<w:document xmlns:w="{parser.W[1:-1]}"><w:body><w:tbl><w:tblPr/>'
        '<w:sdt><w:sdtContent><w:tr><w:tc><w:p><w:r><w:t>Skipped</w:t></w:r></w:p></w:tc></w:tr></w:sdtContent></w:sdt>'
        '<w:tr><w:tc><w:p><w:r><w:t>Second row</w:t></w:r></w:p></w:tc></w:tr>'
        '</w:tbl></w:body></w:document>').encode()
    result = parser.extract(rebuild({"word/document.xml": xml}), "source.docx")
    row = next(unit for unit in result.units if unit.text == "Second row")
    assert row.location.row == 1


def document(body):
    """The units and gaps of the document body; the fixture's header and footer stay out."""
    xml = f'<w:document xmlns:w="{parser.W[1:-1]}"><w:body>{body}</w:body></w:document>'.encode()
    result = parser.extract(rebuild({"word/document.xml": xml}), "source.docx")
    inside = lambda value: value.location.part == "word/document.xml"
    return result.model_copy(update={"units": [*filter(inside, result.units)], "gaps": [*filter(inside, result.gaps)]})


def paragraph(text):
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def test_the_default_paragraph_style_is_resolved_once_not_for_each_run():
    class Counted(dict):
        reads = 0
        def items(self):
            Counted.reads += 1
            return super().items()
    styles = ParagraphStyles(ET.fromstring(f'<w:styles xmlns:w="{parser.W[1:-1]}">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Base"><w:rPr><w:vanish/></w:rPr></w:style></w:styles>'))
    styles.styles = Counted(styles.styles)
    paragraph_node = ET.fromstring(f'<w:p xmlns:w="{parser.W[1:-1]}"><w:r><w:t>Text</w:t></w:r></w:p>')
    assert all(styles.hidden(paragraph_node[0], paragraph_node) for _ in range(5)) and Counted.reads == 0


def test_a_paragraph_is_read_for_its_style_once_not_for_each_run():
    class Counted(ET.Element):
        reads = 0
        def find(self, path, namespaces=None):
            Counted.reads += 1
            return super().find(path, namespaces)
    styles, paragraph_node = ParagraphStyles(), Counted(parser.W + "p")
    runs = [ET.SubElement(paragraph_node, parser.W + "r") for _ in range(5)]
    assert not any(styles.hidden(run, paragraph_node) for run in runs) and Counted.reads == 1
    other = Counted(parser.W + "p", {})
    ET.SubElement(other, parser.W + "pPr").append(ET.Element(parser.W + "pStyle", {parser.W + "val": "Hidden"}))
    assert styles.hidden(ET.Element(parser.W + "r"), other) is False and styles.paragraph_style == "Hidden"


def test_body_level_content_controls_keep_their_text_in_reading_order():
    control = f'<w:sdt><w:sdtPr><w:alias w:val="Label"/></w:sdtPr><w:sdtContent>{paragraph("Опыт работы")}' \
        f'<w:sdt><w:sdtContent>{paragraph("Python")}</w:sdtContent></w:sdt>' \
        f'<w:tbl><w:tr><w:tc>{paragraph("Cell")}</w:tc></w:tr></w:tbl></w:sdtContent></w:sdt>'
    result = document(paragraph("Head") + control + "<w:sdt/>" + paragraph("Tail"))
    assert [unit.text for unit in result.units] == ["Head", "Опыт работы", "Python", "Cell", "Tail"]
    assert [unit.location.paragraph for unit in result.units if unit.location.kind == "paragraph"] == [0, 1, 2, 3]
    assert not result.gaps


def test_nested_tables_keep_their_text_and_their_own_table_index():
    nested = f'<w:tbl><w:tr><w:tc>{paragraph("Nested")}</w:tc></w:tr></w:tbl>'
    outer = f'<w:tbl><w:tr><w:tc>{paragraph("Before")}{nested}{paragraph("After")}</w:tc></w:tr></w:tbl>'
    result = document(outer + f'<w:tbl><w:tr><w:tc>{paragraph("Second")}</w:tc></w:tr></w:tbl>')
    assert [(unit.text, unit.location.table) for unit in result.units] == [("Before", 0), ("Nested", 1), ("After", 0), ("Second", 2)]
    assert [unit.location.paragraph for unit in result.units[:3]] == [0, 0, 1] and not result.gaps


def test_what_still_cannot_be_read_stays_a_gap():
    result = document('<w:customXml><w:p><w:r><w:t>Unread</w:t></w:r></w:p></w:customXml>' + paragraph("Tail"))
    assert [unit.text for unit in result.units] == ["Tail"]
    assert [gap.code for gap in result.gaps] == ["UNSUPPORTED_CONTENT"]


def test_word_hyphen_elements_keep_literal_values_and_a_symbol_is_a_gap():
    result = document('<w:p><w:r><w:t>+7</w:t><w:noBreakHyphen/><w:t>999</w:t><w:softHyphen/><w:t>x</w:t></w:r></w:p>')
    assert result.units[0].text == "+7\u2011999x" and not result.gaps
    symbol = document('<w:p><w:r><w:t>a</w:t><w:sym w:font="Wingdings" w:char="F0B7"/></w:r></w:p>')
    assert symbol.units[0].text == "a"
    assert [(gap.code, gap.location.paragraph) for gap in symbol.gaps] == [("UNSUPPORTED_CONTENT", 0)]
