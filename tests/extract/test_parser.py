"""Independent X01/X02 expectations for literal extraction and unsafe inputs."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import stat
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pymupdf
import pytest

from packages.resume_core.extraction import parser
from packages.resume_core.extraction.parser import ExtractFailure, extract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/synthetic/import"


def source(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def failure(data: bytes, name: str, code: str) -> None:
    with pytest.raises(ExtractFailure) as error:
        extract(data, name)
    assert error.value.code == code


def rebuild(replacements: dict[str, bytes] | None = None, extra: tuple[str, bytes] | None = None,
            symlink: bool = False) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(source("rich.docx"))) as original, ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for info in original.infolist():
            archive.writestr(info, (replacements or {}).get(info.filename, original.read(info)))
        if extra:
            if symlink:
                info = ZipInfo(extra[0])
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, extra[1])
            else:
                archive.writestr(*extra)
    return output.getvalue()


def test_pdf_columns_wraps_repeated_header_mixed_scan_and_empty_pages() -> None:
    result = extract(source("mixed-columns.pdf"), "mixed-columns.pdf")
    assert result.page_count == 4
    assert [(unit.location.page, unit.text) for unit in result.units] == [
        (1, "Repeated header\n"), (1, "Left column A\nLeft wrap-\ncontinues\n"),
        (1, "Right column B\n"), (2, "Repeated header\n"), (3, ""), (4, ""),
    ]
    assert [(gap.code, gap.location.page) for gap in result.gaps] == [
        ("IMAGE", 2), ("NO_TEXT", 3), ("IMAGE", 3), ("NO_TEXT", 4),
    ]
    assert [unit.order for unit in result.units] == list(range(6))


def test_docx_body_tables_headers_footers_image_and_shape_gap() -> None:
    result = extract(source("rich.docx"), "rich.docx")
    assert [(unit.location.kind, unit.text) for unit in result.units] == [
        ("paragraph", "Привет résumé"), ("table_cell", "Строка"), ("table_cell", "C++"),
        ("paragraph", ""), ("paragraph", ""), ("paragraph", "LinkedIn"),
        ("footer", "Footer text"), ("header", "Header repeated"),
    ]
    assert [(unit.location.row, unit.location.column) for unit in result.units[1:3]] == [(0, 0), (0, 1)]
    assert {gap.code for gap in result.gaps} == {"IMAGE", "SHAPE", "TEXT_BOX", "UNSUPPORTED_CONTENT"}
    assert any(gap.code == "UNSUPPORTED_CONTENT" and gap.location.kind == "header" and
               gap.location.part == "word/header1.xml" for gap in result.gaps)
    assert "Hidden shape text" not in "".join(unit.text for unit in result.units)
    assert "Contact inside content control" not in "".join(unit.text for unit in result.units)
    assert [(link.relationship_id, link.target) for link in result.links] == [
        ("rId999", "https://example.invalid/profile")]


def test_docx_printer_settings_remain_inert_and_unknown_binary_is_rejected() -> None:
    result = extract(source("rich.docx"), "rich.docx")
    assert "LinkedIn" in [unit.text for unit in result.units]
    assert result.byte_length == len(source("rich.docx"))
    failure(rebuild(extra=("word/unknown.bin", b"never run")), "unknown.docx", "EXTRACT_UNSUPPORTED")


def test_docx_table_wrappers_report_located_gaps_without_losing_other_units() -> None:
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    def add_text(cell: ET.Element, text: str) -> None:
        paragraph = ET.SubElement(cell, namespace + "p")
        run = ET.SubElement(paragraph, namespace + "r")
        ET.SubElement(run, namespace + "t").text = text

    with ZipFile(BytesIO(source("rich.docx"))) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    table = document.find(f"{namespace}body/{namespace}tbl")
    assert table is not None
    row = table.find(f"{namespace}tr")
    assert row is not None
    cell = row.find(f"{namespace}tc")
    assert cell is not None
    paragraph = cell.find(f"{namespace}p")
    assert paragraph is not None
    cell.remove(paragraph)
    cell_wrapper = ET.SubElement(cell, namespace + "sdt")
    ET.SubElement(cell_wrapper, namespace + "sdtContent").append(paragraph)
    row_wrapper = ET.SubElement(row, namespace + "sdt")
    row_content = ET.SubElement(row_wrapper, namespace + "sdtContent")
    add_text(ET.SubElement(row_content, namespace + "tc"), "Wrapped row content")
    table_wrapper = ET.SubElement(table, namespace + "sdt")
    table_content = ET.SubElement(table_wrapper, namespace + "sdtContent")
    wrapped_row = ET.SubElement(table_content, namespace + "tr")
    add_text(ET.SubElement(wrapped_row, namespace + "tc"), "Wrapped table content")
    wrapped = rebuild({"word/document.xml": ET.tostring(document, encoding="utf-8")})

    result = extract(wrapped, "wrapped.docx")
    baseline = extract(source("rich.docx"), "rich.docx")
    assert result.byte_length == len(wrapped)
    assert result.byte_sha256 == hashlib.sha256(wrapped).hexdigest()
    assert [unit.text for unit in result.units] == [unit.text for unit in baseline.units if unit.text != "Строка"]
    assert [(gap.location.table, gap.location.row, gap.location.column) for gap in result.gaps
            if gap.code == "UNSUPPORTED_CONTENT" and gap.location.kind == "table_cell"] == [
                (0, 0, 0), (0, 0, None), (0, None, None)]


def test_utf8_and_markdown_preserve_line_endings_unicode_and_hash() -> None:
    txt = extract(source("unicode.txt"), "unicode.txt")
    assert [unit.text for unit in txt.units] == ["Привет\r\n", "Café\n", "wrap-\n", "next\n"]
    assert "".join(unit.text for unit in txt.units).encode("utf-8") == source("unicode.txt")
    assert txt.byte_ref == "memory:sha256:" + txt.byte_sha256
    md = extract(source("notes.md"), "notes.md")
    assert md.source_kind == "markdown"
    assert [unit.text for unit in md.units] == ["# Résumé\n", "- Kotlin\n"]
    pasted = extract(b"Line one\r\nLine two", "pasted.txt", pasted=True)
    assert pasted.source_kind == "paste"
    assert [unit.text for unit in pasted.units] == ["Line one\r\n", "Line two"]


def test_empty_invalid_legacy_encrypted_and_mismatched_formats() -> None:
    failure(b"", "empty.txt", "EXTRACT_EMPTY")
    failure(b"\xffbad", "bad.txt", "EXTRACT_ENCODING")
    failure(b"a\x00b", "bad.txt", "EXTRACT_UNSUPPORTED")
    failure(source("rich.docx"), "legacy.doc", "EXTRACT_UNSUPPORTED")
    failure(source("rich.docx"), "macro.docm", "EXTRACT_UNSUPPORTED")
    failure(source("rich.docx"), "wrong.pdf", "EXTRACT_UNSUPPORTED")
    failure(b"%PDF-1.7\ntruncated", "broken.pdf", "EXTRACT_MALFORMED")
    failure(source("rich.docx")[:150], "broken.docx", "EXTRACT_MALFORMED")
    document = pymupdf.open()
    document.new_page().insert_text((20, 20), "secret")
    encrypted = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    document.close()
    failure(encrypted, "locked.pdf", "EXTRACT_ENCRYPTED")


def test_zip_duplicate_traversal_symlink_external_xml_and_bomb_rejected() -> None:
    failure(rebuild(extra=("word/document.xml", b"duplicate")), "duplicate.docx", "EXTRACT_UNSAFE_ARCHIVE")
    failure(rebuild(extra=("../escape.xml", b"x")), "traversal.docx", "EXTRACT_UNSAFE_ARCHIVE")
    failure(rebuild(extra=("word/evil", b"target"), symlink=True), "link.docx", "EXTRACT_UNSAFE_ARCHIVE")
    rels = (b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId9" Target="https://invalid.example/file" TargetMode="External"/></Relationships>')
    failure(rebuild(extra=("word/_rels/new.xml.rels", rels)), "external.docx", "EXTRACT_EXTERNAL_LINK")
    xml = b'<!DOCTYPE x [<!ENTITY e SYSTEM "https://invalid.example/e">]><w:document/>'
    failure(rebuild({"word/document.xml": xml}), "entity.docx", "EXTRACT_UNSAFE_XML")
    failure(rebuild(extra=("word/huge.xml", b" " * (parser.MAX_ZIP_ENTRY + 1))), "bomb.docx", "EXTRACT_ARCHIVE_LIMIT")


def test_limits_fail_without_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parser, "MAX_PAGES", 2)
    failure(source("mixed-columns.pdf"), "mixed-columns.pdf", "EXTRACT_PAGE_LIMIT")
    monkeypatch.setattr(parser, "MAX_TEXT_CHARS", 5)
    failure(source("unicode.txt"), "unicode.txt", "EXTRACT_TEXT_LIMIT")
    monkeypatch.setattr(parser, "MAX_TEXT_CHARS", 750_000)
    monkeypatch.setattr(parser, "MAX_UNITS", 1)
    failure(source("notes.md"), "notes.md", "EXTRACT_UNIT_LIMIT")
