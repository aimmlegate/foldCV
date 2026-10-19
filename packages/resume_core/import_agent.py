"""Preserve source text while assembling flexible, linked editable facts."""

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import re

from pydantic import ValidationError

from .models.importing import ImportDraft, ImportReceipt
from .models.rich_document import RichDocumentV1
from .models.rich_facts import WorkingFacts
from .models.rich_workspace import ProjectV5
from .import_facts import assemble_import_facts, record_fields
from .import_layout import arrange_import
from .rendering.rich_template import require_rich_template


class ImportFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def checksum(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=lambda item: item.model_dump(mode="json", by_alias=True)).encode()).hexdigest()


def import_identity(workspace, rules, skill_sha256, *, allow_text_rewrite=False):
    pre = workspace.pre_draft
    return checksum({"project": workspace.project_id, "created": workspace.project is not None,
        "sources": [s.model_dump(mode="json", by_alias=True) for s in pre.sources
            if s.id == pre.selected_source_id] if pre else [],
        "formatting": workspace.formatting_as_of.model_dump(by_alias=True),
        "rules": rules.model_dump(mode="json", by_alias=True), "skill": skill_sha256,
        "template": require_rich_template().manifest.model_dump(by_alias=True),
        **({"allowTextRewrite": True} if allow_text_rewrite else {})})


@dataclass(frozen=True)
class SourcePart:
    key: str
    text: str
    evidence: dict


def source_parts(sources):
    parts = []
    for source in sources:
        for unit in sorted(source.units, key=lambda item: item.order):
            # Source lines remain exact; bounded parts also cover unusually long lines.
            for line in unit.text.splitlines(keepends=True):
                for start in range(0, len(line), 2000):
                    text = line[start:start + 2000]
                    parts.append(SourcePart(f"part_{len(parts) + 1}", text, {
                        "sourceId": source.id, "sourceRevision": source.revision,
                        "unitId": unit.id, "unitRevision": unit.revision, "text": text}))
    return parts


def validate_draft(draft, parts):
    keys = {part.key for part in parts}
    if not draft.allow_text_rewrite and any(block.text is not None for block in draft.blocks):
        raise ImportFailure("IMPORT_REWRITE_DISABLED")
    for items in (draft.facts, draft.blocks):
        if len({item.id for item in items}) != len(items):
            raise ImportFailure("IMPORT_DUPLICATE_ID")
    for item in [*draft.facts, *draft.blocks, draft.profile, *draft.technology_groups]:
        if len(set(item.source_keys)) != len(item.source_keys) or not set(item.source_keys) <= keys:
            raise ImportFailure("IMPORT_REFERENCE_INVALID")
    visible = {key for block in draft.blocks if block.kind not in {"duplicate", "source_only"} for key in block.source_keys}
    for block in draft.blocks:
        targets = set(block.duplicate_of)
        if (len(targets) != len(block.duplicate_of) or not targets <= visible
                or targets.intersection(block.source_keys)):
            raise ImportFailure("IMPORT_REFERENCE_INVALID")
    if len(draft.model_dump_json().encode()) > 1024 * 1024:
        raise ImportFailure("IMPORT_DRAFT_TOO_LARGE")


def update_draft(draft, batch, parts):
    request_sha = checksum(batch)
    prior = next((r for r in draft.receipts if r.batch_id == batch.batch_id), None)
    if prior:
        if prior.request_sha256 != request_sha:
            raise ImportFailure("IMPORT_IDEMPOTENCY_CONFLICT")
        return draft.model_copy(deep=True), prior
    if draft.finished or batch.sequence != draft.sequence or draft.sequence >= 128:
        raise ImportFailure("IMPORT_STALE_BATCH")
    updated = draft.model_copy(deep=True)
    for key, remove in (("facts", batch.remove_fact_ids), ("blocks", batch.remove_block_ids)):
        old = {item.id: item for item in getattr(updated, key)}
        incoming = getattr(batch, key)
        if len({item.id for item in incoming}) != len(incoming) or set(remove) & {item.id for item in incoming}:
            raise ImportFailure("IMPORT_DUPLICATE_ID")
        if not set(remove) <= old.keys():
            raise ImportFailure("IMPORT_REFERENCE_INVALID")
        for identifier in remove:
            del old[identifier]
        old.update({item.id: item for item in incoming})
        setattr(updated, key, list(old.values()))
    if batch.profile is not None:
        updated.profile = batch.profile.model_copy(deep=True)
    if batch.technology_groups is not None:
        updated.technology_groups = [group.model_copy(deep=True) for group in batch.technology_groups]
    updated.sequence += 1
    receipt = ImportReceipt(batchId=batch.batch_id, requestSha256=request_sha, sequence=updated.sequence)
    updated.receipts.append(receipt)
    try:
        updated = ImportDraft.model_validate(updated.model_dump(by_alias=True))
    except ValidationError:
        raise ImportFailure("IMPORT_DRAFT_TOO_LARGE") from None
    validate_draft(updated, parts)
    return updated, receipt


def finish_draft(draft, request, parts):
    if request.sequence != draft.sequence:
        raise ImportFailure("IMPORT_STALE_BATCH")
    if draft.finished and request.issues != draft.issues:
        raise ImportFailure("IMPORT_IDEMPOTENCY_CONFLICT")
    updated = draft.model_copy(deep=True)
    updated.finished, updated.issues = True, list(request.issues)
    validate_draft(updated, parts)
    return updated


def unplaced_parts(draft, parts):
    assigned = {key for block in draft.blocks for key in block.source_keys}
    return [part for part in parts if part.key not in assigned and part.text.strip()]


def assemble_agent_import(workspace, draft):
    from .import_cleanup import clean_list_text, compact_contacts, normalized
    if not draft.finished or workspace.pre_draft is None:
        raise ImportFailure("IMPORT_NOT_FINISHED")
    sources = [s.model_copy(deep=True) for s in workspace.pre_draft.sources
        if s.id == workspace.pre_draft.selected_source_id]
    parts = source_parts(sources)
    validate_draft(draft, parts)
    by_key = {part.key: part for part in parts}
    def identity(kind, value):
        return kind + "_" + checksum([workspace.project_id, draft.source_sha256, value])[:32]
    def evidence(keys):
        return [by_key[key].evidence for key in keys]
    records, evidence_records, fact_links = assemble_import_facts(draft, identity, evidence)
    from .import_technology_groups import grouped_technologies, replaced_skill_outlines
    technology_groups = grouped_technologies(draft.technology_groups, records, identity, evidence)
    replaced = replaced_skill_outlines(draft)
    regions = {key: [] for key in ("header", "sidebar", "main")}
    metadata = {}
    covered = set()
    outlines = {}
    for block in draft.blocks:
        if block.category == "other":
            outlines.setdefault(block.id.rsplit("_", 1)[0], []).append(block)
    repeated_names = set()
    name = " ".join(draft.profile.name.split())
    for key, blocks in outlines.items():
        texts = [" ".join("".join(by_key[k].text for k in block.source_keys).split()) for block in blocks if block.source_keys]
        # Keep raw page furniture in the source instead of printing the same name again.
        if name and texts and all(text == name for text in texts):
            repeated_names.add(key)
    omitted = {}
    categorized = any(block.category for block in draft.blocks)
    def add_block(identifier, keys, region="main", kind="paragraph", title=None, *, model_block=False, model_item=False,
            edited_text=None):
        pieces, previous = [], None
        for key in keys:
            part = by_key[key]
            if ((model_block or model_item) and previous and previous.evidence["unitId"] != part.evidence["unitId"]
                and previous.text and part.text and not previous.text[-1].isspace() and not part.text[0].isspace()):
                pieces.append("\n")
            pieces.append(part.text)
            previous = part
        text = "".join(pieces) if keys else title
        if edited_text is not None:
            text = edited_text
        if model_block and kind in {"paragraph", "heading", "section"}:
            text = " ".join(text.split())
        if keys:
            text = clean_list_text(text)
        if not model_block and categorized and region != "header" and name and normalized(text) == name:
            for key in keys:
                omitted[key] = "Repeated source name retained in the original."
            return
        if not text.strip():
            for key in keys:
                omitted[key] = "Empty list marker retained in the original."
            return
        spans = evidence(keys)
        provenance = ([{"kind": "source", "id": identity("source_link", identifier), "evidence": spans}] if spans else [])
        for record, source_keys in fact_links:
            shared = set(keys) & source_keys
            if shared:
                provenance.append({"kind": "citation", "id": identity("citation", [identifier, record["id"]]),
                    "recordId": record["id"], "fieldKeys": ["value"] if record["kind"] == "claim" else [],
                    "evidence": evidence([key for key in keys if key in shared])})
        matches = []
        # Literal anchors synchronize fields without judging the interpretation itself.
        for record, source_keys in fact_links:
            if record["kind"] == "claim" or not set(keys) & source_keys:
                continue
            for key, value in record_fields(record):
                found = list(re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text)) if value else []
                if len(found) == 1:
                    matches.append((found[0].start(), found[0].end(), record["id"], key))
        matches = [m for m in matches if not any(m != other and m[0] < other[1] and other[0] < m[1] for other in matches)]
        content, cursor = [], 0
        for start, end, record_id, key in sorted(matches):
            if cursor < start:
                content.append({"type": "text", "text": text[cursor:start], "styles": {}})
            content.append({"type": "fact_field", "bindingId": identity("binding", [identifier, record_id, key]),
                "recordId": record_id, "fieldKey": key, "text": text[start:end],
                "styles": {}, "syncedFactRevision": 1})
            provenance.append({"kind": "field_binding", "id": identity("field_link", [identifier, record_id, key]),
                "recordId": record_id, "fieldKey": key})
            cursor = end
        if cursor < len(text):
            content.append({"type": "text", "text": text[cursor:], "styles": {}})
        block = {"id": identity("import_block", identifier), "revision": 1, "type": kind,
            "props": {"level": 1 if region == "header" and any(owner == "candidate" and key == "name"
                for _, _, owner, key in matches) else 2}
                if kind == "heading" else {"recordId": None} if kind == "section" else {},
            "content": content, "children": [], "provenance": provenance}
        regions[region].append(block)
        return block
    for block in draft.blocks:
        if block.category == "skills" and block.id.rsplit("_", 1)[0] in replaced:
            covered.update(block.source_keys)
            continue
        if block.kind == "source_only":
            for key in block.source_keys:
                omitted[key] = block.reason
            covered.update(block.source_keys)
            continue
        if block.kind == "duplicate":
            targets = list(dict.fromkeys(by_key[key].evidence["unitId"] for key in block.duplicate_of))
            for key in block.source_keys:
                omitted[key] = "Model-marked duplicate; original retained. Matches source units: " + ", ".join(targets)
            covered.update(block.source_keys)
            continue
        repeated = not block.model_block and block.category == "other" and block.id.rsplit("_", 1)[0] in repeated_names
        rendered = None if repeated else add_block(["draft", block.id], block.source_keys, block.region, block.kind,
            block.title, model_block=block.model_block, model_item=block.list_item, edited_text=block.text)
        if rendered:
            metadata[rendered["id"]] = block
        covered.update(block.source_keys)
    for part in parts:
        if part.key not in covered:
            add_block(["retained", part.key], [part.key])
    regions["sidebar"] = compact_contacts(regions["sidebar"], metadata, sources)
    regions = arrange_import(regions, metadata, records, identity, technology_groups=technology_groups)
    if categorized:
        from .import_lists import format_import_lists
        regions = format_import_lists(regions, sources, identity,
            model_items={identifier for identifier, block in metadata.items() if block.list_item},
            model_blocks={identifier for identifier, block in metadata.items() if block.model_block})
    unresolved = []
    missing_units = {}
    for part in unplaced_parts(draft, parts):
        missing_units.setdefault((part.evidence["sourceId"], part.evidence["unitId"]), part)
    for part in missing_units.values():
        unresolved.append({"code": "FACT_SOURCE_UNRESOLVED", "sourceId": part.evidence["sourceId"],
            "unitId": part.evidence["unitId"], "section": "Фрагмент сохранён; его место в резюме требует проверки."})
    issues = list(draft.issues)
    if any("IMAGE" in source.warnings for source in sources):
        issues.append("Изображения в исходнике не обработаны; использован доступный текстовый слой.")
    # Edited summaries can cite the same evidence as detailed project blocks.
    placements = [key for block in draft.blocks if block.kind not in {"duplicate", "source_only"}
        and block.text is None for key in block.source_keys]
    if len(placements) != len(set(placements)):
        issues.append("Некоторые фрагменты исходника размещены повторно. Проверьте, нужны ли эти повторы.")
    if not draft.facts:
        issues.append("Список фактов пуст. Проверьте исходник и добавьте нужные сведения.")
    for issue in issues:
        unresolved.append({"code": "FACT_SOURCE_UNRESOLVED", "sourceId": sources[0].id,
            "unitId": None, "section": issue})
    structured = any(fact.record is not None for fact in draft.facts)
    counts = dict(Counter(record["kind"] for record in records)) if structured else {"digest": len(draft.facts)}
    facts = WorkingFacts.model_validate({"revision": 1, "mode": "imported" if structured else "digest", "records": records, "tombstones": [],
        "extraction": {"status": "partial" if unresolved or any(s.warnings for s in sources) else "complete",
            "factCount": sum(counts.values()), "counts": counts, "requestBytes": 0,
            "recoveredRows": 0, "unresolved": unresolved}})
    document = RichDocumentV1.model_validate({"schemaVersion": 1, "revision": workspace.document_revision + 1,
        "regions": [{"id": key, "role": key, "revision": 1, "blocks": blocks} for key, blocks in regions.items()]})
    placement = {}
    for block in document.blocks():
        for link in block.provenance:
            for span in getattr(link, "evidence", []):
                placement.setdefault((span.source_id, span.unit_id), []).append(block.id)
    omitted_units = {(by_key[key].evidence["sourceId"], by_key[key].evidence["unitId"]): reason for key, reason in omitted.items()}
    coverage = [{"sourceId": source.id, "unitId": unit.id, "disposition": "placed" if placement.get((source.id, unit.id)) else "excluded",
        "blockIds": list(dict.fromkeys(placement.get((source.id, unit.id), []))),
        "reason": None if placement.get((source.id, unit.id)) else omitted_units.get((source.id, unit.id), "Repeated source name retained in the original.") if unit.text.strip()
            else "Whitespace only."} for source in sources for unit in source.units]
    return ProjectV5.model_validate({"schemaVersion": 5, "projectId": workspace.project_id,
        "revision": workspace.project_revision + 1, "createdAt": workspace.created_at, "sources": sources,
        "evidenceRecords": evidence_records, "facts": facts, "document": document, "assets": [],
        "operations": workspace.pre_draft.operations, "renders": [], "importCoverage": coverage,
        "template": require_rich_template().manifest})
