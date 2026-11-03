"""The sample summary on synthetic DOCX and PDF files parsed by the real extraction parser."""

import json

import docx
import pymupdf

from packages.resume_core.extraction.parser import extract
from packages.resume_core.sample_summary import sample_summary

PHONE, MAIL = "+7 915 123-45-67", "sample.person@example.com"


def docx_sample(path, *, items=5, paragraphs=0):
    document = docx.Document()
    document.add_heading("Образец шаблона", level=1)
    document.add_paragraph(f"Телефон: {PHONE}, почта: {MAIL}")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Левая колонка"
    table.cell(0, 1).text = "Правая колонка"
    document.add_heading("Опыт работы", level=2)
    for number in range(1, items + 1):
        document.add_paragraph(f"Пункт списка {number}", style="List Bullet")
    for number in range(paragraphs):
        document.add_paragraph(f"Абзац {number} " + "длинный текст образца " * 12)
    document.save(path)
    return extract(path.read_bytes(), path.name)


def pdf_sample(path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((40, 60), "Sample title", fontsize=20, fontname="hebo")
        for row in range(6):
            page.insert_text((40, 120 + row * 40), f"Left column {row}", fontsize=9, fontname="helv")
            page.insert_text((320, 120 + row * 40), f"Right column {row} {MAIL}", fontsize=11, fontname="helv")
        document.save(path)
    return extract(path.read_bytes(), path.name)


def texts(summary):
    return [unit["text"] for unit in summary["units"]]


def assert_masked_and_short(summary):
    for text in texts(summary):
        assert len(text) <= 120
        assert MAIL not in text and "915" not in text and "@" not in text


def test_docx_summary_keeps_headings_columns_and_cuts_the_list(tmp_path):
    summary = sample_summary(docx_sample(tmp_path / "sample.docx"))
    assert summary["name"] == "sample.docx" and summary["pages"] is None
    assert summary["unitCount"] == summary["listed"] == len(summary["units"])
    units = summary["units"]
    assert set(units[0]) == {"column", "group", "heading", "style", "size", "bold", "list", "text"}
    assert {unit["heading"] for unit in units} >= {1, 2}
    assert {unit["column"] for unit in units if unit["text"].endswith("колонка")} == {1, 2}
    listed = [unit["text"] for unit in units if unit["list"] is not None]
    assert listed == ["Пункт списка 1", "Пункт списка 2", "… ещё 3"]
    assert_masked_and_short(summary)
    assert texts(summary)[1] == ""


def test_pdf_summary_keeps_columns_sizes_and_bold_title(tmp_path):
    summary = sample_summary(pdf_sample(tmp_path / "sample.pdf"))
    assert summary["pages"] == 1
    units = summary["units"]
    title = next(unit for unit in units if unit["text"].startswith("Sample"))
    assert title["bold"] is True and title["size"] == 20
    left = {unit["column"] for unit in units if unit["text"].startswith("Left")}
    right = {unit["column"] for unit in units if unit["text"].startswith("Right")}
    assert len(left) == len(right) == 1 and left != right
    assert {unit["size"] for unit in units if unit["text"].startswith("Left")} == {9}
    assert {unit["size"] for unit in units if unit["text"].startswith("Right")} == {11}
    assert_masked_and_short(summary)


def test_long_document_stays_under_the_byte_limit(tmp_path):
    result = docx_sample(tmp_path / "long.docx", items=40, paragraphs=400)
    summary = sample_summary(result)
    assert len(json.dumps(summary, ensure_ascii=False).encode("utf-8")) <= 32 * 1024
    assert summary["unitCount"] > summary["listed"] == len(summary["units"]) > 0
    assert_masked_and_short(summary)
    assert [text for text in texts(summary) if text.startswith("Пункт")] == ["Пункт списка 1", "Пункт списка 2"]
    small = sample_summary(result, limit=2048)
    assert len(json.dumps(small, ensure_ascii=False).encode("utf-8")) <= 2048
    assert small["listed"] < summary["listed"]


def test_gaps_are_listed_once_per_code_and_page(tmp_path):
    path = tmp_path / "image.pdf"
    with pymupdf.open() as document:
        for _ in range(2):
            page = document.new_page(width=200, height=200)
            page.insert_text((20, 40), "Text", fontsize=10)
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
            page.insert_image(pymupdf.Rect(20, 60, 60, 100), pixmap=pixmap)
            page.insert_image(pymupdf.Rect(80, 60, 120, 100), pixmap=pixmap)
        document.save(path)
    summary = sample_summary(extract(path.read_bytes(), path.name))
    assert summary["gaps"] == [{"code": "IMAGE", "page": 1}, {"code": "IMAGE", "page": 2}]
