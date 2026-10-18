"""Restore list structure and PDF line wrapping without changing source facts."""

from copy import deepcopy
import re

MARKER = re.compile(r"(?m)^[ \t]*(?:[•●▪◦\-—][ \t]+|(?P<number>[1-9]\d?)[.)][ \t]+)")
REDUNDANT_MARKERS = re.compile(r"(?m)^[ \t]*(?:(?:[•●▪◦\-—]|[1-9]\d?[.)])(?:[ \t]+|(?=$)))+")


def text(block):
    return "".join(span["text"] for span in block["content"])


def content_slice(content, start, end):
    result, cursor = [], 0
    for span in content:
        stop = cursor + len(span["text"])
        if cursor < end and stop > start:
            if span["type"] == "fact_field" and (start > cursor or end < stop):
                return None
            part = deepcopy(span)
            part["text"] = part["text"][max(0, start - cursor):min(stop, end) - cursor]
            result.append(part)
        cursor = stop
    return result


def soft_wraps(content):
    for span in content:
        if span["type"] == "text":
            span["text"] = re.sub(r"[ \t]*\r?\n[ \t]*(?!\r?\n)", " ", span["text"])
    if content and content[-1]["type"] == "text":
        content[-1]["text"] = content[-1]["text"].rstrip()
    if content and content[0]["type"] == "text":
        content[0]["text"] = content[0]["text"].lstrip()
    return content


def split_items(block, identity):
    if block["type"] not in {"paragraph", "bullet_list", "numbered_list"} or not isinstance(block["content"], list):
        return [block]
    if any(span["type"] not in {"text", "fact_field"} or span.get("styles", {}).get("code") for span in block["content"]):
        return [block]
    value = text(block)
    markers = list(MARKER.finditer(value))
    if not markers or markers[0].start() != 0 and len(markers) < 2:
        return [block]
    indents = {len(re.match(r"[ \t]*", marker[0])[0].expandtabs(4)) for marker in markers}
    if len(indents) > 1:
        return [block]
    boundaries = [0, *[m.start() for m in markers if m.start() > 0], len(value)]
    if block["children"] and len(boundaries) > 2:
        return [block]
    result = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        marker = next((m for m in markers if m.start() == start), None)
        cursor = 0
        for span in block["content"]:
            stop = cursor + len(span["text"])
            if marker and span["type"] == "fact_field" and cursor < marker.end() and stop > marker.start():
                return [block]
            cursor = stop
        content = content_slice(block["content"], marker.end() if marker else start, end)
        if content is None:
            return [block]
        item = deepcopy(block)
        item["id"] = identity("list_item", [block["id"], index]) if len(boundaries) > 2 else block["id"]
        if marker:
            item["type"] = "numbered_list" if marker["number"] else "bullet_list"
            item["props"] = {"start": int(marker["number"])} if marker["number"] else {}
            content = soft_wraps(content)
        item["content"] = content
        fields = {(s["recordId"], s["fieldKey"]) for s in content if s["type"] == "fact_field"}
        item["provenance"] = [link for link in item["provenance"] if link["kind"] != "field_binding"
            or (link["recordId"], link["fieldKey"]) in fields]
        result.append(item)
    return result


def format_model_item(block):
    value = text(block)
    content, cursor = [], 0
    fields, offset = [], 0
    for span in block["content"]:
        if span["type"] == "fact_field":
            fields.append((offset, offset + len(span["text"])))
        offset += len(span["text"])
    for marker in REDUNDANT_MARKERS.finditer(value):
        if any(start < marker.end() and end > marker.start() for start, end in fields):
            continue
        content.extend(content_slice(block["content"], cursor, marker.start()) or [])
        cursor = marker.end()
    content.extend(content_slice(block["content"], cursor, len(value)) or [])
    block["content"] = soft_wraps(content)
    first = MARKER.match(value)
    if first and first["number"] and not any(start < first.end() and end > first.start() for start, end in fields):
        block["type"], block["props"] = "numbered_list", {"start": int(first["number"])}
    return block


def format_import_lists(regions, sources, identity, *, model_items=frozenset(), model_blocks=frozenset()):
    units = {(source.id, unit.id): unit for source in sources for unit in source.units}

    def source_unit(block, last=False):
        spans = [span for link in block["provenance"] if link["kind"] == "source" for span in link["evidence"]]
        if not spans:
            return None
        span = spans[-1] if last else spans[0]
        return span["sourceId"], units[(span["sourceId"], span["unitId"])]

    def continuation(previous, block):
        if previous["type"] not in {"bullet_list", "numbered_list"} or block["type"] != "paragraph" or block["children"]:
            return False
        value = text(block).strip()
        if not value or MARKER.match(value) or re.match(r"^[^:.\n]{1,36}:\s*", value):
            return False
        a, b = source_unit(previous, True), source_unit(block)
        if not a or not b or a[0] != b[0]:
            return False
        left, right = a[1], b[1]
        if (left.location.kind != "page" or right.location.kind != "page" or left.location.index != right.location.index
            or not left.structure or not right.structure or not left.structure.bounds or not right.structure.bounds
            or left.structure.group is None or left.structure.group != right.structure.group or right.structure.bold):
            return False
        x, y = left.structure.bounds, right.structure.bounds
        height = min(x[3] - x[1], y[3] - y[1])
        return abs(x[0] - y[0]) <= 3 and 0 <= y[1] - x[3] <= max(5, height * .65)

    def visit(blocks):
        result = []
        for original in blocks:
            original["children"] = visit(original["children"])
            if original["id"] in model_items and original["type"] in {"paragraph", "bullet_list", "numbered_list"}:
                if original["type"] == "paragraph":
                    original["type"] = "bullet_list"
                result.append(format_model_item(original))
                continue
            if original["id"] in model_blocks:
                result.append(original)
                continue
            source = source_unit(original)
            structure = source[1].structure if source else None
            if (original["type"] == "paragraph" and structure and getattr(structure, "list_level", None) is not None
                and re.search(r"bullet|маркирован", getattr(structure, "style", None) or "", re.I)):
                original["type"] = "bullet_list"
            for block in split_items(original, identity):
                if result and result[-1]["id"] not in model_items | model_blocks and continuation(result[-1], block):
                    previous = result[-1]
                    previous["content"] = soft_wraps(previous["content"])
                    previous["content"].append({"type": "text", "text": " ", "styles": {}})
                    previous["content"].extend(soft_wraps(block["content"]))
                    previous["provenance"].extend(link for link in block["provenance"] if link not in previous["provenance"])
                else:
                    result.append(block)
        return result

    return {region: visit(blocks) for region, blocks in regions.items()}
