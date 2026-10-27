"""Rich DOCX tables and images: merged cells, exact local image parts and flowing layout."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
from PIL import Image
import pytest
from pydantic import ValidationError

from packages.resume_core.models.rich_document import TableContent
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rendering.template import RenderFailure
from tests.render.rich_layout_fixtures import cell, main_only as document, merged

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}


def test_rich_word_table_preserves_spans_headers_widths_shading_alignment_and_editable_text():
    tree = document([{"id": "table", "revision": 1, "type": "table", "props": {}, "content": merged(), "children": [], "provenance": []}])
    with ZipFile(BytesIO(render_rich_docx(tree))) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        table = root.xpath("//w:tbl[w:tr/w:tc/w:p/w:r/w:t='Wide']", namespaces=NS)[0]
        assert len(table.xpath("w:tr", namespaces=NS)) == 3
        assert table.xpath(".//w:gridSpan[@w:val='2']", namespaces=NS)
        assert table.xpath(".//w:vMerge[@w:val='restart']", namespaces=NS) and table.xpath(".//w:vMerge[not(@w:val)]", namespaces=NS)
        assert table.xpath("w:tr[1]/w:trPr/w:tblHeader", namespaces=NS)
        assert table.xpath(".//w:shd[@w:fill='aabbcc']", namespaces=NS) and table.xpath(".//w:jc[@w:val='right']", namespaces=NS)
        assert "".join(table.xpath(".//w:t/text()", namespaces=NS)) == "WideBTallDEFG"
        assert not table.xpath(".//w:cantSplit", namespaces=NS)
        assert table.xpath("w:tblGrid/w:gridCol/@w:w", namespaces=NS) == ["2800", "4200", "1400"]


def test_image_docx_keeps_exact_bytes_alt_aspect_alignment_and_styled_caption():
    output = BytesIO(); Image.new("RGB", (100, 50), "red").save(output, format="PNG"); image = output.getvalue()
    tree = document([{"id": "image", "revision": 1, "type": "image", "content": None, "children": [], "provenance": [],
        "props": {"assetId": "asset", "width": 1200, "height": 600, "alignment": "center", "alt": "Exact alt",
            "caption": [{"type": "text", "text": "Editable caption", "styles": {"bold": True}}]}}])
    with ZipFile(BytesIO(render_rich_docx(tree, {"asset": image}))) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        assert sum(archive.read(name) == image for name in media) == 1
        assert root.xpath("//wp:docPr/@descr", namespaces=NS) == ["Exact alt"]
        assert root.xpath("//wp:extent/@cx", namespaces=NS) == [str(420 * 12700)]
        assert root.xpath("//wp:extent/@cy", namespaces=NS) == [str(210 * 12700)]
        assert root.xpath("//w:p[w:r/w:t='Editable caption']/w:pPr/w:jc[@w:val='center']", namespaces=NS)
        assert root.xpath("//w:p[.//wp:inline]/w:pPr/w:spacing[@w:lineRule='auto']", namespaces=NS)
        assert root.xpath("//w:r[w:t='Editable caption']/w:rPr/w:b", namespaces=NS)
    with pytest.raises(RenderFailure, match="RICH_IMAGE_MISSING"):
        render_rich_docx(tree)


def test_table_fully_spanned_row_round_trip_and_invalid_neighbor_grid_are_explicit():
    content = {"headerRows": 0, "columnWidths": [100, 100], "rows": [
        {"id": "r1", "cells": [cell("a", "All", rowspan=2, colspan=2)]}, {"id": "r2", "cells": []}]}
    assert TableContent.model_validate(content).rows[1].cells == []
    for changed in ({**content, "columnWidths": [100]}, {**content, "headerRows": 3},
        {**content, "rows": [{"id": "r1", "cells": [cell("a", "Missing")]}]}):
        with pytest.raises(ValidationError):
            TableContent.model_validate(changed)
