"""Translate a small content contract into source-preserving import drafts."""

from dataclasses import dataclass
import json
import re

from .import_agent import ImportFailure, checksum, update_draft
from .models.importing import ContentFact, ImportBatch, ImportBlock, ImportFact, ImportProfile, ImportTechnologyGroup


@dataclass(frozen=True)
class SourceParagraph:
    ref: str
    text: str
    keys: list[str]
    page: int | None
    hints: str = ""


def _source_hints(unit):
    cues = []
    location, structure = unit.location, unit.structure
    if structure and structure.part:
        if re.fullmatch(r"word/header\d*\.xml", structure.part):
            cues.append("header")
        elif re.fullmatch(r"word/footer\d*\.xml", structure.part):
            cues.append("footer")
    if location.kind == "table_cell":
        cues.append(f"table {location.index + 1}, row {location.row + 1}, cell {location.column + 1}")
    if structure:
        if structure.bounds:
            cues.append(f"x={structure.bounds[0]:g}, y={structure.bounds[1]:g}")
        if structure.column:
            cues.append(f"column {structure.column}")
        if structure.group:
            cues.append(f"visual group {structure.group}")
        if structure.gap_before is not None:
            cues.append(f"gap {structure.gap_before:g}pt")
        if structure.font_size:
            cues.append(f"font {structure.font_size:g}pt")
        if structure.bold:
            cues.append("bold")
        if structure.style:
            cues.append("style " + json.dumps(structure.style, ensure_ascii=False))
        if structure.heading_level:
            cues.append(f"heading {structure.heading_level}")
        if structure.list_level is not None:
            cues.append(f"list level {structure.list_level + 1}")
        if structure.column_span and structure.column_span > 1:
            cues.append(f"spans {structure.column_span} cells")
        if structure.row_merge:
            cues.append(f"vertical merge {structure.row_merge}")
        if structure.indent:
            cues.append(f"indent {structure.indent}")
        if structure.blank_before:
            cues.append(f"{structure.blank_before} blank lines before")
        if structure.layout_uncertain:
            cues.append("reading order uncertain")
    return "; ".join(cues)


def source_paragraphs(sources, parts):
    units = {(source.id, unit.id): unit for source in sources for unit in source.units}
    paragraphs, group, length, unit = [], [], 0, None

    def flush():
        if group:
            original = units[unit]
            location = original.location
            paragraphs.append(SourceParagraph(f"p{len(paragraphs) + 1}", "".join(p.text for p in group),
                [p.key for p in group], location.index + 1 if location.kind == "page" else None,
                _source_hints(original)))

    for part in parts:
        current = (part.evidence["sourceId"], part.evidence["unitId"])
        if group and (current != unit or length + len(part.text) > 4000):
            flush()
            group, length = [], 0
        unit = current
        group.append(part)
        length += len(part.text)
    flush()
    return paragraphs


def resolve_refs(refs, paragraphs):
    selected = {}
    for ref in refs:
        match = re.fullmatch(r"p([1-9][0-9]*)(?:\s*[-–—]\s*p?([1-9][0-9]*))?", ref.strip())
        start, end = (int(match[1]), int(match[2] or match[1])) if match else (0, 0)
        if not 1 <= start <= end <= len(paragraphs):
            raise ImportFailure("IMPORT_REFERENCE_INVALID")
        for paragraph in paragraphs[start - 1:end]:
            selected[paragraph.ref] = paragraph
    return list(selected.values())


def source_keys(refs, paragraphs):
    keys = [key for paragraph in resolve_refs(refs, paragraphs) for key in paragraph.keys]
    if len(keys) > 1000:
        raise ImportFailure("IMPORT_EVIDENCE_TOO_LARGE")
    return keys


def paragraph_refs(keys, paragraphs):
    by_key = {key: paragraph.ref for paragraph in paragraphs for key in paragraph.keys}
    return list(dict.fromkeys(by_key[key] for key in keys if key in by_key))


def section_region(category):
    return ("header" if category == "identity" else "sidebar"
        if category in {"contacts", "education", "skills", "languages"} else "main")


def content_blocks(sections, paragraphs):
    blocks = []
    for index, section in enumerate(sections):
        region = "header" if section.category == "identity" else section.region or section_region(section.category)
        if section.blocks:
            if section.heading.strip() and section.category != "identity":
                blocks.append(ImportBlock(id=f"outline_{index}_heading", kind="section", region=region,
                    title=section.heading, category=section.category))
            for number, block in enumerate(section.blocks):
                blocks.append(ImportBlock(id=f"outline_{index}_block{number}",
                    sourceKeys=source_keys(block.refs, paragraphs), region=region,
                    kind="bullet_list" if block.type == "list_item" else block.type,
                    category=section.category, modelBlock=True, listItem=block.type == "list_item",
                    duplicateOf=source_keys(block.duplicate_of, paragraphs), reason=block.reason, text=block.text))
                if len(blocks) > 5000:
                    raise ImportFailure("IMPORT_DRAFT_TOO_LARGE")
            continue
        selected = resolve_refs(section.refs, paragraphs)
        items = [resolve_refs(refs, paragraphs) for refs in section.list_items]
        selected_refs = {paragraph.ref for paragraph in selected}
        for item in items:
            for paragraph in item:
                if paragraph.ref not in selected_refs:
                    selected.append(paragraph)
                    selected_refs.add(paragraph.ref)
        membership = {}
        for number, item in enumerate(items):
            for paragraph in item:
                membership.setdefault(paragraph.ref, []).append(number)
        emitted = set()
        heading = " ".join(section.heading.split()).casefold()
        first = " ".join(selected[0].text.split()).casefold() if selected else ""
        source_heading = bool(heading and (first == heading or first.startswith(heading + ":")))
        if section.heading.strip() and not source_heading and section.category != "identity":
            blocks.append(ImportBlock(id=f"outline_{index}_heading", kind="section", region=region,
                title=section.heading, category=section.category))
        for position, paragraph in enumerate(selected):
            if paragraph.ref in membership:
                for number in membership[paragraph.ref]:
                    if number not in emitted:
                        blocks.append(ImportBlock(id=f"outline_{index}_item{number}",
                            sourceKeys=[key for part in items[number] for key in part.keys],
                            region=region, kind="bullet_list", category=section.category, listItem=True))
                        if len(blocks) > 5000:
                            raise ImportFailure("IMPORT_DRAFT_TOO_LARGE")
                        emitted.add(number)
                continue
            kind = ("heading" if section.category == "identity" else "section" if source_heading and position == 0
                else "bullet_list" if paragraph.text.lstrip().startswith(("• ", "- ", "— ")) else "paragraph")
            blocks.append(ImportBlock(id=f"outline_{index}_{paragraph.ref}", sourceKeys=paragraph.keys,
                region=region, kind=kind, category=section.category))
            if len(blocks) > 5000:
                raise ImportFailure("IMPORT_DRAFT_TOO_LARGE")
    return blocks


def update_content(draft, request, paragraphs, parts):
    facts = (draft.facts if request.facts is None else [ImportFact(id=f"content_fact_{index}",
        text=fact.text if isinstance(fact, ContentFact) else "",
        record=None if isinstance(fact, ContentFact) else fact.model_dump(exclude={"refs"}),
        sourceKeys=source_keys(fact.refs, paragraphs)) for index, fact in enumerate(request.facts)])
    blocks = draft.blocks if request.sections is None else content_blocks(request.sections, paragraphs)
    profile = (draft.profile if request.profile is None else ImportProfile(name=request.profile.name,
        title=request.profile.title, location=request.profile.location,
        sourceKeys=source_keys(request.profile.refs, paragraphs)))
    technology_groups = (draft.technology_groups if request.technology_groups is None else [
        ImportTechnologyGroup(heading=group.heading, region=group.region, technologies=group.technologies,
            sourceKeys=source_keys(group.refs, paragraphs)) for group in request.technology_groups])
    if draft.finished:
        raise ImportFailure("IMPORT_STALE_BATCH")
    if (facts, blocks, profile, technology_groups) == (draft.facts, draft.blocks, draft.profile, draft.technology_groups):
        return draft.model_copy(deep=True)
    fact_ids, block_ids = {item.id for item in facts}, {item.id for item in blocks}
    batch = ImportBatch(batchId="content_" + checksum([draft.sequence, request]), sequence=draft.sequence,
        facts=facts, blocks=blocks, profile=profile, technologyGroups=technology_groups,
        removeFactIds=[f.id for f in draft.facts if f.id not in fact_ids],
        removeBlockIds=[b.id for b in draft.blocks if b.id not in block_ids])
    updated = update_draft(draft, batch, parts)[0]
    by_fact, by_block = {item.id: item for item in updated.facts}, {item.id: item for item in updated.blocks}
    updated.facts = [by_fact[fact.id] for fact in facts]
    updated.blocks = [by_block[block.id] for block in blocks]
    return updated


def draft_content(draft, paragraphs):
    items = [{"profile": {"name": draft.profile.name, "title": draft.profile.title,
        "location": draft.profile.location, "refs": paragraph_refs(draft.profile.source_keys, paragraphs)}}]
    if draft.technology_groups:
        items.append({"technologyGroups": [{"heading": group.heading, "region": group.region, "technologies": group.technologies,
            "refs": paragraph_refs(group.source_keys, paragraphs)} for group in draft.technology_groups]})
    items.extend({"fact": {**(fact.record.model_dump(by_alias=True) if fact.record else {"text": fact.text}),
        "refs": paragraph_refs(fact.source_keys, paragraphs)}}
        for fact in draft.facts)
    outlines = {}
    for block in draft.blocks:
        group = block.id.rsplit("_", 1)[0]
        outlines.setdefault(group, []).append(block)
    for blocks in outlines.values():
        outline = {"category": blocks[0].category or "other", "heading": ""}
        if blocks[0].region != section_region(outline["category"]) and blocks[0].region != "header":
            outline["region"] = blocks[0].region
        explicit = any(block.model_block for block in blocks)
        outline["blocks" if explicit else "refs"] = []
        for block in blocks:
            refs = paragraph_refs(block.source_keys, paragraphs)
            if explicit and block.model_block:
                value = {"type": "list_item" if block.list_item else block.kind, "refs": refs}
                if block.duplicate_of:
                    value["duplicateOf"] = paragraph_refs(block.duplicate_of, paragraphs)
                if block.reason is not None:
                    value["reason"] = block.reason
                if block.text is not None:
                    value["text"] = block.text
                outline["blocks"].append(value)
            else:
                if block.kind == "section":
                    outline["heading"] = block.title or "".join(p.text for p in paragraphs
                        if set(block.source_keys).intersection(p.keys)).strip()
                if not explicit:
                    outline["refs"].extend(refs)
                    if block.list_item:
                        outline.setdefault("listItems", []).append(refs)
        items.append({"section": outline})
    return items
