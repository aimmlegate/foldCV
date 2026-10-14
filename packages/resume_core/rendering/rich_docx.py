"""Flowing editable DOCX from the authoritative rich tree."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from copy import deepcopy
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.table import _Cell
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Pt, RGBColor
from lxml import etree

from ..models.rich_document import Hyperlink, RichDocumentV1
from ..rich_limits import DOCX_BYTES
from ..rich_presentation import presentation, authored_text
from .rich_template import PACKAGE_SHA256, ROOT, require_rich_template
from .template import RenderFailure

RENDERER_VERSION = "1.1.0"
INITIAL_BLOCKS = {"paragraph", "heading", "section", "bullet_list", "numbered_list", "check_list", "toggle_list", "quote", "code", "divider", "table", "image"}


def renderer_sha256():
    sources = [Path(__file__), Path(__file__).with_name("worker.py"), ROOT / "packages/resume_core/rich_presentation.py", ROOT / "packages/resume_core/technologies.py"]
    return hashlib.sha256(b"".join(path.name.encode() + b"\0" + path.read_bytes() for path in sources)).hexdigest()


def validate_export(document: RichDocumentV1):
    if any(block.type not in INITIAL_BLOCKS for block in document.blocks()):
        raise RenderFailure("RICH_EXPORT_UNSUPPORTED")


def current_snapshot(workspace, artifacts):
    if workspace.project is None:
        return None
    validate_export(workspace.project.document)
    if workspace.project.template != require_rich_template().manifest:
        raise RenderFailure("RICH_TEMPLATE_MISMATCH")
    for snapshot in reversed(workspace.project.renders):
        blob = artifacts.get(snapshot.id)
        if (snapshot.document_revision == workspace.document_revision
            and snapshot.facts_revision == workspace.project.facts.revision
            and snapshot.template_sha256 == PACKAGE_SHA256
            and snapshot.renderer_version == RENDERER_VERSION
            and snapshot.renderer_sha256 == renderer_sha256()
            and blob is not None and len(blob) == snapshot.docx_size <= DOCX_BYTES
            and hashlib.sha256(blob).hexdigest() == snapshot.docx_sha256):
            return snapshot, blob
    return None


def element(tag, **attributes):
    node = OxmlElement(tag)
    for key, value in attributes.items():
        node.set(qn("w:" + key), str(value))
    return node


def fill(parent, color):
    if color != "default":
        parent.append(element("w:shd", fill=color.removeprefix("#"), val="clear"))


def embed_fonts(raw, spec):
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                  "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    relationship_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    type_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    with ZipFile(BytesIO(raw)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    table = etree.fromstring(parts["word/fontTable.xml"])
    relationships = etree.Element(f"{{{relationship_ns}}}Relationships")
    for index, face in enumerate(spec["fonts"]):
        name = face["wordFamily"]
        found = table.xpath("w:font[@w:name=$name]", namespaces=namespaces, name=name)
        font = found[0] if found else element("w:font", name=name)
        if not found:
            table.append(font)
        identifier = f"rIdFoldCV{index}"
        key = uuid.UUID(hex=face["sha256"][:32])
        mask = key.bytes[::-1]
        content = bytearray((ROOT / face["path"]).read_bytes())
        for byte in range(32):
            content[byte] ^= mask[byte % 16]
        path = f"fonts/{face['face']}.odttf"
        parts["word/" + path] = bytes(content)
        embedded = element("w:embedBold" if face["wordBold"] else "w:embedRegular", fontKey="{" + str(key).upper() + "}")
        embedded.set(qn("r:id"), identifier)
        font.append(embedded)
        etree.SubElement(relationships, f"{{{relationship_ns}}}Relationship", Id=identifier,
            Type=RELATIONSHIP_TYPE.FONT, Target=path)
    settings = etree.fromstring(parts["word/settings.xml"])
    settings.append(element("w:embedTrueTypeFonts"))
    settings.append(element("w:saveSubsetFonts", val="0"))
    types = etree.fromstring(parts["[Content_Types].xml"])
    etree.SubElement(types, f"{{{type_ns}}}Default", Extension="odttf",
        ContentType="application/vnd.openxmlformats-officedocument.obfuscatedFont")
    if not types.xpath("*[local-name()='Default'][@Extension='txt']"):
        etree.SubElement(types, f"{{{type_ns}}}Default", Extension="txt", ContentType="text/plain")
    parts["word/fonts/LICENSE.txt"] = (ROOT / spec["fontEmbedding"]["license"]).read_bytes()
    for path, tree in (("word/fontTable.xml", table), ("word/_rels/fontTable.xml.rels", relationships),
                       ("word/settings.xml", settings), ("[Content_Types].xml", types)):
        parts[path] = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts["docProps/core.xml"] = b'<?xml version="1.0"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"/>'
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path, blob in parts.items():
            archive.writestr(path, blob)
    return output.getvalue()


class Writer:
    def __init__(self, spec, images=None):
        self.spec = spec
        self.images = images or {}
        self.fonts = {face["face"]: face for face in spec["fonts"]}
        self.document = Document()
        self.numbering = self.document.part.numbering_part.element
        self.next_numbering = 6000
        self.next_drawing = 100000
        self.roles = {}
        for identifier, bullet in ((5000, True), (5001, False)):
            abstract = element("w:abstractNum", abstractNumId=identifier)
            abstract.append(element("w:multiLevelType", val="multilevel"))
            for level in range(9):
                item = element("w:lvl", ilvl=level)
                item.append(element("w:start", val=1))
                item.append(element("w:numFmt", val="bullet" if bullet else "decimal"))
                item.append(element("w:lvlText", val="•" if bullet else f"%{level + 1}."))
                item.append(element("w:lvlJc", val="left"))
                props = element("w:pPr")
                props.append(element("w:ind", left=720 + level * 360, hanging=360))
                item.append(props)
                run = element("w:rPr")
                run.append(element("w:rFonts", ascii="Helvetica" if bullet else "Source Sans Pro",
                    hAnsi="Helvetica" if bullet else "Source Sans Pro"))
                run.append(element("w:sz", val=28 if bullet else 20))
                item.append(run); abstract.append(item)
            self.numbering.append(abstract)
        self.bullet_numbering = self.new_numbering(5000)
        self.document.core_properties.author = ""
        self.document.core_properties.last_modified_by = ""
        section = self.document.sections[0]
        section.page_width, section.page_height = Pt(spec["page"]["width"]), Pt(spec["page"]["height"])
        section.top_margin, section.bottom_margin = Pt(14), Pt(72)
        section.left_margin = Pt(spec["regions"]["sidebar"]["x"])
        section.right_margin = Pt(spec["page"]["width"] - spec["regions"]["main"]["x"] - spec["regions"]["main"]["width"])
        normal = self.document.styles["Normal"]
        normal.font.name = self.fonts["light"]["wordFamily"]
        normal.font.size = Pt(10)
        normal.paragraph_format.space_after = Pt(0)
        normal.paragraph_format.line_spacing = Pt(12.57)
        normal.paragraph_format.keep_together = False
        normal.paragraph_format.keep_with_next = False

    def compact(self, paragraph, height=1):
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = Pt(height)
        paragraph.paragraph_format.keep_together = False
        paragraph.paragraph_format.keep_with_next = False

    def floating_image(self, paragraph, path, width, height, x, y, horizontal="page", vertical="page", label="Template image"):
        picture = paragraph.add_run().add_picture(str(path), width=Pt(width), height=Pt(height))
        inline = picture._inline
        anchor = OxmlElement("wp:anchor")
        for key, value in {"distT": "0", "distB": "0", "distL": "0", "distR": "0", "simplePos": "0", "relativeHeight": "0",
            "behindDoc": "0", "locked": "0", "layoutInCell": "1", "allowOverlap": "1"}.items():
            anchor.set(key, value)
        simple = OxmlElement("wp:simplePos"); simple.set("x", "0"); simple.set("y", "0"); anchor.append(simple)
        for axis, reference, offset in (("H", horizontal, x), ("V", vertical, y)):
            position = OxmlElement("wp:position" + axis); position.set("relativeFrom", reference)
            point = OxmlElement("wp:posOffset"); point.text = str(round(offset * 12700)); position.append(point); anchor.append(position)
        for child in inline:
            if child.tag in {qn("wp:extent"), qn("wp:effectExtent")}:
                anchor.append(deepcopy(child))
        anchor.append(OxmlElement("wp:wrapNone"))
        for child in inline:
            if child.tag not in {qn("wp:extent"), qn("wp:effectExtent")}:
                copy = deepcopy(child)
                if copy.tag == qn("wp:docPr"):
                    copy.set("id", str(self.next_drawing)); self.next_drawing += 1; copy.set("descr", label)
                anchor.append(copy)
        inline.getparent().replace(inline, anchor)

    def brand(self):
        from PIL import Image
        spec = self.spec["header"]["brand"]
        section = self.document.sections[0]
        section.different_first_page_header_footer = True
        section.header_distance = Pt(0)
        paragraph = section.first_page_header.paragraphs[0]; self.compact(paragraph)
        with Image.open(ROOT / spec["path"]) as image:
            ratio = min(spec["boxWidth"] / image.width, spec["boxHeight"] / image.height)
            width, height = image.width * ratio, image.height * ratio
        self.floating_image(paragraph, ROOT / spec["path"], width, height,
            spec["x"] + (spec["boxWidth"] - width) / 2, spec["top"] + (spec["boxHeight"] - height) / 2, label="FoldCV brand")

    def clear_cell(self, cell):
        margins = element("w:tcMar")
        for side in ("top", "start", "bottom", "end"):
            margins.append(element("w:" + side, w="0", type="dxa"))
        cell._tc.get_or_add_tcPr().append(margins)
        for paragraph in cell.paragraphs:
            paragraph._p.getparent().remove(paragraph._p)

    def run(self, paragraph, text, styles, face, size):
        if styles.bold:
            face = "bold"
        font = self.fonts[face]
        run = paragraph.add_run(text)
        run.font.name = "Courier New" if styles.code else font["wordFamily"]
        run.font.size = Pt(size)
        run.bold, run.italic, run.underline = font["wordBold"], styles.italic, styles.underline
        run.font.strike = styles.strike
        fonts = run._r.get_or_add_rPr().rFonts
        for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
            fonts.set(qn("w:" + attribute), run.font.name)
        run.font.color.rgb = RGBColor.from_string(styles.text_color[1:] if styles.text_color != "default" else "000000")
        fill(run._r.get_or_add_rPr(), styles.background_color)
        return run

    def inline(self, paragraph, content, face, size, text_color="default"):
        def effective(styles):
            return styles.model_copy(update={"text_color": text_color}) if styles.text_color == "default" else styles
        for span in content:
            if isinstance(span, Hyperlink):
                link = element("w:hyperlink")
                link.set(qn("r:id"), paragraph.part.relate_to(span.href, RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
                for child in span.content:
                    run = self.run(paragraph, child.text, effective(child.styles), face, size)
                    link.append(run._r)
                paragraph._p.append(link)
            else:
                self.run(paragraph, span.text, effective(span.styles), face, size)

    def new_numbering(self, abstract_id, start=1, level=0):
        identifier = self.next_numbering; self.next_numbering += 1
        node = element("w:num", numId=identifier)
        node.append(element("w:abstractNumId", val=abstract_id))
        override = element("w:lvlOverride", ilvl=level)
        override.append(element("w:startOverride", val=start))
        node.append(override); self.numbering.append(node)
        return identifier

    def blocks(self, container, blocks, width, region, depth=0, focus=False):
        sequence = {"numbering": None, "index": 0, "previous": None}
        for block in blocks:
            self.block(container, block, width, region, depth, focus, sequence)

    def block(self, container, block, width, region, depth=0, focus=False, sequence=None):
        view = self.roles.get(block.id)
        role = view.role if view else "body"
        if block.type == "section" and not authored_text(block).strip():
            self.blocks(container, block.children, width, region, depth, block.props.presentation == "focus")
            self.section_spacing(container, block, region)
            return
        if isinstance(block.content, list) and not authored_text(block) and any(link.kind == "field_binding" for link in block.provenance) and not block.children:
            return
        if block.type == "section" and region == "main" and role == "section_heading":
            self.section_band(container, block)
            self.blocks(container, block.children, width, region, depth)
            self.section_spacing(container, block, region)
            return
        if block.type == "table":
            indent = min(depth * 18, max(0, width - 24))
            self.table(container, block, max(24, width - indent), region, indent)
            self.blocks(container, block.children, width, region, depth + 1)
            return
        paragraph = container.add_paragraph()
        self.compact(paragraph, self.spec["typography"]["body"]["lineHeight"])
        base_left = -self.spec["sectionBand"]["leftFromMain"] if region == "main" else 0
        paragraph.paragraph_format.left_indent = Pt(base_left)
        if region == "main":
            paragraph.paragraph_format.right_indent = Pt(self.spec["sectionBand"]["widthBeyondMain"] + self.spec["sectionBand"]["leftFromMain"])
        paragraph.paragraph_format.keep_together = False
        paragraph.paragraph_format.keep_with_next = False
        # Word's character wrapping preserves long tokens rather than inserting characters.
        paragraph._p.get_or_add_pPr().append(element("w:wordWrap", val="0"))
        paragraph.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[getattr(block.props, "alignment", "left")]
        fill(paragraph._p.get_or_add_pPr(), getattr(block.props, "background_color", "default"))
        if depth:
            paragraph.paragraph_format.left_indent = Pt(base_left + min(min(depth, 12) * 18, max(0, width - 24)))
        state = sequence if sequence is not None else {"numbering": None, "index": 0, "previous": None}
        numbered = block.type == "numbered_list"
        if numbered:
            start = block.props.start
            if state["previous"] != "numbered_list" or start is not None:
                state["numbering"] = self.new_numbering(5001, start or 1, min(depth, 8))
                state["index"] = start or 1
            else:
                state["index"] += 1
        else:
            state["numbering"] = None
        state["previous"] = block.type
        if block.type in {"bullet_list", "numbered_list"} and depth <= 8:
            numbering = element("w:numPr")
            numbering.append(element("w:ilvl", val=depth))
            numbering.append(element("w:numId", val=state["numbering"] if numbered else self.bullet_numbering))
            paragraph._p.get_or_add_pPr().append(numbering)
            indent = min(36 + depth * 18, max(18, width - 24))
            paragraph.paragraph_format.left_indent = Pt(base_left + indent)
            paragraph.paragraph_format.first_line_indent = Pt(-18)
        elif block.type in {"bullet_list", "numbered_list", "check_list", "toggle_list"}:
            from ..models.rich_document import InlineStyles
            marker = f"{state['index']}. " if numbered else "☑ " if block.type == "check_list" and block.props.checked else "☐ " if block.type == "check_list" else "▾ " if block.type == "toggle_list" else "• "
            self.run(paragraph, marker, InlineStyles(), "regular", 10)
            paragraph.paragraph_format.left_indent = Pt(base_left + min(36 + min(depth, 12) * 18, max(18, width - 24)))
            paragraph.paragraph_format.first_line_indent = Pt(-18)
        face, size = "light", 10
        if block.type == "heading":
            paragraph.style = self.document.styles[f"Heading {block.props.level}"]
            paragraph.paragraph_format.keep_with_next = False
            paragraph.paragraph_format.keep_together = False
        if region == "header" and block.type == "heading" and block.props.level in {1, 2}:
            face, size = ("black", 18) if block.type == "heading" and block.props.level == 1 else ("semibold", 16)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.line_spacing = Pt(20.7 if block.props.level == 1 else 18.4)
            paragraph.paragraph_format.space_after = Pt(5.3 if block.props.level == 1 else 0)
        elif block.type == "heading":
            face, size = ("bold", 14) if block.props.level == 1 else ("semibold", 12 if block.props.level == 2 else 10)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.line_spacing = Pt(19 if block.props.level == 1 else 15.08 if block.props.level == 2 else 12.57)
        elif block.type == "section":
            face, size = "bold", 14
            paragraph.paragraph_format.line_spacing = Pt(19)
        elif role == "support":
            face = "regular"
        elif focus:
            face, size = "semibold", 10
            paragraph.paragraph_format.left_indent = Pt(base_left + self.spec["focus"]["textFromSidebar"])
            paragraph.paragraph_format.space_after = Pt(25.43)
            if view and view.logo and (ROOT / view.logo).is_file():
                from PIL import Image
                box = self.spec["focus"]["logoBox"]
                with Image.open(ROOT / view.logo) as image:
                    ratio = min(box["width"] / image.width, box["height"] / image.height)
                    image_width, image_height = image.width * ratio, image.height * ratio
                self.floating_image(paragraph, ROOT / view.logo, image_width, image_height,
                    box["xFromSidebar"] - self.spec["focus"]["textFromSidebar"] + (box["width"] - image_width) / 2,
                    (box["height"] - image_height) / 2, horizontal="character", vertical="paragraph", label="Focus technology logo")
        if block.type == "quote":
            paragraph.paragraph_format.left_indent = Pt(base_left + min(12 + min(depth, 12) * 18, max(0, width - 24)))
            border = element("w:pBdr"); border.append(element("w:left", val="single", sz=6, color="888888", space=4))
            paragraph._p.get_or_add_pPr().append(border)
        if block.type == "divider":
            border = element("w:pBdr"); border.append(element("w:bottom", val="single", sz=6, color="888888"))
            paragraph._p.get_or_add_pPr().append(border)
        elif block.type == "image":
            # Exact body line spacing clips a tall inline picture in Word-compatible readers.
            paragraph.paragraph_format.line_spacing = 1.0
            data = self.images.get(block.props.asset_id)
            if data is None:
                raise RenderFailure("RICH_IMAGE_MISSING")
            available = max(24, width - min(depth * 18, max(0, width - 24)))
            scale = min(1, available / block.props.width, 620 / block.props.height)
            picture = paragraph.add_run().add_picture(BytesIO(data), width=Pt(block.props.width * scale), height=Pt(block.props.height * scale))
            picture._inline.docPr.set("id", str(self.next_drawing)); self.next_drawing += 1
            picture._inline.docPr.set("descr", block.props.alt)
            if block.props.caption:
                paragraph.add_run().add_break()
                self.inline(paragraph, block.props.caption, "light", 10)
        elif block.type == "code":
            from ..models.rich_document import InlineStyles
            self.run(paragraph, block.content, InlineStyles(code=True), "regular", 10)
        else:
            self.inline(paragraph, block.content, face, size, getattr(block.props, "text_color", "default"))
        self.blocks(container, block.children, width, region, depth if block.type == "section" else depth + 1,
            block.type == "section" and block.props.presentation == "focus")
        if block.type == "section":
            self.section_spacing(container, block, region)

    def section_spacing(self, container, block, region):
        if container.paragraphs:
            if block.props.presentation == "focus":
                paragraph = container.paragraphs[-1]
                paragraph.paragraph_format.space_after = (paragraph.paragraph_format.space_after or Pt(0)) + Pt(self.spec["spacing"]["sidebarItemAfter"])
                return
            spacing = self.spec["spacing"]["sidebarSectionAfter"] if region == "sidebar" else self.spec["spacing"]["profileAfter"] if block.id == "profile" else self.spec["spacing"]["jobAfter"] if block.props.record_id else None
            if spacing is not None:
                paragraph = container.paragraphs[-1]
                current = paragraph.paragraph_format.space_after or Pt(0)
                paragraph.paragraph_format.space_after = max(current, Pt(spacing))

    def section_band(self, container, block):
        from docx.enum.table import WD_ROW_HEIGHT_RULE
        band = self.spec["sectionBand"]
        width = self.spec["regions"]["main"]["width"] + band["widthBeyondMain"]
        table = container.add_table(rows=1, cols=1); table.autofit = False
        table.columns[0].width = Pt(width)
        preferred = table._tbl.tblPr.find(qn("w:tblW")); preferred.set(qn("w:w"), str(round(width * 20))); preferred.set(qn("w:type"), "dxa")
        table.rows[0].height, table.rows[0].height_rule = Pt(band["height"]), WD_ROW_HEIGHT_RULE.AT_LEAST
        cell = table.cell(0, 0); cell.width = Pt(width); self.clear_cell(cell)
        margins = cell._tc.get_or_add_tcPr().find(qn("w:tcMar"))
        for side in ("start", "end"):
            margins.find(qn("w:" + side)).set(qn("w:w"), "100")
        fill(cell._tc.get_or_add_tcPr(), block.props.background_color if block.props.background_color != "default" else band["background"])
        paragraph = cell.add_paragraph(); paragraph.style = self.document.styles["Heading 1"]; self.compact(paragraph, 19)
        paragraph.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[block.props.alignment]
        self.inline(paragraph, block.content, "bold", 14, block.props.text_color)
        separator = container.add_paragraph(); self.compact(separator)
        gap = self.spec["spacing"]["barToFirstJob"] if block.id == "experience" else self.spec["spacing"]["earlyCareerBarAfter"] if block.id == "early-career" else self.spec["spacing"]["skillBarAfter"]
        separator.paragraph_format.space_after = Pt(gap - 1)

    def table(self, container, block, width, region=None, indent=0):
        if region == "main":
            wrapper_width = self.spec["regions"]["main"]["width"] + self.spec["sectionBand"]["widthBeyondMain"]
            wrapper = container.add_table(rows=1, cols=1); wrapper.autofit = False
            wrapper.columns[0].width = Pt(wrapper_width)
            preferred = wrapper._tbl.tblPr.find(qn("w:tblW")); preferred.set(qn("w:w"), str(round(wrapper_width * 20))); preferred.set(qn("w:type"), "dxa")
            cell = wrapper.cell(0, 0); cell.width = Pt(wrapper_width); self.clear_cell(cell)
            margins = cell._tc.get_or_add_tcPr().find(qn("w:tcMar"))
            band = self.spec["sectionBand"]
            margins.find(qn("w:start")).set(qn("w:w"), str(round((-band["leftFromMain"] + indent) * 20)))
            margins.find(qn("w:end")).set(qn("w:w"), str(round((band["widthBeyondMain"] + band["leftFromMain"]) * 20)))
            self.table(cell, block, width)
            self.compact(container.add_paragraph())
            return
        content = block.content
        columns = len(content.column_widths)
        preferred = [value or 80 for value in content.column_widths]
        widths = [width * value / sum(preferred) for value in preferred]
        table = container.add_table(rows=0, cols=columns)
        table.autofit = False
        table.alignment = {"left": WD_TABLE_ALIGNMENT.LEFT, "center": WD_TABLE_ALIGNMENT.CENTER,
            "right": WD_TABLE_ALIGNMENT.RIGHT, "justify": WD_TABLE_ALIGNMENT.LEFT}[block.props.alignment]
        table._tbl.tblPr.find(qn("w:tblW")).set(qn("w:w"), str(round(width * 20)))
        table._tbl.tblPr.find(qn("w:tblW")).set(qn("w:type"), "dxa")
        for index, value in enumerate(widths):
            table.columns[index].width = Pt(value)
        active = {}
        for row_index, row in enumerate(content.rows):
            active = {column: value for column, value in active.items() if value[0] > row_index}
            tr = element("w:tr")
            table._tbl.append(tr)
            if row_index < content.header_rows:
                props = element("w:trPr"); props.append(element("w:tblHeader")); tr.append(props)
            entries = [(column, source, True) for column, (_, source) in active.items()]
            column = 0
            for source in row.cells:
                while column in active:
                    column += active[column][1].colspan
                if column + source.colspan > columns or row_index + source.rowspan > len(content.rows):
                    raise RenderFailure("RICH_TABLE_INVALID")
                entries.append((column, source, False))
                if source.rowspan > 1:
                    active[column] = (row_index + source.rowspan, source)
                column += source.colspan
            for column, source, continuation in sorted(entries, key=lambda item: item[0]):
                tc = element("w:tc"); tr.append(tc)
                cell = _Cell(tc, table)
                cell.width = Pt(sum(widths[column:column + source.colspan]))
                if source.colspan > 1:
                    tc.get_or_add_tcPr().append(element("w:gridSpan", val=source.colspan))
                if source.rowspan > 1:
                    tc.get_or_add_tcPr().append(element("w:vMerge") if continuation else element("w:vMerge", val="restart"))
                fill(cell._tc.get_or_add_tcPr(), source.background_color if source.background_color != "default" else block.props.background_color)
                paragraph = cell.add_paragraph()
                paragraph.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[source.alignment]
                paragraph.paragraph_format.keep_together = False
                paragraph.paragraph_format.keep_with_next = False
                paragraph._p.get_or_add_pPr().append(element("w:wordWrap", val="0"))
                if not continuation:
                    self.inline(paragraph, source.content, "semibold" if row_index < content.header_rows or column < content.header_cols else "light", 10, block.props.text_color)
        # Word requires a paragraph after a nested table; it also separates adjacent tables.
        self.compact(container.add_paragraph())

    def render(self, document, facts=None):
        spec = self.spec
        self.roles = presentation(document, facts).blocks
        self.brand()
        from docx.enum.table import WD_ROW_HEIGHT_RULE
        header = self.document.add_table(rows=1, cols=1); header.autofit = False
        header.columns[0].width = Pt(spec["header"]["textPreferredWidth"])
        header._tbl.tblPr.find(qn("w:tblW")).set(qn("w:w"), str(round(spec["header"]["textPreferredWidth"] * 20)))
        header._tbl.tblPr.find(qn("w:tblW")).set(qn("w:type"), "dxa")
        header._tbl.tblPr.append(element("w:tblInd", w=round((spec["header"]["name"]["x"] - spec["regions"]["sidebar"]["x"]) * 20), type="dxa"))
        header.rows[0].height, header.rows[0].height_rule = Pt(44.4), WD_ROW_HEIGHT_RULE.AT_LEAST
        cell = header.cell(0, 0); cell.width = Pt(spec["header"]["textPreferredWidth"]); self.clear_cell(cell)
        self.blocks(cell, document.regions[0].blocks, spec["header"]["textPreferredWidth"], "header")
        if not cell.paragraphs:
            self.compact(cell.add_paragraph())
        divider = self.document.add_paragraph(); self.compact(divider)
        divider.paragraph_format.space_before, divider.paragraph_format.space_after = Pt(19.85), Pt(5.75)
        divider.paragraph_format.left_indent = Pt(spec["header"]["divider"]["x1"] - spec["regions"]["sidebar"]["x"])
        divider.paragraph_format.right_indent = Pt(spec["regions"]["main"]["x"] + spec["regions"]["main"]["width"] - spec["header"]["divider"]["x2"] - .75)
        border = element("w:pBdr"); border.append(element("w:bottom", val="single", sz=5, color="888888", space=0)); divider._p.get_or_add_pPr().append(border)
        table = self.document.add_table(rows=2, cols=3)
        table.autofit = False
        widths = [spec["regions"]["sidebar"]["width"], spec["regions"]["gap"] + spec["sectionBand"]["leftFromMain"],
            spec["regions"]["main"]["width"] + spec["sectionBand"]["widthBeyondMain"]]
        table._tbl.tblPr.find(qn("w:tblW")).set(qn("w:w"), str(round(sum(widths) * 20)))
        table._tbl.tblPr.find(qn("w:tblW")).set(qn("w:type"), "dxa")
        for index, width in enumerate(widths):
            table.columns[index].width = Pt(width)
            for row in (0, 1):
                cell = table.cell(row, index); cell.width = Pt(width); self.clear_cell(cell)
            self.compact(table.cell(0, index).add_paragraph())
            if index == 1:
                self.compact(table.cell(1, index).add_paragraph())
        table.rows[0].height, table.rows[0].height_rule = Pt(10), WD_ROW_HEIGHT_RULE.EXACTLY
        table.rows[0]._tr.get_or_add_trPr().append(element("w:tblHeader"))
        for region, index in zip(document.regions[1:], (0, 2)):
            cell = table.cell(1, index)
            self.blocks(cell, region.blocks, spec["regions"]["sidebar"]["width"] if index == 0 else spec["regions"]["main"]["width"], region.role)
            if not cell.paragraphs:
                self.compact(cell.add_paragraph())
        from ..models.rich_document import InlineStyles
        section = self.document.sections[0]
        section.footer_distance = Pt(26.75)
        for part in (section.footer, section.first_page_footer):
            footer = part.paragraphs[0]
            footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
            footer.paragraph_format.right_indent = Pt(2 * ((spec["regions"]["sidebar"]["x"] + spec["regions"]["main"]["x"] + spec["regions"]["main"]["width"]) / 2 - spec["footer"]["centerX"]))
            self.run(footer, spec["footer"]["text"], InlineStyles(), "light", 12)
        output = BytesIO()
        self.document.save(output)
        return embed_fonts(output.getvalue(), spec)


def render_rich_docx(document: RichDocumentV1, images=None, facts=None):
    validate_export(document)
    content = Writer(require_rich_template().specification, images).render(document, facts)
    if len(content) > DOCX_BYTES:
        raise RenderFailure("RENDER_OUTPUT_LIMIT")
    return content
