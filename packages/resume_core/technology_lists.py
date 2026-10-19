"""Keep explicit technology lists editable without changing surrounding prose."""

import re
from pydantic import TypeAdapter

from .models.rich_document import RichBlock, FactFieldSpan, StyledText
from .models.rich_mutations import PutBlock, RemoveBlock
from .rich_assembly import identity
from .rich_dependencies import placements
from .rich_fields import inline_groups
from .rich_mutations import cut_inline, inline_text
from .technologies import resolve_technology, technology_identity

SEPARATOR = re.compile(r"\s*[,;·|]\s*")


def list_parts(content, records):
    if not content:
        return None
    fields = [span for span in content if isinstance(span, FactFieldSpan)]
    if not fields or any(span.field_key != "display" or span.record_id not in records
            or records[span.record_id].kind != "technology" for span in fields):
        return None
    prefix, suffix, entries = [], [], []
    pending = []
    for span in content:
        if isinstance(span, FactFieldSpan):
            separated = bool(pending)
            if pending:
                text = "".join(inline_text(part) for part in pending)
                if not entries:
                    if text.strip() and not text.rstrip().endswith(":"):
                        return None
                    prefix = pending
                elif not SEPARATOR.fullmatch(text):
                    return None
                pending = []
            if entries and entries[-1][0].record_id == span.record_id and not separated:
                entries[-1].append(span)
            else:
                entries.append([span])
        elif isinstance(span, StyledText):
            if span.text:
                pending.append(span)
        else:
            return None
    if pending:
        text = "".join(span.text for span in pending)
        if text.strip() and text.strip() not in {".", ",", ";", "·", "|"}:
            return None
        suffix = pending if text.strip() == "." else []
    separator = next((span for span in content if isinstance(span, StyledText) and SEPARATOR.fullmatch(span.text)), None)
    return prefix, entries, separator, suffix


def rebuild(parts, entries):
    prefix, _before, separator, suffix = parts
    if not entries:
        return []
    result = list(prefix)
    for index, entry in enumerate(entries):
        if index:
            result.append(separator.model_copy(deep=True) if separator else StyledText(type="text", text=", ", styles={}))
        result.extend(entry)
    return result + suffix


def remove_from_prose(before, kept, records):
    retained = {id(span) for span in kept}
    result = []
    for index, span in enumerate(before):
        if id(span) in retained:
            result.append(span)
            continue
        if not isinstance(span, FactFieldSpan) or records.get(span.record_id) is None or records[span.record_id].kind != "technology":
            continue
        following = before[index + 1] if index + 1 < len(before) else None
        if isinstance(following, StyledText) and re.match(r"^\s*[,;·|]", following.text):
            following.text = re.sub(r"^\s*[,;·|]\s*", "", following.text, count=1)
        elif result and isinstance(result[-1], StyledText):
            result[-1].text = re.sub(r"\s*[,;·|]\s*$", "", result[-1].text, count=1)
    return [span for span in result if not isinstance(span, StyledText) or span.text]


def bind_lists(project, job_id):
    records = {r.id: r for r in project.facts.records}
    choices = {r.display.raw_text.casefold(): r for r in records.values() if r.kind == "technology" and r.job_id == job_id}
    aliases = {}
    for record in choices.values():
        aliases.setdefault(technology_identity(record), []).append(record)
    changed = set()
    def visit(blocks, owner=None, focus=False, tool_group=False):
        for block in blocks:
            current = getattr(block.props, "record_id", None) or owner
            is_focus = focus or getattr(block.props, "presentation", None) == "focus"
            linked = tool_group or current is not None or any(link.kind in {"citation", "field_binding"} for link in block.provenance)
            if linked and not is_focus and current == job_id and block.type in {"paragraph", "bullet_list", "numbered_list"}:
                for _, content in inline_groups(block):
                    if not all(isinstance(span, (StyledText, FactFieldSpan)) for span in content):
                        continue
                    text = "".join(inline_text(span) for span in content)
                    prefix = text.find(":") + 1 if ":" in text else 0
                    start = prefix
                    while start < len(text) and text[start].isspace(): start += 1
                    tokens = list(re.finditer(r"[^,;·|]+", text[start:]))
                    parsed = []
                    for token in tokens:
                        value = token.group().strip()
                        record = choices.get(value.casefold())
                        if record is None:
                            canonical = resolve_technology(value).canonical_id
                            matches = aliases.get(canonical, []) if canonical else []
                            record = matches[0] if len(matches) == 1 else None
                        if record is None:
                            parsed = []; break
                        lo = start + token.start() + len(token.group()) - len(token.group().lstrip())
                        parsed.append((record, lo, lo + len(value)))
                    if not parsed:
                        continue
                    updated, cursor = [], 0
                    for record, lo, hi in parsed:
                        def sliced(a, b):
                            return cut_inline(content, len(text[:a].encode("utf-16-le")) // 2, len(text[:b].encode("utf-16-le")) // 2)
                        updated.extend(sliced(cursor, lo))
                        fragments = sliced(lo, hi)
                        if all(isinstance(span, FactFieldSpan) and span.record_id == record.id and span.field_key == "display" for span in fragments):
                            updated.extend(fragments)
                        else:
                            binding = identity("binding")
                            updated.extend(FactFieldSpan(type="fact_field", bindingId=identity("binding"), bindingRootId=binding,
                                recordId=record.id, fieldKey="display", text=inline_text(span), styles=span.styles,
                                syncedFactRevision=record.display.revision) for span in fragments if hasattr(span, "styles"))
                        cursor = hi
                    updated.extend(cut_inline(content, len(text[:cursor].encode("utf-16-le")) // 2, len(text.encode("utf-16-le")) // 2))
                    if updated != content:
                        content[:] = updated; changed.add(block.id)
            visit(block.children, current, is_focus, tool_group or block.id.startswith("technology_group_"))
    for region in project.document.regions:
        visit(region.blocks)
    return changed


def bind_edit_lists(project, job_id):
    changed = bind_lists(project, job_id)
    if job_id is None:
        # Older imports may bind a job stack to a same-named global fact.
        for record in project.facts.records:
            if record.kind == "employment":
                changed |= bind_lists(project, record.id)
    return changed


def locations(project, job_id):
    records = {r.id: r for r in project.facts.records}
    result = []
    def visit(blocks, focus=False, owner=None, grouped=False):
        for block in blocks:
            current = getattr(block.props, "record_id", None) or owner
            tool_group = grouped or block.id.startswith("technology_group_")
            inside_focus = focus or getattr(block.props, "presentation", None) == "focus"
            if not inside_focus and current == job_id:
                for _, content in inline_groups(block):
                    parts = list_parts(content, records)
                    if parts and (job_id is None and tool_group or all(records[entry[0].record_id].job_id == job_id for entry in parts[1])):
                        result.append((block, content, parts))
            visit(block.children, inside_focus, current, tool_group)
    for region in sorted(project.document.regions, key=lambda region: region.role != "main"):
        visit(region.blocks)
    return result


def sync_links(block):
    fields = [span for _, content in inline_groups(block) for span in content if isinstance(span, FactFieldSpan)]
    value = block.model_dump(by_alias=True)
    value["provenance"] = [link for link in value["provenance"] if link["kind"] != "field_binding"]
    value["provenance"].extend({"kind": "field_binding", "id": span.binding_id, "recordId": span.record_id,
        "fieldKey": span.field_key} for span in fields)
    return TypeAdapter(RichBlock).validate_python(value)



def patch_lists(original, changed):
    from .rich_panel import put_block
    positions = placements(original.document)
    before = {b.id: b for b in original.document.blocks()}
    steps = []
    for block in changed.document.blocks():
        if block.model_dump(exclude={"children"}) != before[block.id].model_dump(exclude={"children"}):
            steps.append(put_block(sync_links(block), positions))
    return steps


def additional_bindings(project, steps, bindings):
    replaced = {step.block.id if isinstance(step, PutBlock) else step.block_id for step in steps if isinstance(step, (PutBlock, RemoveBlock))}
    removed = {step.block_id for step in steps if isinstance(step, RemoveBlock)}
    def exclude(blocks, inherited=False):
        for block in blocks:
            hidden = inherited or block.id in removed
            if hidden:
                replaced.add(block.id)
            exclude(block.children, hidden)
    for region in project.document.regions:
        exclude(region.blocks)
    return [step for step in bindings if step.block.id not in replaced]


def prune_empty_lists(project, steps):
    positions = placements(project.document)
    blocks = {block.id: block for block in project.document.blocks()}
    empty = {step.block.id for step in steps if isinstance(step, PutBlock) and not step.block.content
        and not blocks[step.block.id].children and (positions[step.block.id][0].startswith("technology_group_")
            or getattr(getattr(blocks.get(positions[step.block.id][0]), "props", None), "presentation", None) == "focus"
            or getattr(blocks.get(positions[step.block.id][0]), "props", None) is not None
                and getattr(blocks[positions[step.block.id][0]].props, "record_id", None) is not None)
        and any(isinstance(span, FactFieldSpan) and span.field_key == "display"
            for _, content in inline_groups(blocks[step.block.id]) for span in content)}
    groups = {block.id for block in blocks.values() if block.type == "section" and (block.id.startswith("technology_group_") or block.props.presentation == "focus")
        and block.children and all(child.id in empty for child in block.children)}
    removed = groups | {identifier for identifier in empty if positions[identifier][0] not in groups}
    return [step for step in steps if not isinstance(step, PutBlock) or step.block.id not in empty | groups] + [
        RemoveBlock(kind="remove_block", blockId=identifier, beforeRevision=blocks[identifier].revision) for identifier in sorted(removed)]


def insert_technology(project, record, before_id=None, moving=False):
    from .rich_panel import field_block, put_block
    original = project
    project = project.model_copy(deep=True)
    bind_lists(project, record.job_id)
    places = locations(project, record.job_id)
    if before_id == record.id:
        return []
    positions = placements(project.document)
    grouped = [row for row in places if positions[row[0].id][0].startswith("technology_group_")]
    preferred = grouped or places
    destination = next((row for row in [*preferred, *places] if any(entry[0].record_id == before_id for entry in row[2][1])), None) if before_id else (preferred[-1] if preferred else None)
    if before_id and destination is None:
        raise ValueError("TECHNOLOGY_TARGET_MISSING")
    if destination:
        for block, content, parts in places:
            entries = [entry for entry in parts[1] if not moving or entry[0].record_id != record.id]
            if block.id == destination[0].id and content is destination[1]:
                index = next((index for index, entry in enumerate(entries) if entry[0].record_id == before_id), len(entries))
                existing = next((entry for _, _, source in places for entry in source[1] if entry[0].record_id == record.id), None) if moving else None
                if existing:
                    entry = [span.model_copy(deep=True) for span in existing]
                else:
                    span = FactFieldSpan.model_validate(field_block(record, "display")["content"][0])
                    span.styles = (entries[min(index, len(entries)-1)][0].styles.model_copy(deep=True) if entries else parts[1][0][0].styles.model_copy(deep=True))
                    entry = [span]
                entries.insert(index, entry)
            content[:] = rebuild(parts, entries)
        return prune_empty_lists(original, patch_lists(original, project))
    steps = patch_lists(original, project)
    owner = next((b for b in project.document.blocks() if getattr(b.props, "record_id", None) == record.job_id), None) if record.job_id else None
    block = TypeAdapter(RichBlock).validate_python(field_block(record, "display"))
    if owner:
        steps.append(PutBlock(kind="put_block", parentId=owner.id, afterId=owner.children[-1].id if owner.children else None, beforeRevision=None, block=block))
    else:
        main = next(r for r in project.document.regions if r.role == "main")
        group = {"id": identity("technology_group"), "revision": 1, "type": "section", "props": {"recordId": record.job_id},
            "content": [{"type": "text", "text": "НАВЫКИ", "styles": {}}], "children": [block.model_dump(by_alias=True)], "provenance": []}
        steps.append(PutBlock(kind="put_block", parentId=main.id, afterId=main.blocks[-1].id if main.blocks else None,
            beforeRevision=None, block=TypeAdapter(RichBlock).validate_python(group)))
    return steps
