"""Canonical selection guards shared by source reads and later rewrites."""

from .gui_derived import digest
from .models.recovery import authored_fields, record_slot


def field_index(document):
    return {field.field_id: (field, record_slot(record))
            for record in document.records() for field in authored_fields(record)}


def normalized_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def selection_fingerprint(workspace):
    if workspace.project is None:
        return None
    return digest({"document": workspace.project.document.model_dump(mode="json", by_alias=True),
        "facts": [(fact.id, fact.revision) for fact in workspace.project.facts],
        "sources": [(source.id, source.revision, [(unit.id, unit.revision) for unit in source.units])
                    for source in workspace.project.sources]})


def utf16_slice(text: str, start: int, end: int) -> str:
    encoded = normalized_text(text).encode("utf-16-le")
    if not 0 <= start <= end <= len(encoded) // 2:
        raise ValueError("invalid selection range")
    return encoded[start * 2:end * 2].decode("utf-16-le")


def valid_selection(workspace, selection) -> bool:
    if (workspace.project is None or selection.project_id != workspace.project_id
        or selection.document_revision != workspace.document_revision
        or selection.dependency_fingerprint != selection_fingerprint(workspace)):
        return False
    indexed = field_index(workspace.project.document)
    order = list(indexed)
    selected = selection.spans
    positions = []
    try:
        for span in selected:
            field = indexed[span.field_id][0]
            if span.range.start == span.range.end or utf16_slice(field.text, span.range.start, span.range.end) != span.captured_text:
                return False
            positions.append(order.index(span.field_id))
    except (KeyError, ValueError, UnicodeError):
        return False
    if positions != sorted(set(positions)):
        return False
    if len(selected) > 1:
        for index, span in enumerate(selected):
            size = len(normalized_text(indexed[span.field_id][0].text).encode("utf-16-le")) // 2
            if index > 0 and span.range.start != 0 or index < len(selected) - 1 and span.range.end != size:
                return False
        covered = {span.field_id for span in selected}
        if any(id not in covered and indexed[id][0].text for id in order[positions[0]:positions[-1] + 1]):
            return False
    return True
