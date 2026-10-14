"""Editable initial rich export, full embedded faces and guarded unsupported caches."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
import pytest

from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.rendering.rich_docx import render_rich_docx, current_snapshot
from packages.resume_core.rendering.template import RenderFailure
from packages.resume_core.rich_archive import export_rich_archive
from packages.resume_core.gui_archive_zip import read_zip
from tests.recovery.test_rich_persistence import without_sources


def initial_document(text):
    return RichDocumentV1.model_validate({"schemaVersion": 1, "revision": 1, "regions": [
        {"id": "header", "role": "header", "revision": 1, "blocks": []},
        {"id": "sidebar", "role": "sidebar", "revision": 1, "blocks": []},
        {"id": "main", "role": "main", "revision": 1, "blocks": [{"id": "long", "type": "paragraph", "revision": 1,
            "props": {}, "children": [], "provenance": [], "content": [{"type": "text", "text": text,
                "styles": {"bold": True, "italic": True, "textColor": "#334455", "backgroundColor": "#EEEEDD"}},
                {"type": "link", "href": "https://example.com/" + "a" * 1400,
                    "content": [{"type": "text", "text": "Exact URL", "styles": {"underline": True}}]}]}]}]})


def test_initial_docx_preserves_long_tokens_cyrillic_links_marks_and_full_font_faces():
    text = "Длинный текст\n" + "name@example.com" * 300
    raw = render_rich_docx(initial_document(text))
    with ZipFile(BytesIO(raw)) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        assert "".join(xml.xpath("//w:t/text()", namespaces=ns)) == text.replace("\n", "") + "Exact URL"
        assert xml.xpath("//w:br", namespaces=ns) and xml.xpath("//w:i", namespaces=ns)
        assert xml.xpath("//w:shd[@w:fill='EEEEDD']", namespaces=ns)
        assert not xml.xpath("//w:cantSplit|//w:keepNext[@w:val='1']", namespaces=ns)
        assert all(cell.xpath("w:p|w:tbl", namespaces=ns) for cell in xml.xpath("//w:tc", namespaces=ns))
        relationships = archive.read("word/_rels/document.xml.rels").decode()
        assert "https://example.com/" + "a" * 1400 in relationships
        names = archive.namelist()
        assert len([name for name in names if name.endswith(".odttf")]) == 5
        assert all(len(archive.read(name)) > 250000 for name in names if name.endswith(".odttf"))
        fonts = archive.read("word/fontTable.xml").decode()
        assert all(family in fonts for family in ("Source Sans Pro Light", "Source Sans Pro Semibold", "Source Sans Pro Black"))
        assert "SIL OPEN FONT LICENSE" in archive.read("word/fonts/LICENSE.txt").decode()
        assert b"saveSubsetFonts" in archive.read("word/settings.xml")


def test_rich_table_and_code_export_without_a_stale_plain_cache():
    workspace = without_sources()
    raw = render_rich_docx(workspace.project.document)
    with ZipFile(BytesIO(raw)) as archive:
        assert b"<w:tbl>" in archive.read("word/document.xml")
    assert current_snapshot(workspace, {}) is None
    files = read_zip(export_rich_archive(workspace, {}, {}, {}))
    assert not any(path.startswith("renders/") for path in files)
    assert b'"type":"table"' in files["workspace.json"] and b'"type":"code"' in files["workspace.json"]
