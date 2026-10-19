"""Visible, ordered technology entries shared by the editor, facts and DOCX."""

from .models.rich_document import FactFieldSpan
from .models.rich_facts import WorkingFacts
from .technologies import BY_ID, is_technical, logo_path, technology_identity
from .technology_experience import technology_years


def focus_entry_record(block, records):
    fields = [span for span in block.content if isinstance(span, FactFieldSpan)] if isinstance(block.content, list) else []
    if len(fields) != 1 or fields[0].field_key != "display":
        return None
    record = records.get(fields[0].record_id)
    return record if record and record.kind == "technology" and focus_logo(record) else None


def focus_logo(record):
    entry = BY_ID.get(technology_identity(record))
    return logo_path(entry) if is_technical(record) and entry and entry.logo else None


def focus_sort_key(record, years):
    value = years.get(technology_identity(record))
    return value is None, -(value or 0)


def focus_choices(facts):
    selected = {}
    for record in sorted((r for r in facts.records if r.kind == "technology"), key=lambda r: r.job_id is not None):
        if focus_logo(record):
            selected.setdefault(technology_identity(record), record)
    years = technology_years(facts)
    return sorted(selected.values(), key=lambda r: focus_sort_key(r, years))


def focus_candidates(raw_records, count):
    facts = WorkingFacts(revision=1, records=raw_records, tombstones=[])
    by_id = {r["id"]: r for r in raw_records}
    return [by_id[r.id] for r in focus_choices(facts)[:count]]


def focus_membership_steps(workspace, record_id, include):
    from .models.rich_document import SectionBlock, ParagraphBlock
    from .models.rich_mutations import PutBlock, RemoveBlock
    from .rich_assembly import identity
    from .rich_dependencies import placements
    from .rich_panel import field_block
    project = workspace.project
    records = {record.id: record for record in project.facts.records}
    record = records.get(record_id)
    if record is None or record.kind != "technology" or include and not focus_logo(record):
        raise ValueError("FOCUS_TECHNOLOGY_INVALID")
    canonical = technology_identity(record)
    sections = [block for block in project.document.blocks() if block.type == "section" and block.props.presentation == "focus"]
    def matches(block):
        return isinstance(block.content, list) and any(isinstance(span, FactFieldSpan) and span.field_key == "display"
            and (target := records.get(span.record_id)) is not None and target.kind == "technology"
            and technology_identity(target) == canonical for span in block.content)
    present = any(matches(child) for section in sections for child in section.children)
    if present == include:
        return []
    positions, steps = placements(project.document), []
    if include:
        section = sections[0].model_copy(deep=True) if sections else SectionBlock(type="section", id=identity("focus"),
            revision=1, props={"recordId": None, "presentation": "focus"}, content=[{"type": "text", "text": "ФОКУС", "styles": {}}],
            children=[], provenance=[])
        section.children.append(ParagraphBlock.model_validate(field_block(record, "display")))
        section.children = ordered_focus_children(section, project.facts)
        parent, after = positions[section.id][:2] if sections else ("sidebar", None)
        steps.append(PutBlock(kind="put_block", parentId=parent, afterId=after,
            beforeRevision=section.revision if sections else None, block=section))
    else:
        for original in sections:
            kept = [child for child in original.children if not matches(child)]
            if len(kept) == len(original.children):
                continue
            if not kept:
                steps.append(RemoveBlock(kind="remove_block", blockId=original.id, beforeRevision=original.revision))
            else:
                steps.extend(RemoveBlock(kind="remove_block", blockId=child.id, beforeRevision=child.revision)
                    for child in original.children if matches(child))
    return steps


def ordered_focus_children(section, facts):
    records = {record.id: record for record in facts.records}
    years = technology_years(facts)
    def key(block):
        record = focus_entry_record(block, records)
        return (False, *focus_sort_key(record, years)) if record else (True, True, 0, block.id)
    return sorted(section.children, key=key)


def focus_order_steps(workspace, steps):
    from .models.rich_mutations import MoveBlock, PutRecord, RemoveRecord
    preview = workspace.project.facts.model_copy(deep=True)
    changed = {step.record.id: step.record for step in steps if isinstance(step, PutRecord)}
    removed = {step.record_id for step in steps if isinstance(step, RemoveRecord)}
    preview.records = [changed.get(record.id, record) for record in preview.records if record.id not in removed]
    result = []
    for section in workspace.project.document.blocks():
        if section.type != "section" or section.props.presentation != "focus":
            continue
        current = [block.id for block in section.children]
        ordered = ordered_focus_children(section, preview)
        for index, block in enumerate(ordered):
            if current[index] != block.id:
                result.append(MoveBlock(kind="move_block", blockId=block.id, beforeRevision=block.revision,
                    parentId=section.id, afterId=ordered[index - 1].id if index else None))
                current.remove(block.id); current.insert(index, block.id)
    return result
