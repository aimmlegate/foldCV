"""Keep Word paragraph properties as optional source cues."""

import re

from packages.resume_core.models.contracts import SourceStructure

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def value(parent, path):
    node = parent.find(path) if parent is not None else None
    return node.get(W + "val") if node is not None else None


def number(raw, minimum, maximum):
    try:
        parsed = int(raw)
        return parsed if minimum <= parsed <= maximum else None
    except (TypeError, ValueError):
        return None


def enabled(node):
    return node.get(W + "val", "true").lower() not in {"0", "false", "off"}


class ParagraphStyles:
    def __init__(self, root=None):
        self.styles = {node.get(W + "styleId"): node for node in root.findall(W + "style")} if root is not None else {}
        self.defaults = root.find(W + "docDefaults/" + W + "rPrDefault/" + W + "rPr") if root is not None else None

    def hidden(self, run, paragraph):
        properties = [run.find(W + "rPr")]
        for style_id in (value(run.find(W + "rPr"), W + "rStyle"),
                         value(paragraph.find(W + "pPr"), W + "pStyle") or next(
                             (key for key, node in self.styles.items() if node.get(W + "type") == "paragraph"
                              and node.get(W + "default") in {"1", "true"}), None)):
            seen = set()
            while style_id in self.styles and style_id not in seen and len(seen) < 32:
                seen.add(style_id)
                style = self.styles[style_id]
                properties.append(style.find(W + "rPr"))
                style_id = value(style, W + "basedOn")
        properties.append(self.defaults)
        return next((enabled(node) for prop in properties if prop is not None
                     and (node := prop.find(W + "vanish")) is not None), False)

    def hints(self, paragraph, part):
        direct = paragraph.find(W + "pPr")
        style_id = value(direct, W + "pStyle")
        chain, seen, current = [], set(), style_id
        while current in self.styles and current not in seen and len(chain) < 32:
            seen.add(current)
            style = self.styles[current]
            chain.append(style)
            current = value(style, W + "basedOn")
        properties = [direct, *(node.find(W + "pPr") for node in chain)]

        def inherited(path):
            return next((found for prop in properties if (found := value(prop, path)) is not None), None)

        raw_outline = inherited(W + "outlineLvl")
        outline = number(raw_outline, 0, 8)
        standard_heading = re.fullmatch(r"Heading([1-9])", style_id or "", re.I)
        level = (outline + 1 if outline is not None else
                 int(standard_heading[1]) if standard_heading and raw_outline is None else None)
        num_id = inherited(W + "numPr/" + W + "numId")
        list_level = number(inherited(W + "numPr/" + W + "ilvl"), 0, 8) if num_id not in {None, "0"} else None
        if list_level is None and num_id not in {None, "0"}:
            list_level = 0
        style_name = value(chain[0], W + "name") if chain else style_id
        inherited_bold = next((b for style in chain if (b := style.find(W + "rPr/" + W + "b")) is not None), None)
        bold = set()
        for run in paragraph.findall(".//" + W + "r"):
            if not any((t.text or "").strip() for t in run.findall(W + "t")):
                continue
            explicit = run.find(W + "rPr/" + W + "b")
            node = explicit if explicit is not None else inherited_bold
            bold.add(enabled(node) if node is not None else False)
        return SourceStructure(part=part, style=(style_name or "")[:120] or None,
            heading_level=level, list_level=list_level,
            bold=next(iter(bold)) if len(bold) == 1 else None)
