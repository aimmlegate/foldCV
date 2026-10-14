"""Initial rich assembly from ephemeral normalization/drafting results."""

import uuid

from .dates import partial_date
from .models.rich_workspace import ProjectV5
from .rendering.rich_template import require_rich_template


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


def assemble_rich(workspace, normalized, draft, rules):
    records, evidence_records = [], []
    source_units = {(s.id, u.id): u for s in normalized.sources for u in s.units}
    evidence_by_fact = {}
    for fact in normalized.facts:
        spans = list(getattr(fact, "literal_evidence", []))
        if not spans:
            spans = [{**item.model_dump(by_alias=True), "text": source_units[(item.source_id, item.unit_id)].text}
                     for item in fact.evidence if (item.source_id, item.unit_id) in source_units]
        spans = [s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s for s in spans]
        evidence_by_fact[fact.id] = spans
        evidence_records.append({"id": fact.id, "evidence": spans, "rawText": "\n".join(s["text"] for s in spans)})

    def record(kind, identifier, evidence, **values):
        item = {"id": identifier, "kind": kind, "revision": 1, "origin": "source", "evidence": evidence, **values}
        records.append(item)
        return item

    def spans_for(authored):
        return [span for fact_id in authored.fact_ids for span in evidence_by_fact.get(fact_id, [])]

    candidate = draft.document.candidate
    record("candidate", "candidate", [s.model_dump(by_alias=True) for part in (
        normalized.candidate.name, normalized.candidate.title, normalized.candidate.location) for s in part.evidence],
        name=field(normalized.candidate.name.text), title=field(normalized.candidate.title.text), location=field(normalized.candidate.location.text))
    for index, detail in enumerate(candidate.details):
        detected = next((item.kind for item in normalized.private_details if item.value.text == detail.text), "other")
        record("detail", detail.field_id, spans_for(detail), detailType={"platform_metadata": "metadata"}.get(detected, detected),
            label="", value=field(detail.text))
    jobs = {job.id: job for job in normalized.employment}
    for job in normalized.employment:
        periods = []
        for period in normalized.job_periods.get(job.id, []):
            periods.append({"id": period.id, "revision": 1, "start": field(period.start, period.start_text),
                "end": field(period.end, period.end_text), "present": field(period.present),
                "evidence": [s.model_dump(by_alias=True) for s in period.evidence]})
        record("employment", job.id, [span for fact_id in job.fact_ids for span in evidence_by_fact.get(fact_id, [])],
            employer=field(job.employer), role=field(job.role), periods=periods)
        for sub in job.subprojects:
            record("subproject", sub.id, [span for fact_id in sub.fact_ids for span in evidence_by_fact.get(fact_id, [])],
                jobId=job.id, name=field(sub.name), role=field(None), periods=([{"id": identity("period"), "revision": 1, "start": field(sub.period.start),
                    "end": field(sub.period.end), "present": field(None), "evidence": []}] if sub.period else []))
    for item in normalized.education:
        record("education", item.id, [s.model_dump(by_alias=True) for part in (item.institution, item.qualification, item.specialty, item.date_text) for s in part.evidence],
            institution=field(item.institution.text), qualification=field(item.qualification.text), specialty=field(item.specialty.text),
            completion=date_field(item.date_text.text))
    for item in normalized.languages:
        record("language", item.id, [s.model_dump(by_alias=True) for part in (item.name, item.proficiency) for s in part.evidence],
            language=field(item.name.text), level=field(item.proficiency.text))
    for item in normalized.certifications:
        record("certification", item.id, [s.model_dump(by_alias=True) for part in (item.name, item.issuer, item.date_text) for s in part.evidence],
            name=field(item.name.text), issuer=field(item.issuer.text), date=date_field(item.date_text.text))
    aliases = {}
    record_ids = {item["id"] for item in records}
    for fact in normalized.facts:
        if fact.kind == "employment":
            aliases[fact.id] = fact.value.job_id
        elif fact.kind == "candidate_detail":
            target = fact.value.field_id
            if fact.value.field in {"name", "title", "location"}:
                target = "candidate"
            if target in record_ids:
                aliases[fact.id] = target
    mapped_fact_ids = set(aliases)
    for fact in normalized.facts:
        if fact.kind in {"text", "technology", "metric", "leadership"}:
            values = {"jobId": fact.job_id, "subprojectId": fact.subproject_id}
            if fact.kind == "technology":
                values.update(display=field(fact.value.display), canonicalId=field(fact.value.canonical_id))
            else:
                values["value"] = field(fact.value.text if fact.kind == "text" else fact.value)
            record("claim" if fact.kind == "text" else fact.kind, fact.id, evidence_by_fact[fact.id], **values)
            mapped_fact_ids.add(fact.id)
        elif fact.kind not in {"employment", "candidate_detail", "name_assessment", "source_observation"}:
            record("unresolved", fact.id, evidence_by_fact[fact.id], category="other", status="unresolved")
            mapped_fact_ids.add(fact.id)

    def inline(authored, owner=None, key=None):
        if owner is not None and key is not None:
            return [{"type": "fact_field", "bindingId": identity("binding"), "recordId": owner,
                "fieldKey": key, "text": authored.text, "styles": {}, "syncedFactRevision": 1}]
        return [{"type": "text", "text": authored.text, "styles": {}}]

    def block(authored, owner=None, key=None, kind="paragraph", level=1, technology_scope=None):
        citations = [{"kind": "citation", "id": identity("citation"), "recordId": aliases.get(fact_id, fact_id), "fieldKeys": [],
            "evidence": evidence_by_fact.get(fact_id, [])} for fact_id in authored.fact_ids if fact_id in mapped_fact_ids]
        uncited = [span for fact_id in authored.fact_ids if fact_id not in mapped_fact_ids for span in evidence_by_fact.get(fact_id, [])]
        if uncited:
            citations.append({"kind": "source", "id": identity("source-link"), "evidence": uncited})
        result = {"id": authored.field_id, "revision": 1, "type": kind,
            "props": {"level": level} if kind == "heading" else {}, "content": inline(authored, owner, key),
            "children": [], "provenance": citations}
        if technology_scope is not None:
            technologies = [item for item in records if item["kind"] == "technology" and item.get("jobId") == technology_scope
                and item["id"] in authored.fact_ids and item["display"]["rawText"]]
            # Only a scoped cited token is exact; narrative/global matching never creates an association.
            text, cursor, spans = authored.text, 0, []
            matches = []
            import re
            for item in technologies:
                for match in re.finditer(r"(?<!\w)" + re.escape(item["display"]["rawText"]) + r"(?!\w)", text, re.I):
                    matches.append((match.start(), match.end(), item))
            for start, end, item in sorted(matches, key=lambda match: (match[0], -(match[1] - match[0]))):
                if start < cursor:
                    continue
                if start > cursor:
                    spans.append({"type": "text", "text": text[cursor:start], "styles": {}})
                spans.append({"type": "fact_field", "bindingId": identity("binding"), "recordId": item["id"],
                    "fieldKey": "display", "text": text[start:end], "styles": {}, "syncedFactRevision": 1})
                cursor = end
            if spans:
                if cursor < len(text):
                    spans.append({"type": "text", "text": text[cursor:], "styles": {}})
                result["content"] = spans
        if owner is not None:
            result["provenance"].append({"kind": "field_binding", "id": identity("binding"), "recordId": owner, "fieldKey": key})
        return result

    def section(identifier, title, children, owner=None, presentation="standard"):
        return {"id": identifier, "revision": 1, "type": "section", "props": {"recordId": owner, "presentation": presentation},
            "content": [{"type": "text", "text": title, "styles": {}}], "children": children, "provenance": []}

    header = [block(candidate.name, "candidate", "name", "heading", 1), block(candidate.title, "candidate", "title", "heading", 2)]
    sidebar = [block(candidate.location, "candidate", "location")]
    sidebar.extend(block(detail, detail.field_id, "value") for detail in candidate.details)
    focus = [block(entry.display) for entry in draft.document.skills_focus.focus]
    sidebar.append(section("focus", "FOCUS", focus, presentation="focus"))
    for group, mapping in ((draft.document.education, {"institution": "institution", "qualification": "qualification", "specialty": "specialty", "date_text": "completion"}),
                           (draft.document.certifications, {"name": "name", "issuer": "issuer", "date_text": "date"}),
                           (draft.document.languages, {"name": "language", "proficiency": "level"})):
        for item in group:
            if not item.visible:
                continue
            if item.id not in {record["id"] for record in records}:
                record("unresolved", item.id, spans_for(item.legacy_text) if item.legacy_text else [],
                    category="education" if "institution" in mapping else "language" if "proficiency" in mapping else "certification", status="unresolved")
            if item.legacy_text:
                records[:] = [entry for entry in records if entry["id"] != item.id]
                record("unresolved", item.id, spans_for(item.legacy_text),
                    category="education" if "institution" in mapping else "language" if "proficiency" in mapping else "certification", status="unresolved")
                # Unparsed source stays rich prose; it cannot become a competing typed field.
                children = [block(item.legacy_text)]
            else:
                children = [block(getattr(item, key), item.id, target) for key, target in mapping.items()]
            sidebar.append(section("section-" + item.id, "", children, item.id))
    main = [section("profile", "", [block(draft.document.profile.text)])]
    for job in draft.document.jobs:
        if not job.visible:
            continue
        children = [block(job.employer, job.id, "employer", "heading", 2), block(job.role, job.id, "role")]
        for period in job.periods:
            start = block(period.start_text, job.id, "period:" + period.id + ":start")
            end_text = period.end_text.model_copy(deep=True)
            if period.present and not end_text.text:
                end_text.text = "Present" if draft.editorial_plan.source_language == "en" else "по настоящее время"
            end = block(end_text, job.id, "period:" + period.id + (":present" if period.present else ":end"))
            start["content"].extend([{"type": "text", "text": " — ", "styles": {}}, *end["content"]])
            start["provenance"].extend(end["provenance"])
            children.append(start)
        children.extend(block(part) for part in (job.context, job.tasks, job.results))
        children.append(block(job.stack, technology_scope=job.id))
        for sub in jobs.get(job.id).subprojects if job.id in jobs else []:
            from .models.recovery import AuthoredField
            source_facts = [fact for fact in normalized.facts if fact.subproject_id == sub.id]
            details = [block(AuthoredField(fieldId=identity("subproject-name"), text=sub.name, factIds=sub.fact_ids,
                evidence=[], origin="source"), sub.id, "name", "heading", 3)]
            working_sub = next(item for item in records if item["id"] == sub.id)
            for period in working_sub["periods"]:
                for part in ("start", "end"):
                    details.append(block(AuthoredField(fieldId=identity("subproject-date"), text=period[part]["rawText"],
                        factIds=sub.fact_ids, evidence=[], origin="source"), sub.id, "period:" + period["id"] + ":" + part))
            for fact in source_facts:
                text = fact.value.text if fact.kind == "text" else fact.value.display if fact.kind == "technology" else None
                if text:
                    details.append(block(AuthoredField(fieldId=identity("subproject-fact"), text=text, factIds=[fact.id], evidence=[], origin="source"),
                        technology_scope=job.id if fact.kind == "technology" else None))
            children.append(section("section-" + sub.id, "", details, sub.id))
        if job.id not in jobs:
            record("employment", job.id, spans_for(job.employer), employer=field(job.employer.text), role=field(job.role.text), periods=[])
        main.append(section("section-" + job.id, "", children, job.id))
    main.append(section("early-career", "", [block(draft.document.early_career.text)]))
    main.append(section("skills", "", [block(draft.document.skills_focus.skills_text)]))
    return ProjectV5.model_validate({"schemaVersion": 5, "projectId": workspace.project_id,
        "revision": workspace.project_revision + 1, "createdAt": workspace.created_at,
        "sources": [source.model_dump(by_alias=True) for source in normalized.sources], "evidenceRecords": evidence_records,
        "facts": {"revision": 1, "records": records, "tombstones": []},
        "document": {"schemaVersion": 1, "revision": workspace.document_revision + 1, "regions": [
            {"id": "header", "role": "header", "revision": 1, "blocks": header},
            {"id": "sidebar", "role": "sidebar", "revision": 1, "blocks": sidebar},
            {"id": "main", "role": "main", "revision": 1, "blocks": main}]}, "assets": [],
        "operations": [op.model_dump(by_alias=True) for op in workspace.pre_draft.operations], "renders": [],
        "template": require_rich_template().manifest.model_dump(by_alias=True)})
