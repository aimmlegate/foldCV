"""A project source record from one extraction result, and the exact spans of its units."""

from __future__ import annotations

from .extraction.models import ExtractResult
from .hashing import sha256
from .models.contracts import Source
from .models.template_facts import SourceSpan


def canonical_source(result: ExtractResult, *, source_id: str | None = None) -> Source:
    identity = source_id if source_id is not None else result.source_id
    units = []
    for unit in result.units:
        location = unit.location
        kind = "table_cell" if location.kind == "table_cell" else "page" if location.page else "pasted" if location.kind == "pasted" else "paragraph"
        index = location.page - 1 if location.page else location.table if kind == "table_cell" else location.paragraph
        units.append({"id": f"{identity}/{unit.id}", "revision": 1, "order": unit.order,
                      "text": unit.text.replace("\r\n", "\n").replace("\r", "\n"),
                      "location": {"kind": kind, "index": index if index is not None else unit.order,
                                   "row": location.row if kind == "table_cell" else None,
                                   "column": location.column if kind == "table_cell" else None},
                      "structure": unit.structure.model_dump(by_alias=True) if unit.structure else None,
                      "disposition": "unresolved", "representedFactIds": []})
    return Source.model_validate({"id": identity, "revision": 1, "originalName": result.original_name,
                                  "mimeType": result.mime_type, "byteSha256": result.byte_sha256,
                                  "byteRef": f"sources/{identity}/original",
                                  "parser": result.parser, "parserVersion": result.parser_version,
                                  "units": units, "overlays": [],
                                  "warnings": [gap.code for gap in result.gaps],
                                  "warningDetails": [{"code": gap.code, "page": gap.location.page} for gap in result.gaps]})


def source_slice(sources,span: SourceSpan) -> str:
    matches = [s for s in sources if s.id == span.source_id and s.revision == span.source_revision]
    if len(matches) != 1:
        raise ValueError('source span has no unique captured source')
    units = [u for u in matches[0].units if u.id == span.unit_id and u.revision == span.unit_revision]
    unit = units[0] if len(units) == 1 else None
    if unit is None or span.end>len(unit.text): raise ValueError("invalid captured source span")
    text=unit.text[span.start:span.end]
    if sha256(text.encode('utf-8'))!=span.slice_hash: raise ValueError("source slice hash mismatch")
    return text


def capture_span(source,unit,start=0,end=None):
    end=len(unit.text) if end is None else end
    span=SourceSpan(sourceId=source.id,sourceRevision=source.revision,unitId=unit.id,unitRevision=unit.revision,
        start=start,end=end,sliceHash=sha256(unit.text[start:end].encode('utf-8')))
    source_slice([source],span)
    return span


def line_spans(source, unit):
    """Each non-blank line of a multi-line unit, with its line break, as one exact span."""
    spans, start = [], 0
    for line in unit.text.splitlines(keepends=True):
        if line.strip():
            spans.append(capture_span(source, unit, start, start + len(line)))
        start += len(line)
    return spans if len(spans) > 1 else []
