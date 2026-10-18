"""Extract literal source text and structural gaps without inference."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import PurePosixPath
import posixpath
import re
import stat
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

import pymupdf

from .models import ExtractGap, ExtractLink, ExtractLocation, ExtractResult, ExtractUnit
from .pdf_layout import page_blocks
from .docx_structure import ParagraphStyles, number
from packages.resume_core.models.contracts import SourceStructure

MAX_SOURCE = 6 * 1024 * 1024
MAX_PAGES = 40
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 750_000
MAX_UNITS = 5_000
MAX_ZIP_ENTRIES = 200
MAX_ZIP_ENTRY = 8 * 1024 * 1024
MAX_ZIP_EXPANDED = 32 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"


class ExtractFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Collected:
    def __init__(self) -> None:
        self.units: list[ExtractUnit] = []
        self.gaps: list[ExtractGap] = []
        self.links: list[ExtractLink] = []
        self.text_bytes = 0
        self.text_chars = 0

    def add(self, text: str, location: ExtractLocation, structure: SourceStructure | None = None) -> None:
        size = len(text.encode("utf-8"))
        if len(self.units) >= MAX_UNITS:
            raise ExtractFailure("EXTRACT_UNIT_LIMIT")
        if self.text_bytes + size > MAX_TEXT_BYTES or self.text_chars + len(text) > MAX_TEXT_CHARS:
            raise ExtractFailure("EXTRACT_TEXT_LIMIT")
        order = len(self.units)
        self.units.append(ExtractUnit(id=f"unit_{order + 1}", order=order, text=text,
                                      location=location, structure=structure))
        self.text_bytes += size
        self.text_chars += len(text)

    def gap(self, code: str, location: ExtractLocation) -> None:
        if len(self.gaps) >= MAX_UNITS:
            raise ExtractFailure("EXTRACT_UNIT_LIMIT")
        self.gaps.append(ExtractGap(code=code, location=location))


def _text_lines(data: bytes, kind: str, out: Collected) -> None:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise ExtractFailure("EXTRACT_ENCODING") from None
    if "\x00" in text:
        raise ExtractFailure("EXTRACT_UNSUPPORTED")
    if not text:
        out.add("", ExtractLocation(kind="pasted" if kind == "paste" else "paragraph", paragraph=0))
        out.gap("NO_TEXT", out.units[0].location)
        return
    blank_before = 0
    fence = None
    for index, line in enumerate(text.splitlines(keepends=True)):
        expanded = line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(" "))
        heading = re.match(r" {0,3}(#{1,6})\s+", line) if kind == "markdown" and fence is None else None
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line) if kind == "markdown" else None
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        out.add(line, ExtractLocation(kind="pasted" if kind == "paste" else "paragraph", paragraph=index),
                SourceStructure(indent=indent, blank_before=blank_before,
                                heading_level=len(heading[1]) if heading else None))
        blank_before = blank_before + 1 if not line.strip() else 0


def _pdf(data: bytes, out: Collected) -> int:
    if b"%%EOF" not in data[-1024:]:
        raise ExtractFailure("EXTRACT_MALFORMED")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
        if doc.needs_pass:
            raise ExtractFailure("EXTRACT_ENCRYPTED")
        if doc.is_repaired:
            raise ExtractFailure("EXTRACT_MALFORMED")
        if not 1 <= doc.page_count <= MAX_PAGES:
            raise ExtractFailure("EXTRACT_PAGE_LIMIT")
        for page_number in range(1, doc.page_count + 1):
            page = doc.load_page(page_number - 1)
            visible_text = False
            for text, index, structure in page_blocks(page):
                location = ExtractLocation(kind="page", page=page_number, paragraph=index)
                if text:
                    out.add(text, location, structure)
                    visible_text = visible_text or bool(text.strip())
            if not visible_text:
                location = ExtractLocation(kind="page", page=page_number)
                out.add("", location)
                out.gap("NO_TEXT", location)
            if page.get_image_info():
                out.gap("IMAGE", ExtractLocation(kind="image", page=page_number))
        return doc.page_count
    except ExtractFailure:
        raise
    except (RuntimeError, ValueError, TypeError, IndexError):
        raise ExtractFailure("EXTRACT_MALFORMED") from None
    finally:
        if "doc" in locals():
            doc.close()


def _check_xml(data: bytes) -> ET.Element:
    if b"\x00" in data or re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.IGNORECASE):
        raise ExtractFailure("EXTRACT_UNSAFE_XML")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise ExtractFailure("EXTRACT_MALFORMED") from None


def _check_archive(archive: ZipFile, out: Collected) -> dict[str, bytes]:
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ExtractFailure("EXTRACT_ARCHIVE_LIMIT")
    names: set[str] = set()
    printer_bins: set[str] = set()
    total = 0
    contents: dict[str, bytes] = {}
    for info in infos:
        name = info.filename
        parts = name.split("/")
        mode = info.external_attr >> 16
        if (not name or name.casefold() in names or name.startswith("/") or "\\" in name or "\x00" in name or
                any(part in {"", ".", ".."} for part in (parts[:-1] if info.is_dir() else parts)) or
                (mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}) or
                info.flag_bits & 1 or info.compress_type not in {0, 8}):
            raise ExtractFailure("EXTRACT_UNSAFE_ARCHIVE")
        lower = name.lower()
        if (PurePosixPath(name).suffix.lower() in {".exe", ".dll"} or "vbaproject" in lower or
                "embeddings/" in lower or "activex/" in lower or "oleobject" in lower):
            raise ExtractFailure("EXTRACT_UNSUPPORTED")
        if lower.endswith(".bin"):
            if not re.fullmatch(r"word/printerSettings/printerSettings\d+\.bin", name):
                raise ExtractFailure("EXTRACT_UNSUPPORTED")
            printer_bins.add(name)
        names.add(name.casefold())
        if info.is_dir():
            continue
        total += info.file_size
        if info.file_size > MAX_ZIP_ENTRY or total > MAX_ZIP_EXPANDED:
            raise ExtractFailure("EXTRACT_ARCHIVE_LIMIT")
        if info.file_size > max(1, info.compress_size) * 200:
            raise ExtractFailure("EXTRACT_ARCHIVE_LIMIT")
        try:
            chunks: list[bytes] = []
            actual = 0
            with archive.open(info) as stream:
                while True:
                    chunk = stream.read(min(64 * 1024, MAX_ZIP_ENTRY + 1 - actual))
                    if not chunk:
                        break
                    actual += len(chunk)
                    if actual > MAX_ZIP_ENTRY or total - info.file_size + actual > MAX_ZIP_EXPANDED:
                        raise ExtractFailure("EXTRACT_ARCHIVE_LIMIT")
                    chunks.append(chunk)
            raw = b"".join(chunks)
        except ExtractFailure:
            raise
        except (BadZipFile, RuntimeError, OSError):
            raise ExtractFailure("EXTRACT_MALFORMED") from None
        if len(raw) != info.file_size:
            raise ExtractFailure("EXTRACT_MALFORMED")
        contents[name] = raw
    if "[Content_Types].xml" not in contents or "word/document.xml" not in contents:
        raise ExtractFailure("EXTRACT_UNSUPPORTED")
    if b"macroEnabled" in contents["[Content_Types].xml"]:
        raise ExtractFailure("EXTRACT_UNSUPPORTED")
    printer_targets: set[str] = set()
    for name, raw in contents.items():
        if name.endswith((".xml", ".rels")):
            root = _check_xml(raw)
            if name.endswith(".rels"):
                for node in root.iter():
                    if node.tag == R + "Relationship" and node.attrib.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/printerSettings":
                        target = node.attrib.get("Target", "")
                        if node.attrib.get("TargetMode", "").lower() == "external" or target.startswith("/") or "\\" in target:
                            raise ExtractFailure("EXTRACT_UNSAFE_ARCHIVE")
                        relative = posixpath.normpath(posixpath.join(posixpath.dirname(posixpath.dirname(name)), target))
                        if relative not in printer_bins:
                            raise ExtractFailure("EXTRACT_UNSAFE_ARCHIVE")
                        printer_targets.add(relative)
                    if node.tag == R + "Relationship" and node.attrib.get("TargetMode", "").lower() == "external":
                        relationship_type = node.attrib.get("Type", "")
                        target = node.attrib.get("Target", "")
                        if (relationship_type != "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" or
                                not target.lower().startswith(("https://", "http://", "mailto:")) or
                                len(target) > 2048 or any(ord(char) < 32 for char in target) or len(out.links) >= 100):
                            raise ExtractFailure("EXTRACT_EXTERNAL_LINK")
                        out.links.append(ExtractLink(part=name, relationship_id=node.attrib.get("Id", ""), target=target))
    if printer_bins != printer_targets:
        raise ExtractFailure("EXTRACT_UNSUPPORTED")
    return contents


def _paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    def visit(node: ET.Element) -> None:
        if node.tag.endswith("}txbxContent"):
            return
        if node.tag == MC + "AlternateContent":
            selected = node.find(MC + "Fallback")
            if selected is None:
                selected = node.find(MC + "Choice")
            if selected is not None:
                visit(selected)
            return
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in {W + "br", W + "cr"}:
            parts.append("\n")
        for child in node:
            visit(child)
    visit(paragraph)
    return "".join(parts)


def _paragraph(paragraph: ET.Element, location: ExtractLocation, out: Collected,
               styles: ParagraphStyles, *, column_span=None, row_merge=None) -> None:
    text = _paragraph_text(paragraph)
    structure = styles.hints(paragraph, location.part)
    structure.column_span, structure.row_merge = column_span, row_merge
    out.add(text, location, structure)
    tags = {node.tag.rsplit("}", 1)[-1] for node in paragraph.iter()}
    if "txbxContent" in tags:
        out.gap("TEXT_BOX", location)
    if tags & {"shape", "sp", "pict", "object", "AlternateContent"}:
        out.gap("SHAPE", location)
    if tags & {"drawing", "imagedata", "blip"}:
        out.gap("IMAGE", location)


def _table(table: ET.Element, index: int, out: Collected, styles: ParagraphStyles, part: str | None = None) -> None:
    row_index = 0
    for table_child in table:
        if table_child.tag in {W + "tblPr", W + "tblGrid"}:
            continue
        if table_child.tag != W + "tr":
            out.gap("UNSUPPORTED_CONTENT", ExtractLocation(kind="table_cell", table=index, part=part))
            continue
        before = table_child.find(W + "trPr/" + W + "gridBefore")
        column = number(before.get(W + "val") if before is not None else None, 0, 1000) or 0
        for row_child in table_child:
            if row_child.tag in {W + "trPr", W + "tblPrEx"}:
                continue
            if row_child.tag != W + "tc":
                out.gap("UNSUPPORTED_CONTENT", ExtractLocation(kind="table_cell", table=index,
                                                                 row=row_index, part=part))
                continue
            paragraph_index = 0
            span = row_child.find(W + "tcPr/" + W + "gridSpan")
            column_span = number(span.get(W + "val") if span is not None else None, 1, 1000) or 1
            merge = row_child.find(W + "tcPr/" + W + "vMerge")
            row_merge = ("start" if merge.get(W + "val") == "restart" else "continue") if merge is not None else None
            for cell_child in row_child:
                if cell_child.tag == W + "tcPr":
                    continue
                location = ExtractLocation(kind="table_cell", table=index, row=row_index,
                                           column=column, paragraph=paragraph_index, part=part)
                if cell_child.tag == W + "p":
                    _paragraph(cell_child, location, out, styles, column_span=column_span, row_merge=row_merge)
                    paragraph_index += 1
                else:
                    out.gap("UNSUPPORTED_CONTENT", location)
            column += column_span
        row_index += 1


def _docx(data: bytes, out: Collected) -> None:
    try:
        with ZipFile(BytesIO(data)) as archive:
            contents = _check_archive(archive, out)
    except BadZipFile:
        raise ExtractFailure("EXTRACT_MALFORMED") from None
    document = _check_xml(contents["word/document.xml"])
    styles = ParagraphStyles(_check_xml(contents["word/styles.xml"]) if "word/styles.xml" in contents else None)
    body = document.find(W + "body")
    if body is None:
        raise ExtractFailure("EXTRACT_MALFORMED")
    paragraph_index = 0
    table_index = 0
    for child in body:
        if child.tag == W + "p":
            _paragraph(child, ExtractLocation(kind="paragraph", paragraph=paragraph_index, part="word/document.xml"), out, styles)
            paragraph_index += 1
        elif child.tag == W + "tbl":
            _table(child, table_index, out, styles, "word/document.xml")
            table_index += 1
        elif child.tag != W + "sectPr":
            out.gap("UNSUPPORTED_CONTENT", ExtractLocation(kind="paragraph", paragraph=paragraph_index, part="word/document.xml"))
    for name in sorted(contents):
        if name in {"word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"}:
            root = _check_xml(contents[name])
            if any(node.tag == W + "t" and (node.text or "").strip() for node in root.iter()):
                out.gap("UNSUPPORTED_CONTENT", ExtractLocation(kind="paragraph", part=name))
        if re.fullmatch(r"word/(?:header|footer)\d*\.xml", name):
            root = _check_xml(contents[name])
            kind = "header" if "header" in name else "footer"
            paragraph_index = 0
            table_index = 0
            for child in root:
                if child.tag == W + "p":
                    _paragraph(child, ExtractLocation(kind=kind, paragraph=paragraph_index, part=name), out, styles)
                    paragraph_index += 1
                elif child.tag == W + "tbl":
                    _table(child, table_index, out, styles, name)
                    table_index += 1
                else:
                    out.gap("UNSUPPORTED_CONTENT", ExtractLocation(kind=kind, paragraph=paragraph_index, part=name))
    if not out.units:
        location = ExtractLocation(kind="paragraph", paragraph=0, part="word/document.xml")
        out.add("", location)
        out.gap("NO_TEXT", location)


def extract(data: bytes, original_name: str, pasted: bool = False) -> ExtractResult:
    if not data or len(data) > MAX_SOURCE:
        raise ExtractFailure("EXTRACT_EMPTY" if not data else "INPUT_TOO_LARGE")
    extension = PurePosixPath(original_name).suffix.lower()
    if pasted:
        kind, mime, parser, version = "paste", "text/plain", "utf8", "2"
    elif extension in {".doc", ".docm", ".dot", ".dotm"}:
        raise ExtractFailure("EXTRACT_UNSUPPORTED")
    elif extension == ".pdf" and data.startswith(b"%PDF-"):
        kind, mime, parser, version = "pdf", "application/pdf", "pymupdf", pymupdf.VersionBind + "/layout2"
    elif extension == ".docx" and data.startswith(b"PK\x03\x04"):
        kind, mime, parser, version = "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "ooxml", "2"
    elif extension in {".txt", ".md", ".markdown"} and not data.startswith((b"%PDF-", b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
        kind = "markdown" if extension in {".md", ".markdown"} else "txt"
        mime, parser, version = "text/markdown" if kind == "markdown" else "text/plain", "utf8", "2"
    else:
        raise ExtractFailure("EXTRACT_UNSUPPORTED")
    out = Collected()
    pages = None
    if kind == "pdf":
        pages = _pdf(data, out)
    elif kind == "docx":
        _docx(data, out)
    else:
        _text_lines(data, kind, out)
    digest = hashlib.sha256(data).hexdigest()
    return ExtractResult(source_id="source_" + digest[:24], source_kind=kind, original_name=original_name,
                         mime_type=mime, byte_sha256=digest, byte_length=len(data), byte_ref="memory:sha256:" + digest,
                         parser=parser, parser_version=version, page_count=pages, units=out.units, gaps=out.gaps,
                         links=out.links)
