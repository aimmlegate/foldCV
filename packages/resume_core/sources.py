"""A project source record from one extraction result."""

from __future__ import annotations

from .extraction.models import ExtractResult
from .models.contracts import Source


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
