"""The python-docx helpers the captured DOCX writer uses: elements, shading and three paragraph and cell methods."""

from __future__ import annotations

from copy import deepcopy

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


def element(tag, **attributes):
    node = OxmlElement(tag)
    for key, value in attributes.items():
        node.set(qn("w:" + key), str(value))
    return node


def fill(parent, color):
    if color != "default":
        parent.append(element("w:shd", fill=color.removeprefix("#"), val="clear"))


class Writer:
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

    def clear_cell(self, cell):
        margins = element("w:tcMar")
        for side in ("top", "start", "bottom", "end"):
            margins.append(element("w:" + side, w="0", type="dxa"))
        cell._tc.get_or_add_tcPr().append(margins)
        for paragraph in cell.paragraphs:
            paragraph._p.getparent().remove(paragraph._p)
