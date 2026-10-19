"""Shared fixed-template roles without another authored document."""

from typing import Literal
import re
from pydantic import Field

from .models.contracts import Id, Wire
from .models.rich_document import FactFieldSpan, Hyperlink
from .technologies import BY_ID, logo_path, resolve_technology, technology_identity
from .technology_experience import technology_experience, technology_years, whole_years_text
from .technology_focus import focus_entry_record, focus_sort_key, focus_logo, focus_choices


class BlockPresentation(Wire):
    role: Literal["body", "support", "header_name", "header_title", "job_heading", "profile_heading",
        "section_heading", "focus_heading", "focus_entry", "group", "hidden"]
    logo: str | None = None
    experience: str | None = None
    experience_note: str | None = None


class FocusTechnology(Wire):
    record_id: Id
    display: str
    logo: str
    years: int | None


class RichPresentation(Wire):
    blocks: dict[Id, BlockPresentation]
    focus_entries: list[FocusTechnology] = Field(default_factory=list)
    focus_options: list[FocusTechnology] = Field(default_factory=list)


def authored_text(block):
    if isinstance(block.content, str):
        return block.content
    if not isinstance(block.content, list):
        return ""
    return "".join("".join(part.text for part in span.content) if isinstance(span, Hyperlink) else span.text for span in block.content)


def presentation(document, facts=None):
    result = {}
    records = {record.id: record for record in facts.records} if facts is not None else {}
    russian = any(re.search(r"[а-яё]", authored_text(block), re.I) for block in document.blocks())
    durations = technology_experience(facts, russian) if facts is not None else {}
    years = technology_years(facts) if facts is not None else {}
    focused = {}
    def visit(blocks, region, focus=False, tool_group=False):
        for block in blocks:
            role, logo, experience, note = "body", None, None, None
            if block.type == "section":
                role = "group" if not authored_text(block).strip() else "focus_heading" if block.props.presentation == "focus" else "profile_heading" if (block.id == "profile" or block.id.startswith("import_profile_")) and region == "main" else "section_heading"
            elif region == "header" and block.type == "heading" and block.props.level in {1, 2}:
                role = "header_name" if block.props.level == 1 else "header_title"
            elif block.type == "heading" and block.props.level == 2:
                role = "job_heading"
            elif isinstance(block.content, list):
                fields = [span for span in block.content if isinstance(span, FactFieldSpan)]
                if not tool_group and fields and all(span.field_key.startswith("period:") or span.field_key in {"role", "display"} for span in fields):
                    role = "support"
            if focus and isinstance(block.content, list) and block.type != "section":
                role = "focus_entry"
                record = focus_entry_record(block, records) if facts is not None else None
                if facts is not None and record is None:
                    result[block.id] = BlockPresentation(role="hidden")
                    visit(block.children, region)
                    continue
                canonical = resolve_technology(authored_text(block)).canonical_id
                exact = {span.record_id for span in block.content if isinstance(span, FactFieldSpan)}
                if len(exact) == 1:
                    record = records.get(next(iter(exact)))
                    if record is not None and record.kind == "technology" and (record_logo := focus_logo(record)):
                        focused.setdefault(technology_identity(record), (record, record_logo))
                    if record is not None and record.kind == "technology" and record.display.raw_text == authored_text(block):
                        canonical = technology_identity(record)
                        value = years.get(canonical)
                        experience = whole_years_text(value, russian) if value is not None else None
                        note = durations.get(canonical, (None, None))[1] if experience else None
                entry = BY_ID.get(canonical)
                if entry is not None and entry.logo:
                    logo = logo_path(entry)
            result[block.id] = BlockPresentation(role=role, logo=logo, experience=experience, experienceNote=note)
            visit(block.children, region, block.type == "section" and block.props.presentation == "focus",
                block.type == "section" and block.id.startswith("technology_group_"))
    for region in document.regions:
        visit(region.blocks, region.role)
    entries = [FocusTechnology(recordId=record.id, display=record.display.raw_text, logo=logo,
        years=years.get(technology_identity(record))) for record, logo in sorted(focused.values(), key=lambda item: focus_sort_key(item[0], years))]
    options = [FocusTechnology(recordId=record.id, display=record.display.raw_text, logo=focus_logo(record),
        years=years.get(technology_identity(record))) for record in focus_choices(facts)
        if technology_identity(record) not in focused] if facts is not None else []
    return RichPresentation(blocks=result, focusEntries=entries, focusOptions=options)
