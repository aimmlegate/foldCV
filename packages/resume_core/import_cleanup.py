"""Normalize source layout artifacts without changing extracted facts."""

from copy import deepcopy
import re


def normalized(text):
    return " ".join(text.split())


def clean_list_text(text):
    text = re.sub(r"(?m)^[ \t]*[•●▪◦][ \t]*(?:\r?\n|$)", "", text)
    return re.sub(r"(?m)^([ \t]*[•●▪◦])[ \t]+[-—][ \t]+", r"\1 ", text)


def merge_evidence(target, source):
    for link in source["provenance"]:
        if link["kind"] != "field_binding" and link not in target["provenance"]:
            target["provenance"].append(link)


def contact_key(text):
    text = normalized(text)
    email = re.fullmatch(r"(?:(?:e-?mail|эл\.\s*почта|почта)\s*:\s*)?([^\s@]+@[^\s@]+\.[^\s@]+)", text, re.I)
    if email:
        return "email:" + email[1]
    telegram = re.fullmatch(r"(?:telegram|телеграм)\s*:\s*@?([a-zA-Z0-9_]+)", text, re.I)
    if telegram:
        return "telegram:" + telegram[1]
    return text


def compact_contacts(blocks, metadata, sources):
    units = {(source.id, unit.id): unit for source in sources for unit in source.units}
    rows = {}
    for block in blocks:
        info = metadata.get(block["id"])
        if info is None or info.category != "contacts" or getattr(info, "model_block", False):
            continue
        links = [link for link in block["provenance"] if link["kind"] == "source"]
        if len(links) != 1 or len(links[0]["evidence"]) != 1:
            continue
        span = links[0]["evidence"][0]
        unit = units[(span["sourceId"], span["unitId"])]
        if (unit.location.kind != "page" or not unit.structure or not unit.structure.bounds
                or "\n" in unit.text.strip() or block["type"] != "paragraph"):
            continue
        key = (info.id.rsplit("_", 1)[0], span["sourceId"], unit.location.index)
        rows.setdefault(key, []).append((block, unit.structure.bounds))
    removed, aliases = set(), {}
    for entries in rows.values():
        matches = {}
        for left, box in entries:
            aligned = [(right, other) for right, other in entries if right is not left
                and abs((box[1] + box[3] - other[1] - other[3]) / 2) < min(box[3] - box[1], other[3] - other[1]) * .25]
            if len(aligned) == 1 and aligned[0][1][0] > box[2]:
                matches[left["id"]] = aligned[0][0]
        for left, _box in entries:
            right = matches.get(left["id"])
            if right is None or sum(value is right for value in matches.values()) != 1:
                continue
            if left["id"] in removed or right["id"] in matches:
                continue
            content = deepcopy(left["content"])
            if not content or content[-1]["type"] != "text":
                continue
            content[-1]["text"] = content[-1]["text"].rstrip() + ": "
            left["content"] = content + right["content"]
            left["provenance"].extend(link for link in right["provenance"] if link not in left["provenance"])
            value = contact_key("".join(span["text"] for span in right["content"]))
            aliases.setdefault(value, []).append(left)
            removed.add(right["id"])
    seen = {text: targets[0] for text, targets in aliases.items() if text and len(targets) == 1}
    result = []
    for block in blocks:
        if block["id"] in removed:
            continue
        info = metadata.get(block["id"])
        if info and getattr(info, "model_block", False):
            result.append(block)
            continue
        text = contact_key("".join(span["text"] for span in block["content"]))
        if info and info.category == "contacts" and block["type"] != "section" and text:
            if text in seen and seen[text] is not block:
                merge_evidence(seen[text], block)
                continue
            seen[text] = block
        result.append(block)
    return result
