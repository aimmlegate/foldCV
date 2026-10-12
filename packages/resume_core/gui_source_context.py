"""Read located provenance without changing state or inferring evidence."""

from .gui_selection import field_index, valid_selection
from .models.recovery import EvidenceSpan, SourceContext, SourceExcerpt, record_slot


def source_context(workspace, request) -> SourceContext:
    result = SourceContext(projectId=workspace.project_id, documentRevision=workspace.document_revision,
        status="no-evidence", excerpts=[], annotations=[], legacyText=[])
    if (workspace.project is None or request.project_id != workspace.project_id
        or request.document_revision != workspace.document_revision
        or request.selection is not None and (request.field_ids or not valid_selection(workspace, request.selection))):
        result.status = "stale"
        return result
    project = workspace.project
    indexed = field_index(project.document)
    ids = [span.field_id for span in request.selection.spans] if request.selection else request.field_ids
    if any(id not in indexed for id in ids) or len(ids) != len(set(ids)):
        result.status = "stale"
        return result
    if not ids:
        return result
    slots = {indexed[id][1] for id in ids}
    selected = {span.field_id: span.captured_text for span in request.selection.spans} if request.selection else {}
    sources = {source.id: source for source in project.sources}
    facts = {fact.id: fact for fact in project.facts}
    records = {record_slot(record): record for record in project.document.records()}
    anchor_owners = {id: slot for id, (_field, slot) in indexed.items()}
    anchor_owners.update({job.periods_field_id: record_slot(job) for job in project.document.jobs})
    anchor_owners[project.document.skills_focus.focus_field_id] = 'skills-focus'
    sections = {"education": "education", "language": "languages", "skills-focus": "skills-focus",
                "certification": "certifications", "early-career": "early-career"}
    seen = {}
    linked_facts = set()

    def excerpt(ref, relation, text=None):
        source = sources.get(ref.source_id)
        unit = next((unit for unit in source.units if unit.id == ref.unit_id), None) if source else None
        if (source is None or unit is None or ref.source_revision != source.revision or ref.unit_revision != unit.revision):
            return
        literal = text or unit.text
        if not literal or literal not in unit.text:
            return
        evidence = EvidenceSpan(**ref.model_dump(by_alias=True, exclude={"text"}), text=literal)
        key = (source.id, unit.id, literal)
        priority = {"exact": 0, "field": 1, "block": 2}
        previous = seen.get(key)
        if previous is None or priority[relation] < priority[previous.relation]:
            seen[key] = SourceExcerpt(evidence=evidence, relation=relation,
                page=unit.location.index if unit.location.kind == "page" else None)

    def fact_excerpts(fact, relation, capture=None):
        if fact.origin == "user":
            return
        linked_facts.add(fact.id)
        spans = getattr(fact, "literal_evidence", [])
        for span in spans:
            excerpt(span, "exact" if capture and span.text == capture else relation, span.text)
        represented = {(span.source_id, span.unit_id) for span in spans}
        for ref in fact.evidence:
            if (ref.source_id, ref.unit_id) not in represented:
                literal = getattr(fact.value, "text", None)
                excerpt(ref, "exact" if capture and literal == capture else relation, literal)

    source_fields = [id for id in ids if indexed[id][0].origin != "user"]
    for id in source_fields:
        field = indexed[id][0]
        represented = set()
        for fact_id in field.fact_ids:
            fact = facts.get(fact_id)
            if fact:
                fact_excerpts(fact, "field", selected.get(id))
                represented.update((ref.source_id, ref.unit_id) for ref in fact.evidence)
        for ref in field.evidence:
            if (ref.source_id, ref.unit_id) not in represented:
                excerpt(ref, "field")
    # Broader job context stays distinct from evidence of the field.
    for slot in {indexed[id][1] for id in source_fields}:
        if slot.startswith("job:"):
            job_id = slot.removeprefix("job:")
            for fact in project.facts:
                if fact.job_id == job_id:
                    fact_excerpts(fact, "block")
    for mark in workspace.annotations:
        anchor = mark.anchor
        relevant = anchor.kind == "document" or bool(set(mark.fact_ids) & linked_facts)
        if anchor.kind == "field":
            relevant = relevant or anchor.field_id in ids or anchor_owners.get(anchor.field_id) in slots
        if anchor.kind == "section":
            relevant = relevant or any(sections.get(records[slot].kind) == anchor.section_id for slot in slots)
        if relevant and not mark.resolved:
            result.annotations.append(mark.model_copy(deep=True))
    result.excerpts = list(seen.values())
    if workspace.legacy_data:
        result.legacy_text = [item.model_copy(deep=True) for item in workspace.legacy_data.unmapped_text
            if item.visible and set(item.fact_ids) & linked_facts]
    result.status = "evidence" if result.excerpts else "user-origin" if all(indexed[id][0].origin == "user" for id in ids) else "no-evidence"
    return result
