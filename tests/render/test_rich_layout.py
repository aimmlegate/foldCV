"""Measured native layout, bounded template decoration and editable content."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rich_presentation import presentation
from tests.render.rich_layout_fixtures import fixture

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}


def test_focus_decoration_keeps_all_available_logos_without_truncating_unknown_entries():
    document, _ = fixture()
    before = document.model_dump()
    roles = presentation(document).blocks
    assert sum(view.logo is not None for view in roles.values()) == 9
    assert all(roles[f"focus-{i}"].role == "focus_entry" for i in range(10))
    assert roles["focus-8"].logo is not None and roles["focus-9"].logo is None
    assert roles["profile"].role == "profile_heading"
    assert roles["experience"].role == "section_heading"
    assert roles["job-0"].role == "group"
    assert document.model_dump() == before
    moved = document.model_copy(deep=True)
    moved.regions[2].blocks.remove(moved.regions[2].blocks[0])
    moved.regions[1].blocks.append(document.regions[2].blocks[0])
    assert presentation(moved).blocks["profile"].role == "section_heading"


def test_native_template_keeps_measured_columns_bands_brand_and_repeat_footer():
    document, _ = fixture()
    with ZipFile(BytesIO(render_rich_docx(document))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
        assert xml.xpath("//w:pgSz/@w:w", namespaces=NS) == ["11920"]
        assert xml.xpath("//w:pgSz/@w:h", namespaces=NS) == ["16840"]
        tables = xml.xpath("/w:document/w:body/w:tbl", namespaces=NS)
        assert tables[0].xpath("w:tblGrid/w:gridCol/@w:w", namespaces=NS) == ["9000"]
        assert tables[1].xpath("w:tblGrid/w:gridCol/@w:w", namespaces=NS) == ["2360", "125", "8900"]
        assert tables[1].xpath("w:tr[1]/w:trPr/w:tblHeader", namespaces=NS)
        bands = xml.xpath("//w:p[w:pPr/w:shd[@w:fill='EFEFEF']]", namespaces=NS)
        assert ["".join(p.xpath(".//w:t/text()", namespaces=NS)) for p in bands] == ["ОПЫТ", "НАВЫКИ"]
        assert all(p.xpath("w:pPr/w:ind/@w:left", namespaces=NS) == ["0"]
            and p.xpath("w:pPr/w:ind/@w:right", namespaces=NS) == ["0"]
            and p.xpath("w:pPr/w:ind/@w:firstLine", namespaces=NS) == ["100"] for p in bands)
        assert all(p.xpath("w:pPr/w:keepNext[not(@w:val) or @w:val='1']|ancestor::w:tr/w:trPr/w:cantSplit", namespaces=NS) for p in bands)
        prefixes = xml.xpath("//w:tbl[w:tblPr/w:tblCaption[@w:val='Job header' or @w:val='Section header']]", namespaces=NS)
        assert all(len("".join(t.xpath(".//w:t/text()", namespaces=NS))) <= 1000 for t in prefixes)
        assert len(xml.xpath("//w:cantSplit", namespaces=NS)) == len(prefixes)
        assert not tables[1].xpath("w:tr/w:trPr/w:cantSplit", namespaces=NS)
        headers = [etree.fromstring(archive.read(name)) for name in archive.namelist() if name.startswith("word/header") and name.endswith(".xml")]
        anchor = next(node for header in headers for node in header.xpath("//wp:anchor", namespaces=NS))
        assert int(anchor.xpath("wp:positionH/wp:posOffset/text()", namespaces=NS)[0]) == round(487.6 * 12700)
        assert len(xml.xpath("//wp:docPr[@descr='Focus technology logo']", namespaces=NS)) == 9
        footers = [etree.fromstring(archive.read(name)) for name in archive.namelist() if name.startswith("word/footer") and name.endswith(".xml")]
        assert len(footers) == 2
        assert all("".join(footer.xpath("//w:t/text()", namespaces=NS)) == "" for footer in footers)
        all_parts = [xml, *headers, *footers]
        ids = [id for part in all_parts for id in part.xpath("//wp:docPr/@id", namespaces=NS)]
        assert len(ids) == len(set(ids))


def test_long_and_rich_matrix_keep_editable_native_text_tables_images_and_exact_links():
    for kind in ("long", "matrix"):
        document, images = fixture(kind)
        with ZipFile(BytesIO(render_rich_docx(document, images))) as archive:
            xml = etree.fromstring(archive.read("word/document.xml"))
            text = "".join(xml.xpath("//w:t/text()", namespaces=NS))
            assert "FINAL_MARKER" in text
            if kind == "long":
                assert all(f"JOB_END_{i}" in text and f"Задача {i}.22" in text for i in range(1, 6))
            else:
                assert all(marker in text for marker in ("TOGGLE_CHILD", "CODE_END", "DEPTH_END", "IMAGE_CAPTION", "MATRIX_END"))
                assert xml.xpath("//w:gridSpan[@w:val='2']", namespaces=NS)
                assert xml.xpath("//w:vMerge[@w:val='restart']", namespaces=NS)
                assert "https://example.com/" + "long-path-" * 120 in archive.read("word/_rels/document.xml.rels").decode()
                assert next(iter(images.values())) in [archive.read(name) for name in archive.namelist() if name.startswith("word/media/")]


def test_support_role_requires_exact_bound_period_or_technology_fields():
    document, _ = fixture()
    raw = document.model_dump(by_alias=True)
    body = raw["regions"][2]["blocks"][0]["children"][0]
    body["content"] = [{"type": "fact_field", "bindingId": "period-binding", "recordId": "job", "fieldKey": "period:p:start",
        "text": "2020", "styles": {}, "syncedFactRevision": 1}]
    bound = RichDocumentV1.model_validate(raw)
    assert presentation(bound).blocks[body["id"]].role == "support"
    body["content"][0]["fieldKey"] = "employer"
    assert presentation(RichDocumentV1.model_validate(raw)).blocks[body["id"]].role == "body"
