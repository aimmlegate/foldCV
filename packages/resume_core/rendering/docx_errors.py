"""Safe writer/schema errors with paths from the captured render input only."""

from __future__ import annotations

import re

from pydantic import TypeAdapter, ValidationError

from .models import DocumentAnchor, DocxError, RenderDocument, SafeRenderPath


class DocxFailure(Exception):
    def __init__(self, error: DocxError):
        self.error = error
        self.code = error.code
        super().__init__(error.code)


def safe_path(path: str) -> str | None:
    try:
        return TypeAdapter(SafeRenderPath).validate_python(path)
    except ValidationError:
        return None


def failure(code: str, path: str | None = None, anchors: dict | None = None) -> DocxFailure:
    path = safe_path(path) if path else None
    anchor = (anchors or {}).get(path, DocumentAnchor(kind="document"))
    return DocxFailure(DocxError(code=code, path=path, anchor=anchor))


def _path(parts: tuple) -> str:
    value = ""
    for part in parts:
        value += f"[{part}]" if isinstance(part, int) else ("." if value else "") + str(part)
    return value


def _strings(value: object, prefix: str = ""):
    if isinstance(value, str):
        yield prefix, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _strings(child, prefix + ("." if prefix else "") + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _strings(child, f"{prefix}[{index}]")


def validate_document(data: object, anchors: dict | None = None) -> RenderDocument:
    # Aggregate validators lose their child location; find those known paths first.
    strings = list(_strings(data))
    for path, text in strings:
        if any(ord(char) < 32 and char not in "\n\t" for char in text):
            raise failure("DOCX_INVALID_CHARACTER", path, anchors)
        if re.fullmatch(r"(?:sidebar\[\d+\]\.items\[\d+\]|projects\[\d+\]\.(?:tasks|results)\[\d+\]|achievements\[\d+\])", path) and len(text) > 4000:
            raise failure("DOCX_TEXT_LIMIT", path, anchors)
    try:
        return RenderDocument.model_validate(data)
    except ValidationError as error:
        for item in error.errors(include_input=False, include_context=False, include_url=False):
            type = item["type"]
            path = safe_path(_path(item["loc"]))
            if type in {"string_too_long", "too_long"}:
                code = "DOCX_TEXT_LIMIT" if type == "string_too_long" else "DOCX_LIST_LIMIT"
                raise failure(code, path, anchors) from None
            if path:
                raise failure("DOCX_INVALID_RENDER_INPUT", path, anchors) from None
        if sum(len(text) for _, text in strings) > 100000:
            raise failure("DOCX_TOTAL_TEXT_LIMIT") from None
        raise failure("DOCX_INVALID_RENDER_INPUT") from None


def writer_failure(error: Exception, anchors: dict | None = None) -> DocxFailure:
    reasons = {
        "Candidate display name exceeds one header line": ("DOCX_NAME_LINE_LIMIT", "candidate.name"),
        "Candidate title exceeds two header lines": ("DOCX_TITLE_LINE_LIMIT", "candidate.title"),
        "Unbreakable text exceeds the column width": ("DOCX_UNBREAKABLE_TEXT", None),
        "One resume block exceeds the page budget": ("DOCX_BLOCK_PAGE_BUDGET", None),
        "Resume block cannot fit on its planned page": ("DOCX_BLOCK_PLANNED_PAGE", None),
    }
    code, path = reasons.get(str(error), ("DOCX_RENDER_FAILED", None))
    if str(error).startswith("Unknown focus icon:"):
        code = "DOCX_UNKNOWN_FOCUS_ICON"
    return failure(code, path, anchors)
