"""Exact typed-field access and authored occurrence groups for rich synchronization."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Literal

from .dates import source_date
from .models.rich_document import FactFieldSpan, ImageBlock, TableBlock
from .models.rich_facts import WorkingField
from .models.template_facts import ExtensionRecord
from .models.template_document import BoundLink, FieldRef
from .template_facts import extension_cell, set_human_cell
from .technologies import resolve_technology


def field_key(record_id, key):
    return json.dumps(["fact", record_id, key], ensure_ascii=False, separators=(",", ":"))


def working_field(record, key):
    if isinstance(record, ExtensionRecord): return extension_cell(record,key)
    if key.startswith("period:"):
        rest = key.removeprefix("period:")
        identifier, _, name = rest.rpartition(":")
        if name not in {"start", "end", "present"}:
            return None
        period = next((item for item in getattr(record, "periods", []) if item.id == identifier), None)
        return getattr(period, name, None)
    value = getattr(record, {"canonicalId": "canonical_id"}.get(key, key), None)
    return value if isinstance(value, WorkingField) else None


def builtin_cell_values(records):
    result = {}
    for record in records:
        for key in type(record).model_fields:
            value = getattr(record, key)
            if isinstance(value, WorkingField):
                key = 'canonicalId' if key == 'canonical_id' else key
                result[field_key(record.id, key)] = (record, key, value)
        for period in getattr(record, 'periods', []):
            for name in ['start', 'end', 'present']:
                key = 'period:' + period.id + ':' + name
                result[field_key(record.id, key)] = (record, key, getattr(period, name))
    return result


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
            spans=[child for span in content for child in (span.content if isinstance(span,BoundLink) else [span])]
            for span in spans:
                if not isinstance(span, FactFieldSpan) or not getattr(span,"complete",True):
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


@dataclass(frozen=True)
class BoundLinkField:
    block_id: str
    role: Literal['label', 'url']
    reference: FieldRef
    text: str


def bound_link_fields(document):
    result = []
    for block in document.blocks():
        for _, content in inline_groups(block):
            for span in content:
                if isinstance(span, BoundLink):
                    if span.label_binding is not None:
                        result.append(BoundLinkField(block.id, 'label', span.label_binding,
                            ''.join(child.text for child in span.content)))
                    if span.url_binding is not None:
                        result.append(BoundLinkField(block.id, 'url', span.url_binding, span.href))
    return result


def parse_date(text):
    value = text.strip()
    if not value:
        return None
    # Retain precise ISO values; a sole year with a language suffix keeps year precision.
    if re.fullmatch(r"\d{4}\s*(?:г\.?|year)?", value, re.I):
        value = value[:4]
    found = source_date(value)
    return found[0] if found is not None else None


def set_text(record, key, text):
    if isinstance(record, ExtensionRecord): return set_human_cell(record,key,text)
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
    records = records_by_id(project.facts)
    for group in occurrences(project.document).values():
        record = records.get(group.record_id)
        field = working_field(record, group.key) if record is not None else None
        if field is not None and group.text == field.raw_text:
            for span in group.spans:
                span.synced_fact_revision = field.revision


def records_by_id(facts):
    return {record.id:record for record in [*facts.records,*[r for r in getattr(facts,"extensions",[]) if r.active]]}
