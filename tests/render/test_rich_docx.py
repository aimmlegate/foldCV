"""Rich DOCX export: marks, links, full embedded faces, keep-with-next rows and no stale render cache."""

from io import BytesIO
import json
from zipfile import ZipFile

from lxml import etree
from packages.resume_core.models.rich_document import RichDocumentV1
from packages.resume_core.models.rich_workspace import RichRenderSnapshot
from packages.resume_core.rendering.rich_docx import render_rich_docx, current_snapshot
from packages.resume_core.template_archive import archive_payload_v7
from tests.support.rich import without_sources
from tests.templates.storage_fixtures import workspace as papers


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


def test_rich_table_and_code_export_and_the_archive_carries_no_stale_render_cache():
    workspace = without_sources()
    raw = render_rich_docx(workspace.project.document)
    with ZipFile(BytesIO(raw)) as archive:
        assert b"<w:tbl>" in archive.read("word/document.xml")
    assert current_snapshot(workspace, {}) is None
    project, originals = papers()
    project.project.renders = [RichRenderSnapshot(id="stale", documentRevision=1, factsRevision=1, templateSha256="0" * 64,
        rendererVersion="old", rendererSha256="0" * 64, docxSha256="0" * 64, docxSize=10, docxPath="renders/stale.docx")]
    files = archive_payload_v7(project, originals, {})
    assert not any(path.startswith("renders/") for path in files)
    assert json.loads(files["workspace.json"])["project"]["renders"] == []


def test_section_bands_and_employer_headings_keep_the_next_body_but_long_text_can_split():
    document = initial_document("Long body " * 500)
    body = document.regions[2].blocks[0].model_dump(by_alias=True)
    heading = {"id": "employer", "type": "heading", "revision": 1, "props": {"level": 2},
        "children": [], "provenance": [], "content": [{"type": "text", "text": "Orion", "styles": {}}]}
    role = {"id": "role", "type": "paragraph", "revision": 1, "props": {}, "children": [], "provenance": [],
        "content": [{"type": "fact_field", "text": "Engineer", "styles": {}, "recordId": "job", "fieldKey": "role",
            "bindingId": "role-binding", "syncedFactRevision": 1}]}
    job = {"id": "job", "type": "section", "revision": 1, "props": {"recordId": "job"},
        "children": [heading, role, body], "content": [], "provenance": []}
    section = {"id": "experience", "type": "section", "revision": 1, "props": {"recordId": None},
        "children": [job], "provenance": [], "content": [{"type": "text", "text": "WORK", "styles": {}}]}
    value = document.model_dump(by_alias=True)
    value["regions"][2]["blocks"] = [section]
    with ZipFile(BytesIO(render_rich_docx(RichDocumentV1.model_validate(value)))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    def paragraph(text):
        return next(p for p in xml.xpath("//w:p", namespaces=ns)
            if "".join(p.xpath(".//w:t/text()", namespaces=ns)).startswith(text))
    assert paragraph("WORK").xpath("ancestor::w:tr[1]/w:trPr/w:cantSplit", namespaces=ns)
    assert paragraph("Orion").xpath("ancestor::w:tr[1]/w:trPr/w:cantSplit", namespaces=ns)
    separator = paragraph("WORK").getnext()
    assert separator.xpath("ancestor::w:tr[1]/w:trPr/w:cantSplit", namespaces=ns)
    assert paragraph("Engineer").xpath("ancestor::w:tr[1]/w:trPr/w:cantSplit", namespaces=ns)
    assert paragraph("Long body").xpath("w:pPr/w:keepNext[@w:val='0']", namespaces=ns)
    assert len(xml.xpath("//w:cantSplit", namespaces=ns)) == 1
    assert not paragraph("Long body").xpath("ancestor::w:tr[1]/w:trPr/w:cantSplit", namespaces=ns)
    first = xml.xpath("/w:document/w:body/w:tbl[2]/w:tr[2]/w:tc[3]/w:p[1]", namespaces=ns)[0]
    assert not first.xpath(".//w:t", namespaces=ns)
    assert first.xpath("w:pPr/w:spacing/@w:line", namespaces=ns) == ["1"]
    assert first.xpath("w:pPr/w:keepNext[@w:val='0']", namespaces=ns)


def test_job_header_does_not_restart_the_following_numbered_sequence():
    value = initial_document("unused").model_dump(by_alias=True)
    def block(identifier, kind, text, props):
        return {"id": identifier, "revision": 1, "type": kind, "props": props, "children": [],
            "provenance": [], "content": [{"type": "text", "text": text, "styles": {}}]}
    value["regions"][2]["blocks"] = [{"id": "job", "revision": 1, "type": "section", "props": {"recordId": "job"},
        "content": [], "provenance": [], "children": [block("company", "heading", "Orion", {"level": 2}),
            block("role", "paragraph", "Engineer", {}),
            block("first", "numbered_list", "First numbered task", {"start": 7}),
            block("second", "numbered_list", "Second numbered task", {})]}]
    with ZipFile(BytesIO(render_rich_docx(RichDocumentV1.model_validate(value)))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
        numbering = etree.fromstring(archive.read("word/numbering.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    tasks = xml.xpath("//w:p[w:pPr/w:numPr]", namespaces=ns)
    assert len(tasks) == 2
    identifiers = [p.xpath("w:pPr/w:numPr/w:numId/@w:val", namespaces=ns)[0] for p in tasks]
    assert identifiers[0] == identifiers[1]
    assert numbering.xpath("w:num[@w:numId=$id]/w:lvlOverride/w:startOverride/@w:val", namespaces=ns, id=identifiers[0]) == ["7"]
    assert all(not p.xpath("ancestor::w:tbl[w:tblPr/w:tblCaption[@w:val='Job header']]", namespaces=ns) for p in tasks)


def test_section_band_and_first_list_item_share_a_bounded_row_without_capturing_long_following_text():
    value = initial_document('Long trailing text ' * 400).model_dump(by_alias=True)
    body = value['regions'][2]['blocks'][0]
    item = {'id':'first-item','type':'bullet_list','revision':1,'props':{},'children':[],'provenance':[],
        'content':[{'type':'text','text':'First skill item.','styles':{}}]}
    value['regions'][2]['blocks']=[{'id':'skills','type':'section','revision':1,'props':{'recordId':None},
        'content':[{'type':'text','text':'SKILLS','styles':{}}],'provenance':[],'children':[item,body]}]
    with ZipFile(BytesIO(render_rich_docx(RichDocumentV1.model_validate(value)))) as archive:
        xml=etree.fromstring(archive.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    row=xml.xpath('//w:tbl[w:tblPr/w:tblCaption[@w:val="Section header"]]/w:tr',namespaces=ns)[0]
    assert row.xpath('w:trPr/w:cantSplit',namespaces=ns)
    assert ''.join(row.xpath('.//w:t/text()',namespaces=ns))=='SKILLSFirst skill item.'
    assert 'Long trailing text' not in ''.join(row.xpath('.//w:t/text()',namespaces=ns))
    assert xml.xpath('//w:p[.//w:t[contains(.,"Long trailing text")]]/w:pPr/w:keepNext[@w:val="0"]',namespaces=ns)
