"""A bounded layout summary of a sample document for the template assistant; contacts are masked."""

from __future__ import annotations

import json

from packages.resume_core.extraction.models import ExtractResult
from packages.resume_core.template_source_cleanup import without_contacts

TEXT_LIMIT = 120
LIST_SHOWN = 2


def _size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _cut(text: str) -> str:
    return text if len(text) <= TEXT_LIMIT else text[:TEXT_LIMIT - 1] + "…"


def _entry(unit, text: str) -> dict:
    cues = unit.structure
    column = cues.column if cues is not None else None
    if column is None and unit.location.kind == "table_cell" and unit.location.column is not None:
        # A Word table cell has no layout column; its grid column is the closest cue.
        column = unit.location.column + 1
    return {"column": column, "group": cues.group if cues else None,
        "heading": cues.heading_level if cues else None, "style": cues.style if cues else None,
        "size": cues.font_size if cues else None, "bold": cues.bold if cues else None,
        "list": cues.list_level if cues else None, "text": text}


def _place(unit) -> tuple:
    location = unit.location
    return location.kind, location.part, location.table, location.row, location.column


def _entries(result: ExtractResult) -> list[dict]:
    entries, run, place, hidden = [], 0, None, 0

    def close():
        if hidden:
            entries[-1]["text"] = f"… ещё {hidden}"

    for unit in result.units:
        if not unit.text.strip():
            continue
        entry = _entry(unit, _cut(without_contacts(unit.text).strip()))
        listed = entry["list"] is not None
        if listed and run and _place(unit) == place:
            run += 1
            if run > LIST_SHOWN:
                if run == LIST_SHOWN + 1:
                    entries.append(entry)
                hidden += 1
                continue
        else:
            close()
            run, hidden = (1 if listed else 0), 0
        place = _place(unit)
        entries.append(entry)
    close()
    return entries


def sample_summary(result: ExtractResult, *, limit: int = 32 * 1024) -> dict:
    """Layout cues of every non-empty unit, lists cut to two items, as many units as fit in `limit` bytes."""
    entries = _entries(result)
    gaps = list(dict.fromkeys((gap.code, gap.location.page) for gap in result.gaps))
    summary = {"name": result.original_name, "pages": result.page_count, "unitCount": len(entries),
        "listed": len(entries), "units": [], "gaps": [{"code": code, "page": page} for code, page in gaps]}
    while summary["gaps"] and _size(summary) > limit:
        summary["gaps"].pop()
    used = _size(summary)
    for entry in entries:
        cost = _size(entry) + (1 if summary["units"] else 0)
        if used + cost > limit:
            break
        summary["units"].append(entry)
        used += cost
    summary["listed"] = len(summary["units"])
    return summary
