"""Apply template hierarchy to interpreted import records without rewriting text."""

from copy import deepcopy
import re

from .rendering.rich_template import require_rich_template
from .import_cleanup import merge_evidence, normalized
from .technologies import is_technical, resolve_technology


def split_profile(block, identity):
    chunks = []
    for span in block["content"]:
        profile = span["type"] == "fact_field" and span["recordId"] == "candidate" and span["fieldKey"] in {"name", "title"}
        if profile:
            chunks.append([span])
        elif span["type"] == "text" and chunks:
            whitespace = re.match(r"\s*", span["text"])[0]
            if whitespace:
                chunks[-1].append({**span, "text": whitespace})
            rest = span["text"][len(whitespace):]
            if rest:
                if not re.search(r"\w", rest):
                    chunks[-1].append({**span, "text": rest})
                else:
                    chunks.append([{**span, "text": rest}])
        else:
            chunks.append([span])
    if len(chunks) <= 1:
        return [block]
    result = []
    for index, content in enumerate(chunks):
        copy = deepcopy(block)
        copy["id"], copy["content"] = identity("identity_part", [block["id"], index]), content
        fields = {(span["recordId"], span["fieldKey"]) for span in content if span["type"] == "fact_field"}
        copy["provenance"] = [link for link in copy["provenance"] if link["kind"] != "field_binding"
            or (link["recordId"], link["fieldKey"]) in fields]
        result.append(copy)
    return result

def arrange_import(regions, metadata, records, identity):
    if not any(block.category for block in metadata.values()):
        return regions
    by_id = {record["id"]: record for record in records}
    candidate = by_id.get("candidate")
    header, extra, named = [], [], set()
    def model_block(block):
        return getattr(metadata.get(block["id"]), "model_block", False)

    explicit_identity = any(model_block(block) for block in regions["header"])
    for block in [part for block in regions["header"] for part in
            ([block] if model_block(block) else split_profile(block, identity))]:
        if model_block(block):
            if block["type"] in {"paragraph", "heading"}:
                name = candidate and normalized(authored_text_dict(block)) == normalized(candidate["name"]["rawText"])
                block.update(type="heading", props={"level": 1 if name else 2})
            header.append(block)
            continue
        text = authored_text_dict(block).strip()
        fields = [span for span in block["content"] if span["type"] == "fact_field" and span["recordId"] == "candidate"]
        key = next((key for key in ("name", "title") if candidate and text and key not in named and
            (normalized(text) == normalized(candidate[key]["rawText"]) or len(fields) == 1 and fields[0]["fieldKey"] == key
                and not any(re.search(r"\w", span["text"]) for span in block["content"] if span is not fields[0]))), None)
        if key:
            named.add(key)
            if not any(span["fieldKey"] == key for span in fields):
                binding = identity("profile_binding", key)
                suffix = re.search(r"\s*$", authored_text_dict(block))[0]
                block["content"] = [{"type": "fact_field", "bindingId": binding, "recordId": "candidate",
                    "fieldKey": key, "text": candidate[key]["rawText"], "styles": {}, "syncedFactRevision": 1}]
                if suffix:
                    block["content"].append({"type": "text", "text": suffix, "styles": {}})
                block["provenance"].append({"kind": "field_binding", "id": binding, "recordId": "candidate", "fieldKey": key})
            block.update(type="heading", props={"level": 1 if key == "name" else 2})
            header.append(block)
        else:
            block.update(type="paragraph", props={})
            extra.append(block)
    if candidate and not explicit_identity:
        for key in ("name", "title"):
            text = candidate[key]["rawText"]
            if key in named or not text.strip():
                continue
            binding = identity("profile_binding", key)
            header.append({"id": identity("profile", key), "revision": 1, "type": "heading",
                "props": {"level": 1 if key == "name" else 2}, "children": [],
                "content": [{"type": "fact_field", "bindingId": binding, "recordId": "candidate",
                    "fieldKey": key, "text": text, "styles": {}, "syncedFactRevision": 1}],
                "provenance": [{"kind": "field_binding", "id": binding, "recordId": "candidate", "fieldKey": key}]})
    regions["header"] = header if explicit_identity else sorted(header, key=lambda block: block["props"]["level"])
    for block in extra[:]:
        repeated = next((item for item in header if normalized(authored_text_dict(item)) == normalized(authored_text_dict(block))), None)
        if repeated:
            merge_evidence(repeated, block)
            extra.remove(block)
    groups, jobs, current_jobs = {}, {}, {}
    outline_owners = {}
    for region in ("sidebar", "main"):
        for block in regions[region]:
            info = metadata.get(block["id"])
            if info is None or info.category != "experience":
                continue
            owners = outline_owners.setdefault(info.id.rsplit("_", 1)[0], set())
            owners.update(link["recordId"] for link in block["provenance"] if link["kind"] == "citation"
                and by_id[link["recordId"]]["kind"] == "employment")
            if block["type"] == "section" and not any(link["kind"] == "source" for link in block["provenance"]):
                label = re.sub(r"\s*\((?:continued|continuation|продолжение)\)$", "", normalized(authored_text_dict(block)), flags=re.I)
                owners.update(record["id"] for record in records if record["kind"] == "employment"
                    and normalized(record["employer"]["rawText"]) == label)
    outline_owners = {key: next(iter(owners)) for key, owners in outline_owners.items() if len(owners) == 1}

    def group(key, region, category):
        if key not in groups:
            prefix = "import_profile" if category == "summary" else "import_experience" if category == "experience" else "outline"
            identifier = identity(prefix, key)
            groups[key] = (region, category, {"id": identifier, "revision": 1, "type": "section",
                "props": {"recordId": None}, "content": [], "children": [], "provenance": []})
        return groups[key][2]

    for region in ("sidebar", "main"):
        for block in regions[region]:
            info = metadata.get(block["id"])
            if info is None or info.category is None:
                group(("retained", region), region, "other")["children"].append(block)
                continue
            category = info.category
            outline = info.id.rsplit("_", 1)[0]
            parent = group((category, region) if category in {"experience", "summary"} else outline, region, category)
            fields = [span for span in block["content"] if span["type"] == "fact_field"]
            owners = {link["recordId"] for link in block["provenance"] if link["kind"] == "citation"
                and by_id[link["recordId"]]["kind"] == "employment"}
            employer_heading = category == "experience" and any(span["fieldKey"] == "employer"
                and by_id[span["recordId"]]["kind"] == "employment" for span in fields)
            if block["type"] == "section":
                generated_employer = category == "experience" and not any(link["kind"] == "source" for link in block["provenance"]) and any(
                    re.sub(r"\s*\((?:continued|continuation|продолжение)\)$", "", normalized(authored_text_dict(block)), flags=re.I)
                        == normalized(record["employer"]["rawText"])
                    for record in records if record["kind"] == "employment")
                if generated_employer:
                    continue
                if employer_heading:
                    block.update(type="heading", props={"level": 2})
                elif not parent["content"] and not parent["children"]:
                    parent["content"], parent["provenance"] = block["content"], block["provenance"]
                    continue
                elif category in {"experience", "summary"}:
                    if (not any(link["kind"] == "source" for link in block["provenance"])
                            or normalized(authored_text_dict(block)) == normalized(authored_text_dict(parent))):
                        merge_evidence(parent, block)
                        continue
                    block.update(type="heading", props={"level": 3})
            if category == "experience" and not owners and (current_jobs.get(outline) or outline_owners.get(outline)):
                owner = current_jobs.get(outline) or outline_owners[outline]
                owners.add(owner)
                block["provenance"].append({"kind": "working_owner", "id": identity("job_owner", block["id"]), "recordId": owner})
            if category == "experience":
                current_jobs[outline] = next(iter(owners)) if len(owners) == 1 else None
            if category == "experience" and len(owners) == 1:
                owner = next(iter(owners))
                text = authored_text_dict(block).strip()
                employer = by_id[owner]["employer"]["rawText"].strip()
                if employer and text.startswith(employer) and any(span["recordId"] == owner and span["fieldKey"] == "employer" for span in fields):
                    block.update(type="heading", props={"level": 2})
                if owner not in jobs:
                    jobs[owner] = {"id": identity("job_group", owner), "revision": 1, "type": "section",
                        "props": {"recordId": owner}, "content": [], "children": [], "provenance": []}
                    parent["children"].append(jobs[owner])
                jobs[owner]["children"].append(block)
            else:
                parent["children"].append(block)
            for span in fields:
                record = by_id[span["recordId"]]
                if record["kind"] == "technology" and record["jobId"] is not None:
                    span["styles"]["backgroundColor"] = "#EFEFEF"
    if extra:
        group("identity_details", "sidebar", "contacts")["children"].extend(extra)
    for job in jobs.values():
        headings = [block for block in job["children"] if block["type"] == "heading"]
        if len(headings) == 1:
            job["children"].remove(headings[0])
            job["children"].insert(0, headings[0])
    for _region, category, parent in groups.values():
        if category == "experience" and parent["children"] and not parent["content"]:
            russian = any(re.search(r"[а-яё]", authored_text_dict(block), re.I)
                for job in parent["children"] for block in [job, *job["children"]])
            parent["content"] = [{"type": "text", "text": "ОПЫТ РАБОТЫ" if russian else "EXPERIENCE", "styles": {}}]
    for key, (region, category, parent) in list(groups.items()):
        if category == "skills":
            entries = parent["children"]
            def focus_entry(block):
                fields = [span for span in block["content"] if span["type"] == "fact_field"]
                return (len(fields) == 1 and by_id[fields[0]["recordId"]]["kind"] == "technology"
                    and is_technical(by_id[fields[0]["recordId"]])
                    and authored_text_dict(block).strip() == fields[0]["text"].strip())
            focus = bool(entries) and all(focus_entry(block) for block in entries)
            if focus:
                parent["props"]["presentation"] = "focus"
            else:
                groups[key] = ("main", category, parent)
    for region in ("sidebar", "main"):
        order = {"summary": 0, "experience": 1, "skills": 2, "other": 3} if region == "main" else {
            "skills": 0, "education": 1, "languages": 2, "contacts": 3}
        regions[region] = [block for target, _category, block in sorted(groups.values(), key=lambda row: order.get(row[1], 4)) if target == region]
    if not any(block["props"].get("presentation") == "focus" for block in regions["sidebar"]):
        technologies = [record for record in records if record["kind"] == "technology" and is_technical(record)]
        general = [record for record in technologies if record["jobId"] is None]
        selected, seen = [], set()
        spec = require_rich_template().specification["focus"]
        count = spec["referenceLogoEntries"] + spec["referenceTextOnlyEntries"]
        pool = general + [r for r in technologies if r["jobId"] is not None]
        for record in pool:
            key = record["canonicalId"]["value"] or resolve_technology(record["display"]["rawText"]).canonical_id or record["display"]["rawText"].strip().casefold()
            if key and key not in seen:
                selected.append(record)
                seen.add(key)
            if len(selected) == count:
                break
        if selected:
            russian = any(re.search(r"[а-яё]", authored_text_dict(block), re.I) for _region, _category, block in groups.values())
            focus = {"id": identity("focus", "summary"), "revision": 1, "type": "section",
                "props": {"recordId": None, "presentation": "focus"}, "content": [{"type": "text",
                    "text": "ФОКУС" if russian else "FOCUS", "styles": {}}], "provenance": [], "children": []}
            for record in selected:
                binding = identity("focus_binding", record["id"])
                focus["children"].append({"id": identity("focus_entry", record["id"]), "revision": 1,
                    "type": "paragraph", "props": {}, "children": [], "content": [{"type": "fact_field",
                        "bindingId": binding, "recordId": record["id"], "fieldKey": "display",
                        "text": record["display"]["rawText"], "styles": {}, "syncedFactRevision": 1}],
                    "provenance": [{"kind": "field_binding", "id": binding, "recordId": record["id"], "fieldKey": "display"},
                        {"kind": "citation", "id": identity("focus_source", record["id"]), "recordId": record["id"],
                            "fieldKeys": ["display"], "evidence": record["evidence"]}]})
            regions["sidebar"].insert(0, focus)
    return regions


def authored_text_dict(block):
    return "".join(span["text"] for span in block["content"])
