"""Materialize the tool groups chosen by the import skill without classifying tools."""


def replaced_skill_outlines(draft):
    covered = {key for group in draft.technology_groups for key in group.source_keys}
    outlines = {}
    for block in draft.blocks:
        if block.category == "skills":
            outlines.setdefault(block.id.rsplit("_", 1)[0], set()).update(block.source_keys)
    return {key for key, source_keys in outlines.items() if source_keys and source_keys <= covered}


def grouped_technologies(groups, records, identity, evidence):
    technologies = [record for record in records if record["kind"] == "technology"]
    result = []
    for index, group in enumerate(groups):
        children = []
        summary, links = [], []
        spans = evidence(group.source_keys)
        for number, display in enumerate(group.technologies):
            key = [index, number]
            matches = [record for record in technologies if record["display"]["rawText"] == display]
            record = next((record for record in matches if record["jobId"] is None), matches[0] if matches else None)
            provenance = [{"kind": "source", "id": identity("group_source", key), "evidence": spans}] if spans else []
            if record:
                binding = identity("group_binding", key)
                content = [{"type": "fact_field", "bindingId": binding, "recordId": record["id"],
                    "fieldKey": "display", "text": display, "styles": {}, "syncedFactRevision": record["revision"]}]
                provenance.append({"kind": "field_binding", "id": binding, "recordId": record["id"], "fieldKey": "display"})
            else:
                content = [{"type": "text", "text": display, "styles": {}}]
            if group.region == "sidebar":
                children.append({"id": identity("group_entry", key), "revision": 1,
                    "type": "paragraph", "props": {}, "content": content, "children": [], "provenance": provenance})
            else:
                if summary:
                    summary.append({"type": "text", "text": ", ", "styles": {}})
                summary.extend(content)
                links.extend(link for link in provenance if link["kind"] == "field_binding")
        if summary:
            source = [{"kind": "source", "id": identity("group_source", index), "evidence": spans}] if spans else []
            children.append({"id": identity("group_list", index), "revision": 1, "type": "paragraph", "props": {},
                "content": summary, "children": [], "provenance": source + links})
        result.append((group.region, {"id": identity("technology_group", index), "revision": 1, "type": "section",
            "props": {"recordId": None, "presentation": "focus" if group.region == "sidebar" else "standard"},
            "content": [{"type": "text", "text": group.heading, "styles": {}}], "children": children, "provenance": []}))
    return result
