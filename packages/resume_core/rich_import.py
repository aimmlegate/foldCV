"""Keep the first document literal while extracting editable working facts."""

import re

from .gui_drafting import draft_skeleton
from .models.rich_workspace import ProjectV5
from .rendering.rich_template import require_rich_template
from .rich_assembly import assemble_facts, identity


def literal_content(text, source, unit, records):
    matches = []
    for record in records:
        evidence = [span for span in record["evidence"]
            if span["sourceId"] == source.id and span["unitId"] == unit.id]
        if not evidence:
            continue
        fields = list(record.items())
        for period in record.get("periods", []):
            fields.extend((f"period:{period['id']}:{key}", period[key]) for key in
                ("start", "present") if period["present"]["value"] is True)
            if period["present"]["value"] is not True:
                fields.extend((f"period:{period['id']}:{key}", period[key]) for key in ("start", "end"))
        for key, value in fields:
            if not isinstance(value, dict) or "rawText" not in value or key == "canonicalId":
                continue
            raw = value.get("rawText", "")
            if not raw or not any(raw in span["text"] for span in evidence):
                continue
            found = list(re.finditer(r"(?<!\w)" + re.escape(raw) + r"(?!\w)", text))
            if len(found) == 1:
                matches.append((found[0].start(), found[0].end(), record["id"], key))
    # Ambiguous or competing fields remain literal, with source provenance.
    matches = [item for item in matches if not any(item != other and item[0] < other[1] and other[0] < item[1] for other in matches)]
    content, cursor = [], 0
    for start, end, record_id, key in sorted(matches):
        if start > cursor:
            content.append({"type": "text", "text": text[cursor:start], "styles": {}})
        content.append({"type": "fact_field", "bindingId": identity("binding"), "recordId": record_id,
            "fieldKey": key, "text": text[start:end], "styles": {}, "syncedFactRevision": 1})
        cursor = end
    if cursor < len(text) or not content:
        content.append({"type": "text", "text": text[cursor:], "styles": {}})
    return content


def assemble_import(workspace, normalized):
    records, evidence_records, *_ = assemble_facts(normalized, draft_skeleton(normalized).candidate.details)
    for record in records:
        for period in record.get("periods", []):
            if period["present"]["value"] is True:
                period["present"]["rawText"] = period["end"]["rawText"]
    blocks = []
    for source in normalized.sources:
        for unit in sorted(source.units, key=lambda item: item.order):
            evidence = {"sourceId": source.id, "sourceRevision": source.revision, "unitId": unit.id,
                "unitRevision": unit.revision, "text": unit.text}
            blocks.append({"id": identity("source-literal"), "revision": 1, "type": "paragraph", "props": {},
                "content": literal_content(unit.text, source, unit, records), "children": [],
                "provenance": [{"kind": "source", "id": identity("source-link"), "evidence": [evidence]}]})
    return ProjectV5.model_validate({"schemaVersion": 5, "projectId": workspace.project_id,
        "revision": workspace.project_revision + 1, "createdAt": workspace.created_at,
        "sources": [source.model_dump(by_alias=True) for source in normalized.sources], "evidenceRecords": evidence_records,
        "facts": {"revision": 1, "records": records, "tombstones": []},
        "document": {"schemaVersion": 1, "revision": workspace.document_revision + 1, "regions": [
            {"id": "header", "role": "header", "revision": 1, "blocks": []},
            {"id": "sidebar", "role": "sidebar", "revision": 1, "blocks": []},
            {"id": "main", "role": "main", "revision": 1, "blocks": blocks}]}, "assets": [],
        "operations": [op.model_dump(by_alias=True) for op in workspace.pre_draft.operations], "renders": [],
        "template": require_rich_template().manifest.model_dump(by_alias=True)})
