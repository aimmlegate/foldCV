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
