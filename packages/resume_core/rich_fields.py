"""Exact typed-field access and authored occurrence groups for rich synchronization."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from .dates import partial_date
from .models.rich_document import FactFieldSpan, ImageBlock, TableBlock
from .models.rich_facts import WorkingField
from .technologies import resolve_technology


def field_key(record_id, key):
    return json.dumps(["fact", record_id, key], ensure_ascii=False, separators=(",", ":"))


def working_field(record, key):
    if key.startswith("period:"):
        rest = key.removeprefix("period:")
        identifier, _, name = rest.rpartition(":")
        if name not in {"start", "end", "present"}:
            return None
        period = next((item for item in getattr(record, "periods", []) if item.id == identifier), None)
        return getattr(period, name, None)
    value = getattr(record, {"canonicalId": "canonical_id"}.get(key, key), None)
    return value if isinstance(value, WorkingField) else None


def inline_groups(block):
    if isinstance(block, TableBlock):
        return [(cell.id, cell.content) for row in block.content.rows for cell in row.cells]
    if isinstance(block, ImageBlock):
        return [("caption", block.props.caption)]
    return [("content", block.content)] if isinstance(block.content, list) else []


@dataclass
class FieldOccurrence:
    record_id: str
    key: str
    root: str
    spans: list[FactFieldSpan]
    block_ids: list[str]

    @property
    def text(self):
        return "".join(span.text for span in self.spans)


def occurrences(document):
    groups = {}
    for block in document.blocks():
        for container, content in inline_groups(block):
            previous, inherited = None, None
            for span in content:
                if not isinstance(span, FactFieldSpan):
                    previous, inherited = None, None
                    continue
                pair = (span.record_id, span.field_key)
                root = span.binding_root_id or (inherited if pair == previous else span.binding_id)
                # Old unrooted style fragments stay one occurrence inside their original field block.
                if root is None:
                    root = f"{block.id}:{container}:{span.binding_id}"
                identity = (span.record_id, span.field_key, root)
                group = groups.setdefault(identity, FieldOccurrence(*identity, [], []))
                group.spans.append(span)
                if block.id not in group.block_ids:
                    group.block_ids.append(block.id)
                previous, inherited = pair, root
    return groups


def parse_date(text):
    value = text.strip()
    if not value:
        return None
    # Retain precise ISO values; a sole year with a language suffix keeps year precision.
    if re.fullmatch(r"\d{4}\s*(?:г\.?|year)?", value, re.I):
        value = value[:4]
    try:
        return partial_date(value)
    except (ValueError, TypeError):
        return None


def set_text(record, key, text):
    target = working_field(record, key)
    if target is None:
        raise ValueError("WORKING_FIELD_MISSING")
    known = text.strip() or None
    date = key == "completion" or (record.kind == "certification" and key == "date") or key.endswith(":start") or key.endswith(":end")
    if date:
        known = parse_date(text)
    elif key.endswith(":present"):
        known = True if re.fullmatch(r"(?:present|current|now|настоящее\s+время|по\s+настоящее\s+время|сейчас)", text.strip(), re.I) else False if not text.strip() else None
    status = "known" if known is not None else "unknown" if not text.strip() else "unresolved"
    value = {"value": known.model_dump(by_alias=True) if hasattr(known, "model_dump") else known,
        "rawText": text, "status": status, "revision": target.revision, "pendingRawText": None, "userCorrected": True}
    changed = type(target).model_validate(value)
    for name in type(target).model_fields:
        setattr(target, name, getattr(changed, name))
    record.user_corrected = True
    if record.kind == "technology" and key == "display":
        canonical = resolve_technology(text).canonical_id
        record.canonical_id = type(record.canonical_id)(value=canonical, rawText=canonical or text,
            status="known" if canonical else "unresolved" if text else "unknown", revision=record.canonical_id.revision,
            pendingRawText=None, userCorrected=True)
    return target


def synchronize_binding_revisions(project):
    records = {record.id: record for record in project.facts.records}
    for group in occurrences(project.document).values():
        record = records.get(group.record_id)
        field = working_field(record, group.key) if record is not None else None
        if field is not None and group.text == field.raw_text:
            for span in group.spans:
                span.synced_fact_revision = field.revision
