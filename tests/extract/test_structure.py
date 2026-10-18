"""Source layout cases with independent geometry and literal text expectations."""

from collections import Counter
import json
from pathlib import Path

import pymupdf
import pytest

from packages.resume_core.extraction.parser import extract, W
from packages.resume_core.gui_normalization import canonical_source
from packages.resume_core.import_agent import source_parts
from packages.resume_core.import_content import source_paragraphs
from packages.resume_core.models.contracts import Source
from tests.extract.test_parser import rebuild


def pdf(rows, *, scale=1, pages=1):
    with pymupdf.open() as document:
        for _ in range(pages):
            document.new_page(width=600 * scale, height=800 * scale)
        for page, x, y, text, bold in rows:
            document[page].insert_text((x * scale, y * scale), text, fontsize=10 * scale,
                                      fontname="hebo" if bold else "helv")
        return document.tobytes()


def view(data, name):
    result = extract(data, name)
    source = canonical_source(result)
    return result, source_paragraphs([source], source_parts([source]))


@pytest.mark.parametrize("scale", [.6, 1, 1.8])
@pytest.mark.parametrize("leading_year", [False, True])
def test_pdf_visual_order_and_entry_spacing_survive_object_order_and_page_scale(scale, leading_year):
    texts = (["2009", "Institute One", "Qualification one"] if leading_year else
             ["Institute One", "Qualification one", "2009"])
    second = (["2005", "Institute Two", "Qualification two"] if leading_year else
              ["Institute Two", "Qualification two", "2005"])
    expected = ["Candidate", *texts, *second, "Continued on next page"]
    rows = [(0, 40, 100 + i * 18, text, text.startswith("Institute")) for i, text in enumerate(texts)]
    rows += [(0, 40, 180 + i * 18, text, text.startswith("Institute")) for i, text in enumerate(second)]
    rows += [(1, 40, 70, expected[-1], False), (0, 40, 40, "Candidate", True)]
    result, paragraphs = view(pdf(rows[::-1], scale=scale, pages=2), "varied.pdf")
    assert [u.text.strip() for u in result.units] == expected
    groups = [u.structure.group for u in result.units]
    assert len(set(groups[1:4])) == len(set(groups[4:7])) == 1
    assert groups[1] != groups[4]
    assert result.units[4].structure.gap_before > result.units[3].structure.gap_before * 2
    assert all(u.structure.bold for u in result.units if "Institute" in u.text)
    assert paragraphs[-1].page == 2
    assert all(p.hints and "visual group" in p.hints for p in paragraphs)


def test_pdf_columns_and_spanning_headings_keep_each_column_together():
    rows = []
    for base, prefix in ((80, "Top"), (240, "Bottom")):
        for x, side in ((330, "right"), (40, "left")):
            rows += [(0, x, base + i * 18, f"{prefix} {side} line {i}", False) for i in range(3)]
    rows += [(0, 40, 40, "Candidate heading across both columns with a long profession title", True),
             (0, 40, 180, "A wide section heading spanning both columns of the source document", True)]
    result, paragraphs = view(pdf(rows), "columns.pdf")
    expected = [rows[-2][3], *[f"Top {side} line {i}" for side in ("left", "right") for i in range(3)],
                rows[-1][3], *[f"Bottom {side} line {i}" for side in ("left", "right") for i in range(3)]]
    assert "".join(u.text for u in result.units).splitlines() == expected
    left = [p for p in paragraphs if "left line" in p.text]
    right = [p for p in paragraphs if "right line" in p.text]
    assert all("column 1" in p.hints for p in left)
    assert all("column 2" in p.hints for p in right)
    assert any("reading order uncertain" in p.hints for p in paragraphs)


@pytest.mark.parametrize("side", ["left", "right"])
def test_pdf_sparse_side_labels_stay_near_their_rows_without_semantic_binding(side):
    label_x, body_x = (40, 220) if side == "left" else (480, 40)
    rows = [(0, label_x, y, year, False) for y, year in ((80, "2024"), (180, "2021"))]
    for y, name in ((80, "First"), (180, "Second")):
        rows += [(0, body_x, y + i * 18, f"{name} entry has detailed source line {i}", i == 0) for i in range(3)]
    result, paragraphs = view(pdf(rows), "side-labels.pdf")
    text = "".join(u.text for u in result.units)
    assert text.index("2024") < text.index("First entry has detailed source line 1")
    assert text.index("2021") < text.index("Second entry has detailed source line 1")
    assert text.index("First entry has detailed source line 2") < text.index("2021")
    assert all("reading order uncertain" in p.hints for p in paragraphs)
    assert all(f"column {1 if side == 'left' else 2}" in p.hints for p in paragraphs if p.text.strip() in {"2024", "2021"})
    assert Counter(text.splitlines()) == Counter(row[3] for row in rows)


def test_pdf_rotated_and_overlapping_text_is_kept_with_uncertain_order():
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((100, 100), "Ordinary text")
        page.insert_text((100, 100), "Overlapping text")
        page.insert_text((350, 350), "Rotated text", rotate=90)
        result = extract(document.tobytes(), "rotated.pdf")
    assert Counter(line for u in result.units for line in u.text.splitlines()) == Counter(
        ["Ordinary text", "Overlapping text", "Rotated text"])
    assert all(u.structure.layout_uncertain for u in result.units)


def structured_docx():
    styles = (f'<w:styles xmlns:w="{W[1:-1]}"><w:style w:styleId="Section">'
        '<w:name w:val="Section title"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr>'
        '<w:rPr><w:b/></w:rPr></w:style><w:style w:styleId="Derived">'
        '<w:basedOn w:val="Section"/></w:style><w:style w:styleId="List">'
        '<w:pPr><w:numPr><w:ilvl w:val="2"/><w:numId w:val="7"/></w:numPr></w:pPr>'
        '</w:style></w:styles>').encode()
    body = (f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        '<w:p><w:pPr><w:pStyle w:val="Derived"/></w:pPr><w:r><w:t>Education</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/><w:vMerge w:val="restart"/></w:tcPr>'
        '<w:p><w:r><w:t>Institution</w:t></w:r></w:p><w:p><w:r><w:t>Qualification</w:t></w:r></w:p>'
        '</w:tc><w:tc><w:p><w:r><w:t>2009</w:t></w:r></w:p></w:tc></w:tr>'
        '<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/><w:vMerge/></w:tcPr>'
        '<w:p><w:r><w:t>More details</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p><w:r><w:t>2005</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '<w:p><w:pPr><w:pStyle w:val="List"/></w:pPr><w:r><w:t>Python</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="Section"/></w:pPr>'
        '<w:r><w:rPr><w:b w:val="0"/></w:rPr><w:t>Plain title</w:t></w:r></w:p>'
        '</w:body></w:document>').encode()
    return rebuild({"word/document.xml": body, "word/styles.xml": styles})


def test_docx_preserves_inherited_headings_lists_cells_merges_and_header_footer_context():
    result, paragraphs = view(structured_docx(), "tables.docx")
    units = {u.text: u for u in result.units}
    assert units["Education"].structure.heading_level == 2
    assert units["Education"].structure.bold is True
    assert units["Plain title"].structure.bold is False
    assert units["Python"].structure.list_level == 2
    assert units["Institution"].structure.column_span == 2
    assert units["Institution"].structure.row_merge == "start"
    assert units["More details"].structure.row_merge == "continue"
    assert units["2009"].location.column == units["2005"].location.column == 2
    assert units["2009"].location.row == 0 and units["2005"].location.row == 1
    hints = {p.text: p.hints for p in paragraphs}
    assert "table 1, row 1, cell 3" in hints["2009"]
    assert "table 1, row 2, cell 3" in hints["2005"]
    assert "spans 2 cells" in hints["Institution"]
    assert "header" in hints["Header repeated"] and "footer" in hints["Footer text"]
    assert "heading 2" in hints["Education"] and "list level 3" in hints["Python"]
    assert all(not u.structure.bounds for u in result.units)


def test_docx_explicit_body_outline_overrides_a_heading_style():
    body = (f'<w:document xmlns:w="{W[1:-1]}"><w:body><w:p><w:pPr>'
        '<w:pStyle w:val="Heading1"/><w:outlineLvl w:val="9"/></w:pPr>'
        '<w:r><w:t>Body text</w:t></w:r></w:p></w:body></w:document>').encode()
    result = extract(rebuild({"word/document.xml": body}), "body.docx")
    assert result.units[0].structure.heading_level is None


@pytest.mark.parametrize("name,pasted", [("source.txt", False), ("source.md", False), ("pasted.txt", True)])
def test_text_preserves_blank_lines_and_indentation_without_inventing_geometry(name, pasted):
    text = "# Name\r\n\r\n\r\n  Employer\n\t- detail\n2024\n"
    result = extract(text.encode(), name, pasted)
    assert "".join(u.text for u in result.units) == text
    assert result.units[3].structure.blank_before == 2
    assert result.units[3].structure.indent == 2
    assert result.units[4].structure.indent == 4
    assert result.units[0].structure.heading_level == (1 if name.endswith(".md") else None)
    assert all(u.structure.bounds is None and u.structure.group is None for u in result.units)


def test_markdown_code_fences_keep_hash_lines_as_text():
    result = extract(b"# Title\n```python\n# code comment\n```\n## Work\n", "source.md")
    assert [u.structure.heading_level for u in result.units] == [1, None, None, None, 2]


def test_absent_structure_keeps_legacy_source_unit_serialization_and_hash_inputs():
    legacy = json.loads(Path("contracts/examples/project.json").read_text())["sources"][0]
    source = Source.model_validate(legacy)
    assert all(u.structure is None for u in source.units)
    assert source.model_dump(by_alias=True)["units"] == legacy["units"]
    assert Source.model_validate(source.model_dump(by_alias=True)) == source
