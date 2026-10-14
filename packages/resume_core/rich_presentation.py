"""Shared fixed-template roles without another authored document."""

from typing import Literal

from .models.contracts import Id, Wire
from .models.rich_document import FactFieldSpan, Hyperlink
from .technologies import BY_ID, resolve_technology


class BlockPresentation(Wire):
    role: Literal["body", "support", "header_name", "header_title", "job_heading", "profile_heading",
        "section_heading", "focus_heading", "focus_entry", "group"]
    logo: str | None = None


class RichPresentation(Wire):
    blocks: dict[Id, BlockPresentation]


def authored_text(block):
    if isinstance(block.content, str):
        return block.content
    if not isinstance(block.content, list):
        return ""
    return "".join("".join(part.text for part in span.content) if isinstance(span, Hyperlink) else span.text for span in block.content)


def presentation(document, facts=None):
    result = {}
    records = {record.id: record for record in facts.records} if facts is not None else {}
    def visit(blocks, region, focus=False):
        logos = 0
        for block in blocks:
            role, logo = "body", None
            if block.type == "section":
                role = "group" if not authored_text(block).strip() else "focus_heading" if block.props.presentation == "focus" else "profile_heading" if block.id == "profile" and region == "main" else "section_heading"
            elif region == "header" and block.type == "heading" and block.props.level in {1, 2}:
                role = "header_name" if block.props.level == 1 else "header_title"
            elif block.type == "heading" and block.props.level == 2:
                role = "job_heading"
            elif isinstance(block.content, list):
                fields = [span for span in block.content if isinstance(span, FactFieldSpan)]
                if fields and all(span.field_key.startswith("period:") or span.field_key in {"role", "display"} for span in fields):
                    role = "support"
            if focus and isinstance(block.content, list) and block.type != "section":
                role = "focus_entry"
                canonical = resolve_technology(authored_text(block)).canonical_id
                exact = {span.record_id for span in block.content if isinstance(span, FactFieldSpan)}
                if len(exact) == 1:
                    record = records.get(next(iter(exact)))
                    if record is not None and record.kind == "technology" and record.display.raw_text == authored_text(block):
                        canonical = record.canonical_id.value
                entry = BY_ID.get(canonical)
                if entry is not None and entry.logo and logos < 8:
                    logo = "skills/format-resume/assets/" + entry.logo; logos += 1
            result[block.id] = BlockPresentation(role=role, logo=logo)
            visit(block.children, region, block.type == "section" and block.props.presentation == "focus")
    for region in document.regions:
        visit(region.blocks, region.role)
    return RichPresentation(blocks=result)
