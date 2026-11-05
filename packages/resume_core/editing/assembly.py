"""Small helpers of the V6 facts: generated ids, field values and partial dates."""

import uuid

from ..dates import partial_date


def identity(prefix):
    return prefix + "-" + uuid.uuid4().hex


def field(value, raw=None):
    if raw is None and hasattr(value, "precision"):
        raw = f"{value.year:04d}" + (f"-{value.month:02d}" if value.month is not None else "") + (f"-{value.day:02d}" if value.day is not None else "")
    if hasattr(value, "model_dump"):
        value = value.model_dump(by_alias=True)
    raw_text = raw if raw is not None else str(value) if value is not None else ""
    return {"value": value, "rawText": raw_text,
            "status": "known" if value is not None and value != "" else "unknown", "revision": 1, "pendingRawText": None} | (
            {"value": None} if value == "" else {}) | ({"status": "unresolved"} if value is None and raw_text else {})


def date_field(text):
    try:
        value = partial_date(text.strip()) if text.strip() else None
    except (ValueError, TypeError):
        value = None
    result = field(value, text)
    if value is None and text:
        result["status"] = "unresolved"
    return result
