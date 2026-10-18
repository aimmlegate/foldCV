"""Place every source fragment into the template without drafting new prose."""

import re

from .gui_drafting import draft_skeleton
from .models.rich_workspace import ProjectV5
from .rendering.rich_template import require_rich_template
from .rich_assembly import assemble_facts, identity
from .models.rich_document import RichDocumentV1
from .models.rich_facts import WorkingFacts
from .rich_format import compact, format_document, section_role


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
    blocks, excluded = [], {}
    candidate = next(record for record in records if record["kind"] == "candidate")
    headers = {compact(record[key]["rawText"]) for record in records for key in ("employer", "role") if key in record}
    def fragments(text):
        chunks = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or re.fullmatch(r"[,.;:]+", stripped):
                continue
            marker = re.match(r"^(?:[•●▪]|[-–]\s|\d+[.)]\s)\s*", stripped)
            structural = bool(section_role(stripped) or compact(stripped) in headers or re.search(r"\d{4}\s*[—–-]", stripped))
            if marker:
                chunks.append(["bullet_list", stripped[marker.end():], False])
            elif structural or not chunks or chunks[-1][2]:
                chunks.append(["paragraph", stripped, structural])
            else:
                chunks[-1][1] += " " + stripped
        return chunks

    for source in normalized.sources:
        last_by_page = {}
        for unit in sorted(source.units, key=lambda item: item.order):
            if unit.location.kind == "page" and unit.text.strip():
                last_by_page[unit.location.index] = unit
        footer_names = [unit for unit in last_by_page.values() if compact(unit.text) == compact(candidate["name"]["rawText"]) and unit.text.strip()]
        footer_ids = {unit.id for unit in footer_names} if len(footer_names) >= 2 else set()
        for unit in sorted(source.units, key=lambda item: item.order):
            if unit.id in footer_ids or not unit.text.strip():
                excluded[(source.id, unit.id)] = "Repeated candidate name in the last text block of multiple PDF pages." if unit.id in footer_ids else "Whitespace only."
                continue
            evidence = {"sourceId": source.id, "sourceRevision": source.revision, "unitId": unit.id,
                "unitRevision": unit.revision, "text": unit.text}
            cuts = []
            for key in ("name", "title"):
                value = candidate[key]["rawText"]
                if not value or not any(span["sourceId"] == source.id and span["unitId"] == unit.id for span in candidate["evidence"]):
                    continue
                pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in value.split()) + r"(?!\w)"
                for match in re.finditer(pattern, unit.text, re.I):
                    cuts.append((match.start(), match.end(), key))
            cursor, parts = 0, []
            for start, end, key in sorted(cuts):
                if start < cursor:
                    continue
                if start > cursor:
                    parts.extend((kind, text, None) for kind, text, _ in fragments(unit.text[cursor:start]))
                parts.append(("paragraph", " ".join(unit.text[start:end].split()), key)); cursor = end
            parts.extend((kind, text, None) for kind, text, _ in fragments(unit.text[cursor:]))
            for kind, text, key in parts:
                content = ([{"type": "fact_field", "bindingId": identity("binding"), "recordId": candidate["id"],
                    "fieldKey": key, "text": text, "styles": {}, "syncedFactRevision": 1}] if key else literal_content(text, source, unit, records))
                blocks.append({"id": identity("source-literal"), "revision": 1, "type": kind, "props": {},
                    "content": content, "children": [], "provenance": [{"kind": "source", "id": identity("source-link"), "evidence": [evidence]}]})
    facts = WorkingFacts.model_validate({"revision": 1, "records": records, "tombstones": [],
        "extraction": normalized.extraction.model_dump(by_alias=True) if normalized.extraction else None})
    document = format_document(RichDocumentV1.model_validate({"schemaVersion": 1, "revision": workspace.document_revision + 1, "regions": [
        {"id": "header", "role": "header", "revision": 1, "blocks": []},
        {"id": "sidebar", "role": "sidebar", "revision": 1, "blocks": []},
        {"id": "main", "role": "main", "revision": 1, "blocks": blocks}]}), facts)
    placements = {}
    for block in document.blocks():
        for link in block.provenance:
            for span in getattr(link, "evidence", []):
                placements.setdefault((span.source_id, span.unit_id), []).append(block.id)
    coverage = [{"sourceId": source.id, "unitId": unit.id,
        "disposition": "excluded" if (source.id, unit.id) in excluded else "placed",
        "blockIds": list(dict.fromkeys(placements.get((source.id, unit.id), []))),
        "reason": excluded.get((source.id, unit.id))} for source in normalized.sources for unit in source.units]
    return ProjectV5.model_validate({"schemaVersion": 5, "projectId": workspace.project_id,
        "revision": workspace.project_revision + 1, "createdAt": workspace.created_at,
        "sources": [source.model_dump(by_alias=True) for source in normalized.sources], "evidenceRecords": evidence_records,
        "facts": facts.model_dump(by_alias=True), "document": document.model_dump(by_alias=True), "importCoverage": coverage, "assets": [],
        "operations": [op.model_dump(by_alias=True) for op in workspace.pre_draft.operations], "renders": [],
        "template": require_rich_template().manifest.model_dump(by_alias=True)})
