"""Apply template roles to current authored content without drafting prose."""

import hashlib
import re

from .models.rich_document import RichDocumentV1
from .models.rich_mutations import PutBlock, RemoveBlock
from .rich_presentation import authored_text


def compact(text):
    return " ".join(text.split()).casefold()


SECTION_ROLES = (
    ("profile", "main", r"о\s+себе|профиль|profile|about(?:\s+me)?|summary"),
    ("employment", "main", r"опыт\s+работы|профессиональный\s+опыт.*|проекты|work\s+experience|employment|projects|career\s+history"),
    ("skills", "sidebar", r"ключевые\s+навыки|технические\s+навыки|навыки|фокус|focus|(?:technical\s+)?skills|technologies"),
    ("education", "sidebar", r"образование(?:\s+и\s+сертификации)?|education"),
    ("certifications", "sidebar", r"сертификаты|сертификации|повышение\s+квалификации\s+и\s+курсы|курсы|тесты|certifications|certificates|courses"),
    ("languages", "sidebar", r"знание\s+языков|языки|languages"),
    ("details", "sidebar", r"контакты(?:\s+и\s+ссылки)?|contacts?|локация|location|желаемая\s+должность|тип\s+занятости|формат\s+работы|опыт\s+вождения|дополнительно|рекомендации|сфера\s+работы|дата\s+обновления\s+резюме\s+кандидатом"),
)


def section_role(text):
    text = compact(text).rstrip(":")
    return next(((key, region) for key, region, pattern in SECTION_ROLES if re.fullmatch(pattern, text, re.I)), None)


def stable_id(*parts):
    return "template-" + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:24]


def section(key, text, first, *, record=None, focus=False):
    return {"id": stable_id(key, first), "revision": 1, "type": "section",
        "props": {"recordId": record, "presentation": "focus" if focus else "standard"},
        "content": [{"type": "text", "text": text, "styles": {}}] if text else [], "children": [], "provenance": []}


def format_document(document, facts):
    # Imports already carry interpreted layout; a fixed taxonomy cannot rebuild it.
    if facts.mode in {"digest", "imported"}:
        return document.model_copy(deep=True)
    body = [block for region in document.regions[1:] for block in region.blocks]
    if document.regions[0].blocks and body and all(block.type == "section" for block in body):
        return document.model_copy(deep=True)
    records = {record.id: record for record in facts.records}
    groups, jobs, header, named, headings = {}, {}, [], set(), set()
    state, region, current_job = "additional", "main", None

    def authored_blocks(blocks):
        for block in blocks:
            if block.type == "section" and block.props.record_id is None:
                if block.content:
                    from .models.rich_document import HeadingBlock
                    yield HeadingBlock(id=block.id, revision=block.revision, type="heading", props={"level": 2},
                        content=block.content, children=[], provenance=block.provenance)
                yield from authored_blocks(block.children)
            else:
                yield block

    def group(key, target, first, label=None):
        if key not in groups:
            labels = {"additional": "ДОПОЛНИТЕЛЬНЫЕ СВЕДЕНИЯ", "details": "СВЕДЕНИЯ", "employment": "ОПЫТ РАБОТЫ",
                "profile": "О СЕБЕ", "skills": "НАВЫКИ", "education": "ОБРАЗОВАНИЕ", "languages": "ЯЗЫКИ", "certifications": "СЕРТИФИКАТЫ"}
            groups[key] = (target, section(key, label if label is not None else labels[key], first, focus=key == "skills"))
        return groups[key][1]

    for area in document.regions:
        for original in authored_blocks(area.blocks):
            block = original.model_dump(mode="json", by_alias=True)
            primary = getattr(original.props, "record_id", None)
            if original.type == "section" and getattr(records.get(primary), "kind", None) == "employment":
                state, region, current_job = "employment", "main", primary
                parent = group("employment", "main", original.id)
                jobs[primary] = block
                parent["children"].append(block)
                continue
            primary_kind = getattr(records.get(primary), "kind", None)
            if original.type == "section" and primary_kind in {"education", "language", "certification", "detail"}:
                state = {"language": "languages", "certification": "certifications", "detail": "details"}.get(primary_kind, primary_kind)
                region, current_job = "sidebar", None
                group(state, region, original.id)["children"].append(block)
                continue
            text = authored_text(original)
            spans = original.content if isinstance(original.content, list) else []
            fields = [span for span in spans if getattr(span, "type", None) == "fact_field"]
            exact = [span for span in fields if compact(span.text) == compact(text)]
            candidate = next((span for span in exact if getattr(records.get(span.record_id), "kind", None) == "candidate"
                and span.field_key in {"name", "title"}), None)
            if candidate is not None and candidate.field_key not in named:
                named.add(candidate.field_key)
                block.update(type="heading", props={**block["props"], "level": 1 if candidate.field_key == "name" else 2})
                header.append(block)
                continue
            role = section_role(text)
            if role is not None and original.type not in {"table", "image", "code"}:
                state, region = role
                current_job = None
                target = group(state, region, original.id, text)
                # Source headings keep their own identity and provenance.
                if state not in headings:
                    headings.add(state)
                    target["content"] = block["content"]
                    target["provenance"] = block["provenance"]
                    target["children"].extend(block["children"])
                else:
                    target["children"].append(block)
                continue
            associated = {getattr(records.get(span.record_id), "kind", None) for span in fields}
            side_kind = next((kind for kind in ("education", "language", "certification", "detail") if kind in associated), None)
            global_skills = fields and all(getattr(records.get(span.record_id), "kind", None) == "technology"
                and records[span.record_id].job_id is None for span in fields)
            if side_kind or global_skills:
                state = "skills" if global_skills else {"language": "languages", "certification": "certifications", "detail": "details"}.get(side_kind, side_kind)
                region, current_job = "sidebar", None
            owner = next((records.get(span.record_id) for span in fields
                if getattr(records.get(span.record_id), "kind", None) == "employment" and span.field_key == "employer"
                and compact(text).startswith(compact(span.text))), None)
            if owner is not None:
                state, region, current_job = "employment", "main", owner.id
                block.update(type="heading", props={**block["props"], "level": 2})
            inherited = getattr(original.props, "record_id", None)
            if inherited is not None and getattr(records.get(inherited), "kind", None) == "employment":
                state, region, current_job = "employment", "main", inherited
            if state == "employment" and current_job:
                parent = group("employment", "main", original.id)
                if current_job not in jobs:
                    jobs[current_job] = section("job", "", current_job, record=current_job)
                    parent["children"].append(jobs[current_job])
                jobs[current_job]["children"].append(block)
                continue
            if state == "additional" and associated & {"candidate", "detail"}:
                group("details", "sidebar", original.id)["children"].append(block)
            elif state == "additional" and associated & {"education", "language", "certification"}:
                kind = next(kind for kind in ("education", "language", "certification") if kind in associated)
                key = {"language": "languages", "certification": "certifications"}.get(kind, kind)
                group(key, "sidebar", original.id)["children"].append(block)
            else:
                group(state, region, original.id)["children"].append(block)
    header.sort(key=lambda block: block["props"]["level"])
    order = {"profile": 0, "employment": 1, "skills": 2, "additional": 3,
        "education": 1, "certifications": 2, "languages": 3, "details": 4}
    regions = []
    for area in document.regions:
        blocks = header if area.role == "header" else [block for key, (target, block) in sorted(groups.items(), key=lambda item: order.get(item[0], 9))
            if target == area.role and (block["children"] or block["provenance"] or key in headings)]
        regions.append({**area.model_dump(mode="json", by_alias=True), "blocks": blocks})
    return RichDocumentV1.model_validate({**document.model_dump(mode="json", by_alias=True), "regions": regions})


def format_steps(document, facts):
    formatted = format_document(document, facts)
    if formatted == document:
        return []
    original = {block.id: block for block in document.blocks()}
    steps = [RemoveBlock(kind="remove_block", blockId=block.id, beforeRevision=block.revision)
        for region in document.regions for block in region.blocks]
    for region in formatted.regions:
        previous = None
        for block in region.blocks:
            steps.append(PutBlock(kind="put_block", parentId=region.id, afterId=previous,
                beforeRevision=original[block.id].revision if block.id in original else None, block=block))
            previous = block.id
    return steps
