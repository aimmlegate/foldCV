"""Native editable semantics for ordinary rich features and depth degradation."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree

from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.rendering.rich_docx import render_rich_docx

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def block(identifier, kind, text, props=None, children=None):
    return {"id": identifier, "revision": 1, "type": kind, "props": props or {}, "provenance": [], "children": children or [],
        "content": text if kind == "code" else None if kind == "divider" else [{"type": "text", "text": text, "styles": {}}]}


def document(blocks):
    return RichDocumentV1.model_validate({"schemaVersion": 1, "revision": 1, "regions": [
        {"id": role, "role": role, "revision": 1, "blocks": blocks if role == "main" else []}
        for role in ("header", "sidebar", "main")]})


def test_ordinary_export_has_real_headings_lists_restarts_shading_code_and_expanded_toggles():
    blocks = [block("heading", "heading", "Heading", {"level": 3}),
        block("list-a", "numbered_list", "Third item", {"start": 3}),
        block("list-b", "numbered_list", "Fourth item"),
        block("list-c", "numbered_list", "Restarted item", {"start": 1}),
        block("bullet", "bullet_list", "Bullet"),
        block("checked", "check_list", "Checked", {"checked": True}),
        block("unchecked", "check_list", "Unchecked", {"checked": False}),
        block("toggle", "toggle_list", "Toggle", children=[block("expanded", "paragraph", "Always exported")]),
        block("quote", "quote", "Quoted", {"alignment": "right", "backgroundColor": "#ddebf1"}),
        block("code", "code", 'a\tb\n    print("Ж")\n', {"language": "python", "backgroundColor": "#eeeeee"}),
        block("divider", "divider", "")]
    with ZipFile(BytesIO(render_rich_docx(document(blocks)))) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        paragraphs = {"".join(p.xpath(".//w:t/text()", namespaces=NS)): p for p in root.xpath("//w:p", namespaces=NS)}
        assert paragraphs["Heading"].xpath("w:pPr/w:pStyle[@w:val='Heading3']", namespaces=NS)
        assert paragraphs["Heading"].xpath("w:r/w:rPr/w:color[@w:val='000000']", namespaces=NS)
        ids = [paragraphs[text].xpath("w:pPr/w:numPr/w:numId/@w:val", namespaces=NS)[0] for text in ("Third item", "Fourth item", "Restarted item")]
        assert ids[0] == ids[1] and ids[2] != ids[0]
        numbering = etree.fromstring(archive.read("word/numbering.xml"))
        assert numbering.xpath(f"w:num[@w:numId='{ids[0]}']/w:lvlOverride/w:startOverride[@w:val='3']", namespaces=NS)
        assert numbering.xpath(f"w:num[@w:numId='{ids[2]}']/w:lvlOverride/w:startOverride[@w:val='1']", namespaces=NS)
        assert "☑ Checked" in paragraphs and "☐ Unchecked" in paragraphs and "Always exported" in paragraphs
        assert paragraphs["Quoted"].xpath("w:pPr/w:jc[@w:val='right']", namespaces=NS)
        assert paragraphs["Quoted"].xpath("w:pPr/w:shd[@w:fill='ddebf1']", namespaces=NS)
        assert root.xpath("//w:rFonts[@w:ascii='Courier New']", namespaces=NS)
        assert len(root.xpath("//w:br", namespaces=NS)) == 2 and len(root.xpath("//w:tab", namespaces=NS)) == 1
        assert root.xpath("//w:pBdr/w:bottom", namespaces=NS)


def test_depth_ten_keeps_text_order_and_uses_editable_markers_beyond_native_word_levels():
    nested = None
    for depth in range(10, -1, -1):
        nested = block(f"depth-{depth}", "numbered_list", f"Level {depth}", {"start": 5 if depth == 10 else None}, [nested] if nested else [])
    with ZipFile(BytesIO(render_rich_docx(document([nested])))) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        texts = ["".join(p.xpath(".//w:t/text()", namespaces=NS)) for p in root.xpath("//w:p", namespaces=NS)]
        actual = [text for text in texts if "Level" in text]
        assert actual[:9] == [f"Level {depth}" for depth in range(9)]
        assert actual[9:] == ["1. Level 9", "5. Level 10"]
        levels = root.xpath("//w:numPr/w:ilvl/@w:val", namespaces=NS)
        assert levels == [str(depth) for depth in range(9)]


def test_deep_lists_in_the_sidebar_bound_indent_without_losing_nested_text():
    nested = block("last", "bullet_list", "Deep text")
    for depth in range(10):
        nested = block(f"parent-{depth}", "bullet_list", f"Parent {depth}", children=[nested])
    rich = document([nested])
    rich.regions[1].blocks, rich.regions[2].blocks = rich.regions[2].blocks, []
    with ZipFile(BytesIO(render_rich_docx(rich))) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        paragraphs = [p for p in root.xpath("//w:p", namespaces=NS) if p.xpath(".//w:t", namespaces=NS)]
        assert len([p for p in paragraphs if "Parent" in "".join(p.xpath(".//w:t/text()", namespaces=NS))]) == 10
        assert "Deep text" in "".join(root.xpath("//w:t/text()", namespaces=NS))
        assert all(int(indent) <= (118 - 24) * 20 for indent in root.xpath("//w:ind/@w:left", namespaces=NS))
